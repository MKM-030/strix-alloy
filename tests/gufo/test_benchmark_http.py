"""Offline loopback protocol tests; never connect to a model server."""
import base64
import copy
import importlib.util
import json
import threading
import time
import unittest
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from gufo_control import smoke_http

KEY = "private-benchmark-key"


def usage(prompt=2048, output=1, cached=0):
    return {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt + output,
            "cached_tokens": cached, "gufo": {"prefill_tokens": prompt-cached,
            "prefill_ms": 100, "decode_ms": 20, "ttft_ms": 110}}


def response(stream=True, output=1, terminal="stop", model="local", counters=None, timings=None):
    value = {"model": model, "usage": usage(output=output) if counters is None else counters,
             "timings": {} if timings is None else timings,
             "choices": [{"finish_reason": terminal}]}
    if not stream:
        value["choices"][0]["text"] = "answer"
        return json.dumps(value).encode()
    value["choices"][0]["delta"] = {"content": "answer"}
    return b"data: " + json.dumps(value).encode() + b"\n\ndata: [DONE]\n\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        self.server.calls.append((self.path, self.headers.get("Authorization"),
                                 self.rfile.read(int(self.headers["Content-Length"]))))
        cfg = self.server.config
        self.send_response(cfg.get("status", 200))
        self.send_header("Content-Type", cfg.get("content_type", "text/event-stream"))
        self.send_header("X-Echo", KEY)
        body = cfg.get("body", response())
        self.send_header("Content-Length", str(cfg.get("length", len(body))))
        self.end_headers()
        try:
            # Windows monotonic() can have a 15ms clock tick: make wall timing observable.
            time.sleep(.02)
            self.wfile.write(body)
            self.wfile.flush()
            if cfg.get("stall"):
                cfg["started"].set()
                cfg["release"].wait(2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("gufo_control.benchmark_http"), "benchmark module missing")
        from gufo_control import benchmark_http
        self.client = benchmark_http
        self.server.calls = []
        self.server.config = {}

    def call(self, request=None, **kwargs):
        request = request if request is not None else {"model": "local", "messages": [], "max_tokens": 1, "stream": True}
        return self.client.request_once(port=self.server.server_port, api_key=KEY,
                path=kwargs.pop("path", "/v1/chat/completions"), request=request,
                limits=kwargs.pop("limits", self.client.RequestLimits(8192, 256)),
                deadline=kwargs.pop("deadline", time.monotonic()+2), **kwargs)

    def test_actual_sse_call_preserves_sampled_request_and_rates(self):
        request = {"model": "local", "messages": [{"role": "user", "content": "Grüße"}],
                   "max_tokens": 1, "stream": True, "temperature": 1, "top_p": .95,
                   "seed": 1001, "cache_prompt": False, "tools": [], "tool_choice": "auto"}
        original = copy.deepcopy(request)
        result = self.call(request)
        self.assertTrue(result["success"], result)
        self.assertEqual(request, original)
        self.assertEqual(result["request"], request)
        self.assertEqual(len(self.server.calls), 1)
        self.assertEqual(json.loads(self.server.calls[0][2]), request)
        self.assertEqual(result["metrics"]["engine_pp_tokens_per_second"], 20480)
        self.assertEqual(result["metrics"]["engine_tg_tokens_per_second"], 50)
        self.assertAlmostEqual(result["metrics"]["http_pp_tokens_per_second"],
                               2048*1000/result["metrics"]["http_duration_ms"])
        self.assertIsNone(result["metrics"]["common_window_decode_tokens_per_second"])
        self.assertTrue(result["model_matches_request"])
        self.assertNotIn(KEY, json.dumps(result))
        self.assertTrue(result["evidence_redacted"])

    def test_legacy_json_length_and_optional_unknowns(self):
        counters = {"prompt_tokens": 8192, "completion_tokens": 256, "cached_tokens": 0,
                    "gufo": {"prefill_tokens": 8192}}
        self.server.config = {"content_type": "application/json", "body": response(False, 256, "length", counters=counters)}
        result = self.call({"model": "local", "prompt": "x", "max_tokens": 256, "stream": False}, path="/v1/completions")
        self.assertTrue(result["success"], result)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["visible_answer"], "answer")
        for field in ("first_visible_content_ms", "engine_pp_tokens_per_second", "engine_tg_tokens_per_second", "http_pp_tokens_per_second", "mtp_acceptance"):
            self.assertIsNone(result["metrics"][field], field)

    def test_json_chat_tools_and_stop_edge(self):
        obj = json.loads(response(False))
        obj["choices"][0] = {"finish_reason": "stop", "message": {"content": None,
            "reasoning_content": "thinking", "tool_calls": [{"id": "a", "type": "function",
            "function": {"name": "lookup", "arguments": "{"}}]}}
        self.server.config = {"content_type": "application/json", "body": json.dumps(obj).encode()}
        result = self.call({"model": "local", "messages": [], "max_tokens": 1, "stream": False})
        self.assertTrue(result["success"], result)
        self.assertEqual(result["tool_calls"][0]["function"]["arguments"], "{")
        self.assertEqual(result["reasoning_content"], "thinking")

    def test_cold_and_allow_cache(self):
        counters = usage(cached=100)
        counters["gufo"]["cache_hit"] = True
        self.server.config = {"body": response(counters=counters)}
        self.assertFalse(self.call()["success"])
        result = self.call(limits=self.client.RequestLimits(2048, 256, "allow"))
        self.assertTrue(result["success"], result)
        self.assertEqual(result["metrics"]["new_prefill_tokens"], 1948)

    def test_bad_config_never_transports_and_limits_frozen(self):
        for args in ((True, 1), (0, 1), (262145, 1), (1, 8193), (1, float("inf")), (1, 1, "bad"), (1, 1, "cold", False)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.client.RequestLimits(*args)
        limits = self.client.RequestLimits(2048, 256)
        with self.assertRaises(FrozenInstanceError):
            limits.max_prompt_tokens = 4
        base = {"model": "local", "messages": [], "max_tokens": 1, "stream": True}
        for change in ({"model": ""}, {"max_tokens": True}, {"max_tokens": 257}, {"stream": 1},
                       {"messages": "x"}, {"temperature": float("nan")}):
            with self.subTest(change=change):
                self.assertFalse(self.call(base | change)["success"])
        self.assertFalse(self.call(path="http://remote/v1/completions")["success"])
        self.assertFalse(self.call(base | {"messages": ["x"*2000]}, limits=self.client.RequestLimits(2048, 256, request_bytes=100))["success"])
        self.assertEqual(self.server.calls, [])

    def test_inconsistent_counters_invalidate_all_rates_but_keep_elapsed(self):
        cases = [(usage(), {"prompt_n": 2}), (usage(), {"prompt_ms": 99}),
                 (usage() | {"draft_tokens": 1, "draft_tokens_accepted": 2}, {}),
                 (usage() | {"completion_tokens": True}, {}),
                 ({"prompt_tokens": 2048, "completion_tokens": 1, "cached_tokens": 0}, {}),
                 (usage() | {"gufo": []}, {})]
        for counters, timings in cases:
            with self.subTest(counters=counters, timings=timings):
                self.server.config = {"body": response(counters=counters, timings=timings)}
                result = self.call()
                self.assertFalse(result["success"], result)
                self.assertGreater(result["metrics"]["http_duration_ms"], 0)
                for field in ("engine_pp_tokens_per_second", "engine_tg_tokens_per_second", "http_pp_tokens_per_second", "mtp_acceptance"):
                    self.assertIsNone(result["metrics"][field])

    def test_mtp_and_timing_fallback(self):
        for proposed, accepted, expected in ((4, 3, .75), (0, 0, None)):
            counters = usage() | {"draft_tokens": proposed, "draft_tokens_accepted": accepted}
            counters["gufo"] = {"prefill_tokens": 2048}
            self.server.config = {"body": response(counters=counters, timings={"prompt_ms": 200, "predicted_ms": 40})}
            result = self.call()
            self.assertTrue(result["success"], result)
            self.assertEqual(result["metrics"]["mtp_acceptance"], expected)
            self.assertEqual(result["metrics"]["engine_pp_tokens_per_second"], 10240)
            self.assertEqual(result["metrics"]["engine_tg_tokens_per_second"], 25)

    def test_models_terminal_nonfinite_usage_and_tools_fail_structured(self):
        malformed = [response(model="other"), response(terminal=None), response(terminal="error"),
                     response(counters={}), response().replace(b'2048', b'NaN', 1),
                     b'data: {"error":"bad"}\n\ndata: [DONE]\n\n']
        for tool in ({"index": True}, {"index": -1}, {"index": 0, "function": []},
                     {"index": 0, "function": {"arguments": {}}}):
            malformed.append(b'data: '+json.dumps({"choices": [{"delta": {"tool_calls": [tool]}}]}).encode()+b'\n\n'+response())
        for body in malformed:
            with self.subTest(body=body):
                self.server.config = {"body": body}
                self.assertFalse(self.call()["success"])
        obj = json.loads(response(False)); obj.pop("model")
        self.server.config = {"content_type": "application/json", "body": json.dumps(obj).encode()}
        result = self.call({"model": "local", "prompt": "x", "max_tokens": 1, "stream": False}, path="/v1/completions")
        self.assertTrue(result["success"], result)
        self.assertIsNone(result["model_matches_request"])

    def test_errors_caps_no_retry_and_redaction(self):
        for status in (401, 503, 302):
            self.server.calls = []
            self.server.config = {"status": status, "body": KEY.encode()+b'\xff'}
            result = self.call()
            self.assertFalse(result["success"])
            self.assertEqual(result["status"], status)
            self.assertEqual(len(self.server.calls), 1)
            self.assertTrue(result["evidence_redacted"])
            self.assertNotIn(KEY, json.dumps(result))
            raw = base64.b64decode(result["raw_response_base64"])
            self.assertNotIn(KEY.encode(), raw)
            self.assertIn(b'\xff', raw)
        self.server.config = {"body": b"", "length": smoke_http.MAX_RESPONSE+1}
        self.assertEqual(self.call()["error"], "response_body_limit")

    def test_timeout_and_cancel_keep_partial_wire(self):
        for cancelling in (False, True):
            self.server.calls = []
            started, release, cancel = threading.Event(), threading.Event(), threading.Event()
            self.server.config = {"body": KEY.encode(), "length": 1000, "stall": True,
                                  "started": started, "release": release}
            result = []
            worker = threading.Thread(target=lambda: result.append(self.call(cancel=cancel, deadline=time.monotonic()+.35)))
            worker.start(); self.assertTrue(started.wait(1))
            if cancelling:
                cancel.set()
            worker.join(1); release.set()
            self.assertFalse(worker.is_alive())
            self.assertEqual(result[0]["error"], "cancelled" if cancelling else "deadline_exceeded")
            self.assertTrue(result[0]["raw_response"])
            self.assertNotIn(KEY, json.dumps(result[0]))
            self.assertEqual(len(self.server.calls), 1)

    def test_redacts_cross_fragment_bytes_before_base64_and_preserves_boundaries(self):
        body = response().replace(b"answer", KEY.encode())
        cut = body.index(KEY.encode())+7
        parts = [(body[:cut], 1.1), (body[cut:], 1.2)]
        with patch.object(smoke_http, "_exchange", return_value=(200, {"content-type": "text/event-stream"}, body, 1, 1.3, parts)):
            result = self.call()
        evidence = result["body_parts"]
        decoded = [base64.b64decode(part["base64"]) for part in evidence]
        self.assertEqual(list(map(len, decoded)), list(map(len, (body[:cut], body[cut:]))))
        self.assertNotIn(KEY.encode(), b"".join(decoded))
        self.assertIn(b"*"*len(KEY), b"".join(decoded))
        self.assertEqual([part["arrived_monotonic"] for part in evidence], [1.1, 1.2])

    def test_programmer_interrupt_is_not_swallowed(self):
        for error in (KeyboardInterrupt, SystemExit):
            with patch.object(smoke_http, "_exchange", side_effect=error), self.assertRaises(error):
                self.call()

    def test_sanitized_base64_is_not_text_redacted_again(self):
        # This key coincides with the encoding of unrelated bytes; those bytes
        # must remain decodable. Actual key occurrences are removed pre-encoding.
        with patch.object(smoke_http, "_exchange", return_value=(401, {}, b"abc", 1, 2, [(b"abc", 1.5)])):
            result = self.client.request_once(port=self.server.server_port, api_key="YWJj",
                path="/v1/completions", request={"model": "local", "prompt": "x", "max_tokens": 1, "stream": False},
                limits=self.client.RequestLimits(2048, 256), deadline=time.monotonic()+1)
        self.assertEqual(base64.b64decode(result["raw_response_base64"]), b"abc")
        self.assertEqual(base64.b64decode(result["body_parts"][0]["base64"]), b"abc")

    def test_duplicate_json_keys_and_bad_cache_flags_are_failures(self):
        for body in (response().replace(b'"finish_reason": "stop"', b'"finish_reason": "length", "finish_reason": "stop"'),
                     response(counters=usage() | {"gufo": {"prefill_tokens": 2048, "cache_hit": "false"}})):
            self.server.config = {"body": body}
            result = self.call()
            self.assertFalse(result["success"], result)

    def test_terminal_tool_conflicts_and_multiple_choices(self):
        first = {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "a", "type": "function",
                  "function": {"name": "lookup", "arguments": "{"}}]}}]}
        for fragment in ({"index": 0, "id": "b"}, {"index": 0, "type": "other"}):
            second = {"choices": [{"delta": {"tool_calls": [fragment]}}]}
            self.server.config = {"body": b"".join(b"data: "+json.dumps(event).encode()+b"\n\n" for event in (first, second))+response()}
            self.assertFalse(self.call()["success"])
        obj = json.loads(response(False))
        obj["choices"] *= 2
        self.server.config = {"content_type": "application/json", "body": json.dumps(obj).encode()}
        self.assertFalse(self.call({"model": "local", "prompt": "x", "max_tokens": 1, "stream": False}, path="/v1/completions")["success"])

    def test_zero_durations_and_multi_output_are_not_pp1(self):
        counters = usage(output=2)
        counters["gufo"].update(prefill_ms=0, decode_ms=0)
        self.server.config = {"body": response(output=2, counters=counters)}
        result = self.call({"model": "local", "messages": [], "max_tokens": 256, "stream": True})
        self.assertTrue(result["success"], result)
        for field in ("http_pp_tokens_per_second", "engine_pp_tokens_per_second", "engine_tg_tokens_per_second"):
            self.assertIsNone(result["metrics"][field])

    def test_pre_cancel_and_invalid_transport_inputs_send_nothing(self):
        cancel = threading.Event(); cancel.set()
        self.assertEqual(self.call(cancel=cancel)["error"], "cancelled")
        self.assertEqual(self.call(deadline=time.monotonic()-1)["error"], "deadline_exceeded")
        for kwargs in ({"port": True}, {"port": 65536}, {"api_key": "bad\r\nkey"},
                       {"deadline": float("nan")}, {"cancel": object()}, {"limits": {}}):
            options = dict(port=self.server.server_port, api_key=KEY, path="/v1/chat/completions",
                           request={"model": "local", "messages": [], "max_tokens": 1, "stream": True},
                           limits=self.client.RequestLimits(2048, 256), deadline=time.monotonic()+1)
            options.update(kwargs)
            self.assertFalse(self.client.request_once(**options)["success"])
        self.assertEqual(self.server.calls, [])


if __name__ == "__main__":
    unittest.main()
