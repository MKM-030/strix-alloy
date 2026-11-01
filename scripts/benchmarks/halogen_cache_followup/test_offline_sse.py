"""Artificial offline fixtures only. These tests do not measure any model or hardware."""
import copy
import ast
import importlib.util
import json
import pathlib
import sys
import unittest

MODULE = pathlib.Path(__file__).with_name("offline_sse.py")


def api():
    if not MODULE.is_file():
        raise AssertionError("The offline parser has not been implemented.")
    spec = importlib.util.spec_from_file_location("offline_cache_sse", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture(prompt=1000, cached=0, output=128, finish="length", text="Grüße Welt"):
    ledger = {
        "drafter": "mtp", "rounds": 52,
        "head": {"rounds": 50, "drafted": 100, "accepted": 60},
        "lookup": {"rounds": 2, "drafted": 4, "accepted": 2},
        "grammar": {"rounds": 0, "drafted": 0, "accepted": 0},
    }
    timings = {
        "prompt_n": prompt-cached, "cache_n": cached, "predicted_n": output,
        "prompt_ms": 500.0, "predicted_ms": 2000.0,
        "prompt_per_second": 2000.0, "predicted_per_second": 64.0,
        "draft_n": 104, "draft_n_accepted": 62, "speculation": ledger,
    }
    usage = {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt+output}
    if cached:
        usage["prompt_tokens_details"] = {"cached_tokens": cached}
    frames = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}], "usage": None},
        {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}], "usage": None},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "timings": copy.deepcopy(timings)},
        {"choices": [], "usage": usage, "timings": copy.deepcopy(timings)},
        "[DONE]",
    ]
    for frame in frames:
        if isinstance(frame, dict):
            frame.update({"id": "artificial-request-1", "model": "artificial-model",
                          "created": 1234, "object": "chat.completion.chunk"})
    return frames


def wire(frame, newline="\n"):
    payload = frame if isinstance(frame, str) else json.dumps(frame, ensure_ascii=False, allow_nan=True)
    return ("data: " + payload + newline + newline).encode("utf-8")


class OfflineStreamTests(unittest.TestCase):
    def setUp(self):
        self.m = api()

    def parse(self, frames=None, expected=1000, split=False):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000,
                                         expected_prompt_tokens=expected, max_output_tokens=128)
        for frame, tick in zip(frames or fixture(), [1100, 1200, 1300, 1400, 1500]):
            raw = wire(frame, "\r\n" if split else "\n")
            if split:
                for byte in raw:
                    stream.feed(bytes([byte]), tick)
            else:
                stream.feed(raw, tick)
        return stream.finish()

    def rejects(self, frames, pattern=None):
        with self.assertRaises(self.m.ProtocolError) as caught:
            self.parse(frames)
        if pattern:
            self.assertRegex(str(caught.exception), pattern)

    def test_artificial_full_accounting_and_latency(self):
        result = self.parse()
        self.assertEqual((result.prompt_tokens, result.cached_tokens, result.processed_tokens), (1000, 0, 1000))
        self.assertEqual(result.output_tokens, 128)
        self.assertAlmostEqual(result.first_content_seconds, .2)
        self.assertAlmostEqual(result.end_to_end_seconds, .5)
        self.assertEqual(result.content, "Grüße Welt")
        self.assertEqual((result.response_id, result.model, result.created),
                         ("artificial-request-1", "artificial-model", 1234))
        self.assertEqual((result.speculation.head.accepted, result.speculation.head.drafted), (60, 100))
        self.assertEqual((result.speculation.lookup.accepted, result.speculation.lookup.drafted), (2, 4))
        self.assertEqual((result.speculation.accepted, result.speculation.drafted), (62, 104))
        data = result.as_dict()
        self.assertEqual(data["evidence_kind"], "artificial-fixture")
        self.assertFalse(data["qualifies_hardware_measurement"])
        self.assertTrue(data["native_phase_rates_are_observations_only"])
        self.assertNotIn("effective_prefill_tok_s", data)

    def test_split_utf8_and_crlf_have_same_content_and_stamp(self):
        self.assertEqual(self.parse(split=True).as_dict(), self.parse().as_dict())

    def test_multiline_data_and_comments(self):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        frames = fixture()
        raw = json.dumps(frames[0])
        split = raw.index(",")
        stream.feed((": artificial fixture\nid: synthetic-1\nevent: message\n"
                     "data: " + raw[:split+1] + "\ndata: " + raw[split+1:] + "\n\n").encode(), 1100)
        for frame, tick in zip(frames[1:], [1200, 1300, 1400, 1500]):
            stream.feed(wire(frame), tick)
        self.assertAlmostEqual(stream.finish().first_content_seconds, .2)

    def test_positive_early_stop_output_is_allowed(self):
        result = self.parse(fixture(output=17, finish="stop"))
        self.assertEqual(result.output_tokens, 17)
        self.assertEqual(result.finish_reason, "stop")

    def test_terminal_stamp_is_event_completion_not_first_done_byte(self):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        for frame, tick in zip(fixture()[:-1], [1100, 1200, 1300, 1400]):
            stream.feed(wire(frame), tick)
        stream.feed(b"data: [DONE]\n", 1490)
        stream.feed(b"\n", 1500)
        self.assertAlmostEqual(stream.finish().end_to_end_seconds, .5)

    def test_nonempty_whitespace_content_counts_but_empty_role_does_not(self):
        self.assertEqual(self.parse(fixture(text=" ")).first_content_seconds, .2)

    def test_empty_content_cannot_qualify(self):
        self.rejects(fixture(text=""), "content")

    def test_reasoning_or_tools_rejected(self):
        for delta in [{"reasoning_content": "private reasoning"}, {"tool_calls": []}, {"function_call": {}}]:
            frames = fixture()
            frames[1]["choices"][0]["delta"] = delta
            with self.subTest(delta=delta):
                self.rejects(frames)

    def test_error_frame_followed_by_done_is_failure(self):
        frames = fixture()
        frames[1] = {"error": {"message": "synthetic failure", "type": "fixture"}}
        self.rejects(frames, "error")

    def test_duplicate_done_rejected(self):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        stream.feed(b"".join(wire(x) for x in fixture()), 1500)
        with self.assertRaisesRegex(self.m.ProtocolError, "DONE"):
            stream.feed(wire("[DONE]"), 1501)

    def test_missing_done_and_unterminated_events_rejected(self):
        for payload in [b"".join(wire(x) for x in fixture()[:-1]),
                        b"".join(wire(x) for x in fixture()[:-1])+b"data: [DONE]\n"]:
            stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
            stream.feed(payload, 1500)
            with self.subTest(payload=payload[-20:]), self.assertRaises(self.m.ProtocolError):
                stream.finish()

    def test_invalid_or_truncated_utf8_rejected(self):
        for data in [b"\xff", b"data: \xc3"]:
            stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
            with self.subTest(data=data), self.assertRaises(self.m.ProtocolError):
                stream.feed(data, 1100)
                stream.finish()

    def test_missing_or_duplicate_usage_rejected(self):
        frames = fixture()
        self.rejects([frames[0], frames[1], frames[2], {}, frames[4]])
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        with self.assertRaisesRegex(self.m.ProtocolError, "usage"):
            stream.feed(b"".join(wire(x) for x in frames[:4]+[frames[3], frames[4]]), 1500)

    def test_duplicate_json_keys_rejected(self):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        with self.assertRaises(self.m.ProtocolError):
            stream.feed(b'data: {"choices":[],"usage":null,"usage":{}}\n\n', 1100)

    def test_usage_and_prompt_accounting_drift_rejected(self):
        changes = [
            ("usage", "prompt_tokens", 1001),
            ("usage", "completion_tokens", 127),
            ("usage", "total_tokens", 1127),
            ("timings", "prompt_n", 999),
            ("timings", "cache_n", 1),
            ("timings", "predicted_n", 127),
        ]
        for section, key, value in changes:
            frames = fixture()
            frames[3][section][key] = value
            if section == "timings":
                frames[2]["timings"][key] = value
            with self.subTest(key=key):
                self.rejects(frames)

    def test_cached_details_must_match_explicit_cache_count(self):
        frames = fixture(cached=700)
        frames[3]["usage"]["prompt_tokens_details"]["cached_tokens"] = 701
        self.rejects(frames)
        self.assertEqual(self.parse(fixture(cached=700)).processed_tokens, 300)

    def test_final_timing_copies_must_be_identical(self):
        frames = fixture()
        frames[3]["timings"]["predicted_ms"] = 2001
        self.rejects(frames, "timings")

    def test_terminal_timing_identity_is_type_sensitive(self):
        for key, value in [("cache_n", False), ("draft_n", 104.0)]:
            frames = fixture()
            frames[3]["timings"][key] = value
            with self.subTest(key=key):
                self.rejects(frames, "timings")

    def test_required_timing_keys_nonfinite_and_invalid_counts(self):
        for key in ["cache_n", "prompt_ms", "predicted_per_second", "speculation", "draft_n"]:
            frames = fixture()
            for terminal in frames[2:4]:
                del terminal["timings"][key]
            with self.subTest(missing=key):
                self.rejects(frames)
        for key, value in [("prompt_n", True), ("cache_n", -1), ("draft_n", 104.0),
                           ("prompt_ms", float("nan")), ("predicted_ms", -1), ("prompt_per_second", True)]:
            frames = fixture()
            for terminal in frames[2:4]:
                terminal["timings"][key] = value
            with self.subTest(key=key, value=value):
                self.rejects(frames)

    def test_zero_native_durations_and_rates_are_observations(self):
        frames = fixture()
        for terminal in frames[2:4]:
            for key in ["prompt_ms", "predicted_ms", "prompt_per_second", "predicted_per_second"]:
                terminal["timings"][key] = 0.0
        self.assertEqual(self.parse(frames).native_phase_observations["prompt_ms"], 0.0)

    def test_restore_clamp_and_prefix_diagnostics(self):
        for key, value in [("disk_restore_n", 1), ("disk_restore_ms", .1),
                           ("disk_restore_n", False), ("prefix_n", -1), ("max_tokens_clamped_from", 128)]:
            frames = fixture()
            for terminal in frames[2:4]:
                terminal["timings"][key] = value
            with self.subTest(key=key):
                self.rejects(frames)
        frames = fixture()
        for terminal in frames[2:4]:
            terminal["timings"].update({"disk_restore_n": 0, "disk_restore_ms": 0.0, "prefix_n": 999})
        result = self.parse(frames)
        self.assertEqual(result.cached_tokens, 0)

    def test_speculation_ledger_scope_and_global_drift(self):
        for mutation in [
            lambda t: t.update(draft_n_accepted=63),
            lambda t: t["speculation"].update(rounds=53),
            lambda t: t["speculation"]["head"].update(accepted=101),
            lambda t: t["speculation"]["lookup"].update(drafted=True),
            lambda t: t["speculation"].update(drafter="something-else"),
        ]:
            frames = fixture()
            for terminal in frames[2:4]:
                mutation(terminal["timings"])
            self.rejects(frames)

    def test_finish_reason_output_bound_and_multiple_choices(self):
        for frames in [fixture(finish="tool_calls"), fixture(output=0), fixture(output=129)]:
            self.rejects(frames)
        frames = fixture()
        frames[1]["choices"].append(copy.deepcopy(frames[1]["choices"][0]))
        self.rejects(frames)

    def test_clock_order_types_and_feed_type_rejected(self):
        for kwargs in [{"start_qpc": True, "qpc_frequency": 1000},
                       {"start_qpc": 1000, "qpc_frequency": 0}]:
            with self.assertRaises(self.m.ProtocolError):
                self.m.OfflineChatStream(**kwargs)
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        stream.feed(b": comment\n\n", 1100)
        with self.assertRaises(self.m.ProtocolError):
            stream.feed(b"", 1099)
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        with self.assertRaises(self.m.ProtocolError):
            stream.feed("not bytes", 1100)

    def test_expected_prompt_count_is_optional_but_enforced_when_supplied(self):
        self.assertEqual(self.parse(fixture(prompt=999), expected=None).prompt_tokens, 999)
        self.rejects(fixture(prompt=999))

    def test_envelope_identity_drift_invalid_types_and_missing_fields_rejected(self):
        for key, value in [("id", "another-request"), ("model", "another-model"),
                           ("created", 1235), ("created", True), ("id", ""),
                           ("object", "text_completion")]:
            frames = fixture()
            frames[3][key] = value
            with self.subTest(key=key, value=value):
                self.rejects(frames)
        frames = fixture()
        del frames[1]["model"]
        self.rejects(frames)

    def test_reasoning_usage_metadata_rejected_without_visible_reasoning(self):
        for value in [1, True, -1, 0.0]:
            frames = fixture()
            frames[3]["usage"]["completion_tokens_details"] = {"reasoning_tokens": value}
            with self.subTest(value=value):
                self.rejects(frames)
        frames = fixture()
        frames[3]["usage"]["completion_tokens_details"] = {"reasoning_tokens": 0}
        self.assertEqual(self.parse(frames).output_tokens, 128)

    def test_end_of_turn_and_hidden_tool_usage_metadata_rejected(self):
        for details in [None, [], {"end_of_turn_kept": 1}, {"end_of_turn_kept": False},
                        {"tool_call_from_reasoning": True}, {"tool_call_from_reasoning": 0}]:
            frames = fixture()
            frames[3]["usage"]["completion_tokens_details"] = details
            with self.subTest(details=details):
                self.rejects(frames)
        frames = fixture()
        frames[3]["usage"]["completion_tokens_details"] = {
            "reasoning_tokens": 0, "end_of_turn_kept": 0, "tool_call_from_reasoning": False}
        self.assertEqual(self.parse(frames).output_tokens, 128)

    def test_content_after_final_and_usage_before_final_rejected(self):
        frames = fixture()
        self.rejects([frames[0], frames[2], frames[1], frames[3], frames[4]])
        self.rejects([frames[0], frames[1], frames[3], frames[2], frames[4]])

    def test_missing_initial_role_and_duplicate_role_frames_rejected(self):
        self.rejects(fixture()[1:])
        frames = fixture()
        del frames[0]["choices"][0]["delta"]["role"]
        self.rejects(frames)
        frames = fixture()
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        with self.assertRaisesRegex(self.m.ProtocolError, "role"):
            stream.feed(b"".join(wire(x) for x in [frames[0]] + frames), 1500)
            stream.finish()

    def test_failed_stream_is_poisoned_and_cannot_be_resumed(self):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        with self.assertRaises(self.m.ProtocolError):
            stream.feed(wire({"error": {"message": "artificial error"}}), 1100)
        with self.assertRaises(self.m.ProtocolError):
            stream.feed(b"".join(wire(x) for x in fixture()), 1500)
        with self.assertRaises(self.m.ProtocolError):
            stream.finish()

    def test_module_has_no_network_process_file_or_cli_entrypoint(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        allowed = {"__future__", "codecs", "copy", "hashlib", "json", "math", "statistics", "dataclasses", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(item.name in allowed for item in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"open", "exec", "eval", "compile", "__import__"})
            elif isinstance(node, ast.Name):
                self.assertNotEqual(node.id, "__name__")


class OfflineCohortTests(unittest.TestCase):
    def setUp(self):
        self.m = api()

    def observation(self, cached=0, prompt=1000):
        stream = self.m.OfflineChatStream(start_qpc=1000, qpc_frequency=1000)
        for frame, stamp in zip(fixture(prompt=prompt, cached=cached, output=17, finish="stop"),
                                [1100, 1200, 1300, 1400, 1500]):
            stream.feed(wire(frame), stamp)
        return stream.finish()

    def pairs(self, mode="Flexible"):
        return [self.m.FollowupPair(session_id="artificial-session-"+str(i), warmup=(i == 0),
                                   turn1=self.observation(), turn2=self.observation(cached=700 if mode == "Flexible" else 0))
                for i in range(4)]

    def test_three_complete_pairs_and_excluded_warmup_are_explicit(self):
        summary = self.m.summarize_followups(self.pairs(), cache_mode="Flexible")
        self.assertEqual(summary["measured_pair_count"], 3)
        self.assertEqual(summary["warmup_pair_count"], 1)
        self.assertFalse(summary["qualifies_hardware_measurement"])
        self.assertEqual(summary["evidence_kind"], "artificial-fixture")
        self.assertEqual(len(summary["warmup_pairs"]), 1)
        self.assertEqual(summary["turn2"]["head_acceptance"], {"accepted": 180, "drafted": 300, "ratio": .6})
        self.assertEqual(summary["turn2"]["actual_output_tokens"], [17, 17, 17])
        self.assertEqual(summary["turn2"]["cached_tokens"], [700, 700, 700])
        self.assertNotIn("prefill_tok_s", summary["turn2"])

    def test_incomplete_cohort_duplicate_session_and_warmup_drift_rejected(self):
        for pairs in [self.pairs()[:3], self.pairs()+self.pairs()[:1],
                      [self.m.FollowupPair("same", x.warmup, x.turn1, x.turn2) for x in self.pairs()],
                      [self.m.FollowupPair(x.session_id, False, x.turn1, x.turn2) for x in self.pairs()]]:
            with self.subTest(count=len(pairs)), self.assertRaises(self.m.ProtocolError):
                self.m.summarize_followups(pairs, cache_mode="Flexible")

    def test_cold_turn_cache_hit_and_flexible_followup_miss_rejected(self):
        pairs = self.pairs()
        pairs[2] = self.m.FollowupPair(pairs[2].session_id, False, self.observation(cached=1), pairs[2].turn2)
        with self.assertRaises(self.m.ProtocolError):
            self.m.summarize_followups(pairs, cache_mode="Flexible")
        with self.assertRaises(self.m.ProtocolError):
            self.m.summarize_followups(self.pairs("Off"), cache_mode="Flexible")

    def test_cacheoff_must_really_be_off_and_followup_must_process_new_tokens(self):
        self.assertEqual(self.m.summarize_followups(self.pairs("Off"), cache_mode="Off")["measured_pair_count"], 3)
        with self.assertRaises(self.m.ProtocolError):
            self.m.summarize_followups(self.pairs(), cache_mode="Off")
        pairs = self.pairs()
        pairs[2] = self.m.FollowupPair(pairs[2].session_id, False, pairs[2].turn1, self.observation(cached=1000))
        with self.assertRaises(self.m.ProtocolError):
            self.m.summarize_followups(pairs, cache_mode="Flexible")


if __name__ == "__main__":
    unittest.main()
