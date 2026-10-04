# Frozen conditioned control — 5 October 2026

Serial PP8192/TG1 conditioning before each MTP request did not restore the historical decode rate. On the same retained colleague engine, measured MTP averaged 1259.987028 prefill / 41.625016 decode tok/s with 207/345 accepted draft tokens (60%). Versus the preceding sequential MTP control, prefill rose 2.51%, decode fell 0.76%, and mean MTP request wall fell 1.51%. These are diagnostic observations, with time drift still a confound; they supply no engine optimization claim.

| Cohort | Prefill tok/s | Decode tok/s | Mean MTP request wall, s |
|---|---:|---:|---:|
| Historical paired 8K Stock A | 1866.537225 | 48.423621 | 7.054107 |
| Latest sequential MTP control | 1229.125265 | 41.945034 | 9.751004 |
| Conditioned MTP control | 1259.987028 | 41.625016 | 9.603823 |

The controlled schedule contained four serial calls, each completing before the following MTP clock-calibration and timer window: one MTP warmup plus three measured MTP128 calls. Conditioning added 24.451235 seconds of request wall outside the MTP timers; the sum of all eight request walls was 62.791227 seconds. The workload used capacity 262144, actual input 8192, frozen prompt/profile, run `c4b3c8be6b584d4c901b43e54cc6e8d8`, and server PID 28488. There was no engine restart or setting change.

All four serial receipts have input/output counts 8192/1, zero cache/disk restore/draft/accepted draft counts, request SHA `c908c88d62356450236f5dacb1bad2cb51a8ce19dced1bae739e97bda854d91f`, and output SHA `b344d80e24a3679999fa964450b34bc24d1578a35509f934c1418b0a20d21a67`. All four MTP receipts have counts 8192/128, zero cache/disk restore, 69 accepted / 115 drafted tokens each, request SHA `fcd4fb7a1ea80aecbbe8b42289019a9b08b5f54458c02ec3e1060c95372b16d0`, and output SHA `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`. The three measured MTP receipts therefore retain 207/345 acceptance.

ADLX recorded 90 successful GPU0 samples. All eight request windows are fully inside the 440 host epoch/QPC anchors; query intervals were mapped by interpolation without extrapolation and selected only when wholly inside their request window. Guest UTC and ADLX driver timestamps were excluded. One final sensor sample lies outside the anchors, after all requests, and was excluded. Observed affine consistency residual was 0.020600 ms; this is not a certified timestamp-error bound.

| Pair | Target MTP phase | Serial sensor queries | MTP sensor queries |
|---|---|---:|---:|
| 0 | Warmup | 6 | 9 |
| 1 | Measured | 6 | 10 |
| 2 | Measured | 6 | 9 |
| 3 | Measured | 7 | 9 |

| Sensor cohort | GPU MHz min/mean/max | Reported GPU W min/mean/max | °C min/mean/max | GPU usage % min/mean/max |
|---|---:|---:|---:|---:|
| Conditioned MTP warmup, 9 samples | 1553 / 1653.67 / 1925 | 54 / 54.67 / 56 | 51 / 53.67 / 55 | 94 / 97.22 / 100 |
| Conditioned measured MTP, 28 samples | 1240 / 1634.46 / 2068 | 46 / 54.36 / 57 | 48 / 55.79 / 58 | 59 / 94.04 / 100 |
| Historical separate same-shape measured MTP, 24 samples | 2125 / 2677.17 / 2894 | 85 / 135.58 / 155 | 60 / 79.54 / 88 | 63 / 93.17 / 99 |

VRAM clock was 1000 MHz and NPU frequency/activity were zero in every current retained request query. The lower GPU operating range now has observations across every measured MTP window. One-hertz spacing and unknown driver refresh latency do not isolate prefill/decode phases or establish a power-limit or thermal cause. The historical sensor cohort is a separate control; the exact 1866.537/48.423621 reference has no matched GPU telemetry.

The client and telemetry owned jobs exited 0 and closed, with no pending cleanup; the guardian monitor stopped. Guardian minima were 27.669 GiB physical reserve and 119.952 GiB commit headroom. Raw responses remain in ignored local evidence. [Sanitized source hashes, exact interval membership, metrics and limitations](halogen-conditioned-control-20261005.json) contain no prompt text, generated output text or credentials. The [original performance-gap audit](halogen-performance-gap-audit-20261005.md) is unchanged. This report analyzes retained files only; its author made no hardware/provider call, process mutation, test, server change or Git action.
