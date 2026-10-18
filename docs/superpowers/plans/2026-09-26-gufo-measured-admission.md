# GUFO Measured-Margin Admission Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement and independently review this task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pure admission arithmetic consume an explicitly reviewed shared-memory allowance instead of treating minimum unavoidable spill as a physical upper bound.

**Architecture:** Keep the existing side-effect-free decision function and existing scope/identity/age/commit checks. Add required measured-policy identity and shared allowance to its trusted envelope input; report minimum spill and the reviewed allowance separately. No real profile is qualified by this change.

**Tech Stack:** Python3.12 standard library, unittest.

## Global Constraints

- Preserve the49GiB prelaunch floor,24GiB Windows physical stop floor and12GiB commit reserve.
- User approved bounded staged tests with measured safety margins after build and guards pass review; residual driver-freeze risk remains.
- Dedicated-free subtraction is a minimum unavoidable spill estimate, not a maximum shared-memory bound.
- A reviewed measured policy may acknowledge unresolved future WDDM placement rather than require a mathematical placement guarantee.
- No model, GPU, WSL, host setting changes or public push. Do not alter the dirty native repo, published Halogen or source snapshots.
- Work only in `C:\Projects\strix-alloy-research\integration`; commit only the task-owned files.

### Task 1: Explicit shared allowance and honest result fields

**Files:**
- Modify `scripts/gufo_control/admission.py`.
- Modify `tests/gufo/test_admission.py`.

**Interfaces:**
- Keep `evaluate_admission(sample: dict, envelope: dict, *, now: float) -> dict`.
- Envelope adds `shared_physical_allowance_bytes` (positive integer <=MAX_BYTES), `shared_memory_policy` exactly `measured_margin`, and `shared_allowance_review_id` (nonblank str). These join existing qualification/source/model-review fields; all must be supplied by a future trusted profile loader, not arbitrary public launch arguments.
- Remove misleading result key `shared_spill_bytes` (no external callers exist yet). Return `minimum_shared_spill_bytes`, `shared_physical_allowance_bytes`, `accounting_basis` and existing `allowed`, `reasons`, `predicted_available_bytes`.
- `accounting_basis` is `reviewed_measured_margin` only once valid policy/envelope reaches accounting; otherwiseNone. No output is named a proven bound or reservation.
- Refuse if allowance < minimum unavoidable spill at the current measured occupancy. Do not silently expand the approved allowance. Subtract full allowance + host peak from current available physical, not only minimum spill and not existing shared usage already reflected in available memory.
- Overflow-check host + allowance separately. Existing commit rule remains gpu + host plus reserve; shared is backing of the same GPU allocations and must not be added again to commit.

- [ ] **Step 1: RED tests for the new contract.** Add the following fields to the synthetic fixture, update existing result-key assertions and replace the old dedicated-fit test with the tests below. Keep all existing scope/age/type/identity/floor coverage.

```python
self.envelope.update({
    "shared_physical_allowance_bytes": 12 * G,
    "shared_memory_policy": "measured_margin",
    "shared_allowance_review_id": "synthetic-test-policy-not-runtime-approval",
})

def test_dedicated_fit_does_not_erase_reviewed_shared_allowance(self):
    self.envelope["gpu_peak_bytes"] = 50 * G
    result = self.decide()
    self.assertTrue(result["allowed"])
    self.assertEqual(result["minimum_shared_spill_bytes"], 0)
    self.assertEqual(result["shared_physical_allowance_bytes"], 12 * G)
    self.assertEqual(result["predicted_available_bytes"], 37 * G)
    self.assertEqual(result["accounting_basis"], "reviewed_measured_margin")
    self.assertNotIn("shared_spill_bytes", result)

def test_allowance_below_current_minimum_is_rejected(self):
    self.envelope["shared_physical_allowance_bytes"] = 12 * G - 1
    result = self.decide()
    self.assertFalse(result["allowed"])
    self.assertIn("shared_allowance_below_minimum_spill", result["reasons"])

def test_reviewed_allowance_not_minimum_controls_physical_floor(self):
    self.envelope["shared_physical_allowance_bytes"] = 25 * G
    self.assertTrue(self.decide()["allowed"])
    self.envelope["shared_physical_allowance_bytes"] += 1
    self.assertIn("predicted_physical_floor", self.decide()["reasons"])

def test_missing_or_invalid_shared_policy_rejected(self):
    for key, values in {
        "shared_physical_allowance_bytes": [None, 0, -1, True, 1.0, 1 << 63],
        "shared_memory_policy": [None, "", "dedicated_first", True],
        "shared_allowance_review_id": [None, "", "  ", True],
    }.items():
        saved = self.envelope[key]
        for value in values:
            with self.subTest(key=key, value=value):
                self.envelope[key] = value
                self.assertFalse(self.decide()["allowed"])
        del self.envelope[key]
        self.assertFalse(self.decide()["allowed"])
        self.envelope[key] = saved
```

Run focused suite and capture expected failure against old arithmetic, especially the dedicated-fit allowance assertion. No task is validated merely by changing fixture values to preserve earlier tests.

- [ ] **Step 2: Implement the accounting amendment.** These are the complete surgical changes; preserve unrelated validation logic.

```python
ENVELOPE_BYTES = ("gpu_peak_bytes", "host_peak_bytes", "commit_peak_bytes",
                  "shared_physical_allowance_bytes")
```

Initialize result fields:

```python
result = {"allowed": False, "reasons": reasons,
          "minimum_shared_spill_bytes": None,
          "shared_physical_allowance_bytes": None,
          "predicted_available_bytes": None, "accounting_basis": None}
```

Before the existing early return on validation reasons, add:

```python
if envelope.get("shared_memory_policy") != "measured_margin":
    reasons.append("invalid_shared_memory_policy")
if not _text(envelope.get("shared_allowance_review_id")):
    reasons.append("unreviewed_shared_allowance")
```

Replace unpacking with explicit keys (there are now four fields):

```python
gpu, host, commit = (envelope[k] for k in
                     ("gpu_peak_bytes", "host_peak_bytes", "commit_peak_bytes"))
allowance = envelope["shared_physical_allowance_bytes"]
if allowance == 0 or host + allowance > MAX_BYTES:
    reasons.append("invalid_shared_allowance")
```

After validated dedicated capacity/occupancy and the existing reason return, replace spill accounting:

```python
minimum_spill = max(0, gpu - (capacity - local_used))
predicted = sample["available_physical_bytes"] - host - allowance
result["minimum_shared_spill_bytes"] = minimum_spill
result["shared_physical_allowance_bytes"] = allowance
result["predicted_available_bytes"] = predicted
result["accounting_basis"] = "reviewed_measured_margin"
if allowance < minimum_spill:
    reasons.append("shared_allowance_below_minimum_spill")
```

Then retain the existing prelaunch, predicted physical and commit-floor checks and final allowed assignment. Update module/function docstrings: this accepts a trusted, model/build/profile-bound reviewed measured allowance; it does not prove future WDDM placement or authorize a real profile. The future loader must bind qualification and review IDs to the exact profile. Do not introduce CLI override or a fallback to old arithmetic.

- [ ] **Step 3: GREEN and edge regressions.** Add explicit tests for host+allowance overflow, proof that existing shared occupancy is not subtracted twice, unchanged inputs, and unchanged commit accounting when allowance alone increases. Extend existing all-envelope-fields validation loop with the new numeric field. Verify missing keys reject without exceptions. Check reasons for wrong policy/review identity rather than onlyFalse. Run all offline tests once after the focused cases pass.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'scripts'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_admission.py -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py' -v
git diff --check
git add -- scripts/gufo_control/admission.py tests/gufo/test_admission.py
git commit -m 'fix: distinguish reviewed shared allowance from minimum spill'
```

Report RED/GREEN with commands/counts and the explicit limitation that no measured runtime allowance has yet been qualified. Tests are synthetic arithmetic only.

## Scope review

This replaces one unsafe interpretation in the pure API before the launcher has callers. It does not supply real memory margins, collect telemetry, start GUFO or implement the guardian. Those components remain tracked separately. No design approval is required again: this implements the user's confirmed measured-margin policy.
