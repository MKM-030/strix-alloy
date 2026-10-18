# Halogen 0.18.0: supported MTP options — 11 October 2026

Source-only review. No runtime, hardware, model, image, lifecycle, continuation state or shared implementation was changed.

The strongest next comparison is **0.18.0 with the retained fixed MTP2 / PLD3,3 configuration**. The 0.17.5 [official changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md) reports faster prefill and drafted decode with unchanged checkpoints and greedy output. Neither its section nor 0.18.0 documents a new Flash acceptance algorithm. An engine speed improvement therefore must be measured separately from proposal accuracy.

## Supported controls and request semantics

The current [official flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md) document:

- `HALOGEN_MTP_DEPTH=2`: fixed greedy draft depth. Unset selects 2 or 3 per conversation.
- `HALOGEN_DRAFTER_DEFAULT=1`; per-request `"drafter":"mtp"` or `"serial"`.
- `HALOGEN_PLD=3,3`: context match length N and proposal length K. The native head must agree with the opening. `0` disables it; K above 3 exceeds the shipped verification reservation. PLD is greedy-only and requires a lone generating request.
- `HALOGEN_SPEC_ADAPT=32,0.35,64`: low acceptance pauses drafting; `0` disables adaptation. This changes which rounds draft, rather than improving a head's predictions.

The [official README sampling and concurrency sections](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/README.md) establish that explicit request `temperature:0` overrides sampling defaults; absent temperature is greedy unless a server default supplies another value. Sampling keeps MTP but removes PLD. Exactly two generating conversations can draft together and share target verification; three or more use plain batching. This parallelizes different requests. No documented control makes several independent MTP heads compete on one request. Fixed seeds can produce different sampled outputs across versions, concurrency or cache paths; preserve separate sampled comparisons.

## Practical candidate disposition

| Candidate | Exact change | Purpose and disposition |
|---|---|---|
| New-engine control | 0.18.0, fixed MTP2, PLD3,3, explicit temperature0; preserve the frozen request/settings | First priority: qualify update speed and counters against the retained 0.17.4 natural16k control. No acceptance increase is presumed. |
| Two simultaneous MTP requests | Admit exactly two independent, matched requests, each `drafter:mtp`; keep fixed2 | Upstream supports this. Measure aggregate throughput, slowest per-request rate and wall separately. PLD disappears while both generate. This cannot be reported as better acceptance on the single story request. |
| Shorter PLD tail | `HALOGEN_PLD=3,2`, fixed MTP2 | Upstream N,K option; exploratory only if authentic PLD attempts reject the third token often. Fewer proposals can raise the accepted fraction while losing batching benefit. |
| Stricter PLD match | `HALOGEN_PLD=4,3`, fixed MTP2 | Upstream N,K option; exploratory only if native attempted PLD chains have false matches. Fewer matches may reduce rejected work or remove useful drafts. |
| Adaptation ablation | `HALOGEN_SPEC_ADAPT=0`, fixed MTP2/PLD3,3 | Existing conditional candidate: only after native traces show low-acceptance windows or serial fallback. Aggregate acceptance alone does not establish either trigger. |

The two PLD alternatives had no exact-setting result in the reviewed research/benchmark Markdown. That limited search does not establish universal novelty. The managed backend currently validates only PLD `0`/`3,3` and adaptation `0`/`32,0.35,64`, as documented in [the existing policy contract](halogen-mtp-next-action-20261004.md). The PLD alternatives are **not managed-launch-ready**; bounded validation/pass-through would be separate preparation.

The [retained natural16k PLD ledger](halogen0174-pld64-zero-offer-scope-20261010.md) has zero native PLD attempts. Consequently, PLD changes have no demonstrated acceptance opportunity on that workload. Its API 180/399 = 45.11% is combined/inferred accounting; paired native neural counters are 177/396 = 44.70%. Preserve both scopes.

## Closed comparisons and algorithm boundary

Keep the earlier negative results closed unless a new-engine mechanism supplies a specific reason to revisit them:

- [Depth1](../benchmarks/halogen0162-greedy-depth1-results-20261004/README.md): +6.001 acceptance points, but 5.608% lower decode and 1.857% longer wall against warmed depth2.
- [Depth3](../benchmarks/halogen0162-greedy-depth-results-20261004/README.md): 68.322% versus 73.914% acceptance, 45.8395 versus 46.9304 decode tok/s, longer wall.
- [Stock adaptive2..3](../benchmarks/halogen0172-stock-adaptive-20261008.md): unchanged 61.95% acceptance, 2.85% lower decode versus fixed2 bookend mean on synthetic8k.
- [PLD off](../benchmarks/halogen0162-pld-stock8k-20261004.md): no qualified stock8k speed gain.

[The multiple-source assessment](halogen-multi-draft-feasibility-20261006.md) already separates oracle coverage from causal selection and native verification. Medusa, EAGLE tree verification and the existing DFlash research require distinct trained assets and engine/state integration; they are not documented 0.18.0 configuration choices. Identical deterministic MTP copies add no prediction diversity. No supported configuration or reviewed source supplies a 100% acceptance guarantee.

For any later qualified comparison, retain actual generated/proposed/accepted counts, identical greedy output and finish/cap checks, source-specific counters where available, phase timings and independent request wall. Select useful committed tokens per complete elapsed time; acceptance percentage alone is insufficient.
