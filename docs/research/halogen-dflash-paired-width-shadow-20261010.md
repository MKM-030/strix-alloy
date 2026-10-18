# DFlash paired query-width screen — 10 October 2026

One frozen natural 16,384-input/128-output request; 32 identical anchors, one excluded paired warmup, 16 pairs in each execution order. Both bodies use grouped_batch2 attention, the original BF16 full head for three outputs, one accepted-context cache and shared learned buffers.

| Query slots | Mean consecutive matched tokens | Any match | All three | Pure proposal mean (ms) |
|---|---:|---:|---:|---:|
| 3 | 0.62500 | 13/32 | 2/32 | 35.63568 |
| 7 | 0.68750 | 14/32 | 2/32 | 37.12534 |

Seven slots improved 1 anchors, tied 31 and worsened 0. Mean useful-prefix change: +0.06250 tokens.

These are shadow agreement and measured component costs. They are not native MTP acceptance or serving token rates. No Ready publication/acquisition or NPU execution occurred. Dispatch and finite-sync timings are host envelopes; device work can extend into the following synchronization envelope.

Seven slots improved this panel only; native attachment/serving benefit remains unqualified.

The owned trial ended and the normal 262,144-context server was restored ready/open. Raw rows, excluded warmup, ownership/retirement evidence and memory minima are linked in the JSON report.
