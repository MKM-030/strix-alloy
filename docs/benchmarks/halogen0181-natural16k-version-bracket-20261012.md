# Halogen 0.18.1 natural 16K version comparison — 12 October 2026

The complete clean 0.17.4 → 0.18.1 → 0.17.4 bracket finished with identical greedy output and counters in all twelve requests. One excluded warmup and three measurements per window used 16,384 actual non-repetitive input tokens, 128 output tokens, capacity32,768, chunk/arena8,192, MTP2/PLD3,3, temperature0/seed1, Cache Off and a Thinking Off rendered prompt. No phase observer was loaded in these cohorts.

| Window | Whole request QPC s | API Prefill tok/s* | API Decode tok/s* | Combined draft acceptance |
|---|---:|---:|---:|---:|
| 0.17.4 a-before | 15.894 | 1309.72 | 38.74 | 45.11% |
| 0.18.1 b | 15.531 | 1327.33 | 41.35 | 45.11% |
| 0.17.4 a-after | 15.825 | 1274.78 | 37.72 | 45.11% |

0.18.1's observed mean complete-request time was **2.07% lower** than the pooled control mean of 15.85967s, and lower than both controls individually. Control bookend drift was -0.44%. Three repetitions per arm supply a small descriptive screen, not a significance claim or isolation of an individual kernel. All output hashes are `940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec`. Each measured window accepted180/399=45.1128% by the combined API MTP+PLD convention; neural MTP-only acceptance is not isolated.

*API phase rates are retained unchanged from the engine responses and are **not independently qualified clean phase measurements**. In the first measured A-after reply, the native API reports13,572.6ms Prefill plus3,566.5ms Decode (17.1391s) against15.8228178s for the whole response in independent Windows QPC. No HTTP-derived scaling factor or phase-overhead subtraction is applied. This inconsistency prevents a qualified phase-speed improvement claim. The 0.18.1 cohort reports mean1,327.33 Prefill and41.35 Decode tok/s as observations only.

Every cohort passed raw-reply/source/profile/runtime identity, counts, output, finish, Cache Off, reserved-memory and exclusive completed-request accounting. Fresh Windows process/GPU snapshots found no League/Riot process or nonzero GPU engine above the predeclared threshold. Warmups remain excluded and preserved separately in the JSON.

The already prepared single-request 0.18.1 clock diagnostic was rejected by automatic approval review before any process/start intent existed; it was not executed. Root instead starts the ordinary observer-free 0.18.1 full262/4K serving profile and leaves it open for ServiceNow. Its final live identity/readiness receipt is recorded separately in continuation-current.json; this report does not infer readiness from launch.

The input/profile differs from the historical8K/48.424tok/s measurement and from the prior long-prefix cohorts. Those results are not replaced or averaged here. No NPU speed/acceptance benefit or complete-goal achievement is claimed. [Machine-readable measurements](halogen0181-natural16k-version-bracket-20261012.json).
