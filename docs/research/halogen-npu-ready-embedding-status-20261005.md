# Halogen NPU ready embedding status

Date: 2026-10-05. Source-only report from retained receipts. The ready whole embedding branch cache is implemented and default-off. Both completed GPU controls preserve output/acceptance and prove the intended skipped launches. The second path, using fixed rows and batched validation, still loses decode performance. No acceleration or NPU adoption is qualified.

The distinct `ready64-v1` mode retains `gpu64-v1` and borrows completed 5120-byte BF16 projections for eligible count1 heads. Hits skip embedding gather, embedding RMS, and E M1, changing only the embedding input to the Wire-D seed. Native FC dispatch and hidden/residual/state/history work remain; `model+0xb00` is never rebound. `fixed-v1` imports immutable rows once and executes the complete native branch on misses. `capture-v1` captures original GPU projections and exports before forced stop. Compile admission defaults to zero; malformed armed sequences fail stop. The [consumer contract](halogen-mtp-ready-embedding-consumer-contract-20261005.md) records ABI/lifetime/native seams and earlier host/sanitizer/compilation checks, whose scope does not establish NPU qualification.

The [memory fabric review](halogen-npu-memory-fabric-20261005.md) finds 4 MiB memory-tile plus 2 MiB compute-tile raw SRAM. This distributed storage is not a GPU heap. Shared host/NPU/GPU buffers use existing DDR and add no capacity; no reviewed API maps tile SRAM into GPU space. DDR-to-tile DMA and context/power lifetime remain relevant, and the Windows-NPU-to-WSL/DXG import/fence contract is unestablished. Primary references: [MLIR-AIE devices](https://xilinx.github.io/mlir-aie/dev/Devices/) and [amdxdna documentation](https://www.kernel.org/doc/html/next/accel/amdxdna/amdnpu.html).

Qualification is strictly GPU-first: seal original GPU projections and test a fixed token set with stock bookends, counting real hits and native misses. Only after the consumer improves serving should NPU preparation run offline with the GPU engine absent. Identical-token GPU/NPU controls must include preparation, upload, and amortization costs. The [local path](halogen-npu-local-memory-path-20261005.md) and [algorithm review](halogen-npu-algorithm-candidates-20261005.md) retain the numerical gaps: old NPU A/B outputs differ in 847/858 BF16 words despite tolerance agreement; exact portable RMS evidence covers an artificial 64-row set.

Retained attempt receipts are in the original checkout:

| Cohort | Actual outcome |
|---|---|
| [aac806](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-aac806ccc3524f378a05d600f510e717/result.json) | Admission stopped because another container was running; no measured window. |
| [1f7780](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-1f77803b194b400b9e1b4f046b49ef87/result.json) | Stock-before measured; cleanup/recovery and restoration unresolved in this receipt; no candidate window. |
| [e5d0b0](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-e5d0b0b317e748d7a9baadcca4dd0cfa/result.json) | Stock-before measured; root state read failed and candidate failed startup at the binding gate; original restored open. |
| [47fef3](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-47fef3e497e145458d7e6ea2619c2df5/result.json) | Stock-before measured; candidate became ready, then the bounded counter-read subprocess failed before candidate inference; original restored open. |
| [80fa32](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-80fa32abe12b47ccb0e4a6a43d15734e/result.json) | Corrected reader; stock/candidate/stock completed, GPU rows captured, original restored open; no NPU executed. |
| [cda6bf](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-engine-cda6bf280e7242fd8b20c1cb5162ee56/result.json) | Batched fresh validation and fixed 52 GPU rows; stock/candidate/stock completed, original restored open; no NPU executed. |

Both completed cohorts used one warmup and three measured repetitions per window at 8192 input/128 output tokens. Measured means are:

| Control | Window | Prefill tok/s | Decode tok/s |
|---|---|---:|---:|
| Capture | Stock before | 1279.981374 | 41.263472 |
| Capture | GPU candidate | 1291.979784 | 28.466336 |
| Capture | Stock after | 1287.048779 | 41.458638 |
| Fixed/batched | Stock before | 1301.120816 | 41.643338 |
| Fixed/batched | GPU candidate | 1302.526579 | 32.539165 |
| Fixed/batched | Stock after | 1279.023399 | 41.534636 |

Against each cohort's arithmetic stock-bookend mean, capture deltas are +8.464707 tok/s (+0.659494%) prefill and -12.894718 tok/s (-31.175990%) decode. Fixed/batched bookend means are 1290.072108 prefill and 41.588987 decode; candidate deltas are +12.454471 tok/s (+0.965409%) and -9.049823 tok/s (-21.760142%). The second control batches fresh mapping-validation queries from 39 to 18 per hit and changes policy to `fixed-v1`. These concurrent changes prevent causal attribution of the difference between cohorts; both lose decode performance.

Every response, including warmup, retained output SHA256 `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6` and 69/115 accepted drafts (60%); each measured window totals 207/345. Prompt cache/disk restore counts were zero. Warmup-inclusive `ready_hits`, `gather_skips`, `rms_skips`, `m1_skips`, and `seed_rewrites` each rose by 240 in capture and 292 in fixed; fixed misses and retirements were zero in the fixed control. Capture exported 52 original GPU rows/266784 bytes, SHA256 `2cd6cc0d3cbb589fb0bae09a71fa49900e7cad0191ad2ffa809e43c7f1eb8867`. The [fixed plan](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/ready-embedding-fixed-plan-83abe75704d746ed80ad6ca0974c25fd.json) freezes those token IDs and row bytes, changing only header generation; its artifact SHA256 is `3cf0bcb2f83db17c6cf7734568ebdd37d7a06f42dd8abcb472cb9f200e3afd48`. Both receipts record `passed:true`, no errors, restored original open, and no NPU execution. Passing parity/bookkeeping is not acceleration qualification.

Final claims require exact source/header/launcher/SO/engine/model identities, artifact hash/generation/origin/token set, matching output hashes and native acceptance, and completed hit/skip/seed counter deltas with misses/retirements accounted for. Matching stock/candidate/stock timing, preparation/upload costs, and restoration receipts must remain available. SRAM, utilization, driver success, or component tolerance cannot establish adoption or end-to-end speedup.

The [structured evidence](halogen-npu-ready-embedding-20261005.json) retains both
cohorts, source/artifact seals, and a bounded CPU parser replay. On the copied
stock process map (349 matching prefixes), identical heap/stack probes using
memory streams averaged 41.435 microseconds per scan with `sscanf` versus
10.800 with a canonical-prefix parser; CPU times were 41.436 and 10.801
microseconds. Six 50 ms blocks exclude filesystem reopen and live `/proc`
generation. The roughly 161 ms projected saving across all 292 hits includes
warmup and does not establish recovery of the engine regression. Candidate
mapping count and live map-generation costs remain unmeasured. No parser-only
engine cohort was admitted and no parser change was deployed. Kernel-checked
`process_vm_readv` snapshots are not a drop-in replacement: they do not
preserve the existing exact-permission/single-VMA guard and require handling
short and non-atomic copies. No unproved host mapping lifetime was assumed.

Only if a corrected fixed consumer later demonstrates benefit, the minimum NPU recipe preserves the legacy selection and prepares its eight captured intersections: `14367,279,321,13,314,6092,2235,13759`. One bounded native FC-seam capture window can collect those eight normalized rows plus bound projection hashes, if all eight are observed. Exact portable RMS evidence currently covers only `14367` among them; seven native norm references are missing, while original gamma/FC weight identities already agree. The [producer](../../scripts/benchmarks/halogen_npu_ready_embedding_producer.py) requires exact native norm provenance before fresh same-row CPU projection checks at `.002/.0002`, then offline NPU checks at `.03/.003`; CPU projection agreement alone cannot bypass normalization. Seal origin-2 BF16 rows, import immutably before timing, and compare identical eight-token GPU/NPU fixed controls including all preparation costs. No NPU production is warranted by the present losing consumer results.
