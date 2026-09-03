import logging
import shlex
import subprocess
import threading
import time

from core.state import RequestCancelled


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
        self._process = None
        self._lock = threading.Lock()

    def send(self, prompt: str, max_turns: int = None, cancel_event=None, on_delta=None) -> str:
        turns = max_turns if max_turns is not None else self.max_turns
        command = f'{self.hermes_command} chat -q {shlex.quote(prompt)} -Q --provider {shlex.quote(self.provider)} -m {shlex.quote(self.model)} --max-turns {int(turns)}'
        if self.extra_flags:
            command += f' {self.extra_flags}'

        full_command = ['wsl', '-d', self.wsl_distro, 'bash', '-lc', command]
        self.logger.debug('Executing Hermes command: %s', ' '.join(full_command))

        try:
            process = subprocess.Popen(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._lock:
                self._process = process
            stdout_lines = []
            stderr_lines = []
            readers = []
            if on_delta is not None:
                readers = [
                    threading.Thread(
                        target=self._read_stream,
                        args=(process.stdout, stdout_lines, on_delta),
                        daemon=True,
                    ),
                    threading.Thread(
                        target=self._read_stream,
                        args=(process.stderr, stderr_lines, None),
                        daemon=True,
                    ),
                ]
                for reader in readers:
                    reader.start()
            deadline = time.monotonic() + self.timeout
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.05):
                    self._terminate(process)
                    raise RequestCancelled('Hermes request cancelled')
                if time.monotonic() >= deadline:
                    self._terminate(process)
                    raise RuntimeError(f'Hermes request timed out after {self.timeout}s')
                time.sleep(0.05)
            if readers:
                for reader in readers:
                    reader.join(timeout=2)
                stdout, stderr = ''.join(stdout_lines), ''.join(stderr_lines)
            else:
                stdout, stderr = process.communicate()
        finally:
            with self._lock:
                self._process = None

        if process.returncode != 0:
            raise RuntimeError(f'Hermes command failed: {stderr.strip() or stdout.strip()}')

        output = stdout.strip()
        lines = [line for line in output.splitlines() if not line.startswith('session_id:')]
        response = '\n'.join(lines).strip()
        if not response:
            response = stderr.strip()
        return response

    @staticmethod
    def _read_stream(stream, destination, on_delta):
        for line in iter(stream.readline, ''):
            destination.append(line)
            if on_delta is not None and not line.startswith('session_id:'):
                on_delta(line)

    def cancel(self):
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            self._terminate(process)

    @staticmethod
    def _terminate(process):
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
