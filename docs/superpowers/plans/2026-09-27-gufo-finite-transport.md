# GUFO finite HTTP transport and evidence implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one offline-testable, ledger-bound finite HTTP operation transport with bounded evidence, parser-stage cancellation, and nonblocking milestones for a later phase controller.

**Architecture:** Keep `smoke_http._exchange` and its default callers unchanged. Parameterize its reusable `_Reader` and `_body_chunks` only; a new `finite_transport` module owns socket admission, exact request bytes, streaming observation, evidence, assessment, and durable outcome. The existing `Ledger` remains the sole reservation authority. This task does not schedule phases, launch a server, or establish qualification.

**Tech Stack:** Python 3.12 standard library, `unittest`, synthetic sockets, fake monotonic clock, temporary evidence. Pinned `Workload`, `Ledger`, `finite_responses`, and pure `finite_assessment` interfaces.

## Global Constraints

- Checkout for the later implementation: `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`. This committed plan governs the scoped implementation.
- Preserve the pinned 132273-byte workload, SHA256 `30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38`, exact 66/6 POST bytes and order, at most 240 readiness GETs and one models GET per lifecycle. Never retry or substitute a consumed slot.
- Preserve 49 GiB prelaunch Windows physical availability, 24 GiB runtime physical availability, 12 GiB commit headroom, and the reviewed 68/4/20 GiB GPU/additional-host/shared envelope. This task measures none of them and confers no launch authority.
- No model, GPU, native helper, metadata reader, collector, recovery, guardian, listener, real socket, configuration edit, D: access, download, publication, or installed acceptance change. Full memory review, phase schedule, wave proof, store/guardian integration and live qualification remain later gates.
- Complete operation, including send, receive, parse, evidence flush and outcome persistence: `min(start+60s, resume+lifetime)`; GET also `resume+480s`. At most three owned sockets including GETs, with no second client.
- Per POST: 4096-byte request header, 16384-byte request body except pinned `reject_body_16385`, 16384-byte response header, 8388608 received wire bytes, 7340032 dechunked bytes, 1048576 exact extracted-answer file bytes, 65536 summary bytes. Per GET: 65536 wire, 49152 body, 4096 summary. Received count/hash cover headers, chunk framing, buffered bytes, and errors.
- Existing ledger budgets already reserve 616.328125 MiB / 72.34375 MiB for first/second lifecycle (1 MiB base plus wire capture, answer, summary and 4 KiB reservation per operation). No additional per-operation metadata file; one sanitized capture, one answer for a completed positive POST, and existing reservation/outcome files only. Evidence ceilings remain 768/128 MiB and wire ceilings 543.0625/63.0625 MiB.
- Parser body parts may be bounded in memory for a single operation. Do not retain a second raw-wire, base64, or UTF-8 dump. No truncated, malformed, over-budget, late, or ambiguous operation can pass.

## Implementation notes

This plan copies the frozen private draft SHA256
`B7B6B7B9D30E0F5D3190ABCECC6FA4E13CEA71B6D378A086BF6892533C5EFF2E`,
with parent corrections to integrated positive fixtures and explicit fault tests.
The snippets are starting implementation, not an instruction to retain a defect.
Correct scoped implementation/test defects with focused RED/GREEN evidence while
preserving the normative limits and contracts. Complete chat and tool positives
must exercise the actual response and assessment helpers, not mocked approval.

## File map and interfaces

| Path | Responsibility |
| --- | --- |
| `scripts/gufo_control/smoke_http.py` | Optional finite limits and on-receive hook in `_Reader`, optional body limit in `_body_chunks`; defaults and `_exchange` stay byte-for-byte behaviorally compatible. |
| `scripts/gufo_control/finite_ledger.py` | One run-level, <=4096-byte transport-failed latch charged to the existing 1 MiB base reserve; refuse further reservations and handoff on that latch. No per-operation evidence in its root. |
| `scripts/gufo_control/finite_transport.py` | Sole finite socket semaphore, exact request construction, streaming observation, sibling sanitized capture, assessment, and compact durable result. |
| `tests/gufo/test_finite_transport.py` | Synthetic socket/fake-clock/temp-directory tests only. |

`FiniteTransport(ledger: Ledger, workload: Workload, api_key: str, *, socket_factory: Callable[[str,int,float], socket], clock: Callable[[],float], cancel: threading.Event, milestone: Callable[[Milestone],None])`. Its `post(attempt, *, disconnect=None, previous=None, semantic_review=None) -> OperationResult` and `get(kind, ordinal) -> OperationResult` run one consumed operation synchronously; a later single authenticated controller may put up to three calls in workers. Capture and answer files live in deterministic sibling `ledger.root.with_name(ledger.root.name + '-finite-evidence')`, never inside the ledger root; the ledger's existing reservation charges their maximum sizes. `Milestone(slot:str, event:Literal['sent','first_content','terminal'], at:float)` is immutable. The caller-supplied `milestone` **must** be a nonblocking queue insertion such as `queue.SimpleQueue.put_nowait`; it may not wait, read a socket, or pause drain. The transport emits each milestone once and records matching times in the outcome. A later controller owns rendezvous, phase order, prior assessment/review provenance, and shutdown; the transport itself never claims queue occupancy or server-side cancellation.

`OperationResult` contains `slot`, `success`, `classification`, `status`, `wire_bytes`, `wire_sha256`, `capture_sha256`, `answer_sha256` (the exact stored answer artifact) or null, `visible_text_sha256` (exact extracted UTF-8 text for prose review) or null, `sent_at`, `headers_at`, `first_content_at`, `terminal_at`, `close_started_at`, `close_completed_at`, `buffered_at_close`, `error`, compact `assessment` or null, and a bounded `response` object for a GET. `response` is returned only to the immediate caller and omitted from the durable summary. For a prose case, structural success and pending manual review are distinct. For a cancellation case, `success` means the selected local parser trigger and close were observed, never that server cancellation was proved.

The assessment plan's sole consumed interfaces are `assess_positive(workload,index,attempt,parsed,*,semantic_review=None,previous=None)->dict` and `assess_rejection(workload,index,attempt,status,content_type,body)->dict`. `finite_responses.parse_positive_response(post,body,parts,submitted)->dict` decodes complete positive bodies. The caller supplies authenticated complete protocol evidence, previous assessments and manual review provenance. The transport preserves native usage/timings as supplied; it invents no token counts.

## Task 1: Implement and verify finite HTTP operation transport

**Files:** Modify `scripts/gufo_control/smoke_http.py` and `scripts/gufo_control/finite_ledger.py`; create `scripts/gufo_control/finite_transport.py` and `tests/gufo/test_finite_transport.py`. One review and one commit cover the independently testable transport/evidence task.

**Interfaces:** `_Reader(sock,deadline,cancel,*,wire_limit=MAX_RESPONSE+16384,on_wire=None,retain_raw=True,clock=time.monotonic,check=None)` and `_body_chunks(reader,headers,*,body_limit=MAX_RESPONSE)`. `on_wire(data:bytes,arrived:float)->None` sees each received chunk exactly once before buffering; `check(deadline,cancel)->None` permits the fake clock. No new argument is passed by existing clients.

- [ ] **Step 1: Add the RED reader tests.**

```python
import threading
import unittest
from gufo_control import smoke_http

class ScriptedSocket:
    def __init__(self, receives=(), *, on_send=None):
        self.receives = list(receives)
        self.on_send = on_send
        self.sent, self.closed = [], False
    def settimeout(self, timeout):
        self.timeout = timeout
    def sendall(self, data):
        self.sent.append(data)
        if self.on_send:
            self.on_send(data)
    def recv(self, maximum):
        if not self.receives:
            return b''
        data = self.receives[0]
        head, tail = data[:maximum], data[maximum:]
        if tail:
            self.receives[0] = tail
        else:
            self.receives.pop(0)
        return head
    def close(self):
        self.closed = True

class ReaderTests(unittest.TestCase):
    def test_reader_observes_split_bytes_without_raw_copy(self):
        now = [1.0]
        seen = []
        sock = ScriptedSocket([b'ab', b'cd', b''])
        reader = smoke_http._Reader(sock, 60.0, threading.Event(), wire_limit=3,
                                    on_wire=lambda data, at: seen.append((data, at)),
                                    retain_raw=False, clock=lambda: now[0],
                                    check=lambda deadline, cancel: None)
        self.assertEqual(reader.exact(2), b'ab')
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            reader.exact(2)
        self.assertEqual(seen, [(b'ab', 1.0), (b'cd', 1.0)])
        self.assertEqual(reader.raw, bytearray())

    def test_body_limit_is_optional_and_finite_override_works(self):
        reader = smoke_http._Reader(ScriptedSocket([b'4\r\nABCD\r\n0\r\n\r\n']),
                                    60.0, threading.Event(), check=lambda *_: None)
        self.assertEqual(b''.join(p for p, _ in smoke_http._body_chunks(
            reader, {'transfer-encoding': 'chunked'}, body_limit=4)), b'ABCD')
```

Run the synthetic-only command in Step 9; expect missing optional keyword failures.

- [ ] **Step 2: Make the minimal reader edit.** Change only the constructor, `_recv`, and the two `MAX_RESPONSE` checks inside `_body_chunks` as follows; leave `_exchange` unchanged.

```python
class _Reader:
    def __init__(self, sock, deadline, cancel, *, wire_limit=MAX_RESPONSE + 16_384,
                 on_wire=None, retain_raw=True, clock=time.monotonic, check=None):
        self.sock, self.deadline, self.cancel = sock, deadline, cancel
        self.wire_limit, self.on_wire, self.retain_raw = wire_limit, on_wire, retain_raw
        self.clock, self.check = clock, _check if check is None else check
        self.buffer, self.arrivals, self.raw, self.wire_count = bytearray(), [], bytearray(), 0

    def _recv(self):
        while True:
            self.check(self.deadline, self.cancel)
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            if data:
                arrived = self.clock()
                self.wire_count += len(data)
                if self.on_wire is not None:
                    self.on_wire(data, arrived)  # count/hash all bytes, including an over-limit read
                if self.wire_count > self.wire_limit:
                    raise SmokeError('response_wire_limit')
                if self.retain_raw:
                    self.raw.extend(data)
                self.buffer.extend(data)
                self.arrivals.append((len(data), arrived))
            return data
```

In `_body_chunks`, use `def _body_chunks(reader, headers, *, body_limit=MAX_RESPONSE):` and replace both `> MAX_RESPONSE` size checks with `> body_limit`. The transport also checks cumulative yielded bytes, so chunked framing cannot evade the bound. Run `ReaderTests` and `test_smoke_http.ReusableHelpersTests` only; `SmokeHttpTests` opens a real listener and is excluded.

- [ ] **Step 3: Review the reuse seam:** verify ordinary `_Reader(...)`, `_body_chunks(...)`, `_exchange`, and chat parser signatures and default behavior remain unchanged. Continue with the same task.

### Transport and evidence implementation

**Files:** Create `scripts/gufo_control/finite_transport.py`; modify `scripts/gufo_control/finite_ledger.py` only for the single run-level deadline latch; test in `tests/gufo/test_finite_transport.py`. Its per-operation evidence allowlist remains intact.

**Interfaces:** Consume the Task 1 reader, existing `Ledger.reserve/complete`, pinned `Workload.post`, `finite_responses.parse_positive_response`, and pure assessment signatures above. Produce `FiniteTransport.post/get`, `Milestone`, `OperationResult`. The module must never create a connection before `Ledger.reserve` durably returns.

- [ ] **Step 4: Write the transport RED tests.** Append the complete `FiniteTransportTests` code printed in Step 8 to the test file now, after `ReaderTests`; all shared imports and `ScriptedSocket` already exist. Run the synthetic-only command in Step 9; expect the new tests to fail because `finite_transport.py` does not yet exist. Then implement Steps 5–7 and rerun the same tests.

The reservation allowance already covers the sibling capture and answer and the ledger outcome. The sibling is private run evidence, not another metadata ledger. The later store must bind its deterministic path to run identity and audit allowed names, sizes and hashes. Disk-full or evidence write failure consumes the reservation and fails closed. The one `transport-failed.json` latch, when needed, is charged to the ledger's already reserved 1 MiB base. No per-operation metadata file is added.

- [ ] **Step 5: Implement bounded wire sink and event observer.** Use the complete starting code below in `finite_transport.py`; keep these classes private. `Capture.feed` hashes every received byte before same-length redaction and writes only a sanitized capture. Its pending tail protects secrets split across any reads. `SseObserver.feed` processes only complete frames and uses the frozen event definitions; it counts qualifying content events, never tokens. The header trigger is handled before constructing this observer.

```python
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import re
import socket
import threading
import time
from typing import Callable, Literal

from . import finite_assessment, finite_responses, smoke_http
from .build_identity import checked_path
from .finite_ledger import Ledger
from .finite_workload import Workload

@dataclass(frozen=True)
class Milestone:
    slot: str
    event: Literal['sent', 'first_content', 'terminal']
    at: float

@dataclass(frozen=True)
class OperationResult:
    slot: str
    success: bool
    classification: str
    status: int | None
    wire_bytes: int
    wire_sha256: str
    capture_sha256: str
    answer_sha256: str | None
    visible_text_sha256: str | None
    sent_at: float | None
    headers_at: float | None
    first_content_at: float | None
    terminal_at: float | None
    close_started_at: float | None
    close_completed_at: float | None
    buffered_at_close: int | None
    error: str | None
    assessment: dict | None
    response: dict | None  # bounded GET object for immediate caller only

class Capture:
    def __init__(self, path: Path, secret: bytes, limit: int):
        if not secret or len(secret) > 4096:
            raise ValueError('finite_secret')
        self.file = path.open('xb')
        self.secret, self.mask, self.limit = secret, b'*' * len(secret), limit
        self.pending = b''
        self.count, self.raw_hash, self.capture_hash = 0, sha256(), sha256()

    def _write(self, data):
        if data:
            self.file.write(data)
            self.capture_hash.update(data)

    def feed(self, data, arrived):
        capacity = max(0, self.limit - self.count)
        self.count += len(data)
        self.raw_hash.update(data)
        combined = (self.pending + data[:capacity]).replace(self.secret, self.mask)
        keep = min(len(combined), len(self.secret) - 1)
        self._write(combined[:len(combined)-keep])
        self.pending = combined[len(combined)-keep:]
        if self.count > self.limit:
            for length in range(len(self.secret) - 1, 0, -1):
                if self.pending.endswith(self.secret[:length]):
                    self.pending = self.pending[:-length] + b'*' * length
                    break
            raise smoke_http.SmokeError('response_wire_limit')

    def close(self):
        try:
            self._write(self.pending)
            self.pending = b''
            self.file.flush()
            os.fsync(self.file.fileno())
        finally:
            self.file.close()

class SseObserver:
    def __init__(self, route, trigger, emit):
        self.route, self.trigger, self.emit = route, trigger, emit
        self.pending, self.count = b'', 0
        self.generation_terminal, self.terminal = False, False
        self.output_bytes, self.sequence = 0, 0
        self.first_at = self.terminal_at = None

    def feed(self, data, arrived):
        self.pending += data
        if len(self.pending) > 7340032:
            raise smoke_http.SmokeError('sse_event_limit')
        while True:
            match = re.search(rb'\r?\n\r?\n', self.pending)
            if match is None:
                return False
            frame = self.pending[:match.start()]
            self.pending = self.pending[match.end():]
            if self.terminal:
                raise smoke_http.SmokeError('sse_after_terminal')
            lines = frame.decode('utf-8', 'strict').splitlines()
            if any(line and not line.startswith(('data:', 'event:', ':')) for line in lines):
                raise smoke_http.SmokeError('sse_field')
            data_lines = [line[5:].lstrip(' ') for line in lines if line.startswith('data:')]
            if not data_lines:
                if any(line.startswith('event:') for line in lines):
                    raise smoke_http.SmokeError('sse_field')
                continue
            payload = '\n'.join(data_lines)
            if payload == '[DONE]':
                if self.route != '/v1/chat/completions' or not self.generation_terminal:
                    raise smoke_http.SmokeError('sse_done_route')
                self.terminal = True
            else:
                value = smoke_http._strict_json(payload)
                if type(value) is not dict:
                    raise smoke_http.SmokeError('malformed_sse_json')
                if self.route == '/v1/chat/completions':
                    if any(line.startswith('event:') for line in lines):
                        raise smoke_http.SmokeError('sse_event_route')
                    choices = value.get('choices')
                    if type(choices) is not list or len(choices) > 1:
                        raise smoke_http.SmokeError('malformed_sse_choices')
                    if self.generation_terminal and choices:
                        raise smoke_http.SmokeError('sse_content_after_finish')
                    if not self.generation_terminal and not choices and 'usage' in value:
                        raise smoke_http.SmokeError('sse_usage_before_finish')
                    choice = choices[0] if len(choices) == 1 else {}
                    if type(choice) is not dict or (choice.get('index', 0) != 0):
                        raise smoke_http.SmokeError('malformed_sse_choices')
                    delta = choice.get('delta', {})
                    if type(delta) is not dict:
                        raise smoke_http.SmokeError('malformed_sse_delta')
                    if ('reasoning_content' in delta and type(delta['reasoning_content']) is not str
                            or 'tool_calls' in delta and type(delta['tool_calls']) is not list):
                        raise smoke_http.SmokeError('malformed_sse_delta')
                    content = delta.get('content')
                    if content is not None and type(content) is not str:
                        raise smoke_http.SmokeError('malformed_sse_delta')
                    qualifies = type(content) is str and bool(content)
                    if type(choice) is dict and choice.get('finish_reason') is not None:
                        if type(choice['finish_reason']) is not str:
                            raise smoke_http.SmokeError('malformed_finish_reason')
                        self.generation_terminal = True
                elif self.route == '/v1/responses':
                    kind = value.get('type')
                    event_lines = [line[6:].lstrip(' ') for line in lines if line.startswith('event:')]
                    allowed = {'response.created', 'response.in_progress',
                               'response.output_item.added', 'response.content_part.added',
                               'response.output_text.delta', 'response.output_text.done',
                               'response.content_part.done', 'response.output_item.done',
                               'response.completed', 'response.failed', 'response.incomplete'}
                    if (len(event_lines) != 1 or event_lines[0] != kind or kind not in allowed or
                            type(value.get('sequence_number')) is not int or
                            value['sequence_number'] != self.sequence):
                        raise smoke_http.SmokeError('sse_sequence_or_type')
                    self.sequence += 1
                    if kind == 'response.output_text.delta' and type(value.get('delta')) is not str:
                        raise smoke_http.SmokeError('sse_delta')
                    qualifies = (kind == 'response.output_text.delta' and
                                 type(value.get('delta')) is str and bool(value['delta']))
                    if kind in ('response.completed', 'response.failed', 'response.incomplete'):
                        self.generation_terminal = True
                        self.terminal = True
                else:
                    raise smoke_http.SmokeError('finite_route')
                if qualifies:
                    self.count += 1
                    if self.first_at is None:
                        self.first_at = arrived
                        self.emit('first_content', arrived)
                if self.route == '/v1/chat/completions':
                    fragments = [text for text in (content, delta.get('reasoning_content'))
                                 if type(text) is str]
                    for tool in delta.get('tool_calls', []):
                        if type(tool) is not dict:
                            raise smoke_http.SmokeError('malformed_tool_delta')
                        function = tool.get('function', {})
                        if type(function) is not dict:
                            raise smoke_http.SmokeError('malformed_tool_delta')
                        for text in (tool.get('id'), function.get('name'), function.get('arguments')):
                            if text is not None:
                                if type(text) is not str:
                                    raise smoke_http.SmokeError('malformed_tool_delta')
                                fragments.append(text)
                else:
                    fragments = [value['delta']] if kind == 'response.output_text.delta' else []
                self.output_bytes += sum(len(text.encode('utf-8')) for text in fragments)
                if self.output_bytes > 1048576:
                    raise smoke_http.SmokeError('decoded_output_limit')
            if self.generation_terminal and self.terminal_at is None:
                self.terminal_at = arrived
                self.emit('terminal', arrived)
            if self.generation_terminal and self.trigger is not None:
                raise smoke_http.SmokeError('cancel_trigger_missed')
            if self.trigger is not None and self.count == self.trigger:
                return True
```

Do not use `SseObserver` as the final response validator: `finite_responses` remains responsible for complete SSE sequence, usage, timings, exact route and output consistency. Its bounded `parts` list is created once while receiving and released after assessment. A malformed frame, terminal before trigger, or invalid UTF-8 fails; do not convert it to a successful cancellation.

- [ ] **Step 6: Add the finite operation implementation.** Append this starting code to `finite_transport.py`. The constructor is the only owner of the three-permit semaphore. `socket_factory` defaults to a local loopback connection wrapper only for later authorized live integration; offline tests inject synthetic sockets. The guardian's `secrets.token_urlsafe(32)` key is 43 ASCII URL-safe characters; same-length masking preserves capture size across split reads. The key is never included in an outcome, exception text, or capture. `post` passes the exact `PreparedPost.body` object to both reservation and request construction. No POST is generated inside this module.

```python
def _loopback(host, port, timeout):
    return socket.create_connection((host, port), timeout=timeout)

class FiniteTransport:
    def __init__(self, ledger: Ledger, workload: Workload, api_key: str, *,
                 socket_factory: Callable = _loopback, clock=time.monotonic,
                 cancel=None, milestone=None, host='127.0.0.1', port=8836):
        if type(ledger) is not Ledger or type(workload) is not Workload or ledger.workload != workload:
            raise ValueError('finite_identity')
        if type(api_key) is not str or re.fullmatch(r'[A-Za-z0-9_-]{43}', api_key) is None:
            raise ValueError('finite_key')
        if host != '127.0.0.1' or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('finite_endpoint')
        self.ledger, self.workload, self.key = ledger, workload, api_key
        self.socket_factory, self.clock = socket_factory, clock
        self.cancel = cancel if cancel is not None else threading.Event()
        self.milestone = milestone if milestone is not None else queue.SimpleQueue().put_nowait
        self.host, self.port = host, port
        self.sockets = threading.BoundedSemaphore(3)
        self.evidence_root = checked_path(
            ledger.root.with_name(ledger.root.name + '-finite-evidence'),
            directory=True, exists=False)

    def _evidence_dir(self):
        root = checked_path(self.evidence_root, directory=True, exists=False)
        if not root.exists():
            root.mkdir()
        checked_path(root, directory=True)
        maximum = sum(self.workload.lifecycle(self.ledger.index)[key] for key in
                      ('maximum_post_attempts', 'maximum_ready_polls', 'maximum_model_queries'))
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries, 1):
                if count > 2 * maximum:
                    raise ValueError('finite_evidence_entries')
                path = Path(entry.path)
                match = re.fullmatch(r'(post|ready|models)-([0-9]{3})\.(wire\.bin|answer\.json)', entry.name)
                if match is None or (match[1] != 'post' and match[3] == 'answer.json'):
                    raise ValueError('finite_evidence_entry')
                checked_path(path)
                limit = (self.workload.limits()['generated_text_or_tool_argument_utf8_bytes']
                         if match[3] == 'answer.json' else
                         self.workload.limits()['post_response_wire_bytes' if match[1] == 'post'
                                                else 'get_response_wire_bytes'])
                if path.stat().st_size > limit:
                    raise ValueError('finite_evidence_size')
        return root

    def _check(self, deadline, cancel):
        if cancel.is_set():
            raise smoke_http.SmokeError('cancelled')
        if self.clock() >= deadline:
            raise smoke_http.SmokeError('deadline_exceeded')

    def _request(self, method, path, body):
        lines = [f'{method} {path} HTTP/1.1', f'Host: {self.host}:{self.port}',
                 f'Authorization: Bearer {self.key}', 'Connection: close',
                 'Accept: application/json, text/event-stream']
        if method == 'POST':
            lines += ['Content-Type: application/json', f'Content-Length: {len(body)}']
        head = ('\r\n'.join(lines) + '\r\n\r\n').encode('ascii')
        if len(head) > 4096:
            raise ValueError('finite_request_header_limit')
        if len(body) > 16385:
            raise ValueError('finite_request_body_limit')
        return head + body

    def post(self, attempt, *, disconnect=None, previous=None, semantic_review=None):
        post = self.workload.post(self.ledger.index, attempt)
        if type(disconnect) is bool or disconnect not in (None, 'headers', 1, 8):
            raise ValueError('finite_disconnect')
        trigger = json.loads(post.step_json).get('disconnect_trigger')
        required = {None: None, 'after_successful_headers_before_content': 'headers',
                    'after_first_nonempty_content_event': 1,
                    'after_eight_nonempty_content_events': 8}.get(trigger, object())
        if disconnect != required:
            raise ValueError('finite_disconnect_mismatch')
        return self._run('post', attempt, post.route, post.body, post=post,
                         disconnect=disconnect, previous=previous,
                         semantic_review=semantic_review)

    def get(self, kind, ordinal):
        if kind not in ('ready', 'models'):
            raise ValueError('finite_get_kind')
        path = '/ready' if kind == 'ready' else '/v1/models'
        return self._run(kind, ordinal, path, b'')

    def _run(self, kind, ordinal, path, body, *, post=None, disconnect=None,
             previous=None, semantic_review=None):
        method = 'POST' if kind == 'post' else 'GET'
        if len(body) > 16384 and not (post is not None and
            post.request_id == 'reject_body_16385' and len(body) == 16385):
            raise ValueError('finite_request_body_limit')
        wire = self._request(method, path, body)
        reservation = self.ledger.reserve(kind, ordinal, body=body)
        slot, deadline = reservation['slot'], reservation['deadline']
        capture = None
        status = None
        sent_at = headers_at = first_at = terminal_at = None
        close_started = close_completed = buffered = None
        answer_hash = None
        visible_hash = None
        assessment = None
        response_value = None
        classification, error, success = 'incomplete', None, False
        reader = sock = None
        response_size, parts, headers = 0, [], {}
        permit = False
        emitted = set()

        def emit(event, at):
            if event not in emitted:
                emitted.add(event)
                self.milestone(Milestone(slot, event, at))

        try:
            evidence_root = self._evidence_dir()
            capture = Capture(evidence_root / f'{slot}.wire.bin',
                              self.key.encode('ascii'), reservation['wire_allowance'])
            while not self.sockets.acquire(timeout=0.05):
                self._check(deadline, self.cancel)
            permit = True
            self._check(deadline, self.cancel)
            sock = self.socket_factory(self.host, self.port, min(0.25, deadline-self.clock()))
            sock.settimeout(min(0.25, max(0.001, deadline-self.clock())))
            self._check(deadline, self.cancel)
            sock.sendall(wire)
            sent_at = self.clock()
            emit('sent', sent_at)
            self._check(deadline, self.cancel)
            reader = smoke_http._Reader(sock, deadline, self.cancel,
                wire_limit=reservation['wire_allowance'], on_wire=capture.feed,
                retain_raw=False, clock=self.clock, check=self._check)
            raw_head = reader.until(b'\r\n\r\n', self.workload.limits()['response_header_bytes'])
            headers_at = self.clock()
            lines = raw_head[:-4].decode('iso-8859-1').split('\r\n')
            fields = lines[0].split(' ', 2)
            if len(fields) < 2 or not fields[0].startswith('HTTP/1.') or not fields[1].isdigit():
                raise smoke_http.SmokeError('malformed_status')
            status = int(fields[1])
            for line in lines[1:]:
                if ':' not in line:
                    raise smoke_http.SmokeError('malformed_header')
                name, value = line.split(':', 1)
                name = name.strip().lower()
                if name in headers:
                    raise smoke_http.SmokeError('duplicate_header')
                headers[name] = value.strip()
            transfer = headers.get('transfer-encoding')
            if ((transfer is not None and transfer.lower() != 'chunked') or
                    (transfer is not None and 'content-length' in headers)):
                raise smoke_http.SmokeError('ambiguous_response_framing')
            content_type = headers.get('content-type', '').split(';', 1)[0].lower()
            if disconnect is not None and (status != 200 or content_type != 'text/event-stream'):
                raise smoke_http.SmokeError('cancel_headers')
            if disconnect == 'headers':
                buffered = len(reader.buffer)
                close_started = self.clock()
                sock.close()
                close_completed = self.clock()
                sock = None
                classification, success = 'local_headers_disconnect', True
            else:
                observer = (SseObserver(path, disconnect if type(disconnect) is int else None, emit)
                            if content_type == 'text/event-stream' else None)
                limit = (self.workload.limits()['post_response_body_bytes'] if post else
                         self.workload.limits()['get_response_body_bytes'])
                for part, arrived in smoke_http._body_chunks(reader, headers, body_limit=limit):
                    self._check(deadline, self.cancel)
                    if response_size + len(part) > limit:
                        raise smoke_http.SmokeError('response_body_limit')
                    if len(parts) >= finite_responses.PART_LIMIT:
                        raise smoke_http.SmokeError('body_parts_limit')
                    response_size += len(part)
                    parts.append((part, arrived))
                    if observer and observer.feed(part, arrived):
                        buffered = len(reader.buffer) + len(observer.pending)
                        close_started = self.clock()
                        sock.close()
                        close_completed = self.clock()
                        sock = None
                        first_at, terminal_at = observer.first_at, observer.terminal_at
                        classification, success = 'local_event_disconnect', True
                        break
                if sock is not None:
                    self._check(deadline, self.cancel)
                    sock.close()
                    sock = None
                    if observer:
                        first_at, terminal_at = observer.first_at, observer.terminal_at
                    if disconnect is not None:
                        raise smoke_http.SmokeError('cancel_trigger_missed')
                    response_body = b''.join(part for part, _ in parts)
                    if post and status == 200:
                        if content_type not in ('application/json', 'text/event-stream'):
                            raise smoke_http.SmokeError('content_type')
                        parsed = finite_responses.parse_positive_response(
                            post, response_body, parts, sent_at)
                        visible_hash = sha256(parsed['visible_answer'].encode('utf-8')).hexdigest().upper()
                        assessment = finite_assessment.assess_positive(
                            self.workload, self.ledger.index, ordinal, parsed,
                            semantic_review=semantic_review, previous=previous)
                        answer = json.dumps({k: parsed[k] for k in
                            ('visible_answer', 'reasoning_content', 'tool_calls')},
                            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
                        if len(answer) > self.workload.limits()['generated_text_or_tool_argument_utf8_bytes']:
                            raise smoke_http.SmokeError('answer_limit')
                        if self.key.encode('ascii') in answer:
                            raise smoke_http.SmokeError('answer_contains_secret')
                        with (evidence_root / f'{slot}.answer.json').open('xb') as stream:
                            stream.write(answer)
                            stream.flush()
                            os.fsync(stream.fileno())
                        answer_hash = sha256(answer).hexdigest().upper()
                        success = bool(assessment['structural_success'])
                        classification = 'complete_positive' if success else 'invalid_positive'
                    elif post:
                        assessment = finite_assessment.assess_rejection(
                            self.workload, self.ledger.index, ordinal, status,
                            content_type, response_body)
                        success = bool(assessment.get('request_contract_pass', False))
                        classification = 'expected_rejection' if success else 'invalid_rejection'
                    else:
                        if content_type != 'application/json':
                            raise smoke_http.SmokeError('get_content_type')
                        value = smoke_http._json_object(response_body)
                        response_value = value
                        if kind == 'ready':
                            success = ((status == 503 and type(value.get('error')) is dict and
                                        value['error'].get('code') == 'not_ready') or
                                       (status == 200 and value.get('status') == 'ready' and
                                        value.get('model') == smoke_http.MODEL))
                        else:
                            models = value.get('data')
                            success = (status == 200 and type(models) is list and
                                       len(models) == 1 and type(models[0]) is dict and
                                       models[0].get('id') == smoke_http.MODEL)
                        classification = 'get_response' if success else 'invalid_get'
                    if observer is None and terminal_at is None:
                        terminal_at = self.clock()
                        emit('terminal', terminal_at)
        except (smoke_http.SmokeError, OSError, ValueError, UnicodeError) as exc:
            error = getattr(exc, 'code', None) or type(exc).__name__
            classification, success = 'transport_failure', False
        except BaseException as exc:
            error = type(exc).__name__
            classification, success = 'unexpected_failure', False
            raise
        finally:
            try:
                if sock is not None:
                    close_started = self.clock()
                    try:
                        sock.close()
                    except Exception:
                        classification, success, error = 'close_failure', False, 'socket_close'
                    finally:
                        close_completed = self.clock()
            finally:
                if permit:
                    self.sockets.release()
            try:
                if capture is not None:
                    capture.close()
            except Exception:
                classification, success, error = 'evidence_failure', False, 'capture_write'
            if self.clock() >= deadline:
                classification, success, error = 'deadline_failure', False, 'deadline_exceeded'
            result = OperationResult(slot, success, classification, status,
                0 if capture is None else capture.count,
                sha256(b'').hexdigest().upper() if capture is None else capture.raw_hash.hexdigest().upper(),
                sha256(b'').hexdigest().upper() if capture is None else capture.capture_hash.hexdigest().upper(),
                answer_hash, visible_hash, sent_at, headers_at, first_at, terminal_at,
                close_started, close_completed, buffered, error, assessment,
                response_value)
            durable = dict(result.__dict__)
            durable.pop('response')
            if assessment is not None:
                durable['assessment'] = {key: assessment.get(key) for key in
                    ('structural_success', 'answer_status', 'fully_validated',
                     'request_contract_pass', 'errors')}
            self.ledger.complete(slot, durable)
            if self.clock() >= deadline:
                self.ledger.fail_transport(slot, 'outcome_deadline', self.clock())
                raise smoke_http.SmokeError('outcome_deadline_exceeded')
        return result
```

The starting code enforces the pinned disconnect trigger, uses the assessment module's `request_contract_pass` rejection key, and validates GET shapes and model identity. Preserve these checks in implementation. A secret in an extracted answer fails the operation without storing altered text: sanitized answer bytes cannot support the original exact-answer or manual-review hash. Any unexpected exception remains a failed, consumed operation or an incomplete handoff; it cannot become a successful outcome.

- [ ] **Step 7: Add a durable late-commit latch and refusal.** `_exclusive` may cross the deadline during `fsync`. Keep `Ledger.complete`'s existing exclusive lock through a post-`fsync` clock check. If that check is late, create one `transport-failed.json` under `Ledger.root` before releasing the lock and raise `finite_outcome_deadline`. Charge its <=4096 bytes to `BASE_EVIDENCE_RESERVE` (not to any new per-slot allowance); `_scan` validates its exact run/slot/deadline binding and refuses every future `reserve`, `snapshot` handoff view, and `Ledger(...,create=False)` reopening. A later guardian must also refuse handoff unless the live worker returned an on-time `OperationResult`; process death between outcome flush and latch is an indeterminate run, never recovery permission.

```python
# finite_ledger.py: add a single run-level file to the existing scan's known names.
FAILURE_LATCH = 'transport-failed.json'
# In the scandir loop, before the reservation/outcome regex:
if entry.name == FAILURE_LATCH:
    row = _read(path, RECORD_LIMIT)
    if (type(row) is not dict or set(row) != {'schema', 'run_id', 'slot', 'deadline', 'observed_at', 'code'}
            or row['schema'] != 1 or row['run_id'] != self.header['run_id']
            or type(row['slot']) is not str or row['code'] != 'outcome_deadline'
            or not _time(row['deadline']) or not _time(row['observed_at'])):
        raise ValueError('finite_transport_latch_invalid')
    late_latch = row
    continue
# After reservation/outcome binding:
if late_latch is not None:
    target = reservations.get(late_latch['slot'])
    if (target is None or late_latch['deadline'] != target['deadline']
            or late_latch['observed_at'] < target['deadline']):
        raise ValueError('finite_transport_latch_invalid')
# `_scan` now returns `reservations, outcomes, late_latch`.
# In __init__ after _scan (before incomplete-handoff check), reserve, complete, snapshot:
reservations, outcomes, late_latch = self._scan()
if late_latch is not None:
    raise ValueError('finite_transport_failed')
# In complete(), keep the _locked() context around the existing _exclusive call:
_exclusive(self.root/f'{slot}.outcome.json', row, limit)
committed_at = self.clock()
if committed_at >= reservations[slot]['deadline']:
    _exclusive(self.root/FAILURE_LATCH,
               dict(schema=1, run_id=self.header['run_id'], slot=slot,
                    deadline=reservations[slot]['deadline'],
                    observed_at=committed_at, code='outcome_deadline'), RECORD_LIMIT)
    raise ValueError('finite_outcome_deadline')
return committed_at

# Add this Ledger method for a post-complete clock crossing in the caller:
def fail_transport(self, slot, code, observed_at):
    with self._locked():
        reservations, outcomes, late_latch = self._scan()
        if late_latch is not None:
            raise ValueError('finite_transport_failed')
        if (slot not in reservations or code != 'outcome_deadline' or
                not _time(observed_at) or observed_at < reservations[slot]['deadline']):
            raise ValueError('finite_transport_latch_invalid')
        _exclusive(self.root/FAILURE_LATCH,
                   dict(schema=1, run_id=self.header['run_id'], slot=slot,
                        deadline=reservations[slot]['deadline'],
                        observed_at=observed_at, code=code), RECORD_LIMIT)
```

Initialize `late_latch = None` before scanning; reject a second latch through the fixed filename and exclusive creation. Increase the directory-entry maximum by one. This is a fail-closed late-commit path, not a timing proof for a crashed owner; the later authenticated handoff explicitly requires the live worker's returned receipt. A failed latch write leaves the owned run failed and prevents handoff; never resume it from the positive outcome row alone. Test an injected clock advance during outcome `fsync`, then verify the latch exists, next reservation and reopen refuse, and the socket count remains unchanged.

### Synthetic verification and handoff

**Files:** Continue the `tests/gufo/test_finite_transport.py` started in Step 1 and modify only the three named production files if a test finds a defect.

- [ ] **Step 8: Verify the transport tests already written in Step 4.** Their complete source follows for direct copying at Step 4; no real socket or listener is opened.

```python
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from gufo_control import finite_transport
from gufo_control.finite_ledger import Ledger
from gufo_control.finite_workload import load_workload

class FiniteTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ledger'
        self.workload = load_workload()
        self.now = [100.0]
        self.ledger = Ledger(self.root, self.workload, 1, 'transport-test', 100.0,
                             create=True, clock=lambda: self.now[0])
        self.events = []

    def client(self, factory):
        return finite_transport.FiniteTransport(
            self.ledger, self.workload, 'A' * 43, socket_factory=factory,
            clock=lambda: self.now[0], milestone=self.events.append)

    def test_reservation_precedes_factory_even_on_ambiguous_send(self):
        def factory(host, port, timeout):
            self.assertTrue((self.root / 'post-001.reserved.json').exists())
            return ScriptedSocket(on_send=lambda data: (_ for _ in ()).throw(OSError('ambiguous')))
        result = self.client(factory).post(1)
        self.assertFalse(result.success)
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)
        self.assertTrue((self.root / 'post-001.outcome.json').exists())

    def test_split_secret_capture_hash_and_no_raw_copy(self):
        sink = finite_transport.Capture(Path(self.temp.name) / 'raw.wire.bin', b'split-secret', 100)
        sink.feed(b'prefix split-', 100.0)
        sink.feed(b'secret suffix', 100.1)
        sink.close()
        data = (Path(self.temp.name) / 'raw.wire.bin').read_bytes()
        self.assertEqual(len(data), len(b'prefix split-secret suffix'))
        self.assertNotIn(b'split-secret', data)
        self.assertEqual(sink.raw_hash.hexdigest(),
                         __import__('hashlib').sha256(b'prefix split-secret suffix').hexdigest())

    def test_three_socket_ceiling(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        gate = threading.Event()
        active, peak, made = [0], [0], [0]
        lock = threading.Lock()
        opened = threading.Condition(lock)
        payload = b'{"error":{"code":"not_ready"}}'
        wire = (b'HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(payload)}\r\n\r\n'.encode() + payload)
        class HoldingSocket:
            def __init__(self):
                self.received = False
                self.closed = False
            def settimeout(self, timeout):
                self.timeout = timeout
            def sendall(self, data):
                pass
            def recv(self, maximum):
                gate.wait(2)
                if not self.received:
                    self.received = True
                    return wire
                return b''
            def close(self):
                if not self.closed:
                    self.closed = True
                    with lock:
                        active[0] -= 1
        def factory(host, port, timeout):
            with lock:
                active[0] += 1
                made[0] += 1
                peak[0] = max(peak[0], active[0])
                opened.notify_all()
            return HoldingSocket()
        client = self.client(factory)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = []
            for ordinal in (1, 2, 3):
                futures.append(pool.submit(client.get, 'ready', ordinal))
                with opened:
                    self.assertTrue(opened.wait_for(lambda: made[0] == ordinal, timeout=2))
            fourth = pool.submit(client.get, 'ready', 4)
            time.sleep(0.05)
            with lock:
                self.assertEqual(made[0], 3)
            gate.set()
            results = [future.result(timeout=3) for future in futures + [fourth]]
        self.assertEqual(peak[0], 3)
        self.assertEqual(self.ledger.snapshot()['counts']['ready'], 4)
        self.assertTrue(all(result.success for result in results))

    def test_sibling_evidence_not_ledger_metadata(self):
        sibling = self.root.with_name(self.root.name + '-finite-evidence')
        self.assertEqual(self.ledger.snapshot()['reserved_evidence_bytes'], 1048576)
        sibling.mkdir()
        (sibling / 'unexpected.bin').write_bytes(b'x')
        called = []
        result = self.client(lambda *args: called.append(args)).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(called, [])
        self.assertEqual(self.ledger.snapshot()['counts']['ready'], 1)

    def test_ledger_root_rejects_capture(self):
        (self.root / 'post-001.wire.bin').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_entry'):
            self.ledger.snapshot()
```

Append these concrete synthetic checks to `FiniteTransportTests`; they exercise the header-stage disconnect, exact received-wire accounting, incremental trigger semantics, bounds, and no socket on invalid evidence:

```python
    def test_ready_shape_and_bounded_return(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        result = self.client(lambda *args: sock).get('ready', 1)
        self.assertTrue(result.success)
        self.assertEqual(result.response['model'], 'gufo-flash-next')
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertEqual(result.wire_sha256,
                         __import__('hashlib').sha256(wire).hexdigest().upper())
        self.assertNotIn('response', json.loads((self.root / 'ready-001.outcome.json').read_text())['result'])

    def test_header_disconnect_counts_buffered_body_and_consumes_slot(self):
        for attempt in range(1, 31):
            post = self.workload.post(1, attempt)
            row = self.ledger.reserve('post', attempt, body=post.body)
            self.ledger.complete(row['slot'], {'success': True})
        body = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        result = self.client(lambda *args: sock).post(31, disconnect='headers')
        self.assertTrue(result.success)
        self.assertEqual(result.buffered_at_close, len(body))
        self.assertEqual(result.first_content_at, None)
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertTrue(sock.closed)

    def test_incremental_chat_trigger_ignores_role_and_rejects_terminal(self):
        seen = []
        observer = finite_transport.SseObserver('/v1/chat/completions', 1,
                                                  lambda event, at: seen.append((event, at)))
        self.assertFalse(observer.feed(b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n', 2.0))
        self.assertTrue(observer.feed(b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n', 3.0))
        self.assertEqual(seen, [('first_content', 3.0)])
        early = finite_transport.SseObserver('/v1/chat/completions', 8, lambda *_: None)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'cancel_trigger_missed'):
            early.feed(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n', 4.0)

    def test_responses_sequence_and_type_checked_before_cancel(self):
        observer = finite_transport.SseObserver('/v1/responses', 1, lambda *_: None)
        bad = (b'event: response.output_text.delta\n'
               b'data: {"type":"response.output_text.delta","sequence_number":1,"delta":"x"}\n\n')
        with self.assertRaisesRegex(smoke_http.SmokeError, 'sse_sequence_or_type'):
            observer.feed(bad, 1.0)

    def test_complete_chat_tail_survives_observer_and_transport(self):
        timing = dict(prompt_n=26, cache_n=0, predicted_n=1,
                      draft_n=0, draft_n_accepted=0)
        frames = [
            dict(model='gufo-flash-next',
                 choices=[dict(index=0, delta=dict(content='4'), finish_reason=None)]),
            dict(choices=[dict(index=0, delta={}, finish_reason='stop')], timings=timing),
            dict(choices=[], usage=dict(prompt_tokens=26, completion_tokens=1,
                                        total_tokens=27), timings=timing)]
        events = b''.join(b'data: ' + json.dumps(value).encode() + b'\n\n'
                          for value in frames) + b'data: [DONE]\n\n'
        head = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(events)}\r\n\r\n'.encode())
        result = self.client(lambda *args: ScriptedSocket([head, events])).post(1)
        self.assertTrue(result.success, result)
        self.assertTrue(result.assessment['fully_validated'], result.assessment)
        self.assertEqual(result.classification, 'complete_positive')
        self.assertIsNotNone(result.first_content_at)
        self.assertIsNotNone(result.terminal_at)
        self.assertTrue((self.root.with_name(self.root.name + '-finite-evidence') /
                         'post-001.answer.json').exists())

    def test_pinned_tool_stream_completes_without_usage_chunk(self):
        for attempt in range(1, 12):
            post = self.workload.post(1, attempt)
            row = self.ledger.reserve('post', attempt, body=post.body)
            self.ledger.complete(row['slot'], {'success': True})
        tool = dict(index=0, id='call_1', type='function',
                    function=dict(name='report_sum', arguments='{"sum":4}'))
        frames = [
            dict(model='gufo-flash-next',
                 choices=[dict(index=0, delta=dict(tool_calls=[tool]), finish_reason=None)]),
            dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')],
                 timings=dict(prompt_n=2304, cache_n=0, predicted_n=1,
                              draft_n=0, draft_n_accepted=0))]
        events = b''.join(b'data: ' + json.dumps(value).encode() + b'\n\n'
                          for value in frames) + b'data: [DONE]\n\n'
        head = (b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                + f'Content-Length: {len(events)}\r\n\r\n'.encode())
        result = self.client(lambda *args: ScriptedSocket([head, events])).post(12)
        self.assertTrue(result.success, result)
        self.assertTrue(result.assessment['fully_validated'], result.assessment)
        self.assertEqual(result.classification, 'complete_positive')
        self.assertIsNotNone(result.terminal_at)

    def test_received_overcap_keeps_prefix_and_hashes_all(self):
        path = Path(self.temp.name) / 'bounded.wire.bin'
        sink = finite_transport.Capture(path, b'split-secret', 16)
        first, second = b'prefix split-', b'secret suffix'
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(first + second, 1.0)
        sink.close()
        self.assertEqual(sink.count, len(first + second))
        self.assertLessEqual(path.stat().st_size, 16)
        self.assertNotIn(b'split-secret', path.read_bytes())
        self.assertEqual(sink.raw_hash.hexdigest(),
                         __import__('hashlib').sha256(first + second).hexdigest())

    def test_part_limit_fails_before_append(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        with patch.object(finite_transport.finite_responses, 'PART_LIMIT', 0):
            result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'body_parts_limit')
```

Append these methods to `FiniteTransportTests`. They give exact bytes for the remaining transport boundaries; the later phase scheduler owns full wave proof.

```python
    def test_responses_first_and_eighth_content_events(self):
        for target in (1, 8):
            with self.subTest(target=target):
                seen = []
                observer = finite_transport.SseObserver('/v1/responses', target,
                    lambda event, at: seen.append((event, at)))
                for number in range(target):
                    frame = (f'event: response.output_text.delta\n'
                             f'data: {{"type":"response.output_text.delta",'
                             f'"sequence_number":{number},"delta":"x"}}\n\n').encode()
                    self.assertEqual(observer.feed(frame[:7], float(number)), False)
                    hit = observer.feed(frame[7:], float(number) + 0.1)
                    self.assertEqual(hit, number + 1 == target)
                self.assertEqual(observer.count, target)
                self.assertEqual(seen, [('first_content', 0.1)])

    def test_encoded_output_and_utf8_frame_bounds(self):
        observer = finite_transport.SseObserver('/v1/responses', None, lambda *_: None)
        frame = (b'event: response.output_text.delta\n'
                 b'data: {"type":"response.output_text.delta","sequence_number":0,"delta":"')
        with self.assertRaises(UnicodeError):
            observer.feed(frame + b'\xff"}\n\n', 1.0)
        large = finite_transport.SseObserver('/v1/chat/completions', None, lambda *_: None)
        payload = b'data: {"choices":[{"delta":{"content":"' + b'x' * 1048577 + b'"}}]}\n\n'
        with self.assertRaisesRegex(smoke_http.SmokeError, 'decoded_output_limit'):
            large.feed(payload, 1.0)

    def test_chunk_framing_in_received_hash(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Transfer-Encoding: chunked\r\n\r\n'
                + f'{len(body):X}\r\n'.encode() + body + b'\r\n0\r\n\r\n')
        result = self.client(lambda *args: ScriptedSocket([wire])).get('ready', 1)
        self.assertTrue(result.success)
        self.assertEqual(result.wire_bytes, len(wire))
        self.assertEqual(result.wire_sha256,
                         __import__('hashlib').sha256(wire).hexdigest().upper())

    def test_get_body_and_wire_caps(self):
        body = b'x' * 49153
        framed = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                  + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        result = self.client(lambda *args: ScriptedSocket([framed])).get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'response_body_limit')
        self.assertLessEqual((self.root.with_name(self.root.name + '-finite-evidence') /
                              'ready-001.wire.bin').stat().st_size, 65536)

    def test_post_wire_and_body_limits_use_pinned_numbers(self):
        capture_path = Path(self.temp.name) / 'post-cap.wire.bin'
        sink = finite_transport.Capture(capture_path, b'A' * 43, 8388608)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(b'x' * 8388609, 1.0)
        sink.close()
        self.assertEqual(sink.count, 8388609)
        self.assertEqual(capture_path.stat().st_size, 8388608)
        reader = smoke_http._Reader(ScriptedSocket(), 60.0, threading.Event(),
                                    check=lambda *_: None)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_body_limit'):
            list(smoke_http._body_chunks(reader, {'content-length': '7340033'},
                                         body_limit=7340032))

    def test_get_wire_limit_counts_all_received_bytes(self):
        path = Path(self.temp.name) / 'get-cap.wire.bin'
        sink = finite_transport.Capture(path, b'A' * 43, 65536)
        with self.assertRaisesRegex(smoke_http.SmokeError, 'response_wire_limit'):
            sink.feed(b'x' * 65537, 1.0)
        sink.close()
        self.assertEqual(sink.count, 65537)
        self.assertEqual(path.stat().st_size, 65536)

    def test_get_outcome_limit_is_4096(self):
        row = self.ledger.reserve('ready', 1)
        with self.assertRaisesRegex(ValueError, 'finite_record_size'):
            self.ledger.complete(row['slot'], {'success': True, 'oversize': 'x' * 4096})
        self.assertEqual(self.ledger.snapshot()['pending'], ['ready-001'])

    def test_answer_file_limit_rejects_without_saving_answer(self):
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Content-Length: 2\r\n\r\n{}')
        parsed = dict(visible_answer='x' * 1048576, reasoning_content='', tool_calls=[])
        with patch.object(finite_transport.finite_responses, 'parse_positive_response', return_value=parsed), \
             patch.object(finite_transport.finite_assessment, 'assess_positive',
                          return_value={'structural_success': True}):
            result = self.client(lambda *args: ScriptedSocket([wire])).post(1)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'answer_limit')
        self.assertFalse((self.root.with_name(self.root.name + '-finite-evidence') /
                          'post-001.answer.json').exists())

    def test_exact_pinned_exception_request_bytes(self):
        post = self.workload.post(1, 60)
        self.assertEqual((post.request_id, len(post.body)), ('reject_body_16385', 16385))
        request = self.client(lambda *args: self.fail('socket'))._request('POST', post.route, post.body)
        head, sent_body = request.split(b'\r\n\r\n', 1)
        self.assertIn(b'Content-Length: 16385', head)
        self.assertEqual(sent_body, post.body)
        self.assertEqual(__import__('hashlib').sha256(sent_body).hexdigest().upper(),
                         post.body_sha256)

    def test_deadline_during_send_latches_and_refuses_next(self):
        def late_send(data):
            self.now[0] = 161.0
        client = self.client(lambda *args: ScriptedSocket(on_send=late_send))
        with self.assertRaisesRegex(ValueError, 'finite_outcome_deadline'):
            client.post(1)
        self.assertTrue((self.root / 'transport-failed.json').exists())
        with self.assertRaisesRegex(ValueError, 'finite_transport_failed'):
            client.post(2)

    def test_bad_sibling_symlink_blocks_socket(self):
        sibling = self.root.with_name(self.root.name + '-finite-evidence')
        try:
            sibling.symlink_to(Path(self.temp.name), target_is_directory=True)
        except OSError:
            self.skipTest('Windows symlink privilege unavailable')
        calls = []
        with self.assertRaisesRegex(ValueError, 'reparse_path'):
            self.client(lambda *args: calls.append(args))
        self.assertEqual(calls, [])
```


The following focused fault tests are part of Step 4's RED work; they use
real ledger persistence with failure injection only at the relevant I/O seam:

```python
    def test_late_outcome_flush_refuses_snapshot_reserve_and_reopen(self):
        from gufo_control import finite_ledger
        original_exclusive = finite_ledger._exclusive
        def advance_after_outcome(path, value, maximum):
            original_exclusive(path, value, maximum)
            if path.name.endswith('.outcome.json'):
                self.now[0] = 161.0
        row = self.ledger.reserve('ready', 1)
        with patch.object(finite_ledger, '_exclusive', side_effect=advance_after_outcome):
            with self.assertRaisesRegex(ValueError, 'finite_outcome_deadline'):
                self.ledger.complete(row['slot'], {'success': True})
        self.assertTrue((self.root / 'transport-failed.json').exists())
        for action in (self.ledger.snapshot, lambda: self.ledger.reserve('ready', 2),
                       lambda: Ledger(self.root, self.workload, 1, 'transport-test',
                                      100.0, clock=lambda: self.now[0])):
            with self.assertRaisesRegex(ValueError, 'finite_transport_failed'):
                action()

    def test_unexpected_terminal_callback_persists_failure(self):
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = ScriptedSocket([wire])
        client = self.client(lambda *args: sock)
        def unexpected(event):
            if event.event == 'terminal':
                raise RuntimeError('callback failed')
        client.milestone = unexpected
        with self.assertRaises(RuntimeError):
            client.get('ready', 1)
        outcome = json.loads((self.root / 'ready-001.outcome.json').read_text())
        self.assertFalse(outcome['result']['success'])
        self.assertTrue(sock.closed)
        self.assertEqual(self.ledger.snapshot()['pending'], [])

    def test_socket_close_failure_consumes_and_releases_permit(self):
        class CloseFailSocket(ScriptedSocket):
            def close(self):
                self.closed = True
                raise OSError('close failed')
        body = b'{"status":"ready","model":"gufo-flash-next"}'
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                + f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        sock = CloseFailSocket([wire])
        client = self.client(lambda *args: sock)
        result = client.get('ready', 1)
        self.assertFalse(result.success)
        self.assertEqual(self.ledger.snapshot()['pending'], [])
        acquired = [client.sockets.acquire(blocking=False) for _ in range(4)]
        self.assertEqual(acquired, [True, True, True, False])
        for held in acquired:
            if held:
                client.sockets.release()

```

No test opens a real network socket.

- [ ] **Step 9: Run RED for each new test, implement the minimal correction, then GREEN.** In PowerShell set `$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'`, then run `python -m unittest test_finite_transport.ReaderTests test_finite_transport.FiniteTransportTests test_smoke_http.ReusableHelpersTests -v` and `python -m unittest test_finite_ledger test_finite_responses test_finite_assessment -v`. Run `git diff --check`. Expected: all tests pass; none of these classes creates a real socket or listener. Do not run `test_smoke_http.SmokeHttpTests` under this offline restriction.

- [ ] **Step 10: Self-review and commit only the four named code/test paths.** Inspect `git diff -- scripts/gufo_control/smoke_http.py scripts/gufo_control/finite_ledger.py scripts/gufo_control/finite_transport.py tests/gufo/test_finite_transport.py`; preserve the completed assessment test and files. Record remaining full-memory review gates in the later integration handoff. No launch, live probe, PR or publication follows from this test result.

## Review limits and unresolved risks

This plan is the next transport/evidence task only. The later phase controller must enforce sequential phases, exact readiness handoff, 66/6 coverage, 240/1 GET caps, active stream drain during overlaps, wave1 exact `429/queue_full`, wave2 exact `400/context_length_exceeded` with observed in-flight intervals, cancellation reuse, and authenticated stop. It must not pause a worker, infer queue occupancy from unread buffers, interpret SSE event counts as tokens, or repeat a missed reservation. A late outcome return latches the run and forbids more reservations. At authenticated handoff, the later controller and guardian must require the live worker's on-time returned receipt and complete coverage; a standalone successful ledger row or a process crash between flush and receipt is never sufficient. The later store/guardian review must prove lifecycle admission and 49/24/12 floors under the 68/4/20 envelope. Full process/RSS/VRAM memory accounting and terminal recovery remain independent gates.
