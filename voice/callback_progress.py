"""Public Bot API processing labels; deliberately no agent/result authority."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ProcessingUpdate:
    request_id: str
    revision: int
    observed_at: float
    messages: tuple[str, ...]


class CallbackProgress:
    def __init__(self):
        self.request_id = ''
        self.revision = 0
        self.update = None

    def begin_request(self, request_id):
        if not isinstance(request_id, str) or not 0 < len(request_id) <= 256:
            raise ValueError('Invalid progress request')
        self.request_id = request_id
        self.update = None

    def observe(self, envelope, *, now, clean_text):
        """Caller has authenticated, matched the current user/request and deduped.

        DynamicLoader is the installed public presentation control. Its status
        is not an execution status and is intentionally ignored here.
        """
        if (not isinstance(envelope, dict) or envelope.get('requestId') != self.request_id
                or not self.request_id or type(now) not in (int, float)
                or not math.isfinite(now) or not isinstance(envelope.get('body'), list)):
            return False
        messages = []
        for control in envelope['body'][:100]:
            if (not isinstance(control, dict) or control.get('uiType') != 'ActionMsg'
                    or control.get('actionType') != 'DynamicLoader'):
                continue
            progress = control.get('progressMessages')
            if not isinstance(progress, list) or not 1 <= len(progress) <= 20:
                continue
            for item in progress:
                message = item.get('message') if isinstance(item, dict) else None
                if not isinstance(message, str) or not 0 < len(message) <= 1500:
                    continue
                text = clean_text(message).strip()
                if text and text not in messages:
                    messages.append(text[:500])
        if not messages:
            return False
        # Each presentation update replaces the bounded latest-label snapshot;
        # it never invents an agent history, child set, completion or percentage.
        current = tuple(messages[-5:])
        if self.update is not None and self.update.messages == current:
            return False
        self.revision += 1
        self.update = ProcessingUpdate(self.request_id, self.revision, float(now), current)
        return True

    def snapshot(self, *, now, max_age=30):
        update = self.update
        if (update is None or type(now) not in (int, float) or not math.isfinite(now)
                or not 0 <= now - update.observed_at <= max_age):
            return None
        return {'revision': update.revision, 'messages': list(update.messages),
                'ageSeconds': round(now - update.observed_at, 3),
                'source': 'servicenow_processing', 'agentCompletionKnown': False}
