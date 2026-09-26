import unittest

from gufo_control.admission import evaluate_admission


G = 1 << 30


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "captured_monotonic": 100.0, "available_physical_bytes": 53 * G,
            "commit_headroom_bytes": 100 * G, "dedicated_capacity_bytes": 64 * G,
            "adapter_dedicated_bytes": 4 * G, "adapter_shared_bytes": 3 * G,
            "adapter_luid": "0x00000000_0x00001234", "gpu_scope": "adapter_aggregate",
            "host_scope": "host_global", "provider": "fixture-only",
            "telemetry_ok": True, "other_inference_pids": [],
        }
        self.envelope = {
            "gpu_peak_bytes": 72 * G, "host_peak_bytes": 4 * G,
            "commit_peak_bytes": 76 * G, "qualified": True,
            "review_id": "unit-fixture-not-a-runtime-qualification",
            "source_commit": "cff564964e8506c0abb3e530cecb55332187ac6c",
            "model_revision": "38bb39ee97821de2c9009abb7e93950eec396e66",
        }

    def decide(self):
        return evaluate_admission(self.sample, self.envelope, now=101.0)

    def test_additional_spill_not_existing_shared_is_subtracted(self):
        result = self.decide()
        self.assertTrue(result["allowed"])
        self.assertEqual(result["shared_spill_bytes"], 12 * G)
        self.assertEqual(result["predicted_available_bytes"], 37 * G)

    def test_no_spill_when_dedicated_fits(self):
        self.envelope["gpu_peak_bytes"] = 50 * G
        result = self.decide()
        self.assertTrue(result["allowed"])
        self.assertEqual(result["shared_spill_bytes"], 0)
        self.assertEqual(result["predicted_available_bytes"], 49 * G)

    def test_unqualified_bound_is_rejected(self):
        self.envelope["qualified"] = False
        self.assertIn("unqualified_envelope", self.decide()["reasons"])

    def test_missing_counter_is_rejected(self):
        del self.sample["adapter_shared_bytes"]
        self.assertFalse(self.decide()["allowed"])

    def test_helper_process_scope_is_rejected(self):
        self.sample["gpu_scope"] = "calling_process"
        self.assertIn("invalid_counter_scope", self.decide()["reasons"])

    def test_host_scope_must_be_global(self):
        self.sample["host_scope"] = "process"
        self.assertFalse(self.decide()["allowed"])

    def test_stale_and_future_samples_are_rejected(self):
        for captured in (95.0, 102.0, float("nan"), float("inf"), True):
            with self.subTest(captured=captured):
                self.sample["captured_monotonic"] = captured
                self.assertFalse(self.decide()["allowed"])

    def test_byte_counters_reject_negative_bool_float_and_overflow(self):
        for bad in (-1, True, 3.0, 1 << 63, "12"):
            with self.subTest(bad=bad):
                self.sample["available_physical_bytes"] = bad
                self.assertFalse(self.decide()["allowed"])

    def test_all_envelope_byte_fields_are_validated(self):
        for key in ("gpu_peak_bytes", "host_peak_bytes", "commit_peak_bytes"):
            saved = self.envelope[key]
            for bad in (-1, True, 1 << 63):
                with self.subTest(key=key, bad=bad):
                    self.envelope[key] = bad
                    self.assertFalse(self.decide()["allowed"])
            self.envelope[key] = saved

    def test_missing_identity_or_review_is_rejected(self):
        for key in ("review_id", "source_commit", "model_revision"):
            saved = self.envelope[key]
            self.envelope[key] = ""
            with self.subTest(key=key):
                self.assertFalse(self.decide()["allowed"])
            self.envelope[key] = saved

    def test_prelaunch_floor(self):
        self.sample["available_physical_bytes"] = 49 * G - 1
        self.assertIn("prelaunch_physical_floor", self.decide()["reasons"])

    def test_runtime_floor_and_boundary(self):
        self.envelope["host_peak_bytes"] = 17 * G
        self.envelope["commit_peak_bytes"] = 89 * G
        self.sample["commit_headroom_bytes"] = 110 * G
        self.assertTrue(self.decide()["allowed"])
        self.envelope["host_peak_bytes"] += 1
        self.envelope["commit_peak_bytes"] += 1
        self.assertIn("predicted_physical_floor", self.decide()["reasons"])

    def test_commit_reserve(self):
        self.sample["commit_headroom_bytes"] = 88 * G
        self.assertTrue(self.decide()["allowed"])
        self.sample["commit_headroom_bytes"] -= 1
        self.assertIn("commit_floor", self.decide()["reasons"])

    def test_inconsistent_commit_bound(self):
        self.envelope["commit_peak_bytes"] = 60 * G
        self.assertIn("inconsistent_commit_bound", self.decide()["reasons"])

    def test_dedicated_usage_beyond_capacity_is_not_free_memory(self):
        self.sample["adapter_dedicated_bytes"] = 65 * G
        self.assertFalse(self.decide()["allowed"])

    def test_other_inference_or_lost_telemetry_rejects(self):
        self.sample["other_inference_pids"] = [123]
        self.assertIn("other_inference_active", self.decide()["reasons"])
        self.sample["other_inference_pids"] = []
        self.sample["telemetry_ok"] = False
        self.assertIn("telemetry_unavailable", self.decide()["reasons"])

    def test_inputs_are_not_modified(self):
        before_sample = dict(self.sample)
        before_envelope = dict(self.envelope)
        self.decide()
        self.assertEqual(self.sample, before_sample)
        self.assertEqual(self.envelope, before_envelope)

    def test_empty_provider_or_luid_is_rejected(self):
        for key in ("provider", "adapter_luid"):
            with self.subTest(key=key):
                saved = self.sample[key]
                self.sample[key] = "  "
                self.assertIn("missing_counter_identity", self.decide()["reasons"])
                self.sample[key] = saved

    def test_wrong_source_commit_is_rejected(self):
        self.envelope["source_commit"] = "0" * 40
        self.assertIn("invalid_profile_identity", self.decide()["reasons"])

    def test_malformed_process_inventory_is_rejected(self):
        for bad in (None, 123, [True], [0], ["123"], {123}):
            with self.subTest(bad=bad):
                self.sample["other_inference_pids"] = bad
                self.assertIn("invalid_process_inventory", self.decide()["reasons"])

    def test_sample_exactly_five_seconds_old_is_accepted(self):
        self.sample["captured_monotonic"] = 96.0
        self.assertTrue(self.decide()["allowed"])

    def test_invalid_top_level_input_is_rejected(self):
        for sample, envelope in ((None, self.envelope),
                                 (self.sample, None),
                                 ([], self.envelope),
                                 (self.sample, [])):
            with self.subTest(sample=sample, envelope=envelope):
                result = evaluate_admission(sample, envelope, now=101.0)
                self.assertFalse(result["allowed"])
                self.assertIn("invalid_input", result["reasons"])

    def test_zero_gpu_demand_is_rejected(self):
        self.envelope["gpu_peak_bytes"] = 0
        self.assertIn("inconsistent_commit_bound", self.decide()["reasons"])

    def test_nonfinite_and_extreme_timestamps_fail_closed(self):
        for now, captured in ((float("nan"), 100.0),
                              (float("inf"), 100.0),
                              (101.0, -1.0),
                              (101.0, 10 ** 1000),
                              (10 ** 1000, 100.0),
                              (1e308, -1e308)):
            with self.subTest(now=now, captured=captured):
                self.sample["captured_monotonic"] = captured
                result = evaluate_admission(self.sample, self.envelope, now=now)
                self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
