import sys
import threading
import types
import unittest
from unittest.mock import patch

from core.tts import TTS


class FakeEngine:
    def __init__(self):
        self.created_on = threading.get_ident()
        self.calls = []

    def setProperty(self, name, value):
        self.calls.append(('setProperty', name, value, threading.get_ident()))

    def getProperty(self, name):
        return []

    def say(self, text):
        self.calls.append(('say', text, threading.get_ident()))

    def runAndWait(self):
        self.calls.append(('runAndWait', threading.get_ident()))

    def stop(self):
        self.calls.append(('stop', threading.get_ident()))


class TestTTS(unittest.TestCase):
    def test_multiple_requests_use_engine_thread(self):
        engines = []

        def create_engine():
            engine = FakeEngine()
            engines.append(engine)
            return engine

        fake_pyttsx3 = types.SimpleNamespace(init=create_engine)

        with patch.dict(sys.modules, {'pyttsx3': fake_pyttsx3}):
            tts = TTS(rate=160)
            try:
                tts.speak('first')
                tts.speak('second')
            finally:
                tts.close()

        self.assertEqual(len(engines), 2)
        engine_thread_ids = [call[-1] for engine in engines for call in engine.calls]
        self.assertTrue(engine_thread_ids)
        self.assertTrue(
            all(
                call[-1] == engine.created_on
                for engine in engines
                for call in engine.calls
            )
        )
        self.assertEqual(
            [call[1] for engine in engines for call in engine.calls if call[0] == 'say'],
            ['first', 'second'],
        )


if __name__ == '__main__':
    unittest.main()
