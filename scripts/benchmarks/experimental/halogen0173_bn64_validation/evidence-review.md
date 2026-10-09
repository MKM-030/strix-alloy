# Independent component evidence review

Date: 2026-10-09. Reviewed saved evidence and source only; no accelerator, test, build, API/engine call, lifecycle, fetch or STATE/Git operation. Root owns execution. This review does not authorize another BN64 or resolver-cache experiment.

The completed component result is internally consistent with **50 fixture comparisons and 256 measured pairs**. All 307 JSON stdout records equal the `result.json` records, the terminal summary is successful, exit status is 0 and stderr is empty. All 12 direct result references match their saved bytes and SHA-256, including the retained preparation receipt. The prior receipt's source/host/oracle log references also match, except for its historical coordinator-source limitation below. Fixture success means agreement with expected accept/reject results: 24 submit post-validation; 26 malformed histograms suppress that stage.

## Independently recomputed paired arithmetic

Each fixture has exactly pairs 0..63, 32 legacy-first and 32 aggregate-first, with `accelerated_first == (pair % 2 == 1)`. The host source excludes eight warmup pairs per shape, or 32 total warmup pairs. Both arms are measured with `CLOCK_MONOTONIC_RAW`, and every recorded duration is a positive integer.

The time reduction below is `100 * (1 - mean(aggregate_ns)/mean(legacy_ns))`. It is not the mean of the individual pair percentages and is not a serving-rate metric.

| Fixture | Measured pairs | Legacy mean ms | Aggregate mean ms | Time reduction | Legacy-first reduction | Aggregate-first reduction |
|---|---:|---:|---:|---:|---:|---:|
| uniform-512x160 | 64 | 2.204969 | 1.426303 | 35.314169% | 40.947086% | 29.241751% |
| sparse-tail-boundaries | 64 | 2.029196 | 1.310960 | 35.395110% | 41.958001% | 28.130185% |
| max-segments-skew | 64 | 2.057463 | 1.355792 | 34.103715% | 44.123477% | 22.439974% |
| single-expert-511 | 64 | 2.206803 | 1.482008 | 32.843655% | 39.176284% | 25.998763% |

Across all 256 equal-weight pairs, means are **2.124608 ms legacy** and **1.393766 ms aggregate**, a **34.398923%** reduction by ratio of means and an absolute mean difference of **0.730842 ms**. The mean individual paired percentage reduction is **32.984252%**; its median is **34.458889%**. Aggregate is faster in **253/256** pairs. These statistics have different definitions and must not be interchanged.

Order affects the magnitude materially: stratified reductions range from **22.439974% to 44.123477%**. Both order groups improve for every shape, and balanced alternation is present. The record supports a bounded component improvement under this schedule, not a stable engine speedup or a claim that every pair improves.

## Included costs and measured scope

The corrected `host.c` times the complete valid transaction, with **two `hipStreamSynchronize(NULL)` waits in each arm**. Legacy performs three histogram D2H copies and five post-item D2H copies: **8 calls / 22548 bytes**, including count checks and the exact one-buffer guard copy-and-scan order. Aggregate performs **two kernel launches**, **two D2H result copies / 64 bytes**, and **two H2D result-poison copies / 64 bytes** inside its timed interval. Kernel submission, argument preparation, device scans/reductions, both waits, freshness/shape/count decisions and the poison copies are included; none may be subtracted from the aggregate total.

Allocation, symbol/module loading, fixture construction and input uploads are outside the timed interval. Seven device allocations total **452660 bytes**, all owned by this fixture. The output ABI is 32 bytes; source checks epoch, stage and magic, compares full fixture results with the CPU oracle, and refuses post-validation after a failed histogram. The component does not enqueue native items/GU/DN/fold producers between the decision boundaries and has no live engine pointers. It therefore does not capture queued native producer work, normal engine host costs, throughput, Prefill, Decode or return on integration.

## Preserved server, reserves and cleanup

The retained preparation performed host compilation and the CPU oracle, then failed before hardware on `KeyError: 'LD_LIBRARY_PATH'`. Its hardware flag is false, oracle reports 50 fixtures, and both helpers closed. The successful resumed invocation has a new unique Linux component directory and runs only the component stage, using the same verified host binary/source/module. This is one completed accelerator component, not two GPU trials.

Both preparation and resumed receipts preserve health counters **completed 4 -> 4**, **cancelled 0 -> 0**, active requests 0 and draining false. The completed invocation records normal server ready/open, no engine requests, no lifecycle operation, no NPU, and no serving gain qualification. The source validates controller/backend/run/container identities and idle health, and the saved prelaunch GPU-load snapshot has 350 valid samples, no gaming process and no active competing sample.

The saved tracked memory minima are **24751419392 available bytes (23.051556 GiB)** and **118685655040 commit-headroom bytes (110.534630 GiB)**, exceeding the 22 GiB admission and 18 GiB continuation thresholds. These are sampled values with the reporting limitation below.

Terminal evidence has `passed=true`, `phase=terminal`, `original_ready_open=true`, `own_helpers_closed=true`, and null coordinator/helper identities after confirmed closure. The Windows component job reports closed; Linux component cleanup records no observed, signalled or remaining helpers and `closed=true`. Compiler cleanup is correctly scoped `not-launched` for the resumed invocation. The current control uses per-invocation paths, independently attempts component/compiler cleanup, and retains failed close owners for retry. The completed receipt contains no cleanup failure or recovery contradiction.

## Actionable findings and limits

1. **Historical preparation coordinator source is unavailable in WORK.** Its archived receipt names `run.py` at **16097 bytes**, SHA-256 `6c07fded3a2063db1235ca466277934a1b3da4b48eadbf724d702c7eee351a54`; that path now holds the successful resume coordinator at **17678 bytes**, SHA-256 `fcfdff0726b57e5a381eeec0804db339975057e3f618a257c8f32770d5833d2b`. Preserve the exact earlier source if independently recoverable; otherwise report it as hash-only provenance and retain a versioned coordinator snapshot before future control edits. The saved host source, binary and oracle logs remain verifiable, and the successful component coordinator reference matches.
2. **Memory fields are minima of the tracked samples.** `run.py` appends its direct polling frames and before/after frames, but does not append all additional `idle()`/admission memory observations. Describe these values as tracked sampled minima; future controls should include every collected frame if claiming a minimum over all observations. No continuous reserve guarantee is supplied by sampled evidence.
3. **Dormant constructor recovery gap remains outside this successful run.** At `run.py:137`, an `OwnedProcess` constructor whose setup cleanup fails can expose `error.owner` (`winjob.py:306`), before the stage's protected block or retained-owner list is reached. The outer handler stringifies that exception. Retain and retry such an exposed owner if this control is reused. The saved successful component reports no such exception; this does not contradict its confirmed cleanup.

No measurement-integrity defect was found in the completed stdout, paired arithmetic, costs, hashes, counters or terminal closure. Runtime pointer-fault/HIP-error equivalence, unsampled competing load, production input lifetimes and net engine behavior remain unqualified.

## Distinct normal-serving mechanism decision

**None is supported by this component evidence.** The measured eight-copy validation boundary belongs to the separate BN64 adapter. The normal 0.17.3 interposer sources do not contain that launch wrapper or validation transaction, as recorded in `../normal-resolver-cache-20261009/decision.md`. The component supplies no independently identified normal-serving D2H decision site, its allocation/lifetime contract, or its removable cost. Generalizing the aggregate technique would therefore be a new hypothesis, not a concrete normal mechanism indicated by these measurements. Do not repeat BN64, revive the rejected resolver cache, or project these component percentages onto serving rates.

## Evidence and source references

All references below are relative to this WORK directory. Hashes were freshly checked during this independent read-only audit.

| File | Bytes | SHA-256 |
|---|---:|---|
| `result.json` | 66700 | `7a156b7f19fb26d5214e87386aa72cf4990cd43fe0fcf8ca0a04b1b7172e005b` |
| `component-stdout.txt` | 37171 | `42cbbeb98b67472f311f8ae08276842e77bc6a10174687d7c5731c8348855dda` |
| `component-stderr.txt` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `build.py` | 4150 | `ca960ed29b600238c6d0bd3f2cfc21fd93aba9f3c479f43291b8079178fdc54d` |
| `run.py` | 17678 | `fcfdff0726b57e5a381eeec0804db339975057e3f618a257c8f32770d5833d2b` |
| `host.c` | 14225 | `e4c116fe6fe4167f2bbad83f89c6fb8e5332e8956fb8485ef006b2951355561a` |
| `oracle.c` | 16631 | `85f6644f24328c17fdb285c126611b6ba565e70fd30ba469a2fed6f1ed79ca15` |
| `validator.hip` | 10570 | `56f190706a70637172e29e81b98e0e736b5e4f4d13c5bc8fd0a2710b5f4e7191` |

Additional preserved references: module `build-v1/validator.hsaco`, 12880 bytes, SHA-256 `3769ad5b25d8fb0aa82ded60feeb8a156c658a2e56e121273fbd7510553c1218`; executed host `run-f93ef905e13142fea13167a5e174c295/host`, 29888 bytes, SHA-256 `f30fe4c33a4db8943fd29c12e67dcf86e086f312dc69e2ed2a5b44f7b3d1bfe6`; retained preparation receipt `preparation-failure-f93ef905e13142fea13167a5e174c295.json`, 10609 bytes, SHA-256 `01c85d22a1057712c9d1c69aa754babfefd65972cbe66ff7e9e485f8a51d9e6a`.
