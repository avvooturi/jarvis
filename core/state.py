import threading
from enum import Enum


class AssistantState(str, Enum):
    IDLE = 'idle'
    RECORDING = 'recording'
    TRANSCRIBING = 'transcribing'
    ROUTING = 'routing'
    THINKING = 'thinking'
    SPEAKING = 'speaking'
    CANCELLING = 'cancelling'
    ERROR = 'error'
    STOPPED = 'stopped'


class RequestCancelled(RuntimeError):
    """Raised when the active Jarvis request has been cancelled."""


class AssistantStateMachine:
    """Thread-safe lifecycle and cancellation owner for one active request."""

    _ALLOWED = {
        AssistantState.IDLE: {AssistantState.RECORDING, AssistantState.ROUTING, AssistantState.STOPPED},
        AssistantState.RECORDING: {AssistantState.TRANSCRIBING, AssistantState.CANCELLING, AssistantState.ERROR, AssistantState.IDLE},
        AssistantState.TRANSCRIBING: {AssistantState.ROUTING, AssistantState.CANCELLING, AssistantState.ERROR, AssistantState.IDLE},
        AssistantState.ROUTING: {AssistantState.THINKING, AssistantState.SPEAKING, AssistantState.CANCELLING, AssistantState.ERROR, AssistantState.IDLE},
        AssistantState.THINKING: {AssistantState.SPEAKING, AssistantState.CANCELLING, AssistantState.ERROR, AssistantState.IDLE},
        AssistantState.SPEAKING: {AssistantState.CANCELLING, AssistantState.ERROR, AssistantState.IDLE},
        AssistantState.CANCELLING: {AssistantState.IDLE, AssistantState.ERROR, AssistantState.STOPPED},
        AssistantState.ERROR: {AssistantState.IDLE, AssistantState.RECORDING, AssistantState.ROUTING, AssistantState.STOPPED},
        AssistantState.STOPPED: set(),
    }

    def __init__(self, on_change=None):
        self._state = AssistantState.IDLE
        self._detail = 'Standing by'
        self._on_change = on_change
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def detail(self):
        with self._lock:
            return self._detail

    @property
    def cancel_event(self):
        return self._cancel_event

    @property
    def busy(self):
        return self.state not in {AssistantState.IDLE, AssistantState.ERROR, AssistantState.STOPPED}

    def transition(self, new_state, detail=None, force=False):
        new_state = AssistantState(new_state)
        with self._lock:
            if new_state == self._state:
                if detail is not None:
                    self._detail = detail
                    self._notify()
                return
            if not force and new_state not in self._ALLOWED[self._state]:
                raise RuntimeError(f'Invalid assistant state transition: {self._state.value} -> {new_state.value}')
            if self._state in {AssistantState.IDLE, AssistantState.ERROR} and new_state in {AssistantState.RECORDING, AssistantState.ROUTING}:
                self._cancel_event = threading.Event()
            self._state = new_state
            if detail is not None:
                self._detail = detail
            self._notify()

    def cancel(self, detail='Cancelling active request'):
        with self._lock:
            if not self.busy or self._state == AssistantState.CANCELLING:
                return False
            self._cancel_event.set()
            self.transition(AssistantState.CANCELLING, detail)
            return True

    def checkpoint(self):
        if self._cancel_event.is_set():
            raise RequestCancelled('Request cancelled')

    def _notify(self):
        if self._on_change is not None:
            self._on_change(self._state, self._detail)
