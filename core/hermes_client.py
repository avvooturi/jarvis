import logging
import shlex
import subprocess


class HermesClient:
    def __init__(self, wsl_distro: str = 'Ubuntu', hermes_command: str = 'hermes', provider: str = 'openrouter', model: str = 'openrouter/auto', session_name: str = 'jarvis_voice_assistant', extra_flags: str = '--ignore-rules --accept-hooks --source tool', timeout: int = 60, max_turns: int = 6):
        self.logger = logging.getLogger('HermesClient')
        self.wsl_distro = wsl_distro
        self.hermes_command = hermes_command
        self.provider = provider
        self.model = model
        self.session_name = session_name
        self.extra_flags = extra_flags
        self.timeout = timeout
        self.max_turns = max_turns

    def send(self, prompt: str, max_turns: int = None) -> str:
        turns = max_turns if max_turns is not None else self.max_turns
        command = f'{self.hermes_command} chat -q {shlex.quote(prompt)} -Q --provider {shlex.quote(self.provider)} -m {shlex.quote(self.model)} --max-turns {int(turns)}'
        if self.extra_flags:
            command += f' {self.extra_flags}'

        full_command = ['wsl', '-d', self.wsl_distro, 'bash', '-lc', command]
        self.logger.debug('Executing Hermes command: %s', ' '.join(full_command))

        try:
            completed = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'Hermes request timed out after {self.timeout}s') from exc

        if completed.returncode != 0:
            raise RuntimeError(f'Hermes command failed: {completed.stderr.strip() or completed.stdout.strip()}')

        output = completed.stdout.strip()
        lines = [line for line in output.splitlines() if not line.startswith('session_id:')]
        response = '\n'.join(lines).strip()
        if not response:
            response = completed.stderr.strip()
        return response
