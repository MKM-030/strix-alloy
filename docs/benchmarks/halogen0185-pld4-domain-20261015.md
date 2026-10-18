# Halogen 0.18.5 PLD K4 domain comparison — 15 October 2026

**Retain PLD 3,3 with fixed MTP depth 2/gate0 and native default 64 readers.** K4 improves code lookup accepted tokens per round, but establishes no overall HTTP gain under the frozen promotion rule.

The fixed mix takes +0.303456% more HTTP time than the mean of the controls. Code and incident fall between the two controls; JSON is slower than both. The code and mix candidates therefore fail to beat both controls beyond their drift.

The first K3 window reuses the already qualified final control from the prior gate comparison; it was not resent. Candidate and final K3 each add twelve calls: one excluded warmup plus three measured requests for each case. All 27 measured requests and nine excluded warmups across the three windows are preserved. This bounded sequential comparison supports no statistical-significance claim.

| Case | Actual input/output per request | K3 before HTTP mean (s) | K4 HTTP mean (s) | K3 after HTTP mean (s) | K4 vs before | K4 vs after | K4 vs bookend mean | K3 bookend drift |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| code | 166/512 | 8.100032 | 8.132244 | 8.150909 | +0.397682% | -0.228990% | +0.083365% | +0.628110% |
| incident | 220/512 | 9.260128 | 9.320050 | 9.321737 | +0.647102% | -0.018095% | +0.313401% | +0.665317% |
| json | 142/51 | 1.011249 | 1.024429 | 0.997595 | +1.303382% | +2.689900% | +1.991929% | -1.350199% |

Positive candidate percentages mean slower. Bookend drift compares final K3 with reused K3. The mix weights three requests from each case; it does not estimate the user’s workload distribution.

| Window | Fixed-mix measured HTTP (s) | Actual output tokens | Output / whole HTTP second |
|---|---:|---:|---:|
| K3 before (reused) | 55.1142254 | 3225 | 58.514839 |
| K4 candidate | 55.4301711 | 3225 | 58.181311 |
| K3 after | 55.4107226 | 3225 | 58.201732 |

K4 mix change: +0.573256% versus before; +0.035099% versus after. Mix bookend drift is +0.537969%.

| Case/window | All measured HTTP walls (s) | HTTP sample SD (s) |
|---|---|---:|
| code / K3 before (reused) | 8.1772568, 8.0895520, 8.0332872 | 0.072555 |
| code / K4 candidate | 8.2179181, 8.1161324, 8.0626826 | 0.078862 |
| code / K3 after | 8.2290608, 8.1541183, 8.0695482 | 0.079805 |
| incident / K3 before (reused) | 9.2762531, 9.2766955, 9.2274346 | 0.028314 |
| incident / K4 candidate | 9.3343629, 9.3315355, 9.2942521 | 0.022386 |
| incident / K3 after | 9.3156142, 9.3265168, 9.3230797 | 0.005574 |
| json / K3 before (reused) | 0.9930661, 0.9965575, 1.0441226 | 0.028523 |
| json / K4 candidate | 1.0063853, 1.0061059, 1.0607963 | 0.031495 |
| json / K3 after | 0.9979318, 0.9992375, 0.9956153 | 0.001834 |

Counters below pool the three measured requests in each cell. Grammar rounds/drafts/accepts are zero in every cell; no strict-tool variant was measured.

| Case/window | Head accepted/drafted | Head rounds | Accepted/head round | Lookup accepted/drafted | Lookup rounds | Accepted/lookup round |
|---|---:|---:|---:|---:|---:|---:|
| code / K3 before (reused) | 729/924 | 462 | 1.577922 | 243/297 | 99 | 2.454545 |
| code / K4 candidate | 723/912 | 456 | 1.585526 | 261/369 | 93 | 2.806452 |
| code / K3 after | 729/924 | 462 | 1.577922 | 243/297 | 99 | 2.454545 |
| incident / K3 before (reused) | 861/1284 | 642 | 1.341121 | 18/36 | 12 | 1.500000 |
| incident / K4 candidate | 861/1284 | 642 | 1.341121 | 18/48 | 12 | 1.500000 |
| incident / K3 after | 861/1284 | 642 | 1.341121 | 18/36 | 12 | 1.500000 |
| json / K3 before (reused) | 93/102 | 51 | 1.823529 | 9/9 | 3 | 3.000000 |
| json / K4 candidate | 90/102 | 51 | 1.764706 | 12/12 | 3 | 4.000000 |
| json / K3 after | 93/102 | 51 | 1.823529 | 9/9 | 3 | 3.000000 |

On each code reply, lookup moves from 81/99 accepted/drafted over 33 rounds to 87/123 over 31 rounds: accepted tokens per lookup round rises from 2.454545 to 2.806452 (+14.336918%). Head moves from 243/308 over 154 rounds to 241/304 over 152 rounds. Total rounds fall 187→183, total accepted drafts rise 324→328, and total proposals rise 407→427 for the same 512 output tokens. These actual schedule totals do not recover per-position marginal acceptance or isolate a native component cost. A lookup efficiency gain alone did not satisfy complete HTTP selection.

**API prefill/decode clocks remain independently unqualified.** The following rates are retained native observations in tokens/second. Pooled rates divide summed actual tokens by summed reported API phase seconds; arithmetic means remain separate. No scaling or overhead subtraction is applied. Whole HTTP uses the independent client clock; nonstream body arrival is not TTFT.

| Case/window | Pooled API prefill* | Mean API prefill* | Pooled API decode* | Mean API decode* |
|---|---:|---:|---:|---:|
| code / K3 before (reused) | 689.655172 | 689.862333 | 65.652248 | 65.653000 |
| code / K4 candidate | 573.798825 | 604.777667 | 65.370604 | 65.371333 |
| code / K3 after | 566.424022 | 596.898000 | 65.248974 | 65.250333 |
| incident / K3 before (reused) | 800.291015 | 800.366000 | 57.049896 | 57.050333 |
| incident / K4 candidate | 778.210117 | 778.450000 | 56.719989 | 56.720333 |
| incident / K3 after | 773.014758 | 773.101000 | 56.727950 | 56.728000 |
| json / K3 before (reused) | 609.878311 | 609.898333 | 66.305525 | 66.366333 |
| json / K4 candidate | 603.655944 | 603.684000 | 65.432152 | 65.494667 |
| json / K3 after | 607.443320 | 607.458000 | 67.663188 | 67.663000 |

All raw output hashes, actual token counts and finish reasons match across the three policies within each case. Code and incident each generate 512 tokens and stop at the cap. Code ends inside the Script Include before its query/function are complete. Incident ends midsection 4 and proposes creating a test account despite the requested read-only diagnostic checklist. These identical prefixes are performance evidence, not complete usable artifacts. JSON produces 51 tokens, stops normally and passes exact field/type checks.

Both controls use native HALOGEN_PLD=3,3; the candidate uses 3,4. All use the same pinned 0.18.5 engine image, full 262,144 context, one slot, fixed depth 2/gate0, prefill/arena 4,096, vision enabled and global Exact cache. Frozen requests use temperature 0/seed 1, Thinking Off and no_store; cached/reasoning counts and clamps remain zero. All omit the reader override; exact getter bytes in both unchanged engine files establish default 64.

The baseline manifest is explicitly resolved under next-pld4-prep/saved-install/services/5acb5a42bb3b42e5b66f3676c3e55c6a after root’s recorded migration. Candidate and final manifests are bound to their recorded run/container/profile identities. The only runtime source member changed is speculation_policy.py adding exact PLD 3,4 admission, with its sources.json pin updated; the other 43 source pins and all compiled/include products match. Profile bytes differ only at PLD 3,3→3,4. The engine image and engine hash are unchanged.

This report replays all saved raw/client receipts through the frozen collector and checks memory, traffic and request/runtime identity evidence. No live API, hardware or lifecycle operation was performed by reporting. Root separately owns final readiness. No timing outlier receives a causal attribution, and no version-speed or NPU-speed claim is made. The frozen one-candidate screen stops here; retain PLD 3,3. Full identities, raw/client hashes, scoped ledgers, phase discrepancies, source migration proof and protocol are in the JSON report.
