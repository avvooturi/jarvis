import os
import queue
import time
import sounddevice as sd
import soundfile as sf
from pathlib import Path


class AudioRecorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1):
        self.samplerate = samplerate
        self.channels = channels
        self._queue = queue.Queue()
        self._recording = False
        self._stream = None
        self._temp_file = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f'Audio status: {status}')
        self._queue.put(indata.copy())

    def start_recording(self):
        if self._recording:
            return
        self._temp_file = Path(f'temp_recording_{time.time_ns()}.wav')
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._recording = True

    def stop_recording(self) -> str:
        if not self._recording:
            raise RuntimeError('Recorder is not active.')

        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._recording = False

        frames = []
        while not self._queue.empty():
            frames.append(self._queue.get())

        if not frames:
            raise RuntimeError('No audio frames recorded.')

        import numpy as np
        audio_data = np.concatenate(frames, axis=0)

        sf.write(str(self._temp_file), audio_data, self.samplerate)
        return str(self._temp_file)

    def cleanup_file(self, path: str):
        if path and Path(path).exists():
            try:
                os.remove(path)
            except OSError:
                pass

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._recording = False
