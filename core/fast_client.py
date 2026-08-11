import httpx


class FastChatClient:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def available(self):
        return bool(self.api_key)

    def send(self, system_prompt: str, history, user_text: str) -> str:
        if not self.available:
            raise RuntimeError('OPENROUTER_API_KEY is not configured')
        messages = [{'role': 'system', 'content': system_prompt}]
        for user, assistant in history[-4:]:
            messages.extend(({'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}))
        messages.append({'role': 'user', 'content': user_text})
        response = httpx.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization': f'Bearer {self.api_key}'},
            json={'model': self.model, 'messages': messages, 'max_tokens': 180, 'temperature': 0.4},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
