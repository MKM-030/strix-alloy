# Halogen 0.16.2 startup reserve — 4 October 2026

The five-cell 8K matrix aborted during its first `cstocka` load, before any
measured requests or completed cells. Windows physical RAM crossed the 18-GiB
runtime floor during KV allocation; commit headroom remained above 108 GiB.

| Retained backend Windows measure | Failed `cstocka` | Successful stock |
|---|---:|---:|
| Initial available RAM (GiB) | 38.524128 | 43.603760 |
| Minimum available RAM (GiB) | 17.554546 | 22.935123 |
| Observed physical decline (GiB) | 20.969582 | 20.668636 |

Both runs used the same checkpoint, pinned image, 262144-position KV pool,
single slot, cache policy and working-memory geometry. The failed log ended at
`dmalloc` 17.043 GiB; the successful load reached 19.030 GiB, leaving approximately
1.987 GiB of allocation tail. This allocation difference estimates remaining
cost; it is not an independently measured physical-RAM requirement.

The failed backend began 5.079632 GiB below the successful baseline. Availability
fell 4.193836 GiB between the coordinator's first sample and backend admission,
so an entry-only admission gate would be insufficient.

Live process metadata placed the game executable's start at 15:50:21 Berlin,
35 seconds before the guard crossing. From the last pre-game sample to the last
sample before the first model `dmalloc`, available RAM fell 1.138260 GiB and
commit grew 2.466324 GiB. Checkpoint copying continued throughout this window.
This establishes temporal interference; it does not isolate game allocation or
attribute the already lower admission baseline to gameplay.

At failure, the [host admission planner](../../backends/halogen-wsl2-0.16.2/scripts/memory_budget.py)
budgeted 36 GiB for v2: 16 GiB decline + 8 GiB uncertainty + a stale 12-GiB
reserve. The [managed runtime guard](../../backends/halogen-wsl2-0.16.2/scripts/service.py)
enforced 18 GiB. A provisional correction targets **44 GiB of actual backend
availability before create/start**, retaining the 18-GiB runtime floor and engine
geometry. This correction is implemented for all v2 contexts; w4b admission is
52 GiB. The projected remainder plus reserve and uncertainty rounds to 43 GiB;
44 GiB additionally rounds up the successful stock's starting headroom.
Commit admission now also budgets 18 GiB, giving 123/127/131 GiB at
4096/129024/262144 positions. Guest/direct-stage policies are unchanged.

Five targeted offline admission checks passed, including stable-window waiting,
timeout, scaling and actual service refusal below either full-capacity boundary
and at the failed 38-GiB baseline. Backend source pins passed. A fresh live load
has not yet qualified the provisional headroom estimate.

Retained comparison: `native-pld-stock8k-bookend-d2404f7300d74e08b303984f968b0d74`
and `stock8k-final-no-observer-1` under `server/.local/optimization9h-20261004`;
backend guard receipts identify runs `057bb3850e944eb2b1a987e0377a47e8` and
`ed4b0b7bfa4a4fc88def5ddfd21a5899`.

Supplemental recovery `aborted-stock8k-recovery-057bb3850e944eb2b1a987e0377a47e8-78af9da6275f437b96a5186bf5694158/release.json`
passed, with the runner lock absent. It records `normal_cleanup=false` and
`benchmark_qualified=false`; the original matrix and failure latch remain
unchanged. Recovery does not qualify the aborted benchmark. A fresh three-cell
PLD `3,3` → `0` → `3,3` plan was prepared with the corrected admission source,
unchanged 8K requests and 262144 capacity. It has not started. This narrows the
next experiment to regular decode and speculative selection; the abandoned
five-cell plan has no valid measurements to repeat.

The prepared three-cell attempt subsequently stopped before model creation.
Initial logged admission waits observed about 42.16–43.84 GiB; retained memory
samples later stayed above 44 GiB for roughly 63 seconds. The fresh check
after exclusive-host inspection then observed 42.32 GiB and refused creation.
Its engine log is empty, there were no requests, and normal cleanup/recovery
passed. The precise allocation responsible for the decline is unproved;
checkpoint/source preflight and exclusive-host inspection precede these
backend checks.

After the user's 16:49:41 Europe/Berlin reboot, a fresh identical comparison
completed all three cells in 16.03 minutes. Post-WSL availability was 50.444 GiB
physical / 209.103 GiB commit; lifecycle minimums were 28.318 / 123.348 GiB.
The corrected admission and 18-GiB guard remained enabled, and each cell
completed with normal cleanup. This qualifies the successful configuration
at the observed headroom, not the sufficiency of exactly 44 GiB. See the
[completed comparison](halogen0162-pld-stock8k-20261004.md).
