import unittest
from config import Config
from core.hermes_client import HermesClient


class TestHermesClient(unittest.TestCase):
    def test_send_returns_text(self):
        config = Config.load()
        client = HermesClient(
            wsl_distro=config.hermes_wsl_distro,
            hermes_command=config.hermes_command,
            provider=config.hermes_provider,
            model=config.hermes_model,
            session_name=config.hermes_session_name,
            extra_flags=config.hermes_extra_flags,
        )
        result = client.send('Say hello in one sentence.')
        self.assertIn('hello', result.lower())


if __name__ == '__main__':
    unittest.main()
