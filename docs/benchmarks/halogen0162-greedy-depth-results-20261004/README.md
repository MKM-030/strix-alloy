# Greedy MTP depth results — 2026-10-04

32K occupied input at 64K Exact capacity; two three-turn greedy conversations; low-effort thinking. Retrieval graded; implementation and review ungraded.

Implementation and review outputs are **ungraded**. Retrieval is the graded fixture task.

Sequential stockA/depth3/stockB order; no OS cache flush. stockB is the later warmed-host control, while both initial conversation caches are cold. Two repetitions do not establish a causal or statistically confirmed gain.

All three cells passed cleanup/recovery, unchanged seals and identical request, reasoning, output and token-count checks. Each retained 14/14 retrieval, six EOS finishes and zero caps or clamps.

| Cell | Depth | Six-request actual wall s | Normalized three-turn s | Prefill tok/s | Decode tok/s | Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| stockA | 2 | 169.686 | 98.172 | 1096.44 | 42.358 | 73.914% |
| depth3 | 3 | 162.106 | 93.451 | 1095.91 | 45.839 | 68.322% |
| stockB | 2 | 159.768 | 92.908 | 1093.67 | 46.930 | 73.914% |

Depth3 does not beat warmed stockB on both measures; no speed win is supported.

Depth3 versus stockB: actual wall reduction -1.464%; normalized reduction -0.584%.

Actual wall is the sum of six measured request intervals. Normalized three-turn time is the mean of two sums of TTFT + 1000/calibrated decode tok/s; it is not actual elapsed wall.

Sanitized counts, hashes and evidence gates: [results.json](results.json).
