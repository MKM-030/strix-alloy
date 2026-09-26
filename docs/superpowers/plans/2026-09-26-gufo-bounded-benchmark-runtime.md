# GUFO finite benchmark profiles implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. The native design, staged execution and parallel implementation/review are already approved; do not repeat that approval loop.

**Goal:** Run useful AR correctness and comparable HTTP PP2048/8192 measurements under the proven owned-process guardian, without resetting any completed smoke attempt or relaxing memory controls.

**Architecture:** Extend the private store/policy/guardian binding seams, preserving the existing v3 CLI and defaults. Two code-defined benchmark profiles bind exact recipes and predecessor evidence in separate qualification records. One HTTP worker executes a finite sequential schedule, persists each raw request separately, and stops on failure; the guardian remains independent and owns shutdown/recovery.

**Tech Stack:** Existing Python standard-library guard/store/policy and benchmark_http.request_once; unittest fake processes/telemetry/HTTP. No new dependencies, source patches or server rebuild.

## Global Constraints

- Workspace C:\Projects\strix-alloy-research\integration, codex/gufo-native-integration. Preserve dirty original StrixAlloy, Halogen/27B deployments, model/SDK/source snapshots and old evidence. No public push/release.
- Keep49GiB available before launch,24GiB runtime physical floor,12GiB commit headroom; existing68/4/20GiB GPU/host/shared allowances and84GiB prelaunch commit headroom. No concurrent model/guest. No BIOS/carve/driver/services/security/pagefile/WSL/D: changes.
- Same source cff564964e8506c0abb3e530cecb55332187ac6c, executable SHA E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943, model revision38bb39ee97821de2c9009abb7e93950eec396e66 and all current runtime pins. One model/session, noMTP/projector/diskcache, one pending/per-client pending request. HTTP connection cap16 is housekeeping, not model concurrency.
- Accepted numerical review reports/gufo-ar-benchmark-fit-20260926.md SHA75BDFDFFFB46D6BB88529FA12D76EE29910064AE03334906ABB46B8A38861620 permits <=36 sequential generation requests, <=256 output tokens/request, request body<=262144B, response<=1048576B, per-request<=60s and total owned lifetime<=600s including startup/warmups. Startup<=480s; query<=2s, final sample<=2s old, runtime sample<=5s old; nonoverlapping query starts>=1s apart. No automatic model/request retries.
- Preserve kill-on-close suspended Job ownership, source/model/static rechecks, independent watchdog, exact live PID proof, stop-before-worker-wait, terminal collectors/inspection/HTTP, stricter original/current live ceilings and five per-run recovery samples. All known sibling incomplete latches block progression. A stop threshold is not reserved memory.
- Existing v3 remains consumed and unchanged: one short arithmetic request, max64, its current qualification/attempt/raw output untouched. Generalization never makes an old attempt reusable.
- Counter-based PP/TG only, HTTP/engine boundaries separate. Three measured repetitions retained with failures/spread; first-use and cache-hit labels explicit. No text-chunk token counting or general Windows/Linux parity claim.

## Task 1: Bound existing guard/store/policy to immutable profile identities

**Files:** modify scripts/gufo_control/smoke_guard.py, smoke_store.py, smoke_policy.py and their three tests. Create scripts/gufo_control/benchmark_runtime.py and tests/gufo/test_benchmark_runtime.py. Do not touch benchmark_http/smoke_http in this task.

**Interfaces and exact behavior:**

```python
# smoke_store.py; append defaults after existing StorePins fields.
@dataclass(frozen=True)
class PredecessorPin:
    profile_id: str
    run: Path
    result_sha256: str

# New StorePins fields:
# experiment_json: str | None = None
# predecessors: tuple[PredecessorPin, ...] = ()
# The original PINS has None/(); legacy expected_qualification shape unchanged.

# Fixed supported IDs (no pattern/wildcard acceptance): existing PROFILE_ID,
# 'ar4k-iq4xs-correctness-pp1-v1', 'ar16k-iq4xs-pp1-cache-v1'.

# Existing private helpers operate on pins.profile_id instead of captured
# PROFILE_ID. Public legacy wrappers still use exactly original PINS.
# expected_qualification adds parsed experiment_json and explicit predecessor
# identity/hash entries only for benchmark pins. Include these in manifest.

# smoke_policy.py: keyword-bound pins default to current PINS on these APIs:
# profile_from_manifest, _profile_valid, _common, admission_decision,
# admission_reasons, runtime_decision, runtime_reasons, frame_numeric_reasons.
# Propagate pins through every internal call. Construct expected SmokeProfile
# with explicit profile/source/model/margin fields. All numeric allowances stay
# fixed existing constants, never caller-overridable profile arithmetic.

# smoke_guard.py: additive private dependency seams only.
class _Guardian:
    def __init__(self, *, store=smoke_store, owned_factory=None,
                 query_factory=None, http_start=None, collect=collect_snapshot,
                 port_check=check_port, policy_module=policy,
                 argv_builder=fixed_argv, profile_id=smoke_store.PROFILE_ID): ...
# Save/bind these; replace internal policy calls and fixed_argv calls.
# At prelaunch require manifest['profile']==self.profile_id; result uses it.
# No changed timing, cleanup, lock, exception or watcher control flow.

# benchmark_runtime.py provides bound adapters only, not a CLI/launch side effect:
class BoundStore:
    def __init__(self, pins): ...
    # PINS,BUILD,EVIDENCE; verify_static(),recheck_static(manifest,current_run=None),
    # load_original_operator_baseline(),begin_run(run_dir,manifest,baseline),
    # finish_run(run_dir,result), all delegating shared reviewed helpers.

class BoundPolicy:
    def __init__(self, pins): ...
    # Bind all profile-dependent functions above with functools.partial;
    # expose unchanged ownership/baseline/recovery functions directly.
```

Canonical experiment_json must round-trip to exactly its sorted compact JSON representation, be a bounded object and identify the same supported profile. Task2 constructs it from exact context/recipe/sampler/count/body/time settings. A benchmark ID without experiment/predecessors must refuse, as must a legacy ID with benchmark-only data. Numeric bounds must equal unchanged BOUNDS. The bound adapter accepts only supported code-defined profile IDs, never arbitrary paths/IDs supplied by CLI.

Sibling incomplete-latch checks cover fixed legacy roots gufo-ar4k-smoke-runs, gufo-ar4k-connect-wait-smoke-runs, gufo-ar4k-http-slots-smoke-runs and both new benchmark roots below, plus existing operator latch. Check initial/static, cheap recheck and begin. During this run only its own exact validated current-run latch is allowed. Sibling permanent attempt markers alone do not prohibit later profiles.

Predecessor validation: exact absolute root-contained run directory/profile/hash; result success, owned_exit_confirmed, collector_terminal,collector_cleanup_confirmed,http_terminal,inspection_terminal,inspection_duplicate_closed,evidence_write_confirmed,cleanup_confirmed all true; recovery_samples5. Its permanent attempt marker must refer to the same run/profile and root must have no incomplete latch. Preserve stamped artifact records and recheck them before create/resume. For a benchmark predecessor also verify every declared per-request evidence file path is inside that run, byte count and SHA256 match; do not embed/re-read >2MiB combined raw results with the state helper. No file deletion or proof inferred from a PID filename.

The new recipe's own public constants and qualification must bind its exact predecessor choice. First4k prerequisite is v3 run20260926T164942Z-a4d64a8f565248bdb508895b6f3ec931, SHA58B222AA96BE4A84F4349697A9914B20E1953ECC7464085A4BE9984819121FBF. Second16k cannot be qualified until a real first4k successful result and separate semantic review ID exist; never use a dummy hash or select latest directory.

- [ ] RED fake tests: original v3 exact argv/qualification unchanged; both benchmark IDs and exact experiment/predecessor binding accepted only with review; unknown ID/canonical mismatch/missingpredecessor/falsecleanup/wrongroot/digest/rawartifact fail before child; sibling latch blocks launch and recheck, sibling consumed clean attempt does not; only current exact owned latch exempt; unsafe numeric bounds refuse; guardian wrongprofile fails before start; injected policy/argv used with independent timeout/cleanup unchanged.
- [ ] Implement narrow seams/adapters. Follow existing filesystem validation and atomic-write patterns. No separate guardian copy, global monkeypatch or widened state-read limit.
- [ ] Focused tests then full tests/gufo once; diff-check; self-review; localcommit. Parent independently reviews recorded-base diff before Task2 runtime wiring/qualification.

## Task 2: Fixed recipes, bounded suite and research CLI

**Files:** create scripts/gufo_control/benchmark_recipes.py, benchmark_suite.py, benchmark_guard.py and their matching three test files. These consume Task1 adapters and the separately completed benchmark_http.py. No model/telemetry run during implementation.

**Produced interfaces:**

```python
PROFILE_4K = 'ar4k-iq4xs-correctness-pp1-v1'
PROFILE_16K = 'ar16k-iq4xs-pp1-cache-v1'

def recipe_definition(profile_id: str) -> dict: ...
def recipe_json(profile_id: str) -> str: ...  # canonical fresh value
def build_argv(profile_id: str, secret: str) -> list[str]: ...
def validate_answer(case_id: str, result: dict) -> dict: ...
def calibrated_prompt(target: int, first_tokens: int, second_tokens: int) -> str: ...

def start_suite(*, profile_id: str, evidence_dir: Path, api_key: str,
                startup_deadline: float, lifetime_deadline: float,
                cancel: threading.Event | None = None): ...
# Return the same done/cancel/result interface consumed by _Guardian.
# Finish every path by publishing a structured sanitized result and done.set().
```

Use the exact five EN/DE/CODE/TOOL/LONG prompt strings, tool schema and public sampler fields from reports/gufo-benchmark-recipes-20260926.md. Copy fixtures into code with pinned-source attribution, not runtime dependence on the external report. Per-case output caps128,128,256,128,256. Tool must remain a real tools/tool_choice=required request, not JSON-shaped text masquerading as a call. No tool execution. Greedy temperature0/top_p1/top_k0/seed42; sampled temperature1/top_p0.95/top_k20/seeds1001,1002,1003; both thinkingoff to isolate sampler differences. Thinking-on is a separately labelled later experiment, not silently treated as covered here.

4k schedule exactly36 generation requests:1 existing arithmetic warmup (max64);30 task requests (five fixtures x two sampler modes x three repetitions);2 untimed Halogen calibration probes;3 measured PP2048/max1 requests. For repetitions0,1,2 rotate fixture order left by repetition; mode order greedy,sampled on even repetitions and sampled,greedy on odd. Record the actual order. A fixture repetition is not retried if failed. Warmup answer must be4. All4k task actualprompt counts<=3072 and input+reservedoutput<=4096. Three PP rows require actual newprompt within2048+/-32, cached0 and actualoutput1; otherwise retain calibrationmiss and abort, never rename actual count to2048.

16k schedule exactly13 requests: arithmetic warmup;two calibration probes;PP1 measured target order [2048,8192,8192,2048,2048,8192];onecache preparation andthreecached repeats. Cache preparation/repeats use the exact same long public prompt with approximately2048 tokens, max64, explicitly request concise summary; firstcache_promptfalse, repeatscache_prompttrue. Record actual hit/miss; a miss is a cache experiment result, not a forged hit. Every complete input+reservedoutput<=16384. Require first4k success plus parent semantic review before binding16k qualification.

Halogen calibration uses exactly FILLER='The unified memory architecture changes how inference engines schedule work across the accelerator and the host processor. ', firstprompt='x', secondprompt='x'+FILLER*20; both max1,thinkingoff,cachefalse. Reject second<=first, noninteger counters and body/context overflow; no extra calibration request. Formula units=max(1,round(max(0,target-first)/((second-first)/20))), Python round as source. Prompt='x'+FILLER*units. Requests are nonstreaming /v1/chat/completions to match Halogen HTTP boundary; do not send unsupported Halogen drafter/enable_thinking fields to GUFO. Record generator provenance, actual prompt bytes/hash and token counts.

Suite readiness reuses existing bounded /ready and /v1/models logic with exact alias but does not call start_smoke (which would consume an extra generation). Extract a shared bounded readiness helper if the completed client already supplies one; otherwise implement only these two GET stages using existing transport, with <=240ready polls/480sstartup and cancel/deadline. ModelsGET once, no POST retry. Direct3xx/401/503overloaded or unknown identity fail. Readiness connect-refused/connect-timeout may wait within the fixed poll bound, as in v3. The generation warmup itself completes functional readiness.

Validate outputs without executing model code: DE strictJSON exactkeys/de/B, nonempty German rationale; TOOL merge exactcallid/name/arguments and no invented status; CODE ast.parse plus a tiny bounded interpreter for clamp's tests. Permit params/constants,if/return/raiseValueError,comparisons,conditionalexpressions, and safe min/max; reject imports, attributes, decorators, loops, arbitrarycalls and top-level effects. Unsupported syntax is needs_review rather than executed. EN/LONG are nonempty structurally complete candidates with semantic_review_pending, not false automatic semantic passes. Known invalid arithmetic/JSON/tool/code behavior aborts. LONG output<256 is earlyEOS, not a full256-token sustained rate; length is measured budget exhaustion, not necessarily a transport failure. Parent reads all textual candidates before claims or16k progression. A suite's transport success alone cannot fabricate semantic approval.

Persist per-request raw result immediately to a new deterministic ordinal filename using atomic_json, bounded by the client body/response contracts. Save its SHA256/byte count and a compact summary; do not accumulate raw bodies in the final result. Keep result.json<2MiB. In-flight parent/client memory must stay bounded; release each raw result after writing. On protocol/counter/known-correctness failure write the failed row and planned-but-not-run markers; set error and end, no automatic nextrequest. Exceptions/evidence-writefailures fail closed; all waits respect cancellation/lifetime. Guardian closes ownedprocess before waiting for this worker.

Each row stores kind (warmup/calibration/measurement),case,mode,repetition,targetactualcontext distinction,cache policy,outputbudget,metrics and correctness state. Summary includes allindividual rows, means and sampleSD (statistics.stdev onlyn>=2), valid/failed/notrun counts. No successful-only table without failure counts. Engine stages and HTTP PP1 columns separate. Common20s aggregate decode remains null with reason native_window_counters_unavailable.

CLI research commands: python -m gufo_control.benchmark_guard {status,print-only,run} --profile {the two exactIDs}. No context/sampler/floor/paths/qualification override. Run uses _Guardian with BoundStore/BoundPolicy/fixedargv and one start_suite closure bound to its unique run_dir. New roots reports/gufo-ar4k-benchmark-runs and reports/gufo-ar16k-benchmark-runs; qualification files gufo-ar4k-benchmark-qualification.json and gufo-ar16k-benchmark-qualification.json. No persistent service yet; automatic owned stop is mandatory. Unknown/unqualified/consumed profiles refuse. Status/print-only perform no launch/request/marker mutation.

- [ ] RED: exact schedules/counts/rotation/requests/hash/coldPP/cache labels; safe validators inclmaliciouscode/toolfragments; calibrationrounding/miss; mid-schedulefailure abort/noextraPOST; readiness bounds/cancel; rowwritefailure; metricsunknown/earlyEOS/sampleSD; boundedrawpersistence and predecessor verification; fakeguardwrongprofile/latch/deadline/recovery regressions; legacyv3unmodified.
- [ ] Implement finite recipes/suite/CLI. Focused tests then fullsuite once; self-review/localcommit; independent code review. Do not write real qualifications or launch during implementation.

## Task 3: Parent qualification, live evidence and comparison

- [ ] Check full reviewed code, previousv3 exactdigest/cleanup and newfitreviewdigest. Bind4kqualification to recipe/argv/count/time/sampler and predecessor, preserving originalreports. Freshprint-only then one parent-run4k suite. No extra health/model requests outsideits worker.
- [ ] Inspect all raw outputs/counters/memory and cleanup. Adjudicate pending English/German/code/tool/long semantics; recordactualissues. If valid, retain all three reps/spread and updatecomparison with same-recipe HTTPPP2048 plus cautions. Successfulload alone is not success.
- [ ] After successful4k and semanticreview, bind actual4k run/digest/rawartifacts as16kpredecessor. Freshadmission and one16k run; verifyPP8192 actualcounts/HTTPdenominator/cache behavior and recovery. Compare only compatible rows; preserve quantization/template/sampler/OS/deployment differences.
- [ ] Keep goalactive for MTP/sidecars/draftpolicies, PP32768, nativeper-token concurrency instrumentation, Halogen update isolation, optional production setup/start/status/stop/rollback packaging and finalwholebranchreview. No public push/release/post without new instruction.

## Self-review

This plan preserves the complete objective while advancing from a one-answer smoke to finite useful workloads and matched PP2k/8k. It reuses all completed ownership/telemetry work, binds exact new recipe scope and predecessor evidence, fixes cross-profile failure isolation, and keeps raw-evidence growth outside the2MiB state format. Subsequent MTP/largecontext/concurrency and production lifecycle work are explicit remaining deliverables, not redefined success.
