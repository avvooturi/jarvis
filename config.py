import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default: str = None) -> str:
    return os.getenv(key, default)


@dataclass
class Config:
    hermes_wsl_distro: str
    hermes_command: str
    hermes_provider: str
    hermes_model: str
    hermes_session_name: str
    hermes_extra_flags: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    audio_sample_rate: int
    tts_engine: str
    tts_voice: str
    tts_rate: int
    hotkey: str
    default_personality: str
    personalities_dir: Path

    @classmethod
    def load(cls) -> 'Config':
        return cls(
            hermes_wsl_distro=_get_env('HERMES_WSL_DISTRO', 'Ubuntu'),
            hermes_command=_get_env('HERMES_COMMAND', 'hermes'),
            hermes_provider=_get_env('HERMES_PROVIDER', 'openrouter'),
            hermes_model=_get_env('HERMES_MODEL', 'openrouter/auto'),
            hermes_session_name=_get_env('HERMES_SESSION_NAME', 'jarvis_voice_assistant'),
            hermes_extra_flags=_get_env('HERMES_EXTRA_FLAGS', '--ignore-rules --accept-hooks --source tool'),
            whisper_model=_get_env('WHISPER_MODEL', 'small.en'),
            whisper_device=_get_env('WHISPER_DEVICE', 'cpu'),
            whisper_compute_type=_get_env('WHISPER_COMPUTE_TYPE', 'int8'),
            audio_sample_rate=int(_get_env('AUDIO_SAMPLE_RATE', '16000')),
            tts_engine=_get_env('TTS_ENGINE', 'pyttsx3'),
            tts_voice=_get_env('TTS_VOICE', ''),
            tts_rate=int(_get_env('TTS_RATE', '160')),
            hotkey=_get_env('HOTKEY', 'f8'),
            default_personality=_get_env('DEFAULT_PERSONALITY', 'jarvis'),
            personalities_dir=Path(_get_env('PERSONALITIES_DIR', 'personalities')),
        )
