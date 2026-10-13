# Exact prompt-cache A/B plan — not activated

Status at 2026-10-13 14:49 UTC: **NO-GO pending separate original-model recovery and a new review.** This document authorizes no runtime action. The user-confirmed successful four-turn native call is analyzed in [real-call-performance-20261013.json](real-call-performance-20261013.json).

## Evidence and scope

The four turns took 41.902, 63.771, 55.716 and 89.038 seconds after ASR. Eighteen time-correlated model requests consumed 138,321 prompt tokens and 3,150 output tokens; logged prefill totaled 113.10 seconds and decode 76.47 seconds. ASR took 0.234–0.281 seconds. Repeated prefill is the largest measured engine phase. Model requests cannot be uniquely mapped to Bot messages without a shared request ID; the JSON preserves this limitation and avoids assigning unobserved tool roles.

The installed service accepts Off, Exact and Flexible; service.environment maps Exact to HALOGEN_PROMPT_CACHE=1. The installed 0.18.1 API describes Exact reuse as bitwise-identical to cold execution. Actual SCC prefix hits and latency benefit remain unmeasured. There is no runtime API to enable a disabled cache; a managed model restart is required. No cache experiment has been executed.

Only engine.prompt_cache may change from Off to Exact. Context262144, one slot, draft depth2, prefill chunk/max4096, all API defaults and physical/commit guards18GiB remain unchanged. The existing public gateway no-thinking alias override stays unchanged.

## Exact files and commands

Clean controller: C:\Projects\strix-alloy-clean\server\controller.py.

Profiles are in C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012.

| File | SHA256 |
|---|---|
| serving0181-full262-profile.json | cf02e2e695160c3e199a2efbf81920192d77f538616b4a3a00153e33927333c4 |
| serving0181-full262-exact-cache-candidate-20261013.json | f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323 |

Fresh structural comparison found only engine.prompt_cache Off→Exact. Original and candidate remain separate files. Existing candidate evidence: voice/halogen-exact-cache-candidate-20261013.json.

Future commands, only after explicit review and all gates:

~~~powershell
$Clean = 'C:\Projects\strix-alloy-clean'
$CorePy = "$Clean\server\.local\venv\Scripts\python.exe"
$Controller = "$Clean\server\controller.py"
$Profiles = "$Clean\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012"
$Original = "$Profiles\serving0181-full262-profile.json"
$Candidate = "$Profiles\serving0181-full262-exact-cache-candidate-20261013.json"

& $CorePy $Controller stop
# Verify full managed stop/recovery/lock release before the next command.
& $CorePy -u -B $Controller run --config $Candidate --port 8840
# Rollback: same managed stop and all stop/recovery gates, then:
& $CorePy -u -B $Controller run --config $Original --port 8840
~~~

Actual execution must launch into unique stdout/stderr/ownership receipts, poll in short bounded calls, and keep one operator in control. These are command contracts, not an unattended trial script.

## Admission and stop gates

1. Hold demo users and all shared model callers. Require native sessions0 and fresh model/gateway active0/queued0, healthy speech/Bot/native, exact full controller command/profile/source identity, unchanged hashes and exact current run/lock. Any unknown active request aborts before stop; never cancel it.
2. The outer controller stop path drains its own8840 gateway and requests the exact backend run to stop. It does **not** drain the separate public8841 gateway. Holding shared traffic throughout is required; one idle snapshot cannot prevent a later arrival.
3. Before starting the candidate require terminal managed owners, no8731/8840 listeners, proven owned container cleanup, successful original recovery predicate and automatic lock release. Any retained lock or failed recovery is a hard stop for this experiment. Separate operator recovery requires its own review; never delete a guard or reuse a retained lock.
4. Original cold admission remains at least35GiB physical and131GiB commit, plus the service's full stable admission window and exact run-specific recovery target. Proposed experiment-only no-new-turn floor:22GiB physical and22GiB commit, a4GiB cushion above the unchanged18GiB runtime guards. This is conservative operator policy, **not a proven cache memory bound**. Measure ready/peak minima and continuing drift; a guard event or unexplained decline invalidates the trial.
5. The historical115MiB-per-snapshot / six-entry / approximately0.67GiB estimate is not measured incremental RAM for this profile. Cache health must report mode1 and positive capacity; collect actual counters and Windows memory before/after each request. Do not claim the estimate guarantees safety.

## Small controlled comparison

Use existing voice/native-bridge/runtime/run-post-language-first-turn.ps1 -ConfirmedPatch only after checking its hashes and current authorization. This first-turn-only harness sends the known laptop intent, then ends its own conversation; it sends no employee name or confirmation and creates no order. It is an existing audio probe, not a cache lifecycle controller. No new cache trial launcher exists yet.

Establish two fresh baseline first-turn runs on restored original Off profile, then two identical fresh first-turn runs on Exact; one request stream at a time, no retry after failure. Keep fixtures, native/Bot/gateway versions, no-thinking mode and orchestration unchanged. Record actual input-ready marker, first audio, each request's prompt/generated/cached token counts, prefill/decode, cache hits/misses/evictions and memory minima. Account for guest/host clock offset and unrelated callers. A fresh conversation controls dialogue state; the second Exact run tests whether reusable stable prefixes actually exist. Do not substitute this for generic-hello or microphone acceptance.

Stop immediately if dialogue correctness changes, a session fails to end, unknown work appears, ownership drifts, memory gate fails, or useful cache hits are absent. Do not continue to names/order confirmations.

## Rollback and desktop compatibility

voice/Start-NativeModel.ps1 is deliberately pinned to the original profile SHA. While Exact is active, its Start path refuses to adopt the candidate, and Model/All desktop shortcuts cannot start/reuse that stack. Its Status may exit0 with owned_controller=false; exit status alone is not ownership acceptance. The coordinator's generic health checks also do not attest cache mode.

Keep those launchers unchanged. Hold Model/All shortcuts during the experiment and use only the managed clean controller commands above. **Restore the original profile before handing the demo back**, even if Exact improves speed. A permanent cache default would require a separate reviewed launcher change.

Rollback requires idle callers, managed candidate stop, verified cleanup/recovery/lock release and absent listeners, then original-profile start. Verify exact original SHA, owned current controller, 0.18.1 health,262144 context/one slot, cacheOff/mode0, all services healthy/idle, and Start-NativeModel.ps1 -Action Status with owned_controller=true. If a lock remains, stop and report; do not attempt another start.

Known configured bounds are service startup timeout900s, outer readiness timeout1200s, backend cleanup wait240s and memory-recovery window180s. A previous successful cold restoration took approximately144s; this is one observation, not a guaranteed downtime bound. Shared traffic, failed recovery or a retained lock can extend outage indefinitely until reviewed recovery. No automatic retry is planned.

## Separate guard incident and present recovery

Current backend run1d996b5648654362afdebee6c5c655ea was original Off. At14:33:34.759Z its guard recorded physical17.841GiB / commit110.252GiB against18/18. Cleanup passed, initial180-frame recovery failed: required42.445GiB physical, then approximately37.6GiB. The original guard, failed outcome, terminal record and runner.lock remain evidence.

Root independently identified and confirmed an agent-owned read-only PowerShell process PID19932, created14:28:26Z, parent17608, consuming about22.6GB working set. It serialized Get-Content annotated strings inside objects using ConvertTo-Json -Depth8. Root verified full identity with its owning agent and terminated exactly that process at14:46:27.610Z. This is a concrete additional consumer; this incident does not establish a KV-pool growth or cache cause. Exact was never active.

After cleanup, five direct host_frames measurements at14:49:20Z met runner.recovered() unchanged: at least51.142GiB physical and201.459GiB commit. The historical failed recovery is not rewritten. A separate one-time operator reconciliation candidate, runtime/reconcile-halogen-1d996b-20261013.py, has Verify and explicit Archive phases. It verifies pinned records/lock/profile, owned persisted container terminal state, no controller/service/guard/runner owner or listener, all WSL stopped, and five new frames. It never starts/stops WSL or the model. Root independently reviewed and verified the candidate, archived the exact lock once at14:56:17Z (complete receipt recorded in halogen-guard-incident-20261013-1433.json), then requested original Start-NativeModel once at14:56:49Z. Readiness is pending root monitoring; no cache activation has occurred. Historical failed records remain unchanged.

Recovery precedent: clean/docs/benchmarks/halogen-cache-gufo-followup-20260930.md, “Shutdown reporting corrections”; clean/docs/benchmarks/halogen0162-long-context-20261003.md, retained guard-failure example. No general recover/reconcile CLI exists in the inspected controller/service parsers. The older one-off scripts are pinned to different run IDs and must not be blindly reused.
