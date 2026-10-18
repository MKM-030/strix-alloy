# GUFO Admission Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement independently testable, fail-closed memory-admission arithmetic used by the upcoming GUFO controller.

**Architecture:** This first small plan isolates pure admission decisions from Windows counters, GGUF parsing, process creation and benchmark code. The caller must supply validated model identity and a reviewed complete allocation envelope; this module alone never authorizes a real model start. Later plans connect it to real telemetry and owned-process supervision.

**Tech Stack:** Python 3.12 standard library, unittest; no installed dependencies, GPU, WSL or server.

## Global Constraints

- Native Windows, localhost only, separate default port `8836` and model alias `gufo-flash-next`.
- Exactly one session, context capacity 4096, no MTP, no projector/vision auto-discovery and no disk prompt-cache configuration.
- Preserve at least the existing conservative **49 GiB Windows prelaunch floor and 24 GiB predicted post-load/runtime physical headroom**.
- An unbounded or unexplained component is not silently treated as zero; it blocks qualification until audited or bounded.
- Source snapshots remain clean. Any required engine fix belongs in a separate working checkout and a recorded patch, not a silently modified reference snapshot.
- No model/GPU/WSL starts or persistent host changes in this plan. No writes in the dirty native checkout or published Halogen checkout.
- Work in `C:\Projects\strix-alloy-research\integration` on `codex/gufo-native-integration`.
- This plan is one dependency of the full approved goal, not a replacement for backend delivery or benchmarks.

## Full-goal continuation map

After review of this plan's deliverable, continue with separately detailed plans for: bounded GGUF/profile validation; reproducible CPU/GPU build with pinned dependencies; scoped Windows telemetry and guardian/job ownership; optional PowerShell launch/status/stop entrypoint; explicit-request HTTP benchmark client; reviewed single-session model qualification and matched performance tests; safe concurrency and later long-context qualification. Halogen/Strix Llama optimizations remain separate measured experiments. Do not mark the goal complete at any intermediate stage.

### Task 1: Pure fail-closed memory admission

**Files:**
- Create: `scripts/gufo_control/__init__.py` (one package docstring).
- Create: `scripts/gufo_control/admission.py` (validation and pure arithmetic only).
- Create: `tests/gufo/test_admission.py` (real arithmetic, no mocks).

**Interfaces:**
- Produces `evaluate_admission(sample: dict, envelope: dict, *, now: float) -> dict`.
- Return keys: `allowed` (bool), `reasons` (list[str]), `shared_spill_bytes` and `predicted_available_bytes` (int or None).
- `sample` counters are bytes, host-global for available/commit and adapter-aggregate for GPU occupancy. A helper-process budget is not accepted as an aggregate counter. All byte values must be non-boolean integers in [0, 2**63-1]. `now` and capture time are monotonic seconds from the same clock.
- `envelope` is an INTERNAL caller-supplied reviewed bound, not a public override. Its GPU peak includes all device weights/scratch/state/transients; host peak includes pinned allocations and retained/in-flight snapshots, excluding shared GPU spill to avoid double counting. Commit peak must cover at least GPU plus host peak; reserve a further 12 GiB commit headroom. A later curated profile loader—not arbitrary user JSON—will own qualification and bind the envelope to model/context/MTP/build identity.
- Current shared usage is already reflected in host available memory; subtract only additional predicted spill. No OS calls, process creation, GGUF reads or actual-profile qualification here.

- [ ] **Step 1: Create the failing test file and package path only.**

Set `scripts/gufo_control/__init__.py` to `"""Optional GUFO control helpers; importing never starts a runtime."""`.
Create `tests/gufo/test_admission.py` with:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED.** From the integration root in PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'scripts')
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_admission.py -v
```

Expected: missing `gufo_control.admission`, demonstrating the unimplemented interface. Then create a stub that returns `allowed=True` and empty reasons, run a rejection test and capture its failing assertion. Replace the stub in Step 3; no production process is involved.

- [ ] **Step 3: Implement the pure policy.** Use this complete starting implementation in `scripts/gufo_control/admission.py`. Improve any concrete correctness defect exposed by tests; do not implement telemetry or launch methods in this task.

```python
"""Pure pre-start accounting, not a reservation or runtime safety guarantee."""
import math
import re

GIB = 1 << 30
MAX_BYTES = (1 << 63) - 1
PRELAUNCH_FLOOR = 49 * GIB
RUNTIME_FLOOR = 24 * GIB
COMMIT_RESERVE = 12 * GIB
MAX_SAMPLE_AGE_SECONDS = 5.0
SOURCE_COMMIT = "cff564964e8506c0abb3e530cecb55332187ac6c"
SAMPLE_BYTES = ("available_physical_bytes", "commit_headroom_bytes",
                "dedicated_capacity_bytes", "adapter_dedicated_bytes",
                "adapter_shared_bytes")
ENVELOPE_BYTES = ("gpu_peak_bytes", "host_peak_bytes", "commit_peak_bytes")


def _bytes(value):
    return type(value) is int and 0 <= value <= MAX_BYTES


def _finite_time(value):
    try:
        return type(value) in (int, float) and value >= 0 and math.isfinite(value)
    except OverflowError:
        return False


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def evaluate_admission(sample: dict, envelope: dict, *, now: float) -> dict:
    """Evaluate trusted profile bounds against a fresh, scoped telemetry sample.

    The caller is responsible for binding qualified bounds to its exact model,
    build and request profile, and for proving the telemetry provider's scope.
    No model has been qualified merely because a synthetic fixture passes here.
    """
    reasons = []
    result = {"allowed": False, "reasons": reasons,
              "shared_spill_bytes": None, "predicted_available_bytes": None}
    if not isinstance(sample, dict) or not isinstance(envelope, dict):
        reasons.append("invalid_input")
        return result
    for key in SAMPLE_BYTES:
        if not _bytes(sample.get(key)):
            reasons.append("invalid_counter:" + key)
    for key in ENVELOPE_BYTES:
        if not _bytes(envelope.get(key)):
            reasons.append("invalid_envelope:" + key)
    captured = sample.get("captured_monotonic")
    if not _finite_time(now) or not _finite_time(captured):
        reasons.append("invalid_sample_time")
    elif not 0 <= now - captured <= MAX_SAMPLE_AGE_SECONDS:
        reasons.append("stale_or_future_sample")
    if sample.get("gpu_scope") != "adapter_aggregate" or sample.get("host_scope") != "host_global":
        reasons.append("invalid_counter_scope")
    if not _text(sample.get("adapter_luid")) or not _text(sample.get("provider")):
        reasons.append("missing_counter_identity")
    if sample.get("telemetry_ok") is not True:
        reasons.append("telemetry_unavailable")
    pids = sample.get("other_inference_pids")
    if not isinstance(pids, (list, tuple)) or any(type(p) is not int or p <= 0 for p in pids):
        reasons.append("invalid_process_inventory")
    elif pids:
        reasons.append("other_inference_active")
    if envelope.get("qualified") is not True or not _text(envelope.get("review_id")):
        reasons.append("unqualified_envelope")
    revision = envelope.get("model_revision")
    if envelope.get("source_commit") != SOURCE_COMMIT or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        reasons.append("invalid_profile_identity")
    if reasons:
        return result
    gpu, host, commit = (envelope[k] for k in ENVELOPE_BYTES)
    if gpu == 0 or commit < gpu + host or gpu + host + COMMIT_RESERVE > MAX_BYTES:
        reasons.append("inconsistent_commit_bound")
    capacity = sample["dedicated_capacity_bytes"]
    local_used = sample["adapter_dedicated_bytes"]
    if capacity == 0 or local_used > capacity:
        reasons.append("inconsistent_dedicated_counter")
    if reasons:
        return result
    spill = max(0, gpu - (capacity - local_used))
    predicted = sample["available_physical_bytes"] - host - spill
    result["shared_spill_bytes"] = spill
    result["predicted_available_bytes"] = predicted
    if sample["available_physical_bytes"] < PRELAUNCH_FLOOR:
        reasons.append("prelaunch_physical_floor")
    if predicted < RUNTIME_FLOOR:
        reasons.append("predicted_physical_floor")
    if sample["commit_headroom_bytes"] - commit < COMMIT_RESERVE:
        reasons.append("commit_floor")
    result["allowed"] = not reasons
    return result
```

- [ ] **Step 4: Run GREEN and edge tests.** Run the Step 2 command, expected 17 tests passing. Add concrete tests for empty provider/LUID, wrong source commit, malformed PID collection, exactly-five-second sample, invalid top-level input and zero GPU demand before extending code. Check non-finite and extreme timestamps cannot escape validation with an exception. Add focused RED/GREEN evidence for any correction.
- [ ] **Step 5: Commit only owned paths after self-review.**

```powershell
git diff --check
git add -- scripts/gufo_control/__init__.py scripts/gufo_control/admission.py tests/gufo/test_admission.py
git commit -m 'feat: add fail-closed GUFO admission arithmetic'
```

Write the implementation report to the task-brief sibling `task-1-report.md`, including RED/GREEN commands, actual counts, commit(s), limitations and self-review findings. No real profile is qualified by this task. Main performs independent task review before connecting this code to launch.
