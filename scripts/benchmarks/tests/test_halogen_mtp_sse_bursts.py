import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halogen_mtp_sse_bursts import audit_capture


def capture(times_ms, *, head=(3, 6, 3), lookup=(0, 0, 0), choice_index=0, first_id="cmpl-fixture"):
    def scope(values):
        return dict(zip(("rounds", "drafted", "accepted"), values, strict=True))

    timings = {
        "prompt_n": 8192,
        "predicted_n": len(times_ms),
        "cache_n": 0,
        "disk_restore_n": 0,
        "draft_n": head[1] + lookup[1],
        "draft_n_accepted": head[2] + lookup[2],
        "speculation": {
            "drafter": "mtp",
            "rounds": head[0] + lookup[0],
            "head": scope(head),
            "lookup": scope(lookup),
            "grammar": scope((0, 0, 0)),
        },
    }
    finish = {"id": "cmpl-fixture", "choices": [{"index": 0, "text": "", "finish_reason": "length"}],
              "timings": timings}
    usage = {"id": "cmpl-fixture", "choices": [], "timings": timings,
             "usage": {"completion_tokens": len(times_ms), "prompt_tokens": 8192,
                       "completion_tokens_details": {"reasoning_tokens": 0}}}
    values = [{"id": first_id if i == 0 else "cmpl-fixture",
               "choices": [{"index": choice_index, "text": "" if i == 2 else "x", "finish_reason": None}]}
              for i in range(len(times_ms))]
    values.extend((finish, usage))
    ticks = [t * 1_000_000 for t in (*times_ms, times_ms[-1] + 1, times_ms[-1] + 2)]
    lines = [(time, b"data: " + json.dumps(value).encode()) for time, value in zip(ticks, values, strict=True)]
    lines.append((ticks[-1] + 1, b"data: [DONE]"))
    return {"http_status": 200, "dispatch_qpc_ns": 1, "http_header_qpc_ns": 2,
            "eof_qpc_ns": ticks[-1] + 2, "lines": [
                {"qpc_ns": t, "base64": base64.b64encode(raw).decode()} for t, raw in lines
            ]}


class BurstEvidenceTests(unittest.TestCase):
    def test_fixed_depth_outcomes_reconcile_including_empty_delta(self):
        record = capture([20, 50, 80, 81, 82, 110, 111, 140])
        result = audit_capture(record, fixed_depth=2)
        self.assertEqual(result["burst_sizes"], [1, 1, 3, 2, 1])
        self.assertEqual(result["boundary_singletons"], 2)
        self.assertEqual(result["inferred_accepted_per_round"], [0, 2, 1])
        self.assertEqual(result["inferred_rounds_at_least_rank"], [2, 1])
        self.assertEqual(result["empty_deltas"], 1)

    def test_one_boundary_and_unknown_adaptive_proposal_depth(self):
        record = capture([20, 50, 51, 80, 81], head=(2, 3, 2))
        result = audit_capture(record)
        self.assertEqual(result["boundary_singletons"], 1)
        self.assertEqual(result["inferred_accepted_per_round"], [1, 1])
        self.assertIsNone(result["fixed_depth"])

    def test_grouping_must_hold_across_thresholds(self):
        with self.assertRaisesRegex(ValueError, "threshold"):
            audit_capture(capture([20, 50, 80, 85, 86, 110, 111, 140]), fixed_depth=2)

    def test_native_aggregate_must_reconcile(self):
        with self.assertRaisesRegex(ValueError, "reconcile"):
            audit_capture(capture([20, 50, 80, 81, 82, 110, 111, 140], head=(4, 8, 2)), fixed_depth=2)

    def test_mixed_drafters_are_outside_the_contract(self):
        with self.assertRaisesRegex(ValueError, "head-only"):
            audit_capture(capture([20, 50, 80, 81, 82, 110, 111, 140], lookup=(1, 2, 1)))

    def test_fixed_depth_cannot_be_inferred_from_matching_average_alone(self):
        with self.assertRaisesRegex(ValueError, "fixed depth"):
            audit_capture(capture([20, 50, 80, 81, 82, 110, 111, 140]), fixed_depth=1)

    def test_multiple_choices_or_ids_are_outside_the_contract(self):
        times = [20, 50, 80, 81, 82, 110, 111, 140]
        with self.assertRaisesRegex(ValueError, "token event"):
            audit_capture(capture(times, choice_index=1))
        with self.assertRaisesRegex(ValueError, "one completion identity"):
            audit_capture(capture(times, first_id="another-response"))

    def test_qpc_order_must_match_wire_order(self):
        with self.assertRaisesRegex(ValueError, "QPC"):
            audit_capture(capture([20, 50, 80, 79, 82, 110, 111, 140]))


if __name__ == "__main__":
    unittest.main()
