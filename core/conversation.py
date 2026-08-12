import logging
import yaml
from pathlib import Path

from config import Config
from core.interview import INTERVIEW_PROMPT, InterviewSession


class ConversationManager:
    def __init__(self, config: Config):
        self.logger = logging.getLogger('ConversationManager')
        self.config = config
        self.is_muted = False
        self.history = []
        self.personality = config.default_personality
        self.personality_prompt = self._load_personality(self.personality)
        self.interview = InterviewSession()

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
        return INTERVIEW_PROMPT if self.interview.active else self.personality_prompt

    def add_turn(self, user_text: str, assistant_text: str):
        self.history.append((user_text, assistant_text))
        self.interview.add_turn(user_text, assistant_text)

    def handle_command(self, text: str):
        lowered = text.strip().lower()
        normalized = lowered.strip(' .!?')
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
