# Post-service-disable re-measure: throughput unchanged, warm-up ramp gone (2026-09-16)

The operator disabled 20 Windows services for performance and asked for a re-measure. **Result: no
change in steady-state throughput — prefill and decode are within ±2% of the previous run at every
depth. The one real difference is that prefill reaches steady state in 1 rep instead of 3–4.**

## What was disabled

20 services set to `Disabled`, notably:

| service | what it does | why it could matter |
| --- | --- | --- |
| **WSearch** | Windows Search indexer | continuous background **disk I/O** |
| **DiagTrack** | Connected User Experiences / telemetry | periodic disk + network |
| `dmwappushservice` | device-management WAP push | network |
| Xbox stack (`XblAuthManager`, `XblGameSave`, `XboxGipSvc`, `XboxNetApiSvc`) | Xbox Live + accessory mgmt | background |
| `RemoteRegistry`, `RemoteAccess`, `NetTcpPortSharing`, `ssh-agent` | remote/network services | network |
| `WMPNetworkSvc`, `RetailDemo`, `WalletService`, `UevAgentService`, `DialogBlockingService` | misc | background |
| `AppVClient`, `MsKeyboardFilter`, `shpamsvc`, `tzautoupdate` | misc | background |

Nothing GPU-, memory-, clock- or power-related was touched; the carve, drivers and our launch flags are
unchanged.

## Steady-state throughput: unchanged

Same configs as before: `-c 262144`; prefill shape `-ub 16384` no drafter; MTP shape `-ub 8192` +
shared head n-max 2, `gen 256`. Warm reps (rep ≥ 1).

| depth | prefill before | **prefill after** | Δ | MTP decode before | **MTP decode after** | Δ | acceptance before → after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 16,384 | 1030† | **1030** | 0% | 31.58 | **31.19** | −1.2% | 56.1% → 56.1% |
| 65,536 | 984 | **990** | +0.6% | 32.70 | **32.62** | −0.2% | 64.9% → 64.9% |
| 131,072 | 907 | **924** | +1.9% | 32.79 | **32.76** | −0.1% | 69.8% → 69.8% |
| 251,904 | 811 | **811** | 0% | 31.33 | **31.03** | −1.0% | 72.9% → 72.9% |

† 16k prefill before is the 4-rep steady value (1030); the 2-rep ladder showed 862 because it had not
converged (see below).

**Every number is within run-to-run noise (±2%).** Acceptance is identical to the decimal at 16k, 65k
and 131k — which is a strong signal that the *computation* is bit-for-bit the same; only timing moved.

## The one real change: prefill warm-up is gone

| depth | before: rep0 → rep1 → rep2 → rep3 | after: rep0 → rep1 → rep2 → rep3 |
| ---: | --- | --- |
| 16,384 | 646 → 817 → 870 → **1033** | 662 → **1018** → 1014 → 1030 |
| 65,536 | 602 → 984 (2-rep) | 710 → **990** → 985 → 984 |

Before, prefill needed **3–4 passes** to reach steady state (rep 1 was ~80% of steady). Now **rep 1 is
already at steady state**. The steady-state *value* is the same — the machine simply gets there
immediately.

**Interpretation:** this is consistent with removing **background disk contention** (WSearch /
DiagTrack). The model is mmap'd, so the early reps were paying page-fault / disk-read cost; with the
indexer dormant that cost is gone. It is a *latency-to-warm* improvement, not a throughput improvement.

## Why throughput did not move (and could not have)

Consistent with the session's finding that **decode is ALU-issue-bound, not memory-bound**
(`decode-alu-bound-dp4a-20260916.md`): disabling background disk/network services reduces *I/O*
contention, which decode does not consume. And prefill is GPU-bound at ~1030 t/s once warm, so
removing background work cannot raise the ceiling — it only removes the ramp to it.

## Practical consequence

- **Steady-state serving performance is unchanged.** No regression, no gain — the service changes are
  safe (throughput-wise) but not a speed lever on this workload.
- **First-request latency is better:** a large prompt now hits full prefill speed on the second
  request instead of the third or fourth. For interactive use that is a real, if small, user-visible
  win.
- **The earlier "capacity penalty" and "deep cliff" are still artifacts**, not service effects: both
  were the same warm-up ramp, now shown to be removable by reducing background I/O rather than by any
  `-c` change.

## Caveats

- Single session, sequential measurement; ±2% noise floor applies. The 131k +1.9% is at the edge of it
  and should not be read as a real gain.
- The change is not A/B'd (services cannot be toggled mid-run safely). The claim is "no throughput
  change, faster warm-up", not a controlled causal attribution to a specific service.

## Artifacts

`results/lc-post-prefill.{json,log}` (4 reps shallow, 2 deep), `results/lc-post-mtp.{json,log}`
(gen 256). Pre-change comparators: `results/lc-lc-prefill.json`, `results/cap-262144.json`,
`results/lc-lc-mtp-g256.json`, `results/lc-lcwarm-prefill.json`.
