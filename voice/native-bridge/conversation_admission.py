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
        self.receipt = AdmissionSnapshot(request_id=uuid.uuid4().hex,
            input_limit=budget.input_tokens, completion_limit=budget.completion_tokens)

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
            self.receipt = replace(self.receipt, connection_closed=True)
        if owned is not None:
            try: owned.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            owned.close()

    def retire(self, reason):
        with self.lock:
            if not self.sealed:
                self.receipt = replace(self.receipt, reason=reason)
            self.sealed = True
            self.cancelled.set()
        self.close()

    def bind(self, payload, catalog):
        self.check()
        self.payload = payload  # bytes, frozen before either request is prepared
        self.update(payload_sha256=hashlib.sha256(payload).hexdigest(),
                    catalog_sha256=hashlib.sha256(catalog).hexdigest())

    def dispatch(self, phase, wire_bytes):
        # Only a small state transition is locked. Socket I/O never holds it.
        with self.lock:
            self.check()
            if self.sealed or getattr(self.receipt, phase + '_attempts'):
                raise AdmissionUnavailable('retired dispatch')
            if phase == 'inference' and (self.receipt.count_valid is not True or
                                        self.receipt.input_tokens > self.budget.input_tokens):
                raise AdmissionUnavailable('count gate')
            self.receipt = replace(self.receipt, stage=phase,
                **{phase + '_attempts': 1}, total_attempts=self.receipt.total_attempts + 1,
                transaction_bytes=self.receipt.transaction_bytes + wire_bytes)

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


def prepare_frames(host, port, payload, token_file):
    """These exact bytes are sent; there are no implicit client headers."""
    authority = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
    headers = [('Host', authority), ('Content-Type', 'application/json'),
               ('Accept', 'application/json'), ('Content-Length', str(len(payload))),
               ('Connection', 'keep-alive')]
    if token_file:
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
    frames = tuple(f'POST {path} HTTP/1.1\r\n'.encode('ascii') + header_bytes + b'\r\n' + payload
                   for path in (COUNT_PATH, INFERENCE_PATH))
    if len(payload) > MAX_REQUEST_BYTES or any(len(frame) > MAX_REQUEST_BYTES for frame in frames):
        raise ContextBudgetExceeded('conversation request framing too large')
    return frames


def exchange(request, owned, frame):
    """Exactly one attempted HTTP exchange; never reconnect or retry."""
    owned.settimeout(request.check())
    owned.sendall(frame)
    response = _CompleteHTTPResponse(_ResponseSocket(owned, request), method='POST')
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




def _chat_transaction(transaction, host, port, token_file, prepare, decode_content):
    try:
        transaction.check()
        prepared = prepare()
        payload, catalog = prepared.payload, prepared.catalog
        if len(payload) > MAX_REQUEST_BYTES:
            raise ContextBudgetExceeded('conversation request body too large')
        maximum = _strict_json(payload, MAX_REQUEST_BYTES).get('max_tokens')
        if type(maximum) is not int or maximum != transaction.budget.completion_tokens:
            raise AdmissionUnavailable('completion budget mismatch')
        transaction.bind(payload, catalog)
        frames = prepare_frames(host, port, payload, token_file)
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
            transaction.update(count_ms=(time.monotonic() - phase_started) * 1000)
        phase_started = time.monotonic()
        transaction.dispatch('inference', len(frames[1]))
        transaction.update(payload_bound=True)
        try:
            raw, _ = exchange(transaction, owned, frames[1])
            result = _decode_admitted(raw, count, transaction, decode_content, prepared.binding)
            transaction.check()
        finally:
            transaction.update(inference_ms=(time.monotonic() - phase_started) * 1000)
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
        transaction.update(reason='unavailable')
        raise AdmissionUnavailable('admission unavailable') from error
    finally:
        transaction.close()
        transaction.update(worker_outstanding=False)



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


async def run_admitted_chat(request, *, host, port, token_file, prepare, decode_content, observe):
    # Preparation/authentication/parser work share this one absolute deadline.
    worker = asyncio.create_task(asyncio.to_thread(_chat_transaction, request, host, port, token_file, prepare, decode_content))
    try:
        done, _ = await asyncio.wait((worker,), timeout=request.check())
        if not done:
            raise TimeoutError('conversation deadline')
        result = worker.result()
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
        try: await _observe_with_deadline(request, observe)
        except TimeoutError:
            request.retire('timeout')
            notify_terminal(request, observe)
            raise
        raise
    finally:
        if not worker.done():
            # Do not cancel the wrapper and pretend its thread was stopped.
            def cleanup(future):
                _consume(future)
                notify_terminal(request, observe)
            worker.add_done_callback(cleanup)
