# Independent saved affinity A/B/A audit

All 36 request ordinals passed independent raw request/response, token, output, native scoped-counter and QPC checks. Nine warmups are excluded; 27 requests are measured. The same server identities and original affinity masks are restored.

The candidate is **not promoted**. At 8K it is 1.06% slower than the restored bookend. The 16K and separate PP1 requests are shorter against both bookends in this cohort, but the result does not establish an overall inference improvement. The complete prefill/decode/acceptance optimization goal remains unachieved.

| Workload | Original HTTP s | Co-located HTTP s | Restored HTTP s | B vs before | B vs after | Acceptance |
|---|---:|---:|---:|---:|---:|---:|
| historical8k: 8,192 input → 128 output | 11.181330 | 9.986964 | 9.882146 | -10.68% | +1.06% | 210/318 (66.04%) |
| natural16k: 16,384 input → 128 output | 18.007172 | 16.723346 | 17.305912 | -7.13% | -3.37% | 177/336 (52.68%) |
| pp8k: 8,192 input → 1 output | 7.591938 | 6.563064 | 6.678852 | -13.55% | -1.73% | N/A (no drafts) |

These are three measured requests after one excluded warmup per workload and window, on the same Halogen 0.18.16 engine with 32,768 context capacity, adaptive MTP gate0.90/PLD3,3, chunk8192/arena8192, CacheOff and ThinkingOff. Request bytes remain frozen. Every ordinal's output hash, actual token counts, combined and scoped native counters agree across all three windows. Acceptance is unchanged: all accepted/drafted proposals in the MTP requests belong to the native head; lookup and grammar each report zero proposals. PP1 remains a separate serial case with no decode or acceptance claim.

Negative duration percentages mean shorter complete HTTP requests. These are whole-request QPC durations; they are not independently measured prefill or decode token rates. No native phase rescaling is performed.

Observed idle CPU totals: 1.9992 → 0.9896 → 1.9913 guest logical cores. The separate roughly one-second RAW observations do not establish GPU package-power causation or function identity.

The affinity lease co-located only the two observed idle hot TIDs on guest logical CPU23. Original masks0–23 were verified restored on both bound TIDs; main-thread affinity was not changed. This demonstrates reduced aggregate idle polling CPU, while inference benefit remains mixed. Guest logical placement does not identify Windows physical-core placement. Continuous sampled physical reserve stayed at least22.0134GiB and commit headroom113.1437GiB. The existing server remained open with no restart.

The independently recomputed means, duration differences and counts exactly match Root's saved comparison. This single three-request sample per window establishes no general or statistically significant speed gain. Per-request timing, combined and scoped counters, source/raw hashes and restoration evidence are retained in the JSON companion. No engine or hardware action was performed by this analyzer.
