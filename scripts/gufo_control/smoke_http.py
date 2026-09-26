"""Fixed, bounded HTTP smoke client for the optional native GUFO profile."""

import json
import math
import socket
import threading
import time


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
    "temperature": 0,
    "top_p": 1,
    "top_k": 0,
    "min_p": 0,
    "min_keep": 1,
    "seed": 42,
    "repeat_penalty": 1,
    "repeat_last_n": 0,
    "frequency_penalty": 0,
    "presence_penalty": 0,
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
        self.arrivals = []
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
                if self.wire_count > MAX_RESPONSE + 16_384:
                    raise SmokeError("response_wire_limit")
                self.raw.extend(data)
                self.buffer.extend(data)
                self.arrivals.append((len(data), time.monotonic()))
            return data

    def _consume(self, length):
        out = bytes(self.buffer[:length])
        del self.buffer[:length]
        last_arrived = None
        remaining = length
        while remaining:
            count, arrived = self.arrivals[0]
            taken = min(count, remaining)
            remaining -= taken
            last_arrived = arrived
            if taken == count:
                self.arrivals.pop(0)
            else:
                self.arrivals[0] = (count - taken, arrived)
        return out, last_arrived

    def until(self, marker, limit):
        while marker not in self.buffer:
            if len(self.buffer) > limit and marker not in self.buffer:
                raise SmokeError("response_header_limit")
            if not self._recv():
                raise SmokeError("truncated_response")
        index = self.buffer.index(marker) + len(marker)
        if index > limit:
            raise SmokeError("response_header_limit")
        return self._consume(index)[0]

    def exact(self, length):
        while len(self.buffer) < length:
            if not self._recv():
                raise SmokeError("truncated_response")
        return self._consume(length)[0]

    def some(self, maximum=4096):
        if not self.buffer:
            self._recv()
        if not self.buffer:
            return b"", None
        return self._consume(min(maximum, len(self.buffer), self.arrivals[0][0]))


def _body_chunks(reader, headers):
    transfer = headers.get("transfer-encoding", "").lower()
    if transfer == "chunked":
        while True:
            line = reader.until(b"\r\n", 128)[:-2]
            digits = line.split(b";", 1)[0]
            if not digits or any(byte not in b"0123456789abcdefABCDEF" for byte in digits):
                raise SmokeError("malformed_chunk_size")
            try:
                size = int(digits, 16)
            except ValueError as exc:
                raise SmokeError("malformed_chunk_size") from exc
            if size < 0 or size > MAX_RESPONSE:
                raise SmokeError("response_body_limit")
            if size == 0:
                if reader.exact(2) != b"\r\n":
                    raise SmokeError("malformed_chunk_end")
                return
            remaining = size
            while remaining:
                part, arrived = reader.some(min(remaining, 4096))
                if not part:
                    raise SmokeError("truncated_response")
                remaining -= len(part)
                yield part, arrived
            if reader.exact(2) != b"\r\n":
                raise SmokeError("malformed_chunk_end")
    elif "content-length" in headers:
        digits = headers["content-length"]
        if not digits or not digits.isascii() or not digits.isdecimal():
            raise SmokeError("malformed_content_length")
        try:
            remaining = int(digits)
        except ValueError as exc:
            raise SmokeError("malformed_content_length") from exc
        if remaining < 0 or remaining > MAX_RESPONSE:
            raise SmokeError("response_body_limit")
        while remaining:
            part, arrived = reader.some(min(remaining, 4096))
            if not part:
                raise SmokeError("truncated_response")
            remaining -= len(part)
            yield part, arrived
    else:
        while True:
            part, arrived = reader.some()
            if not part:
                return
            yield part, arrived


def _exchange(method, path, body, key, deadline, cancel, *,
              host=None, port=None, request_limit=None):
    if host is not None and host != "127.0.0.1":
        raise SmokeError("invalid_host")
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise SmokeError("invalid_port")
    if request_limit is not None and (type(request_limit) is not int or not 1 <= request_limit <= 262144):
        raise SmokeError("invalid_request_limit")
    host = HOST if host is None else host
    port = PORT if port is None else port
    request_limit = MAX_REQUEST if request_limit is None else request_limit
    if not key or any(ch.isspace() for ch in key) or "\r" in key or "\n" in key:
        raise SmokeError("invalid_private_key")
    if body is not None and len(body) > request_limit:
        raise SmokeError("request_body_limit")
    _check(deadline, cancel)
    headers = [f"{method} {path} HTTP/1.1", f"Host: {host}:{port}",
               f"Authorization: Bearer {key}", "Connection: close",
               "Accept: application/json, text/event-stream"]
    if body is not None:
        headers += ["Content-Type: application/json", f"Content-Length: {len(body)}"]
    wire = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + (body or b"")
    submitted = time.monotonic()
    reader = None
    connected = False
    parts, status, response_headers = [], None, {}
    try:
        with socket.create_connection((host, port), timeout=SOCKET_SLICE) as sock:
            connected = True
            sock.settimeout(SOCKET_SLICE)
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
        exc.body_parts, exc.status, exc.headers = parts, status, response_headers
        exc.submitted = submitted
        raise
    except (OSError, UnicodeError) as exc:
        code = ("connect_timeout" if not connected and isinstance(exc, TimeoutError)
                else f"transport_{type(exc).__name__}")
        failure = SmokeError(code, bytes(reader.raw) if reader is not None else b"")
        failure.body_parts, failure.status, failure.headers = parts, status, response_headers
        failure.submitted = submitted
        raise failure from None


def _int_or_none(value):
    return value if type(value) is int and value >= 0 else None


def _number_or_none(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _redact(value, key):
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]")
    if isinstance(value, dict):
        return {_redact(name, key): _redact(item, key) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return value


def _validate_usage(usage, timings, *, max_prompt_tokens=512,
                    max_completion_tokens=64, cache_policy="cold"):
    if (type(max_prompt_tokens) is not int or max_prompt_tokens <= 0
            or type(max_completion_tokens) is not int or max_completion_tokens <= 0
            or cache_policy not in ("cold", "allow")):
        raise ValueError("invalid_usage_limits")
    problems = []
    unavailable = []
    if not isinstance(usage, dict) or not isinstance(timings, dict):
        return {}, ["missing_usage_or_timings"], unavailable
    gufo = usage.get("gufo")
    if not isinstance(gufo, dict):
        if "gufo" in usage:
            problems.append("invalid_usage.gufo")
        gufo = {}
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        if "prompt_tokens_details" in usage:
            problems.append("invalid_usage.prompt_tokens_details")
        details = {}

    def read(source, name, label, parser, optional=False):
        if name not in source:
            if optional:
                unavailable.append(label)
            return None
        value = parser(source[name])
        if value is None:
            problems.append("invalid_" + label)
        return value

    prompt = read(usage, "prompt_tokens", "usage.prompt_tokens", _int_or_none)
    completion = read(usage, "completion_tokens", "usage.completion_tokens", _int_or_none)
    total = read(usage, "total_tokens", "usage.total_tokens", _int_or_none, True)
    prefill = read(gufo, "prefill_tokens", "usage.gufo.prefill_tokens", _int_or_none)
    timing_prefill = read(timings, "prompt_n", "timings.prompt_n", _int_or_none)
    cached = read(details, "cached_tokens", "usage.prompt_tokens_details.cached_tokens", _int_or_none)
    legacy_cached = read(usage, "cached_tokens", "usage.cached_tokens", _int_or_none)
    timing_cached = read(timings, "cache_n", "timings.cache_n", _int_or_none)
    if prefill is None:
        prefill = timing_prefill
    if cached is None:
        cached = legacy_cached if legacy_cached is not None else timing_cached
    if prompt is None or completion is None or prefill is None or cached is None:
        problems.append("required_token_count_unknown")
    if prompt is not None and prompt > max_prompt_tokens:
        problems.append(f"prompt_exceeds_{max_prompt_tokens}")
    if completion is not None and completion > max_completion_tokens:
        problems.append(f"completion_exceeds_{max_completion_tokens}")
    if cache_policy == "cold" and cached is not None and cached != 0:
        problems.append("cache_hit")
    if cache_policy == "cold" and (gufo.get("cache_hit") is True or gufo.get("cache_disk_hit") is True):
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
    predicted = read(timings, "predicted_n", "timings.predicted_n", _int_or_none, True)
    if predicted is not None and completion is not None and predicted != completion:
        problems.append("completion_disagrees")
    return {
        "logical_prompt_tokens": prompt, "new_prefill_tokens": prefill,
        "cached_prompt_tokens": cached, "completion_tokens": completion,
        "total_tokens": total,
        "engine_prefill_ms": read(gufo, "prefill_ms", "usage.gufo.prefill_ms", _number_or_none, True),
        "engine_decode_ms": read(gufo, "decode_ms", "usage.gufo.decode_ms", _number_or_none, True),
        "engine_ttft_ms": read(gufo, "ttft_ms", "usage.gufo.ttft_ms", _number_or_none, True),
        "engine_queue_ms": read(gufo, "queue_ms", "usage.gufo.queue_ms", _number_or_none, True),
        "engine_timing_prompt_ms": read(timings, "prompt_ms", "timings.prompt_ms", _number_or_none, True),
        "engine_timing_predicted_ms": read(timings, "predicted_ms", "timings.predicted_ms", _number_or_none, True),
        "engine_predicted_tokens": predicted,
        "draft_tokens": read(usage, "draft_tokens", "usage.draft_tokens", _int_or_none, True),
        "draft_tokens_accepted": read(usage, "draft_tokens_accepted", "usage.draft_tokens_accepted", _int_or_none, True),
    }, list(dict.fromkeys(problems)), unavailable


def _strict_json(text):
    def unique_object(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("duplicate_json_key")
            result[name] = value
        return result

    def finite_float(number):
        value = float(number)
        if not math.isfinite(value):
            raise ValueError("nonfinite_json_number")
        return value

    def reject_constant(_):
        raise ValueError("nonfinite_json_number")

    return json.loads(text, parse_float=finite_float, parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


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


def _merge_tool_calls(calls, tools, *, streaming=True):
    """Accumulate protocol fragments without interpreting or executing arguments."""
    if not isinstance(calls, list):
        raise SmokeError("malformed_tool_calls")
    for position, call in enumerate(calls):
        if not isinstance(call, dict):
            raise SmokeError("malformed_tool_calls")
        index = call.get("index") if streaming else position
        if type(index) is not int or index < 0:
            raise SmokeError("malformed_tool_index")
        tool = tools.setdefault(index, {"index": index, "function": {"name": "", "arguments": ""}})
        for field in ("id", "type"):
            if field in call:
                value = call[field]
                if (not isinstance(value, str) or not value
                        or (field == "type" and value != "function")
                        or (field in tool and tool[field] != value)):
                    raise SmokeError("conflicting_or_bad_tool_" + field)
                tool[field] = value
        if "function" in call:
            function = call["function"]
            if not isinstance(function, dict) or any(key not in ("name", "arguments") for key in function):
                raise SmokeError("malformed_tool_function")
            for field, value in function.items():
                if not isinstance(value, str):
                    raise SmokeError("malformed_tool_function")
                tool["function"][field] += value


def parse_sse_response(parts, submitted, *, path="/v1/chat/completions"):
    pending = bytearray()
    content = []
    reasoning, tools, models = [], {}, []
    first_visible = None
    first_tool = None
    terminal = None
    usage = None
    timings = None
    done = False
    for part, arrived in parts:
        pending.extend(part)
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
            if "model" in event:
                if not isinstance(event["model"], str) or not event["model"]:
                    raise SmokeError("malformed_response_model")
                models.append(event["model"])
            choices = event.get("choices")
            if not isinstance(choices, list):
                raise SmokeError("malformed_sse_choices")
            if choices:
                if len(choices) != 1 or not isinstance(choices[0], dict):
                    raise SmokeError("malformed_sse_choices")
                choice = choices[0]
                if "index" in choice and (type(choice["index"]) is not int or choice["index"] != 0):
                    raise SmokeError("malformed_sse_choices")
                if terminal is not None:
                    raise SmokeError("duplicate_or_bad_terminal")
                delta = ({"content": choice.get("text")} if path == "/v1/completions"
                         else choice.get("delta", {}))
                if not isinstance(delta, dict):
                    raise SmokeError("malformed_sse_delta")
                visible = delta.get("content")
                if visible is not None:
                    if not isinstance(visible, str):
                        raise SmokeError("malformed_sse_delta")
                    if visible and first_visible is None:
                        first_visible = 1000 * (arrived - submitted)
                    content.append(visible)
                thought = delta.get("reasoning_content")
                if thought is not None:
                    if not isinstance(thought, str):
                        raise SmokeError("malformed_sse_delta")
                    reasoning.append(thought)
                if "tool_calls" in delta:
                    _merge_tool_calls(delta["tool_calls"], tools)
                    if delta["tool_calls"] and first_tool is None:
                        first_tool = 1000 * (arrived - submitted)
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
    if bytes(pending).strip() or not done or terminal is None or usage is None:
        raise SmokeError("incomplete_sse")
    useful = [value for value in (first_visible, first_tool) if value is not None]
    return {"visible_answer": "".join(content), "reasoning_content": "".join(reasoning),
            "first_visible_content_ms": first_visible, "first_tool_call_ms": first_tool,
            "first_useful_output_ms": min(useful) if useful else None,
            "finish_reason": terminal, "tool_calls": [tools[i] for i in sorted(tools)],
            "usage": usage, "timings": {} if timings is None else timings,
            "observed_models": models}


def _parse_sse(parts, submitted):
    result = parse_sse_response(parts, submitted)
    return tuple(result[name] for name in ("visible_answer", "first_visible_content_ms",
                                           "finish_reason", "usage", "timings"))


class SmokeTask:
    def __init__(self, cancel):
        self.done = threading.Event()
        self.cancel = cancel
        self.result = None


def start_smoke(*, api_key: str, startup_deadline: float,
                lifetime_deadline: float, cancel: threading.Event | None = None) -> SmokeTask:
    if (not isinstance(api_key, str) or not api_key or len(api_key) > 256
            or not api_key.isascii() or any(c.isspace() for c in api_key)):
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
                  "ready_polls": 0, "ready_connect_timeouts": 0,
                  "timestamps": {"worker_started_monotonic": time.monotonic()}}
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
                    if exc.code in ("transport_ConnectionRefusedError", "connect_timeout"):
                        if exc.code == "connect_timeout":
                            result["ready_connect_timeouts"] += 1
                        task.cancel.wait(min(2, max(0, ready_deadline-time.monotonic())))
                        continue
                    raise
                _capture(result, path, status, body)
                response = _json_object(body)
                if (status == 503 and isinstance(response.get("error"), dict)
                        and response["error"].get("code") == "not_ready"):
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
            if (not isinstance(models, list) or len(models) != 1
                    or not isinstance(models[0], dict) or models[0].get("id") != MODEL):
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
            metrics, errors, unavailable = _validate_usage(usage, timings)
            metrics["first_visible_content_ms"] = first_ms
            metrics["http_duration_ms"] = result["metrics"]["http_duration_ms"]
            result["metrics"] = metrics
            result.update(visible_answer=visible, finish_reason=reason,
                          usage=usage, timings=timings, validation_errors=errors,
                          unavailable_metrics=unavailable)
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
            result["error"] = "unexpected_" + type(exc).__name__
        finally:
            result["timestamps"]["worker_finished_monotonic"] = time.monotonic()
            task.result = _redact(result, api_key)
            task.done.set()

    threading.Thread(target=work, daemon=True, name="gufo-smoke-http").start()
    return task
