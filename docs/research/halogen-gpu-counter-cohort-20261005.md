The retained Windows GPU Engine counters show little GPU activity from named desktop clients during the measured Stock A, native-lookup and restored Stock B requests. They provide no evidence of a large competing named Windows client in this cohort. The dominant compute accounting belongs to a host PID reported as `vmwp`; its process creation/executable identity could not be acquired. This does not prove total GPU utilization, exclusive attribution to Halogen, or a clock, power or thermal cause for performance differences.

This is an offline analysis of existing artifacts. No counter provider, hardware, process inventory, engine or network call was made. The reproducible analyzer is [halogen_gpu_counter_cohort_analysis.py](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_gpu_counter_cohort_analysis.py), with per-instance statistics and source hashes in [the compact JSON companion](C:/Projects/strix-alloy-clean/docs/research/halogen-gpu-counter-cohort-20261005.json).

| Window | Collector samples / counter rows | Strict interior samples in measured requests 1, 2, 3 | Prefill tok/s | Decode tok/s |
|---|---:|---:|---:|---:|
| Stock A | 46 / 16,882 | 6, 6, 7 | 1,321.262 | 41.622 |
| Native lookup | 50 / 18,350 | 6, 6, 7 | 1,316.040 | 41.899 |
| Restored Stock B | 54 / 19,818 | 8, 7, 7 | 1,277.139 | 41.280 |

Each window contains one warmup and three measured requests, with 8,192 input tokens, 128 output tokens, matching request/generated-output hashes and measured accepted/drafted totals of 207/345. Rates are the retained QPC-calibrated measurements. Stock B is a subsequent restoration continuation after the original coordinator failed; it is not a successful completion of that original qualification. The native cache-advice receipt records `helper_started=false`, `advice_issued=false` and a missing relative `wsl.exe` executable. These counters do not qualify cache advice or adoption of native lookup.

Every acquisition returned 367 full counter paths and 20 reported PIDs. All 55,050 rows had status 0 and finite, nonnegative cooked values; there were zero recorded query errors. All three raw hashes match their coverage receipts, request QPC boundaries match the measurement artifacts, sample indices are consecutive, and each collector ended with one clean `stopfile` terminal and recorded job closure. There were three adapter LUIDs; all nonzero counters were on `0x00000000_0x00011884`, physical index 0. This analysis does not establish which physical devices the LUIDs identify.

The following numbers are arithmetic means and maxima of **individual counter-path cooked values**, over acquisition brackets wholly inside the three measured request brackets. They are not summed across engines, duplicate instances, adapters or processes. There are 19 observations per path for A/native and 22 for B.

| Reported process and counter | Stock A mean / max | Native mean / max | Stock B mean / max |
|---|---:|---:|---:|
| `vmwp`, compute 0, engine 2, duplicate suffix `#1` | 92.529 / 120.635 | 92.371 / 118.048 | 96.189 / 135.248 |
| `vmwp`, copy, engine 1, `#1` | 0.00101 / 0.01926 | 0.00229 / 0.02171 | 0.00395 / 0.04588 |
| `System` PID 4, copy, engine 1 | 0.11973 / 0.51121 | 0.09343 / 0.19834 | 0.19031 / 1.19456 |
| `ChatGPT` PID 15864, 3D, engine 0 | 0.02297 / 0.05658 | 0.02960 / 0.09165 | 0.04773 / 0.24638 |
| `ChatGPT` PID 15864, copy, engine 1 | 0.00841 / 0.07062 | 0.00235 / 0.04461 | 0.00361 / 0.05212 |
| `dwm` PID 2796, 3D, engine 0 | 0.00555 / 0.04115 | 0.00367 / 0.00917 | 0.00656 / 0.06332 |
| `csrss` PID 2192, 3D, engine 0 | 0.00311 / 0.01987 | 0.00427 / 0.02372 | 0.00235 / 0.00908 |
| `explorer` PID 8596, 3D, engine 0 | 0.00024 / 0.00460 | 0 / 0 | 0 / 0 |

`vmwp` was PID 27016 in A/native and PID 20108 in B. Its measured compute path exceeded 100 in 5/19, 2/19 and 6/22 observations respectively. Across complete collector spans there were 7, 4 and 10 above-100 rows, all on that compute path. Values are preserved without clipping. The scaling/accounting behind these values is unqualified, so 92.5 cannot be read as a proven 92.5% of physical GPU busy time. The process name suggests VM-host accounting, but no retained creation identity or guest-client decomposition establishes that all of it belongs to the measured engine. `System` copy activity also cannot be classified as an unrelated competing client from its name alone.

Across the full collector spans, `ChatGPT` PID 15864 peaked at 0.0990, 0.1907 and 0.4009 on an individual engine path. The other `ChatGPT` PID 11316, `RadeonSoftware`, `AMDRSSrcExt`, `AMDRSServ`, `msedgewebview2`, `codex-computer-use-swift` and the remaining observed shell/UI clients had zero cooked values on every retained path. This weakens the hypothesis that a large named desktop-client GPU workload explains this cohort's current approximately 41–42 decode tok/s. It cannot rule out work between queries, unreported clients, guest workloads hidden inside VM accounting, or contention in the historical 48.424 tok/s run, for which these counters were not collected.

Timing and attribution limits are material:

- Request alignment uses Windows QPC seconds from the existing clock calibrations and each counter query's QPC start/end. The means use only complete acquisition brackets inside one measured request; boundary-overlapping queries and warmup are excluded. These are sampled descriptive means, not an integral of busy time or a separate prefill/decode measurement.
- Median acquisition duration was 1.186, 1.174 and 1.156 seconds; median start-to-start cadence was 1.225, 1.195 and 1.193 seconds. The largest gap between query brackets was 0.160, 0.160 and 0.156 seconds. A nominal 1,000-ms setting therefore does not mean exactly one sample per second or continuous coverage.
- The first flushed sample ended 6.150, 5.657 and 5.245 seconds before warmup calibration. The first query starting after the final response calibration began 1.047, 0.011 and 1.101 seconds later. Request-calibration handshake uncertainty was below one millisecond; counter acquisition duration dominates the time resolution.
- Retained `timestamp_utc` values fell 3.6–15.4 ms before their query-end UTC brackets. Interpreting `Timestamp100NSec` as UTC FILETIME instead yields an approximately +7,200-second offset from those strings in every sample. That is consistent with a local-time encoding on this host, but its semantics have not been established. Native numbers are preserved and are not used as UTC or directly substituted for QPC.
- `InstanceName` omits PDH duplicate suffixes: each sample has eight duplicate base names for `vmwp` engines 0–7, while the full counter paths retain `#1`. The analyzer keys by the full path. Averaging rows by PID/InstanceName alone would merge distinct observations and dilute the active compute path with its zero companion.
- PID identity is acquired once per first-seen PID and is not revalidated for reuse. Creation identity was unavailable for `vmwp`, `System`, `dwm` and `csrss`; those names are weaker attribution evidence. Provider status 0 does not establish physically meaningful scaling, as the above-100 values demonstrate.
- Collector overhead was present in all three windows, but there is no otherwise identical collector-off control. These artifacts contain no direct power, thermal, queue-priority or effective operating-state measurement.

Inputs remain the original [Stock A](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/native-lookup-stock8k-prepared-20261005/run/stock_before/gpu-counters.jsonl), [native lookup](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/native-lookup-stock8k-prepared-20261005/run/native_lookup/gpu-counters.jsonl), and [restored Stock B](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/native-lookup-stock8k-resume-20261005/run/stock_after/gpu-counters.jsonl), together with each sibling `gpu-counter-coverage.json` and `measurement.json`. Raw SHA256 values, in that order, are `0fa295e65c7b1922c365db682551500d55ff4e93bb9b6a7495b8b7a6ed74b5cf`, `c97f32d076c4286084d90f4383bd6cbee68069378a9ac5753500aa6a0f2fbf7b`, and `d050de4c2cbbc3951f647e7b16cf682878e51470c7a35facfc888128b02470d6`.
