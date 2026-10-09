# Halogen 0.17.3: bounded native bulk BN64 engine comparison

The adapter remains off and the broader acceleration goal is unachieved. V1 observed no native64 transactions. V2 executed the bounded native64 path, but its qualified candidate/before comparison regressed; no serving gain is established.

The frozen workload is synthetic pseudoprose: 8192 actual input tokens, including 116 repeated input calibration units, and 128 ordinary output tokens. Context262144, one slot, prefill/max8192, cache/thinking off, temperature0/seed1, MTP2 and PLD3,3 remain fixed. Each arm contains one excluded warmup and three measurements. Acceptance combines native API MTP+PLD. This is not natural long-input evidence and no NPU execution is claimed.

| Revision / arm | Native Prefill tok/s, mean ± SD | Native Decode tok/s, mean ± SD | Accepted/drafted |
| --- | ---: | ---: | ---: |
| v1 / before | 1264.639667 ± 11.628456 | 42.784000 ± 1.734917 | 210/339 |
| v1 / candidate | 1207.796333 ± 4.616114 | 43.812667 ± 0.583142 | 210/339 |
| v1 / after | 1234.141000 ± 6.359810 | 44.443667 ± 0.946596 | 210/339 |
| v2 / before (reused v1-after) | 1234.141000 ± 6.359810 | 44.443667 ± 0.946596 | 210/339 |
| v2 / candidate | 1173.972667 ± 13.835347 | 44.246333 ± 0.666607 | 210/339 |
| v2 / after | 1142.177667 ± 20.890369 | 41.311333 ± 0.341154 | 210/339 |

Measured acceptance in every arm is 210/339 = **61.95%**, combining native MTP and PLD.

Rates are the original native API timings; no clock normalization or reconstruction is applied. SD is the sample standard deviation of the three measured requests. V2-before is exactly the four v1-after requests, with zero new baseline requests; the shared rows are not additional independent observations.

V1’s resident-size helper claimed the exclusive audit log before serving. Its completed zero-hit window therefore does not establish BN64 execution or a BN64 rate. V2 excludes only exact argv[1] `--resident-gib` before log creation; the native kernels, ABI and rollback path are unchanged.

The qualified v2 candidate/before comparison is Prefill **-4.875321%** and Decode **-0.444008%**. This is a bounded negative result on the frozen workload, not a confidence or general-quality claim.

Candidate/after and the pooled three-arm comparison are **unqualified** because their observed clock scaling differs. The final after arm’s raw native rates are retained above; an apparent decode increase against that incompatible arm is not a qualified gain. The limit is 0.1% for measured MONOTONIC/RAW spread and each RAW/QPC deviation. Warmup clocks are retained separately in the evidence.

| Clock scope | MONOTONIC/RAW minimum | maximum | relative spread | RAW/QPC within0.1% | Comparable |
| --- | ---: | ---: | ---: | --- | --- |
| v1 / three arms | 0.999999812 | 1.000099053 | 0.000099240 | True | True |
| v1 / before | 0.999999998 | 1.000099053 | 0.000099055 | True | True |
| v1 / after | 0.999999812 | 1.000000099 | 0.000000286 | True | True |
| v2 / three arms | 0.999999787 | 1.083332840 | 0.083333071 | True | False |
| v2 / before | 0.999999787 | 1.000000067 | 0.000000280 | True | True |
| v2 / after | 0.999999787 | 1.083332840 | 0.083333071 | True | False |

V2 recorded 192 complete bounded native64 transactions, with started/committed deltas 192/192, zero rollbacks and zero failures. Contiguous audit records and all output/acceptance hashes match. Rejected launches are stock forwards, not failures. The rejected count of 158167 is cumulative from initialization through the last logged commit, including startup; it is not a request-window-exclusive launch count. No universal or all-layer hit claim is made.

| Revision / arm / request | Phase | Native PP tok/s | Native TG tok/s | Wall seconds | Min physical / commit GiB | Accepted/drafted |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v1/before/0 | warmup | 674.944000 | 34.768000 | 15.848220 | 23.467712 / 110.364632 | 70/113 |
| v1/before/1 | measured | 1260.250000 | 40.781000 | 9.664158 | 23.547352 / 110.373867 | 70/113 |
| v1/before/2 | measured | 1255.845000 | 43.816000 | 9.473675 | 23.832737 / 111.095119 | 70/113 |
| v1/before/3 | measured | 1277.824000 | 43.755000 | 9.367691 | 23.832565 / 111.095547 | 70/113 |
| v1/candidate/0 | warmup | 643.277000 | 32.821000 | 16.665207 | 23.870998 / 111.247021 | 70/113 |
| v1/candidate/1 | measured | 1209.437000 | 43.167000 | 9.772440 | 23.809875 / 111.177395 | 70/113 |
| v1/candidate/2 | measured | 1202.584000 | 43.970000 | 9.783364 | 23.760109 / 111.131290 | 70/113 |
| v1/candidate/3 | measured | 1211.368000 | 44.301000 | 9.682012 | 23.795025 / 111.170986 | 70/113 |
| v1/after/0 | warmup | 689.591000 | 34.228000 | 15.647812 | 23.519474 / 110.802460 | 70/113 |
| v1/after/1 | measured | 1228.554000 | 43.378000 | 9.652254 | 23.492458 / 110.763485 | 70/113 |
| v1/after/2 | measured | 1241.062000 | 45.187000 | 9.464338 | 23.544979 / 110.833500 | 70/113 |
| v1/after/3 | measured | 1232.807000 | 44.766000 | 9.531177 | 23.538372 / 110.789448 | 70/113 |
| v2/before/0 | warmup | 689.591000 | 34.228000 | 15.647812 | 23.519474 / 110.802460 | 70/113 |
| v2/before/1 | measured | 1228.554000 | 43.378000 | 9.652254 | 23.492458 / 110.763485 | 70/113 |
| v2/before/2 | measured | 1241.062000 | 45.187000 | 9.464338 | 23.544979 / 110.833500 | 70/113 |
| v2/before/3 | measured | 1232.807000 | 44.766000 | 9.531177 | 23.538372 / 110.789448 | 70/113 |
| v2/candidate/0 | warmup | 665.086000 | 33.416000 | 16.180037 | 23.396416 / 110.669651 | 70/113 |
| v2/candidate/1 | measured | 1184.243000 | 45.007000 | 9.790350 | 23.413536 / 110.702675 | 70/113 |
| v2/candidate/2 | measured | 1179.435000 | 43.764000 | 9.902857 | 23.436218 / 110.700615 | 70/113 |
| v2/candidate/3 | measured | 1158.240000 | 43.968000 | 10.014510 | 23.353432 / 110.596718 | 70/113 |
| v2/after/0 | warmup | 648.753000 | 30.621000 | 15.591795 | 23.332325 / 110.574387 | 70/113 |
| v2/after/1 | measured | 1162.299000 | 41.127000 | 9.408485 | 23.343224 / 110.585300 | 70/113 |
| v2/after/2 | measured | 1120.595000 | 41.705000 | 9.610578 | 23.359497 / 110.611259 | 70/113 |
| v2/after/3 | measured | 1143.639000 | 41.102000 | 9.514942 | 23.347397 / 110.577835 | 70/113 |

All entry reserves passed22/22 GiB and all request minima passed18/18 GiB. Complete numeric clock calibrations, native timing/usage rows, parity hashes and private raw-evidence hashes are retained in the JSON.

Final normal stock is authenticated, idle and ready with visible trace: controller4868, backend40424, console25396; exact creation identities were freshly verified by root. Final health is completed4/cancelled0 and the candidate is removed.

Adapter source/build hashes are retained in the evidence. Component milliseconds justify the experiment only; they are not converted to engine token rates or used to infer a gain. No prompts, answers, credentials, native binaries or model data are published.

[Evidence](halogen0173-bulk-bn64-engine-20261009.json) · [Default-off source archive](../../scripts/benchmarks/experimental/halogen0173_bulk_bn64_engine/README.md)
