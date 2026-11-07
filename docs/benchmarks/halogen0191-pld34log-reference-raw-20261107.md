# Halogen 0.19.1 pld34log_reference RAW comparison

**Performance-only study against the recorded API-visible serial response. That recorded response failed the canonical final-LF requirement.**

The frozen recorded output has 4933 UTF-8 bytes. The canonical expected output has 4934 bytes and includes one final LF absent from the recorded output. Native token-sequence identity is unverified.

The public plan was registered before measurements. [Study plan](halogen0191-log-serial-reference-plan-20261107.md).

The original failed pilot has a separate report. [Failed canonical pilot](halogen0191-pld34log-raw-20261107.md).

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
| before | real-log-json-quote | failed_or_partial | 2 | 2 | AssertionError |
| candidate | real-log-json-quote | not_started | 0 | 0 |  |
| after | real-log-json-quote | not_started | 0 | 0 |  |

The accompanying JSON retains actual token counts, pooled head, lookup and grammar counters, qualification checks and source, request, response and journal hashes. Full response bodies remain private.
