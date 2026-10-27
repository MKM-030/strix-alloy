"""Inert, persistent candidate-text adapter; never a speech or action authority.

Only the injected factory can acquire a transport. It must synchronously return
an owned socket with async send_json/receive_json/close. This module imports no
model, network or process library. TextSession remains the sole receive owner.

``response_key`` is a plain dict containing the seven application identity
fields below. ``trusted_snapshot`` is a plain allowlisted dict containing the
five scope fields, raw_inputs (tuple of original ASR/spelling strings), and
public_findings (tuple of scoped evidence dicts). Optional fields are question,
capability_limits, required_children_revision and required_children. Evidence
dicts require the five scope fields plus evidence_id, source_event, sequence,
observed_at, text and superseded. Child dicts contain child_id, state and
evidence_ids. Snapshot facts must already be authorized public observations.
The schema excludes credential/reasoning fields; it cannot detect secrets or
false claims embedded by a trusted caller in an allowed string.

Call invalidate() synchronously at a correction boundary, then await its
returned coroutine to cancel/drain. Local epoch changes before any await.
Candidate text still needs an independent semantic/revision release gate.
Call is_current() at that gate and at every later speech queue consumption.
"""
import asyncio
from dataclasses import dataclass
import json
import math
import time
import uuid

from omni_protocol import ProtocolError, TextSession


SCOPE = ('call_id', 'task_id', 'task_revision', 'context_revision', 'observation_revision')
KEY = SCOPE + ('output_epoch', 'request_id')
SEED_RULES = (
    'You are an independent German conversation candidate. Authoritative user '
    'input is final Whisper text; preserve original ASR and spelling evidence. '
    'Use only the current trusted snapshot for public findings. Never invent '
    'findings, completion, confirmations, causes or capabilities. No business '
    'tools or actions: never submit, look up, retry, cancel or progress a task. '
    'No credentials or hidden reasoning. A completed reply is candidate text '
    'and does not authorize speech or any business action.\n')


def _require(condition):
    if not condition:
        raise ProtocolError('Invalid optional conversation data or state.')


def _string(value, limit, *, empty=False):
    _require(type(value) is str and (empty or bool(value)) and len(value) <= limit)
    _require(len(value.encode('utf-8')) <= limit * 4)
    return value


def _integer(value, minimum=0):
    _require(type(value) is int and minimum <= value <= 2**53 - 1)
    return value


def _scope(value):
    _string(value.get('call_id'), 128)
    _string(value.get('task_id'), 128)
    for field in SCOPE[2:]:
        _integer(value.get(field))
    return tuple(value[field] for field in SCOPE)


def _bounded(value, depth=0):
    """Bound injected decoded JSON before traversing/serializing it further."""
    _require(depth <= 5)
    if value is None or type(value) is bool:
        return 5
    if type(value) is str:
        return len(_string(value, 16384, empty=True).encode('utf-8')) + 2
    if type(value) in (int, float):
        _require(math.isfinite(value) and abs(value) <= 2**53)
        return 24
    _require(type(value) in (dict, list, tuple) and len(value) <= 64)
    size = 2
    if type(value) is dict:
        for key, item in value.items():
            _string(key, 128)
            size += len(key) + _bounded(item, depth + 1) + 4
            _require(size <= 32768)
    else:
        for item in value:
            size += _bounded(item, depth + 1) + 1
            _require(size <= 32768)
    return size


def _snapshot(snapshot, key):
    _require(type(snapshot) is dict)
    required = set(SCOPE) | {'raw_inputs', 'public_findings'}
    allowed = required | {'question', 'capability_limits', 'required_children_revision', 'required_children'}
    _require(required <= snapshot.keys() <= allowed and _scope(snapshot) == _scope(key))
    _bounded(snapshot)
    for name in ('raw_inputs', 'public_findings', 'capability_limits', 'required_children'):
        value = snapshot.get(name, ())
        _require(type(value) is tuple and len(value) <= 32)
    for raw in snapshot['raw_inputs']:
        _string(raw, 4000)
    _string(snapshot.get('question', ''), 2000, empty=True)
    for limit in snapshot.get('capability_limits', ()):
        _string(limit, 1000)
    evidence_ids = set()
    for finding in snapshot['public_findings']:
        fields = set(SCOPE) | {'evidence_id', 'source_event', 'sequence', 'observed_at', 'text', 'superseded'}
        _require(type(finding) is dict and finding.keys() == fields and _scope(finding) == _scope(key))
        evidence = _string(finding['evidence_id'], 128)
        _require(evidence not in evidence_ids)
        evidence_ids.add(evidence)
        _string(finding['source_event'], 128)
        _integer(finding['sequence'])
        _require(type(finding['observed_at']) in (int, float) and math.isfinite(finding['observed_at'])
                 and finding['observed_at'] >= 0)
        _string(finding['text'], 2000)
        _require(type(finding['superseded']) is bool and not finding['superseded'])
    if 'required_children' in snapshot:
        _integer(snapshot.get('required_children_revision'))
    children = set()
    for child in snapshot.get('required_children', ()):
        _require(type(child) is dict and child.keys() == {'child_id', 'state', 'evidence_ids'})
        child_id = _string(child['child_id'], 128)
        _require(child_id not in children)
        children.add(child_id)
        _require(child['state'] in ('running', 'completed', 'unavailable'))
        refs = child['evidence_ids']
        _require(type(refs) is tuple and len(refs) <= 32)
        for ref in refs:
            _require(_string(ref, 128) in evidence_ids)
    encoded = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    _string(encoded, 10000)
    return encoded


@dataclass(frozen=True)
class ResponseIdentity:
    call_id: str
    task_id: str
    task_revision: int
    context_revision: int
    observation_revision: int
    output_epoch: int
    request_id: str
    socket_instance: str
    server_session_id: str
    turn_id: int
    generation_id: int


@dataclass(frozen=True)
class SessionRef:
    call_id: str
    output_epoch: int
    socket_instance: str
    server_session_id: str


@dataclass(frozen=True)
class CandidateReply:
    text: str = ''
    identity: ResponseIdentity | None = None
    authoritative_whisper_text: str = ''
    submitted_at: float | None = None
    first_valid_text_at: float | None = None
    done_at: float | None = None
    terminal_at: float | None = None
    cancelled: bool = False
    failure: str | None = None


class _ObservedSocket:
    """One receive boundary, shared by the composed TextSession only."""
    def __init__(self, raw, now):
        self.raw, self.now = raw, now
        self.closed = False
        self.session_id = None
        self.turn_id = self.generation_id = None
        self.last_turn = self.last_generation = 0
        self.first_at = self.done_at = self.terminal_at = None
        self.delta_size = self.events = 0

    def begin_response(self):
        # Context send can be superseded before input.text. Do not bind that
        # unsubmitted request to the preceding response's IDs or measurements.
        self.turn_id = self.generation_id = None
        self.first_at = self.done_at = self.terminal_at = None
        self.delta_size = self.events = 0

    async def send_json(self, event):
        _require(not self.closed)
        if event['type'] == 'input.text':
            self.begin_response()
        await self.raw.send_json(event)

    async def receive_json(self):
        while True:
            event = await self.raw.receive_json()
            _require(not self.closed)
            _bounded(event)
            _require(type(event) is dict)
            kind = _string(event.get('type'), 64)
            self.events += 1
            _require(self.events <= 4096)
            if kind == 'session.ready':
                _require(self.session_id is None and event.get('mode') == 'text')
                self.session_id = _string(event.get('session_id'), 128)
                return event
            _require(self.session_id is not None)
            if 'session_id' in event:
                _require(event['session_id'] == self.session_id)
            _require(kind in ('input.committed', 'response.created', 'response.text.delta',
                              'response.text.done', 'response.cancelled', 'metrics'))
            incoming = event.get('generation_id')
            if incoming is not None:
                _integer(incoming, 1)
                if incoming <= self.last_generation:
                    if 'turn_id' in event:
                        _require(0 < _integer(event['turn_id']) <= self.last_turn)
                    # TextSession discards old generations before parsing deltas.
                    return event
            if kind == 'input.committed':
                _require(self.turn_id is None and incoming is None and event.get('text') is True)
                self.turn_id = _integer(event.get('turn_id'), 1)
                _require(self.turn_id > self.last_turn)
            elif kind == 'response.created':
                _require(self.turn_id is not None and self.generation_id is None
                         and type(event.get('turn_id')) is int and event['turn_id'] == self.turn_id)
                self.generation_id = _integer(incoming, 1)
            else:
                _require(self.generation_id is not None and incoming == self.generation_id)
                if 'turn_id' in event:
                    _require(type(event['turn_id']) is int and event['turn_id'] == self.turn_id)
                if kind == 'response.text.delta':
                    delta = _string(event.get('delta'), 16384, empty=True)
                    if delta == '':
                        continue
                    self.delta_size += len(delta)
                    _require(self.delta_size <= 16384)
                    if self.first_at is None:
                        self.first_at = self.now()
                elif kind == 'response.text.done':
                    _require(self.done_at is None)
                    _string(event.get('text'), 16384, empty=True)
                    self.done_at = self.now()
                elif kind == 'metrics':
                    _require(type(event.get('cancelled')) is bool
                             and type(event.get('turn_id')) is int and event['turn_id'] == self.turn_id)
                    self.terminal_at = self.now()
                    self.last_turn, self.last_generation = self.turn_id, self.generation_id
            return event

    async def close(self):
        if not self.closed:
            self.closed = True
            await self.raw.close()


class OmniConversation:
    def __init__(self, socket_factory, *, clock=time.monotonic, deadlines=None):
        _require(callable(socket_factory) and callable(clock))
        self._factory, self._clock = socket_factory, clock
        limits = dict(handshake_seconds=10, turn_seconds=30, control_seconds=1, cleanup_seconds=.25)
        if deadlines is not None:
            _require(type(deadlines) is dict and deadlines.keys() <= limits.keys())
            limits.update(deadlines)
        # Frozen TextSession validates these bounds too; validate before factory.
        for name, maximum in (('handshake_seconds', 10), ('turn_seconds', 30),
                              ('control_seconds', 1), ('cleanup_seconds', 1)):
            value = limits[name]
            _require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= maximum)
        self._limits = limits
        self._state, self._busy, self._invalidating = 'new', False, 0
        self._session = self._socket = self._active_turn = None
        self._last_time = None
        self._key = self._bound_scope = None
        self._response_done = asyncio.Event()
        self._response_done.set()
        self.output_epoch = 0
        self.call_id = self.socket_instance = self.server_session_id = None

    def _now(self):
        value = self._clock()
        _require(type(value) in (int, float) and math.isfinite(value)
                 and (self._last_time is None or value >= self._last_time))
        self._last_time = value
        return value

    async def start(self, call_id, output_epoch, seed_rules):
        _require(self._state == 'new')
        _string(call_id, 128)
        _integer(output_epoch, 1)
        prompt = SEED_RULES + _string(seed_rules, 10000)
        self._state = 'starting'
        self.call_id, self.output_epoch = call_id, output_epoch
        self.socket_instance = uuid.uuid4().hex
        try:
            self._socket = _ObservedSocket(self._factory(), self._now)
            self._session = TextSession(self._socket, **self._limits)
            await self._session.start(prompt)
            _require(self._state == 'starting')
            self.server_session_id = self._session.session_id
            self._state = 'ready'
            return SessionRef(call_id, output_epoch, self.socket_instance, self.server_session_id)
        except BaseException:
            await self._abort()
            raise

    def is_current(self, identity):
        return (type(identity) is ResponseIdentity and self._state == 'ready'
                and self._key is not None and self._invalidating == 0
                and tuple(getattr(identity, name) for name in KEY) == self._key
                and identity.output_epoch == self.output_epoch
                and identity.socket_instance == self.socket_instance
                and identity.server_session_id == self.server_session_id
                and self._socket is not None and not self._socket.closed
                and identity.turn_id == self._socket.last_turn
                and identity.generation_id == self._socket.last_generation)

    def is_stream_current(self, identity):
        """A validated active generation may stream, but never across a revision."""
        return (type(identity) is ResponseIdentity and self._state == 'ready'
                and self._key is not None and self._invalidating == 0
                and tuple(getattr(identity, name) for name in KEY) == self._key
                and identity.output_epoch == self.output_epoch
                and identity.socket_instance == self.socket_instance
                and identity.server_session_id == self.server_session_id
                and self._socket is not None and not self._socket.closed
                and identity.turn_id == self._socket.turn_id
                and identity.generation_id == self._socket.generation_id)

    def _candidate(self, key, raw, submitted, *, text='', cancelled=False, failure=None):
        socket = self._socket
        identity = None
        if socket is not None and socket.turn_id is not None and socket.generation_id is not None:
            identity = ResponseIdentity(*key, self.socket_instance, self.server_session_id,
                                        socket.turn_id, socket.generation_id)
        return CandidateReply(text, identity, raw, submitted,
                              socket.first_at if socket else None, socket.done_at if socket else None,
                              socket.terminal_at if socket else None, cancelled, failure)

    async def respond(self, final_whisper_text, trusted_snapshot, response_key, *, on_delta=None):
        if self._state != 'ready':
            return CandidateReply(failure='unavailable')
        if self._busy or self._invalidating:
            return CandidateReply(failure='busy')
        try:
            raw = _string(final_whisper_text, 4000)
            _require(on_delta is None or callable(on_delta))
            _require(type(response_key) is dict and response_key.keys() == set(KEY))
            scope = _scope(response_key)
            _string(response_key['request_id'], 128)
            _integer(response_key['output_epoch'], 1)
            _require(scope[0] == self.call_id and response_key['output_epoch'] == self.output_epoch)
            if self._bound_scope is not None:
                _require(scope[:2] == self._bound_scope[:2]
                         and all(new >= old for new, old in zip(scope[2:], self._bound_scope[2:])))
            patch = _snapshot(trusted_snapshot, response_key)
            key = tuple(response_key[name] for name in KEY)
            _require(key != self._key)
        except (ProtocolError, ValueError, TypeError, OverflowError, UnicodeError):
            return CandidateReply(failure='invalid_input')
        self._busy = True
        self._response_done.clear()
        self._key, self._bound_scope = key, scope
        self._socket.begin_response()
        submitted = None
        try:
            submitted = self._now()
            await self._session.update_context(patch)
            if self._state != 'ready' or key[5] != self.output_epoch:
                return self._candidate(key, raw, submitted, cancelled=True, failure='superseded')
            async def stream(delta):
                identity = self._candidate(key, raw, submitted).identity
                if self.is_stream_current(identity):
                    await on_delta(delta, identity)
            self._active_turn = asyncio.create_task(self._session.turn(key[6], raw,
                on_delta=stream if on_delta is not None else None))
            result = await self._active_turn
            candidate = self._candidate(key, raw, submitted, text=result['text'], cancelled=result['cancelled'])
            if result['cancelled'] or not self.is_current(candidate.identity):
                return self._candidate(key, raw, submitted, cancelled=True, failure='superseded')
            _require(candidate.done_at is not None and candidate.terminal_at is not None)
            return candidate
        except asyncio.CancelledError:
            interrupted = self._state != 'ready' or key[5] != self.output_epoch
            await self._abort()
            if not interrupted:
                raise
            return self._candidate(key, raw, submitted, cancelled=True, failure='unavailable')
        except Exception:
            await self._abort()
            return self._candidate(key, raw, submitted, cancelled=key[5] != self.output_epoch, failure='unavailable')
        finally:
            self._active_turn = None
            self._busy = False
            self._response_done.set()

    def invalidate(self, new_epoch, reason):
        """Invalidate immediately; await return value before another respond()."""
        _integer(new_epoch, 1)
        _require(new_epoch > self.output_epoch)
        _string(reason, 512)
        self.output_epoch = new_epoch
        self._key = None
        self._invalidating += 1
        return self._drain()

    async def _drain(self):
        deadline = asyncio.get_running_loop().time() + self._limits['control_seconds']
        try:
            if self._state == 'ready' and self._busy:
                if self._active_turn is not None:
                    await TextSession._until(self._session.cancel(), deadline)
                await TextSession._until(self._response_done.wait(), deadline)
                _require(not self._session.closed)
        except BaseException as error:
            await self._abort()
            if isinstance(error, asyncio.CancelledError):
                raise
        finally:
            self._invalidating -= 1

    async def _abort(self):
        self._state = 'unavailable'
        self._key = None
        if self._active_turn is not None and not self._active_turn.done():
            self._active_turn.cancel()
        if self._socket is not None:
            try:
                await TextSession._until(self._socket.close(), asyncio.get_running_loop().time()
                                         + self._limits['cleanup_seconds'])
            except Exception:
                pass

    async def close(self):
        if self._state == 'unavailable':
            return
        self._state = 'unavailable'
        self._key = None
        self.output_epoch += 1
        try:
            if self._session is not None and not self._session.closed:
                await self._session.close()
        except Exception:
            pass
        finally:
            await self._abort()
