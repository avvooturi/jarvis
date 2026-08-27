import httpx
import threading

from core.state import RequestCancelled


class FastChatClient:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = None
        self._lock = threading.Lock()

    @property
    def available(self):
        return bool(self.api_key)

    def send(self, system_prompt: str, history, user_text: str, max_tokens: int = 180, cancel_event=None) -> str:
        if not self.available:
            raise RuntimeError('OPENROUTER_API_KEY is not configured')
        messages = [{'role': 'system', 'content': system_prompt}]
        for user, assistant in history[-4:]:
            messages.extend(({'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}))
        messages.append({'role': 'user', 'content': user_text})
        if cancel_event is not None and cancel_event.is_set():
            raise RequestCancelled('Fast model request cancelled')
        with httpx.Client(timeout=self.timeout) as client:
            with self._lock:
                self._client = client
            try:
                with client.stream(
                    'POST',
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization': f'Bearer {self.api_key}'},
                    json={'model': self.model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': 0.4},
                ) as response:
                    response.raise_for_status()
                    chunks = []
                    for chunk in response.iter_bytes():
                        if cancel_event is not None and cancel_event.is_set():
                            raise RequestCancelled('Fast model request cancelled')
                        chunks.append(chunk)
            finally:
                with self._lock:
                    self._client = None
        payload = b''.join(chunks)
        return httpx.Response(200, content=payload).json()['choices'][0]['message']['content'].strip()

    def cancel(self):
        with self._lock:
            client = self._client
        if client is not None:
            client.close()
