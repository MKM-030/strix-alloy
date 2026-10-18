# Halogen 0.17.3 DFlash head-constructor capture diagnostic

Session **85409** completed with exit code **1**. The candidate reached API readiness, passed request admission and processed the diagnostic's **16,384 input tokens**. It then rejected the actual request birth before exporting or ingesting any feature packet. No new serving prefill rate, decode rate, acceptance value or acceleration is qualified.

The normal colleague server was restored and verified ready/open at closure. The retained checks identify controller **33780**, backend **35452** and visible console **34872**, with context capacity **262,144**. This report independently reviews saved evidence; it does not perform a live hardware or API probe.

## Scope and workload

The head-constructor candidate was a single capture-only diagnostic, not a performance cohort. Its runtime context capacity was **32,768**; the restored normal server uses **262,144**. The submitted request declared 16,384 actual input tokens and a maximum of 128 output tokens, temperature 0, seed 1, no streaming, `drafter=mtp` and `cache_prompt=false`. `ready_provider_enabled` remained false and the NPU remained disabled. Startup smoke requests precede the diagnostic in the engine log; they are separate requests and must not be reported as diagnostic decode results.

The trial directory is:

```text
server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/
  dflash-root-head-ctor-capture-launch-20261010/trial/
```

## Admission and memory observations

| Saved observation | Physical reserve | Commit reserve |
| --- | ---: | ---: |
| Candidate-ready snapshot | 23,877,267,456 bytes = 22.237438 GiB | 121,817,341,952 bytes = 113.451241 GiB |
| Minimum across 76 request-watcher frames | 23,153,496,064 bytes = 21.563374 GiB | 121,194,954,752 bytes = 112.871597 GiB |

The ready snapshot exceeded the 22/22 GiB experiment-entry floor. `submitted.json` and the engine's request 3 logs establish that the actual request was submitted. `memory.json` records 76 frames and `guard_error=null`; both recorded minima remained above the 18/18 GiB runtime floor. The physical and commit minima are independent frame minima, not necessarily simultaneous observations.

This is an admission success after the constructor lifetime change. It does **not** measure exactly 1.184 GiB of physical memory reclamation or isolate the patch's memory effect. Comparisons with an earlier candidate-ready snapshot are uncontrolled. No serving performance conclusion follows from these reserve snapshots.

## What executed and where it failed

The retained `startup-native-runtime/native-result/native-loaded.json` reports `WorkerLoadedAccepted`. Its loaded receipt precedes `CaptureOnlyAvailable` in the same monotonic clock domain, so the bank had loaded before request execution.

The saved candidate `engine.log` establishes this order for diagnostic request 3:

| Engine log line | Observation |
| --- | --- |
| 1146 | Prefill begins for 16,384 input tokens. |
| 1153 | Prefill reaches 8,192/16,384. |
| 1158 | Prefill reaches 16,384/16,384. |
| 1159–1160 | `outer_entry_disposition`, then `callback_rejected`. |
| 1161 | Worker enters `Held`: `Stale/reused/unproved actual Request birth`. |
| 1162 | `ns/net` disappears after the first callback rejection. |
| 1163 | The completion request returns HTTP 502. |
| 1168 | Supervisor observes native exit code 125. |

The client retained `engine closed the connection`. The first relevant failure is request-birth validation; the later namespace/process-identity messages do not establish a preceding namespace cause. The saved receipts do not identify the exact failed birth-validation predicate, so a guard change or causal fix cannot be inferred from this result.

The retained native terminal receipt is **`.native-terminal.pending`**, with state `FailedRetained`. Its counters and flags distinguish work performed by Halogen from data accepted by the capture worker:

| Native capture result | Value |
| --- | ---: |
| Request births observed | 1 |
| Birth acknowledged | false |
| Feature export attempts | 0 |
| Fence-qualified packets ingested | 0 |
| Prefill rows ingested by worker | 0 |
| Decode rows ingested by worker | 0 |
| Worker finish / worker drain / generation drain | false / false / false |

Halogen's 16K prefill completion therefore does not imply a successful worker prefill handover. The zero decode-ingestion counter is not a measured zero tok/s rate. Diagnostic request 3 had no successful completion, no completed 128-token output and no acceptance measurement. The log's rounded prefill duration is not a qualified benchmark value.

Wall-clock timestamps in saved Windows records and candidate engine log prefixes do not form a reliable shared timeline: `submitted.json` is stamped 00:38:02.608050 UTC after conversion from its +02:00 offset, while request 3 log prefixes span 00:37:39–00:37:54 UTC. Engine line 1151 also has a later health timestamp between earlier request lines. This report relies on request identity, local log sequence and same-domain monotonic receipts; it derives no cross-domain latency from those timestamps.

## Closure and normal serving restoration

The candidate's capture retirement remained unqualified. `capture-cleanup.json` explicitly records `qualified_retirement=false` and `emergency_cleanup=true`; the supervisor retained a failed handshake. These facts coexist with successful owned-process cleanup and memory recovery by the ordinary lifecycle. They must not be described as a successful capture retirement or generation drain.

The trial's `outcome.json` records `diagnostic_completed=false`, `new_cohort_qualified=false`, `serving_gain_qualified=false` and `colleague_server_ready_open=true`. `terminal-checkpoint.json` records terminal session 85409, exit 1 and closed coordinator identities. `retained-startup-runtime.json` preserves 20 files after verified candidate cleanup.

`restored-ready.json` and the later terminal checkpoint agree on the normal server identities:

| Role | PID | Creation time (100 ns) | Run ID |
| --- | ---: | ---: | --- |
| Controller | 33780 | 134360663424341664 | `a52ebf89761d4e9dacf7fd606c5574b8` |
| Backend | 35452 | 134360663529103134 | `fc178c369ca64f1db4308455930642c3` |
| Visible PowerShell console | 34872 | 134360663421707391 | — |

The restored health snapshot is `status=ok`, context 262,144, `active_requests=0` and `draining=false`. Restoration completed at the saved 00:42:05.543105 UTC readiness snapshot; the terminal closure verification is stamped 00:44:23.814300 UTC. Root's ordinary `root_current_check.py` verification is saved in `dflash-checkpoint-20261009/current-preserved.json` at 00:44:24.232580 UTC and confirms these process identities and healthy normal service. These are closure observations, not a claim that the same identities will remain current after subsequent authorized experiments.

## Qualification and next prerequisite

This attempt advances the admission evidence and reaches the real request boundary. It supplies no qualified acceleration, NPU serving result, acceptance gain, successful feature export or successful capture retirement. The real-KV shadow experiment remains ineligible because its accepted-capture, retirement and generation-drain prerequisites were not met. The next correction should identify and preserve the actual birth-validation predicates rather than weakening them.

The last qualified serving measurement is retained separately in [the natural 16K benchmark](../benchmarks/halogen0173-natural16k-raw-20261009.md). This failed diagnostic does not replace that cohort.

The independent source-only receipt, input pins, derived values and review limitations are retained at:

```text
server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/
  dflash-head-ctor-terminal-evidence-20261010/independent-evidence.json
```
