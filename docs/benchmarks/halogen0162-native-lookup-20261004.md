# Halogen 0.16.2 native lookup placement — sampled article, 2026-10-04

Serving the qualified, bit-identical n-gram feature tensor from native WSL ext4 improved initial-turn prefill in both retained article replicas against both stock bookends. It did **not** establish a decode or full three-turn wall-time gain. The later Stock B decoded substantially faster than either earlier cell, so the Stock A-only improvement is insufficient for an end-to-end claim. This is a local GPU-backend lookup-placement result; it contains no NPU speed measurement or promotion.

## Matched workload and result

Order was Stock A → native lookup → Stock B. All cells used the frozen sampled article client and replacement coding corpus, capacity 65,536, nominal fill 32,768, native MTP depth 2, prompt cache Off, concurrency 1, low-effort thinking, and output limit 1,536. Each cell retained two replicas of three turns. Actual initial inputs were 32,791 and 32,792 tokens; corresponding requests, input/output counts, finish reasons and canonical generated-output hashes matched across all three cells. Retrieval was 14/14 in each cell. PLD policy and adaptation were unchanged; this placement intervention concerns the model's n-gram feature tensor, independently of speculative prompt lookup.

| Cell | Initial-turn PP mean, tok/s | Token-weighted decode, tok/s | Observed six-request wall, s | Accepted/drafted | Retrieval | Cleanup scope |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Stock A | 988.615 | 23.399 | 349.332 | 2156/2539 | 14/14 | Original normal cleanup |
| Native WSL lookup | 1441.064 | 25.363 | 311.830 | 2156/2539 | 14/14 | Container cleanup; separately captured late RAM recovery |
| Stock B | 1108.969 | 40.687 | 256.918 | 2156/2539 | 14/14 | Normal cleanup after Stock B resume |

Prefill means above use only the two initial `turn0` rows. Decode is the output-token-weighted harmonic phase rate across six requests. Wall is the sum of observed request wall times, excluding startup, copying, qualification and recovery. Accepted/drafted is the integer sum across six requests: 84.9153% in every cell. It is reported independently of speed and behavioral parity.

| Matched initial-turn stratum | Stock A PP | Native PP | Stock B PP | Native vs A | Native vs B | Clears both bookends and their drift |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| rep0/turn0 | 1039.861 | 1390.050 | 1084.651 | +33.68% | +28.16% | Yes |
| rep1/turn0 | 937.369 | 1492.078 | 1133.288 | +59.18% | +31.66% | Yes |

“Cold initial prefill” here means the first turn of a conversation with no prompt-cache tokens. Rep0/turn0 is also the first retained article request of each lifecycle. Rep1/turn0 and later turns remain separate; no OS cache flush or article warmup was performed. Stock A's first prefill was 1039.9 tok/s versus 1585.7 tok/s in its first followup, illustrating why these request strata must not be pooled as replicate noise.

The local guard compares each matching rep/turn separately: a rate must exceed `max(A, B) + abs(A - B)`; a latency must fall below `min(A, B) - abs(A - B)`. Both initial prefill rows pass. An isolated rep0/turn2 prefill row also passes (+1.84% versus Stock B), but its rep1 counterpart does not; this does not establish a consistent followup-prefill gain. The first rep0 request wall passes its local guard, while rep1 does not. These individual flags remain in the JSON evidence.

| Cell | Observed rep0 three-turn wall, s | Observed rep1 three-turn wall, s |
| --- | ---: | ---: |
| Stock A | 172.234 | 177.098 |
| Native WSL lookup | 156.521 | 155.309 |
| Stock B | 128.832 | 128.086 |

Native is slower than Stock B in both observed three-turn sequences. No matched decode row qualifies against both controls and their drift; neither three-turn wall qualifies. The renderer therefore records no qualified decode, full-wall or joint wall/decode gain. Two replicas with different corpus order, seed and output lengths support a bounded descriptive result, not population significance or a thermal-causation claim. The client's `three_turn_seconds` metric is a normalized sum of TTFT + 1000/decode estimates; it is not substituted for the observed wall values above.

## Original failure and supplemental recovery

Native completed all six measurements and container cleanup, but its original normal recovery window failed. The original matrix stopped before Stock B and remains failed and immutable. Native's `normal_cleanup=false` is retained explicitly.

Root subsequently captured five recovery frames satisfying the **original** available-RAM requirement `max(24 GiB, baseline - 2 GiB)` and at least 22 GiB commit headroom, with exact owned process/container identity and absence checks. Original baseline was 43.050987 GiB; original required available RAM was 41.050987 GiB. The receipt supplements the later recovery scope; it does not rewrite the original lifecycle or claim that normal cleanup succeeded.

A separate resume reused the retained Stock A/native measurement receipts and launched only the original, previously unstarted Stock B profile/client workload. Stock B then completed normal cleanup. The final resumed evidence passed every source/input/runtime, selected-intervention, actual-engine, request/count/finish, generated-output and retrieval gate, with the explicit native supplemental scope accepted by the pinned pure validator. No native measurements were repeated.

## Receipts and sanitized evidence

[Sanitized renderer sidecar](halogen0162-native-lookup-20261004.json) contains the exact per-request timing/counter/hash metadata, local drift comparisons, qualified flags, source/input checks and recovery provenance. It is a byte-identical copy of the existing completed renderer sidecar: 50,630 bytes, SHA-256 `5b9f2a7bfd7bde2118f6e9c84ccd58b0c893dfc51ea8fab0d0e3f96c58c3807d`. Recursive inspection found no generated answers, reasoning text, prompt/message content, API-token bytes or credential fields. Prompt/output token counts and SHA-256 values are metadata; model and lookup payloads were not copied.

| Receipt | SHA-256 |
| --- | --- |
| Original immutable article plan | `b9d95e7e57704f0b652978cd240a0531f46d4e66bf950c9fdeb53f3a2a5e0cbe` |
| Preserved failed original matrix-state | `6e5d76b9ea6f2ade4bf0de23f8d3487c39f8e5d60b9a0b9bd9b91763866a8b96` |
| Supplemental late recovery release | `cba86707e614276a4bf94d3c9f19e2fb1966fed9689b5fd326c9f65d46bc56b9` |
| Stock B resume plan | `28f07a39bde3036d24e85fd5ea12532e1f9dddd5f60f2b17c397961a0f336984` |
| Resume coordinator source | `319a0248fb67a7eecf14c6a13f24d144ed3068617c87c83759ce35852f8f8a3e` |
| Result renderer source | `864a44ae822e9cf9ecc7d8ad5b99b7c3a20d73f7d2f6fb7fbe831973e8be961c` |

Detailed local receipt paths and further metadata hashes are retained in the sidecar. The candidate uses a validated n-gram-only HGN wrapper, independently read back before this experiment; its container-file SHA-256 is `3343a193cb2e1fe68fac83a42b49176621174abb1cc57ba67e2ab149ead80575`, with n-gram tensor payload SHA-256 `c42900db1bef0d9a688241031f614e179752b0463f822dc07a197b1a42493d8c`. The primary model-weight path and lookup values stayed fixed.

The prior greedy 8K serial PP-only result 1661.0181 and separate native MTP PP 1584.5019/TG 47.0600 with 207/345 acceptance are different workload/cohort references, not article controls. This completed article note makes no claim about regular 8K placement/PLD results.
