import logging
import yaml
from pathlib import Path

from config import Config
from core.interview import INTERVIEW_PROMPT, InterviewSession
from core.memory import MemoryStore


class ConversationManager:
    def __init__(self, config: Config):
        self.logger = logging.getLogger('ConversationManager')
        self.config = config
        self.is_muted = False
        self.history = []
        self.personality = config.default_personality
        self.personality_prompt = self._load_personality(self.personality)
        self.interview = InterviewSession(config.interview_reports_dir)
        self.memory = MemoryStore(
            config.memory_db_path,
            enabled=config.memory_enabled,
            retention_days=config.memory_retention_days,
            redact_sensitive=config.memory_redact_sensitive,
            export_dir=config.memory_export_dir,
        )
        self.interview.purge_reports(config.memory_retention_days)
        self.history = self.memory.recent_conversations(limit=5)
        self._confirm_forget_all = False
        self._confirm_forget_record = None

    def _load_personality(self, personality_name: str) -> str:
        persona_file = self.config.personalities_dir / f'{personality_name}.yaml'
        if not persona_file.exists():
            raise FileNotFoundError(f'Personality file not found: {persona_file}')
        with persona_file.open('r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh)
        return data.get('prompt', '')

    def set_personality(self, personality_name: str):
        self.personality = personality_name
        self.personality_prompt = self._load_personality(personality_name)

    def build_prompt(self, user_text: str) -> str:
        source_history = self.interview.turns if self.interview.active else self.history
        context = '\n'.join([f'User: {item[0]}\nAssistant: {item[1]}' for item in source_history[-5:]])
        voice_guidance = 'This response will be spoken aloud. Answer in at most three concise sentences unless the user explicitly asks for detail.'
        system_prompt = self.system_prompt
        prompt = f'{system_prompt}\n{voice_guidance}\n{context}\nUser: {user_text}\nAssistant:'
        return prompt

    @property
    def system_prompt(self):
        if self.interview.active:
            return f'{INTERVIEW_PROMPT}\n\nCANDIDATE LEARNING PROFILE:\n{self.memory.learning_profile()}'
        return self.personality_prompt

    def add_turn(self, user_text: str, assistant_text: str):
        safe_user = self.memory.sanitize(user_text)
        safe_assistant = self.memory.sanitize(assistant_text)
        self.history.append((safe_user, safe_assistant))
        self.interview.add_turn(user_text, assistant_text)
        mode = 'interview' if self.interview.active else 'assistant'
        self.memory.add_conversation(safe_user, safe_assistant, mode, self.personality)

    def handle_command(self, text: str):
        lowered = text.strip().lower()
        normalized = lowered.strip(' .!?')
        if normalized in {'/privacy', 'privacy', 'memory privacy'}:
            return {'action': 'memory_privacy'}
        if normalized in {'/private', 'private mode', 'memory off', '/memoryoff'}:
            return {'action': 'memory_persistence', 'value': False}
        if normalized in {'/memoryon', 'memory on', 'save memory'}:
            return {'action': 'memory_persistence', 'value': True}
        if normalized == '/exportmemory':
            return {'action': 'memory_export'}
        if normalized.startswith('/searchmemory '):
            return {'action': 'memory_search', 'value': text.strip()[len('/searchmemory '):].strip()}
        if normalized.startswith('/forgetmemory '):
            raw_id = normalized[len('/forgetmemory '):].strip()
            if raw_id.isdigit():
                self._confirm_forget_record = int(raw_id)
                return {
                    'action': 'message',
                    'value': f'This will permanently delete memory record {raw_id}. Type /confirmforgetmemory to continue.',
                    'remember': False,
                }
            return {'action': 'message', 'value': 'Use /forgetmemory followed by the numeric memory ID.', 'remember': False}
        if normalized == '/confirmforgetmemory':
            if self._confirm_forget_record is None:
                return {'action': 'message', 'value': 'No individual memory deletion is awaiting confirmation.', 'remember': False}
            record_id = self._confirm_forget_record
            self._confirm_forget_record = None
            return {'action': 'memory_forget_record', 'value': record_id}
        if normalized in {'/memory', 'memory', 'what do you remember about me'}:
            return {'action': 'memory_summary'}
        if normalized in {'/progress', 'progress', 'how have my scores changed', 'what should i practice next'}:
            return {'action': 'memory_progress'}
        if normalized in {'/lastinterview', '/last interview', 'show my last interview'}:
            return {'action': 'memory_last_interview'}
        if normalized in {'/forgetlast', '/forget last', 'forget the last session'}:
            return {'action': 'memory_forget_last'}
        if normalized in {'/forgetall', '/forget all', 'forget everything'}:
            self._confirm_forget_all = True
            return {'action': 'message', 'value': 'This will permanently delete all saved conversations and interview progress. Type /confirmforgetall to continue.', 'remember': False}
        if normalized in {'/confirmforgetall', '/confirm forget all'}:
            if self._confirm_forget_all:
                self._confirm_forget_all = False
                return {'action': 'memory_forget_all'}
            return {'action': 'message', 'value': 'No memory deletion is awaiting confirmation.', 'remember': False}
        if normalized in {'/cancel', 'cancel', 'stop', 'stop current request'}:
            return {'action': 'cancel'}
        if normalized in {'/interview', 'slash interview', 'start interview', 'start an interview', 'start system design interview', 'start a system design interview'}:
            return {'action': 'interview_start'}
        if normalized in {'/endinterview', '/end interview', 'slash end interview', 'end interview', 'end the interview', 'finish interview', 'finish the interview'}:
            return {'action': 'interview_end'} if self.interview.active else {'action': 'message', 'value': 'No interview is currently active.'}
        if normalized in {'/hint', 'slash hint', 'give me a hint', 'hint'} and self.interview.active:
            return {'action': 'interview_hint'}
        if lowered == '/quit':
            return {'action': 'quit'}
        if lowered == '/mute':
            return {'action': 'mute'}
        if lowered == '/unmute':
            return {'action': 'unmute'}
        if lowered == '/jarvis':
            return {'action': 'personality', 'value': 'jarvis'}
        if lowered == '/eve':
            return {'action': 'personality', 'value': 'eve'}
        return None
