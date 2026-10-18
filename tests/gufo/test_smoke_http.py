import json
import inspect
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from gufo_control import smoke_http


API_KEY = "private-test-key"


def sse(value):
    return b"data: " + json.dumps(value, allow_nan=False).encode("utf-8") + b"\n\n"


def valid_events(**overrides):
    usage = {
        "prompt_tokens": 20,
        "completion_tokens": 1,
        "total_tokens": 21,
        "prompt_tokens_details": {"cached_tokens": 0},
        "gufo": {"prefill_tokens": 20, "cache_hit": False, "ttft_ms": 12.5,
                 "prefill_ms": 5.0, "decode_ms": 7.5},
    }
    timings = {"prompt_n": 20, "cache_n": 0, "predicted_n": 1,
               "prompt_ms": 5.0, "predicted_ms": 7.5}
    usage.update(overrides.pop("usage", {}))
    timings.update(overrides.pop("timings", {}))
    answer = overrides.pop("answer", "4")
    terminal = overrides.pop("terminal", "stop")
    events = [
        {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": answer}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": terminal}], "timings": timings},
        {"choices": [], "usage": usage, "timings": timings},
    ]
    if overrides.get("reasoning"):
        events.insert(1, {"choices": [{"delta": {"reasoning_content": "thinking"},
                                        "finish_reason": None}]})
    return b"".join(sse(event) for event in events) + b"data: [DONE]\n\n"


class TimedSocket:
    def __init__(self, receives, clock):
        self.receives, self.clock = iter(receives), clock

    def recv(self, _):
        arrived, data = next(self.receives, (self.clock["now"], b""))
        self.clock["now"] = arrived
        return data


def timed_body_parts(receives):
    clock = {"now": 0.0}
    with patch.object(smoke_http.time, "monotonic", side_effect=lambda: clock["now"]):
        # _Reader binds its default clock at import time. Pass the simulated
        # receive clock explicitly so arrival timestamps share one timeline.
        reader = smoke_http._Reader(TimedSocket(receives, clock), 10.0,
                                    threading.Event(), clock=lambda: clock["now"])
        head = reader.until(b"\r\n\r\n", 16_384)
        headers = {name.lower(): value.strip() for name, value in
                   (line.split(":", 1) for line in head.decode("ascii").split("\r\n")[1:-2])}
        parts = list(smoke_http._body_chunks(reader, headers))
        visible = smoke_http._parse_sse(parts, 0.0)[1]
    return visible, parts


class Handler(BaseHTTPRequestHandler):
    calls = []
    ready_polls = 0
    config = {}

    def log_message(self, *_):
        pass

    def handle_error(self, request, client_address):
        pass

    def _reply(self, status, body, content_type="application/json", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if not self.config.get("close_delimited"):
            self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            if body:
                self.wfile.write(body)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self.calls.append(("GET", self.path, self.headers.get("Authorization"), None))
        if self.config.get("unauthorized") == self.path:
            return self._reply(401, b'{"error":{"code":"unauthorized"}}')
        if self.path == "/ready":
            type(self).ready_polls += 1
            if self.config.get("ready_wrong_model"):
                return self._reply(200, b'{"status":"ready","model":"other"}')
            retry = self.config.get("ready_503", 0)
            if type(self).ready_polls <= retry:
                return self._reply(503, b'{"error":{"code":"not_ready"}}')
            return self._reply(200, b'{"status":"ready","model":"gufo-flash-next"}')
        if self.path == "/v1/models":
            if self.config.get("models_wrong"):
                return self._reply(200, b'{"data":[{"id":"other"}]}')
            return self._reply(200, b'{"data":[{"id":"gufo-flash-next"}]}')
        return self._reply(404, b'{"error":{"code":"not_found"}}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        mode = self.config.get("post_mode")
        if self.config.get("unauthorized") == self.path:
            return self._reply(401, b'{"error":{"code":"unauthorized"}}')
        if mode == "http_400":
            return self._reply(400, b'{"error":"unsupported field"}')
        if mode == "chunked":
            data = self.config.get("body", valid_events())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            for name, value in self.config.get("headers", {}).items():
                self.send_header(name, value)
            self.end_headers()
            try:
                for index in range(0, len(data), 37):
                    block = data[index:index + 37]
                    self.wfile.write(f"{len(block):X};x=y\r\n".encode() + block + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        if mode == "stalled":
            data = b"data: {\"choices\":[]}" + b" " * 1024
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data) + 100))
            self.end_headers()
            try:
                self.wfile.write(data)
                self.wfile.flush()
                self.config["stall_started"].set()
                self.config["release_stall"].wait(3)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        if mode == "trickle":
            data = self.config.get("body", valid_events())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                for byte in data:
                    self.wfile.write(bytes((byte,)))
                    self.wfile.flush()
                    time.sleep(0.01)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            return
        if mode == "close_delimited":
            self.config["close_delimited"] = True
        data = self.config.get("body", valid_events())
        if mode == "oversize":
            data = b"x" * (smoke_http.MAX_RESPONSE + 1)
        if mode == "chunked_unknown":
            return self._reply(200, data, "text/event-stream",
                               {"Transfer-Encoding": "gzip"})
        if mode == "framing_conflict":
            return self._reply(200, data, "text/event-stream",
                               {"Transfer-Encoding": "chunked"})
        if mode == "bad_header":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "gzip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._reply(200, data, "text/event-stream")


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


class FastWaitEvent(threading.Event):
    def wait(self, timeout=None):
        return self.is_set()


class SmokeHttpTests(unittest.TestCase):
    def setUp(self):
        Handler.calls, Handler.ready_polls, Handler.config = [], 0, {}
        self.server = QuietThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.patch_port = patch.object(smoke_http, "PORT", self.server.server_port)
        self.patch_port.start()
        self.addCleanup(self._cleanup_server)

    def _cleanup_server(self):
        Handler.config.get("release_stall", threading.Event()).set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.patch_port.stop()

    def run_smoke(self, *, config=None, startup=1.0, lifetime=2.0, cancel=None):
        Handler.config = {"ready_503": 0} if config is None else config
        now = time.monotonic()
        task = smoke_http.start_smoke(api_key=API_KEY, startup_deadline=now + startup,
                                      lifetime_deadline=now + lifetime, cancel=cancel)
        self.assertTrue(task.done.wait(lifetime + 1), "worker did not finish within deadline")
        result = task.result
        json.dumps(result, allow_nan=False)
        self.assertNotIn(API_KEY, json.dumps(result, allow_nan=False))
        posts = [call for call in Handler.calls if call[0] == "POST"]
        self.assertLessEqual(len(posts), 1)
        for call in Handler.calls:
            self.assertEqual(call[2], f"Bearer {API_KEY}")
        return task, result, posts

    def test_one_authenticated_completion_and_metrics(self):
        task, result, posts = self.run_smoke(config={"ready_503": 1}, startup=5, lifetime=8)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["ready_polls"], 2)
        self.assertEqual([call[1] for call in Handler.calls],
                         ["/ready", "/ready", "/v1/models", "/v1/chat/completions"])
        self.assertEqual(len(posts), 1)
        self.assertLessEqual(len(posts[0][3]), 16_384)
        self.assertEqual(json.loads(posts[0][3]), smoke_http.REQUEST)
        self.assertEqual(result["metrics"]["logical_prompt_tokens"], 20)
        self.assertEqual(result["metrics"]["new_prefill_tokens"], 20)
        self.assertEqual(result["metrics"]["completion_tokens"], 1)
        self.assertGreaterEqual(result["metrics"]["first_visible_content_ms"], 0)
        self.assertGreaterEqual(result["metrics"]["http_duration_ms"],
                                result["metrics"]["first_visible_content_ms"])
        self.assertNotEqual(result["metrics"]["engine_ttft_ms"],
                            result["metrics"]["first_visible_content_ms"])
        self.assertEqual(result["metrics"]["engine_ttft_ms"], 12.5)
        self.assertIs(task.cancel, task.cancel)

    def test_connect_timeouts_wait_for_real_ready_then_single_models_and_post(self):
        actual_connect = socket.create_connection
        for timeouts in (1, 2):
            with self.subTest(timeouts=timeouts):
                Handler.calls, Handler.ready_polls = [], 0
                connects = []

                def connect(*args, **kwargs):
                    connects.append(args[0])
                    if len(connects) <= timeouts:
                        raise TimeoutError("listener still starting")
                    return actual_connect(*args, **kwargs)

                with patch.object(smoke_http.socket, "create_connection", side_effect=connect):
                    _, result, posts = self.run_smoke(cancel=FastWaitEvent())
                self.assertTrue(result["success"], result)
                self.assertEqual(result["ready_connect_timeouts"], timeouts)
                self.assertEqual(result["ready_polls"], timeouts + 1)
                self.assertEqual([call[1] for call in Handler.calls],
                                 ["/ready", "/v1/models", "/v1/chat/completions"])
                self.assertEqual(len(posts), 1)

    def test_repeated_ready_connect_timeouts_obey_deadline_and_poll_cap(self):
        connects = []

        def connect(*args, **kwargs):
            connects.append(args[0])
            raise TimeoutError("listener still starting")

        with patch.object(smoke_http.socket, "create_connection", side_effect=connect):
            _, expired, posts = self.run_smoke(startup=0.05, lifetime=1)
        self.assertEqual(expired["error"], "deadline_exceeded")
        self.assertEqual(expired["ready_connect_timeouts"], expired["ready_polls"])
        self.assertEqual(posts, [])
        self.assertEqual(Handler.calls, [])

        connects.clear()
        with patch.object(smoke_http, "MAX_READY_POLLS", 2), patch.object(
                smoke_http.socket, "create_connection", side_effect=connect):
            _, capped, posts = self.run_smoke(startup=1, lifetime=2,
                                              cancel=FastWaitEvent())
        self.assertEqual(capped["error"], "ready_poll_limit")
        self.assertEqual(capped["ready_polls"], 2)
        self.assertEqual(capped["ready_connect_timeouts"], 2)
        self.assertEqual(posts, [])
        self.assertEqual(len(connects), 2)

    def test_ready_connect_timeout_cancellation_stops_before_post(self):
        class CancelOnWait(FastWaitEvent):
            def wait(self, timeout=None):
                self.set()
                return True

        with patch.object(smoke_http.socket, "create_connection",
                          side_effect=TimeoutError("listener still starting")) as connect:
            _, result, posts = self.run_smoke(cancel=CancelOnWait())
        self.assertEqual(result["error"], "cancelled")
        self.assertEqual(result["ready_connect_timeouts"], 1)
        self.assertEqual(result["ready_polls"], 1)
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(posts, [])

    def test_models_connect_timeout_is_fatal_without_post(self):
        actual_connect = socket.create_connection
        connects = []

        def connect(*args, **kwargs):
            connects.append(args[0])
            if len(connects) == 2:
                raise TimeoutError("models connect timeout")
            return actual_connect(*args, **kwargs)

        with patch.object(smoke_http.socket, "create_connection", side_effect=connect):
            _, result, posts = self.run_smoke()
        self.assertEqual(result["error"], "connect_timeout")
        self.assertEqual(result["ready_connect_timeouts"], 0)
        self.assertFalse(result["post_attempted"])
        self.assertEqual(len(connects), 2)
        self.assertEqual([call[1] for call in Handler.calls], ["/ready"])
        self.assertEqual(posts, [])

    def test_post_connect_timeout_consumes_one_attempt_without_retry(self):
        actual_connect = socket.create_connection
        connects = []

        def connect(*args, **kwargs):
            connects.append(args[0])
            if len(connects) == 3:
                raise TimeoutError("post connect timeout")
            return actual_connect(*args, **kwargs)

        with patch.object(smoke_http.socket, "create_connection", side_effect=connect):
            _, result, posts = self.run_smoke()
        self.assertEqual(result["error"], "connect_timeout")
        self.assertTrue(result["post_attempted"])
        self.assertEqual(result["ready_connect_timeouts"], 0)
        self.assertEqual(len(connects), 3)
        self.assertEqual([call[1] for call in Handler.calls], ["/ready", "/v1/models"])
        self.assertEqual(posts, [])

    def test_wrong_ready_model_stops_before_model_list_or_post(self):
        _, result, posts = self.run_smoke(config={"ready_wrong_model": True})
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "wrong_ready_model")
        self.assertEqual(posts, [])

    def test_wrong_model_list_stops_before_post(self):
        _, result, posts = self.run_smoke(config={"models_wrong": True})
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "wrong_models_identity")
        self.assertEqual(posts, [])

    def test_unauthorized_route_fails_without_replaying_post(self):
        for route in ("/ready", "/v1/models", "/v1/chat/completions"):
            with self.subTest(route=route):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"unauthorized": route})
                self.assertFalse(result["success"])
                self.assertEqual(len(posts), int(route == "/v1/chat/completions"))
                self.assertEqual(result["error"], "ready_http_401" if route == "/ready" else
                                 "models_http_401" if route == "/v1/models" else "completion_http_401")

    def test_http_400_preserves_raw_response_and_single_post(self):
        _, result, posts = self.run_smoke(config={"post_mode": "http_400"})
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "completion_http_400")
        self.assertEqual(len(posts), 1)
        self.assertIn("unsupported field", result["responses"][-1]["raw_response"])

    def test_wrong_answer_and_length_finish_are_rejected(self):
        for body, error in ((valid_events(answer="5"), "wrong_answer"),
                            (valid_events(terminal="length"), "incomplete_finish")):
            with self.subTest(error=error):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"body": body})
                self.assertFalse(result["success"])
                self.assertEqual(len(posts), 1)
                self.assertIn(error, result["validation_errors"])

    def test_malformed_sse_missing_done_and_missing_terminal_fail(self):
        variants = (b"data: {broken}\n\ndata: [DONE]\n\n",
                    valid_events().replace(b"data: [DONE]\n\n", b""),
                    b"data: {\"choices\":[],\"usage\":{},\"timings\":{}}\n\ndata: [DONE]\n\n")
        for body in variants:
            with self.subTest(body=body[:40]):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"body": body})
                self.assertFalse(result["success"])
                self.assertEqual(len(posts), 1)
                self.assertTrue(result["responses"][-1]["raw_response"])

    def test_sse_protocol_errors_and_missing_usage_fail(self):
        invalid_utf8 = b"data: {\"choices\":[]}\xff\n\ndata: [DONE]\n\n"
        server_error = sse({"error": {"message": "failed"}}) + b"data: [DONE]\n\n"
        missing_usage = (sse({"choices": [{"delta": {"content": "4"},
                                               "finish_reason": None}]})
                         + sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                "timings": {}}) + b"data: [DONE]\n\n")
        trailing = valid_events() + b"data: {\"unfinished\": true}"
        after_done = valid_events() + sse({"choices": []})
        for body in (invalid_utf8, server_error, missing_usage, trailing, after_done):
            with self.subTest(body=body[:50]):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"body": body})
                self.assertFalse(result["success"])
                self.assertEqual(len(posts), 1)
                self.assertTrue(result["responses"][-1]["raw_response"])

    def test_multiple_conflicting_usage_objects_are_rejected(self):
        body = valid_events() + sse({"choices": [], "usage": {"prompt_tokens": 1}})
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertFalse(result["success"])
        self.assertEqual(len(posts), 1)

    def test_cache_hit_flags_and_inconsistent_token_totals_fail(self):
        changes = [
            {"usage": {"gufo": {"cache_hit": True}}},
            {"usage": {"total_tokens": 22}},
            {"usage": {"prompt_tokens": 21}},
        ]
        for change in changes:
            with self.subTest(change=change):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"body": valid_events(**change)})
                self.assertFalse(result["success"])
                self.assertTrue(result["validation_errors"])
                self.assertEqual(len(posts), 1)

    def test_response_event_count_is_not_used_as_token_count(self):
        body = b"".join(sse({"choices": [{"delta": {"content": "4"},
                                         "finish_reason": None}]}) for _ in range(8))
        body += sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                     "timings": {"prompt_n": 20, "cache_n": 0, "predicted_n": 1}})
        body += sse({"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 1,
                                                "total_tokens": 21,
                                                "prompt_tokens_details": {"cached_tokens": 0},
                                                "gufo": {"prefill_tokens": 20}},
                     "timings": {"prompt_n": 20, "cache_n": 0, "predicted_n": 1}})
        body += b"data: [DONE]\n\n"
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertFalse(result["success"])
        self.assertIn("wrong_answer", result["validation_errors"])
        self.assertEqual(result["metrics"]["completion_tokens"], 1)
        self.assertEqual(len(posts), 1)

    def test_usage_validation_rejects_missing_contradictory_cache_and_limits(self):
        cases = [
            {"usage": {"prompt_tokens": None}},
            {"usage": {"prompt_tokens": 21}},
            {"usage": {"gufo": {"prefill_tokens": 19}}},
            {"usage": {"prompt_tokens_details": {"cached_tokens": 1}}},
            {"usage": {"prompt_tokens": 513, "total_tokens": 514}},
            {"usage": {"completion_tokens": 65, "total_tokens": 85}},
            {"timings": {"predicted_n": 2}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"body": valid_events(**changes)})
                self.assertFalse(result["success"])
                self.assertEqual(result["error"], "validation_failed")
                self.assertTrue(result["validation_errors"])
                self.assertEqual(len(posts), 1)

    def test_chunked_sse_reasoning_is_not_visible_content(self):
        _, result, posts = self.run_smoke(config={"post_mode": "chunked",
                                                   "body": valid_events(reasoning=True)})
        self.assertTrue(result["success"], result)
        self.assertEqual(len(posts), 1)
        self.assertEqual(result["visible_answer"], "4")

    def test_nonfinite_json_is_rejected_as_failed_result(self):
        body = (b'data: {"choices":[{"delta":{"content":"4"},"finish_reason":null}],'
                b'"usage":{"prompt_tokens":NaN},"timings":{}}\n\n'
                b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"timings":{}}\n\n'
                b'data: [DONE]\n\n')
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertFalse(result["success"])
        self.assertEqual(len(posts), 1)

    def test_echoed_key_in_json_property_name_is_redacted(self):
        body = valid_events().replace(b'"choices"', b'"private-test-key"', 1)
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertFalse(result["success"])
        serialized = json.dumps(result, allow_nan=False)
        self.assertNotIn(API_KEY, serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertEqual(len(posts), 1)

    def test_unknown_and_conflicting_response_framing_fail(self):
        for mode in ("chunked_unknown", "framing_conflict"):
            with self.subTest(mode=mode):
                Handler.calls, Handler.ready_polls = [], 0
                _, result, posts = self.run_smoke(config={"post_mode": mode})
                self.assertFalse(result["success"])
                self.assertEqual(len(posts), 1)
                self.assertTrue(result["responses"][-1]["raw_response"])

    def test_response_over_one_mib_is_rejected_and_retained(self):
        _, result, posts = self.run_smoke(config={"post_mode": "oversize"}, lifetime=5)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "response_body_limit")
        self.assertEqual(len(posts), 1)
        self.assertLessEqual(len(result["responses"][-1]["raw_response"]),
                             smoke_http.MAX_RESPONSE + 16_384)

    def test_deadline_under_slow_trickle_is_not_extended(self):
        _, result, posts = self.run_smoke(config={"post_mode": "trickle"},
                                           startup=0.5, lifetime=0.5)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "deadline_exceeded")
        self.assertEqual(len(posts), 1)

    def test_cancellation_during_stalled_response_is_prompt_and_preserves_body(self):
        cancel = threading.Event()
        Handler.config = {"ready_503": 0, "post_mode": "stalled", "stall_started": threading.Event(),
                          "release_stall": threading.Event()}
        now = time.monotonic()
        task = smoke_http.start_smoke(api_key=API_KEY, startup_deadline=now + 2,
                                      lifetime_deadline=now + 5, cancel=cancel)
        self.assertTrue(Handler.config["stall_started"].wait(2))
        cancel.set()
        self.assertTrue(task.done.wait(1))
        serialized = json.dumps(task.result, allow_nan=False)
        self.assertNotIn(API_KEY, serialized)
        self.assertFalse(task.result["success"])
        self.assertEqual(task.result["error"], "cancelled")
        self.assertIn("data:", task.result["responses"][-1]["raw_response"])
        self.assertEqual(sum(call[0] == "POST" for call in Handler.calls), 1)

    def test_content_length_visible_time_uses_event_completing_receive(self):
        events = valid_events()
        first = events.index(b"\n\n") + 2
        visible = events.index(b'"content": "4"')
        complete = events.index(b"\n\n", visible) + 2
        head = f"HTTP/1.1 200 OK\r\nContent-Length: {len(events)}\r\n\r\n".encode()
        arrived, parts = timed_body_parts([(0.1, head + events[:complete]),
                                           (0.9, events[complete:])])
        self.assertEqual(arrived, 100.0)
        self.assertEqual(b"".join(part for part, _ in parts), events)
        self.assertLess(first, complete)

    def test_chunked_visible_time_uses_receive_within_chunk(self):
        events = valid_events()
        visible = events.index(b'"content": "4"')
        complete = events.index(b"\n\n", visible) + 2
        head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        chunk_head = f"{len(events):X};x=y\r\n".encode()
        arrived, parts = timed_body_parts([(0.1, head + chunk_head + events[:complete]),
                                           (0.9, events[complete:] + b"\r\n0\r\n\r\n")])
        self.assertEqual(arrived, 100.0)
        self.assertEqual(b"".join(part for part, _ in parts), events)

    def test_framing_rejects_non_digit_content_length_and_chunk_size(self):
        for value in ("+2", "1_0", "-2", "2.0"):
            with self.subTest(content_length=value):
                reader = smoke_http._Reader(TimedSocket([(0.1, b"ok")], {"now": 0}),
                                            time.monotonic() + 1, threading.Event())
                with self.assertRaisesRegex(smoke_http.SmokeError, "malformed_content_length"):
                    list(smoke_http._body_chunks(reader, {"content-length": value}))
        for value in (b"+2", b"0_2", b"-2", b"2.0"):
            with self.subTest(chunk_size=value):
                clock = {"now": 0}
                reader = smoke_http._Reader(TimedSocket([(0.1, value + b";x=y\r\nok\r\n0\r\n\r\n")], clock),
                                            time.monotonic() + 1, threading.Event())
                with self.assertRaisesRegex(smoke_http.SmokeError, "malformed_chunk_size"):
                    list(smoke_http._body_chunks(reader, {"transfer-encoding": "chunked"}))

    def test_supplied_invalid_counters_and_metrics_fail_despite_fallbacks(self):
        cases = [
            ({"gufo": {"prefill_tokens": True}}, {}, "usage.gufo.prefill_tokens"),
            ({"gufo": {"prefill_tokens": -1}}, {}, "usage.gufo.prefill_tokens"),
            ({"prompt_tokens_details": {"cached_tokens": True}}, {}, "usage.prompt_tokens_details.cached_tokens"),
            ({"cached_tokens": -1}, {}, "usage.cached_tokens"),
            ({}, {"prompt_n": True}, "timings.prompt_n"),
            ({}, {"cache_n": -1}, "timings.cache_n"),
            ({"gufo": {"ttft_ms": float("nan")}}, {}, "usage.gufo.ttft_ms"),
            ({"draft_tokens": True}, {}, "usage.draft_tokens"),
            ({}, {"predicted_n": "1"}, "timings.predicted_n"),
        ]
        base_usage = {"prompt_tokens": 20, "completion_tokens": 1,
                      "prompt_tokens_details": {"cached_tokens": 0},
                      "gufo": {"prefill_tokens": 20}}
        base_timings = {"prompt_n": 20, "cache_n": 0, "predicted_n": 1}
        for usage_change, timings_change, field in cases:
            with self.subTest(field=field, value=(usage_change, timings_change)):
                usage = json.loads(json.dumps(base_usage))
                for name, value in usage_change.items():
                    if name in ("gufo", "prompt_tokens_details"):
                        usage[name].update(value)
                    else:
                        usage[name] = value
                metrics, errors, _ = smoke_http._validate_usage(usage, base_timings | timings_change)
                self.assertIn(field, " ".join(errors))
                self.assertTrue(errors)

    def test_absent_optional_metrics_are_nonfatal_diagnostics(self):
        usage = {"prompt_tokens": 20, "completion_tokens": 1,
                 "prompt_tokens_details": {"cached_tokens": 0},
                 "gufo": {"prefill_tokens": 20}}
        timings = {"prompt_n": 20, "cache_n": 0}
        body = (sse({"choices": [{"delta": {"content": "4"}, "finish_reason": None}]})
                + sse({"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": timings})
                + sse({"choices": [], "usage": usage, "timings": timings})
                + b"data: [DONE]\n\n")
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertTrue(result["success"], result)
        self.assertEqual(len(posts), 1)
        self.assertIsNone(result["metrics"]["engine_ttft_ms"])
        self.assertIsNone(result["metrics"]["draft_tokens"])
        self.assertIsNone(result["metrics"]["total_tokens"])
        self.assertIsNone(result["metrics"]["engine_predicted_tokens"])
        self.assertIn("usage.gufo.ttft_ms", result["unavailable_metrics"])
        self.assertIn("usage.draft_tokens", result["unavailable_metrics"])
        self.assertIn("usage.total_tokens", result["unavailable_metrics"])
        self.assertIn("timings.predicted_n", result["unavailable_metrics"])

    def test_missing_timings_container_is_nonfatal_but_supplied_bad_container_fails(self):
        usage = {"prompt_tokens": 20, "completion_tokens": 1,
                 "prompt_tokens_details": {"cached_tokens": 0},
                 "gufo": {"prefill_tokens": 20}}
        body = (sse({"choices": [{"delta": {"content": "4"}, "finish_reason": None}]})
                + sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})
                + sse({"choices": [], "usage": usage})
                + b"data: [DONE]\n\n")
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertTrue(result["success"], result)
        self.assertEqual(len(posts), 1)
        self.assertIsNone(result["metrics"]["engine_timing_prompt_ms"])
        self.assertIsNone(result["metrics"]["engine_timing_predicted_ms"])
        self.assertIn("timings.prompt_ms", result["unavailable_metrics"])

        for bad_timings in (None, []):
            with self.subTest(timings=bad_timings):
                Handler.calls, Handler.ready_polls = [], 0
                malformed = (sse({"choices": [{"delta": {"content": "4"},
                                                  "finish_reason": None}]})
                             + sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                    "timings": bad_timings})
                             + sse({"choices": [], "usage": usage})
                             + b"data: [DONE]\n\n")
                _, bad_result, bad_posts = self.run_smoke(config={"body": malformed})
                self.assertFalse(bad_result["success"])
                self.assertEqual(bad_result["error"], "conflicting_timings")
                self.assertEqual(len(bad_posts), 1)

    def test_invalid_supplied_prefill_fails_full_smoke_with_valid_fallback(self):
        body = valid_events(usage={"gufo": {"prefill_tokens": True}})
        _, result, posts = self.run_smoke(config={"body": body})
        self.assertEqual(len(posts), 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "validation_failed")
        self.assertIn("invalid_usage.gufo.prefill_tokens", result["validation_errors"])
        self.assertEqual(result["metrics"]["new_prefill_tokens"], 20)

    def test_response_side_close_after_post_is_one_attempt(self):
        # The request reached the handler; closing its response is not a send failure.
        Handler.calls, Handler.ready_polls = [], 0
        original = Handler.do_POST
        def close_response(handler):
            body = handler.rfile.read(int(handler.headers["Content-Length"]))
            Handler.calls.append(("POST", handler.path, handler.headers.get("Authorization"), body))
            handler.connection.close()
        Handler.do_POST = close_response
        try:
            _, result, posts = self.run_smoke(lifetime=1)
        finally:
            Handler.do_POST = original
        self.assertFalse(result["success"])
        self.assertTrue(result["post_attempted"])
        self.assertEqual(len(posts), 1)

    def test_ambiguous_post_send_failure_is_one_attempt(self):
        actual_connect = socket.create_connection
        connects = []
        sends = []

        class FailedSendSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def settimeout(self, _):
                pass

            def sendall(self, wire):
                sends.append(wire)
                raise TimeoutError("ambiguous send")

        def connect(*args, **kwargs):
            connects.append(args[0])
            if len(connects) == 3:
                return FailedSendSocket()
            return actual_connect(*args, **kwargs)

        with patch.object(smoke_http.socket, "create_connection", side_effect=connect):
            _, result, posts = self.run_smoke()
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "transport_TimeoutError")
        self.assertTrue(result["post_attempted"])
        self.assertEqual(len(connects), 3)
        self.assertEqual(len(sends), 1)
        self.assertEqual(len(posts), 0)


class ReusableHelpersTests(unittest.TestCase):
    def test_legacy_sse_text_is_endpoint_aware_and_uses_frame_arrival(self):
        self.assertIn("path", inspect.signature(smoke_http.parse_sse_response).parameters)
        first = sse({"choices": [{"text": "", "finish_reason": None}]})
        visible = sse({"choices": [{"text": "hello", "finish_reason": None}]})
        final = (sse({"choices": [{"text": "!", "finish_reason": "stop"}], "usage": {}})
                 + b"data: [DONE]\n\n")
        parts = [(first + visible[:-1], 10.1), (visible[-1:], 10.25), (final, 10.5)]
        result = smoke_http.parse_sse_response(parts, 10, path="/v1/completions")
        self.assertEqual(result["visible_answer"], "hello!")
        self.assertEqual(result["first_visible_content_ms"], 250)
        self.assertEqual(result["first_useful_output_ms"], 250)
        # Existing chat callers and the smoke wrapper retain chat-only defaults.
        self.assertEqual(smoke_http.parse_sse_response(parts, 10)["visible_answer"], "")
        self.assertEqual(smoke_http._parse_sse(parts, 10)[0], "")
        malformed = sse({"choices": [{"text": 7, "finish_reason": "stop"}], "usage": {}})
        with self.assertRaises(smoke_http.SmokeError):
            smoke_http.parse_sse_response([(malformed + b"data: [DONE]\n\n", 11)],
                                          10, path="/v1/completions")

    def test_exchange_explicit_bounds_are_validated_before_connect(self):
        self.assertIn("port", inspect.signature(smoke_http._exchange).parameters)
        for kwargs in ({"host": "example.com"}, {"port": True}, {"port": 65536},
                       {"request_limit": 262145}, {"request_limit": False}):
            with self.subTest(kwargs=kwargs), patch.object(smoke_http.socket, "create_connection") as connect:
                with self.assertRaises(smoke_http.SmokeError):
                    smoke_http._exchange("POST", "/v1/completions", b"{}", API_KEY,
                                         time.monotonic() + 1, threading.Event(), **kwargs)
                connect.assert_not_called()

    def test_custom_usage_limits_and_cache_policy(self):
        self.assertIn("cache_policy", inspect.signature(smoke_http._validate_usage).parameters)
        usage = {"prompt_tokens": 2048, "completion_tokens": 256,
                 "gufo": {"prefill_tokens": 2000, "cache_hit": True}, "cached_tokens": 48}
        metrics, errors, _ = smoke_http._validate_usage(usage, {}, max_prompt_tokens=8192,
                                                       max_completion_tokens=256, cache_policy="allow")
        self.assertEqual(errors, [])
        self.assertEqual(metrics["cached_prompt_tokens"], 48)
        _, errors, _ = smoke_http._validate_usage(usage, {}, max_prompt_tokens=2047,
                                                  max_completion_tokens=255)
        self.assertIn("cache_hit", errors)
        self.assertIn("prompt_exceeds_2047", errors)
        self.assertIn("completion_exceeds_255", errors)
        for value in (0, True, 1.5, float("inf")):
            with self.assertRaises(ValueError):
                smoke_http._validate_usage({}, {}, max_prompt_tokens=value)

    def test_rich_sse_retains_reasoning_tools_and_separate_arrival_times(self):
        self.assertTrue(hasattr(smoke_http, "parse_sse_response"))
        events = [
            {"model": "local", "choices": [{"delta": {"reasoning_content": "denke"}}]},
            {"model": "local", "choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call1", "type": "function", "function": {"name": "look", "arguments": "{\"x\":"}}]}}]},
            {"choices": [{"delta": {"content": "ü", "tool_calls": [
                {"index": 0, "function": {"name": "up", "arguments": "1}"}}]}}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1}}]
        parts = []
        for i, event in enumerate(events):
            raw = (b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\r\n\r\n")
            parts.extend((bytes([byte]), 10 + i) for byte in raw)
        parts.append((b"data: [DONE]\r\n\r\n", 14))
        result = smoke_http.parse_sse_response(parts, 10)
        self.assertEqual(result["reasoning_content"], "denke")
        self.assertEqual(result["visible_answer"], "ü")
        self.assertEqual(result["first_tool_call_ms"], 1000)
        self.assertEqual(result["first_useful_output_ms"], 1000)
        self.assertEqual(result["first_visible_content_ms"], 2000)
        self.assertEqual(result["tool_calls"][0]["function"], {"name": "lookup", "arguments": '{"x":1}'})
        self.assertEqual(len(smoke_http._parse_sse(parts, 10)), 5)


if __name__ == "__main__":
    unittest.main()
