import logging
import yaml
from pathlib import Path

from config import Config


class ConversationManager:
    def __init__(self, config: Config):
        self.logger = logging.getLogger('ConversationManager')
        self.config = config
        self.is_muted = False
        self.history = []
        self.personality = config.default_personality
        self.personality_prompt = self._load_personality(self.personality)

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
        context = '\n'.join([f'User: {item[0]}\nAssistant: {item[1]}' for item in self.history[-5:]])
        prompt = f'{self.personality_prompt}\n{context}\nUser: {user_text}\nAssistant:'
        return prompt

    def add_turn(self, user_text: str, assistant_text: str):
        self.history.append((user_text, assistant_text))

    def handle_command(self, text: str):
        lowered = text.strip().lower()
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
