# Halogen 0.17.2: stock adaptive depth 2/3, matched 8K comparison

Actual input: **8,192 non-repeated LF prose tokens**; context capacity: **262,144**. All windows use 0.17.2 v2, one slot, chunk/arena8192/8192, PLD3,3, Cache Off, Thinking Off, temperature0/seed1. The middle window only omits the fixed-depth control. Each cohort has three measured repetitions and one excluded warmup.

| Window | Serial TG1 prefill tok/s | MTP TG128 prefill tok/s | MTP TG128 decode tok/s | API MTP+PLD acceptance |
| --- | ---: | ---: | ---: | ---: |
| before (fixed2) | 1278.09 | 1242.66 | 44.06 | 210/339 = 61.95% |
| adaptive (native stock adaptive2..3) | 1249.18 | 1241.33 | 42.66 | 210/339 = 61.95% |
| after (fixed2) | 1241.13 | 1175.16 | 43.76 | 210/339 = 61.95% |

TG1 prefill-only and the prompt phase of TG128 are separate measurements. Acceptance combines API head and prompt-lookup counters. All warmup/measured, serial/MTP and cross-policy greedy output hashes agree; actual token counts and request hashes match the frozen contract.

| Metric | Adaptive vs before | Adaptive vs after | Adaptive vs bookend mean | After/before drift |
| --- | ---: | ---: | ---: | ---: |
| Serial TG1 prefill | -2.26% | +0.65% | -0.83% | -2.89% |
| MTP TG128 prefill | -0.11% | +5.63% | +2.68% | -5.43% |
| Serial TG128 prefill | -1.39% | +1.93% | +0.24% | -3.25% |
| MTP TG128 decode | -3.18% | -2.52% | -2.85% | -0.68% |
| Serial TG128 decode | +0.78% | -1.09% | -0.16% | +1.89% |

Combined acceptance changes by +0.00 percentage points against the bookend mean. Its denominator can change with depth; it is not an isolated draft-head accuracy estimate. These three-repetition differences do not establish statistical significance. Raw API rates, calibrated means/stdev, counts and excluded warmups are in the companion JSON.

| Window | Measured host RAM minimum GiB | Measured commit headroom minimum GiB | All snapshots RAM/commit minimum GiB |
| --- | ---: | ---: | ---: |
| before | 24.51 | 114.07 | 24.51/114.07 |
| adaptive | 24.38 | 113.98 | 24.38/113.98 |
| after | 24.16 | 113.73 | 24.14/113.64 |

Startup admission remains35/131 GiB; runtime reserve18/18 GiB. These sampled host values are not VRAM peaks and do not prove startup sufficiency exactly at35 GiB.

Saved manifests show fixed `HALOGEN_MTP_DEPTH=2` in both bookends and omission in the adaptive window, with no custom `HALOGEN_MTP_DEPTH_HI`. Saved startup lines confirm `MTP depth-2 selectable` versus `MTP depth-2 (up to 3) selectable`. Engine/API versions and source pins match. The client does not expose chosen per-round depths or policy thresholds.

No NPU serving gain was measured. The overall GPU/NPU acceleration goal remains unachieved.

Root's native Windows host timing reconstruction places a tiny CPU regression in calibration and tens of milliseconds at the beginning of the excluded first serial TG1 warmup. It was terminal over six seconds before the earliest measured request. No measured-request overlap is established; residual contention and causal impact are not ruled out or estimated. This bounded diagnostic overlap does not by itself invalidate all completed MTP rows. The exact CPU diagnostic start was not retained.

The fixed2 stop observer failed with WinError31 after its engine exited0. Root's separate terminal revalidation confirmed stopped state, normal cleanup/recovery and missing fresh process identities. The failed observer is retained separately from that successful revalidation; the next adaptive engine had confirmed live handles.

The user chose to develop and keep the latest0.17.2 server open. Root verified its fixed2 deployment ready, idle and visibly open at 2026-10-08T04:25:08.182652+00:00; the companion JSON separately binds its profile, launch, process identities and saved startup files. The older0.16.2 restoration was intentionally superseded by that instruction and is not pending.

Evidence: private adaptive-depth23-comparison contract and complete before/adaptive/after raw windows. Prompt SHA256: 0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1. The earlier fixed-depth version report is preserved.
