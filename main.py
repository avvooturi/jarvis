import logging
import queue
import sys
import threading
import time

from config import Config
from core.audio import AudioRecorder
from core.conversation import ConversationManager
from core.hermes_client import HermesClient
from core.stt import WhisperTranscriber
from core.tts import TTS
from gui import HudWindow

try:
    import keyboard
except ImportError:
    keyboard = None


class VoiceAssistantApp:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger('VoiceAssistant')
        self.audio_recorder = AudioRecorder(samplerate=config.audio_sample_rate)
        self.transcriber = WhisperTranscriber(model_name=config.whisper_model, device=config.whisper_device, compute_type=config.whisper_compute_type)
        self.hermes = HermesClient(
            wsl_distro=config.hermes_wsl_distro,
            hermes_command=config.hermes_command,
            provider=config.hermes_provider,
            model=config.hermes_model,
            session_name=config.hermes_session_name,
            extra_flags=config.hermes_extra_flags,
        )
        self.tts = TTS(engine_name=config.tts_engine, voice=config.tts_voice, rate=config.tts_rate)
        self.conversation = ConversationManager(config)
        self.hotkey = config.hotkey.lower()
        self.recording = False
        self.running = True
        self._lock = threading.Lock()
        self._debounce_until = 0.0
        self._command_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.hud = None

    def run(self):
        self.logger.info('Starting voice assistant. Press %s once to start listening, again to stop and send.', self.hotkey.upper())
        self.logger.info('Use /jarvis, /eve, /mute, /unmute, /quit as voice or keyboard commands.')

        self.hud = HudWindow(
            on_toggle_recording=self._on_hotkey_pressed,
            on_close=self.stop,
            model=self.config.hermes_model,
            personality=self.conversation.personality,
            hotkey=self.hotkey,
        )
        if keyboard is not None:
            keyboard.add_hotkey(self.hotkey, self._on_hotkey_pressed)
        else:
            self.logger.warning('Global hotkey unavailable. Click the core or press Space in the HUD.')
        self._worker_thread.start()

        try:
            self.hud.run()
        except KeyboardInterrupt:
            self.logger.info('Interrupted by user.')
        finally:
            self.running = False
            if keyboard is not None:
                keyboard.unhook_all_hotkeys()
            self.audio_recorder.close()
            self.tts.close()
            self.logger.info('Stopped voice assistant.')

    def stop(self):
        self.running = False
        if self.recording:
            self.recording = False
            self.audio_recorder.close()

    def console_loop(self):
        while self.running:
            try:
                line = input('Type /record to capture audio, /quit to exit: ').strip()
            except EOFError:
                break

            if not line:
                continue
            if line.lower() == '/quit':
                self.running = False
                break
            if line.lower() == '/record':
                self.logger.info('Recording audio from microphone... Press Enter again to stop.')
                self.audio_recorder.start_recording()
                input()
                audio_path = self.audio_recorder.stop_recording()
                self.process_audio(audio_path)
                continue
            self.logger.info('Unknown command: %s', line)

        self.audio_recorder.close()
        self.tts.close()

    def _on_hotkey_pressed(self):
        now = time.time()
        if now < self._debounce_until:
            return
        self._debounce_until = now + 0.25

        with self._lock:
            if self.recording:
                self.recording = False
                try:
                    audio_path = self.audio_recorder.stop_recording()
                    self.logger.info('Stopping listening and queueing audio for processing...')
                    self._set_hud_state('transcribing', 'Decoding voice input')
                    self._command_queue.put('process_audio')
                    self._command_queue.put(audio_path)
                except Exception as exc:
                    self.logger.error('Failed to stop recording: %s', exc)
                    self._set_hud_state('error', 'Microphone capture failed')
                return

            self.recording = True
            try:
                self.audio_recorder.start_recording()
                self.logger.info('Listening...')
                self._set_hud_state('listening', 'Voice channel active')
            except Exception as exc:
                self.logger.error('Failed to start recording: %s', exc)
                self.recording = False
                self._set_hud_state('error', 'Microphone unavailable')

    def process_audio(self, audio_path: str):
        self.logger.info('Transcribing audio...')
        self._set_hud_state('transcribing', 'Whisper speech recognition')
        try:
            transcript = self.transcriber.transcribe(audio_path)
        except Exception as exc:
            self.logger.error('Speech recognition failed: %s', exc)
            self._set_hud_state('error', 'Speech recognition failed')
            return
        finally:
            self.audio_recorder.cleanup_file(audio_path)

        if not transcript:
            self.logger.warning('No speech was detected.')
            self._set_hud_state('idle', 'No speech detected')
            return

        self.logger.info('Transcript: %s', transcript)

        command_result = self.conversation.handle_command(transcript)
        if command_result is not None:
            self._handle_command_result(command_result)
            if self.running:
                self._set_hud_state('idle', 'Command acknowledged')
            return

        prompt = self.conversation.build_prompt(transcript)
        self.logger.info('Sending prompt to Hermes...')
        self._set_hud_state('thinking', 'Hermes agent processing')

        try:
            response = self.hermes.send(prompt)
        except RuntimeError as exc:
            self.logger.error('Hermes request failed: %s', exc)
            self._set_hud_state('error', 'Hermes connection failed')
            return

        if response:
            self.logger.info('Hermes response received.')
            self.conversation.add_turn(transcript, response)
            if self.hud is not None:
                self.hud.add_exchange(transcript, response)
            if not self.conversation.is_muted:
                self.logger.info('Speaking response...')
                self._set_hud_state('speaking', 'Synthesizing voice response')
                try:
                    self.tts.speak(response)
                    self.logger.info('Finished speaking response.')
                    self._set_hud_state('idle', 'Standing by')
                except Exception as exc:
                    self.logger.error('Text-to-speech failed: %s', exc)
                    self._set_hud_state('error', 'Voice synthesis failed')
            else:
                self.logger.info('Muted: response not spoken.')
                self._set_hud_state('idle', 'Response received // audio muted')
        else:
            self.logger.warning('Hermes returned an empty response.')
            self._set_hud_state('error', 'Empty agent response')

    def _worker_loop(self):
        while self.running:
            try:
                action = self._command_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if action == 'process_audio':
                audio_path = self._command_queue.get()
                try:
                    self.process_audio(audio_path)
                except Exception:
                    self.logger.exception('Unexpected error while processing audio.')
                    self._set_hud_state('error', 'Processing fault')
            elif action == 'quit':
                self.running = False

    def _handle_command_result(self, result: dict):
        if result['action'] == 'quit':
            self.logger.info('Quitting via command.')
            self.running = False
            if self.hud is not None:
                self.hud.request_close()
        elif result['action'] == 'mute':
            self.conversation.is_muted = True
            self.logger.info('Muted voice output.')
        elif result['action'] == 'unmute':
            self.conversation.is_muted = False
            self.logger.info('Unmuted voice output.')
        elif result['action'] == 'personality':
            self.conversation.set_personality(result['value'])
            if self.hud is not None:
                self.hud.set_personality(result['value'])
            self.logger.info('Switched personality to %s.', result['value'])
        elif result['action'] == 'message':
            self.logger.info(result['value'])

    def _set_hud_state(self, state: str, detail: str = None):
        if self.hud is not None:
            self.hud.set_state(state, detail)


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )


def main():
    configure_logging()
    config = Config.load()
    app = VoiceAssistantApp(config)
    app.run()


if __name__ == '__main__':
    main()
