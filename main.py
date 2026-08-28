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
from core.permissions import PermissionManager
from core.request_router import needs_tools
from core.spotify import SpotifyHandler
from core.state import AssistantState, AssistantStateMachine, RequestCancelled
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
        self.permissions = PermissionManager(config.permission_mode, config.permission_timeout)
        self.hotkey = config.hotkey.lower()
        self.running = True
        self._lock = threading.Lock()
        self._debounce_until = 0.0
        self._command_queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.hud = None
        self.lifecycle = AssistantStateMachine(self._on_state_changed)

    def run(self):
        self.logger.info('Starting voice assistant. Press %s once to start listening, again to stop and send.', self.hotkey.upper())
        self.logger.info('Use /cancel, /interview, /endinterview, /hint, /jarvis, /eve, /mute, /unmute, /quit as commands.')

        self.hud = HudWindow(
            on_toggle_recording=self._on_hotkey_pressed,
            on_submit_text=self._on_text_submitted,
            on_cancel=self._on_cancel_requested,
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
            self.lifecycle.transition(AssistantState.STOPPED, 'Jarvis offline', force=True)
            self.logger.info('Stopped voice assistant.')

    def stop(self):
        self.running = False
        was_recording = self.lifecycle.state == AssistantState.RECORDING
        self.lifecycle.cancel('Shutting down')
        self.tts.cancel()
        self.hermes.cancel()
        self.fast_chat.cancel()
        if was_recording:
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
            if self.lifecycle.state == AssistantState.RECORDING:
                try:
                    audio_path = self.audio_recorder.stop_recording()
                    self.logger.info('Stopping listening and queueing audio for processing...')
                    self.lifecycle.transition(AssistantState.TRANSCRIBING, 'Decoding voice input')
                    self._command_queue.put(('process_audio', audio_path))
                except Exception as exc:
                    self.logger.error('Failed to stop recording: %s', exc)
                    self.lifecycle.transition(AssistantState.ERROR, 'Microphone capture failed')
                return

            if self.lifecycle.state == AssistantState.AWAITING_PERMISSION:
                self.permissions.clear()
                self.lifecycle.transition(AssistantState.IDLE, 'Previous pending action denied')

            if self.lifecycle.busy:
                self.logger.info('Jarvis is busy; use /cancel or the HUD cancel control.')
                return

            try:
                self.lifecycle.transition(AssistantState.RECORDING, 'Voice channel active')
                self.audio_recorder.start_recording()
                self.logger.info('Listening...')
            except Exception as exc:
                self.logger.error('Failed to start recording: %s', exc)
                self.lifecycle.transition(AssistantState.ERROR, 'Microphone unavailable')

    def _on_text_submitted(self, text):
        text = text.strip()
        if not text:
            return False
        if text.strip().lower() in {'/cancel', 'cancel', 'stop current request'}:
            self._on_cancel_requested()
            return True
        with self._lock:
            if self.lifecycle.busy:
                self.logger.info('Jarvis is busy; typed command ignored.')
                return False
            self.lifecycle.transition(AssistantState.ROUTING, 'Processing typed command')
            self.logger.info('Typed command: %s', text)
            self._command_queue.put(('process_text', text))
            return True

    def _on_cancel_requested(self):
        with self._lock:
            pending_permission = self.permissions.clear()
            state = self.lifecycle.state
            if state == AssistantState.RECORDING:
                self.lifecycle.cancel('Discarding voice capture')
                self.audio_recorder.close()
                self.lifecycle.transition(AssistantState.IDLE, 'Voice capture cancelled')
                return True
            if not self.lifecycle.cancel():
                if pending_permission is not None:
                    self.logger.info('Pending permission request cancelled.')
                    if state == AssistantState.AWAITING_PERMISSION:
                        self.lifecycle.transition(AssistantState.IDLE, 'Pending action denied')
                    return True
                self.logger.info('There is no active request to cancel.')
                return False
            self.logger.info('Cancelling active request...')
            self.tts.cancel()
            self.hermes.cancel()
            self.fast_chat.cancel()
            return True

    def process_audio(self, audio_path: str):
        total_started = time.perf_counter()
        self.logger.info('Transcribing audio...')
        self._set_hud_state('transcribing', 'Whisper speech recognition')
        try:
            self.lifecycle.checkpoint()
            stage_started = time.perf_counter()
            transcript = self.transcriber.transcribe(audio_path)
            self.lifecycle.checkpoint()
            self.logger.info('Timing: transcription %.2fs', time.perf_counter() - stage_started)
        except Exception as exc:
            if isinstance(exc, RequestCancelled):
                raise
            self.logger.error('Speech recognition failed: %s', exc)
            self.lifecycle.transition(AssistantState.ERROR, 'Speech recognition failed')
            return
        finally:
            self.audio_recorder.cleanup_file(audio_path)

        if not transcript:
            self.logger.warning('No speech was detected.')
            self.lifecycle.transition(AssistantState.IDLE, 'No speech detected')
            return

        self.logger.info('Transcript: %s', transcript)

        self.process_text(transcript, total_started)

    def process_text(self, transcript: str, total_started=None):
        if total_started is None:
            total_started = time.perf_counter()

        self.lifecycle.checkpoint()
        if self.lifecycle.state == AssistantState.TRANSCRIBING:
            self.lifecycle.transition(AssistantState.ROUTING, 'Routing voice request')

        permission_granted = False
        permission_assessment = None
        permission_status, pending = self.permissions.handle_command(transcript)
        if permission_status == 'confirmed':
            if pending is None:
                self._deliver_response(
                    transcript,
                    'There is no pending permission request, or the previous approval has expired.',
                    total_started,
                )
                return
            permission_granted = True
            permission_assessment = pending.assessment
            transcript = pending.text
            self.logger.info('One-time permission granted for %s.', pending.assessment.category)
            self.lifecycle.transition(AssistantState.ROUTING, 'Permission granted // routing action')
        elif permission_status == 'denied':
            message = 'The pending action was denied.' if pending is not None else 'There is no pending action to deny.'
            self._deliver_response(transcript, message, total_started)
            return
        elif self.permissions.pending is not None:
            self.permissions.clear()
            self.logger.info('Previous pending permission was discarded because a new request was received.')

        command_result = self.conversation.handle_command(transcript)
        if command_result is not None:
            response = self._handle_command_result(command_result)
            if response:
                self._deliver_response(transcript, response, total_started)
            if self.running:
                self.lifecycle.transition(AssistantState.IDLE, 'Command acknowledged')
            return

        if not permission_granted and not self.conversation.interview.active:
            permission_assessment = self.permissions.assess(transcript)
            if permission_assessment.requires_confirmation:
                pending = self.permissions.request(transcript, permission_assessment)
                self.logger.info('Awaiting permission for %s.', permission_assessment.category)
                self._deliver_response(transcript, self.permissions.confirmation_message(pending), total_started)
                self.lifecycle.transition(AssistantState.AWAITING_PERMISSION, 'Type /confirm or /deny')
                return

        prompt = self.conversation.build_prompt(transcript)
        if self.permissions.mode != 'off' and permission_assessment is not None and needs_tools(transcript):
            prompt = (
                f'{self.permissions.execution_directive(permission_assessment, permission_granted)}\n\n'
                f'{prompt}'
            )
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
                except RequestCancelled:
                    self.logger.info('Voice request cancelled.')
                except Exception:
                    self.logger.exception('Unexpected error while processing audio.')
                    self._set_hud_state('error', 'Processing fault')
                finally:
                    if self.running and self.lifecycle.state not in {AssistantState.ERROR, AssistantState.AWAITING_PERMISSION}:
                        self.lifecycle.transition(AssistantState.IDLE, 'Standing by', force=True)
            elif action == 'process_text':
                try:
                    self.process_text(payload)
                except RequestCancelled:
                    self.logger.info('Typed request cancelled.')
                except Exception:
                    self.logger.exception('Unexpected error while processing typed command.')
                    self._set_hud_state('error', 'Processing fault')
                finally:
                    if self.running and self.lifecycle.state not in {AssistantState.ERROR, AssistantState.AWAITING_PERMISSION}:
                        self.lifecycle.transition(AssistantState.IDLE, 'Standing by', force=True)
            elif action == 'quit':
                self.running = False

    def _get_response(self, transcript: str, prompt: str):
        self.lifecycle.checkpoint()
        if self.spotify.can_handle(transcript):
            response = self.spotify.handle(transcript)
            if response:
                self.logger.info('Spotify request handled locally.')
                return response

        tool_request = needs_tools(transcript) and not self.conversation.interview.active
        stage_started = time.perf_counter()
        self.lifecycle.transition(AssistantState.THINKING, 'Selecting response route')
        if not tool_request and self.fast_chat.available:
            self.logger.info('Sending prompt through fast OpenRouter route (%s)...', self.config.fast_model)
            self._set_hud_state('thinking', 'Fast model processing')
            try:
                response = self.fast_chat.send(
                    self.conversation.system_prompt + '\nAnswer in at most three concise sentences.',
                    self.conversation.interview.turns if self.conversation.interview.active else self.conversation.history,
                    transcript,
                    cancel_event=self.lifecycle.cancel_event,
                )
                self.logger.info('Fast response received. Timing: model %.2fs', time.perf_counter() - stage_started)
                return response
            except RequestCancelled:
                raise
            except Exception as exc:
                if self.lifecycle.cancel_event.is_set():
                    raise RequestCancelled('Fast model request cancelled') from exc
                self.logger.warning('Fast route failed; falling back to Hermes: %s', exc)

        turns = self.config.hermes_max_turns if tool_request else 1
        self.logger.info('Sending prompt to Hermes (max turns: %d)...', turns)
        self._set_hud_state('thinking', 'Hermes agent processing')
        try:
            response = self.hermes.send(prompt, max_turns=turns, cancel_event=self.lifecycle.cancel_event)
            self.logger.info('Hermes response received. Timing: model %.2fs', time.perf_counter() - stage_started)
            return response
        except RuntimeError as exc:
            if self.lifecycle.cancel_event.is_set():
                raise RequestCancelled('Request cancelled') from exc
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
        elif result['action'] == 'cancel':
            return 'There is no active request to cancel.'
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
                        cancel_event=self.lifecycle.cancel_event,
                    )
                else:
                    evaluation = self.hermes.send(
                        evaluation_prompt, max_turns=1, cancel_event=self.lifecycle.cancel_event,
                    )
            except RequestCancelled:
                raise
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
        self.lifecycle.checkpoint()
        self.conversation.add_turn(transcript, response)
        if self.hud is not None:
            self.hud.add_exchange(transcript, response)
        if self.conversation.is_muted:
            self.logger.info('Muted: response not spoken.')
            self._set_hud_state('idle', 'Response received // audio muted')
            return
        self.logger.info('Speaking response...')
        self.lifecycle.transition(AssistantState.SPEAKING, 'Synthesizing voice response')
        try:
            stage_started = time.perf_counter()
            self.tts.speak(response, cancel_event=self.lifecycle.cancel_event)
            self.lifecycle.checkpoint()
            self.logger.info('Finished speaking response. Timing: TTS %.2fs; total %.2fs', time.perf_counter() - stage_started, time.perf_counter() - total_started)
            self.lifecycle.transition(AssistantState.IDLE, 'Standing by')
        except Exception as exc:
            if isinstance(exc, RequestCancelled):
                raise
            self.logger.error('Text-to-speech failed: %s', exc)
            self._set_hud_state('error', 'Voice synthesis failed')

    def _set_hud_state(self, state: str, detail: str = None):
        mapping = {'listening': AssistantState.RECORDING}
        target = mapping.get(state, state)
        self.lifecycle.transition(target, detail)

    def _on_state_changed(self, state, detail):
        if self.hud is not None:
            self.hud.set_state(state.value, detail)



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
