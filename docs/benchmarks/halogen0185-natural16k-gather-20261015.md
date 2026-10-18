# Halogen 0.18.5 native gather 64 → 128 → 64 — natural 16K

Decision: retain 64 gather readers. The 128-reader candidate increases mean whole HTTP time by 2.414799% versus the 64 bookend mean. Pooled native API prefill changes by -0.480564% and pooled native API decode by -7.905113%; these phase rates remain independently unqualified.

Each window has 177 accepted head tokens from 408 proposals across 204 rounds, or 0.867647 accepted per round. There is no accepted-per-round gain, and every greedy output matches. The larger third 128-reader request (12.5418500 seconds) is retained. No causal attribution is made for that result.

This bracket does not establish a stable whole-request gain for 128 readers over 64.

One excluded warmup and all three measured requests are retained per window, including every outlier. The frozen request uses 16,384 input tokens and 128 output tokens, temperature 0/seed 1, MTP 2/gate 0/PLD 3,3, Thinking Off, Cache Off, context 32,768 and prefill/arena 4,096. Profile bytes differ only in the explicit reader count; saved native manifests independently agree with each profile.

| Window | All measured HTTP walls (s) | HTTP mean ± SD (s) | Output tokens / HTTP second | API pooled prefill* | API pooled decode* |
|---|---|---:|---:|---:|---:|
| A-before gather64 | 11.7254297, 11.7900853, 11.8193011 | 11.778272 ± 0.048038 | 10.86747 | 1849.544 | 45.268 |
| B gather128 | 11.8673502, 11.7231229, 12.5418500 | 12.044108 ± 0.437048 | 10.62760 | 1843.924 | 41.709 |
| A-after gather64 | 11.6887951, 11.7670832, 11.7700514 | 11.741977 ± 0.046080 | 10.90106 | 1856.123 | 45.310 |

*API rates are native observations in tokens/second without independent phase-clock qualification. Pooled rates divide summed tokens by summed API phase seconds. HTTP uses an independent client clock, includes prefill/generation/delivery and is not used to rescale phases.

| Window | API arithmetic mean prefill* | API arithmetic mean decode* | Head accepted / drafted | Head acceptance | Head rounds |
|---|---:|---:|---:|---:|---:|
| A-before gather64 | 1849.571 | 45.268 | 177/408 | 43.382% | 204 |
| B gather128 | 1843.991 | 42.198 | 177/408 | 43.382% | 204 |
| A-after gather64 | 1856.169 | 45.311 | 177/408 | 43.382% | 204 |

128-reader mean HTTP time changes by +2.257% versus 64-before, +2.573% versus 64-after and +2.415% versus the equal-weight 64 bookend mean. Positive means slower. 64-after drifts -0.308% versus 64-before.

All greedy output hashes match. Head, lookup and grammar ledgers, all twelve raw responses including warmups, source/profile/manifest receipts and individual phase observations remain in JSON. No measured request is discarded.

This is a bounded descriptive 32K screen, without a statistical-significance or final 262K speed claim. Nonstream body arrival is not TTFT.
