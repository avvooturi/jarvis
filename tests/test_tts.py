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

    def test_long_responses_use_faster_rate(self):
        engines = []

        def create_engine():
            engine = FakeEngine()
            engines.append(engine)
            return engine

        fake_pyttsx3 = types.SimpleNamespace(init=create_engine)
        short_text = ' '.join(['short'] * 50)
        long_text = ' '.join(['long'] * 51)

        with patch.dict(sys.modules, {'pyttsx3': fake_pyttsx3}):
            tts = TTS(rate=190, fast_rate=230, fast_word_threshold=50)
            try:
                tts.speak(short_text)
                tts.speak(long_text)
            finally:
                tts.close()

        rates = [
            call[2]
            for engine in engines
            for call in engine.calls
            if call[0] == 'setProperty' and call[1] == 'rate'
        ]
        self.assertEqual(rates, [190, 230])

    def test_async_requests_can_be_queued_then_waited(self):
        engines = []

        def create_engine():
            engine = FakeEngine()
            engines.append(engine)
            return engine

        with patch.dict(sys.modules, {'pyttsx3': types.SimpleNamespace(init=create_engine)}):
            tts = TTS()
            try:
                first = tts.speak_async('First sentence.')
                second = tts.speak_async('Second sentence.')
                tts.wait(first)
                tts.wait(second)
            finally:
                tts.close()

        spoken = [call[1] for engine in engines for call in engine.calls if call[0] == 'say']
        self.assertEqual(spoken, ['First sentence.', 'Second sentence.'])



if __name__ == '__main__':
    unittest.main()
