"""Immutable authenticated Bridge receipts; no business or model operations."""
from dataclasses import dataclass
from copy import deepcopy
import re


INPUT_TYPES = frozenset(('InputText', 'Picker', 'TopicPickerControl', 'Boolean', 'Date', 'DateTime', 'Time'))
UNSET = object()


class BackendControlChanged(RuntimeError):
    """Exact own attempt was refused before dispatch; original is held, never retried."""
    def __init__(self, input_control, owner, attempt_id):
        super().__init__('Native input boundary changed before dispatch')
        self.input_control, self.owner, self.attempt_id = input_control, owner, attempt_id
        self.body_closed = True


def _request_id(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{32}', value) is not None


@dataclass(frozen=True)
class BackendEvent:
    event_id: int
    business_request_id: str
    ui_type: str
    text: str
    control_uid: str
    owner: object

    @classmethod
    def parse(cls, value, request_id, owner):
        if (type(value) is not dict or set(value) != {'id', 'source', 'businessRequestId', 'uiType',
                'text', 'streamComplete', 'controlUid'} or value.get('source') != 'servicenow_bridge_event'
                or not _request_id(request_id) or value.get('businessRequestId') != request_id
                or type(value.get('id')) is not int or value['id'] <= 0
                or value.get('uiType') not in INPUT_TYPES | {'OutputText'}
                or type(value.get('text')) is not str or len(value['text']) > 8000
                or value.get('streamComplete') is not True
                or type(value.get('controlUid')) is not str or len(value['controlUid']) > 256
                or owner is None):
            raise ValueError('Invalid owned backend event')
        return cls(value['id'], request_id, value['uiType'], value['text'], value['controlUid'], owner)


@dataclass(frozen=True)
class BackendState:
    request_id: str
    action: str
    busy: bool
    ended: bool
    failed: bool
    owner: object

    @classmethod
    def parse(cls, value, request_id, owner):
        if (type(value) is not dict or set(value) != {'source', 'requestId', 'action', 'busy', 'ended', 'failed'}
                or value.get('source') != 'servicenow_bridge_state' or not _request_id(request_id)
                or value.get('requestId') != request_id or value.get('action') != 'MESSAGE'
                or any(type(value.get(name)) is not bool for name in ('busy', 'ended', 'failed'))
                or owner is None):
            raise ValueError('Invalid owned backend state')
        return cls(request_id, value['action'], value['busy'], value['ended'], value['failed'], owner)


@dataclass(frozen=True)
class ControlBinding:
    business_request_id: str
    control_type: str
    label: str
    event_id: int
    control_uid: str
    owner: object

    @classmethod
    def from_event(cls, event):
        if event is None or event.ui_type != 'Boolean':
            return None
        return cls(event.business_request_id, event.ui_type, event.text,
                   event.event_id, event.control_uid, event.owner)

    def wire(self):
        return dict(businessRequestId=self.business_request_id, controlType=self.control_type,
            label=self.label, eventId=self.event_id, controlUid=self.control_uid)


@dataclass(frozen=True)
class HeldInput:
    turn: object
    onset: object
    voice_context: object
    reason: str
    binding: object


class ControlGate:
    def __init__(self):
        self.binding = None
        self.heard = self.dispatched = False
        self.held = []
        self._held_ids = set()

    def observe(self, binding):
        if self.binding != binding:
            self.binding = binding
            self.heard = self.dispatched = False

    def mark_emitted(self, binding):
        if binding == self.binding and binding is not None and binding.label and not self.dispatched:
            self.heard = True

    def hold(self, turn, onset, voice_context, reason):
        if turn[3] not in self._held_ids:
            self._held_ids.add(turn[3])
            self.held.append(HeldInput(turn, onset, deepcopy(voice_context), reason, self.binding))
        return False

    def admit(self, turn, onset, voice_context):
        if self.binding is None:
            return True
        if not self.heard:
            return self.hold(turn, onset, voice_context, 'control_unheard')
        if onset != self.binding:
            return self.hold(turn, onset, voice_context, 'control_onset_unbound')
        if self.dispatched:
            return self.hold(turn, onset, voice_context, 'control_already_dispatched')
        self.dispatched = True
        return True

    def retire(self):
        self.observe(None)
