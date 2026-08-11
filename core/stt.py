from faster_whisper import WhisperModel


class WhisperTranscriber:
    def __init__(self, model_name: str = 'base.en', device: str = 'cpu', compute_type: str = 'int8', beam_size: int = 1, vad_filter: bool = True):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
        )
        return ' '.join(segment.text.strip() for segment in segments if segment.text.strip())
