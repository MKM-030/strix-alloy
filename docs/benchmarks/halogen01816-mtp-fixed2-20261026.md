# Halogen 0.18.16: retain adaptive MTP

Fixed depth 2 with gate 0 did not improve either frozen workload. Retain adaptive gate 0.90. All 24 requests completed with exact request, output, input/output-token and finish-reason parity. Six warmups are excluded, leaving 18 measurements; genuine draft and acceptance differences remain recorded by policy.

| Whole HTTP mean, seconds | Adaptive before | Fixed2 | Adaptive after | Fixed2 longer vs controls |
|---|---:|---:|---:|---:|
| 8K input / 128 output | 6.8928 | 7.0456 | 6.8539 | 2.22–2.80% |
| 16K input / 128 output | 11.8636 | 11.8960 | 11.7456 | 0.27–1.28% |

At 8K, adaptive accepted 210/318 drafts (66.04%); fixed2 accepted 201/360 (55.83%). At 16K, the figures were 177/336 (52.68%) and 180/399 (45.11%). The returning adaptive counts match the first control. Acceptance alone is not a speed result.

Only the two MTP policy fields changed. All windows used 0.18.16 v2, OEM Performance mode, 32K capacity, 8K chunk/arena, Cache Off/no_store, Thinking Off, TextOnly, PLD 3,3 and prefetch Off. Times cover complete Windows QPC HTTP intervals. Native phase rates remain unqualified; no statistical-significance claim is made.

The first returning-control startup failed during model loading before receiving requests. Its original failure remains retained. A separate owned recovery collected only the missing A_after window; neither earlier window was rerun. This interruption limits the temporal match of the bookends. Normal uninstrumented serving was restored after recovery.

At completion of this earlier cohort, the independently qualified 8K result was **1,858.90 Prefill / 54.37 Decode tok/s, 210/318 acceptance**. The later [evening 8K/16K report](halogen01816-natural-8k16k-20261026-evening.md) supersedes that serving-rate headline and retains its separate RAW/API clock observations. No Fixed2 promotion follows, and the broader optimization goal remains unachieved. The [JSON evidence](halogen01816-mtp-fixed2-20261026.json) pins all raw requests/responses/client clocks, the recovered comparison and lifecycle receipts. The separate PF cohort is outside this report.
