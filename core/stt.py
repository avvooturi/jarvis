from faster_whisper import WhisperModel


class WhisperTranscriber:
    def __init__(self, model_name: str = 'small.en', device: str = 'cpu', compute_type: str = 'int8'):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(audio_path)
        return ' '.join(segment.text.strip() for segment in segments if segment.text.strip())
