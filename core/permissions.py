import re
import threading
import time
from dataclasses import dataclass
from enum import IntEnum

from core.request_router import needs_tools


class RiskLevel(IntEnum):
    READ_ONLY = 0
    REVERSIBLE = 1
    EXTERNAL = 2
    DESTRUCTIVE = 3


@dataclass(frozen=True)
class PermissionAssessment:
    risk: RiskLevel
    category: str
    reason: str
    requires_confirmation: bool


@dataclass(frozen=True)
class PendingAction:
    text: str
    assessment: PermissionAssessment
    created_at: float
    expires_at: float


class PermissionManager:
    """Classifies tool actions and owns the single pending confirmation."""

    CONFIRM_COMMANDS = {'/confirm', 'confirm', 'approve', 'yes', 'yes proceed', 'go ahead'}
    DENY_COMMANDS = {'/deny', 'deny', 'reject', 'no', 'do not proceed', "don't proceed"}

    _DESTRUCTIVE = (
        r'\b(delete|remove|erase|wipe|destroy|format|purge|uninstall|overwrite)\b',
        r'\b(drop|truncate)\s+(?:the\s+)?(?:table|database)\b',
        r'\breset\b.*\b(hard|factory)\b',
    )
    _EXTERNAL = (
        r'\b(send|email|message|post|publish|submit|upload|share)\b',
        r'\b(schedule|book|reserve|order|purchase|buy|pay|transfer)\b',
    )
    _REVERSIBLE = (
        r'\b(create|write|edit|change|modify|rename|move|copy|save)\b',
        r'\b(run|execute|install|download|open|launch|start|close|quit)\b',
        r'\bplay\b.*\bspotify\b',
    )

    def __init__(self, mode='balanced', timeout_seconds=120, clock=time.monotonic):
        if mode not in {'balanced', 'strict', 'off'}:
            raise ValueError('PERMISSION_MODE must be balanced, strict, or off')
        self.mode = mode
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._clock = clock
        self._pending = None
        self._lock = threading.Lock()

    @property
    def pending(self):
        with self._lock:
            self._expire_locked()
            return self._pending

    def assess(self, text):
        lowered = text.strip().lower()
        if not needs_tools(lowered) and not re.search(r'\bplay\b.*\bspotify\b', lowered):
            return PermissionAssessment(RiskLevel.READ_ONLY, 'conversation', 'No tool action detected.', False)

        risk = RiskLevel.READ_ONLY
        category = 'read-only tool access'
        reason = 'The request appears to inspect information without changing it.'
        for candidate, patterns, label, explanation in (
            (RiskLevel.DESTRUCTIVE, self._DESTRUCTIVE, 'destructive action', 'This action may permanently delete or overwrite data.'),
            (RiskLevel.EXTERNAL, self._EXTERNAL, 'external side effect', 'This action may communicate, publish, schedule, or spend outside Jarvis.'),
            (RiskLevel.REVERSIBLE, self._REVERSIBLE, 'device or data change', 'This action may change files, applications, or the device.'),
        ):
            if any(re.search(pattern, lowered) for pattern in patterns):
                risk, category, reason = candidate, label, explanation
                break

        requires_confirmation = self.mode == 'strict' or (
            self.mode == 'balanced' and risk >= RiskLevel.REVERSIBLE
        )
        return PermissionAssessment(risk, category, reason, requires_confirmation)

    def request(self, text, assessment):
        now = self._clock()
        pending = PendingAction(text, assessment, now, now + self.timeout_seconds)
        with self._lock:
            self._pending = pending
        return pending

    def handle_command(self, text):
        normalized = text.strip().lower().strip(' .!?')
        if normalized in self.CONFIRM_COMMANDS:
            if not normalized.startswith('/') and self.pending is None:
                return None, None
            return 'confirmed', self._consume()
        if normalized in self.DENY_COMMANDS:
            if not normalized.startswith('/') and self.pending is None:
                return None, None
            return 'denied', self._consume()
        return None, None

    def clear(self):
        with self._lock:
            pending = self._pending
            self._pending = None
            return pending

    def confirmation_message(self, pending):
        preview = ' '.join(pending.text.split())
        if len(preview) > 180:
            preview = preview[:177] + '...'
        risk = pending.assessment.risk.name.replace('_', ' ').lower()
        return (
            f'Permission required ({risk}): {pending.assessment.reason} '
            f'Proposed request: "{preview}". Type /confirm to proceed once or /deny to reject it. '
            f'This approval expires in {self.timeout_seconds} seconds.'
        )

    @staticmethod
    def execution_directive(assessment, approved=False):
        if assessment.risk == RiskLevel.READ_ONLY:
            return (
                'PERMISSION BOUNDARY: This request is authorized for read-only inspection only. '
                'Do not create, edit, delete, execute, install, send, publish, or otherwise change external state.'
            )
        if approved:
            return (
                'PERMISSION BOUNDARY: The user approved this request once. Perform only the action explicitly '
                'described by the user. Do not broaden its targets or add unrelated side effects.'
            )
        return 'PERMISSION BOUNDARY: Do not perform side effects without explicit user confirmation.'

    def _consume(self):
        with self._lock:
            self._expire_locked()
            pending = self._pending
            self._pending = None
            return pending

    def _expire_locked(self):
        if self._pending is not None and self._clock() >= self._pending.expires_at:
            self._pending = None
