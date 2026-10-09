# Halogen 0.17.2 native-worker page order — 2026-10-08

The new native-worker detour executed on all 13 candidate requests and copied 1,703,936 rows. All matching requests, prompts and greedy outputs agree. No repeatable Prefill/Decode improvement is qualified, so the candidate remains default-off. The clean 0.17.2 Thinking server was restored, authenticated health and actual controller/backend/visible-console identities were verified, and it remains open on port 8840.

Frozen workload: 8192 actual input tokens of synthetic pseudoprose, including 116 repeated ` a` prefix units for token calibration; TG1 serial and TG128 serial/MTP; Cache Off, Thinking Off, temperature 0, seed 1. One excluded rep0 warmup and three measured repetitions per cell in stock-before/candidate/stock-after. Capacity 262144, one slot/concurrency 1, checkpoint v2, draft_tokens profile 2/PLD 3,3, prefill_chunk 8192 and max_prefill_tokens 8192. No model precision, GPU kernel, native token-ID computation, thread count or startup-floor changes. No NPU work ran in this series.

The retained before/candidate/after prompt copies normalize to the same 42,238 LF bytes as `fixed-depth2-comparison/prompts/prompt-8192-prose.txt`, SHA256 `0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`. Those bytes begin with 116 repeated ` a` units followed by `Weeks valley cheese clouds`.

## Results

Rates below use the unchanged harness whole-request clock normalization. Spread is sample standard deviation. Phase-specific corrected speed is not established; raw API rates and QPC request wall times are retained below and in JSON.

| Window | Workload | Prefill tok/s mean ± SD | Decode tok/s mean ± SD | Request wall s mean ± SD | Combined MTP+PLD acceptance |
|---|---|---:|---:|---:|---:|
| before | p8192-serial-tg1 | 1258.18 ± 40.69 | — | 6.5456 ± 0.2096 | — |
| before | p8192-mtp-tg128 | 1199.81 ± 41.38 | 42.66 ± 3.46 | 9.8771 ± 0.1025 | 210/339 = 61.95% |
| before | p8192-serial-tg128 | 1217.61 ± 60.63 | 32.02 ± 0.47 | 10.7676 ± 0.3981 | — |
| candidate | p8192-serial-tg1 | 1251.67 ± 26.06 | — | 6.5846 ± 0.1383 | — |
| candidate | p8192-mtp-tg128 | 1229.89 ± 20.89 | 42.81 ± 2.42 | 9.6936 ± 0.0654 | 210/339 = 61.95% |
| candidate | p8192-serial-tg128 | 1233.26 ± 2.62 | 32.22 ± 0.24 | 10.6716 ± 0.0520 | — |
| after | p8192-serial-tg1 | 1277.32 ± 8.36 | — | 6.4469 ± 0.0418 | — |
| after | p8192-mtp-tg128 | 1226.62 ± 9.65 | 42.61 ± 0.71 | 9.7116 ± 0.0679 | 210/339 = 61.95% |
| after | p8192-serial-tg128 | 1279.65 ± 7.03 | 32.18 ± 0.34 | 10.4095 ± 0.0784 | — |

Acceptance uses sum native API draft_n_accepted / sum draft_n and combines MTP with PLD. It is 210/339 = 61.9469% in every measured MTP window; isolated head-only acceptance is unavailable.

## Decision

| Candidate vs arithmetic stock bookend mean | Prefill | Decode | Request wall |
|---|---:|---:|---:|
| p8192-serial-tg1 | -1.27% | — | +1.36% |
| p8192-mtp-tg128 | +1.37% | +0.42% | -1.03% |
| p8192-serial-tg128 | -1.23% | +0.37% | +0.78% |

MTP request wall time is 9.6936 s for the candidate versus 9.7116 s after restoration: only 18 ms/0.186%, with sample SD 65–68 ms. Candidate raw MTP Prefill/Decode are slightly lower than the stable-after window; whole-request normalization changes those signs. Serial TG1 Prefill is lower than both stock windows. Thus midpoint deltas are descriptive, not a causal or repeatable gain. No unchanged retry is warranted.

## Raw API sensitivity

Whole-request MONOTONIC/raw factors vary by up to 8.33% before and 2.08% in the candidate. The helper raw/QPC checks passed, but one whole-request factor cannot locate a clock change to Prefill or Decode. Filesystem cache is not cleared: Cache Off refers to prompt cache. The first excluded calibration copy window took about 5.486 s; later selected-copy intervals were about 26–57 ms. No matching stock copy-interval trace exists, so these component times establish no copy speedup.

| Window | Workload | Raw API Prefill tok/s | Raw API Decode tok/s | Whole-request factor min–max |
|---|---|---:|---:|---:|
| before | p8192-serial-tg1 | 1258.18 ± 40.69 | — | 0.999999850–1.000000256 |
| before | p8192-mtp-tg128 | 1160.71 ± 62.81 | 41.25 ± 3.45 | 1.000000219–1.058335642 |
| before | p8192-serial-tg128 | 1156.45 ± 103.79 | 30.39 ± 1.84 | 1.000000217–1.083333595 |
| candidate | p8192-serial-tg1 | 1251.67 ± 26.06 | — | 1.000000057–1.000000191 |
| candidate | p8192-mtp-tg128 | 1221.39 ± 6.51 | 42.54 ± 2.89 | 1.000000240–1.020757146 |
| candidate | p8192-serial-tg128 | 1233.26 ± 2.62 | 32.22 ± 0.24 | 1.000000341–1.000000376 |
| after | p8192-serial-tg1 | 1277.32 ± 8.36 | — | 0.999999693–0.999999863 |
| after | p8192-mtp-tg128 | 1226.62 ± 9.65 | 42.61 ± 0.71 | 0.999999848–1.000000000 |
| after | p8192-serial-tg128 | 1279.65 ± 7.03 | 32.18 ± 0.34 | 0.999999907–0.999999931 |

## Implemented path and evidence

Four exact-byte/hash-pinned seams cover the actual first and speculative native launcher, token raw-copy point, worker completion and post-join consumer. The native scalar IDs remain unchanged. Original workers gather in source-page order into the original output order before original GPU unpack/RMS/FC. Mapping binding supports adjacent protection-split VMAs of the same HGN file, with declared file bounds and device/inode/offset continuity. Default short Decode windows fall back before mapping scans.

The shared object compiled with baseline x86-64 ISA/AVX disabled. Focused CPU checks cover byte-exact 8192-token output/64 workers, split and non-page-aligned HGN mappings, unreadable-gap rejection, cancellation/throw exit 79, and 14 assembly register/flags/floating-state/replay cases. Real serving proves execution and greedy parity on this one workload; native failure paths and broad model quality were not exercised by the serving cohort. The stop observer encountered WinError31 querying an exiting backend; the stop itself completed normally, both exact handles were subsequently closed, and cleanup/recovery were verified before stock restoration.

No experimental preload/enable remains in the restored engine. The full acceleration goal remains unachieved. The historical 48.42 tok/s measurement belongs to its earlier workload/configuration and is not substituted into this 0.17.2 comparison.

All 36 raw warmup/measured rows, clock samples, variances, hashes, exact build inputs and 13 completion markers are preserved in [halogen0172-native-worker-page-order-20261008.json](halogen0172-native-worker-page-order-20261008.json). Source package: [native-worker implementation](../../scripts/benchmarks/experimental/halogen0172_native_worker_page_order/README.md).
