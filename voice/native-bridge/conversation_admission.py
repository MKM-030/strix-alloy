"""Request-owned bounded HTTP admission transport; no routing authority."""
import asyncio
import json
import math
import hashlib
import http.client
import io
import socket
import threading
import time
import uuid
from dataclasses import dataclass, replace
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import nullcontext

from routing_policy import ContextBudgetExceeded
from route_proposal import ProposalError

MAX_REQUEST_BYTES = 16384
MAX_BODY_BYTES = 8192
MAX_RESPONSE_WIRE_BYTES = 16384
COUNT_PATH = '/v1/chat/completions/input_tokens'
INFERENCE_PATH = '/v1/chat/completions'


class AdmissionUnavailable(OSError):
    """Bounded protocol failure, never model JSON/schema evidence."""


@dataclass(frozen=True)
class AdmissionBudget:
    input_tokens: int
    completion_tokens: int

    def __post_init__(self):
        if (type(self.input_tokens) is not int or type(self.completion_tokens) is not int
                or min(self.input_tokens, self.completion_tokens) <= 0
                or self.input_tokens + self.completion_tokens > 4096):
            raise ValueError('invalid admission budget')


ROUTE_BUDGET = AdmissionBudget(3584, 24)
PLANNER_BUDGET = AdmissionBudget(3072, 128)


@dataclass(frozen=True)
class PreparedChat:
    payload: bytes
    catalog: bytes
    binding: object


@dataclass(frozen=True)
class AdmissionSnapshot:
    protocol: str = 'pinned_chat_count_v1'
    request_id: str = ''
    stage: str = 'prepare'
    reason: str = 'pending'
    input_tokens: int | None = None
    count_valid: bool | None = None
    payload_bound: bool | None = None
    usage_count_match: bool | None = None
    payload_sha256: str | None = None
    catalog_sha256: str | None = None
    count_attempts: int = 0
    inference_attempts: int = 0
    total_attempts: int = 0
    count_request_bytes: int = 0
    inference_request_bytes: int = 0
    transaction_bytes: int = 0
    prepare_ms: float | None = None
    count_ms: float | None = None
    inference_ms: float | None = None
    elapsed_ms: float = 0
    connection_closed: bool = True
    worker_outstanding: bool = True
    input_limit: int = 3584
    completion_limit: int = 24
    role: str = ''
    slot_id: int | None = None
    owner_id: str = ''
    lease_id: str = ''
    predecessor: str = ''
    deadline: float = 0
    started_at: float = 0
    count_dispatched_at: float | None = None
    inference_dispatched_at: float | None = None
    count_terminal_at: float | None = None
    inference_terminal_at: float | None = None
    wait_started: float | None = None
    acquired_at: float | None = None
    sealed_at: float | None = None
    publication_revoked_at: float | None = None
    drain_started_at: float | None = None
    cancelled_at: float | None = None
    closed_at: float | None = None
    worker_terminal_at: float | None = None
    full_terminal_at: float | None = None
    active_task: int | None = None
    active_observed_at: float | None = None
    release_basis: str = ''
    released_at: float | None = None
    unresolved_reason: str = ''
    slot_get_attempts: int = 0
    cleanup_get_attempts: int = 0
    witness_get_attempts: int = 0
    cleanup_outstanding: bool = False
    all_http_attempts: int = 0


class AdmissionRequest:
    def __init__(self, timeout, *, budget=ROUTE_BUDGET):
        if budget not in (ROUTE_BUDGET, PLANNER_BUDGET):
            raise ValueError('unsupported admission budget')
        self.budget = budget
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.socket = None
        self.sealed = False
        self.payload = None
        self.slot_owner = None
        self.cleanup_started = False
        self.witness_started = False
        self.receipt = AdmissionSnapshot(request_id=uuid.uuid4().hex,
            input_limit=budget.input_tokens, completion_limit=budget.completion_tokens,
            deadline=self.deadline, started_at=self.started)

    def check(self):
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise TimeoutError('conversation deadline')
        return remaining

    def update(self, **facts):
        with self.lock:
            # Terminal cancellation wins against a worker returning late.
            if self.sealed:
                facts.pop('reason', None)
                facts.pop('stage', None)
            self.receipt = replace(self.receipt, **facts)

    def snapshot(self):
        with self.lock:
            return replace(self.receipt, elapsed_ms=(time.monotonic() - self.started) * 1000)

    def close(self):
        with self.lock:
            owned, self.socket = self.socket, None
            self.receipt = replace(self.receipt, connection_closed=True, closed_at=time.monotonic())
        if owned is not None:
            try: owned.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            owned.close()

    def retire(self, reason):
        with self.lock:
            if not self.sealed or (self.receipt.drain_started_at is not None and not self.cancelled.is_set()):
                self.receipt = replace(self.receipt, reason=reason)
            self.sealed = True
            self.cancelled.set()
            self.receipt = replace(self.receipt, sealed_at=self.receipt.sealed_at or time.monotonic(),
                cancelled_at=self.receipt.cancelled_at or time.monotonic())
        self.close()

    def revoke_for_drain(self, reason='cancelled'):
        """Revoke publication/new dispatch atomically; keep only an existing read.

        This never renews the deadline or clears a hard abort. The outer job
        owns publication validity; check() deliberately permits a sealed drain.
        """
        with self.lock:
            now = time.monotonic()
            self.sealed = True
            self.receipt = replace(self.receipt, sealed_at=self.receipt.sealed_at or now,
                publication_revoked_at=self.receipt.publication_revoked_at or now)
            if (self.budget == PLANNER_BUDGET and self.receipt.inference_attempts == 1
                    and not self.cancelled.is_set() and now < self.deadline):
                self.receipt = replace(self.receipt, reason=reason,
                    drain_started_at=self.receipt.drain_started_at or now)
                return True
            self.cancelled.set()
            self.receipt = replace(self.receipt, reason=reason,
                cancelled_at=self.receipt.cancelled_at or now)
        self.close()
        return False

    def bind(self, payload, catalog):
        self.check()
        self.payload = payload  # bytes, frozen before either request is prepared
        self.update(payload_sha256=hashlib.sha256(payload).hexdigest(),
                    catalog_sha256=hashlib.sha256(catalog).hexdigest())

    def dispatch(self, phase, wire_bytes):
        # Only a small state transition is locked. Socket I/O never holds it.
        if self.slot_owner is not None:
            self.slot_owner.guard(self)
        owner = self.slot_owner
        with owner.lock if owner is not None else nullcontext():
            with self.lock:
                self.check()
                if (self.sealed or getattr(self.receipt, phase + '_attempts')
                        or (owner is not None and owner.invalid)):
                    raise AdmissionUnavailable('retired dispatch')
                if phase == 'inference' and (self.receipt.count_valid is not True or
                                            self.receipt.input_tokens > self.budget.input_tokens):
                    raise AdmissionUnavailable('count gate')
                self.receipt = replace(self.receipt, stage=phase,
                    **{phase + '_attempts': 1, phase + '_dispatched_at': time.monotonic()},
                    total_attempts=self.receipt.total_attempts + 1,
                    all_http_attempts=self.receipt.all_http_attempts + 1,
                    transaction_bytes=self.receipt.transaction_bytes + wire_bytes)
                if owner is not None:
                    field = phase + '_attempts'
                    setattr(owner, field, getattr(owner, field) + 1)

    def connect(self, host, port):
        owned = socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET, socket.SOCK_STREAM)
        with self.lock:
            try:
                self.check()
                self.socket = owned
                self.receipt = replace(self.receipt, connection_closed=False)
            except BaseException:
                owned.close()
                raise
        owned.settimeout(self.check())
        owned.connect((host, port))
        return owned


class _DeadlineReader(io.RawIOBase):
    """HTTPResponse's buffered parser gets a fresh remaining timeout per recv."""
    def __init__(self, owned, request):
        super().__init__()
        self.owned, self.request, self.received = owned, request, 0

    def readable(self): return True

    def readinto(self, buffer):
        self.owned.settimeout(self.request.check())
        amount = min(len(buffer), MAX_RESPONSE_WIRE_BYTES + 1 - self.received)
        if amount <= 0:
            raise AdmissionUnavailable('response framing bound')
        count = self.owned.recv_into(memoryview(buffer)[:amount])
        self.received += count
        if self.received > MAX_RESPONSE_WIRE_BYTES:
            raise AdmissionUnavailable('response framing bound')
        self.request.check()
        return count


class _ResponseSocket:
    def __init__(self, owned, request):
        self.reader = _DeadlineReader(owned, request)

    def makefile(self, *_args, **_kwargs):
        return io.BufferedReader(self.reader)


class _CompleteHTTPResponse(http.client.HTTPResponse):
    """Tighten two permissive stdlib chunk boundaries; keep its HTTP parser."""
    def _get_chunk_left(self):
        if self.chunk_left == 0:
            if self._safe_read(2) != b'\r\n':
                raise AdmissionUnavailable('invalid chunk separator')
            self.chunk_left = None
        return super()._get_chunk_left()

    def _read_and_discard_trailer(self):
        while True:
            line = self.fp.readline(MAX_RESPONSE_WIRE_BYTES + 1)
            if not line.endswith(b'\r\n'):
                raise AdmissionUnavailable('incomplete chunk trailer')
            if line == b'\r\n':
                return


def _read_token(token_file):
    if token_file is None:
        raise AdmissionUnavailable('missing authentication')
    with Path(token_file).open('rb') as stream:
        raw = stream.read(4100)
    try: token = raw.decode('utf-8').strip()
    except UnicodeError: raise AdmissionUnavailable('invalid authentication') from None
    if (len(raw) >= 4100 or not token or len(token) > 4096 or not token.isascii()
            or any(ord(c) < 32 or ord(c) == 127 for c in token)):
        raise AdmissionUnavailable('invalid authentication')
    return token, hashlib.sha256(raw).digest()


def prepare_frames(host, port, payload, token_file, *, token=None, paths=None, method='POST'):
    """These exact bytes are sent; there are no implicit client headers."""
    authority = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
    headers = [('Host', authority), ('Content-Type', 'application/json'),
               ('Accept', 'application/json'), ('Content-Length', str(len(payload))),
               ('Connection', 'keep-alive')]
    if token is not None:
        headers.append(('Authorization', 'Bearer ' + token))
    elif token_file:
        # Bound local authentication reads too; a slow read is retired by caller.
        with token_file.open('r', encoding='utf-8') as stream:
            token = stream.read(4098).strip()
            if stream.read(1):
                raise AdmissionUnavailable('invalid authentication')
        if not token or len(token) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in token):
            raise AdmissionUnavailable('invalid authentication')
        headers.append(('Authorization', 'Bearer ' + token))
    try:
        header_bytes = ''.join(f'{key}: {value}\r\n' for key, value in headers).encode('ascii')
    except UnicodeError:
        raise AdmissionUnavailable('invalid authentication') from None
    frames = tuple(f'{method} {path} HTTP/1.1\r\n'.encode('ascii') + header_bytes + b'\r\n' + payload
                   for path in (paths or (COUNT_PATH, INFERENCE_PATH)))
    if len(payload) > MAX_REQUEST_BYTES or any(len(frame) > MAX_REQUEST_BYTES for frame in frames):
        raise ContextBudgetExceeded('conversation request framing too large')
    return frames


def exchange(request, owned, frame, *, method='POST'):
    """Exactly one attempted HTTP exchange; never reconnect or retry."""
    owned.settimeout(request.check())
    owned.sendall(frame)
    response = _CompleteHTTPResponse(_ResponseSocket(owned, request), method=method)
    try:
        response.begin()
        request.check()
        if response.status != 200:
            raise AdmissionUnavailable('endpoint rejected')
        lengths = response.headers.get_all('Content-Length', [])
        encodings = response.headers.get_all('Transfer-Encoding', [])
        if (len(lengths) > 1 or len(encodings) > 1 or (lengths and encodings)
                or (encodings and encodings[0].lower() != 'chunked')
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
            raise AdmissionUnavailable('ambiguous response framing')
        if lengths:
            if not lengths[0].isascii() or not lengths[0].isdigit() or int(lengths[0]) > MAX_BODY_BYTES:
                raise AdmissionUnavailable('response body bound')
        elif not response.chunked:
            raise AdmissionUnavailable('unbounded response framing')
        # CL is checked before read(); chunk parsing must see the terminating frame.
        raw = response.read() if lengths else response.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES or not response.isclosed():
            raise AdmissionUnavailable('incomplete or oversized response')
        request.check()
        return raw, response.will_close
    except (http.client.HTTPException, ValueError) as error:
        raise AdmissionUnavailable('invalid response framing') from error
    finally:
        response.close()  # parser only; the request owns and closes the socket


def _reject_duplicates(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def _invalid_constant(value):
    raise ValueError("nonfinite JSON value")


def _strict_json(raw, max_bytes):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise ValueError("JSON too large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                           parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite JSON value")
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return value




class SharedSlotOwner:
    """One verified process generation, two persistent exclusive role leases.

    Lock order is owner.lock -> request.lock. Retirement/dispatch both use the
    request lock: sealing zero attempts and marking a possible send are atomic.
    No lock is held during host, token, socket or observer I/O. This guard is
    deliberately not readiness authority; native still requires its real proof.
    """
    ROLES = {'classifier': 0, 'planner': 1}

    def __init__(self, host_boundary, owner_pid, owner_created, endpoint, model, token_file):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
                or parsed.path != INFERENCE_PATH or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not model
                or type(owner_pid) is not int or owner_pid <= 0
                or type(owner_created) not in (int, float) or not math.isfinite(owner_created)
                or owner_created <= 0):
            raise AdmissionUnavailable('invalid owned endpoint')
        self.host_boundary = host_boundary
        self.owner_pid, self.owner_created = owner_pid, owner_created
        self.endpoint, self.model = endpoint, model
        self.host, self.port = '127.0.0.1', parsed.port
        self.token_file = Path(token_file).resolve() if token_file else None
        self.lock = threading.Lock()
        self.owner_id = uuid.uuid4().hex
        self.invalid = False
        self.initialized = False
        self.startup_attempted = False
        self.roles = dict.fromkeys(self.ROLES)
        self.waiters = dict.fromkeys(self.ROLES, False)
        self.last_task = dict.fromkeys(self.ROLES, -1)
        self.history = deque(maxlen=128)
        self.probes = deque(maxlen=128)
        self.slot_get_attempts = 0
        self.count_attempts = self.inference_attempts = 0
        self.cleanup_tasks = set()
        self.probe_workers = {}
        self.identity = self._identity()
        self.token, self.token_digest = _read_token(self.token_file)
        if self._identity() != self.identity:
            raise AdmissionUnavailable('owner changed during capture')

    def _identity(self):
        facts = self.host_boundary.process(self.owner_pid)
        if (type(facts) is not dict or type(facts.get('pid')) is not int
                or facts['pid'] != self.owner_pid
                or type(facts.get('created')) is not type(self.owner_created)
                or facts['created'] != self.owner_created
                or not isinstance(facts.get('exe'), str) or not facts['exe']
                or type(facts.get('argv')) not in (list, tuple) or not facts['argv']
                or any(type(arg) is not str for arg in facts['argv'])):
            raise AdmissionUnavailable('owner identity unavailable')
        listeners = self.host_boundary.listeners(self.port)
        if (not isinstance(listeners, (list, tuple)) or not listeners
                or any(type(item) is not dict or type(item.get('pid')) is not int
                    or item['pid'] != self.owner_pid or item.get('ip') != '127.0.0.1' for item in listeners)):
            raise AdmissionUnavailable('exclusive loopback listener unavailable')
        return (facts['pid'], facts['created'], facts['exe'], tuple(facts['argv']))

    def guard(self, request):
        request.check()
        if self.invalid: raise AdmissionUnavailable('owner invalidated')
        try:
            identity = self._identity()
            token, digest = _read_token(self.token_file)
            if identity != self.identity or token != self.token or digest != self.token_digest:
                raise AdmissionUnavailable('owner binding drift')
        except Exception as error:
            with self.lock: self.invalid = True
            raise AdmissionUnavailable('owner binding unavailable') from error
        request.check()  # A late OS read grants no dispatch permission.

    async def _bounded(self, request, action):
        worker = asyncio.create_task(asyncio.to_thread(action))
        try:
            done, _ = await asyncio.wait((worker,), timeout=request.check())
            if not done: raise TimeoutError('owner deadline')
            result = worker.result()
            request.check()
            return result
        finally:
            if not worker.done(): worker.add_done_callback(_consume)
            else: _consume(worker)

    async def initialize(self, deadline):
        with self.lock:
            if self.initialized: return
            if self.startup_attempted: raise AdmissionUnavailable('startup observation already attempted')
            self.startup_attempted = True
        probe = AdmissionRequest(max(0, deadline - time.monotonic()))
        probe.deadline = deadline
        await self._probe(None, probe)
        if not self.initialized: raise AdmissionUnavailable('slot startup unavailable')

    def matches(self, host, port, token_file):
        if (host != self.host or port != self.port or token_file is None
                or Path(token_file).resolve() != self.token_file):
            raise AdmissionUnavailable('request owner binding mismatch')

    async def acquire(self, request, role):
        if role not in self.ROLES: raise AdmissionUnavailable('unknown role')
        if (request.budget != (ROUTE_BUDGET if role == 'classifier' else PLANNER_BUDGET)
                or request.snapshot().lease_id):
            raise AdmissionUnavailable('role budget or lease mismatch')
        request.update(role=role, slot_id=self.ROLES[role], owner_id=self.owner_id,
                       wait_started=time.monotonic())
        await self._bounded(request, lambda: self.guard(request))
        waiting = False
        guarded = True
        wait_until = min(request.deadline, time.monotonic() + (.1 if role == 'planner' else 2))
        try:
            while True:
                request.check()
                refresh = False
                with self.lock:
                    if self.invalid or not self.initialized:
                        raise AdmissionUnavailable('owner not available')
                    previous = self.roles[role]
                    if previous is None or previous.snapshot().released_at is not None:
                        if guarded:
                            predecessor = previous.snapshot().lease_id if previous else ''
                            request.slot_owner = self
                            request.update(lease_id=uuid.uuid4().hex, predecessor=predecessor,
                                           acquired_at=time.monotonic())
                            self.roles[role] = request
                            return
                        refresh = True
                    else:
                        # A completed/retired unresolved lease cannot improve
                        # merely by waiting or creating another fixture.
                        if previous.sealed or not previous.snapshot().worker_outstanding:
                            raise AdmissionUnavailable('role unresolved')
                        guarded = False
                        if not waiting:
                            if self.waiters[role]: raise AdmissionUnavailable('role waiter occupied')
                            self.waiters[role] = waiting = True
                if time.monotonic() >= wait_until:
                    raise AdmissionUnavailable('role wait bound')
                if refresh:
                    await self._bounded(request, lambda: self.guard(request))
                    guarded = True
                    continue
                await asyncio.sleep(min(.005, max(0, wait_until-time.monotonic())))
        finally:
            if waiting:
                with self.lock: self.waiters[role] = False

    def validate_payload(self, request, data):
        slot = self.ROLES[request.snapshot().role]
        if (type(data.get('id_slot')) is not int or data['id_slot'] != slot
                or data.get('model') != self.model
                or ('n' in data and (type(data['n']) is not int or data['n'] != 1))
                or ('stream' in data and data['stream'] is not False)
                or any(key in data for key in ('resume', 'resume_id', 'stream_options'))):
            raise AdmissionUnavailable('invalid reserved request shape')

    def _parse_slots(self, raw):
        # Reuse the strict bounded JSON parser, with an object wrapper solely to
        # allow the pinned /slots array. Its original body remains bounded.
        if len(raw) > MAX_BODY_BYTES: raise AdmissionUnavailable('slots body bound')
        value = _strict_json(b'{"slots":' + raw + b'}', MAX_BODY_BYTES + 10)['slots']
        if type(value) is not list or len(value) != 2:
            raise AdmissionUnavailable('slot count mismatch')
        result = {}
        for item in value:
            if (type(item) is not dict or type(item.get('id')) is not int or item['id'] not in (0, 1)
                    or item['id'] in result or type(item.get('n_ctx')) is not int or item['n_ctx'] != 4096
                    or type(item.get('is_processing')) is not bool
                    or ('id_task' in item and (type(item['id_task']) is not int or item['id_task'] < -1))
                    or (item['is_processing'] and ('id_task' not in item or item['id_task'] < 0))):
                raise AdmissionUnavailable('invalid slot observation')
            # Pinned b10690 omits id_task on a virgin idle slot. Absence is not
            # an active witness, and is never compared to an OAI completion ID.
            result[item['id']] = (item['is_processing'], item.get('id_task'))
        return result

    def _release_locked(self, request, basis):
        # Caller holds owner lock. Retirement uses request.lock too, so no late
        # count thread can cross a zero-inference release/seal.
        with request.lock:
            if request.receipt.released_at is not None: return
            request.sealed = True
            request.receipt = replace(request.receipt, sealed_at=request.receipt.sealed_at or time.monotonic(),
                release_basis=basis, released_at=time.monotonic(), unresolved_reason='')
            self.history.append(request)

    def _apply_slots(self, request, state, sent_at):
        with self.lock:
            if self.invalid: raise AdmissionUnavailable('owner invalidated')
            if request is None:
                if any(busy for busy, _ in state.values()): raise AdmissionUnavailable('startup slots busy')
                self.last_task = {role: state[slot][1] for role, slot in self.ROLES.items()}
                self.initialized = True
                return
            receipt = request.snapshot()
            if self.roles[receipt.role] is not request or receipt.released_at is not None: return
            busy, task = state[receipt.slot_id]
            if receipt.unresolved_reason == 'unexpected_task': return
            if busy:
                if (receipt.inference_attempts != 1 or task == self.last_task[receipt.role]
                        or (receipt.active_task is not None and receipt.active_task != task)):
                    request.update(unresolved_reason='unexpected_task')
                    return
                request.update(active_task=task, active_observed_at=receipt.active_observed_at or time.monotonic(),
                               unresolved_reason='target_busy')
            elif receipt.active_task is not None and task not in (None, -1, receipt.active_task):
                request.update(unresolved_reason='unexpected_task')
            elif ((receipt.full_terminal_at is not None and sent_at >= receipt.full_terminal_at)
                    or (receipt.active_observed_at is not None and sent_at >= receipt.active_observed_at)):
                self.last_task[receipt.role] = task
                self._release_locked(request, 'full_terminal_then_idle' if receipt.full_terminal_at else 'active_then_idle')
            else:
                request.update(unresolved_reason='no_terminal_or_active_witness')

    async def observe_active(self, request, deadline):
        """One qualification-only active-slot observation on the current planner.

        This does not grant release or readiness. Ordinary native callers never
        request this witness; completion still needs its fresh cleanup GET.
        """
        with self.lock:
            receipt = request.snapshot()
            if (self.invalid or not self.initialized or self.roles['planner'] is not request
                    or receipt.role != 'planner' or receipt.inference_attempts != 1
                    or receipt.full_terminal_at is not None or receipt.released_at is not None
                    or request.cancelled.is_set() or request.witness_started):
                raise AdmissionUnavailable('active witness unavailable')
            request.witness_started = True
        deadline = min(deadline, request.deadline)
        probe = AdmissionRequest(max(0, deadline-time.monotonic()))
        probe.deadline = deadline
        await self._probe(request, probe, kind='witness')
        return request.snapshot()

    async def _probe(self, request, probe, *, kind='cleanup'):
        role = request.snapshot().role if request else 'startup'
        with self.lock:
            previous = self.probe_workers.get(role)
            if previous is not None and not previous.done(): raise AdmissionUnavailable('observer outstanding')
        record = {'role': role, 'kind': kind if request else 'startup', 'owner_id': self.owner_id,
            'lease_id': request.snapshot().lease_id if request else '',
            'request_id': request.snapshot().request_id if request else '',
            'probe_request_id': probe.snapshot().request_id,
            'deadline': probe.deadline, 'sent_at': None, 'received_at': None,
            'terminal_at': None, 'connection_closed': True, 'worker_outstanding': True, 'reason': 'pending'}
        def observe():
            try:
                self.guard(probe)
                frame = prepare_frames(self.host, self.port, b'', None, token=self.token,
                                       paths=('/slots',), method='GET')[0]
                with self.lock:
                    probe.check()
                    if request:
                        with request.lock:
                            receipt = request.receipt
                            field = 'witness_get_attempts' if kind == 'witness' else 'cleanup_get_attempts'
                            cap = 2 if kind == 'cleanup' and receipt.cancelled_at is not None else 1
                            if getattr(receipt, field) >= cap: raise AdmissionUnavailable('observer cap')
                            if kind == 'witness' and (receipt.full_terminal_at is not None
                                    or receipt.cancelled_at is not None or receipt.released_at is not None):
                                raise AdmissionUnavailable('active witness window closed')
                            # The GET attempt marker and pre-terminal witness
                            # check share the terminal receipt's lock.
                            record['sent_at'] = time.monotonic()
                            request.receipt = replace(receipt, slot_get_attempts=receipt.slot_get_attempts + 1,
                                **{field: getattr(receipt, field) + 1},
                                all_http_attempts=receipt.all_http_attempts + 1)
                    self.slot_get_attempts += 1
                    if request is None: record['sent_at'] = time.monotonic()
                    record['connection_closed'] = False
                owned = probe.connect(self.host, self.port)
                raw, _ = exchange(probe, owned, frame, method='GET')
                state = self._parse_slots(raw)
                self.guard(probe)
                record['received_at'] = time.monotonic()
                self._apply_slots(request, state, record['sent_at'])
                record['reason'] = 'observed'
            except Exception as error:
                record['reason'] = 'unavailable'
                record['error_type'] = type(error).__name__
                if request: request.update(unresolved_reason='observer_unavailable')
                raise
            finally:
                probe.close()
                record['connection_closed'] = True
                record['worker_outstanding'] = False
                record['terminal_at'] = time.monotonic()
        worker = asyncio.create_task(asyncio.to_thread(observe))
        with self.lock:
            self.probe_workers[role] = worker
            self.probes.append(record)
        try:
            done, _ = await asyncio.wait((worker,), timeout=probe.check())
            if not done: raise TimeoutError('slots deadline')
            worker.result()
            probe.check()
        except BaseException:
            probe.retire('observer_retired')
            record['connection_closed'] = True
            raise
        finally:
            if not worker.done(): worker.add_done_callback(_consume)
            else: _consume(worker)

    async def completed(self, request):
        if request.snapshot().full_terminal_at is not None:
            previous = self.probe_workers.get(request.snapshot().role)
            if previous is not None and not previous.done():
                done, _ = await asyncio.wait((previous,), timeout=request.check())
                if not done: raise TimeoutError('outstanding witness deadline')
                request.check()
            probe = AdmissionRequest(max(0, request.deadline - time.monotonic()))
            probe.deadline = request.deadline
            try: await self._probe(request, probe)
            except AdmissionUnavailable:
                if self.invalid: raise
                # Valid answer, honestly unresolved role on busy/protocol error.
        request.check()

    def finish(self, request):
        with self.lock:
            receipt = request.snapshot()
            if not receipt.lease_id or receipt.released_at is not None: return
            # Sealing and the zero-attempt decision share the dispatch lock.
            with request.lock:
                if request.receipt.inference_attempts == 0:
                    request.sealed = True
                    zero = True
                else:
                    zero = False
            if zero:
                self._release_locked(request, 'sealed_zero_inference')
                return
            if not receipt.unresolved_reason: request.update(unresolved_reason='release_unproved')
            if receipt.cancelled_at is None or request.cleanup_started: return
            request.cleanup_started = True
            request.update(cleanup_outstanding=True)
        task = asyncio.create_task(self._cancel_observe(request))
        self.cleanup_tasks.add(task)
        def complete(future):
            self.cleanup_tasks.discard(future)
            request.update(cleanup_outstanding=False)
            _consume(future)
        task.add_done_callback(complete)

    async def _cancel_observe(self, request):
        cancelled = request.snapshot().cancelled_at
        await asyncio.sleep(max(0, cancelled + .08 - time.monotonic()))
        for index in range(2):
            receipt = request.snapshot()
            if receipt.released_at is not None or receipt.cleanup_get_attempts >= 2 or self.invalid: return
            previous = self.probe_workers.get(receipt.role)
            if previous is not None:
                # Never overlap or pretend a timed-out OS/socket worker ended.
                if not previous.done():
                    done, _ = await asyncio.wait((previous,), timeout=1.1)
                    if not done: return
                records = [r for r in self.probes if r['lease_id'] == receipt.lease_id and r['kind'] == 'cleanup']
                if records:
                    terminal = records[-1]['terminal_at']
                    if terminal is None: return
                    await asyncio.sleep(max(0, terminal + 1.1 - time.monotonic()))
            deadline = cancelled + .1 if index == 0 and receipt.cleanup_get_attempts == 0 else time.monotonic() + .1
            if deadline <= time.monotonic(): return
            probe = AdmissionRequest(deadline - time.monotonic())
            probe.deadline = deadline
            try: await self._probe(request, probe)
            except (OSError, ValueError): pass

    def snapshot(self):
        from dataclasses import asdict
        with self.lock:
            roles = {role: asdict(request.snapshot()) if request else None for role, request in self.roles.items()}
            return {'owner_id': self.owner_id, 'owner_pid': self.owner_pid, 'owner_created': self.owner_created,
                'initialized': self.initialized, 'invalid': self.invalid, 'roles': roles,
                'slot_get_attempts': self.slot_get_attempts,
                'count_attempts': self.count_attempts, 'inference_attempts': self.inference_attempts,
                'total_attempts': self.count_attempts + self.inference_attempts,
                'all_http_attempts': self.count_attempts + self.inference_attempts + self.slot_get_attempts,
                'probes': tuple(dict(record) for record in self.probes),
                'history': tuple(asdict(request.snapshot()) for request in self.history)}


def _chat_transaction(transaction, host, port, token_file, prepare, decode_content):
    try:
        transaction.check()
        prepared = prepare()
        payload, catalog = prepared.payload, prepared.catalog
        if len(payload) > MAX_REQUEST_BYTES:
            raise ContextBudgetExceeded('conversation request body too large')
        data = _strict_json(payload, MAX_REQUEST_BYTES)
        maximum = data.get('max_tokens')
        if transaction.slot_owner is not None:
            transaction.slot_owner.validate_payload(transaction, data)
        if type(maximum) is not int or maximum != transaction.budget.completion_tokens:
            raise AdmissionUnavailable('completion budget mismatch')
        transaction.bind(payload, catalog)
        frames = (prepare_frames(host, port, payload, token_file, token=transaction.slot_owner.token)
                  if transaction.slot_owner else prepare_frames(host, port, payload, token_file))
        transaction.update(count_request_bytes=len(frames[0]), inference_request_bytes=len(frames[1]),
            prepare_ms=(time.monotonic() - transaction.started) * 1000)
        # Dispatch counts an attempted connection/send even if its outcome is unknown.
        phase_started = time.monotonic()
        transaction.dispatch('count', len(frames[0]))
        try:
            owned = transaction.connect(host, port)
            raw, closing = exchange(transaction, owned, frames[0])
            try:
                counted = _strict_json(raw, MAX_BODY_BYTES)
                count = counted.get('input_tokens')
                if counted.get('object') != 'response.input_tokens' or type(count) is not int or count < 1:
                    raise ValueError('invalid count')
            except ValueError:
                transaction.update(count_valid=False)
                raise AdmissionUnavailable('invalid count') from None
            transaction.update(input_tokens=count, count_valid=True)
            transaction.check()
            if count > transaction.budget.input_tokens or count + transaction.budget.completion_tokens > 4096:
                raise ContextBudgetExceeded('conversation input token budget')
            if closing:
                raise AdmissionUnavailable('count connection retired')
        finally:
            transaction.update(count_ms=(time.monotonic() - phase_started) * 1000,
                               count_terminal_at=time.monotonic())
        phase_started = time.monotonic()
        transaction.dispatch('inference', len(frames[1]))
        transaction.update(payload_bound=True)
        try:
            raw, _ = exchange(transaction, owned, frames[1])
            result = _decode_admitted(raw, count, transaction, decode_content, prepared.binding)
            transaction.check()
            transaction.update(full_terminal_at=time.monotonic())
        finally:
            transaction.update(inference_ms=(time.monotonic() - phase_started) * 1000,
                               inference_terminal_at=time.monotonic())
        transaction.update(stage='validated', reason='validated')
        return result
    except TimeoutError:
        transaction.retire('timeout')
        raise
    except ContextBudgetExceeded:
        transaction.update(reason='context_budget')
        raise
    except ProposalError:
        transaction.update(reason='schema')
        raise
    except (OSError, ValueError) as error:
        if transaction.slot_owner is not None:
            transaction.retire('unavailable')
        else:
            transaction.update(reason='unavailable')
        raise AdmissionUnavailable('admission unavailable') from error
    finally:
        transaction.close()
        transaction.update(worker_outstanding=False, worker_terminal_at=time.monotonic())



def _decode_admitted(raw, count, transaction, decode_content, binding):
    try:
        envelope = _strict_json(raw, MAX_BODY_BYTES)
    except ValueError:
        raise ProposalError('syntax_rejected', syntax=False) from None
    choices = envelope.get('choices')
    choice_shape = isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
    if choice_shape and choices[0].get('finish_reason') == 'length':
        raise ProposalError('shape_rejected', syntax=True, shape=False)
    usage = envelope.get('usage')
    matching = (isinstance(usage, dict) and type(usage.get('prompt_tokens')) is int
                and usage['prompt_tokens'] == count)
    transaction.update(usage_count_match=matching)
    if (not matching or type(usage.get('completion_tokens')) is not int
            or not 0 <= usage['completion_tokens'] <= transaction.budget.completion_tokens):
        raise AdmissionUnavailable('admission disagreement')
    if not choice_shape:
        raise ProposalError('shape_rejected', syntax=True, shape=False)
    if choices[0].get('finish_reason') != 'stop':
        raise AdmissionUnavailable('incomplete admission')
    message = choices[0].get('message')
    if not isinstance(message, dict) or not isinstance(message.get('content'), str):
        raise ProposalError('shape_rejected', syntax=True, shape=False)
    return decode_content(message['content'], binding)


def _consume(future):
    if not future.cancelled(): future.exception()


def notify_terminal(request, observe):
    receipt = request.snapshot()
    notification = asyncio.create_task(asyncio.to_thread(observe, receipt))
    notification.add_done_callback(_consume)


async def _observe_with_deadline(request, observe):
    notification = asyncio.create_task(asyncio.to_thread(observe, request.snapshot()))
    try:
        done, _ = await asyncio.wait((notification,), timeout=request.check())
        if not done:
            raise TimeoutError('conversation observer deadline')
        notification.result()
        request.check()
    finally:
        if not notification.done(): notification.add_done_callback(_consume)


async def run_admitted_chat(request, *, host, port, token_file, prepare, decode_content, observe,
                            slot_owner=None, role=None):
    # Preparation/authentication/parser work share this one absolute deadline.
    worker = None
    try:
        if slot_owner is not None:
            slot_owner.matches(host, port, token_file)
            await slot_owner.acquire(request, role)
        worker = asyncio.create_task(asyncio.to_thread(_chat_transaction, request, host, port, token_file, prepare, decode_content))
        done, _ = await asyncio.wait((worker,), timeout=request.check())
        if not done:
            raise TimeoutError('conversation deadline')
        result = worker.result()
        if slot_owner is not None: await slot_owner.completed(request)
        await _observe_with_deadline(request, observe)
        return result
    except asyncio.CancelledError:
        request.retire('cancelled')
        notify_terminal(request, observe)
        raise
    except TimeoutError:
        request.retire('timeout')
        notify_terminal(request, observe)
        raise
    except Exception:
        # Error-path observers are also bounded by the same remaining time.
        if request.cancelled.is_set():
            notify_terminal(request, observe)
            raise
        try: await _observe_with_deadline(request, observe)
        except TimeoutError:
            request.retire('timeout')
            notify_terminal(request, observe)
            raise
        raise
    finally:
        if worker is None:
            request.update(worker_outstanding=False, worker_terminal_at=time.monotonic())
        if slot_owner is not None: slot_owner.finish(request)
        if worker is not None and not worker.done():
            # Do not cancel the wrapper and pretend its thread was stopped.
            def cleanup(future):
                _consume(future)
                notify_terminal(request, observe)
            worker.add_done_callback(cleanup)
        elif worker is not None:
            _consume(worker)
