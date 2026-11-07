# Halogen 0.19.1 pld34log RAW comparison

The campaign is terminal and the normal serving profile was restored.

RAW bounds include observer overhead. Native clock and API rates are separate observations. API phase clocks remain unqualified.

## Profiles

| Arm | Native slots | Prefill chunk | Max prefill tokens | KV pool positions | PLD |
| --- | --- | --- | --- | --- | --- |
| before | 1 | 2048 | 2048 | 32768 | 3,3 |

## Workloads

The real-log-json-quote workload uses frozen log records and an exact output oracle. A mechanism comparison requires positive measured lookup drafted and accepted totals in every arm.

## Complete cohorts

Each complete cohort contains one excluded warmup and three measured requests. The table summarizes those three measured requests.

| Arm | Case | Native input tokens | Actual output tokens | Head accepted/drafted | RAW prefill t/s, midpoint [lower, upper] | RAW decode t/s, midpoint [lower, upper] | HTTP QPC seconds | Matched comparison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

There are no complete measured cohorts.

No three-arm comparison qualified.

## Native and API observations

| Arm | Case | Native prefill t/s | Native decode t/s | API prefill t/s | API decode t/s |
| --- | --- | --- | --- | --- | --- |

## Failed, partial and unstarted cohorts

| Arm | Case | Status | Saved samples | Saved responses | Error type |
| --- | --- | --- | --- | --- | --- |
| before | real-log-json-quote | failed_or_partial | 0 | 0 | OracleMismatch |
| candidate | real-log-json-quote | excluded_after_baseline_failure | 0 | 0 |  |
| after | real-log-json-quote | excluded_after_baseline_failure | 0 | 0 |  |

The accompanying JSON retains actual token counts, pooled head, lookup and grammar counters, qualification checks and source, request, response and journal hashes. Full response bodies remain private.
