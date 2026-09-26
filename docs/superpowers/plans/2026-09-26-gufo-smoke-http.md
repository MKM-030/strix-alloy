# Bounded GUFO HTTP Smoke Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one cancellable, bounded, authenticated HTTP client that establishes GUFO readiness and makes exactly one small direct-answer generation request, without owning the server.

**Architecture:** `smoke_http.py` is an isolated standard-library worker. A future guardian supplies absolute monotonic startup and owned-process deadlines, starts one daemon worker, polls its completion, and may set its cancellation event without waiting for network I/O. The worker uses short socket timeouts plus absolute deadlines, records bounded raw responses and distinct client/engine metrics, and never retries a generation.

**Tech Stack:** Python standard library (`socket`, `threading`, `time`, `json`, `dataclasses`); existing `unittest` convention; local CPU fake HTTP server only.

## Global Constraints

- Implement only `C:\Projects\strix-alloy-research\integration\scripts\gufo_control\smoke_http.py` and `C:\Projects\strix-alloy-research\integration\tests\gufo\test_smoke_http.py`. Do not change process, memory, GPU, build, installation, or existing client modules in this task.
- Source contract is `pixmaate/gufo@cff564964e8506c0abb3e530cecb55332187ac6c`; use the already researched `reports/gufo-http-measurement-contract-20260926.md` and `reports/gufo-ar4k-measured-margin-review-20260926.md`.
- Fixed endpoint: IPv4 loopback `127.0.0.1:8836`, model `gufo-flash-next`. A private ephemeral bearer key is mandatory on **every** GET and POST, and must never appear in returned records, saved logs, or exception text.
- First smoke has at most 240 `/ready` polls within 480 seconds, exactly one `/v1/models` query after readiness, and at most one `/v1/chat/completions` POST total. The POST is also the correctness/readiness completion; there is no warmup or automatic retry.
- Generation body is the exact public `2 + 2` control below, `max_tokens: 64`, explicit supported greedy controls, `cache_prompt: false`, `enable_thinking: false`, streaming with `include_usage: true`. No per-request speculative/MTP fields.
- Request body <=16,384 bytes; collected response <=1,048,576 bytes **per HTTP exchange**. Reject over-limit responses, malformed framing, malformed JSON/SSE, HTTP errors, wrong alias, unknown required token counts, cache hits, or incorrect answer while preserving sanitized raw response and error.
- Completion has an absolute 60-second deadline from request submission, further limited by the guardian's absolute owned-process deadline. A trickle of bytes cannot renew it. The guardian independently enforces its proposed 600-second lifetime and continues memory monitoring and owned stop; this module never starts, kills, or waits for a server process.
- `usage.prompt_tokens` is full logical input; `usage.gufo.prefill_tokens` and `timings.prompt_n` are newly processed input. Record both, detect disagreement, and never infer token counts from SSE chunks or output characters. A missing value stays `None`, never zero. Engine times and client HTTP times have separate names and monotonic semantics.

## File map and integration interface

| File | Responsibility |
| --- | --- |
| `scripts/gufo_control/smoke_http.py` | Fixed request and endpoint, bounded HTTP/SSE transport, count/metric extraction, sanitized result, nonblocking-to-guardian worker interface. |
| `tests/gufo/test_smoke_http.py` | Deterministic loopback fake GUFO HTTP responses, authorization and request-shape assertions, one-POST guarantee, deadlines, cancellation, size and malformed-data failures. |

Public interface: `start_smoke(*, api_key: str, startup_deadline: float, lifetime_deadline: float, cancel: threading.Event | None = None) -> SmokeTask`. `SmokeTask.done` is a `threading.Event`, `SmokeTask.cancel` is the supplied/shared event, and `SmokeTask.result` is `None` until done, then a JSON-serializable dictionary. Guardian calls this once after resuming its owned child, polls `done.is_set()` while monitoring memory, and sets `cancel` on an abort. It must never `join()` this worker on its monitoring or stop path. The client returns `post_attempted: true` immediately after committing to the only POST; the guardian must treat any POST failure as consumed and stop the owned run rather than call `start_smoke` again. This is an integration contract, not an implementation of the guardian.

## Approved review amendment (2026-09-26)

The user explicitly approved the review fixes and continuation. This amendment supersedes conflicting example implementation and test prose below; remaining endpoint, authentication, count, deadline and size constraints are unchanged.

- Preserve original socket receive boundaries and monotonic arrival times through header stripping and HTTP body decoding. First visible SSE content is timed at the receive that completes its event, not a later buffered read. Cover delayed multi-read Content-Length and chunked bodies, multiple events within a chunk, and co-received headers/body.
- Validate Content-Length as ASCII decimal digits and chunk-size as ASCII hexadecimal digits before conversion (before any chunk extension). Reject signed, underscored and other malformed syntax; preserve bounded framing checks.
- Distinguish absent counters from present-invalid values. Every supplied malformed counter or timing metric is a fatal validation error naming its source, even when a valid fallback exists. Required logical prompt, completion, newly processed prefill and cached-token counts remain mandatory; valid duplicate sources must agree.
- Genuinely absent optional metrics remain null and are listed in nonfatal `unavailable_metrics` diagnostics. This includes optional timing/draft metrics and optional total/predicted counters; no fabricated zero or throughput. Malformed supplied optional values still fail. Output must remain finite JSON.
- Fix the response-close POST failure test to record the received attempt inside its replacement handler and assert exactly one. Label response-side close accurately. Test ambiguous send failure separately if claiming that coverage; no generation retry in either case.

Use focused regression-first tests in `tests/gufo/test_smoke_http.py`; implementation stays in the two named files. No real model, GPU or production endpoint is exercised by this task.

## Task 1: Complete fixed, bounded HTTP smoke worker

**Files:** Create `scripts/gufo_control/smoke_http.py`; test in `tests/gufo/test_smoke_http.py`.

**Interfaces:** `REQUEST` is a constant dict copied into the result. `_exchange(method, path, body, key, deadline, cancel)` returns `(status, headers, body_bytes, submitted_monotonic, completed_monotonic, body_parts)`; each `body_parts` member is `(decoded_body_chunk, monotonic_arrival)`. A single `SmokeTask` worker calls it. No caller may supply a URL or host.

- [ ] **Step 1: Write all failing local fake-server tests.** Use `unittest`, `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` and a patched module `PORT` for tests only. The handler must record method, path, `Authorization`, exact POST JSON and POST count. Test authenticated 503→200 readiness, a single model list, the exact POST body, and a terminal streaming response. Assert `POST count == 1`, all three paths had `Bearer <key>`, `request bytes <= 16384`, and the serialized `task.result` does not contain the key. Add the failure matrix below in the same test-writing phase. Do not use a real GUFO server.

```python
# tests/gufo/test_smoke_http.py: first local contract test. Add the Step 1
# failure cases as separate methods using the same handler pattern.
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import patch
from gufo_control import smoke_http

def sse(value):
    return b"data: " + json.dumps(value).encode("utf-8") + b"\n\n"

class Handler(BaseHTTPRequestHandler):
    calls = []
    ready_polls = 0

    def log_message(self, *_):
        pass

    def _reply(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization"), None))
        if self.path == "/ready":
            type(self).ready_polls += 1
            if self.ready_polls == 1:
                return self._reply(503, b'{"error":{"code":"not_ready"}}')
            return self._reply(200, b'{"status":"ready","model":"gufo-flash-next"}')
        if self.path == "/v1/models":
            return self._reply(200, b'{"data":[{"id":"gufo-flash-next"}]}')
        self._reply(404, b'{"error":{"code":"not_found"}}')

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        usage = {"prompt_tokens": 20, "completion_tokens": 1,
                 "total_tokens": 21,
                 "prompt_tokens_details": {"cached_tokens": 0},
                 "gufo": {"prefill_tokens": 20, "cache_hit": False,
                          "ttft_ms": 12.5, "prefill_ms": 5.0, "decode_ms": 7.5}}
        timings = {"prompt_n": 20, "cache_n": 0, "predicted_n": 1,
                   "prompt_ms": 5.0, "predicted_ms": 7.5}
        events = (sse({"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]})
                  + sse({"choices": [{"delta": {"content": "4"}, "finish_reason": None}]})
                  + sse({"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": timings})
                  + sse({"choices": [], "usage": usage, "timings": timings})
                  + b"data: [DONE]\n\n")
        self._reply(200, events, "text/event-stream")

class SmokeHttpTests(unittest.TestCase):
    def test_one_authenticated_completion_and_metrics(self):
        Handler.calls, Handler.ready_polls = [], 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(smoke_http, "PORT", server.server_port):
                now = time.monotonic()
                task = smoke_http.start_smoke(api_key="private-test-key",
                    startup_deadline=now+5, lifetime_deadline=now+8)
                self.assertTrue(task.done.wait(6))
            result = task.result
            self.assertTrue(result["success"], result)
            self.assertEqual(result["ready_polls"], 2)
            self.assertEqual([call[1] for call in Handler.calls],
                             ["/ready", "/ready", "/v1/models", "/v1/chat/completions"])
            self.assertTrue(all(call[2] == "Bearer private-test-key" for call in Handler.calls))
            posts = [call for call in Handler.calls if call[0] == "POST"]
            self.assertEqual(len(posts), 1)
            self.assertLessEqual(len(posts[0][3]), 16_384)
            self.assertEqual(json.loads(posts[0][3]), smoke_http.REQUEST)
            self.assertEqual(result["metrics"]["logical_prompt_tokens"], 20)
            self.assertEqual(result["metrics"]["new_prefill_tokens"], 20)
            self.assertEqual(result["metrics"]["completion_tokens"], 1)
            self.assertGreaterEqual(result["metrics"]["first_visible_content_ms"], 0)
            self.assertGreaterEqual(result["metrics"]["http_duration_ms"],
                                    result["metrics"]["first_visible_content_ms"])
            self.assertNotIn("private-test-key", json.dumps(result))
        finally:
            server.shutdown()
            server.server_close()
```
- [ ] **Step 2: Run the focused test.** From `C:\Projects\strix-alloy-research\integration`: `python -m unittest discover -s tests/gufo -p test_smoke_http.py -v`. Expected: fail because `gufo_control.smoke_http` does not exist. Use the repository's existing test import setup (the existing GUFO test suite imports `gufo_control` from `scripts`); if needed set `PYTHONPATH=scripts` for this one command, not in code.
- [ ] **Step 3: Implement the complete worker.** The transport and protocol code below are one deliverable; make all focused tests pass before review. These are the fixed transport constants and methods:

```python
HOST = "127.0.0.1"
PORT = 8836
MODEL = "gufo-flash-next"
MAX_REQUEST = 16_384
MAX_RESPONSE = 1_048_576
MAX_READY_POLLS = 240
SOCKET_SLICE = 0.25
PROMPT = "What is 2 + 2? Reply with the number only."
REQUEST = {
    "model": MODEL,
    "messages": [{"role": "user", "content": PROMPT}],
    "max_tokens": 64,
    "temperature": 0, "top_p": 1, "top_k": 0,
    "min_p": 0, "min_keep": 1, "seed": 42,
    "repeat_penalty": 1, "repeat_last_n": 0,
    "frequency_penalty": 0, "presence_penalty": 0,
    "cache_prompt": False,
    "chat_template_kwargs": {"enable_thinking": False},
    "stream": True,
    "stream_options": {"include_usage": True},
}

class SmokeError(Exception):
    def __init__(self, code, raw_response=b""):
        super().__init__(code)
        self.code = code
        self.raw_response = raw_response

def _check(deadline, cancel):
    if cancel.is_set():
        raise SmokeError("cancelled")
    if time.monotonic() >= deadline:
        raise SmokeError("deadline_exceeded")

class _Reader:
    def __init__(self, sock, deadline, cancel):
        self.sock, self.deadline, self.cancel = sock, deadline, cancel
        self.buffer = bytearray()
        self.raw = bytearray()
        self.wire_count = 0

    def _recv(self):
        while True:
            _check(self.deadline, self.cancel)
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            if data:
                self.wire_count += len(data)
                # Header/framing overhead is bounded as well as decoded body.
                if self.wire_count > MAX_RESPONSE + 16_384:
                    raise SmokeError("response_wire_limit")
                self.raw.extend(data)
            return data

    def until(self, marker, limit):
        while marker not in self.buffer:
            if len(self.buffer) > limit and marker not in self.buffer:
                raise SmokeError("response_header_limit")
            data = self._recv()
            if not data:
                raise SmokeError("truncated_response")
            self.buffer.extend(data)
        index = self.buffer.index(marker) + len(marker)
        if index > limit:
            raise SmokeError("response_header_limit")
        out = bytes(self.buffer[:index])
        del self.buffer[:index]
        return out

    def exact(self, length):
        while len(self.buffer) < length:
            data = self._recv()
            if not data:
                raise SmokeError("truncated_response")
            self.buffer.extend(data)
        out = bytes(self.buffer[:length])
        del self.buffer[:length]
        return out

    def some(self, maximum=4096):
        if not self.buffer:
            self.buffer.extend(self._recv())
        out = bytes(self.buffer[:maximum])
        del self.buffer[:maximum]
        return out

def _body_chunks(reader, headers):
    transfer = headers.get("transfer-encoding", "").lower()
    if transfer == "chunked":
        while True:
            line = reader.until(b"\r\n", 128)[:-2]
            try:
                size = int(line.split(b";", 1)[0], 16)
            except ValueError as exc:
                raise SmokeError("malformed_chunk_size") from exc
            if size < 0 or size > MAX_RESPONSE:
                raise SmokeError("response_body_limit")
            if size == 0:
                # GUFO does not send trailers; require the terminating CRLF.
                if reader.exact(2) != b"\r\n":
                    raise SmokeError("malformed_chunk_end")
                return
            remaining = size
            while remaining:
                part = reader.exact(min(remaining, 4096))
                remaining -= len(part)
                yield part, time.monotonic()
            if reader.exact(2) != b"\r\n":
                raise SmokeError("malformed_chunk_end")
    elif "content-length" in headers:
        try:
            remaining = int(headers["content-length"])
        except ValueError as exc:
            raise SmokeError("malformed_content_length") from exc
        if remaining < 0 or remaining > MAX_RESPONSE:
            raise SmokeError("response_body_limit")
        while remaining:
            part = reader.exact(min(remaining, 4096))
            remaining -= len(part)
            yield part, time.monotonic()
    else:
        while True:
            part = reader.some()
            if not part:
                return
            yield part, time.monotonic()

def _exchange(method, path, body, key, deadline, cancel):
    if not key or any(ch.isspace() for ch in key) or "\r" in key or "\n" in key:
        raise SmokeError("invalid_private_key")
    if body is not None and len(body) > MAX_REQUEST:
        raise SmokeError("request_body_limit")
    _check(deadline, cancel)
    # Fixed literal authority and target prevent redirects or accidental remote use.
    headers = [f"{method} {path} HTTP/1.1", f"Host: {HOST}:{PORT}",
               f"Authorization: Bearer {key}", "Connection: close",
               "Accept: application/json, text/event-stream"]
    if body is not None:
        headers += ["Content-Type: application/json", f"Content-Length: {len(body)}"]
    wire = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + (body or b"")
    submitted = time.monotonic()
    reader = None
    try:
        with socket.create_connection((HOST, PORT), timeout=SOCKET_SLICE) as sock:
            sock.settimeout(SOCKET_SLICE)
            # A send timeout is terminal. Never repeat the POST after ambiguity.
            _check(deadline, cancel)
            sock.sendall(wire)
            reader = _Reader(sock, deadline, cancel)
            raw_head = reader.until(b"\r\n\r\n", 16_384)
            head = raw_head[:-4].decode("iso-8859-1").split("\r\n")
            status_parts = head[0].split(" ", 2)
            if len(status_parts) < 2 or not status_parts[0].startswith("HTTP/1."):
                raise SmokeError("malformed_status")
            try:
                status = int(status_parts[1])
            except ValueError as exc:
                raise SmokeError("malformed_status") from exc
            response_headers = {}
            for line in head[1:]:
                if ":" not in line:
                    raise SmokeError("malformed_header")
                name, value = line.split(":", 1)
                name = name.strip().lower()
                if name in response_headers:
                    raise SmokeError("duplicate_header")
                response_headers[name] = value.strip()
            transfer = response_headers.get("transfer-encoding")
            if transfer is not None and transfer.lower() != "chunked":
                raise SmokeError("unsupported_transfer_encoding")
            if transfer is not None and "content-length" in response_headers:
                raise SmokeError("ambiguous_response_framing")
            parts, total = [], 0
            for part, arrived in _body_chunks(reader, response_headers):
                total += len(part)
                if total > MAX_RESPONSE:
                    raise SmokeError("response_body_limit")
                parts.append((part, arrived))
            _check(deadline, cancel)
            return status, response_headers, b"".join(p for p, _ in parts), submitted, time.monotonic(), parts
    except SmokeError as exc:
        if reader is not None:
            exc.raw_response = bytes(reader.raw)
        raise
    except (OSError, UnicodeError) as exc:
        # Do not include request headers or an arbitrary URL in errors.
        raise SmokeError(f"transport_{type(exc).__name__}",
                         bytes(reader.raw) if reader is not None else b"") from None
```

`SmokeError.raw_response` is the bounded raw HTTP response bytes received so far, including framing; the public result decodes it with replacement and redacts the key. Tests must reject a failed POST whose partial SSE/error response is lost. The header limit applies to bytes before `\r\n\r\n`, not valid body bytes in the same socket read. No socket, server, or worker cleanup is needed beyond closing this client's connection.

The rest of Step 3 implements readiness, streaming result, and guardian-safe cancellation. `start_smoke(...) -> SmokeTask` is the sole public entry. The worker stores a JSON-serializable dict with `success`, `error`, `post_attempted`, `request`, `responses`, `metrics`, `ready_polls`, `timestamps`; all raw bodies are UTF-8 text with replacement and key redacted. A missing metric is `None` with a specific `validation_errors` entry, never inferred. `cancel` is settable independently by guardian; `done` is pollable without a join.

Step 1's additional cases use GUFO-shaped chunked SSE: role event, a `choices[0].delta.content` event containing `4`, terminal `choices[0].finish_reason: "stop"` with `timings`, usage event with `choices: []`, `usage.prompt_tokens`, `usage.completion_tokens`, `usage.prompt_tokens_details.cached_tokens`, `usage.gufo.prefill_tokens`, then `[DONE]`. Assert first visible event time and full HTTP completion time are nonnegative and distinct from engine `ttft_ms`; no SSE-event count is reported as tokens. Test 503 polling, wrong `/ready` model, wrong `/v1/models` ID, 401 on each route, HTTP 400 unsupported field, malformed SSE, missing `[DONE]`, missing/contradictory counts, cache hit, incorrect answer, output count >64, logical prompt >512, response >1MiB, timeout under slow trickle, and cancellation during a stalled response. Each path asserts no second POST and key redaction. Use short injected deadlines in tests; do not sleep for 60/480 seconds. Test unknown `Transfer-Encoding`, conflicting `Transfer-Encoding` plus `Content-Length`, echoed key in a JSON property name, nonfinite response JSON, and `timings.predicted_n` disagreement. Require `json.dumps(result, allow_nan=False)` to succeed and exclude the private key.

Parse SSE by accumulating decoded body bytes and splitting complete `\n\n` events (accept CRLF by normalizing only complete buffered data). Ignore comment-only frames; concatenate all `data:` lines in one event with `\n`. Reject invalid UTF-8, invalid JSON/SSE, `error` event, missing terminal, missing usage, missing `[DONE]`, trailing incomplete non-whitespace frame, or multiple conflicting usage/timing objects. Preserve every raw HTTP body as sanitized text. `first_visible_content_ms = 1000 * (arrival_of_first_complete_nonempty_delta.content_event - POST_submitted)`. Do not count reasoning deltas as visible content. `http_duration_ms = 1000 * (entire_POST_response_completed - POST_submitted)`. `engine_ttft_ms` is copied only from `usage.gufo.ttft_ms`. For each numerical field, accept only a finite nonnegative JSON number (integer token counts; booleans rejected). Keep full `usage`, `timings`, finish reason and response status; no fabricated metric if absent.

```python
def _int_or_none(value):
    return value if type(value) is int and value >= 0 else None

def _number_or_none(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None

def _redact(value, key):
    # Apply recursively to all returned strings, including raw response/error.
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]")
    if isinstance(value, dict):
        return {_redact(name, key): _redact(item, key) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return value

def _validate_usage(usage, timings):
    problems = []
    if not isinstance(usage, dict) or not isinstance(timings, dict):
        return {}, ["missing_usage_or_timings"]
    gufo = usage.get("gufo")
    if not isinstance(gufo, dict):
        gufo = {}
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        details = {}
    prompt = _int_or_none(usage.get("prompt_tokens"))
    completion = _int_or_none(usage.get("completion_tokens"))
    total = _int_or_none(usage.get("total_tokens"))
    prefill = _int_or_none(gufo.get("prefill_tokens"))
    timing_prefill = _int_or_none(timings.get("prompt_n"))
    cached = _int_or_none(details.get("cached_tokens"))
    legacy_cached = _int_or_none(usage.get("cached_tokens"))
    timing_cached = _int_or_none(timings.get("cache_n"))
    if prefill is None:
        prefill = timing_prefill
    if cached is None:
        cached = legacy_cached if legacy_cached is not None else timing_cached
    if prompt is None or completion is None or prefill is None or cached is None:
        problems.append("required_token_count_unknown")
    if prompt is not None and prompt > 512:
        problems.append("prompt_exceeds_512")
    if completion is not None and completion > 64:
        problems.append("completion_exceeds_64")
    if cached is not None and cached != 0:
        problems.append("cache_hit")
    if gufo.get("cache_hit") is True or gufo.get("cache_disk_hit") is True:
        problems.append("cache_hit")
    for name, a, b in (("prefill_disagrees", prefill, timing_prefill),
                       ("cached_disagrees", cached, legacy_cached),
                       ("cached_disagrees", cached, timing_cached)):
        if a is not None and b is not None and a != b:
            problems.append(name)
    if prompt is not None and prefill is not None and cached is not None and prompt != prefill + cached:
        problems.append("prompt_parts_disagree")
    if total is not None and prompt is not None and completion is not None and total != prompt + completion:
        problems.append("total_disagrees")
    predicted = _int_or_none(timings.get("predicted_n"))
    if predicted is not None and completion is not None and predicted != completion:
        problems.append("completion_disagrees")
    return {
        "logical_prompt_tokens": prompt, "new_prefill_tokens": prefill,
        "cached_prompt_tokens": cached, "completion_tokens": completion,
        "total_tokens": total,
        "engine_prefill_ms": _number_or_none(gufo.get("prefill_ms")),
        "engine_decode_ms": _number_or_none(gufo.get("decode_ms")),
        "engine_ttft_ms": _number_or_none(gufo.get("ttft_ms")),
        "engine_queue_ms": _number_or_none(gufo.get("queue_ms")),
        "engine_timing_prompt_ms": _number_or_none(timings.get("prompt_ms")),
        "engine_timing_predicted_ms": _number_or_none(timings.get("predicted_ms")),
        "engine_predicted_tokens": _int_or_none(timings.get("predicted_n")),
        "draft_tokens": _int_or_none(usage.get("draft_tokens")),
        "draft_tokens_accepted": _int_or_none(usage.get("draft_tokens_accepted")),
    }, list(dict.fromkeys(problems))
```

`/ready`: retry only a well-formed HTTP 503 `not_ready`; each completed poll consumes one of 240. A transport refusal before the server binds may also consume a poll and retry within startup deadline; authentication failures, malformed responses and any other status fail. Ready 200 must have `{"status":"ready","model":"gufo-flash-next"}`. `/v1/models`: exactly one GET; require HTTP 200 and a JSON `data` array containing exactly one entry with `id == "gufo-flash-next"` (other model IDs are an error for this isolated first profile). POST only after both checks. Prepare `json.dumps(REQUEST, separators=(",", ":"), allow_nan=False).encode("utf-8")` before POST; require <=16KiB. Mark `post_attempted=True` before the `_exchange` call. Stop at the first result/error; never loop around the POST. The direct visible answer must be exactly `"4"` after surrounding whitespace is stripped and finish reason must be `"stop"`; a length finish is incomplete.

Implement the worker with the following concrete control flow. Helper `_json_object` decodes strict UTF-8 and raises `SmokeError("malformed_json")` unless it finds a JSON object. Helper `_capture` appends `{path, status, raw_response}` to `result["responses"]`, using `body.decode("utf-8", "replace")`; final `_redact` removes any echo of the key. A `SmokeError.raw_response` from a failed exchange is captured under that attempted path before returning. These helpers never put the bearer header in the result.

```python
def _strict_json(text):
    def finite_float(number):
        value = float(number)
        if not math.isfinite(value):
            raise ValueError("nonfinite_json_number")
        return value
    def reject_constant(_):
        raise ValueError("nonfinite_json_number")
    return json.loads(text, parse_float=finite_float, parse_constant=reject_constant)

def _json_object(body):
    try:
        value = _strict_json(body.decode("utf-8", "strict"))
    except (UnicodeError, ValueError) as exc:
        raise SmokeError("malformed_json") from exc
    if not isinstance(value, dict):
        raise SmokeError("malformed_json")
    return value

def _capture(result, path, status, body):
    result["responses"].append({"path": path, "status": status,
                                "raw_response": body.decode("utf-8", "replace")})

def _parse_sse(parts, submitted):
    pending = bytearray()
    content = []
    first_visible = None
    terminal = None
    usage = None
    timings = None
    done = False
    for part, arrived in parts:
        pending.extend(part)
        # Keep undecoded bytes across transport/chunk boundaries.
        normalized = bytes(pending).replace(b"\r\n", b"\n")
        frames = normalized.split(b"\n\n")
        pending[:] = frames.pop()
        for frame in frames:
            if done:
                raise SmokeError("sse_after_done")
            try:
                lines = frame.decode("utf-8", "strict").split("\n")
            except UnicodeError as exc:
                raise SmokeError("malformed_sse_utf8") from exc
            fields = [line[5:].lstrip(" ") for line in lines if line.startswith("data:")]
            if not fields:
                continue
            payload = "\n".join(fields)
            if payload == "[DONE]":
                done = True
                continue
            try:
                event = _strict_json(payload)
            except ValueError as exc:
                raise SmokeError("malformed_sse_json") from exc
            if not isinstance(event, dict):
                raise SmokeError("malformed_sse_json")
            if "error" in event:
                raise SmokeError("sse_server_error")
            choices = event.get("choices")
            if not isinstance(choices, list):
                raise SmokeError("malformed_sse_choices")
            if choices:
                if len(choices) != 1 or not isinstance(choices[0], dict):
                    raise SmokeError("malformed_sse_choices")
                choice = choices[0]
                delta = choice.get("delta", {})
                if not isinstance(delta, dict):
                    raise SmokeError("malformed_sse_delta")
                visible = delta.get("content")
                if visible is not None:
                    if not isinstance(visible, str):
                        raise SmokeError("malformed_sse_delta")
                    if visible and first_visible is None:
                        first_visible = 1000 * (arrived - submitted)
                    content.append(visible)
                reason = choice.get("finish_reason")
                if reason is not None:
                    if terminal is not None or not isinstance(reason, str):
                        raise SmokeError("duplicate_or_bad_terminal")
                    terminal = reason
            if "usage" in event:
                if usage is not None or not isinstance(event["usage"], dict):
                    raise SmokeError("duplicate_or_bad_usage")
                usage = event["usage"]
            if "timings" in event:
                incoming = event["timings"]
                if not isinstance(incoming, dict) or (timings is not None and timings != incoming):
                    raise SmokeError("conflicting_timings")
                timings = incoming
    if bytes(pending).strip() or not done or terminal is None or usage is None or timings is None:
        raise SmokeError("incomplete_sse")
    return "".join(content), first_visible, terminal, usage, timings

class SmokeTask:
    def __init__(self, cancel):
        self.done = threading.Event()
        self.cancel = cancel
        self.result = None

def start_smoke(*, api_key: str, startup_deadline: float,
                lifetime_deadline: float, cancel: threading.Event | None = None) -> SmokeTask:
    if not isinstance(api_key, str) or not api_key or len(api_key) > 256 or not api_key.isascii() or any(c.isspace() for c in api_key):
        raise ValueError("invalid_private_key")
    if not all(type(x) in (int, float) and math.isfinite(x)
               for x in (startup_deadline, lifetime_deadline)):
        raise ValueError("invalid_deadline")
    if startup_deadline <= time.monotonic() or lifetime_deadline <= time.monotonic():
        raise ValueError("expired_deadline")
    task = SmokeTask(cancel if cancel is not None else threading.Event())

    def work():
        result = {"success": False, "error": None, "post_attempted": False,
                  "request": json.loads(json.dumps(REQUEST)), "responses": [], "metrics": {},
                  "ready_polls": 0, "timestamps": {"worker_started_monotonic": time.monotonic()}}
        path = None
        try:
            ready_deadline = min(startup_deadline, lifetime_deadline,
                                 result["timestamps"]["worker_started_monotonic"] + 480)
            ready = False
            for _ in range(MAX_READY_POLLS):
                _check(ready_deadline, task.cancel)
                path = "/ready"
                result["ready_polls"] += 1
                try:
                    status, _, body, _, _, _ = _exchange("GET", path, None, api_key,
                                                           ready_deadline, task.cancel)
                except SmokeError as exc:
                    if exc.code == "transport_ConnectionRefusedError":
                        task.cancel.wait(min(2, max(0, ready_deadline-time.monotonic())))
                        continue
                    raise
                _capture(result, path, status, body)
                response = _json_object(body)
                if status == 503 and isinstance(response.get("error"), dict) and response["error"].get("code") == "not_ready":
                    task.cancel.wait(min(2, max(0, ready_deadline-time.monotonic())))
                    continue
                if status != 200:
                    raise SmokeError(f"ready_http_{status}")
                if response.get("status") != "ready" or response.get("model") != MODEL:
                    raise SmokeError("wrong_ready_model")
                ready = True
                break
            if not ready:
                raise SmokeError("ready_poll_limit")
            path = "/v1/models"
            status, _, body, _, _, _ = _exchange("GET", path, None, api_key,
                                                  ready_deadline, task.cancel)
            _capture(result, path, status, body)
            if status != 200:
                raise SmokeError(f"models_http_{status}")
            models = _json_object(body).get("data")
            if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict) or models[0].get("id") != MODEL:
                raise SmokeError("wrong_models_identity")
            body = json.dumps(REQUEST, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(body) > MAX_REQUEST:
                raise SmokeError("request_body_limit")
            path = "/v1/chat/completions"
            completion_deadline = min(time.monotonic()+60, lifetime_deadline)
            _check(completion_deadline, task.cancel)
            result["post_attempted"] = True
            result["timestamps"]["post_attempt_monotonic"] = time.monotonic()
            status, headers, response, submitted, completed, parts = _exchange(
                "POST", path, body, api_key, completion_deadline, task.cancel)
            _capture(result, path, status, response)
            result["timestamps"].update(post_submitted_monotonic=submitted,
                                        post_completed_monotonic=completed)
            result["metrics"]["http_duration_ms"] = 1000 * (completed-submitted)
            if status != 200:
                raise SmokeError(f"completion_http_{status}")
            if not headers.get("content-type", "").lower().startswith("text/event-stream"):
                raise SmokeError("wrong_completion_content_type")
            visible, first_ms, reason, usage, timings = _parse_sse(parts, submitted)
            metrics, errors = _validate_usage(usage, timings)
            metrics["first_visible_content_ms"] = first_ms
            metrics["http_duration_ms"] = result["metrics"]["http_duration_ms"]
            result["metrics"] = metrics
            result.update(visible_answer=visible, finish_reason=reason,
                          usage=usage, timings=timings, validation_errors=errors)
            if visible.strip() != "4": errors.append("wrong_answer")
            if reason != "stop": errors.append("incomplete_finish")
            if first_ms is None: errors.append("no_visible_content")
            if errors:
                raise SmokeError("validation_failed")
            result["success"] = True
        except SmokeError as exc:
            result["error"] = exc.code
            if exc.raw_response:
                _capture(result, path, None, exc.raw_response)
        except Exception as exc:
            # No arbitrary exception text; it might contain sensitive input.
            result["error"] = "unexpected_" + type(exc).__name__
        finally:
            result["timestamps"]["worker_finished_monotonic"] = time.monotonic()
            task.result = _redact(result, api_key)
            task.done.set()

    threading.Thread(target=work, daemon=True, name="gufo-smoke-http").start()
    return task
```

`SmokeTask` contains no server/process handle. The guardian polls `.done` while collecting telemetry and never joins before initiating owned stop. On abort it calls `task.cancel.set()`, closes the owned job promptly, then may wait only within its existing finite cleanup deadline for `.done`; a worker still running makes cleanup unconfirmed. The worker's socket slices and `done.set()` in `finally` make that termination check bounded. A pending result is never success. The 60-second completion deadline is set once before the POST and is not renewed by bytes or SSE events.

- [ ] **Step 4: Run the focused suite and the existing local GUFO CPU suite.** Commands from `integration`: `python -m unittest discover -s tests/gufo -p test_smoke_http.py -v`, then `python -m unittest discover -s tests/gufo -p 'test_*.py' -v`. Expected: all focused cases pass, no regressions. These tests are offline and must not invoke the actual GUFO executable, model, GPU, HIP, WSL, or a non-loopback endpoint.
- [ ] **Step 5: Review the result contract.** Inspect all returned values with `json.dumps(result, allow_nan=False)`; assert no key, exception object, socket object, bytes, or non-finite number can escape. Verify one POST remains true on send failure, timeout, cancellation and server-side SSE error. A failed result retains sanitized request body, statuses, raw responses received so far, and the precise failure code; missing counters remain `None`. Do not produce a throughput claim from this 64-token smoke.

## Guardian handoff and unresolved integration gates

The future guardian must privately generate the bearer token, start GUFO on `127.0.0.1:8836` with `--api-key`, `--max-connections 1`, and `--max-request-bytes 16384`, reject port occupancy/other clients before resume, and pass deadlines derived from its owned-process resume time. The one-POST rule also needs an ingress/ownership gate outside this client: a well-behaved client cannot stop another local process from using a reachable listener. The guardian keeps its own telemetry loop, cancellation/stop authority, 600-second absolute lifetime, recovery checks and failure logs. This plan deliberately does not implement those modules or qualify an AR4k load.

Known source details that settle the protocol choices: the pinned Windows port emits `data:` SSE events, a terminal choice with `timings`, a separate usage chunk when `include_usage` is true, and `[DONE]` (`src/cli/serve/openai_chat.cpp:1714-1801`). `/ready` returns `status` and `model`, and `/v1/models` lists model IDs (`src/cli/serve/http_server.cpp:1269-1297`, `docs/SERVER.md:546-550`). All routes require bearer auth when configured (`docs/SERVER.md:582-590`). The plan uses no new source research.

## Self-review checklist

- [ ] Every route includes the same private authorization; no key appears in returned raw response, errors, timestamps, or logs.
- [ ] 240 readiness polls and 480-second startup are maxima; only a 503 `not_ready`/prebind refusal is retryable; exactly one model GET and at most one generation POST occur.
- [ ] Completion uses an absolute 60-second deadline, capped by the guardian lifetime; socket wait and SSE trickle cannot extend it; cancel does not block guardian memory observation or owned stop.
- [ ] Correct aliases, exact request fields, one 64-token maximum, 16KiB request and 1MiB per-response collection are checked in code and local fake-server tests.
- [ ] Raw response is retained on HTTP/protocol/timeout errors, with key redaction; malformed/unknown counts fail instead of becoming zero. Timings use monotonic request submission and full HTTP completion; first visible content is timed at a complete content event. SSE chunks are never token counts.
- [ ] No server launch, stop, GPU work, live request, WSL work, installation edit, source snapshot edit, or process/memory module work is part of this task.
