# Halogen GPU device predication, 2026-10-09

**Correctness passed; the frozen performance admission failed. Keep this candidate disabled.** The complete device-predication operation did not achieve the required 5% reduction against both controls. This owned synthetic component establishes no Prefill/Decode token-rate or MTP gain. No NPU execution, engine inference, or live integration occurred.

## Mechanism and frozen screen

The candidate moves the disabled BN64 adapter's two host validation decisions to device preparation and count selection. It preserves stock128 item generation and submits both projection families, selecting one through device counts. This removes the intermediate host decision waits while adding preparation, selection and inactive-branch launches.

| Arm | Complete operation |
| --- | --- |
| A: stock128 | Native items128, GU128, DN128, fold: four launches |
| B: synchronized64 | Actual legacy histogram/post decisions, eight D2H copies and two decision fences; native items64, GU64, DN64, fold: four launches |
| C: device predication | Items128, prepare64, items64, post-select, GU128, GU64, DN128, DN64, fold: seven native and two custom launches |

Both patterns use deterministic synthetic weights, metadata and BF16 inputs: N8192 token rows, R81920 routed rows, 512 experts, TOPK10, WIDTH2560 and HIDDEN640. Each token routes to ten distinct experts with stable forward/inverse permutations. Uniform has 160 rows per expert and 1024/1536 segments for BN128/BN64; boundary tails has 1001/1504 segments.

Each pattern has one excluded `ABC` warmup triad and six measured triads in the frozen order `ABC, ACB, BAC, BCA, CAB, CBA`. Every arm occupies each position twice. BATCH1 means one complete, freshly retired transaction per arm; this replaced the early BATCH4 proposal before hardware execution.

Admission required all correctness/cleanup checks to pass, C's host and GPU mean **and** median to be at least 5% below **both** A and B for **each** pattern, and balanced first/last-position groups to favor C.

## Measured complete-operation times

Values are mean / median milliseconds from six measured rows per arm and pattern.

| Pattern / endpoint | A stock128 | B synchronized64 | C device predication |
| --- | ---: | ---: | ---: |
| Uniform / host | 51.027410 / 51.184617 | 56.764241 / 55.695937 | 56.267885 / 58.759455 |
| Uniform / GPU event | 50.737296 / 50.912354 | 56.423490 / 55.397354 | 54.570787 / 57.234665 |
| Boundary tails / host | 77.112117 / 73.823568 | 77.631999 / 74.509487 | 78.461602 / 76.871041 |
| Boundary tails / GPU event | 76.614689 / 73.148678 | 77.138224 / 74.058846 | 76.535842 / 75.066353 |

None of the four pattern/endpoint cells passes the gate. C's uniform host mean is 10.27% slower than A; its small mean advantage over B does not extend to the median. Boundary host mean is slower than both controls. First/last-position results are mixed under both equal-position cohorts and matched triads grouped by C's position. No outliers were removed, values normalized, or patterns pooled to declare a winner.

Host timing uses CLOCK_MONOTONIC_RAW from the first required decision/submission through checked completion. B includes its two decision fences and eight D2H copies totaling 22,548 bytes. C includes its final completion fence, six retirement copies totaling 92 bytes, and status/count/oracle checks. Same-stream GPU events measure the queued operation span and exclude final host retirement readbacks. Allocation/module loading, common fixture construction/upload, sorting/rotation, output poisoning and full output/item/guard comparisons are outside timing.

## Correctness and limits

All 42 timed-operation rows, including six warmup rows, have zero bit mismatches and nonfinite words across all 52,428,800 GU, 209,715,200 DN and 20,971,520 final BF16 words. Item/count checks, guards and retirement pass.

All 41 correctness-only cases pass full output, guard and retirement checks: one accepted case and 40 stock fallbacks. They cover private empty routing, histogram/count rejection, all four item guards at first/middle/last corruption positions, stale epoch/stage/magic, first-stage failure, incoherent expected counts, consumed-state reuse and sticky failure. Generation40 preserves `accepted -> count rejection -> valid input still falls back`; transaction reuse does not clear sticky failure.

Recorded preparation stages exited zero, including the CPU oracle's 50 legacy fixtures plus protocol fixtures and 13 mock host-control cases. The mocks load no HIP runtime. Actual GPU execution exited zero with empty stderr and released all explicit owners; no real GPU fault or failed-submission recovery occurred. The fixture owns 2,516,167,560 guarded device bytes across 37 allocations and 9,400,672 host staging bytes.

Six observations per arm and two per position group do not establish statistical confidence or a precise production slowdown. Inputs are synthetic, with no captured model workload. Live allocation identity/extents, owner/epoch lifetime, stream serialization, transaction recovery and integration costs remain unqualified. Component milliseconds are not converted into engine token rates.

At the component receipt snapshot, separate normal-server restoration admission was pending. A subsequent root-owned continuation recovered a quiescence/memory-guard failure and recorded normal ready/open at 11:42:57 +02:00 on 9 October: context262144, active requests0, visible console and controller/backend identities verified. Its separate receipt hashes are bound in the JSON; the original failed restoration snapshot is preserved. Restoration does not change the rejected component gate or establish a serving gain. The broader acceleration goal remains unachieved.

[Compact evidence summary](halogen-gpu-device-predication-20261009.json) · [Source snapshots](halogen-gpu-device-predication-20261009/README.md)
