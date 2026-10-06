# Independent original-W preparation screen review, 6 October 2026

**Retire the W16=false preparation candidate for optimization after this
completed screen.** Its captured prepared W is exact, but the measured evidence
does not show a robust benefit. The conditional complete prep-plus-stock-GEMM
plan is therefore ineligible; no full-path or serving qualification follows.

This review independently read the saved evidence, compared the complete W
files in bounded 1 MiB chunks, computed their SHA256 values, and recomputed
statistics from the 16 measured raw pairs. It performed no GPU, NPU, WSL,
engine runtime, build, test or lifecycle operation. All work consisted of
saved-file reads and writing this supplement. The evidence directory is
`server/.local/optimization9h-20261004/alloy-prefill-deq-3b1765aa3da1458388076866072fdf7a/`.

## File bindings and exactness

| Evidence relative to that directory | Actual bytes | Independently computed SHA256 |
|---|---:|---|
| `comparison.json` | 1,588 | `9f5abf4a22534f5efc6b11dfe36844a4b4b3937bb7a7791b21fa1d0e40ecd549` |
| `result.json` | 726 | `ba4638613d96e802dcd47f7cc63d9925e9fd350f6bb4d45ad6e5bb5fadc22871` |
| `component/native/timing.json` | 26,266 | `093df60932ae8d4b1b6d36574c9bba9c455e4d451f4bb3b93853018f8d92e4a7` |
| `component/runtime.json` | 2,341 | `792ebb835191d3e41c1d552376588ba48c07198cf238926607c4fda006f2a10d` |
| `component/native/original-W.u16` | 52,428,800 | `6374bfe3b7c36c29cabeb631f125d4291bdf62735abbb0f5c177615d62d675a7` |
| `component/native/candidate-W.u16` | 52,428,800 | `6374bfe3b7c36c29cabeb631f125d4291bdf62735abbb0f5c177615d62d675a7` |

The streaming comparison covered all 52,428,800 bytes with **zero differing
bytes**, independently confirming the two excluded qualification outputs.
Each file contains all 26,214,400 BF16 words for N=10240, K=2560. The actual
timing-file hash agrees with `comparison.json.raw_sha256`; its oracle hash and
all 42 recorded run hashes agree with both saved W files. The timed outputs
were not retained as separate files, so their per-launch equality is supported
by the raw recorder and its reviewed implementation rather than another saved
output comparison. Exactness is established for this captured fixture and
screen; it is not a proof for every possible packed tensor.

The current 28,151-byte native source independently hashes to its frozen
`0fe60be21173d1f2395725da4ea83aa1210b5d492f3e871927b4e00941d89e5b`.
The current 5,481-byte wrapper hashes to
`1935d06f63d1b97e5214a0919f37142346412244ed3426a531fb71bb23208e1a`.
Both match the runtime receipt. Static AMDGPU metadata confirms six kernel
arguments with offsets 0/8/16/24/32/40 and sizes 8/4/8/8/8/4, kernarg
size 44/alignment 8, wave32, static LDS 65,536 and maximum workgroup sizes
512/256. This supports the bound launch ABI; it does not prove arithmetic
equivalence independently of the output oracle.

The runtime receipt binds a 35,184-byte native executable to SHA256
`69142bb40b6434df6abeb9388c2c0bc4ec8dfaaadf221cce2a8ea94b6329bf4b`.
That digest agrees with the saved build receipt, but this audit did not
independently access the WSL executable or rerun compilation. Compiler,
header and transitive-library bytes are not sealed by the build receipt.

## Counter and boundary audit

The raw run sequences are contiguous 0 through 41: two untimed qualifications,
eight excluded warmup launches and 32 measured launches. They contain exactly
20 timing pairs: four warmup and 16 measured, alternating original-first and
candidate-first throughout, with eight measured pairs per order and 21 total
launches per arm. Every run records attempted/completed/exact=true and zero
word mismatches. All raw run values agree with their corresponding pair row.
Every pair reports a complete 26,214,400-word check per arm and zero primers.

The recorded counters reconcile: 42 attempts/successes/poisons/pre-launch
completions/full completions, 45 copies, four allocations/frees, one module
load/unload, two event creates/destroys, 80 event records, 40 waits and 40
elapsed-time queries. There is one successful cleanup synchronization, zero
cleanup errors and zero file-close errors. The qualifications precede all
timing; original poison is 0xff and candidate poison is 0xa5. The same original
code object supplies the bound 512-thread and 256-thread sibling kernels,
with grid (20,80,1), PRE=1, KFAST=1 and six arguments.

`result.json` reports owned-container/job cleanup proven, monitor stopped and
cleanup_pending=false. These are saved owner receipts; this review did not
independently inspect live lifecycle state or claim stock restoration.

## Recomputed measured statistics

All times below are milliseconds. Delta means candidate minus original, so a
negative value favors the candidate. The four warmup pairs are excluded.

| Metric | Original mean | Candidate mean | Paired delta mean | Paired delta median | Candidate wins |
|---|---:|---:|---:|---:|---:|
| GPU event | 0.872904110375 | 0.867690365750 | -0.005213744625 | +0.007455498500 | 8/16 |
| Host enqueue/wait | 1.239335625000 | 1.215512687500 | -0.023822937500 | -0.010311000000 | 9/16 |

Separate original/candidate medians are 0.919883519/0.9102090005 for GPU and
1.2191635/1.287583 for host. These are not medians of paired differences.
The GPU paired standard deviation is 0.290744418, with differences ranging
from -0.495029925 to +0.489932954. The host paired standard deviation is
0.317801905, with differences from -0.666961 to +0.419917. The small mean
advantage is much smaller than the variation among retained pairs.

| Group, eight measured pairs each | GPU paired delta mean | GPU wins | Host paired delta mean | Host wins |
|---|---:|---:|---:|---:|
| Original runs first | -0.011059880375 | 4/8 | -0.165348625000 | 6/8 |
| Candidate runs first | +0.000632391125 | 4/8 | +0.117702750000 | 3/8 |
| First measured half, pairs 4-11 | +0.011926621500 | 4/8 | -0.053488500000 | 3/8 |
| Second measured half, pairs 12-19 | -0.022354110750 | 4/8 | +0.005842625000 | 6/8 |

GPU original/candidate means change from 0.81459036425/0.82651698575 in the
first half to 0.9312178565/0.90886374575 in the second. Host means change
from 1.204530625/1.151042125 to 1.274140625/1.27998325. The GPU quarter delta
means are +0.209113732, -0.185260489, -0.04700575725 and +0.00229753575.
Order and chronological splits do not establish a consistent advantage.
The retained evidence does not identify the cause of the variation.

GPU events measure one preparation launch on the default stream. Host timing
includes launch, event submissions and full completion. Poisoning, pre-launch
completion, readback, equality checks, hashes, file I/O and initialization
are excluded; this is not a complete prep-plus-GEMM interval.

**Release the captured exactness evidence; retire the performance candidate.**
The native replay's `passed=true` records successful exactness, execution and
cleanup, not a performance qualification. No repeat cohort, full-path test,
global W16 setting, serving override or token-rate conversion is justified by
this result. GEMM, Prefill, Decode and native acceptance remain unmeasured.
