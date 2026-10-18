# Multiple configured MTP drafts — 11 October 2026

**Recommendation: qualify the new native 0.18.0 engine before adding another drafter.** Diversified drafts can increase the chance that a target continuation appears among candidates. That alone does not make them faster: the engine must select or verify those alternatives, preserve target semantics and state, and pay their complete cost. The current public Halogen interface supplies no multi-head/tree verifier for one request.

This is source/research work only. No WSL, Docker, accelerator, serving API, lifecycle, installation or continuation-state operation was performed. Existing trials were not repeated.

## What greedy and sampled drafting change

For a fixed greedy target, the accepted draft must equal the target's argmax at each position, conditioned on the already accepted prefix. Verification stops at the first mismatch; a plausible alternative word still fails. Several identical deterministic copies produce the same chain. Sampling one copy can expose a different candidate, but can also replace a correct argmax draft with a wrong one. A union of candidates has potential value only with a usable selector or a verifier that actually evaluates the branches.

For a sampled target distribution `p` and a draft distribution `q`, exact single-chain speculative sampling accepts a proposed token `x` with probability `min(1,p(x)/q(x))`; rejection samples from normalized `max(p-q,0)`. This is not equality between two independently sampled outputs. Its expected one-position acceptance is `sum_x min(p(x),q(x))`; identical distributions can achieve acceptance one. Temperature or filters can change distribution overlap, with no universal direction. Changing the **target** temperature to raise acceptance changes the requested generation. Selecting among multiple sampled proposals also changes the proposal law, which the acceptance/correction algorithm must account for. [Chen et al., Algorithm 2 and §4.2](https://arxiv.org/html/2302.01318v1).

For a continuing greedy linear round with `m` proposals, expected committed length is `1 + sum_j P(first j drafts match)`. Actual EOS, caps and fallback require actual counts. More accepted/proposed tokens is therefore not itself a speed result. Optimize committed tokens divided by full draft, verification, state resolution, transport and contention time.

## What 0.18.0 supports

The [official flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md) describe one built-in MTP head, greedy linear depth 2/3, and greedy-only prompt lookup. A lookup chain must open with the head's speculative choice; that opening is still target-verified. Sampled requests use the head alone. `HALOGEN_MTP_HEAD` selects the required head for a GGUF trunk, rather than registering several heads. Adaptive backoff already exists. The earlier binary-proven single-token sampled dispatch is specifically a [0.16.2 result](halogen-sampled-mtp-depth-20261004.md), not an inspected 0.18.0 limit.

Since 0.17.0, two **different conversations** can draft and verify as a batch. The 0.18.0 session forks retain conversation resume state. Neither feature describes competing speculative branches within one request. NPU models serve separate inference tasks; the public interface does not connect them as Flash drafters. [Official changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md), [NPU documentation](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/NPU.md). This is a statement about the supported contract; no new engine binary was inspected here.

Multiple trained heads and branch verification are real research routes. [Medusa](https://arxiv.org/html/2401.10774v3) adds trained heads plus tree attention; its typical-acceptance option is not a proof of preserving the target sampling distribution. [EAGLE-2](https://arxiv.org/html/2406.16858v1) allocates a dynamic draft tree using draft confidence. Halogen integration would need branch-aware attention, position/recurrent state, selected-prefix commit and rejection handling. The retained custom consumer accepts one linear chain of at most three IDs; external sidecars do not add those capabilities.

## What the retained evidence already rules out

| Completed route | Result and disposition |
|---|---|
| Second full GPU proposer | Opening-equality selection retained 22/44 leading labels, equal to stock, at 26.05545 ms/round component cost. Hindsight union 28/44 is not a causal selector. Keep closed. [Study](halogen-multi-draft-feasibility-20261006.md). |
| DFlash query slots 3→7, still proposing K3 | Useful prefix 0.625→0.6875, one improving anchor of 32; proposal cost 35.63568→37.12534 ms. Shadow agreement only. Keep the tested route closed. [Paired screen](halogen-dflash-paired-width-shadow-20261010.md). |
| Full-vocabulary native head | Matched 0.17.2 cohort regressed decode about 6%; no gain. [Result](../benchmarks/halogen0172-native-full-vocab-20261008.md). |
| Token-hash neural skip selector / PLD64 | Held-out selector failed its controls; live PLD64 made zero tail substitutions. No unchanged rerun. [Selector](halogen0173-selector-pilot-20261009.md), [PLD64](halogen0174-causal-pld64-20261010.md). |

The natural16K 0.17.4 reference has a qualified whole-request QPC median of **12.8247304 s** and **180/399 = 45.1128% combined API MTP+PLD acceptance**. Prefill/Decode phase rates remain unqualified, and neural-only acceptance was not isolated. The separate short-task pilot records neural 978/1,412 and PLD 237/288, including censored outcomes, whereas its full-request API total is 1,219/1,704. These scopes and workloads cannot be interchanged. [Natural16K reference](../benchmarks/halogen0174-natural16k-qpc-20261010.md), [pilot accounting](halogen0173-selector-pilot-20261009.md).

## Small next test

The untested mechanism with the strongest present benefit case is **the official native drafted-decode improvement introduced in 0.17.5 and carried by 0.18.0**. This inference rests on a new implementation with unchanged checkpoints, not a predicted acceptance gain. The [update receipt](halogen-official-update-resume-20261011.md) pins 0.18.0 manifest `sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9`.

After root qualifies the new image and its phase mapping, run one fresh native 0.17.4 → 0.18.0 → 0.17.4 comparison: the frozen natural 16,384-input/128-output request, one excluded warmup and three measured calls per window, unchanged checkpoint/tokenizer, temperature 0, Cache Off, Thinking Off, fixed MTP2/PLD3,3 and existing reserves. Retain exact greedy output, finish/token counts, direct RAW phase times, QPC wall time and combined counters. Require a benefit beyond stock-bookend drift. Report neural and PLD counters separately only when their current-version attribution is independently qualified; do not put a new observer in the speed bracket merely to rename the combined ratio. Stop after this finite comparison if it supplies no gain. No private 0.17.4 patch should be transplanted into the new engine without current-version verification.
