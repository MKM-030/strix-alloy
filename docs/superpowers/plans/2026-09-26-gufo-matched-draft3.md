# GUFO matched draft-3 profile implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable one separately qualified, fixed 36-request MTP draft-cap-3 experiment using the existing reviewed Guardian.

**Architecture:** Add a fixed identity to the matched profile registry and propagate it through recipe, binding, routing and response assessment. Reuse the exact existing requests and runtime; do not alter Guardian, telemetry, process ownership or native source.

**Tech Stack:** Python 3.12 standard library, unittest, Windows native GUFO/TheRock HIP.

## Global Constraints

- Keep at least 49 GiB available Windows physical memory before launch, a 24 GiB available physical-memory stop floor and at least 12 GiB system commit headroom.
- Draft3 uses GPU73/host4/shared20 GiB, conservative commit77 and fresh commit headroom89 GiB. Old profiles and their qualifications stay byte-equivalent.
- Exact 36 request bodies/order, request-list SHA256 EF677B664873CC42C07E4A22DA69723D6743AB57BF7944A0163A8E4799F394AB; context4096, complete input<=2304, output<=256, sessions1, connections16, startup480/request60/lifetime600 seconds, body262144/response1048576 bytes.
- Only algorithmic change: draft cap1 to3; minimum1, length policy, full vocabulary, thinking off, cache bypass, no lookup/disk cache/vision. Preserve executable/runtime/model/sidecar identities.
- No live GPU test, qualification write, persistent settings, source edits, installation change, push or publication in the implementation task. Parent qualifies only after independent review.
- Read C:/Projects/strix-alloy-research/reports/gufo-mtp-draft3-envelope-review-20260926.md completely. Its SHA256 is 825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D.

---

### Task 1: Fixed draft3 identity through the existing matched runner

**Files:**
- Modify: scripts/gufo_control/matched_recipes.py, matched_profile.py, matched_validation.py, benchmark_guard.py, smoke_store.py.
- Create: tests/gufo/test_mtp_draft3_profile.py.
- Extend where appropriate: tests/gufo/test_matched_suite.py, test_matched_validation.py.

**Interfaces:**
- Consumes existing profile_pins(profile_id), experiment_definition(profile_id), build_argv(profile_id, secret), recipe_definition(profile_id), assess(row, observation, definition), _binding(pins), _demand(pins), make_guardian(profile_id).
- Produces PROFILE_MTP_D3, MTP_DRAFT_LIMITS and PROFILES in matched_recipes; all existing APIs accept the new fixed identity without generic overrides.

- [ ] **Step 1: Add failing identity, bounds and request tests.**

```python
from dataclasses import replace
import unittest
from gufo_control import matched_recipes as r, matched_profile as p, smoke_store as s, smoke_policy

class Draft3Tests(unittest.TestCase):
    def test_bound_identity(self):
        pins = p.profile_pins(r.PROFILE_MTP_D3)
        self.assertEqual(pins.evidence.name, 'gufo-matched-mtp4k-d3-v1-runs')
        self.assertEqual(pins.qualification.name, 'gufo-matched-mtp4k-d3-v1-qualification.json')
        self.assertEqual(pins.bounds, dict(s.BOUNDS, gpu_gib=73))
        self.assertEqual(smoke_policy._demand(pins)['commit_peak_bytes'], 77 * 2**30)
        self.assertEqual(s._binding(pins)['experiment']['draft_tokens'], 3)
        with self.assertRaises(ValueError):
            s._binding(replace(pins, bounds=dict(pins.bounds, gpu_gib=72)))

    def test_fixed_requests(self):
        d1 = r.recipe_definition(r.PROFILE_MTP)
        d3 = r.recipe_definition(r.PROFILE_MTP_D3)
        self.assertEqual(d1['schedule'], d3['schedule'])
        self.assertEqual([r.request_for(row) for row in d1['schedule']],
                         [r.request_for(row) for row in d3['schedule']])
        argv = p.build_argv(r.PROFILE_MTP_D3, 'secret')
        self.assertEqual(argv[argv.index('--draft-tokens') + 1], '3')
```

Run with PYTHONPATH=scripts;tests/gufo: `python -m unittest discover -s tests/gufo -p test_mtp_draft3_profile.py -v`; expect absent PROFILE_MTP_D3 failure before production edits.

- [ ] **Step 2: Wire the exact profile with shared fixed membership.**

```python
# matched_recipes, immediately after PROFILE_MTP
PROFILE_MTP_D3 = 'matched4k-iq4xs-mtp-length-d3-v1'
MTP_DRAFT_LIMITS = {PROFILE_MTP: 1, PROFILE_MTP_D3: 3}
PROFILES = (PROFILE_AR, PROFILE_AR_V2, *MTP_DRAFT_LIMITS)
```

In recipe_definition use `profile_id not in PROFILES`, `mtp = profile_id in MTP_DRAFT_LIMITS`, and `draft_tokens=MTP_DRAFT_LIMITS.get(profile_id, 0)`. In matched_validation select MTP by membership in MTP_DRAFT_LIMITS. In all four benchmark_guard dispatch/CLI positions use matched_recipes.PROFILES, preserving the two existing unmatched choices.

```python
# matched_profile fixed additions
D3_MARGIN_SHA256 = '825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D'
# PROFILE_FILES entry
matched_recipes.PROFILE_MTP_D3: ('gufo-matched-mtp4k-d3-v1-runs', 'gufo-matched-mtp4k-d3-v1-qualification.json'),
# all MTP checks
mtp = profile_id in matched_recipes.MTP_DRAFT_LIMITS
# experiment MTP update
result.update(draft_tokens=matched_recipes.MTP_DRAFT_LIMITS[profile_id],
              min_draft_tokens=1, mtp_policy='length', mtp_draft_vocab='full')
# profile_pins margin selection
d3 = profile_id == matched_recipes.PROFILE_MTP_D3
margin_name = ('gufo-mtp-draft3-envelope-review-20260926.md' if d3
               else 'gufo-matched-mtp-envelope-review-20260926.md')
margin_sha = D3_MARGIN_SHA256 if d3 else MARGIN_SHA256
# replace() margin_report=reports/margin_name, margin_sha256=margin_sha
# build_argv draft argument
str(matched_recipes.MTP_DRAFT_LIMITS[profile_id])
```

```python
# smoke_store constants and fixed entries
MATCHED_MTP_D3 = 'matched4k-iq4xs-mtp-length-d3-v1'
MATCHED_MTP_D3_BOUNDS = dict(BOUNDS, gpu_gib=73)
MATCHED_D3_MARGIN_SHA256 = '825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D'
# PROFILE_ROOTS entry
MATCHED_MTP_D3: 'gufo-matched-mtp4k-d3-v1-runs'
# profile_bounds before other known conditions
if profile_id == MATCHED_MTP_D3:
    return MATCHED_MTP_D3_BOUNDS
```

Include MATCHED_MTP_D3 in exact experiment validation, MTP sidecar binding, matched path check, and historical predecessor/acceptance checks. Within the existing MTP margin selector, D3 takes `MATCHED_D3_MARGIN_SHA256` and `ROOT/'reports/gufo-mtp-draft3-envelope-review-20260926.md'`; retain both previous cases unchanged. Within qualification path selection D3 takes `gufo-matched-mtp4k-d3-v1-qualification.json`. Existing global latch iteration includes the new PROFILE_ROOTS entry automatically. No new predecessor format is necessary: preserve original token-count proof; the hashed D3 envelope binds the audited D1 measurement.

- [ ] **Step 3: Exercise exact refusal/routing and native-counter paths.**

Extend focused tests using the existing test_matched_profile fixture: new admission charge77 must admit at baseline commit+89GiB and reject one byte less; physical thresholds unchanged. Reject altered margin/hash/path, missing sidecar/stamp, changed draft/min/policy/vocab, bool/float substitutions and missing qualification. Assert old AR68, stage71, D1 72 bounds and old recipe hashes unchanged. Construct D3 Guardian without running and verify matched hooks; D3 incomplete latch must block older profiles. Reuse test_matched_suite fake transport for all36 requests in D3, positive counters and valid zero accepted cases; retain failures. Replay stored raw D1 observations through D3 assessor offline to verify real SSE repeated-model shape, without HTTP or GPU. Expected all native fields accepted; semantic reviews remain pending, not newly passed.

- [ ] **Step 4: Run focused tests then the full offline GUFO suite once.**

`python -m unittest discover -s tests/gufo -p 'test_mtp_draft3_profile.py' -v`

`python -m unittest discover -s tests/gufo -v`

Expected all passing; report exact command/count and RED/GREEN evidence. Use no native executable launch, no live telemetry and no model load.

- [ ] **Step 5: Self-review, commit explicit files, and hand off.**

`git diff --check` then stage only this task's five production files and covering tests. Commit `feat: add fixed reviewed GUFO draft3 benchmark profile`. Full report in `.superpowers/sdd/matched-draft3-report.md`; include exact old/new hashes, tests, no-live-actions statement, concerns. Parent independently reviews full BASE..HEAD, creates qualification and runs print-only before any GPU request.
