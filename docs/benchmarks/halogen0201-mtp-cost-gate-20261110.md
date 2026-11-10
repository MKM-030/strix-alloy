# Halogen 0.20.1 native MTP cost comparison

The complete `gate / cost / gate` experiment finished on 10 November 2026 UTC.
Both input sizes passed all three arms, each with one excluded warmup and three
measured requests. All 24 responses preserve the exact output bytes for their
input size. The normal authenticated server was restored on port 8840.

| Actual input tokens | Configuration | RAW prefill tok/s | RAW decode tok/s | API head accepted/drafted | Whole HTTP QPC mean, s |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8192 | Gate before | 1277.86 | 46.82 | 189/318 = 59.43% | 9.1827 |
| 8192 | Cost candidate | 1156.47 | 42.54 | 189/291 = 64.95% | 10.2370 |
| 8192 | Gate after | 1068.84 | 45.38 | 189/318 = 59.43% | 10.6252 |
| 16384 | Gate before | 1291.32 | 42.71 | 165/327 = 50.46% | 15.7232 |
| 16384 | Cost candidate | 1264.97 | 44.19 | 171/294 = 58.16% | 15.8940 |
| 16384 | Gate after | 1193.86 | 39.09 | 165/327 = 50.46% | 17.0601 |

Rates are arithmetic means of the three measured requests. Acceptance pools
their API head counters. RAW clock bracketing validates the measured phases
under the declared protocol. These runs include observer and trace overhead.
The original API-only cohort remains separately recorded. [Numeric evidence](halogen0201-mtp-cost-gate-20261110.json), [API-only observations](halogen0201-natural8k16k-20261110.md).

## Outcome and serving decision

At 8192 input tokens, cost raises API head acceptance by 5.51 percentage points,
but decode falls 9.15% against the before control and 6.26% against the after
control. At 16384 tokens, acceptance rises by 7.70 percentage points and decode
is 3.46% above the before control and 13.04% above the after control.

The stock controls drift materially. Their prefill falls from 1277.86 to
1068.84 tok/s at 8K and from 1291.32 to 1193.86 at 16K. Consequently the
candidate's prefill lies between the controls in both cases. Whole HTTP time
also lies between the controls. The mechanism has a workload-dependent decode
result and provides insufficient evidence for a general serving improvement.
The normal profile retains its existing gate rule and paired 2048-token
prefill settings. A production cost-rule speedup remains unqualified.

## Frozen workload and controls

Both inputs use the exact non-repeated contiguous War and Peace prefixes of
the earlier natural workloads, with 8192 and 16384 actual input tokens. Every
request generates exactly 128 tokens at temperature 0 and seed 1, finishes
at length, and reports zero reasoning tokens and zero cache reuse. Cache is
Off with `no_store`. Lookup and grammar propose zero tokens.

The v2 profile fixes context/pool 32768, one slot, concurrency 1, paired 2048
prefill chunk and arena, Q4 draft vocabulary, MTP gate threshold 0.90, PLD
`3,3`, Vision Off, Thinking Off and prefetch 0. The only treatment is the
native cost rule. All 48 request-entry/post-request admission receipts pass,
including GPU-load checks. Startup remains 30/131 GiB physical/commit,
measurement entry 22/22 GiB and runtime reserve 18/18 GiB. [Prospective V5 protocol](halogen0201-mtp-cost-gate-plan-20261110-v5.json).

## Counter and clock scope

The table retains API-reported all-neural head accepted/drafted counts.
Independent reconstruction of the full accepted count remains unavailable,
and `acceptance_independently_reconciled` stays false. The saved native chain
counters have a narrower scope. At 8K they pool to 186/315 for each gate
control and 186/288 for cost. At 16K they agree numerically with the API head
totals in this cohort. No fixed offset or counter correction is applied.
Performance eligibility is declared separately from acceptance reconstruction.
[Counter derivation and limitation](../research/halogen0201-counter-scopes-20261110.md).

RAW lower/upper bounds describe clock bracketing. Statistical confidence
intervals were not estimated. API phase clocks retain their separate
unqualified status, and Windows QPC measures each complete HTTP response.
Observer overhead and stock-control drift limit extrapolation to ordinary
production traffic. Manufacturer parity and NPU acceleration remain
unestablished by this experiment.

## Restoration and reproducibility

The run used public plan SHA256
`68b5010de6681c17dd10507d82bd51a8372efbed528ad8e5bca45e7589d1e59a`
at registered commit `c7b7704225af15637d299487e2eebe96f3e483a4`. All 51
executed source pins match. Offline export revalidates all six complete
cohorts, RAW journals, exact responses, QPC records, admission receipts and
native rule activation. Both input sizes qualify for the declared performance
comparison.

Cleanup verified 50 restoration hashes, all 47 normal source-manifest members
and removal of the three overlay-only files. The original normal and three
measurement owners have stopped/absent receipts. The restored normal
controller run is `cb06ad92e8174149bd2e7dcdba2d3ae1`, with backend run
`13e2437a04d14f628ad4a00b7032fe16`.

A fresh authenticated check at 23:00 UTC confirms API and engine 0.20.1,
matching versions and healthy serving. An authenticated chat request returns
`READY`. The persistent request/response console remains open on port 8840.
Post-restoration Windows CPU checks pass 24 tests. Eight WSL/GCC-only vision
fixture tests were skipped in that Windows verification. [Current start and integration](../research/halogen0201-update-20261110.md).
