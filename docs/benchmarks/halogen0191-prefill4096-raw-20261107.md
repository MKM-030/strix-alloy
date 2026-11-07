# Halogen 0.19.1 prefill4096 RAW comparison

The campaign is terminal and the normal serving profile was restored.

RAW bounds include observer overhead. Native clock and API rates are separate observations. API phase clocks remain unqualified.

## Profiles

| Arm | Native slots | Prefill chunk | Max prefill tokens | KV pool positions | PLD |
| --- | --- | --- | --- | --- | --- |
| before | 1 | 2048 | 2048 | 32768 | 3,3 |
| candidate | 1 | 4096 | 4096 | 32768 | 3,3 |

## Workloads

Natural8192 and natural16384 use genuine War and Peace prose. Native input counts include the frozen task and prompt framing.

## Complete cohorts

Each complete cohort contains one excluded warmup and three measured requests. The table summarizes those three measured requests.

| Arm | Case | Native input tokens | Actual output tokens | Head accepted/drafted | RAW prefill t/s, midpoint [lower, upper] | RAW decode t/s, midpoint [lower, upper] | HTTP QPC seconds | Matched comparison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| before | natural8192 | 8192 | 128 | 207/327 (63.303%) | 1143.701 [1143.701, 1143.701] | 48.575 [48.575, 48.575] | 9.829977 | False |
| before | natural16384 | 16384 | 128 | 210/321 (65.421%) | 1124.358 [1124.357, 1124.358] | 49.677 [49.677, 49.677] | 17.189814 | False |

No three-arm comparison qualified.

## Native and API observations

| Arm | Case | Native prefill t/s | Native decode t/s | API prefill t/s | API decode t/s |
| --- | --- | --- | --- | --- | --- |
| before | natural8192 | 1143.701 | 48.575 | 1143.698 | 48.575 |
| before | natural16384 | 1124.358 | 49.677 | 1124.359 | 49.677 |

## Failed, partial and unstarted cohorts

| Arm | Case | Status | Saved samples | Saved responses | Error type |
| --- | --- | --- | --- | --- | --- |
| candidate | natural8192 | failed_or_partial | 1 | 1 | ValueError |
| candidate | natural16384 | not_started | 0 | 0 |  |
| after | natural8192 | not_started | 0 | 0 |  |
| after | natural16384 | not_started | 0 | 0 |  |

The accompanying JSON retains actual token counts, pooled head, lookup and grammar counters, qualification checks and source, request, response and journal hashes. Full response bodies remain private.
