# GUFO final-sample refresh implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execution and parallel independent review are already selected by the user; no new design approval is needed.

**Goal:** Complete the approved native PP8192/cache experiment by obtaining fresh telemetry after bounded setup, without weakening the final admission checks or replaying consumed evidence.

**Architecture:** Keep the early admission before permanent attempt consumption. After setup, take one new final-precreate frame, recheck static identity again, then admit that frame and retain the final no-I/O age check before creating the owned suspended process. Name the next16k experiment v2 while preserving the refusedv1 and successful4k-v2.

**Tech Stack:** Existing Python standard-library Guardian/store/recipes, fake-clock unittest harness, unchanged native GUFO binary.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, branch codex/gufo-native-integration. Preserve all working Halogen/native/27B installations and unrelated changes. No public push/release, D:, BIOS/carve/driver/services/security/pagefile/WSL/reboot changes.
- At least49 GiB Windows available physical before launch;24 GiB runtime stop floor;12 GiB commit reserve. Unchanged68/4/20 GiB GPU/host/shared allowance and84 GiB required prelaunch commit headroom. No concurrent inference model. Stop thresholds are not reservations.
- Query duration<=2s, final sample age<=2s, runtime age<=5s; nonoverlapping queries with starts>=1s apart. Keep480s startup,60s/request,600s owned lifetime,10s cleanup and60s recovery. Exact owned Job-tree termination, all worker/handle/evidence gates and five recovery frames remain mandatory.
- No removal or weakening of static identity, pin, predecessor, current-run marker, port, admission, ownership or last no-I/O age checks. Keep the final static recheck after the refreshed query so mutations during collection are caught.
- No retry loop, reset/deletion of any attempt/latch/result/qualification, or automatic repeated model launch. All real evidence is immutable. Implementer does offline work only; parent owns review, qualification and one separately named real experiment.
- Model/binary/runtime pins,36-request4k recipe and13-request16k workload, samplers, prompt bytes, validator_version2, API limits, capacities, AR/noMTP and cache modes remain unchanged. The4k profile and acceptance digest stay intact.

## Evidence behind the change

16kv1 result47C4B355C470808052F08BF2BE2997DAFBD3DFCC7CFE4D0506BB29776AD53F7A:
one frame admitted at1.656s, refused after setup at2.062s; identity/resumed null,
all cleanup flags true, five recovery samples. Query1.453s, available50.252 GiB.
Successful4kv2 same-code second admission was1.985s, nearly expired. Independent
audit_16k_precreate_age confirmed setup/evidence work ages the reused frame.

## Task 1: Refresh final telemetry and version the16k experiment

**Files:** scripts/gufo_control/smoke_guard.py, smoke_store.py, benchmark_recipes.py, benchmark_guard.py; tests/gufo/test_smoke_guard.py, test_smoke_store.py, test_benchmark_guard.py, test_benchmark_recipes.py, test_benchmark_runtime.py and test_smoke_policy.py only for necessary fixed-identity expectations. No HTTP client/suite scheduling/native source edits.

**Interfaces:** Keep all signatures. Existing Harness offers clock/query_delay/query_changes/recheck_hook/store.begin_run/owned hooks; the real Guardian must remain under test. `_collect_one('final_precreate')` uses existing nonoverlap/cadence/logging/cleanup paths. No new collector framework.

- [ ] RED: Add a fake-clock regression to GuardianTests using this core scenario before editing production:

```python
def test_setup_delay_refreshes_final_precreate_before_owned_create(self):
    h = self.h
    begin = h.store.begin_run
    def slow_begin(*args):
        begin(*args)
        h.clock.sleep(.7)
    h.store.begin_run = slow_begin
    h.query_delay = lambda p, i: 1.45 if p == 'final_precreate' else .1
    create_at = []
    owned = h.owned
    def record_create(*args, **kwargs):
        create_at.append(h.clock.monotonic())
        return owned(*args, **kwargs)
    h.owned = record_create
    result = h.run()
    self.assertTrue(result['success'], result)
    final = [q for q in h.queries if q.phase == 'final_precreate']
    self.assertEqual(len(final), 2)
    self.assertEqual(len(create_at), 1)
    self.assertGreater(create_at[0] - final[0].started, 2)
    self.assertLessEqual(create_at[0] - final[1].started, 2)
    self.assertGreaterEqual(final[1].started - final[0].started, 1)
    self.assertTrue(result['cleanup_confirmed'])
    self.assertEqual(result['recovery_samples'], 5)
```

Run the named test with PYTHONPATH scripts;tests/gufo. Expect assertion failure because old frame expires and no child is created, not a setup/import error.

- [ ] Add refusal tests using the same real Harness: final_precreate index1 delay2.1 must never create; only index1 available49GiB-1 must never create; recheck_hook after second final query raises artifact_changed and must never create; recheck_hook after second final query ages it2.1s and must never create. Preserve the existing last decision-I/O expiry regression. Verify current-run markers remain consumed as appropriate and controlled recovery/uncertain-latch behavior unchanged.

- [ ] GREEN: Insert only the refreshed collection and additional static recheck in `_prelaunch` after the existing setup/static recheck, before its second `_admit`:

```python
self.port_check()
self.store.recheck_static(self.manifest, current_run=self.run_dir)
# Setup and evidence writes must not consume the final frame's age budget.
final = self._collect_one('final_precreate')
# Catch static identity/marker changes during the replacement collection.
self.store.recheck_static(self.manifest, current_run=self.run_dir)
self._admit(final)
# Existing final admission_reasons(no I/O), owned create, final_preresume,
# resume, watchdog and cleanup follow unchanged.
```

This is one bounded new sample, not a retry-until-pass loop. A stale/slow replacement still refuses. No I/O is inserted after the last no-I/O admission check. Do not remove the early admission or either existing static check to make the regression pass.

- [ ] Version only16k constants/paths and preserve oldroot latching:

```python
# benchmark_recipes.PROFILE_16K and smoke_store.BENCHMARK_16K:
'ar16k-iq4xs-pp1-cache-v2'
# PROFILE_ROOTS/benchmark_guard profile_pins16k evidence:
'gufo-ar16k-benchmark-v2-runs'
# benchmark_guard16k qualification:
'gufo-ar16k-benchmark-v2-qualification.json'
# _incomplete_latches literal historical roots must also include:
'gufo-ar16k-benchmark-runs'
```

The old16kv1 is no longer launchable, but all its evidence stays untouched. Add exact v2 path/id tests, v1 refusal, old16k incomplete latch blocking initial/recheck/begin, clean oldattempt permitting v2 without modifying it, and unchanged13-request schedule/argv except fixed experiment metadata. Do not modify real4k acceptance or any consumed qualification.

- [ ] Run focused modules test_smoke_guard test_smoke_store test_benchmark_guard test_benchmark_recipes test_benchmark_runtime test_smoke_policy; one full `python -m unittest discover -s tests/gufo`; diff-check; scoped local commit. Report RED/GREEN commands/results and self-review against constraints. Independent recorded-base review follows before live execution.

## Parent execution checklist

- [ ] Confirm exact failed16kv1 hash/identity null/cleanup5recovery and no live process or incomplete latch; keep all files. Confirm successful4kv2 acceptance/hash still valid.
- [ ] After independent review and fresh final-tip verification, derive16kv2 qualification from exact code pins/review ID, unchanged accepted AR-fit SHA75BDFDFFFB46D6BB88529FA12D76EE29910064AE03334906ABB46B8A38861620.
- [ ] Print-only/static then one guarded13-request16kv2 run. Observe same exec handle, no extra requests or automatic retries. Inspect every artifact and cleanup, report exact PP2048/8192 and cold/cached distinctions or retained failure.
- [ ] Continue full objective: MTP fit/qualification, matched upstream AR/MTP, PP32768, instrumented concurrency, usable optional backend/install/rollback and independent overall review remain outstanding.

## Self-review

The change addresses observed frame reuse rather than increasing age tolerance.
Static changes during the replacement query remain checked before create; last
no-I/O admission prevents decision/logging delays from silently aging the frame.
This experiment does not claim total quality or safety beyond bounded policy.
