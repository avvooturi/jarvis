import logging
import queue
import threading
import gc


class _SpeechRequest:
    def __init__(self, text: str):
        self.text = text
        self.done = threading.Event()
        self.error = None


class TTS:
    def __init__(self, engine_name: str = 'pyttsx3', voice: str = '', rate: int = 160):
        self.logger = logging.getLogger('TTS')
        self.engine_name = engine_name
        self.voice = voice
        self.rate = rate
        if engine_name != 'pyttsx3':
            raise ValueError(f'Unsupported TTS engine: {engine_name}')
        self._queue = queue.Queue()
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False
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
                # pyttsx3's Windows SAPI driver can remain in a completed but
                # silent state after runAndWait(). Give every utterance a fresh
                # engine, created and used entirely on this COM-owning thread.
                engine = pyttsx3.init()
                if self.voice:
                    self._set_voice(engine, self.voice)
                if self.rate:
                    engine.setProperty('rate', self.rate)
                engine.say(request.text)
                engine.runAndWait()
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

    def speak(self, text: str):
        if not text:
            return
        if self._closed or not self._thread.is_alive():
            raise RuntimeError('TTS engine is not available')

        request = _SpeechRequest(text)
        self._queue.put(request)
        if not request.done.wait(timeout=180):
            raise RuntimeError('TTS playback timed out')
        if request.error is not None:
            raise RuntimeError('TTS playback failed') from request.error

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=5)
