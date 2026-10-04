# Unchanged stock control with ADLX observation — 4 October 2026

At approximately six hours, no new end-to-end speed or acceptance improvement is qualified. Full live NPU MTP remains incomplete. The unchanged stock control completed at 05:32:34 UTC with higher PP than the intervening control; this rebound is not an optimization or an isolated causal diagnosis.

Profile: Halogen 0.16.2, v2 checkpoint, 262144 capacity, one slot, cache Off, greedy temperature 0, seed 1, thinking disabled, stock MTP depth2. Each cohort excludes one warmup and contains three measured requests.

| Measured cohort | Prefill tok/s, mean ± sample SD | Decode tok/s, mean ± sample SD | Acceptance |
|---|---:|---:|---:|
| PP8192/TG1 serial | 1768.4717 ± 4.0632 | — | — |
| PP8192/TG128 mtp | 1678.9173 ± 7.1358 | 46.3550 ± 0.4039 | 207/345 (60%) |
| PP8192/TG128 serial | 1762.9222 ± 8.2040 | 35.6829 ± 0.3762 | — |

Earlier stock PP-only/MTP decode was 1731.31/46.591 tok/s; intervening stock was 1605.07/46.874; this control was 1768.47/46.355. All acceptance values remain 60%. The intervening PP mono/raw ratio was 1.0833332, versus 1.0000147 here. Corrected rates already incorporate those ratios. Host client wall changed 5.12831 → 4.65772 seconds (9.18% lower), independently confirming a real request-wall rebound. The descriptive PP increases of 10.18% over intervening stock and 2.15% over the initial window do not establish an optimization, restart effect or thermal cause.

GPU values below are min / arithmetic sample mean / max, across the complete measured request windows. Warmups are excluded.

| Cohort | GPU samples | GPU °C | GPU MHz | Reported GPU W | Usage % |
|---|---:|---:|---:|---:|---:|
| PP8192/TG1 | 14 | 74 / 76.43 / 80 | 2083 / 2664.14 / 2770 | 109 / 139.79 / 151 | 68 / 94.93 / 100 |
| TG128 mtp | 24 | 60 / 79.54 / 88 | 2125 / 2677.17 / 2894 | 85 / 135.58 / 155 | 63 / 93.17 / 99 |
| TG128 serial | 24 | 57 / 79.08 / 87 | 2091 / 2666.71 / 2883 | 94 / 132.29 / 154 | 62 / 91.96 / 99 |

VRAM clock was 1000 MHz in all 62 measured GPU samples. Alignment maps C++ Windows `requested_epoch_ms`/`completed_epoch_ms` to QPC by interpolation between adjacent host `epoch_ns`/`qpc` anchors, then selects intervals wholly contained in each request's before/after QPC window. Guest UTC and raw ADLX driver timestamps were not used. No extrapolation was used; one final idle sample lies outside the anchor span.
Host anchors: 1770; gap mean/max 204.63/220.04 ms; affine clock-consistency residual maximum 0.810 ms. Request handshake uncertainty maximum 0.851 ms; selected sample boundary distance minimum 46.37 ms. Sensor spacing mean/max 1007.90/1017.00 ms.

All 360 sensor requests succeeded. Recorded GetCurrentGPUMetrics/TimeStamp spans were 0–1 ms, mean 0.208 ms, total 75 ms; mean over measured samples 0.226 ms. These spans exclude later sensor getters, output and logger/memory-monitor costs; 0 ms means below millisecond reporting resolution. Host clock calls are consecutive and unbracketed, so the residual is observed consistency, not a certified absolute timing bound. One-hertz sampling and unknown sensor refresh latency limit phase detail; TG128 windows combine prefill and generation. GPUPower rail accounting is unverified, and board power/hotspot/fan metrics are unavailable. No prior workload GPU sensors exist, and ADLX overhead was not isolated.

All twelve saved prompt/request/output hash triples match the earlier stock directly, including warmups. `result.json` records passed=true, cleanup_proven=true and source_seal_unchanged=true. The full `terminal.json` records both controller and backend stopped, zero active requests, and backend ready/cleanup/recovery=true with no error. All 50 source-seal entries were independently hashed and still match. Logger exit0 and owned-job closure passed. The 18-GiB physical/commit floor held; retained warmup/measured request minima were 22.471 / 113.437 GiB, and logger-window minima were 22.539 / 113.439 GiB. These are their respective observation scopes.

Artifacts: `server/.local/optimization9h-20261004/adlx-control-stock8k-1` and
`server/.local/optimization9h-20261004/adlx-stock8k-fb606b9bfd344e398ea5f2fda2a45dd7`.
Per-request sensor membership and input hashes are preserved in the ignored
logger directory's `cohort-telemetry-analysis.json`. The
[status evidence JSON](../benchmarks/halogen9h-optimization-20261004.json) retains
all three phase rows, timing, memory scopes and artifact hashes.

| Evidence | SHA256 |
|---|---|
| Control samples | `02081125ed81fd45f8fcf7844b4e8dbc332128b852cd88fb57808636bfd2d9e8` |
| Control lifecycle result | `1593649916b91ac2373aeb55a2242e7cdc0184dcb562535c2c94af594ebae044` |
| Control terminal state | `158d210306b5555208f2a08ddc87721eaf3658fb69a7c917649c0812fc435492` |
| ADLX raw samples | `7d6027f61df7888197d7cf761ea11b3894d8fd795e74575f9111050a59be50a2` |
| Host epoch/QPC anchors | `89abbcc7d9f729fb43996858d42000ebf34f71fde3fffee918dd2db34430f62e` |
| Per-request telemetry analysis | `478d80b7d20db50eb6d8639d51ed376b5eb9ad210a19feb8661aeca56fa1fad9` |

Publication used saved artifacts and source hashing only; no new hardware/provider call, benchmark, test run or runtime setting change.
