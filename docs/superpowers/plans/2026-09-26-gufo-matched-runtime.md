# Matched AR/MTP finite runtime integration plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Implement and review the task below before writing qualifications or launching a model.

**Goal:** Measure identical 36-request AR and MTP length/draft1 workloads with native counter evidence and the existing owned Guardian.

**Architecture:** Extend the existing benchmark CLI with two exact profile IDs from matched_recipes. Reuse its sequential suite through narrow private recipe/assessment hooks, not a second HTTP or process runner. Profile-specific measured margins remain immutable; historical experiments and one-shot attempt markers remain untouched.

**Tech Stack:** Python 3.12 standard library, existing GUFO Windows executable and TheRock10.2 runtime.

## Global Constraints

- At least 49 GiB available Windows physical memory before launch.
- A 24 GiB available Windows physical-memory stop floor during testing.
- At least 12 GiB system commit headroom.
- No concurrent inference model during initial qualification.
- Matched AR uses68/4/20 GiB, commit72; matched MTP uses72/4/20, commit76 and fresh88 GiB commit headroom. Existing AR and first MTP71/4/20 profiles remain unchanged.
- Queries/final admission age<=2s, runtime age<=5s, nonoverlap and start spacing>=1s. Preserve current lifecycle, ownership, locks and five-frame recovery.
- One process/session, context4096, max complete input2304/output256, exactly36 fixed request rows; startup480/request60/lifetime600 seconds; request256KiB/response1MiB, maxconnections16.
- No model/GPU action by implementer, no source/binary/system-settings/reboot/D:/publication changes; no qualification creation or historical artifact/marker mutation.
- No edits to smoke_guard.py, winjob.py, telemetry collectors, native engine, old benchmark_recipes or old MTP stage.

### Task 1: Paired profiles, native evidence and existing-suite integration

**Files:** Create `scripts/gufo_control/matched_profile.py`, `matched_validation.py`, `tests/gufo/test_matched_profile.py`, `test_matched_validation.py`, `test_matched_suite.py`. Modify narrowly `benchmark_guard.py`, `benchmark_suite.py`, `smoke_store.py`, `smoke_policy.py`. Use reviewed matched_recipes unchanged. Do not introduce a second Guardian or copy the sequential suite/HTTP transport.

**Interfaces consumed:** `matched_recipes.PROFILE_AR`, `PROFILE_MTP`, `recipe_definition`, `recipe_json`, `request_for`, `validate_request`; `benchmark_guard.profile_pins(PROFILE_16K)` for the already verified AR predecessor; `benchmark_suite._assess` for unchanged model-quality checks; `BoundStore`, `BoundPolicy`, existing `_Guardian` and request transport.

**Interfaces produced:** `matched_profile.profile_pins(profile_id)`, `experiment_definition(profile_id)`, `build_argv(profile_id, secret)`; `matched_validation.assess(row, observation, definition)` returning `(correctness, fatal_errors)`. Extend `benchmark_suite.start_suite` with private optional `recipe_provider`, `request_validator`, `response_assessor` keyword arguments; defaults preserve existing behavior.

Binding constraints for this task: Windows49/24/12 GiB floors and all existing timing/ownership/recovery invariants remain unchanged; AR68/4/20 and new MTP72/4/20 (commit76/fresh88), no concurrent model. Fixed36requests, complete input2304/output256/context4096/session1, deadlines480/60/600s, request262144/response1048576bytes/connections16. No Guardian/telemetry/engine/old recipe/old MTP edits, live GPU, qualification creation, persistent setting changes, reboot, D: or publication.

#### Step 1: Read the accepted contracts and write RED tests

Read in full:

- `C:\Projects\strix-alloy-research\reports\gufo-matched-mtp-envelope-review-20260926.md`
- `C:\Projects\strix-alloy-research\reports\gufo-matched-response-contract-20260926.md`

Pin the finalized margin report SHA256
`49433BB54E71F7F27418FEC63E71DA98F4C372F31E19E6A95292E21148874344`.
The response contract SHA256 is
`820F53B9D454A58D641283FE8C1383F3891C2F75E9CE859F903F25BEC5D3D3F3`.
The memory review is not permission to load an unreviewed harness.
The response report distinguishes valid poor quality/acceptance from invalid
native telemetry. No automatic POST retry is permitted.

Add focused tests with these concrete expectations:

```python
def test_distinct_unchanged_demands(self):
    ar = matched_profile.profile_pins(matched_recipes.PROFILE_AR)
    mtp = matched_profile.profile_pins(matched_recipes.PROFILE_MTP)
    self.assertEqual(ar.bounds['gpu_gib'], 68)
    self.assertEqual(mtp.bounds['gpu_gib'], 72)
    self.assertEqual(smoke_store.MTP_BOUNDS['gpu_gib'], 71)
    self.assertEqual(smoke_policy._demand(mtp)['commit_peak_bytes'], 76 * 2**30)
    with self.assertRaises(ValueError):
        smoke_store._binding(replace(mtp, bounds=dict(mtp.bounds, gpu_gib=71)))
```

Test unknown IDs, wrong sidecar/margin/recipe/request hashes, changed sampler or
budget, strict bool/float rejection, AR receiving sidecar, missing qualification,
cross-profile incomplete latches, pure policy evaluation without file stat, and
fresh launch needing88GiB commit headroom for MTP versus84 for AR. Use existing
fake filesystem/model/admission fixtures; no genuine stat dependency in pure
policy calls. Verify the new demand cannot leak into any existing profile.

#### Step 2: Bind exact paired profile identities

Use these roots and qualifications under `smoke_store.ROOT/'reports'`:

```python
PROFILE_FILES = {
    matched_recipes.PROFILE_AR: ('gufo-matched-ar4k-v1-runs', 'gufo-matched-ar4k-v1-qualification.json'),
    matched_recipes.PROFILE_MTP: ('gufo-matched-mtp4k-v1-runs', 'gufo-matched-mtp4k-v1-qualification.json'),
}
```

Both use the new expanded signed margin report and the exact existing AR4k-v2
predecessor plus its semantic acceptance file. That predecessor/result/request
validation already binds the36 historical request files and their tokenizer
counts. The margin report additionally binds the completed MTP stage, its
independent review, source allocation accounting and explicit unknown reserve.
Keep historical raw semantics flags intact.

`profile_pins` starts from the existing16k benchmark pins to reuse its checked
AR4k predecessor/acceptance; replace profile ID, paths, margin identity, bounds,
experiment JSON, and (only MTP) the existing shared sidecar with its recorded
stamp. No stat is permitted inside expected_qualification/policy decisions.

`experiment_definition` is pure: profile+exact recipe SHA, context4096,
max_prompt_tokens2304, max_output_tokens256, max_requests36, sessions1,
max_connections16, max_request_bytes262144, max_response_bytes1048576,
request60/startup480/lifetime600, disk_cacheFalse. Speculative is a strict bool;
MTP additionally binds draft_tokens1/min_draft_tokens1/length/full; AR binds no
sidecar or speculative options. Canonical JSON and exact key/type/value equality
are required by `_experiment` as for the prior MTP stage.

Extend only the fixed store allowlist, bounds selection and acceptance-profile
set needed for these two IDs. Prefer one pure `profile_bounds(profile_id)` helper
used by store and policy over divergent repeated demand selection. It must reject
unknown IDs. Match MTP sidecar/recorded-stamp checks to the existing stage; new
MTP margin hash differs from the old stage and cannot authorize that stage.
Keep all existing predecessor artifact checks and static rechecks. Both new
roots participate in the existing global incomplete-latch exclusion.

AR argv is the existing4k benchmark argv. MTP adds `--speculative mtp`, explicit
shared `--mtp-model`, `--draft-tokens 1`, `--min-draft-tokens 1`, `--mtp-policy length`,
`--mtp-draft-vocab full`; max tokens stays256. Preserve all other safety/env/auth
flags. No override knobs, survival or arbitrary prompts in this version.

Extend benchmark_guard's profile routing/CLI choices, status bounds and
argv selection. Only the two new profiles use the new provider and validators.
Original profiles take their unchanged path. `status` and `print-only` do not
create processes; print-only checks the new exact qualification. Only parent
creates qualification after review.

#### Step 3: Validate native evidence without erasing bad outcomes

Use the response contract's exact four native draft fields as mandatory strict
nonnegative integers, including on single-output rows. AR requires0/0; MTP
allows0/0 or positive proposals with zero accepted, requires agreement of both
usage/timing pairs and accepted<=proposed. Metrics acceptance must equal the
ratio when proposed>0; for0 proposals it is None with recorded `no_proposals`.
`drafted-accepted` means unaccepted proposals, not rejection/rollback events.

Validate complete actual prompt count equals the row's prechecked historical
count; output positive and <=row budget, predicted/output and total agree;
prefill/prompt counters agree; cached counts/hits/restores/disk queued bytes0.
Lookup fields are both omitted (record pinned-emitter-zero provenance) or both
strict integer0. Present common-prefix tokens must0. Snapshot/shared capture
fields may be nonzero, but are not reused tokens. Require exact single-session
width/resident/logical-concurrency fields, expected model identities, and no
unexpected reasoning. Allow tool output only for the TOOL case and normal
stop/length/tool finish states through existing case assessment.

Reuse benchmark_suite._assess for quality and PP/calibration checks, then separate
`known_correctness_failure` from fatal protocol/counter/safety errors. A coherent
native response with incorrect formatting/answer, early EOS, zero acceptance or
slow speed is persisted and subsequent fixed rows continue. Do not mark its
correctness passed. An invalid native count/model/cache/concurrency/transport
or changed prompt fails the suite after saving its response; no dependent row
or retry follows. Every case's raw output remains for manual semantic review.

Add `matched_evidence` to each observation and compact row: mode, proposed,
accepted, ratio/reason, lookup provenance, quality_failed, expected/actual prompt
count, and sustained_256 eligibility for LONG (`output==256 && finish=='length'`).
Do not calculate aggregate/common-window throughput. A suite-level MTP claim
requires at least one valid LONG with positive proposals; positive accepted
tokens are required to claim useful accepted speculation, not to retain a valid
0%-acceptance measurement. Parent report separately records that qualification.

#### Step 4: Reuse the suite with narrow private hooks

Defaults preserve old calls and behavior. Resolve `recipe_provider` to existing
recipes when omitted, and call its definition/JSON/request functions. A supplied
request_validator validates the final private request immediately before the
sole request_once call for each row; no call may occur on mismatch. A supplied
response_assessor replaces `_assess` for that profile, and adds the compact
matched_evidence described above before persistence. Existing raw-data bounds,
redaction, cancellation, deadlines, no retries and worker completion remain.

Count completed rows with failed quality separately in the new profile summary,
without renaming invalid/unexecuted rows as successes. Quality failures remain
visible in each row and are excluded from claims of correct useful throughput;
native times remain observable. Both original benchmark profiles retain their
current fatal quality behavior and result shape. Don't duplicate the worker.

Offline tests must include one36-row fake suite per mode, altered request
rejected before POST, MTP PP1zero draft valid, MTP0accepted valid, ARnonzero draft
invalid, bool/float/missing/inconsistent counters invalid, cache hit/wrong prompt
invalid, early EOS retained, quality failure followed by later completed rows,
fatal counter failure followed by not_run rows, cancelled/evidence-write-failed
suite and all old suites unchanged. Never execute model-generated code.

#### Step 5: GREEN, commit and independent review

Run targeted new tests while iterating; full offline tests once before commit:

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_matched_*.py' -v
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p 'test_*.py'
```

Self-review, local commit only, and full RED/GREEN report at
`.superpowers/sdd/matched-runtime-report.md`. Parent reviews exact BASE..HEAD
diff and reruns focused checks. Unresolved Important findings block GPU launch.

## Parent execution and evidence

After clean review, create each qualification using exact reviewed pins without
JavaScript number-rounding of nanosecond stamps. Run print-only. Require fresh
ordinary admission and no parallel shell diagnostics during baseline. Run AR,
review counters/answers/cleanup, then MTP only after confirmed recovery. No blind
retry or consumed-marker reset. Preserve failures and incomplete rows.

Compare every like-for-like case/mode/seed, actual counts, TTFT, engine TG and
HTTP PP/engine PP separately, means/sample SD and individual repetitions.
Only LONG256 rows support sustained256 claims; all answer quality outcomes remain
visible. Explicitly distinguish this corpus from upstream GUFO warmed prose/
repetition and Halogen ten-prompt suites. Record sampled memory and uncertainty.
This task does not finish PP32k, concurrent sessions, long contexts, reusable
service/setup, Halogen upgrades or broader tuning; those goal requirements remain.
