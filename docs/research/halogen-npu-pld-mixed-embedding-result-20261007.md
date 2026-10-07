# Native PLD mixed embedding component result — 7 October 2026

**Retire this NPU prepared-prefix candidate for the current effort.** The
finite original-GPU arithmetic component passed, but its observed branch
budget is only 0.2–17.6µs across six fixed cases, with order and outlier
sensitivity. There is no demonstrated margin for live validation, slab
ownership, producer/transport contention or readiness coverage. This result
does not justify implementing a live hook, NPU producer or another live cohort.
It does not prove that every possible asynchronous producer is impossible.

The sealed [component contract](halogen-npu-pld-mixed-embedding-component-20261007.md)
now has one successful root-owned GPU receipt. The offline audit and all
96 measured pairs,24 warmup pairs, output hashes, counter checks, descriptive
statistics and retained outlier records are in the accompanying
[evidence JSON](halogen-npu-pld-mixed-embedding-result-20261007.json).

## Receipt and independent offline audit

The native receipt is
`server/.local/optimization9h-20261004/mixed-embedding-component-ef395bec938f40159d4c1843aef7bf53/result/native/mixed-replay.json`,
SHA256 `a6cd4a4c7a0595c64a155b4166be55cc574efc9831d80d86d9d961060bd28278`.
It reports `passed=true`,120 completed/120 exact-parity pairs and no error.
The retained container terminal records exit 0 without OOM; the outer
coordinator records success. No NPU was executed and no engine throughput
was measured. The source and wrapper seals remain unchanged.

Windows-only rechecks independently verified:

- All 10 root source/asset pins, including sealed mixed C, included FC C,
  wrapper, engine, HSACO and both fixture manifests.
- All 7 direct raw input/weight files against the saved runtime hashes/extents.
- All 24 saved output file hashes, exact extents and finite BF16 words.
- All 12 saved stock/mixed embedding/seed output pairs byte-for-byte.
- All 36 saved embedding rows against the frozen original M1 A/B output hashes.
- All expected launch, copy, allocation, module, event, drain, file and pair
  counters; all 120 timing records are finite and complete.

The final saved files independently establish final-case output parity.
Intermediate 120 device readback/parity checks and repeat stability are attested
by the sealed native receipt; their intermediate byte arrays were not all
saved. The Linux binary, installed HIP and bridge were not reopened by this
offline audit. Their saved runtime seals were crosschecked, including the
binary digest against root's owned compile receipt. No device, provider,
Linux, server or continuation operation occurred during this analysis.

The counter contract is 978 successful/attempted original launches, 972 copies,
8 setup synchronizations,17 allocations/frees,1 module load/unload,3 event
creates/destroys,720 records/elapsed calls,240 event waits,1 successful cleanup
drain, zero cleanup/file-close errors and 24 binary outputs. Immutable-input
rechecks are recorded true. The offline audit recomputed pair deltas and case
means; discrepancies stay below 1.5e-9 ms from decimal serialization. Event
segment additivity differences stay below 5e-8 ms. Those checks establish
serialization consistency, not timing resolution or microsecond accuracy.

## All measured samples and component budget

Exactly iterations 0–3 of each case are warmup. Iterations 4–19 contribute
16 measured pairs per case,96 total; no measured pair is removed. Positive
`B−T` means the stock embedding branch took longer. B is original full-k
gather/RMS/Mk; T is correction-only original gather/RMS/M1. Full-count seed
remains present on both paths. All table times below are microseconds.

| Case | B mean | T mean | B−T mean | B−T median | Exploratory block interval | Positive pairs |
|---|---:|---:|---:|---:|---:|---:|
| A-k2 | 172.401 | 166.339 | 6.062 | -0.093 | -2.985..15.108 | 8/16 |
| B-k2 | 165.696 | 165.494 | 0.202 | -1.089 | -8.075..8.479 | 7/16 |
| A-k3 | 175.278 | 170.148 | 5.130 | 7.280 | -2.727..12.988 | 11/16 |
| B-k3 | 187.767 | 170.171 | 17.596 | 8.781 | -1.570..36.762 | 12/16 |
| A-k4 | 175.405 | 168.541 | 6.864 | 3.210 | -2.532..16.260 | 9/16 |
| B-k4 | 181.570 | 169.461 | 12.109 | 18.526 | -0.133..24.351 | 11/16 |

The pooled descriptive B−T mean is 7.994 µs, median 4.549 µs, sample SD 21.460 µs,
with 58/96 positive pairs and range -22.852..120.538 µs. Equal counts make this
an equal-case summary of six fixed synthetic workloads. It is not weighted
by real PLD acceptance frequency and is not an estimate of live savings.
The largest case mean is **B-k3 at 17.596 µs**.

Each case has eight stock-first and eight mixed-first measured pairs; overall
balance is 48/48. Deterministic alternating order is balanced but not
randomized. Adjacent pairs `(4,5)` through `(18,19)` form eight blocks, each
containing both orders. The exploratory block intervals use
`mean ± 2.364624252*SD(block means)/sqrt(8)`; every case includes zero.
Conventional per-pair t intervals are retained in JSON as another diagnostic;
their independence assumptions are not established. These intervals describe
sensitivity in this one serial run, not a population 95% bound, formal
multiple-comparison result or causal effect.

## Order, unchanged seed and retained extremes

| Case | B−T mean, stock first | B−T mean, mixed first | Full-seed total delta mean | Seed delta mean |
|---|---:|---:|---:|---:|
| A-k2 | 18.023 | -5.900 | 8.209 | 2.148 |
| B-k2 | 3.011 | -2.608 | 6.574 | 6.372 |
| A-k3 | 6.805 | 3.456 | -0.663 | -5.794 |
| B-k3 | 14.341 | 20.852 | 15.487 | -2.109 |
| A-k4 | 14.107 | -0.379 | 5.130 | -1.734 |
| B-k4 | 16.863 | 7.356 | 17.302 | 5.193 |

Across the 96 samples, stock-first B−T mean is 12.192 µs and mixed-first is
3.796 µs; mixed-first median is -0.563 µs. Three cases change the sign of their
mean by order. Chronological case sequencing, cache/scheduling conditions and
event/enqueue gaps remain potential influences; this receipt does not isolate
their causes. The event intervals include host enqueue gaps and event overhead,
so they are not a shader-instruction-only estimate.

The pooled full-seed total delta mean is 8.673 µs and median 3.530 µs, with
56/96 positive pairs, SD 38.552 µs and range -146.160..143.850 µs. The same full-k
seed kernel, common hidden batch and byte-identical E rows appear on both
paths. The mixed signs of seed differences offer no supported seed reduction;
the component's intended saving remains B−T.

Per-case 1.5×IQR flags identify five high B−T samples, all retained:

- A-k2 iterations 4, 14, 18: 31.710, 37.313, 51.454 µs.
- B-k3 iteration 7: 120.538 µs.
- A-k4 iteration 18: 82.065 µs.

B-k3's mean 17.596 µs is notably above its 8.781 µs median. As an influence
diagnostic only, omitting its single largest observation would yield 10.733 µs;
the reported estimate keeps that observation. A-k4's analogous diagnostic is
1.851 µs versus its retained mean 6.864 µs. No trimmed result is used for the
decision.

Two mixed-path host enqueue/wait intervals exceed 10 ms: B-k3 iteration 7 is
40.447711 ms and B-k4 iteration 18 is 40.300401 ms. Their corresponding GPU event
totals are 0.384498 ms and 0.334522 ms. The first coincides with the largest
branch delta; this does not identify the cause of either observation. Both
remain in all statistics. Pooled host stock−mixed mean is -0.821611 ms versus
median -0.002021 ms, showing how those wall-time extremes dominate the mean.
No quiet-system or host-speed conclusion follows.

## Why there is no next live cohort

This run answers the finite arithmetic question: original M2/M3/M4 embedding
outputs and original full-k seed agree byte-exactly with an original-GPU M1
prepared prefix plus native gather/RMS/M1 correction for the frozen A/B rows.
It does not establish live vocabulary lineage, an NPU prefix's numerical
equivalence, one-shot lease lifetime, the early publication window, useful
coverage or concurrent contention.

The measured budget is already optimistic: prefix and hidden preparation,
table/upload copies, poison, validation and readback are outside the intervals.
A live ready round would save only `B(k)-T(1)-C-J`; missed publication has no
embedding saving while preparation and lookup still cost resources. C and J
have no demonstrated bound below this microsecond-scale margin. Native batches
must not be priced as accepted-row count times the 152.995 µs scalar FC figure.

The previous v3 NPU/pipe/staged times 1.3307/2.4231/6.1337 ms concern a different
frozen scalar handoff and are not direct costs for a new asynchronous producer.
They supply no evidence that a new producer's lead time, validation or
contention fits the small margin observed here. Building that producer or
another ready64/parser/eventquery cohort now has no measured cost target.
Keep the offline planner default-off and preserve this arithmetic receipt;
retire the current PLD NPU prepared-prefix acceleration attempt. No native
skip, full-head acceptance, NPU benefit or token-rate claim is admitted.
