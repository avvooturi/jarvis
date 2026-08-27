import logging
import queue
import threading
import gc
import time

from core.state import RequestCancelled


class _SpeechRequest:
    def __init__(self, text: str, cancel_event=None):
        self.text = text
        self.cancel_event = cancel_event
        self.done = threading.Event()
        self.error = None


class TTS:
    def __init__(self, engine_name: str = 'pyttsx3', voice: str = '', rate: int = 160,
                 fast_rate: int = 230, fast_word_threshold: int = 50):
        self.logger = logging.getLogger('TTS')
        self.engine_name = engine_name
        self.voice = voice
        self.rate = rate
        self.fast_rate = fast_rate
        self.fast_word_threshold = fast_word_threshold
        if engine_name != 'pyttsx3':
            raise ValueError(f'Unsupported TTS engine: {engine_name}')
        self._queue = queue.Queue()
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False
        self._cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name='JarvisTTS', daemon=True)
        self._thread.start()

        if not self._ready.wait(timeout=15):
            raise RuntimeError('Timed out while starting the TTS engine')
        if self._startup_error is not None:
            raise RuntimeError('Failed to start the TTS engine') from self._startup_error

    def _run(self):
        try:
            import pyttsx3
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()
            return

        self._ready.set()
        while True:
            request = self._queue.get()
            if request is None:
                break
            engine = None
            try:
                self._cancel_event.clear()
                # pyttsx3's Windows SAPI driver can remain in a completed but
                # silent state after runAndWait(). Give every utterance a fresh
                # engine, created and used entirely on this COM-owning thread.
                engine = pyttsx3.init()
                if self.voice:
                    self._set_voice(engine, self.voice)
                word_count = len(request.text.split())
                speech_rate = self.fast_rate if word_count > self.fast_word_threshold else self.rate
                if speech_rate:
                    engine.setProperty('rate', speech_rate)
                self.logger.info('Speaking %d words at rate %d.', word_count, speech_rate)
                engine.say(request.text)
                if hasattr(engine, 'startLoop') and hasattr(engine, 'iterate'):
                    engine.startLoop(False)
                    try:
                        while engine.isBusy():
                            if self._cancel_event.is_set() or (request.cancel_event is not None and request.cancel_event.is_set()):
                                engine.stop()
                                raise RequestCancelled('Speech cancelled')
                            engine.iterate()
                            time.sleep(0.01)
                    finally:
                        engine.endLoop()
                else:
                    engine.runAndWait()
                    if self._cancel_event.is_set() or (request.cancel_event is not None and request.cancel_event.is_set()):
                        raise RequestCancelled('Speech cancelled')
            except Exception as exc:
                request.error = exc
            finally:
                if engine is not None:
                    try:
                        engine.stop()
                    except Exception:
                        pass
                engine = None
                # pyttsx3 keeps engines in a weak cache; collect here so the
                # next request cannot receive the stale SAPI driver instance.
                gc.collect()
                request.done.set()

    def _set_voice(self, engine, voice_name: str):
        voices = engine.getProperty('voices')
        for voice in voices:
            if voice_name.lower() in voice.name.lower():
                engine.setProperty('voice', voice.id)
                return
        self.logger.warning('TTS voice %s not found. Using default voice.', voice_name)

    def speak(self, text: str, cancel_event=None):
        if not text:
            return
        if self._closed or not self._thread.is_alive():
            raise RuntimeError('TTS engine is not available')

        request = _SpeechRequest(text, cancel_event)
        self._queue.put(request)
        if not request.done.wait(timeout=180):
            raise RuntimeError('TTS playback timed out')
        if isinstance(request.error, RequestCancelled):
            raise request.error
        if request.error is not None:
            raise RuntimeError(f'TTS playback failed: {request.error}') from request.error

    def cancel(self):
        self._cancel_event.set()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=5)
