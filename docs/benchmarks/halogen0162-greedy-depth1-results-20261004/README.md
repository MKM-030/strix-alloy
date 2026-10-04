# Greedy MTP depth1 results — 2026-10-04

Depth1 does not beat both current stock controls on actual wall and normalized time; retain depth2.

Against warmed stockB, depth1 is 1.857% slower in actual wall, 2.757% slower in the normalized estimate and 5.608% lower in decode throughput. Acceptance rises by 6.001 percentage points; this supplies no accuracy or speed gain.

32K target input (actual cold requests 32791/32792 tokens) at 64K Exact capacity; two three-turn greedy retrieval/implementation/review conversations per cell. Thinking enabled, low effort. Stock lookup and compute; only draft depth changes. Coding and review answers are **ungraded**.

All 18 requests completed with identical request/output/reasoning/token hashes, 4509 generated tokens per cell, retrieval 14/14, six EOS responses and zero caps or clamps. Owned cleanup/recovery passed; source seals remained unchanged and the 18 GiB physical/commit reserve held.

| Cell | Depth | Six-request actual wall s | Normalized three-turn s | Prefill tok/s | Decode tok/s | Acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| stockA | 2 | 197.669 | 115.682 | 913.13 | 37.301 | 73.914% |
| depth1 | 1 | 168.681 | 98.650 | 1047.95 | 43.873 | 79.915% |
| stockB | 2 | 165.605 | 96.004 | 1008.12 | 46.479 | 73.914% |

Positive reductions mean depth1 is faster:

| Compared with | Actual wall reduction % | Normalized time reduction % | Corrected decode change % | Raw decode change % |
| --- | ---: | ---: | ---: | ---: |
| stockA | +14.665 | +14.723 | +17.619 | +17.191 |
| stockB | -1.857 | -2.757 | -5.608 | -5.739 |

Actual wall is the sum of six client request intervals. The normalized estimate averages two three-turn sums of TTFT + 1000/calibrated decode tok/s; it is not elapsed wall. Prefill averages the two cold first turns; decode weights all generated tokens, including reasoning.

Rates use whole-request guest monotonic/raw clock correction. The JSON retains raw rates, clock ratios, handshake uncertainty and independent client wall; that correction does not establish identical clock behavior in every phase. Fixed run order, no OS cache flush and only two conversations limit causal and statistical conclusions.

Whole-request monotonic/raw ratios span 1.08355–1.10000 across the matrix; raw/QPC stays within 0.999999–1.000004. Depth1's raw decode rate also trails stockB by 5.739%, and independent client wall confirms the slower result.

Historical greedy coding stockB measured 1093.67 prefill / 46.9304 decode. Current stockA is slower (-16.51% prefill / -20.52% decode); that sequential variation has no isolated cause. Historical values are not substituted for current bookends.

Those historical/current stock manifests have identical native environments. Mounts differ only in the run-specific entrypoint and service-state paths; the manifest comparison does not identify a changed compute setting that explains the variation.

The historical 8K stock 1768.47 PP-only / 46.355 MTP decode / 60% acceptance is a separate greedy story workload, at 262144 capacity with cache Off / thinking Off and separate prefill/decode cohorts. This matrix does not change those measurements.

Exact profile/client/coordinator pins, per-request raw/calibrated rates, equality hashes, draft counts, retained lifecycle IDs and memory floors: [results.json](results.json). Raw receipts remain under `server/.local/article0162-20261003/`, using the three `greedy-d1cmp-*` namespaces. Publication reads saved receipts only.
