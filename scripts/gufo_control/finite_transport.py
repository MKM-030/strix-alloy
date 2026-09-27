"""Bounded HTTP transport for finite GUFO operations."""

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
        if not (disconnect is None or disconnect == 'headers' or
                type(disconnect) is int and disconnect in (1, 8)):
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
        reader = sock = observer = None
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
            if (len(fields) < 2 or fields[0] not in ('HTTP/1.0', 'HTTP/1.1')
                    or not fields[1].isascii() or not fields[1].isdecimal()
                    or len(fields[1]) != 3):
                raise smoke_http.SmokeError('malformed_status')
            status = int(fields[1])
            for line in lines[1:]:
                if ':' not in line:
                    raise smoke_http.SmokeError('malformed_header')
                name, value = line.split(':', 1)
                if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None:
                    raise smoke_http.SmokeError('malformed_header')
                name = name.lower()
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
                    if reader.some(1)[0]:
                        raise smoke_http.SmokeError('ambiguous_response_framing')
                    close_started = self.clock()
                    sock.close()
                    close_completed = self.clock()
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
            if observer is not None:
                first_at, terminal_at = observer.first_at, observer.terminal_at
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
