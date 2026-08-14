import logging
import queue
import sys
import threading
import time

from config import Config
from core.audio import AudioRecorder
from core.conversation import ConversationManager
from core.fast_client import FastChatClient
from core.hermes_client import HermesClient
from core.request_router import needs_tools
from core.spotify import SpotifyHandler
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
        self.transcriber = WhisperTranscriber(model_name=config.whisper_model, device=config.whisper_device, compute_type=config.whisper_compute_type, beam_size=config.whisper_beam_size, vad_filter=config.whisper_vad_filter)
        self.hermes = HermesClient(
            wsl_distro=config.hermes_wsl_distro,
            hermes_command=config.hermes_command,
            provider=config.hermes_provider,
            model=config.hermes_model,
            session_name=config.hermes_session_name,
            extra_flags=config.hermes_extra_flags,
            timeout=config.hermes_timeout,
            max_turns=config.hermes_max_turns,
        )
        self.fast_chat = FastChatClient(config.fast_api_key, config.fast_model, config.fast_timeout)
        self.spotify = SpotifyHandler()
        self.tts = TTS(
            engine_name=config.tts_engine,
            voice=config.tts_voice,
            rate=config.tts_rate,
            fast_rate=config.tts_fast_rate,
            fast_word_threshold=config.tts_fast_word_threshold,
        )
        self.conversation = ConversationManager(config)
        self.hotkey = config.hotkey.lower()
        self.recording = False
        self.processing = False
        self.running = True
        self._lock = threading.Lock()
        self._debounce_until = 0.0
        self._command_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.hud = None

    def run(self):
        self.logger.info('Starting voice assistant. Press %s once to start listening, again to stop and send.', self.hotkey.upper())
        self.logger.info('Use /interview, /endinterview, /hint, /jarvis, /eve, /mute, /unmute, /quit as commands.')

        self.hud = HudWindow(
            on_toggle_recording=self._on_hotkey_pressed,
            on_submit_text=self._on_text_submitted,
            on_close=self.stop,
            model=self.config.hermes_model,
            personality=self.conversation.personality,
            hotkey=self.hotkey,
        )
        self.hud.set_progress(self.conversation.memory.learning_profile())
        if keyboard is not None:
            keyboard.add_hotkey(self.hotkey, self._on_hotkey_pressed, trigger_on_release=True)
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
            self.conversation.memory.close()
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
                    self.processing = True
                    self._command_queue.put(('process_audio', audio_path))
                except Exception as exc:
                    self.logger.error('Failed to stop recording: %s', exc)
                    self._set_hud_state('error', 'Microphone capture failed')
                return

            if self.processing:
                self.logger.info('Jarvis is still processing the previous request; recording ignored.')
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

    def _on_text_submitted(self, text):
        text = text.strip()
        if not text:
            return False
        with self._lock:
            if self.recording or self.processing:
                self.logger.info('Jarvis is busy; typed command ignored.')
                return False
            self.processing = True
            self.logger.info('Typed command: %s', text)
            self._set_hud_state('thinking', 'Processing typed command')
            self._command_queue.put(('process_text', text))
            return True

    def process_audio(self, audio_path: str):
        total_started = time.perf_counter()
        self.logger.info('Transcribing audio...')
        self._set_hud_state('transcribing', 'Whisper speech recognition')
        try:
            stage_started = time.perf_counter()
            transcript = self.transcriber.transcribe(audio_path)
            self.logger.info('Timing: transcription %.2fs', time.perf_counter() - stage_started)
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

        self.process_text(transcript, total_started)

    def process_text(self, transcript: str, total_started=None):
        if total_started is None:
            total_started = time.perf_counter()

        command_result = self.conversation.handle_command(transcript)
        if command_result is not None:
            response = self._handle_command_result(command_result)
            if response:
                self._deliver_response(transcript, response, total_started)
            if self.running:
                self._set_hud_state('idle', 'Command acknowledged')
            return

        prompt = self.conversation.build_prompt(transcript)
        response = self._get_response(transcript, prompt)
        if response is None:
            return

        if response:
            self._deliver_response(transcript, response, total_started)
        else:
            self.logger.warning('Hermes returned an empty response.')
            self._set_hud_state('error', 'Empty agent response')

    def _worker_loop(self):
        while self.running:
            try:
                command = self._command_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            action, payload = command if isinstance(command, tuple) else (command, None)
            if action == 'process_audio':
                try:
                    self.process_audio(payload)
                except Exception:
                    self.logger.exception('Unexpected error while processing audio.')
                    self._set_hud_state('error', 'Processing fault')
                finally:
                    self.processing = False
            elif action == 'process_text':
                try:
                    self.process_text(payload)
                except Exception:
                    self.logger.exception('Unexpected error while processing typed command.')
                    self._set_hud_state('error', 'Processing fault')
                finally:
                    self.processing = False
            elif action == 'quit':
                self.running = False

    def _get_response(self, transcript: str, prompt: str):
        if self.spotify.can_handle(transcript):
            response = self.spotify.handle(transcript)
            if response:
                self.logger.info('Spotify request handled locally.')
                return response

        tool_request = needs_tools(transcript) and not self.conversation.interview.active
        stage_started = time.perf_counter()
        if not tool_request and self.fast_chat.available:
            self.logger.info('Sending prompt through fast OpenRouter route (%s)...', self.config.fast_model)
            self._set_hud_state('thinking', 'Fast model processing')
            try:
                response = self.fast_chat.send(
                    self.conversation.system_prompt + '\nAnswer in at most three concise sentences.',
                    self.conversation.interview.turns if self.conversation.interview.active else self.conversation.history,
                    transcript,
                )
                self.logger.info('Fast response received. Timing: model %.2fs', time.perf_counter() - stage_started)
                return response
            except Exception as exc:
                self.logger.warning('Fast route failed; falling back to Hermes: %s', exc)

        turns = self.config.hermes_max_turns if tool_request else 1
        self.logger.info('Sending prompt to Hermes (max turns: %d)...', turns)
        self._set_hud_state('thinking', 'Hermes agent processing')
        try:
            response = self.hermes.send(prompt, max_turns=turns)
            self.logger.info('Hermes response received. Timing: model %.2fs', time.perf_counter() - stage_started)
            return response
        except RuntimeError as exc:
            self.logger.error('Hermes request failed: %s', exc)
            self._set_hud_state('error', 'Hermes connection failed')
            return None

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
            return result['value']
        elif result['action'] == 'interview_start':
            self.conversation.interview.start()
            if self.hud is not None:
                self.hud.set_mode('INTERVIEW')
            self.logger.info('System-design interview mode started.')
            prompt_text = 'Begin the interview now. Choose one realistic system-design problem, state it briefly, and ask me to clarify requirements.'
            return self._get_response(prompt_text, self.conversation.build_prompt(prompt_text))
        elif result['action'] == 'interview_hint':
            prompt_text = 'Give me one small hint based on where I am stuck, without revealing the solution.'
            return self._get_response(prompt_text, self.conversation.build_prompt(prompt_text))
        elif result['action'] == 'interview_end':
            self.logger.info('Generating system-design interview evaluation...')
            self._set_hud_state('thinking', 'Evaluating interview performance')
            evaluation_prompt = self.conversation.interview.evaluation_prompt()
            try:
                if self.fast_chat.available:
                    evaluation = self.fast_chat.send(
                        'You are a candid senior system-design interview evaluator.', [], evaluation_prompt,
                        max_tokens=900,
                    )
                else:
                    evaluation = self.hermes.send(evaluation_prompt, max_turns=1)
            except Exception as exc:
                self.logger.error('Interview evaluation failed: %s', exc)
                return 'The interview ended, but I could not generate the evaluation.'
            result_data = self.conversation.interview.finish(evaluation)
            self.conversation.memory.add_interview(
                result_data['started_at'], result_data['ended_at'], result_data['duration_seconds'],
                result_data['turns'], result_data['evaluation'],
            )
            if self.hud is not None:
                self.hud.set_mode('ASSISTANT')
                self.hud.set_progress(self.conversation.memory.learning_profile())
            self.logger.info('Interview report saved to %s', result_data['report_path'])
            return evaluation
        elif result['action'] == 'memory_summary':
            recent = len(self.conversation.memory.recent_conversations(limit=100))
            return f'I have {recent} recent saved conversation turns. {self.conversation.memory.learning_profile()}'
        elif result['action'] == 'memory_progress':
            return self.conversation.memory.progress_summary()
        elif result['action'] == 'memory_last_interview':
            row = self.conversation.memory.last_interview()
            if row is None:
                return 'No completed interview is saved yet.'
            return row['evaluation']
        elif result['action'] == 'memory_forget_last':
            removed = self.conversation.memory.forget_last_session()
            return 'The previous saved session was deleted.' if removed else 'There is no previous session to delete.'
        elif result['action'] == 'memory_forget_all':
            self.conversation.memory.forget_all()
            self.conversation.history = []
            if self.hud is not None:
                self.hud.set_progress('NO INTERVIEW DATA')
            return 'All saved conversations and interview progress have been permanently deleted.'

    def _deliver_response(self, transcript, response, total_started):
        self.logger.info('Response ready for delivery.')
        self.conversation.add_turn(transcript, response)
        if self.hud is not None:
            self.hud.add_exchange(transcript, response)
        if self.conversation.is_muted:
            self.logger.info('Muted: response not spoken.')
            self._set_hud_state('idle', 'Response received // audio muted')
            return
        self.logger.info('Speaking response...')
        self._set_hud_state('speaking', 'Synthesizing voice response')
        try:
            stage_started = time.perf_counter()
            self.tts.speak(response)
            self.logger.info('Finished speaking response. Timing: TTS %.2fs; total %.2fs', time.perf_counter() - stage_started, time.perf_counter() - total_started)
            self._set_hud_state('idle', 'Standing by')
        except Exception as exc:
            self.logger.error('Text-to-speech failed: %s', exc)
            self._set_hud_state('error', 'Voice synthesis failed')

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
