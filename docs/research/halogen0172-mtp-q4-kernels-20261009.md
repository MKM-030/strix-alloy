# Halogen 0.17.2: exact MTP Q4 kernel component comparisons

9 October 2026. All three measured candidates reproduced every tested native output bit. The two query-LDS candidates were slower and are rejected for adoption. Global-query batched LUT reads reduced mean component time by 1.2190%, with a smaller advantage in AB than BA order. Keep adoption disabled: this modest, order-sensitive component result does not establish an engine gain. The regular 0.17.2 server stayed ready/open with its stock configuration; these runs made no engine request or lifecycle change.

The first candidate cooperatively stages the raw 5120-byte BF16 query in quarter-major LDS beside the native 1024-byte packed BF16 code-pair table. The second retains that layout and batches the sixteen code-pair LUT reads ahead of the unchanged dependent dot2 chain. The third keeps the batched LUT reads and returns the query packs to global memory, removing query LDS staging while retaining the 1024-byte native table. Packed Q4 codes, native codebook RNE, BF16 dot2 order, FP32 scale FMA and XOR 8/4/2/1 reduction remain exact. Reviewed descriptors agree on float mode 240, IEEE mode and clamp mode. Static LDS is 6144 bytes for the first two candidates and 1024 bytes for the third, matching stock.

Times below cover the complete core-plus-tail projection path. Each variant has 45 measured pairs after 15 excluded warmup pairs, one warmup and three measurements per head. Values are mean ± sample standard deviation in milliseconds. Percentage change is the ratio of the two means; positive means slower.

| Candidate | Native GPU ms | Candidate GPU ms | Time change | Decision |
| --- | ---: | ---: | ---: | --- |
| Cooperative query LDS | 0.920156 ± 0.040910 | 0.964391 ± 0.050473 | +4.8074% | Reject |
| Query LDS + batched LUT reads | 0.889116 ± 0.055371 | 0.900671 ± 0.039790 | +1.2996% | Reject |
| Global query + batched LUT reads | 0.926001 ± 0.048336 | 0.914713 ± 0.050066 | -1.2190% | Disabled; component advantage only |

| Candidate | Order | Pairs | Native GPU ms | Candidate GPU ms | Time change |
| --- | --- | ---: | ---: | ---: | ---: |
| Query LDS | AB | 22 | 0.915176 ± 0.040060 | 0.985916 ± 0.053461 | +7.7296% |
| Query LDS | BA | 23 | 0.924919 ± 0.042035 | 0.943802 ± 0.038216 | +2.0416% |
| Query LDS + batched LUT | AB | 22 | 0.893992 ± 0.078348 | 0.904307 ± 0.011987 | +1.1538% |
| Query LDS + batched LUT | BA | 23 | 0.884453 ± 0.015034 | 0.897193 ± 0.054804 | +1.4404% |
| Global query + batched LUT | AB | 22 | 0.925079 ± 0.056499 | 0.923194 ± 0.049237 | -0.2038% |
| Global query + batched LUT | BA | 23 | 0.926882 ± 0.040299 | 0.906601 ± 0.050581 | -2.1881% |

AB means native then candidate; BA reverses the arms. Both query-LDS candidates have higher mean time in both orders. The third has a mean time change of −0.2038% in AB and −2.1881% in BA, showing order sensitivity. Mean paired percentage changes are 4.9953%, 1.6167% and -1.0401%; those differ from the headline ratios of means. Mean monotonic host spans for both arms together are 2.208872 ms, 2.061875 ms and 2.160667 ms. The companion JSON retains full means, sample deviations, ranges, paired differences, order strata and independently recomputed dispersion of the fifteen per-head means.

All 60 pairs per variant passed strict bitwise native-module versus captured-logit and candidate versus native comparisons across all 34,571 rows, including 32,033 core rows and 2,538 tail rows. This covers the same 518,565 unique head/row outputs and 2,074,260 repeated row comparisons per comparison type per variant. There were zero bit mismatches, maximum absolute error zero, and no corrupted guard bytes. Each variant completed 240 projection launches and released all four device allocations, three events and two modules; external helper cleanup also completed.

The captured scope is partial: fifteen of sixteen exported heads match this asset, from an earlier capture with 112 observed scatters. Its original `validated-asset-binding-changed` failure and unmatched head remain preserved. No new capture expanded coverage. See the [capture scope report](halogen0172-mtp-shortlist-cpu-20261009.md).

HIP events bracket each arm's two launches, including all staging and barriers inside the kernels. File reads, input and output-poison copies, and output/guard readback occur outside timing. The host span covers enqueue and completion for the whole pair. Three measurements per head are repeated observations, not forty-five independent capture samples; sample deviations are descriptive, not a serving-speed confidence claim.

The packed input reproduces the tested bytes and offsets but relocates them into a fresh allocation. It does not reproduce the engine arena or its cache state. The separate cohorts have native means of 0.920156 ms, 0.889116 ms and 0.926001 ms, so candidate-to-candidate differences do not isolate LUT scheduling or removal of query LDS staging. No token/s, live MTP acceptance delta, NPU result, or end-to-end serving gain was measured. The third result is a component diagnostic and remains disabled.

The third variant saves a nominal 11.2878 microseconds per tested complete projection. Even granting that saving to every one of the 112 observed heads in a retained 128-output-token request would save only 1.2642 milliseconds per request. This optimistic extrapolation assumes untested assets benefit equally and adds no integration cost; it is not a serving measurement. It does not justify a serving hook or another engine cohort on the present evidence. Source assessment of direct core/tail dispatch fusion leaves essentially all active arithmetic and weight traffic intact. Fusing full-logit publication with selection lacks the exact native filtering, tie, sampling and lifetime contract. Neither assessment produced a justified next hardware candidate.

An initial preparation attempt failed while resolving a Windows executable path, before a GPU component ran. Its failed receipt is retained, and all three completed runs have separate receipts. The third variant completed an exact component comparison; no serving adoption follows from it.

Full code and evidence hashes are in the [whitelisted JSON report](halogen0172-mtp-q4-kernels-20261009.json). Kernel source pins are `ce9fce3932c7a9ce1dfa4d3840cc1eeafa4264b337bdf24184b420153dfd3506` for query LDS, `c8539ff1a7a5853edddacd58b5d202e22365c229ded32c6ad841c4e591e020aa` for query-LDS batched LUT reads, and `1092346e03de5f0681a2d2fedbf669b910b8d321a47b6341da3d83a399c53a50` for global-query batched LUT reads. Host source, module, disassembly, build, descriptor-review and component-receipt hashes are included without payloads or private process/server state. Private component receipts are retained at `mtp-q4-query-stage-component-v1/result.json`, `mtp-q4-query-lut-batch-component-v1/result.json` and `mtp-q4-global-lut-batch-component-v1/result.json` under the preparation directory; the failed receipt is `mtp-q4-query-stage-component-v1/preparation-v1-result.json`.
