# Halogen 0.18.16: decode prefetch Off / native auto / Off

**Recommendation: retain explicit prefetch Off for the general profile.** Native auto did not improve both MTP tasks against both Off bookends. This report makes no profile change; the final decision remains with root.

| Exact task | Off before s | Native auto s | Off after s | Auto vs first Off | Auto vs last Off |
|---|---:|---:|---:|---:|---:|
| MTP128/historical8k | 9.747121 | 10.184524 | 9.678150 | +4.488% | +5.232% |
| MTP128/natural16k | 20.516182 | 18.956558 | 18.061365 | -7.602% | +4.956% |
| PP1/pp8k | 7.994906 | 7.061462 | 7.582294 | -11.675% | -6.869% |

Values are means of three measured Windows QPC **whole HTTP** durations; positive change means slower. No native phase rates are converted or rescaled.

Auto was slower on every measured 8K MTP request than every request in either Off bookend. The apparent 16K gain against the first Off is not stable: the Off mean itself fell 11.965%, and late Off beat auto. PP1 auto had a lower mean than both Off runs, but its individual samples overlap them. These three-repeat cohorts do not establish a universal or statistically robust improvement.

All **36 fresh requests** validated: nine excluded warmups and 27 measured requests across three arms and three cases. Exact request bytes, output hashes, finish reasons, input/output token counts, drafted/accepted counts and every scoped counter matched across all four ordinals per case. No prior failed-run requests were reused.

Measured MTP acceptance was unchanged: **210/318 = 66.0377%** at 8K and **177/336 = 52.6786%** at 16K. All proposals came from the head scope (171 and 204 rounds respectively); lookup and grammar had zero rounds/drafts/acceptances. PP1 had no drafts; its acceptance ratio is unavailable, not zero.

The only candidate profile change removed `HALOGEN_DECODE_PREFETCH: 0`, allowing native auto. The full Docker environment was checked for an absent key, and the engine startup log confirmed auto selected prefetch on. Both Off arms explicitly used zero. Other conditions remained v2, 32K context, one slot, 8192 chunk/arena, TextOnly/ThinkingOff, cache Off with `no_store`, and adaptive drafting (gate 0.90, PLD 3,3). Per-suite background guards remained active.

| PP1 whole-request measured samples | Count | GPU MHz min / median / max | Usage % min / median / max | Reported GPU W | Temperature C |
|---|---:|---|---|---|---|
| A_before | 24 | 913 / 1245.0 / 1433 | 63 / 95.5 / 99 | 54 / 54.0 / 55 | 58 / 64.0 / 66 |
| B | 21 | 862 / 1380 / 1520 | 35 / 94 / 99 | 50 / 55 / 55 | 60 / 66 / 67 |
| A_after | 23 | 887 / 1287 / 1535 | 65 / 93 / 99 | 54 / 55 / 55 | 60 / 66 / 67 |

ADLX samples were included only when fully contained in each PP1 whole HTTP window using saved epoch/QPC anchor envelopes. Warmups remain separate in the JSON. These one-second samples show low clocks despite high utilization, providing an operating-condition discrepancy to investigate. They do not isolate exact GPU phases or prove a package-power cap, thermal limitation or firmware profile.

The saved final receipt records normal Off run `e7739e6e91c24e80aa4ce3ba3513f779` ready at **2026-10-26 01:34:34.141 UTC**; it is not a claim of current readiness. Earlier failed-start and interrupted cohorts remain preserved. The [verified aggregate](halogen01816-prefetch-auto-20261026.json) retains individual elapsed samples, standard deviations, acceptance scopes, sensor memory ranges and SHA-256 evidence pins.
