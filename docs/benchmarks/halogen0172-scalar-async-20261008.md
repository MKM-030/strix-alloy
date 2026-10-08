# Halogen 0.17.2: exact asynchronous scalar experiment

No repeatable Prefill or Decode improvement was established. The candidate remains off. The normal 0.17.2 server is restored, ready and open in the visible request-log console.

Stock → candidate → stock; each window has one excluded warmup plus three measurements. Every request has exactly8,192 synthetic pseudoprose input tokens, including116 repeated ` a` prefix units for token calibration, and128 normally generated non-copying story tokens. The earlier natural-input description was incorrect. Temperature0, seed1, Thinking Off and Cache Off. Context capacity is262,144; MTP depth is2 and PLD is3,3. Original requests, timings, outputs and acceptance are unchanged.

| Window | Prefill tok/s, normalized | Decode tok/s, normalized | Raw API prefill | Raw API decode | Request wall s | Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 1215.98 | 43.81 | 1215.98 | 43.81 | 9.6908 | 210/339 = 61.95% |
| candidate | 1235.17 | 43.23 | 1139.24 | 39.87 | 9.6281 | 210/339 = 61.95% |
| after | 1232.65 | 42.53 | 1232.65 | 42.53 | 9.6870 | 210/339 = 61.95% |

Acceptance is the API’s combined MTP/PLD draft counter, not separately measured native MTP acceptance. Warmup rates are excluded.

Guest CLOCK_MONOTONIC rates are normalized using the contemporaneous guest RAW / Windows QPC comparison. The correction is measured over the whole request, not separately for Prefill and Decode. The candidate’s factors differ materially from both stock windows; its normalized phase rates are estimates under a uniform-clock-rate assumption and are not qualified as new post values. Stock-after rates are a separately measured reference: its factors are 0.999993805, 1.000000221 and 1.000000413, and raw and normalized means round to the same values. Raw rates and end-to-end wall times are preserved above, with individual factors and sample spread in the evidence. No causal phase speedup is established.

The hook replaces only the guarded four-byte H2D call at return RVA 0x17b91be with a bit-identical D32 value fill on the explicit legacy queue. The complete engine, HIP runtime, both original preloads and candidate library hashes are checked before activation. Source and consumer ordering were independently reviewed. All other copies, GPU math, profile and existing fences are retained.

The idle live export contains 52 valid successful append records and zero immediate fill errors. Counters are contiguous and there is no partial tail. This is an aggregate count across the cohort; per-request BOOTTIME attribution was not recorded. No receipt footer or GPU completion proof is inferred. Four exact greedy output hashes and four acceptance counters match stock.

The observed fill enqueue intervals total 0.087949 ms across the four requests. The earlier synchronous 6.204-second host interval included upstream GPU waiting; it was never a proven removable transfer cost. A smaller enqueue interval does not establish a faster engine.

The previous 48.42 decode tok/s result belongs to Halogen 0.16.2. It is not relabeled as a current 0.17.2 result. No startup threshold was changed or studied in this experiment. No NPU work was active.

Sources and retained receipts are pinned in the accompanying JSON. The candidate is not promoted and this unchanged experiment will not be repeated. The broader acceleration goal remains unachieved.
