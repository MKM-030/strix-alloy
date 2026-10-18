# Halogen 0.18.5 full 262K domain MTP comparison — 15 October 2026

Retain current Fixed2/gate0 with native default64 readers. The gate0.90 candidate establishes no MTP speed gain in this bounded full262K domain screen.

The fixed three-case mix takes +1.513506% more measured HTTP time with gate 0.90 than the equal-weight fixed bookend reference. Every case is slower than both fixed controls. All 27 measured requests and nine excluded warmups are preserved; no outlier is removed.

**All native/API phase rates remain independently unqualified. In all three gated code replies, reported phase sums exceed complete independent HTTP wall by 0.618903–0.664617 seconds. No scaling, overhead subtraction or causal explanation is applied. HTTP comparisons below use the independent client clock.**

| Case | Actual input/output tokens per request | Fixed before HTTP mean (s) | Gate 0.90 HTTP mean (s) | Fixed after HTTP mean (s) | Gate vs bookend mean | Fixed bookend drift |
|---|---:|---:|---:|---:|---:|---:|
| code | 166/512 | 8.122348 | 8.229026 | 8.100032 | +1.452762% | -0.274750% |
| incident | 220/512 | 9.301241 | 9.430090 | 9.260128 | +1.609853% | -0.442016% |
| json | 142/51 | 0.995364 | 1.014477 | 1.011249 | +1.113372% | +1.595851% |

Positive candidate percentages mean slower; bookend drift compares fixed-after with fixed-before. The mix weights three requests from each case, not a general user workload distribution.

| Case/window | All measured HTTP walls (s) | HTTP sample SD (s) |
|---|---|---:|
| code / A-before fixed2 gate0 | 8.2052041, 8.0623837, 8.0994567 | 0.074111 |
| code / B fixed2 gate0.90 | 8.5128970, 8.1193834, 8.0547986 | 0.247951 |
| code / A-after fixed2 gate0 | 8.1772568, 8.0895520, 8.0332872 | 0.072555 |
| incident / A-before fixed2 gate0 | 9.3065141, 9.2813822, 9.3158259 | 0.017817 |
| incident / B fixed2 gate0.90 | 9.4525292, 9.4457534, 9.3919863 | 0.033172 |
| incident / A-after fixed2 gate0 | 9.2762531, 9.2766955, 9.2274346 | 0.028314 |
| json / A-before fixed2 gate0 | 0.9957834, 0.9981351, 0.9921741 | 0.003003 |
| json / B fixed2 gate0.90 | 0.9964193, 0.9992557, 1.0477560 | 0.028855 |
| json / A-after fixed2 gate0 | 0.9930661, 0.9965575, 1.0441226 | 0.028523 |

Counters below pool only the three measured requests in each cell. Head and lookup remain separate; grammar counters are zero in every cell, and the optional strict-tool variant was not measured.

| Case/window | Head accepted/drafted | Head acceptance | Accepted/head round | Head rounds | Lookup accepted/drafted | Lookup acceptance | Accepted/lookup round |
|---|---:|---:|---:|---:|---:|---:|---:|
| code / A-before fixed2 gate0 | 729/924 | 78.896% | 1.577922 | 462 | 243/297 | 81.818% | 2.454545 |
| code / B fixed2 gate0.90 | 705/840 | 83.929% | 1.459627 | 483 | 246/297 | 82.828% | 2.484848 |
| code / A-after fixed2 gate0 | 729/924 | 78.896% | 1.577922 | 462 | 243/297 | 81.818% | 2.454545 |
| incident / A-before fixed2 gate0 | 861/1284 | 67.056% | 1.341121 | 642 | 18/36 | 50.000% | 1.500000 |
| incident / B fixed2 gate0.90 | 792/1071 | 73.950% | 1.123404 | 705 | 21/45 | 46.667% | 1.400000 |
| incident / A-after fixed2 gate0 | 861/1284 | 67.056% | 1.341121 | 642 | 18/36 | 50.000% | 1.500000 |
| json / A-before fixed2 gate0 | 93/102 | 91.176% | 1.823529 | 51 | 9/9 | 100.000% | 3.000000 |
| json / B fixed2 gate0.90 | 93/102 | 91.176% | 1.823529 | 51 | 9/9 | 100.000% | 3.000000 |
| json / A-after fixed2 gate0 | 93/102 | 91.176% | 1.823529 | 51 | 9/9 | 100.000% | 3.000000 |

On code and incident, gating rejects fewer proposals and raises head acceptance percentage, while accepted head tokens per round fall and head-round counts rise. Code lookup acceptance increases slightly; incident lookup acceptance falls. JSON counters are unchanged. Higher acceptance alone is not useful throughput gain.

| Case/window | Pooled API prefill* | Mean API prefill* | Pooled API decode* | Mean API decode* |
|---|---:|---:|---:|---:|
| code / A-before fixed2 gate0 | 693.014194 | 693.066000 | 65.047261 | 65.051333 |
| code / B fixed2 gate0.90 | 449.702005 | 523.623000 | 60.181956 | 60.183000 |
| code / A-after fixed2 gate0 | 689.655172 | 689.862333 | 65.652248 | 65.653000 |
| incident / A-before fixed2 gate0 | 783.941086 | 784.295000 | 56.830795 | 56.831000 |
| incident / B fixed2 gate0.90 | 795.947902 | 796.066000 | 55.999329 | 55.999667 |
| incident / A-after fixed2 gate0 | 800.291015 | 800.366000 | 57.049896 | 57.050333 |
| json / A-before fixed2 gate0 | 612.156919 | 612.197333 | 67.768083 | 67.768000 |
| json / B fixed2 gate0.90 | 606.837607 | 606.912333 | 66.170746 | 66.238000 |
| json / A-after fixed2 gate0 | 609.878311 | 609.898333 | 66.305525 | 66.366333 |

*All values are unqualified native observations in tokens/second. Pooled rates use summed actual tokens / summed reported API phase seconds; arithmetic means stay separate. In particular, the gated code values cannot be presented as independently measured clean phase speed.

Every greedy output hash matches across all three arms within each case. Code and incident each generate exactly 512 tokens and end at the cap. Code stops inside the Script Include before its query/function are complete. Incident stops midsection 4 and proposes creating a test account despite the requested read-only diagnostic list. These identical capped prefixes are performance evidence, not usable complete artifacts. JSON generates 51 tokens, stops normally and passes all exact field/type checks.

Both policies use explicit depth 2 and PLD 3,3 on the same pinned 0.18.5 engine image, full context 262,144, prefill/arena 4,096, vision enabled and global Exact cache. The frozen requests explicitly disable thinking and use no-store; raw cached/reasoning counts are zero. Controls omit the gather-thread override; the candidate explicitly selects 64. Saved native manifests, profile hashes and container identities are verified. Exact getter bytes/disassembly bound to this engine prove default 64 when the override is absent. The source migration between before and candidate only admitted 128 in the bounded policy allowlist and updated that source pin; other runtime sources and the engine image match.

This is a descriptive three-arm policy comparison, with no statistical-significance, comparative-version-speed or NPU-on/off-speed claim. No cause is assigned to timing outliers or phase-clock inconsistency. Final live readiness is sealed separately by the parent task. Full raw/client receipts, all actual counts, policy/default-reader evidence and scoped ledgers are in the JSON report.
