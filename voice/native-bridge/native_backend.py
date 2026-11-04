"""Immutable authenticated Bridge receipts; no business or model operations."""
from dataclasses import dataclass
import re


INPUT_TYPES = frozenset(('InputText', 'Picker', 'TopicPickerControl', 'Boolean', 'Date', 'DateTime', 'Time'))
UNSET = object()


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
