# Halogen 0.18.0: matched acceptance comparison, 11 October 2026

Both cohorts completed and passed saved-cohort qualification at **32,768 context capacity with 16,384 actual input tokens**. Native adaptive supplied no benefit in this screen: mean whole-request wall time was **17.50405% longer**, with unchanged combined acceptance and identical output. Retain fixed2. The fixed2→adaptive order has no final fixed2 bookend, so this observed difference does not isolate a causal drafting-policy effect from time/order or machine drift. Historical 262,144-capacity measurements are a separate reference and cannot supply a matched engine-speed baseline for these 32K arms.

## Verified update and source packet

The official 0.18.0 image is pinned to `ghcr.io/peonist-ai/halogen-flash-server@sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9`, revision `c31448922f6e`. Its image creation metadata is `2026-10-11T05:32:02.604217078Z`; this is not an established publication time. The extracted engine is 27,078,280 bytes, SHA256 `71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08`. [Update assessment](halogen-official-update-resume-20261011.md).

The official changelog attributes faster native prefill and drafted decode to 0.17.5; 0.18.0 adds NPU speech, session keep/fork/join and cache repairs with unchanged Flash checkpoints. These upstream claims are not local performance measurements. A bounded primary-source browser refresh at 21:35:32–21:38:26 UTC observed no material change since the 19:18 UTC check. Its receipt records browser freshness limits; it does not establish fresh raw-byte hashes or a complete publication chronology. Receipt: `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/updates-20261011-2135-source-refresh/official-update-check.json`, SHA256 `2788390daa96ca940a53eabf9838dd86c11cf0d7da79d703a4408f266f4d3a83`.

The comparison packet is under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-adaptive-option-20261011/client/`:

| Artifact | SHA256 |
|---|---|
| `fixed2-context32768-profile.json` | `3157c4300e011a19233f8f03fccd0a4d721a6fed62df1cfc340808e1b55379ca` |
| `native-adaptive-context32768-profile.json` | `574d17b9cfb9839c4377d5c2affe9b006bb0550bc2896479bd7937116b6c7e90` |
| `measure.py` | `ddfc64739e365dd0e25632019ac56c90dea6ec33596f0466c2bf6c8e563c8341` |
| `request-16384.json` | `0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c` |

Nine offline fixture tests, compilation and both file-only profile checks passed (`offline-validation-v2.json`). These checks sent no HTTP requests and exercised no memory/process or lifecycle APIs.

## Matched protocol and results

Both arms use v2, one slot, capacity 32,768, PLD `3,3`, prefill chunk/arena 8,192, and the identical natural nonrepeated request: actual input 16,384, output cap 128, temperature 0, seed 1, nonstream completion, Thinking Off and Cache Off. Each arm has one excluded warmup and three measured requests. Normal API defaults remain Thinking On, medium effort and 2,048 thinking tokens; the benchmark request overrides them.

Fixed2 sets `engine.draft_tokens=2` and native `HALOGEN_MTP_DEPTH=2`. Adaptive uses the existing supported omission route: both `engine.draft_tokens` and native `HALOGEN_MTP_DEPTH` must be **absent**, rather than empty or zero. No `draft_policy` field or controller feature was added. The client does not infer each round's native depth.

| Measured result | Fixed2 | Native adaptive |
|---|---:|---:|
| Three-request whole-request QPC times (seconds) | 16.8294892, 16.6436045, 16.5239806 | 19.4518586, 20.0762097, 19.2205203 |
| Whole-request QPC median / mean (seconds) | 16.6436045 / 16.6656914 | 19.4518586 / 19.5828629 |
| Combined accepted / proposed draft tokens | 180 / 399 | 180 / 399 |
| Combined accepted / proposed fraction | 45.11278% | 45.11278% |
| Accepted drafts / summed whole-request wall seconds | 3.6002107 | 3.0639034 |
| Proposed drafts / summed whole-request wall seconds | 7.9804670 | 6.7916525 |
| Generated tokens / summed whole-request wall seconds | 7.6804494 | 6.5363272 |
| Output identity, actual counts and finish reason | identical; 16,384 input / 128 output each; length | identical; 16,384 input / 128 output each; length |
| Saved-cohort qualification and disposition | passed; retained | passed; no adoption benefit |

Evidence is under `halogen0180-adaptive-option-20261011/{fixed2,adaptive}-32k-cohort/` in the preparation directory. Fixed2 `qualification.json` SHA256 is `f7d5945c17ff6e1f423f97191d4cb7824d247afe4a20326512b45401a696a27e`; adaptive is `ee683d6a2eaac0c08b885c6f2719ec617fdada966a56a83584d14ead0827be0e`. All six measured raw-response hashes match their client receipts, with output SHA256 `940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec`. The [companion comparison JSON](../benchmarks/halogen0180-fixed-adaptive-natural16k-20261011.json) binds qualification, client, response, profile, request and health hashes and reproduces the exact pooled arithmetic from measured replies. The saved native health before and after each cohort proves matching API/engine **0.18.0**, healthy idle operation, one slot and context/slot/KV capacity **32,768**. Full262 restoration is separate from this comparison.

Whole-request QPC wall time includes prefill and HTTP delivery. The pooled rates sum each counter across measured replies and divide by their summed QPC intervals. API phase timings are unqualified observations and must not be rescaled into Prefill/Decode rates. Counters combine MTP and PLD; neural-only acceptance is not isolated. A higher acceptance fraction alone does not establish acceleration. The 128-token cap covers equal limited work, not uncapped story completion or story quality.

The historical natural16K 0.17.4 result at capacity 262,144 has QPC median **12.8247304 seconds** and combined acceptance **180/399 = 45.11278%**. Its phase rates remain unqualified; the published control drift and overlapping ranges do not establish a robust engine gain. These values are historical context only for the present 32K comparison. [Published QPC report](../benchmarks/halogen0174-natural16k-qpc-20261010.md).

The previous 0.17.2 adaptive synthetic8K screen remains closed: unchanged 61.95% acceptance and decode 2.85% below the fixed2 bookend mean. The changed 0.18.0 engine and natural16K workload motivate this finite comparison, without predicting a gain or reopening that unchanged screen.

## Supported MTP limits

The official interface describes one MTP head and a greedy linear chain with native default depth 2 or 3 and adaptive backoff. Greedy-only PLD requires the head to open the chain; sampled requests use the head alone. `HALOGEN_MTP_HEAD` supplies a GGUF trunk's required head, rather than registering multiple heads. Two distinct conversations can draft/verify together, and sessions retain or fork resumable conversation state. No public supported same-request multi-head, tree or competing-drafter verifier is described. This is an inference from the supported contract, not an inspection of private engine capabilities. [Official flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md), [multiple-draft assessment](halogen-multiple-drafts-20261011.md).

Identical greedy clones provide no candidate diversity. Diverse proposals or increased candidate coverage still require correct selection/verification and must repay drafting, verification, state, transport and contention cost. Acceptance alone does not prove speed.

## ServiceNow launcher source check

`scripts/Start-Halogen-ServiceNow.ps1` now defaults to **Current4K / 0.18.0** after root restored full262 fixed2 serving. Current4K pairs prefill chunk and arena at 4,096 while the explicit Current8K option retains 8,192. It calls the normal installed-profile generator, preserves an existing `server/.local/servicenow-api-token.txt` as the public gateway token path, and keeps the separately generated backend token path. No token bytes were read or printed during this inspection.

`-ConsoleTrace` sets `configuration.console_trace=true` independently of version; omission leaves it false. The default serving command is now `./scripts/Start-Halogen-ServiceNow.ps1 -ConsoleTrace`. The earlier explicit Current4K check passed native PowerShell 5.1.26100.7462 parsing and CPU-only `PrintOnly`; root also confirmed the final default `PrintOnly` passed under PowerShell 5.1. It reports full262 capacity, 4,096/4,096 prefill settings, fixed2, PLD `3,3`, the retained token path and normal reserves. `PrintOnly` writes no session configuration and launches no engine. Final script SHA256: `9ff3c8629a6a588725e68850efa66bd034f917768907823b93903ea58197a69e`.

## Full262 restoration and startup admission

The earlier 0.18.0 full262 Current8K launch reached ready but the independent runtime guard stopped it at 17.965 GiB after about 90 seconds; its 22/22 GiB long-measurement request-entry check never passed. Root subsequently restored **0.18.0 v2, full262 capacity, fixed2, PLD `3,3`, Cache Off and Current4K 4,096/4,096** ready and open on port 8840. The final checkpoint records a runtime physical-memory minimum of **19.60175 GiB**, with a bound fresh readiness receipt of **21.750 GiB available physical / 110.146 GiB commit headroom**. No additional benchmark request was sent during this restoration.

The actual startup engine log reports 62.1 GiB weights, 7.2 GiB KV, **4.3 GiB working memory** and 73.6 GiB total at 4,096, compared with 5.4 GiB working memory in the earlier full262 8,192 launch. This is a startup memory observation; no Current4K serving-speed or Prefill/Decode gain is established.

The v2 consecutive-safe startup admission interval changed from 60 to **10 seconds**. Startup physical/commit floors remain **35/131 GiB**, startup/runtime reserves remain **18/18 GiB**, and the immediate checks before container/model admission and 240-second admission timeout remain. W4B retains its 60-second interval. The new long-measurement entry floors remain 22/22 GiB; ready/open status does not establish admission for another such request.

These results are bound under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-normal-bridge-preparation-20261011/`: `final-checkpoint-20261012.json` SHA256 `d04d62d0e90d40ac5c18185a0db0ce61543ea43182c2ca0247a21ffe172228fd`; its readiness receipt SHA256 is `1b56474e047e9fa8f89e9118dea9b38ec793fb98d60e7d75fa1748bbb71150f7`. The source change and retained gate checks are recorded in `admission-stability-adjustment-20261012.json`, SHA256 `69bae3c3b1432042b736dca4280737a84a97e47fd87db640b95ef53654fdcf47`. This report finalization performed no further tests, review, hardware, lifecycle or continuation-state operation.
