# Halogen 0.18.5 sampled complete-fixture screen — 15 October 2026

**Descriptive sampled serial → MTP → serial comparison. No automatic quality, full-goal or production promotion.**

One fixed sampler (temperature 0.7, top_p 0.95, top_k 20, min_p 0, penalties 0/0/1), Thinking Off and no_store applies to all arms on the same recorded instance. Each case/window excludes one warmup and retains all three predeclared measured seeds, including failed/incomplete answers. Variable sampled output lengths and hashes are permitted. Greedy is a different generation target and is not pooled here.

Final independent artifact review: code has2/3 definite static failures and1/3 with no defect identified per arm; parser/mock execution remains unexecuted. Incident has0/3 successful answers per arm. JSON has3/3 exact successful artifacts per arm. Initial collector manual-pending counts below are pre-review observations, not outstanding review requests. Overall useful-task/production promotion remains unqualified.

| Case/window | Attempts | All measured HTTP (s) | HTTP mean ± SD (s) | Actual output tokens | Tokens / whole HTTP s | Finish reasons / caps |
|---|---:|---:|---:|---|---:|---|
| code / serial-before | 3/3 | 28.5779592 | 9.525986 ± 0.346890 | 321, 314, 302 | 32.787506 | stop, stop, stop; 0 caps |
| code / mtp | 3/3 | 15.3264068 | 5.108802 ± 0.451105 | 289, 356, 290 | 61.005819 | stop, stop, stop; 0 caps |
| code / serial-after | 3/3 | 26.8268402 | 8.942280 ± 0.246562 | 321, 314, 302 | 34.927706 | stop, stop, stop; 0 caps |
| incident / serial-before | 3/3 | 34.2282131 | 11.409404 ± 0.297309 | 343, 342, 314 | 29.186449 | stop, stop, stop; 0 caps |
| incident / mtp | 3/3 | 25.5390254 | 8.513008 ± 1.070233 | 258, 282, 362 | 35.318497 | stop, stop, stop; 0 caps |
| incident / serial-after | 3/3 | 28.1974855 | 9.399162 ± 0.462015 | 343, 342, 314 | 35.428691 | stop, stop, stop; 0 caps |
| json / serial-before | 3/3 | 7.9127949 | 2.637598 ± 0.213778 | 80, 80, 80 | 30.330623 | stop, stop, stop; 0 caps |
| json / mtp | 3/3 | 4.0918679 | 1.363956 ± 0.035846 | 80, 80, 80 | 58.652920 | stop, stop, stop; 0 caps |
| json / serial-after | 3/3 | 7.1937954 | 2.397932 ± 0.005884 | 80, 80, 80 | 33.362083 | stop, stop, stop; 0 caps |

| Case | MTP HTTP vs serial before | MTP HTTP vs serial after | MTP HTTP vs bookend mean | Serial drift |
|---|---:|---:|---:|---:|
| code | -46.369835% | -42.869131% | -44.674804% | -6.127516% |
| incident | -25.386040% | -9.428004% | -18.177847% | -17.619172% |
| json | -48.287957% | -43.119485% | -45.826718% | -9.086543% |

Positive MTP changes mean longer elapsed time. These are per-attempt HTTP observations; faster complete useful tasks require separate successful-artifact grading. No measurement is discarded and no outlier cause is assigned.

| Fixed mix/window | Measured attempts | All measured HTTP (s) | Actual output total | Tokens / whole HTTP s | Accepted/drafted | Acceptance |
|---|---:|---:|---:|---:|---:|---:|
| serial-before | 9 | 70.7189672 | 2176 | 30.769680 | 0/0 | n/a (zero or unavailable drafts) |
| mtp | 9 | 44.9573001 | 2077 | 46.199394 | 1296/1681 | 77.097% |
| serial-after | 9 | 62.2181211 | 2176 | 34.973734 | 0/0 | n/a (zero or unavailable drafts) |

Fixed-mix MTP HTTP changes by -36.428229% versus before, -27.742434% versus after and -32.363044% versus their mean. The mix weights the frozen case set, not the user's workload distribution.

| Case/window | Source | Accepted/drafted | Rounds | Accepted/round |
|---|---|---:|---:|---:|
| code / serial-before | head | 0/0 | 0 | unavailable |
| code / serial-before | lookup | 0/0 | 0 | unavailable |
| code / serial-before | grammar | 0/0 | 0 | unavailable |
| code / mtp | head | 669/728 | 268 | 2.496269 |
| code / mtp | lookup | 0/0 | 0 | unavailable |
| code / mtp | grammar | 0/0 | 0 | unavailable |
| code / serial-after | head | 0/0 | 0 | unavailable |
| code / serial-after | lookup | 0/0 | 0 | unavailable |
| code / serial-after | grammar | 0/0 | 0 | unavailable |
| incident / serial-before | head | 0/0 | 0 | unavailable |
| incident / serial-before | lookup | 0/0 | 0 | unavailable |
| incident / serial-before | grammar | 0/0 | 0 | unavailable |
| incident / mtp | head | 450/758 | 454 | 0.991189 |
| incident / mtp | lookup | 0/0 | 0 | unavailable |
| incident / mtp | grammar | 0/0 | 0 | unavailable |
| incident / serial-after | head | 0/0 | 0 | unavailable |
| incident / serial-after | lookup | 0/0 | 0 | unavailable |
| incident / serial-after | grammar | 0/0 | 0 | unavailable |
| json / serial-before | head | 0/0 | 0 | unavailable |
| json / serial-before | lookup | 0/0 | 0 | unavailable |
| json / serial-before | grammar | 0/0 | 0 | unavailable |
| json / mtp | head | 177/195 | 66 | 2.681818 |
| json / mtp | lookup | 0/0 | 0 | unavailable |
| json / mtp | grammar | 0/0 | 0 | unavailable |
| json / serial-after | head | 0/0 | 0 | unavailable |
| json / serial-after | lookup | 0/0 | 0 | unavailable |
| json / serial-after | grammar | 0/0 | 0 | unavailable |

Serial requests map to native drafter none with zero drafted/accepted and null acceptance. Missing counters are unavailable rather than zero. Sampled lookup and grammar must be zero under the frozen source contract. Head accepted counts are API-derived from commits/rounds/shared/lookup/grammar; they are not a wholly independent acceptance instrument.

**Every API phase rate is independently unqualified.** Pooled rates below use summed actual phase tokens divided by summed reported API milliseconds. Arithmetic means and each raw phase/HTTP discrepancy are retained in JSON. No phase scaling, overhead subtraction or native component attribution is applied. Nonstream body arrival is not TTFT.

| Case/window | Pooled API prefill* | Mean API prefill* | Pooled API decode* | Mean API decode* |
|---|---:|---:|---:|---:|
| code / serial-before | 749.906262 | 749.906333 | 33.348875 | 33.344000 |
| code / mtp | 591.366056 | 611.779333 | 65.475273 | 65.502667 |
| code / serial-after | 741.015191 | 741.043000 | 36.040541 | 36.038333 |
| incident / serial-before | 449.737883 | 534.799000 | 30.078674 | 30.080000 |
| incident / mtp | 664.763458 | 664.788667 | 36.416782 | 36.263000 |
| incident / serial-after | 596.705308 | 601.721000 | 36.527310 | 36.525000 |
| json / serial-before | 629.464286 | 629.503667 | 33.285716 | 33.474667 |
| json / mtp | 612.599566 | 612.649000 | 71.201828 | 71.254000 |
| json / serial-after | 615.720524 | 615.838333 | 37.057625 | 37.057667 |

| Case/window | Incomplete/cap/finish failures | Transport/HTTP failures | Accounting failures | Automatic exact JSON successes | Collector pending (pre-review) |
|---|---:|---:|---:|---:|---:|
| code / serial-before | 0 | 0 | 0 | 0 | 3 |
| code / mtp | 0 | 0 | 0 | 0 | 3 |
| code / serial-after | 0 | 0 | 0 | 0 | 3 |
| incident / serial-before | 0 | 0 | 0 | 0 | 3 |
| incident / mtp | 0 | 0 | 0 | 0 | 3 |
| incident / serial-after | 0 | 0 | 0 | 0 | 3 |
| json / serial-before | 0 | 0 | 0 | 3 | 0 |
| json / mtp | 0 | 0 | 0 | 3 | 0 |
| json / serial-after | 0 | 0 | 0 | 3 | 0 |

Independent code and incident reviews are retained separately from initial collector accounting. Static findings can establish failures. JavaScript parser and mock execution are unexecuted; a static absence of a found defect is not dynamic functional success. Exact ordinary-text JSON is checked separately for full fields/values/types, duplicate keys, completion and clamps. Seconds per successful incident task is unavailable because all nine answers fail; code remains partially qualified because its three no-defect rows lack parser/mock evidence. Any task-cost calculation must divide all measured HTTP time, including failures, by independently successful tasks.

Same-drafter/equal-seed serial bookend hash observations, full independent output review (if attached), all raw/client/request pins, seeds, actual counts, complete API timings, every HTTP wall and all failure details remain in JSON. Different MTP/serial hashes are allowed; a small fixed seed set does not certify distributional equality or population quality. Prior greedy capped-prefix results are separate context and supply no same-target sampled speed claim.

Same-instance identity equality: True. Complete windows: True. Reporting performed no live API, hardware, lifecycle or production mutation.

For this exact JSON fixture only, all three measured replies per arm pass the full exact field/type and completion checks, with equal80-token outputs/hashes. MTP costs 1.363956s per successful task versus serial 2.637598s before and 2.397932s after: -45.826718% versus the bookend mean. This is a bounded descriptive JSON-specific useful-task gain, with all measured HTTP time included. It does not qualify code/incident, population quality or a production sampler change.

Separately authored output reviews are attached by file/hash in JSON. Static/semantic findings remain distinct from parser/mock evidence and do not change overall promotion flags.

Code static review: each arm has2/3 definite failures and1/3 with no defect identified by visual/static inspection. Failures include non-ES5 Number.isFinite/Number.isInteger; serial also includes a lowercase-only ID regex, and one serial reply lacks primitive-string guards. The final serial repeats reuse blind assessments only after exact content-hash matching. No parser, generated function or mock execution passed; the no-defect rows remain partial qualification.

Incident semantic review:0/3 pass in every arm. Serial replies contain277/273/248 words and exceed the strict under240-word limit; final serial content matches exactly. MTP replies1/2 are203/216 words but propose a new GET using another user’s session token or token reuse/user-context simulation and invent endpoint versions; MTP reply1 also omits full table/field ACL coverage. MTP reply3 contains294 words. Ambiguous authorized-user wording alone is not treated as proven impersonation; decisive failures and qualified concerns remain separate in the attached evidence.
