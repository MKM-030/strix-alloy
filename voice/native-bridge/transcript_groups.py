"""Bounded text-only ledger for completed local speech; no audio operations."""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class GroupedTranscript:
    text: str
    turn: object
    owner: object
    first_pcm_at: float
    reason: str


class TranscriptGroups:
    def __init__(self, *, max_groups=8, max_parts=32, max_chars=4000, max_bytes=16000):
        self.limits = max_groups, max_parts, max_chars, max_bytes
        if any(type(x) is not int or x < 1 for x in self.limits):
            raise ValueError('invalid_transcript_group_limits')
        self._groups = {}
        self._ready = deque()
        self._closed = False

    def open(self, owner, turn):
        """Issue a unique live response token; a retired token can never reopen."""
        if self._closed or owner is None or turn is None:
            return None
        if len(self._groups) >= self.limits[0] or len(self._ready) >= self.limits[0]:
            raise ValueError('transcript_group_overflow')
        key = object()
        self._groups[key] = dict(owner=owner, turn=turn, parts={}, finished=False)
        return key

    def _group(self, key, owner):
        group = self._groups.get(key)
        return group if group is not None and group['owner'] is owner else None

    def admit(self, key, owner, turn, part, text):
        if self._closed:
            return False
        group = self._groups.get(key)
        if group is None or group['owner'] is not owner or group['turn'] is not turn or group['finished']:
            return False
        if owner is None or turn is None or type(text) is not str or not text.strip():
            return False
        if part in group['parts']:
            return False
        _, parts, chars, size = self.limits
        previous = tuple(group['parts'].values())
        joined = ' '.join([entry['text'] for entry in previous] + [text.strip()])
        if len(previous) >= parts or len(joined) > chars or len(joined.encode('utf-8')) > size:
            self._flush(key, group, 'transcript_group_overflow')
            raise ValueError('transcript_group_overflow')
        group['parts'][part] = dict(text=text.strip(), state='pending', first_pcm_at=None)
        return True

    def started(self, key, owner, part, at):
        group = self._group(key, owner)
        entry = group['parts'].get(part) if group is not None else None
        if (entry is None or entry['state'] != 'pending' or type(at) not in (int, float)
                or not math.isfinite(at) or at < 0):
            return False
        entry.update(state='started', first_pcm_at=at)
        return True

    def emitted(self, key, owner, part):
        group = self._group(key, owner)
        entry = group['parts'].get(part) if group is not None else None
        if entry is None or entry['state'] != 'started':
            return False
        entry['state'] = 'emitted'
        self._complete(key, group)
        return True

    def finish(self, key, owner):
        group = self._group(key, owner)
        if group is None:
            return False
        group['finished'] = True
        self._complete(key, group)
        return True

    def retire(self, key, owner, part):
        group = self._group(key, owner)
        entry = group['parts'].get(part) if group is not None else None
        if entry is None or entry['state'] != 'pending':
            return False
        entry['state'] = 'retired'
        self._complete(key, group)
        return True

    def _complete(self, key, group):
        if group['finished'] and all(x['state'] in ('emitted', 'retired') for x in group['parts'].values()):
            reason = ('partial_response' if any(x['state'] == 'retired' for x in group['parts'].values())
                      else 'complete')
            self._flush(key, group, reason)

    def _flush(self, key, group, reason):
        prefix = []
        for part in group['parts'].values():
            if part['state'] != 'emitted':
                break
            prefix.append(part)
        if prefix:
            self._ready.append(GroupedTranscript(' '.join(x['text'] for x in prefix),
                group['turn'], group['owner'], prefix[0]['first_pcm_at'], reason))
        del self._groups[key]

    def interrupt(self, key, owner, reason):
        group = self._group(key, owner)
        if group is None:
            return False
        self._flush(key, group, reason)
        return True

    def before_native(self):
        for key, group in tuple(self._groups.items()):
            self._flush(key, group, 'native_handoff')

    def close(self):
        self._closed = True
        for key, group in tuple(self._groups.items()):
            self._flush(key, group, 'call_closed')

    def take_ready(self):
        result = list(self._ready)
        self._ready.clear()
        return result
