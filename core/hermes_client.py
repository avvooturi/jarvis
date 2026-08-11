import logging
import shlex
import subprocess
from typing import Optional


class HermesClient:
    def __init__(self, wsl_distro: str = 'Ubuntu', hermes_command: str = 'hermes', provider: str = 'openrouter', model: str = 'openrouter/auto', session_name: str = 'jarvis_voice_assistant', extra_flags: str = '--ignore-rules --accept-hooks --source tool'):
        self.logger = logging.getLogger('HermesClient')
        self.wsl_distro = wsl_distro
        self.hermes_command = hermes_command
        self.provider = provider
        self.model = model
        self.session_name = session_name
        self.extra_flags = extra_flags

    def send(self, prompt: str) -> str:
        command = f'{self.hermes_command} chat -q {shlex.quote(prompt)} -Q --source tool --ignore-rules --accept-hooks --provider {shlex.quote(self.provider)} -m {shlex.quote(self.model)}'
        if self.extra_flags:
            command += f' {self.extra_flags}'

        full_command = ['wsl', '-d', self.wsl_distro, 'bash', '-lc', command]
        self.logger.debug('Executing Hermes command: %s', ' '.join(full_command))

        try:
            completed = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Hermes request timed out') from exc

        if completed.returncode != 0:
            raise RuntimeError(f'Hermes command failed: {completed.stderr.strip() or completed.stdout.strip()}')

        output = completed.stdout.strip()
        lines = [line for line in output.splitlines() if not line.startswith('session_id:')]
        response = '\n'.join(lines).strip()
        if not response:
            response = completed.stderr.strip()
        return response
