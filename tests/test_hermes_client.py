import threading
import unittest
from unittest.mock import patch

from core.hermes_client import HermesClient
from core.state import RequestCancelled


class FakeProcess:
    def __init__(self, running=False):
        self.returncode = None if running else 0
        self.terminated = False

    def poll(self):
        return self.returncode

    def communicate(self):
        return 'session_id: ignored\nHello from Hermes.', ''

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class TestHermesClient(unittest.TestCase):
    def test_send_returns_clean_text(self):
        client = HermesClient()
        with patch('core.hermes_client.subprocess.Popen', return_value=FakeProcess()):
            result = client.send('Say hello in one sentence.')
        self.assertEqual(result, 'Hello from Hermes.')

    def test_cancelled_request_terminates_process(self):
        process = FakeProcess(running=True)
        cancelled = threading.Event()
        cancelled.set()
        client = HermesClient()
        with patch('core.hermes_client.subprocess.Popen', return_value=process):
            with self.assertRaises(RequestCancelled):
                client.send('Long task', cancel_event=cancelled)
        self.assertTrue(process.terminated)


if __name__ == '__main__':
    unittest.main()
