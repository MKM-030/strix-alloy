import json
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

    def test_transport_failure_after_post_attempt_never_replays(self):
        # Closing the listening socket after the preflight routes forces a POST send failure.
        Handler.calls, Handler.ready_polls = [], 0
        original = Handler.do_POST
        Handler.do_POST = lambda self: (self.server.shutdown(), self.connection.close())
        try:
            _, result, posts = self.run_smoke(lifetime=1)
        finally:
            Handler.do_POST = original
        self.assertFalse(result["success"])
        self.assertTrue(result["post_attempted"])
        self.assertLessEqual(len(posts), 1)


if __name__ == "__main__":
    unittest.main()
