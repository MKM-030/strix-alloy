# GUFO finite two-run store and profile registration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Code snippets are starting implementations; preserve the normative safety and evidence contracts when fixing scoped issues through RED/GREEN.

**Goal:** Add a private, independently pinned `FiniteStore` that consumes at most two linked lifecycle attempts and accepts the second only after bound structural completion, terminal cleanup, five recovery samples, and a new admission decision.

**Architecture:** Register one closed finite profile beside the existing profiles. Reuse the existing candidate checks, bounded JSON I/O, pure admission arithmetic, controller inventory and strict terminal-clean predicate; implement a small fixed-length history rather than copying the unbounded installed history. A separate initially empty finite review anchor binds a future finite review certificate; neither phase coverage nor that finite review grants installed service acceptance.

**Tech Stack:** Python standard library, `unittest`, the existing `BoundStore`/`BoundPolicy` seams, JSON evidence, Windows paths.

## Global Constraints

- Approved native-Windows design: `C:/Projects/strix-alloy-research/integration/docs/superpowers/specs/2026-09-26-gufo-native-design.md`; do not reopen design approval.
- Target checkout for later implementation only: `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`. It was read-only during this planning task.
- Planning provenance: private report `gufo-finite-store-plan-20260927.md`, SHA256 `FEF8749DEEF7AEF5F07D525B635BFAC9FCE722AA4B3580670FB9A484C7ED51AA`, fully read by the main agent; this committed plan governs later implementation.
- Preserve installed source/profile/root/acceptance, historical smoke profiles, working launchers and every failed-run artifact. Do not instantiate `InstalledStore` or call installed acceptance functions from finite code.
- Finite profile `ar4k-service-lifecycle-v1`; private root `C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-v1-runs`.
- Fixed workload `config/gufo-service-lifecycle-workload.json`, raw SHA256 `30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38`. Use `finite_workload.load_workload`, not a rewritten workload.
- Production source `e6feed7ca52df4661d10434c72a8ea5b5f054bc2`, tree `7912be2688d6874c0e13f4723aad00a5c3cbe1cf`; runtime `C:/Projects/strix-alloy-research/runtimes/gufo-native-service-header-e6feed7-therock10.2`, variant `service-ar4k-header-v1`.
- EXE `(42440192, 9682019A5198B19CA131D60298A1E896186099ACC971C17B04BB31E302F7FFE9)`; keep existing model, SDK/DLL and operator-history pins.
- Envelope exactly 68/4/20 GiB GPU/additional-host/shared; floors exactly 49/24/12 GiB prelaunch/runtime/commit reserve. No admission arithmetic changes.
- Lifecycle POST counts 66 then 6; deadlines 3600 then 900 seconds from resume; readiness at most 480 seconds, 240 GET polls and one models query per lifecycle. No third attempt, automatic retries, replacements or erased failed attempt.
- First structural completion can retain `pending_semantic_review=True`. Final qualification still requires manual semantic and coverage review. Neither a boolean `success`, a copied disk receipt nor a HTTP 200 is sufficient structural evidence.
- Preserve the cross-profile scan including `gufo-ar4k-smoke-runs`, `gufo-ar4k-connect-wait-smoke-runs` and operator history. The old failed historical latch blocks this profile too. No recovery invocation, deletion or override in this component or its implementation commands.
- No guardian, IPC, client transport/orchestration, helper, collector, model/GPU, network listener, system setting, live socket, D: access, public release, push or installed acceptance mutation belongs to this plan.
- Current header-cap envelope review plus final controller footprint review form the finite review context. A separately pinned finite certificate records those reviews; this plan introduces no additional user design-approval gate and manufactures no approval.
- All code below is complete starting code, not executed or claimed passing in this report. Future tests use temporary directories and mocked artifact providers only.
- New finite review, anchor and phase files must undergo bounded strict reads before any unbounded JSON parser. Reused hashing/artifact helpers require a checked file-size cap first; never call them on an unchecked review or phase file. A later read/stamp/hash disagreement is a failure, not a fallback to permissive parsing.

## Existing seams and file map

`benchmark_runtime.BoundStore` provides the five guardian-facing methods. Its default one-attempt `smoke_store._begin_run` is unsuitable for two runs. `service_store._clean` already requires owned identity, successful lifecycle result, all terminal workers/evidence/cleanup and exactly five recovery samples; reuse it without modification. `finite_ledger._read/_exclusive` supply bounded strict JSON, duplicate-key/nonfinite rejection, checked local paths and exclusive fsynced immutable writes. Importing them does not construct a ledger or perform I/O. `service_store._digest`, `controller_artifacts` and the source provenance constants are stateless reusable helpers. `smoke_store._verify_candidate_artifacts/_recheck_candidate_artifacts`, `_operator_sequence` and `_load_original_operator_baseline` retain their existing semantics.

All paths below are relative to `C:/Projects/strix-alloy-research/integration` unless an absolute path is supplied.

| File | Responsibility |
| --- | --- |
| `scripts/gufo_control/finite_profile.py` (new) | Exact pins, finite review schema, pure policy binding. |
| `config/gufo-finite-review-anchor.json` (new) | Null finite certificate hash; deliberately not launch authority. |
| `scripts/gufo_control/smoke_store.py` (small edits) | Closed profile/bounds/root registration and finite current-latch dispatch. |
| `scripts/gufo_control/smoke_policy.py` (small edits) | Recognize finite certificate and preserve the existing policy paths. |
| `scripts/gufo_control/admission.py` (small edit) | Route finite profile through its closed identity check, then unchanged source-specific arithmetic. |
| `scripts/gufo_control/finite_store.py` (new) | Static verification, strict two-entry history, fresh-admission witness and bound terminal records. |
| `tests/gufo/test_finite_profile.py` (new) | Pure profile, certificate, policy and historical-profile regression tests. |
| `tests/gufo/test_finite_store.py` (new) | Temporary-directory state, failure, linkage and admission tests. |

There is no edit to `service_store.py`, `benchmark_runtime.py`, `finite_phase.py`, guardian, IPC or recovery modules.

### Task 1: Register the closed finite profile and pure policy binding

**Files:** Create `scripts/gufo_control/finite_profile.py`, `config/gufo-finite-review-anchor.json`, `tests/gufo/test_finite_profile.py`; modify the exact registration functions in `smoke_store.py`, `smoke_policy.py`, `admission.py` shown below.

**Interfaces:** `finite_binding(pins) -> dict`; `review_record(candidate_sha256, review_id, envelope_review_id, footprint_review_id) -> dict`; `validate_review(record) -> dict`; `bind_manifest(manifest, pins=PINS) -> dict`; `profile_from_manifest(manifest, pins=PINS) -> SmokeProfile`; `profile_valid(profile, pins=PINS) -> bool`. Review records are data, not self-authenticating approvals. Only `FiniteStore` authenticates the raw certificate file against the independent anchor.

- [ ] **Step 1: Write the failing profile tests.** Create the complete test file:

```python
from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from gufo_control import admission, finite_profile as fp, service_store
from gufo_control import smoke_policy, smoke_store
from gufo_control.benchmark_runtime import BoundPolicy
from gufo_control.operator_policy import baseline
from test_operator_policy import frame, series


def candidate():
    return dict(profile=fp.PROFILE_ID, source=fp.PINS.source_commit,
        bounds=dict(fp.PINS.bounds), finite_profile=fp.finite_binding(fp.PINS),
        executable=str(fp.PINS.build/fp.PINS.executable_name),
        sdk=str(fp.PINS.sdk), model=dict(first_shard=str(fp.PINS.first_shard),
        revision=fp.PINS.model_revision), margin_report=dict(sha256=fp.PINS.margin_sha256))


def qualified(value=None):
    m = deepcopy(candidate() if value is None else value)
    q = fp.review_record(service_store._digest(m), 'finite-review',
                         'header-envelope-review', 'controller-footprint-review')
    m.update(qualification=q, qualification_anchor=dict(schema=1,
        profile_id=fp.PROFILE_ID, certificate_sha256='A'*64),
        qualification_stamp=dict(sha256='A'*64),
        qualification_anchor_stamp=dict(sha256='B'*64))
    return m


class FiniteProfileTests(unittest.TestCase):
    def test_closed_registration_preserves_existing_pins(self):
        installed = deepcopy(service_store.PINS)
        historical = deepcopy(smoke_store.PINS)
        self.assertEqual(smoke_store.PROFILE_ROOTS[fp.PROFILE_ID],
                         'gufo-service-lifecycle-v1-runs')
        self.assertEqual(smoke_store.profile_bounds(fp.PROFILE_ID), smoke_store.BOUNDS)
        self.assertEqual(smoke_store._binding(fp.PINS), fp.finite_binding(fp.PINS))
        self.assertEqual(service_store.PINS, installed)
        self.assertEqual(smoke_store.PINS, historical)
        for change in (dict(source_commit='0'*40), dict(evidence=installed.evidence),
                       dict(bounds=dict(fp.PINS.bounds, host_gib=5)),
                       dict(bounds=dict(fp.PINS.bounds, gpu_gib=68.0))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                smoke_store._binding(replace(fp.PINS, **change))

    def test_certificate_does_not_accept_installed_or_changed_candidate(self):
        good = qualified()
        p = BoundPolicy(fp.PINS).profile_from_manifest(good)
        self.assertTrue(BoundPolicy(fp.PINS)._profile_valid(p))
        self.assertFalse(smoke_policy._profile_valid(p))
        self.assertFalse(BoundPolicy(service_store.PINS)._profile_valid(p))
        for change in (
            lambda m: m['qualification'].update(status='persistent-service-accepted'),
            lambda m: m['qualification'].update(max_lifecycles=True),
            lambda m: m['qualification'].update(footprint_review_id=''),
            lambda m: m['qualification_anchor'].update(certificate_sha256=None),
            lambda m: m['qualification_stamp'].update(sha256='C'*64),
            lambda m: m['bounds'].update(shared_gib=19),
            lambda m: m['finite_profile'].update(workload_sha256='0'*64)):
            changed = deepcopy(good); change(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                BoundPolicy(fp.PINS).profile_from_manifest(changed)
        self.assertFalse(BoundPolicy(fp.PINS)._profile_valid(replace(p, host_peak_bytes=True)))

    def test_review_is_separate_from_installed_anchor(self):
        anchor = service_store.expected_anchor(service_store.expected_profile(service_store.PINS))
        self.assertIsNone(anchor['acceptance_sha256'])
        self.assertIsNone(anchor['installed_workload'])
        self.assertNotEqual(fp.ANCHOR_PATH, service_store.ANCHOR_PATH)
        with patch.object(service_store, '_acceptance', side_effect=AssertionError):
            self.assertTrue(BoundPolicy(fp.PINS).profile_from_manifest(qualified()).qualified)

    def test_finite_admission_uses_exact_header_source_without_changing_math(self):
        p = BoundPolicy(fp.PINS).profile_from_manifest(qualified())
        b = baseline(series()); f = frame(12)
        kw = dict(now=f.query_end, now_utc=f.validated_utc)
        actual = BoundPolicy(fp.PINS).admission_decision(p, b, f, **kw)
        self.assertEqual(actual['reasons'], [])
        direct = admission._evaluate_admission(f.snapshot, dict(p.envelope),
            now=f.query_end, source_commit=fp.PINS.source_commit)
        self.assertEqual(actual['predicted_available_bytes'], direct['predicted_available_bytes'])
        stale = BoundPolicy(fp.PINS).admission_decision(p, b, f,
            now=f.query_end+3, now_utc=f.validated_utc)
        self.assertFalse(stale['allowed'])
        with patch.object(admission, '_evaluate_admission') as evaluate:
            admission._evaluate_service_admission({}, {}, now=1, pins=fp.PINS)
            self.assertEqual(evaluate.call_args.kwargs['source_commit'], fp.PINS.source_commit)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Confirm RED using only offline tests.** From the target checkout:

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest discover -s tests/gufo -p test_finite_profile.py -v
```

Expected: import failure for absent `finite_profile`. Do not execute these commands during report creation.

- [ ] **Step 3: Add the complete profile module.**

```python
"""Closed finite profile; pure review binding, no launch or acceptance mutation."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path

from . import service_store, smoke_store
from .finite_workload import WORKLOAD_SHA256

PROFILE_ID = smoke_store.FINITE_SERVICE
CONTROLLER_ID = 'gufo-native-finite-controller-v1'
ANCHOR_PATH = Path(__file__).resolve().parents[2]/'config/gufo-finite-review-anchor.json'
PINS = replace(deepcopy(service_store.PINS), profile_id=PROFILE_ID,
    evidence=smoke_store.ROOT/'reports/gufo-service-lifecycle-v1-runs',
    qualification=smoke_store.ROOT/'reports/gufo-service-lifecycle-v1-review.json')
REVIEW_FIELDS = frozenset(('qualification', 'qualification_stamp',
                         'qualification_anchor', 'qualification_anchor_stamp'))


def finite_binding(pins):
    # Canonical comparison retains bool/int distinctions in dataclass fields.
    canonical = lambda p: json.dumps(asdict(p), default=str, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False)
    if (canonical(pins) != canonical(PINS)
            or pins.profile_id != PROFILE_ID
            or pins.evidence.name != smoke_store.PROFILE_ROOTS[PROFILE_ID]
            or pins.bounds != smoke_store.BOUNDS
            or any(type(value) is not int for value in pins.bounds.values())):
        raise ValueError('finite_identity_invalid')
    return dict(profile_id=PROFILE_ID, controller_id=CONTROLLER_ID,
        source_tree=service_store.SOURCE_TREE,
        runtime_variant=service_store.RUNTIME_VARIANT,
        runtime_policy_sha256=service_store.RUNTIME_POLICY_SHA256,
        workload_sha256=WORKLOAD_SHA256, max_lifecycles=2,
        acceptance_status='finite_only_not_installed_acceptance')


def review_record(candidate_sha256, review_id, envelope_review_id, footprint_review_id):
    if (not smoke_store._digest_valid(candidate_sha256)
            or any(type(v) is not str or not v.strip() or len(v) > 256
                   for v in (review_id, envelope_review_id, footprint_review_id))):
        raise ValueError('finite_review_identity')
    return dict(schema=1, kind='gufo-finite-two-lifecycle-review',
        status='finite-two-lifecycle-reviewed', profile_id=PROFILE_ID,
        controller_id=CONTROLLER_ID, source_commit=PINS.source_commit,
        runtime_variant=service_store.RUNTIME_VARIANT,
        workload_sha256=WORKLOAD_SHA256, candidate_sha256=candidate_sha256,
        envelope=dict(PINS.bounds), max_lifecycles=2,
        review_id=review_id, envelope_review_id=envelope_review_id,
        footprint_review_id=footprint_review_id)


def validate_review(record):
    try:
        expected = review_record(record['candidate_sha256'], record['review_id'],
                                 record['envelope_review_id'], record['footprint_review_id'])
        if service_store._canonical(record) != service_store._canonical(expected):
            raise ValueError('finite_review_mismatch')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('finite_review_invalid') from error
    return record


def candidate_part(manifest):
    return {key: value for key, value in manifest.items() if key not in REVIEW_FIELDS}


def validate_anchor(anchor):
    if (type(anchor) is not dict or set(anchor) != {'schema', 'profile_id', 'certificate_sha256'}
            or type(anchor['schema']) is not int or anchor['schema'] != 1
            or anchor['profile_id'] != PROFILE_ID
            or (anchor['certificate_sha256'] is not None
                and not smoke_store._digest_valid(anchor['certificate_sha256']))):
        raise ValueError('finite_anchor_invalid')
    return anchor


def bind_manifest(manifest, *, pins=PINS):
    try:
        binding = finite_binding(pins)
        q = validate_review(manifest['qualification'])
        anchor = validate_anchor(manifest['qualification_anchor'])
        if (anchor['certificate_sha256'] is None
                or manifest['qualification_stamp']['sha256'] != anchor['certificate_sha256']
                or q['candidate_sha256'] != service_store._digest(candidate_part(manifest))
                or service_store._canonical(manifest['finite_profile']) != service_store._canonical(binding)
                or manifest['profile'] != PROFILE_ID or manifest['source'] != pins.source_commit
                or service_store._canonical(manifest['bounds']) != service_store._canonical(pins.bounds)
                or manifest['executable'] != str(pins.build/pins.executable_name)
                or manifest['model']['revision'] != pins.model_revision
                or manifest['model']['first_shard'] != str(pins.first_shard)
                or manifest['margin_report']['sha256'] != pins.margin_sha256):
            raise ValueError('finite_manifest_mismatch')
        return q
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('finite_manifest_invalid') from error


def profile_from_manifest(manifest, *, pins=PINS):
    from .smoke_policy import SmokeProfile, _demand
    q = bind_manifest(manifest, pins=pins)
    return SmokeProfile(**_demand(pins), profile_id=PROFILE_ID,
        source_commit=pins.source_commit, model_revision=pins.model_revision,
        qualified=True, review_id=q['review_id'],
        shared_allowance_review_id=q['envelope_review_id'],
        qualification_json=service_store._canonical(q))


def profile_valid(profile, *, pins=PINS):
    from .smoke_policy import SmokeProfile, _demand
    try:
        finite_binding(pins)
        if type(profile) is not SmokeProfile:
            return False
        q = validate_review(json.loads(profile.qualification_json))
        expected = SmokeProfile(**_demand(pins), profile_id=PROFILE_ID,
            source_commit=pins.source_commit, model_revision=pins.model_revision,
            qualified=True, review_id=q['review_id'],
            shared_allowance_review_id=q['envelope_review_id'],
            qualification_json=service_store._canonical(q))
        return (profile == expected and profile.qualified is True
                and all(type(getattr(profile, key)) is int for key in (
                    'gpu_peak_bytes', 'host_peak_bytes',
                    'shared_physical_allowance_bytes', 'commit_peak_bytes')))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
```

Create the anchor with exactly this unapproved content. Implementation must not populate it with a test or synthetic review hash:

```json
{
  "schema": 1,
  "profile_id": "ar4k-service-lifecycle-v1",
  "certificate_sha256": null
}
```

Add these exact registrations to `smoke_store.py`:

```python
# Immediately after INSTALLED_SERVICE:
FINITE_SERVICE = 'ar4k-service-lifecycle-v1'
```

Replace the mapping with the following exact superset:

```python
PROFILE_ROOTS = {PROFILE_ID: 'gufo-ar4k-http-slots-smoke-runs',
                 SERVICE_SMOKE: 'gufo-service-policy-smoke-v1-runs',
                 INSTALLED_SERVICE: 'gufo-native-installed-v1-runs',
                 FINITE_SERVICE: 'gufo-service-lifecycle-v1-runs',
                 BENCHMARK_4K: 'gufo-ar4k-benchmark-v2-runs',
                 BENCHMARK_16K: 'gufo-ar16k-benchmark-v3-runs',
                 MTP_4K: 'gufo-mtp4k-stage-v1-runs',
                 MATCHED_AR: 'gufo-matched-ar4k-v1-runs',
                 MATCHED_AR_V2: 'gufo-matched-ar4k-v2-runs',
                 MATCHED_MTP: 'gufo-matched-mtp4k-v1-runs',
                 MATCHED_MTP_D3: 'gufo-matched-mtp4k-d3-v1-runs'}
```

Replace `profile_bounds` with this complete function:

```python
def profile_bounds(profile_id):
    if profile_id == MATCHED_MTP_D3:
        return MATCHED_MTP_D3_BOUNDS
    if profile_id == MTP_4K:
        return MTP_BOUNDS
    if profile_id == MATCHED_MTP:
        return MATCHED_MTP_BOUNDS
    if profile_id in (PROFILE_ID, BENCHMARK_4K, BENCHMARK_16K, MATCHED_AR,
                       MATCHED_AR_V2, SERVICE_SMOKE, INSTALLED_SERVICE, FINITE_SERVICE):
        return BOUNDS
    raise ValueError('unknown_profile')
```

Insert this finite branch in `_binding` immediately after the unknown-profile rejection, before the existing service branches. Leave all existing branches unchanged:

```python
    if pins.profile_id == FINITE_SERVICE:
        from .finite_profile import finite_binding
        return finite_binding(pins)
```

In `smoke_policy.py`, add `FINITE_SERVICE` to the explicit `.smoke_store` import. Insert these exact branches before the installed branches in the named functions:

```python
# At the beginning of profile_from_manifest, after its docstring:
    if pins.profile_id == FINITE_SERVICE:
        from .finite_profile import profile_from_manifest as finite_profile_from_manifest
        return finite_profile_from_manifest(manifest, pins=pins)

# In _profile_valid, after the existing SmokeProfile/review checks:
    if pins.profile_id == FINITE_SERVICE:
        from .finite_profile import profile_valid as finite_profile_valid
        return finite_profile_valid(profile, pins=pins)
```

Replace only the service-profile condition in `smoke_policy.admission_decision`:

```python
        if pins.profile_id in (SERVICE_SMOKE, INSTALLED_SERVICE, FINITE_SERVICE):
```

Replace `admission._evaluate_service_admission` with this complete function; the arithmetic below it is unchanged:

```python
def _evaluate_service_admission(sample: dict, envelope: dict, *, now: float, pins) -> dict:
    """Internal seam: the closed service binding authenticates candidate identity."""
    from . import smoke_store
    if pins.profile_id == smoke_store.FINITE_SERVICE:
        from .finite_profile import finite_binding
        finite_binding(pins)
    elif pins.profile_id == smoke_store.INSTALLED_SERVICE:
        from .service_store import installed_binding
        installed_binding(pins)
    else:
        from .service_smoke_store import service_binding
        service_binding(pins)
    return _evaluate_admission(sample, envelope, now=now, source_commit=pins.source_commit)
```

- [ ] **Step 4: Confirm GREEN and the old policy contracts.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest discover -s tests/gufo -p test_finite_profile.py -v
python -B -m unittest discover -s tests/gufo -p test_smoke_policy.py -v
python -B -m unittest discover -s tests/gufo -p test_service_store.py -v
```

Expected: all selected offline tests PASS; no helper/model/collector starts. Failure is a stop-and-fix gate, never a reason to widen a binding.

- [ ] **Step 5: Review the finite-only diff and commit the completed unit.** These are later implementation commands, not authorization to run them during planning:

```powershell
git diff --check
git add scripts/gufo_control/finite_profile.py config/gufo-finite-review-anchor.json scripts/gufo_control/smoke_store.py scripts/gufo_control/smoke_policy.py scripts/gufo_control/admission.py tests/gufo/test_finite_profile.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat: register isolated finite GUFO qualification profile"
```

### Task 2: Implement bound two-attempt history and the store contract

**Files:** Create `scripts/gufo_control/finite_store.py`, `tests/gufo/test_finite_store.py`; modify only `_incomplete_latches` in `smoke_store.py`.

**Interfaces consumed:** Task 1 pure profile functions; existing candidate verification and baseline functions; phase executor's `CoverageCertificate` field schema below. This task does not import or instantiate the phase executor, transport, guardian or IPC.

**Interfaces produced:** `FiniteStore()` has `verify_static()`, `recheck_static(manifest, *, current_run=None, prepared_run=None)`, `load_original_operator_baseline()`, `begin_run(run_dir, manifest, baseline)`, `finish_run(run_dir, result)`. Additional explicit adapter seam: `record_admission(run_dir, manifest, current_baseline, frame, *, now, now_utc) -> dict`, called after a fresh real admission; `phase_record(run_dir, manifest, lifecycle, coverage_dict) -> dict` is a pure serializer/validator for later exclusive persistence as `phase-evidence.json`. `inspect_finite_profile() -> dict` reads only and does not initialize evidence roots.

**Durable protocol:** Each `identity.json` includes lifecycle number, manifest/admission hashes and the preceding run's path/identity/result hashes. `current.json` points at the latest immutable identity and gains a terminal result hash only after all checks pass. `incomplete.json` is written exclusively before per-run identity/manifest or any child creation. Failed, partial, missing, tampered or unlinked results never grant attempt 2. Success clears only the latch for this exact owned finite attempt after result and pointer durability; historical or other-profile latches are never cleared. This is not a generic recovery tool.

- [ ] **Step 1: Write the complete failing store tests.**

```python
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import finite_profile as fp, finite_store as fs
from gufo_control import operator_store, service_store, smoke_store
from gufo_control.operator_policy import baseline
from test_operator_policy import frame, series
from test_finite_profile import candidate, qualified

REAL_REVIEW = fs._review


def coverage(run, index):
    count = 66 if index == 1 else 6
    return dict(run_id=run.name, lifecycle=index,
        returned_slots=[f'post-{n:03d}' for n in range(2, count+1)],
        ready_count=1, models_count=1, post_count=count, workers_terminal=True,
        phase_boundaries=[],
        idle_windows=[[n, 50.0+30*i, 80.0+30*i]
                      for i, n in enumerate((6, 18, 30, 48))] if index == 1 else [],
        wave_proofs=[[n, 70.0, 71.0, 72.0] for n in (45, 48)] if index == 1 else [],
        pending_semantic_review=index == 1, failure=None, complete=True)


class FiniteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.evidence = self.root/'gufo-service-lifecycle-v1-runs'; self.evidence.mkdir()
        self.pins = replace(fp.PINS, evidence=self.evidence,
            operator_evidence=self.root/'operator-runs',
            qualification=self.root/'finite-review.json')
        self.anchor = self.root/'anchor.json'
        self.addCleanup(patch.stopall)
        patch.object(fp, 'PINS', self.pins).start()
        patch.object(fs, 'PINS', self.pins).start()
        patch.object(fs, 'ANCHOR_PATH', self.anchor).start()
        self.base = baseline(series())
        self.value = candidate()
        self.value['finite_profile'] = fp.finite_binding(self.pins)
        self.value['operator'] = dict(original_baseline=asdict(self.base), state={})
        self.manifest = qualified(self.value)
        patch.object(fs, '_candidate', return_value=deepcopy(self.value)).start()
        patch.object(fs, '_recheck_candidate').start()
        patch.object(fs, '_review', return_value=(
            self.manifest['qualification'], self.manifest['qualification_stamp'],
            self.manifest['qualification_anchor'], self.manifest['qualification_anchor_stamp'])).start()
        self.clock = patch.object(fs.time, 'monotonic', return_value=14.0).start()
        self.store = fs.FiniteStore()

    def prepared(self, name='run-1', *, start=20):
        m = self.store.verify_static()
        run = self.evidence/name; run.mkdir()
        current = baseline(series(start=start))
        f = frame(start+12)
        self.clock.return_value = f.query_end
        self.store.record_admission(run, m, current, f,
            now=f.query_end, now_utc=f.validated_utc)
        self.store.begin_run(run, m, self.base)
        return run, m

    def result(self, run, manifest, *, index=1, recovered=200.0):
        phase = fs.phase_record(run, manifest, index, coverage(run, index))
        fs._write(run/'phase-evidence.json', phase)
        flags = dict.fromkeys(('owned_exit_confirmed', 'collector_terminal',
            'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
            'inspection_duplicate_closed', 'evidence_write_confirmed', 'cleanup_confirmed'), True)
        return dict(profile=fp.PROFILE_ID, run=str(run), manifest=manifest,
            identity=dict(pid=123, creation_time_100ns=456, executable=manifest['executable']),
            success=True, exit_code=0, resumed_monotonic=40.0 if index == 1 else 240.0,
            recovery_samples=5, service_ready=True, stop_requested=True,
            original_baseline=manifest['operator']['original_baseline'],
            current_baseline=fs._read(run/'finite-admission.json')['current_baseline'],
            finite_phase_sha256=service_store._digest(phase),
            finite_recovery_completed_monotonic=recovered, **flags)

    def test_two_linked_attempts_then_permanent_exhaustion(self):
        first, m1 = self.prepared()
        r1 = self.result(first, m1)
        self.store.finish_run(first, r1)
        second, m2 = self.prepared('run-2', start=220)
        identity = fs._read(second/'identity.json')
        self.assertEqual(identity['previous_run'], str(first))
        self.assertEqual(identity['previous_result_sha256'], service_store._digest(r1))
        self.assertEqual(identity['lifecycle'], 2)
        self.store.finish_run(second, self.result(second, m2, index=2, recovered=300.0))
        with self.assertRaisesRegex(ValueError, 'finite_attempts_exhausted'):
            self.store.verify_static()
        self.assertFalse((self.evidence/'incomplete.json').exists())

    def test_failure_retains_result_and_latch_and_refuses_second(self):
        run, m = self.prepared(); result = self.result(run, m)
        result['success'] = False
        result['cleanup_confirmed'] = False
        self.store.finish_run(run, result)
        before = (run/'result.json').read_bytes()
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()
        with self.assertRaises(ValueError): self.store.finish_run(run, dict(result, success=True))
        self.assertEqual((run/'result.json').read_bytes(), before)

    def test_result_or_phase_tampering_prevents_second(self):
        run, m = self.prepared(); self.store.finish_run(run, self.result(run, m))
        phase = fs._read(run/'phase-evidence.json'); phase['coverage']['post_count'] = 65
        operator_store.atomic_json(run/'phase-evidence.json', phase)
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_missing_structural_evidence_is_not_terminal_success(self):
        run, m = self.prepared()
        result = self.result(run, m)
        (run/'phase-evidence.json').unlink()  # Temporary fixture only.
        with self.assertRaisesRegex(ValueError, 'finite_success_incomplete'):
            self.store.finish_run(run, result)
        self.assertTrue((run/'result.json').exists())
        self.assertEqual(fs._read(run/'result.json'), json.loads(json.dumps(result)))
        self.assertTrue((self.evidence/'incomplete.json').exists())
        self.assertNotIn('result_sha256', fs._read(self.evidence/'current.json'))
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_tampered_phase_raises_after_preserving_incomplete_success(self):
        run, m = self.prepared(); result = self.result(run, m)
        phase = fs._read(run/'phase-evidence.json')
        phase['coverage']['post_count'] = 65
        operator_store.atomic_json(run/'phase-evidence.json', phase)
        with self.assertRaisesRegex(ValueError, 'finite_success_incomplete'):
            self.store.finish_run(run, result)
        self.assertEqual(fs._read(run/'result.json'), json.loads(json.dumps(result)))
        self.assertTrue((self.evidence/'incomplete.json').exists())
        self.assertNotIn('result_sha256', fs._read(self.evidence/'current.json'))
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_incomplete_terminal_flags_and_coverage_fail_closed(self):
        run = self.evidence/'candidate'; run.mkdir()
        c = coverage(run, 1)
        for key, value in (('complete', False), ('workers_terminal', False),
                           ('post_count', 65), ('ready_count', True),
                           ('failure', 'missed_overlap'), ('lifecycle', 2)):
            changed = deepcopy(c); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                fs.phase_record(run, self.manifest, 1, changed)
        good = fs.phase_record(run, self.manifest, 1, c)
        self.assertTrue(good['coverage']['pending_semantic_review'])
        self.assertEqual(good['acceptance'], 'structural_only')

    def test_old_failed_root_and_other_profile_latch_block_finite(self):
        for name in ('gufo-ar4k-connect-wait-smoke-runs', 'gufo-native-installed-v1-runs'):
            root = self.root/name; root.mkdir()
            operator_store.atomic_json(root/'incomplete.json', {'historical': True})
            before = (root/'incomplete.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
                self.store.verify_static()
            self.assertEqual((root/'incomplete.json').read_bytes(), before)
            (root/'incomplete.json').unlink()  # Temporary fixture only.

    def test_current_recheck_exempts_only_exact_owned_finite_latch(self):
        run, m = self.prepared()
        self.store.recheck_static(m, current_run=run)
        old = self.root/'gufo-ar4k-smoke-runs'; old.mkdir()
        operator_store.atomic_json(old/'incomplete.json', {'old': True})
        with self.assertRaises(ValueError): self.store.recheck_static(m, current_run=run)

    def test_finite_latch_is_visible_to_existing_profile(self):
        run, m = self.prepared()
        installed = replace(service_store.PINS, evidence=self.root/'gufo-native-installed-v1-runs',
                            operator_evidence=self.root/'operator-runs')
        with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
            smoke_store._incomplete_latches(installed)

    def test_fresh_admission_required_and_first_recovery_precedes_second(self):
        first, m = self.prepared(); self.store.finish_run(first, self.result(first, m))
        run = self.evidence/'run-2'; run.mkdir()
        with self.assertRaises(ValueError): self.store.begin_run(run, m, self.base)
        f = frame(32)
        with self.assertRaisesRegex(ValueError, 'finite_admission_before_recovery'):
            self.store.record_admission(run, m, baseline(series(start=20)), f,
                now=f.query_end, now_utc=f.validated_utc)
        current = baseline(series(start=220)); f = frame(232)
        self.clock.return_value = f.query_end
        self.store.record_admission(run, m, current, f,
            now=f.query_end, now_utc=f.validated_utc)
        self.clock.return_value += 3
        with self.assertRaisesRegex(ValueError, 'finite_admission_stale'):
            self.store.begin_run(run, m, self.base)

    def test_orphan_and_link_cycle_rejected(self):
        run, m = self.prepared(); self.store.finish_run(run, self.result(run, m))
        orphan = self.evidence/'orphan'; orphan.mkdir()
        with self.assertRaisesRegex(ValueError, 'finite_orphan'):
            self.store.verify_static()
        orphan.rmdir()  # Temporary fixture only.
        pointer = fs._read(self.evidence/'current.json')
        identity = fs._read(run/'identity.json'); identity['previous_run'] = str(run)
        operator_store.atomic_json(run/'identity.json', identity)
        pointer['identity_sha256'] = service_store._digest(identity)
        operator_store.atomic_json(self.evidence/'current.json', pointer)
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_partial_begin_never_grants_another_attempt(self):
        run = self.evidence/'run-1'; run.mkdir()
        f = frame(32); self.clock.return_value = f.query_end
        self.store.record_admission(run, self.manifest, baseline(series(start=20)), f,
            now=f.query_end, now_utc=f.validated_utc)
        real = fs._write
        def fail_manifest(path, value):
            if Path(path).name == 'manifest.json': raise OSError('disk full')
            return real(path, value)
        with patch.object(fs, '_write', side_effect=fail_manifest), self.assertRaises(OSError):
            self.store.begin_run(run, self.manifest, self.base)
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()

    def test_read_only_inspection_never_creates_files(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        self.assertTrue(fs.inspect_finite_profile()['reviewed'])
        self.assertEqual(sorted(str(p) for p in self.root.rglob('*')), before)

    def test_absent_null_and_tampered_review_are_not_launch_authority(self):
        with patch.object(fs, '_review', wraps=REAL_REVIEW):
            with self.assertRaises((ValueError, OSError)):
                self.store.verify_static()
            operator_store.atomic_json(self.anchor, dict(schema=1, profile_id=fp.PROFILE_ID,
                                                         certificate_sha256=None))
            with self.assertRaisesRegex(ValueError, 'finite_review_absent'):
                self.store.verify_static()
            q = fp.review_record(service_store._digest(self.value), 'finite-review',
                                  'header-envelope', 'controller-footprint')
            operator_store.atomic_json(self.pins.qualification, q)
            digest = operator_store.artifact_record(self.pins.qualification)['sha256']
            operator_store.atomic_json(self.anchor, dict(schema=1, profile_id=fp.PROFILE_ID,
                                                         certificate_sha256=digest))
            self.assertEqual(self.store.verify_static()['qualification'], q)
            operator_store.atomic_json(self.pins.qualification, dict(q, review_id='tampered'))
            with self.assertRaises(ValueError): self.store.verify_static()

    def test_current_recheck_detects_prior_result_change(self):
        first, m1 = self.prepared(); self.store.finish_run(first, self.result(first, m1))
        second, m2 = self.prepared('run-2', start=220)
        previous = fs._read(first/'result.json'); previous['recovery_samples'] = 4
        operator_store.atomic_json(first/'result.json', previous)
        with self.assertRaises(ValueError): self.store.recheck_static(m2, current_run=second)

    def test_terminal_pointer_write_failure_keeps_incomplete_latch(self):
        run, m = self.prepared(); result = self.result(run, m)
        with patch.object(operator_store, 'atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.finish_run(run, result)
        self.assertTrue((run/'result.json').exists())
        self.assertTrue((self.evidence/'incomplete.json').exists())
        with self.assertRaises(ValueError): self.store.verify_static()


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Confirm RED.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest discover -s tests/gufo -p test_finite_store.py -v
```

Expected: import failure for absent `finite_store`.

- [ ] **Step 3: Add the complete store module.**

```python
"""Private two-attempt evidence; no process, telemetry or recovery execution."""
from dataclasses import asdict
import math
from pathlib import Path
import time

from . import build_identity, finite_profile as fp, operator_store
from . import runtime_package, service_store, smoke_store
from .benchmark_runtime import BoundPolicy, BoundStore
from .finite_ledger import _read as strict_read, _exclusive
from .finite_workload import WORKLOAD_PATH, WORKLOAD_SHA256, load_workload
from .operator_policy import MAX_PRELAUNCH_AGE_SECONDS

PINS = fp.PINS
ANCHOR_PATH = fp.ANCHOR_PATH
LIMIT = 2*1024*1024
_digest = service_store._digest
_canonical = service_store._canonical


def _read(path):
    return strict_read(Path(path), LIMIT)


def _write(path, value):
    return _exclusive(Path(path), value, LIMIT)


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _run(pins, value):
    raw = Path(value)
    root = build_identity.checked_path(pins.evidence, directory=True)
    run = build_identity.checked_path(raw, directory=True)
    if raw != run or run.parent != root:
        raise ValueError('finite_run_path')
    return run


def _source(pins):
    return build_identity.verify_git(
        build_identity.checked_path(pins.source, directory=True), Path('git'),
        remote=service_store.SOURCE_REMOTE, head=pins.source_commit,
        tree=service_store.SOURCE_TREE, base=service_store.SOURCE_BASE)


def _candidate(pins):
    binding = fp.finite_binding(pins)
    _source(pins)
    load_workload()
    package = runtime_package.verify_runtime(pins.build, variant=service_store.RUNTIME_VARIANT)
    if package.get('policy_sha256') != service_store.RUNTIME_POLICY_SHA256:
        raise ValueError('finite_runtime_policy')
    artifacts = smoke_store._verify_candidate_artifacts(
        pins, model_validator=smoke_store.validate_ar4k_model)
    original, state = smoke_store._operator_sequence(pins)
    margin = smoke_store._checked_artifact(pins.margin_report,
        (pins.margin_report.stat().st_size, pins.margin_sha256), 'candidate_margin')
    return dict(profile=fp.PROFILE_ID, source=pins.source_commit,
        bounds=dict(pins.bounds), finite_profile=binding, **artifacts,
        operator=dict(original_baseline=asdict(original), state=state),
        margin_report=margin, workload_stamp=operator_store.artifact_record(WORKLOAD_PATH),
        controller_artifacts=service_store.controller_artifacts(), runtime_package=package,
        runtime_manifest=operator_store.artifact_record(pins.build/'runtime-manifest.json'))


def _recheck_candidate(manifest, pins):
    fp.finite_binding(pins)
    _source(pins)
    smoke_store._recheck_candidate_artifacts(manifest, pins)
    load_workload()
    original, state = smoke_store._operator_sequence(pins)
    if (not _same(manifest['operator'], dict(original_baseline=asdict(original), state=state))
            or manifest['controller_artifacts'] != service_store.controller_artifacts()
            or manifest['workload_stamp'] != operator_store.artifact_record(WORKLOAD_PATH)
            or manifest['runtime_manifest'] != operator_store.artifact_record(pins.build/'runtime-manifest.json')
            or manifest['runtime_package'] != runtime_package.verify_runtime(
                pins.build, variant=service_store.RUNTIME_VARIANT)
            or {k: v for k, v in manifest['margin_report'].items() if k != 'label'} !=
                operator_store.artifact_record(pins.margin_report)):
        raise ValueError('finite_candidate_changed')


def _review(candidate, pins):
    build_identity.checked_path(ANCHOR_PATH)
    anchor = _read(ANCHOR_PATH)
    fp.validate_anchor(anchor)
    if anchor['certificate_sha256'] is None:
        raise ValueError('finite_review_absent')
    build_identity.checked_path(pins.qualification)
    q = _read(pins.qualification)
    fp.validate_review(q)
    # Strict bounded parsing precedes the reused hashing/parser helper.
    if any(path.stat().st_size > LIMIT for path in (ANCHOR_PATH, pins.qualification)):
        raise ValueError('finite_record_size')
    hashed_anchor, anchor_stamp = smoke_store._json_artifact(
        ANCHOR_PATH, None, 'finite_review_anchor')
    hashed_q, stamp = smoke_store._json_artifact(pins.qualification,
        anchor['certificate_sha256'], 'finite_review')
    if (not _same(anchor, hashed_anchor) or not _same(q, hashed_q)
            or not _same(anchor, _read(ANCHOR_PATH))
            or not _same(q, _read(pins.qualification))):
        raise ValueError('finite_review_changed')
    if q['candidate_sha256'] != _digest(candidate):
        raise ValueError('finite_review_candidate_changed')
    return q, stamp, anchor, anchor_stamp


def phase_record(run_dir, manifest, lifecycle, coverage):
    """Validate serialization only; live receipt provenance belongs to the wrapper."""
    run = Path(run_dir)
    expected_keys = {'run_id', 'lifecycle', 'returned_slots', 'ready_count', 'models_count',
        'post_count', 'workers_terminal', 'phase_boundaries', 'idle_windows', 'wave_proofs',
        'pending_semantic_review', 'failure', 'complete'}
    posts = 66 if lifecycle == 1 else 6
    if (type(lifecycle) is not int or lifecycle not in (1, 2)
            or type(coverage) is not dict or set(coverage) != expected_keys
            or coverage['run_id'] != run.name or type(coverage['lifecycle']) is not int
            or coverage['lifecycle'] != lifecycle or coverage['complete'] is not True
            or coverage['workers_terminal'] is not True or coverage['failure'] is not None
            or type(coverage['pending_semantic_review']) is not bool
            or type(coverage['ready_count']) is not int or not 1 <= coverage['ready_count'] <= 240
            or type(coverage['models_count']) is not int or coverage['models_count'] != 1
            or type(coverage['post_count']) is not int or coverage['post_count'] != posts
            or type(coverage['returned_slots']) not in (list, tuple)
            or len(coverage['returned_slots']) != posts-1
            or set(coverage['returned_slots']) != {f'post-{n:03d}' for n in range(2, posts+1)}
            or type(coverage['phase_boundaries']) not in (list, tuple)
            or type(coverage['idle_windows']) not in (list, tuple)
            or type(coverage['wave_proofs']) not in (list, tuple)):
        raise ValueError('finite_phase_incomplete')
    idle, waves = coverage['idle_windows'], coverage['wave_proofs']
    if (len(idle) != (4 if lifecycle == 1 else 0)
            or len(waves) != (2 if lifecycle == 1 else 0)):
        raise ValueError('finite_phase_coverage')
    # Executor owns durations/rendezvous semantics. Store rejects malformed serialized proof.
    for rows, width in ((coverage['phase_boundaries'], 2), (idle, 3), (waves, 4)):
        for row in rows:
            if (type(row) not in (list, tuple) or len(row) != width
                    or type(row[0]) is not int or not 1 <= row[0] <= posts
                    or any(not _time(t) for t in row[1:])):
                raise ValueError('finite_phase_proof')
    if lifecycle == 1 and ([row[0] for row in idle] != [6, 18, 30, 48]
                           or [row[0] for row in waves] != [45, 48]):
        raise ValueError('finite_phase_schedule')
    if (any(row[2]-row[1] < 30 for row in idle)
            or any(not row[1] <= row[2] <= row[3] for row in waves)):
        raise ValueError('finite_phase_timing')
    return dict(schema=1, profile=fp.PROFILE_ID, run=str(run), lifecycle=lifecycle,
        manifest_sha256=_digest(manifest), workload_sha256=WORKLOAD_SHA256,
        acceptance='structural_only', coverage=coverage)


def _terminal(run, manifest, identity, result):
    admission = _read(run/'finite-admission.json')
    if (type(result) is not dict or result.get('run') != str(run)
            or result.get('profile') != fp.PROFILE_ID
            or not _same(result.get('manifest'), manifest)
            or not _same(result.get('original_baseline'), manifest['operator']['original_baseline'])
            or not _same(result.get('current_baseline'), admission['current_baseline'])
            or not service_store._clean(result)
            or result.get('service_ready') is not True or result.get('stop_requested') is not True
            or not _time(result.get('finite_recovery_completed_monotonic'))
            or result['finite_recovery_completed_monotonic'] < result['resumed_monotonic']):
        raise ValueError('finite_terminal_incomplete')
    phase = _read(run/'phase-evidence.json')
    expected = phase_record(run, manifest, identity['lifecycle'], phase['coverage'])
    if (not _same(phase, expected) or result.get('finite_phase_sha256') != _digest(phase)):
        raise ValueError('finite_terminal_phase')
    return result


def _history(pins, *, prepared_run=None, active_run=None):
    root = build_identity.checked_path(pins.evidence, directory=True, exists=False)
    if not root.exists():
        if prepared_run is not None: raise ValueError('finite_prepared_missing')
        return []
    if active_run is not None and prepared_run is not None:
        raise ValueError('finite_run_phase_ambiguous')
    prepared = _run(pins, prepared_run) if prepared_run is not None else None
    if prepared and any((prepared/n).exists() for n in ('manifest.json', 'identity.json', 'result.json')):
        raise ValueError('finite_prepared_not_fresh')
    if (root/'attempt.json').exists(): raise ValueError('finite_legacy_attempt')
    pointer = _read(root/'current.json') if (root/'current.json').exists() else None
    active_identity = None
    if active_run is not None:
        prepared = _run(pins, active_run)
        active_identity = _read(prepared/'identity.json')
        pointer = (dict(profile=fp.PROFILE_ID, run=active_identity['previous_run'],
            identity_sha256=active_identity['previous_identity_sha256'],
            result_sha256=active_identity['previous_result_sha256'])
            if active_identity['previous_run'] is not None else None)
    chain, seen = [], set()
    while pointer is not None:
        if (type(pointer) is not dict or set(pointer) !=
                {'profile', 'run', 'identity_sha256', 'result_sha256'}
                or pointer['profile'] != fp.PROFILE_ID or len(chain) >= 2):
            raise ValueError('finite_history_pointer')
        run = _run(pins, pointer['run'])
        if run in seen: raise ValueError('finite_history_cycle')
        seen.add(run)
        identity, manifest, result = (_read(run/name) for name in
                                     ('identity.json', 'manifest.json', 'result.json'))
        keys = {'profile', 'run', 'lifecycle', 'manifest_sha256', 'admission_sha256',
                'previous_run', 'previous_identity_sha256', 'previous_result_sha256'}
        if (type(identity) is not dict or set(identity) != keys
                or identity['profile'] != fp.PROFILE_ID or identity['run'] != str(run)
                or type(identity['lifecycle']) is not int or identity['lifecycle'] not in (1, 2)
                or identity['manifest_sha256'] != _digest(manifest)
                or pointer['identity_sha256'] != _digest(identity)
                or pointer['result_sha256'] != _digest(result)
                or identity['admission_sha256'] != _digest(_read(run/'finite-admission.json'))):
            raise ValueError('finite_history_identity')
        _terminal(run, manifest, identity, result)
        chain.append(dict(run=run, identity=identity, result=result))
        previous = identity['previous_run']
        if previous is None:
            if (identity['lifecycle'] != 1 or identity['previous_identity_sha256'] is not None
                    or identity['previous_result_sha256'] is not None):
                raise ValueError('finite_history_origin')
            pointer = None
        else:
            if identity['lifecycle'] != 2: raise ValueError('finite_history_order')
            pointer = dict(profile=fp.PROFILE_ID, run=previous,
                identity_sha256=identity['previous_identity_sha256'],
                result_sha256=identity['previous_result_sha256'])
    chain.reverse()
    if [row['identity']['lifecycle'] for row in chain] != list(range(1, len(chain)+1)):
        raise ValueError('finite_history_order')
    if active_identity is not None and (active_identity['lifecycle'] != len(chain)+1
            or (not chain and (active_identity['previous_identity_sha256'] is not None
                              or active_identity['previous_result_sha256'] is not None))):
        raise ValueError('finite_history_order')
    for entry in root.iterdir():
        build_identity.checked_path(entry, directory=entry.is_dir())
        if entry.is_dir() and entry not in seen and entry != prepared:
            raise ValueError('finite_orphan')
    return chain


def _current_run_markers(manifest, pins, current_run):
    run = _run(pins, current_run)
    pointer, latch, identity = (_read(path) for path in
        (pins.evidence/'current.json', pins.evidence/'incomplete.json', run/'identity.json'))
    identity_keys = {'profile', 'run', 'lifecycle', 'manifest_sha256', 'admission_sha256',
                     'previous_run', 'previous_identity_sha256', 'previous_result_sha256'}
    if (type(identity) is not dict or set(identity) != identity_keys
            or not _same(pointer, dict(profile=fp.PROFILE_ID, run=str(run), identity_sha256=_digest(identity)))
            or not _same(latch, dict(run=str(run), phase='before_create',
                original_baseline=manifest['operator']['original_baseline']))
            or identity.get('profile') != fp.PROFILE_ID or identity.get('run') != str(run)
            or type(identity.get('lifecycle')) is not int or identity['lifecycle'] not in (1, 2)
            or identity.get('manifest_sha256') != _digest(manifest)
            or identity.get('admission_sha256') != _digest(_read(run/'finite-admission.json'))
            or not _same(_read(run/'manifest.json'), manifest) or (run/'result.json').exists()):
        raise ValueError('finite_current_mismatch')
    history = _history(pins, active_run=run)
    if history and not _same(history[0]['result']['manifest'], manifest):
        raise ValueError('finite_pair_manifest_changed')


class FiniteStore(BoundStore):
    def __init__(self):
        super().__init__(PINS)

    def verify_static(self):
        smoke_store._incomplete_latches(self.PINS)
        history = _history(self.PINS)
        if len(history) == 2: raise ValueError('finite_attempts_exhausted')
        manifest = _candidate(self.PINS)
        q, stamp, anchor, anchor_stamp = _review(manifest, self.PINS)
        manifest.update(qualification=q, qualification_stamp=stamp,
            qualification_anchor=anchor, qualification_anchor_stamp=anchor_stamp)
        fp.bind_manifest(manifest, pins=self.PINS)
        if history and not _same(history[0]['result']['manifest'], manifest):
            raise ValueError('finite_pair_manifest_changed')
        return manifest

    def recheck_static(self, manifest, *, current_run=None, prepared_run=None):
        if current_run is not None and prepared_run is not None:
            raise ValueError('finite_run_phase_ambiguous')
        fp.bind_manifest(manifest, pins=self.PINS)
        smoke_store._incomplete_latches(self.PINS, manifest=manifest, current_run=current_run)
        _recheck_candidate(manifest, self.PINS)
        q, stamp, anchor, anchor_stamp = _review(fp.candidate_part(manifest), self.PINS)
        if not _same((q, stamp, anchor, anchor_stamp), tuple(manifest[k] for k in
                ('qualification', 'qualification_stamp', 'qualification_anchor', 'qualification_anchor_stamp'))):
            raise ValueError('finite_review_changed')
        if current_run is not None:
            _current_run_markers(manifest, self.PINS, current_run)
        elif len(_history(self.PINS, prepared_run=prepared_run)) >= 2:
            raise ValueError('finite_attempts_exhausted')

    def load_original_operator_baseline(self):
        return smoke_store._load_original_operator_baseline(self.PINS)

    def record_admission(self, run_dir, manifest, current_baseline, frame, *, now, now_utc):
        run = _run(self.PINS, run_dir)
        self.recheck_static(manifest, prepared_run=run)
        history = _history(self.PINS, prepared_run=run)
        original = smoke_store._baseline(manifest['operator']['original_baseline'])
        policy = BoundPolicy(self.PINS)
        effective = policy.stricter_runtime_baseline(original, current_baseline)
        if history and current_baseline.first_start <= history[-1]['result']['finite_recovery_completed_monotonic']:
            raise ValueError('finite_admission_before_recovery')
        decision = policy.admission_decision(policy.profile_from_manifest(manifest),
            effective, frame, now=now, now_utc=now_utc)
        if decision['allowed'] is not True: raise ValueError('finite_admission_refused')
        if not _time(now) or not 0 <= time.monotonic()-now <= MAX_PRELAUNCH_AGE_SECONDS:
            raise ValueError('finite_admission_stale')
        proof = dict(schema=1, profile=fp.PROFILE_ID, run=str(run), lifecycle=len(history)+1,
            manifest_sha256=_digest(manifest), current_baseline=asdict(current_baseline),
            decision=decision, checked_monotonic=now, query_start=frame.query_start,
            query_end=frame.query_end, sample=frame.snapshot)
        _write(run/'finite-admission.json', proof)
        return proof

    def begin_run(self, run_dir, manifest, baseline):
        run = _run(self.PINS, run_dir)
        self.recheck_static(manifest, prepared_run=run)
        history = _history(self.PINS, prepared_run=run)
        if not _same(asdict(baseline), manifest['operator']['original_baseline']):
            raise ValueError('finite_original_baseline_changed')
        proof = _read(run/'finite-admission.json')
        if (proof.get('profile') != fp.PROFILE_ID or proof.get('run') != str(run)
                or type(proof.get('lifecycle')) is not int or proof['lifecycle'] != len(history)+1
                or proof.get('manifest_sha256') != _digest(manifest)
                or proof.get('decision', {}).get('allowed') is not True
                or not _time(proof.get('query_start'))
                or not 0 <= time.monotonic()-proof['query_start'] <= MAX_PRELAUNCH_AGE_SECONDS):
            raise ValueError('finite_admission_stale')
        previous = history[-1] if history else None
        if previous and not _same(previous['result']['manifest'], manifest):
            raise ValueError('finite_pair_manifest_changed')
        if previous and proof['current_baseline']['first_start'] <= previous['result']['finite_recovery_completed_monotonic']:
            raise ValueError('finite_admission_before_recovery')
        identity = dict(profile=fp.PROFILE_ID, run=str(run), lifecycle=len(history)+1,
            manifest_sha256=_digest(manifest), admission_sha256=_digest(proof),
            previous_run=str(previous['run']) if previous else None,
            previous_identity_sha256=_digest(previous['identity']) if previous else None,
            previous_result_sha256=_digest(previous['result']) if previous else None)
        _write(self.EVIDENCE/'incomplete.json', dict(run=str(run), phase='before_create',
            original_baseline=asdict(baseline)))
        _write(run/'manifest.json', manifest)
        _write(run/'identity.json', identity)
        operator_store.atomic_json(self.EVIDENCE/'current.json', dict(profile=fp.PROFILE_ID,
            run=str(run), identity_sha256=_digest(identity)))

    def finish_run(self, run_dir, result):
        run = _run(self.PINS, run_dir)
        manifest = _read(run/'manifest.json')
        _current_run_markers(manifest, self.PINS, run)
        identity = _read(run/'identity.json')
        # Always preserve the first terminal report, including failure/incomplete evidence.
        _write(run/'result.json', result)
        try:
            _terminal(run, manifest, identity, result)
        except (ValueError, OSError, KeyError, TypeError) as error:
            if type(result) is dict and result.get('success') is True:
                raise ValueError('finite_success_incomplete') from error
            return
        latch = _read(self.EVIDENCE/'incomplete.json')
        if not _same(latch, dict(run=str(run), phase='before_create',
                               original_baseline=manifest['operator']['original_baseline'])):
            raise ValueError('finite_latch_changed')
        operator_store.atomic_json(self.EVIDENCE/'current.json', dict(profile=fp.PROFILE_ID,
            run=str(run), identity_sha256=_digest(identity), result_sha256=_digest(result)))
        # Only this exact finite run's owned latch, after durable terminal evidence.
        if not _same(_read(self.EVIDENCE/'incomplete.json'), latch):
            raise ValueError('finite_latch_changed')
        (self.EVIDENCE/'incomplete.json').unlink()


def inspect_finite_profile():
    result = dict(profile=fp.PROFILE_ID, artifacts_valid=False, reviewed=False,
        history_valid=False, attempts_completed=None, next_lifecycle=None,
        installed_service_accepted=False, refusals=[])
    try:
        candidate = _candidate(PINS)
        result['artifacts_valid'] = True
        _review(candidate, PINS)
        result['reviewed'] = True
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    try:
        smoke_store._incomplete_latches(PINS)
        history = _history(PINS)
        result.update(history_valid=True, attempts_completed=len(history),
                      next_lifecycle=len(history)+1 if len(history) < 2 else None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    return result
```

Replace `_incomplete_latches` with this complete function. The historical roots and installed dispatch are retained verbatim in meaning; only the finite dispatch is new:

```python
def _incomplete_latches(pins, *, manifest=None, current_run=None):
    if (pins.operator_evidence / 'incomplete.json').exists():
        raise ValueError('operator_incomplete')
    roots = {pins.evidence, *(pins.evidence.parent / name for name in (
        'gufo-ar4k-smoke-runs', 'gufo-ar4k-connect-wait-smoke-runs',
        'gufo-ar4k-benchmark-runs', 'gufo-ar16k-benchmark-runs',
        'gufo-ar16k-benchmark-v2-runs', *PROFILE_ROOTS.values()))}
    for root in roots:
        if (root / 'incomplete.json').exists():
            if current_run is not None and root.resolve() == pins.evidence.resolve():
                if pins.profile_id == FINITE_SERVICE:
                    from .finite_store import _current_run_markers as finite_current_run_markers
                    finite_current_run_markers(manifest, pins, current_run)
                elif pins.profile_id == INSTALLED_SERVICE:
                    from .service_store import _current_run_markers as installed_current_run_markers
                    installed_current_run_markers(manifest, pins, current_run)
                else:
                    _current_run_markers(manifest, pins, current_run)
            else:
                raise ValueError('prior_smoke_incomplete')
```

- [ ] **Step 4: Confirm GREEN and existing store regressions.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest discover -s tests/gufo -p test_finite_store.py -v
python -B -m unittest discover -s tests/gufo -p test_finite_profile.py -v
python -B -m unittest discover -s tests/gufo -p test_smoke_store.py -v
python -B -m unittest discover -s tests/gufo -p test_service_store.py -v
python -B -m unittest discover -s tests/gufo -p test_benchmark_runtime.py -v
```

Expected: all selected offline tests PASS. These tests create synthetic evidence only below temporary roots; they do not touch the real finite or historical roots.

- [ ] **Step 5: Review and commit this unit, then stop.**

```powershell
git diff --check
git add scripts/gufo_control/finite_store.py scripts/gufo_control/smoke_store.py tests/gufo/test_finite_store.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat: persist two linked finite GUFO lifecycles"
```

## Exact later integration boundary (not implementation in this task)

The later finite wrapper must hold the existing exclusive root lock across each lifecycle, instantiate `FiniteStore()` and `BoundPolicy(fp.PINS)`, and use the exact profile ID. It must neither call installed service entrypoints nor relax installed lease acceptance. Registration does not itself create an executable launch path.

The current guardian passes `prepared_run` only for `isinstance(store, InstalledStore)` in `_prelaunch`. The finite wrapper must explicitly call `recheck_static(manifest, prepared_run=run_dir)` after allocating its exact directory and while it contains baseline/telemetry evidence, before `begin_run`; no directory search or broad orphan exemption is acceptable. Call `record_admission` after the complete fresh current baseline, with the actual final admission `Frame`, current baseline and validated times. Keep the guardian's additional fresh admission immediately before create. If hashing or evidence writes consume freshness, fail closed; any planned refreshing must still occur before the attempt latch and before child creation, with no hidden inference retry. The current one-shot admission evidence can be replaced only by a separately designed pre-attempt refresh protocol, not by overwriting immutable evidence.

The first `record_admission`/`begin_run` consumes lifecycle 1. Lifecycle 2 requires the entire linked first `result.json`, bound `phase-evidence.json`, strict terminal flags and exactly five recovered samples. Its new baseline must start strictly after `finite_recovery_completed_monotonic` from lifecycle 1; stale admission, restarts that invalidate monotonic ordering, incomplete recovery or a known failure refuse it. This ordering check is in addition to the existing full telemetry/admission logic; it is not a substitute for properly scoped counters.

Readiness and continuation preserve the same in-process `Ledger`, `FiniteTransport` and live `ReturnedReceipt` identity. They can remain inside the finite guardian while the authenticated parent coordinates/statuses/stops; do not reconstruct a second client from disk. The readiness case is POST 1, already counted. The store's serialized certificate cannot recreate a live receipt or prove IPC authentication; it merely binds the reviewed wrapper's complete phase output to durable lifecycle evidence.

`finite_phase.CoverageCertificate` in `docs/superpowers/plans/2026-09-27-gufo-finite-phase.md` has fields `run_id, lifecycle, returned_slots, ready_count, models_count, post_count, workers_terminal, phase_boundaries, idle_windows, wave_proofs, pending_semantic_review, failure, complete`. Its `returned_slots` contains continuation POST slots 2 onward, not readiness GET/model/POST-1 receipts. The wrapper passes `dataclasses.asdict(certificate)` to `phase_record(run_dir, manifest, index, coverage_dict)`, writes that record exclusively to `run_dir/'phase-evidence.json'`, and supplies its canonical digest as `finite_phase_sha256` in the guardian result. Only after confirmed recovery may it attach `finite_recovery_completed_monotonic`, sampled after the fifth confirmed recovered sample. Coverage success and all terminal proofs must reach `finish_run` together.

In the current guardian `_persist`, `store.finish_run` precedes `lifecycle.on_result`. Binding phase/recovery fields only in `on_result` is too late. A finite-specific result hook must enrich the result before persistence. The current `_terminal_failure` special-cases installed stores to preserve terminal evidence, while its generic branch overwrites `result.json`; the later finite integration must give finite immutable terminal evidence the same preservation. No such guardian changes belong to this store plan.

`finish_run` preserves every first terminal report before validating it. If a report claims `success=True` but its structural or terminal binding fails, it raises `finite_success_incomplete` after retaining that immutable report and the incomplete latch; it does not return a successful persistence outcome or add a terminal result hash to the pointer. The future finite guardian must surface failure and retain separate failure evidence without overwriting `result.json`. Reports already declaring failure retain the normal non-raising retention path. Neither case grants a second attempt.

The returned complete coverage may include pending prose review. The store permits that structural state for the second bounded lifecycle but always labels the phase record `acceptance='structural_only'`; it never creates public/installed acceptance. Final semantic review still binds exact saved response hashes, reviewer identity, verdicts and reasons. The finite review certificate here binds source/runtime/model/controller/workload/envelope and controller footprint before launch; it is distinct from these later semantic verdicts.

The review file `C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-v1-review.json` and its pinned anchor hash remain absent/null until the existing finite controller/footprint review is completed and separately bound. Generating a candidate or expected review dictionary is not review completion. No commands in this report populate that certificate, clear a historical latch, invoke recovery, collect telemetry or launch a model.

## Self-review and frozen handoff

- The two tasks are independent review units: closed pure profile/policy registration, then durable two-attempt storage. Neither is an orchestration task.
- Spec coverage: provenance/envelope/workload are in Task 1 and candidate verification; historical blocking, retention, exactly two attempts, fresh second admission, structural phase binding and cleanup/recovery are in Task 2. Semantic acceptance, live ownership, IPC, transport and sampled peaks are explicitly later boundaries, not claimed implemented here.
- Reuse avoids copying `InstalledStore` or weakening it. Existing arithmetic and strict terminal predicate remain unchanged; finite source admission dispatch is the only arithmetic entrypoint edit.
- No tests or implementation were run while writing this report. The checkout was observed on `codex/gufo-native-integration`; the workload raw hash was read and matched the pinned value above.
- Plan is frozen on handoff. Parent should review the complete code/tests and exact phase-certificate interface before executing. The historical failed recovery remains blocking regardless of offline test success.
