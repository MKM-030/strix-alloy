# Round cost vs depth: flat — and that closes the indexer/attention line (2026-09-15)

Codex's priority-1 ask was: *"the distinguishing measurement is `G` and `C = V+D+H` per round, stratified by
context and actual width"* — because three different explanations for the depth penalty predict different
outcomes (round cost constant with falling yield ⇒ acceptance; round cost rising and removed by index
replay ⇒ indexer; round cost rising despite index replay ⇒ something else).

Measured directly, two independent runs, `--spec-draft-n-max 2`, ub 2048:

| run | prompt | rounds | **width** (proposed/round) | **yield** (emitted/round) | **target ms/round** | target ms/emitted token | prefix survival (pos 1, 2) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1k | 186 | 1.99 | 2.06 | **59.32** | 28.73 | 0.618, 0.435 |
| 1 | 8k | 67 | 2.00 | 1.81 | **57.38** | 31.78 | 0.552, 0.239 |
| 1 | 16k | 174 | 1.99 | 2.21 | **54.03** | 24.48 | 0.736, 0.466 |
| 2 | 1k | 122 | 2.00 | 2.10 | **54.94** | 26.18 | 0.631, 0.451 |
| 2 | 8k | 67 | 2.00 | 1.81 | **55.50** | 30.73 | 0.552, 0.239 |
| 2 | 16k | 118 | 1.99 | 2.17 | **55.85** | 25.75 | 0.737, 0.424 |

## Finding 1: round cost does not grow with depth

**~54–59 ms per round, flat across a 16× context range**, in both runs. (If anything it drifts slightly
*down* at 16k.)

**The range spans the dense→sparse transition.** The block-selection gate is
`n_kv > indexer_top_k + ratio − 1` (≈2051 with `top_k = 2048`, ratio 4), so:

- **1k prompt → dense attention** (block selection OFF)
- **8k / 16k prompt → sparse block-selection path ON**

Round cost is the same on both sides.

**Consequence — this closes the indexer/attention line.** Per Codex's own decision table, "target round
cost rises, and exact index replay removes the rise" would implicate the indexer. Round cost *does not
rise*, so **indexer scoring/selection and the sparse attention path are not adding a measurable
depth-dependent per-round cost.** Codex ranked index replay as priority 4 (60–90 min of hook work); **that
budget is now unnecessary for this question.** The QSA design is doing its job: sparse at 16k costs what
dense costs at 1k.

## Finding 2: the marginal second draft row costs far less than a full row

At width 2.0 the round costs ~55 ms and yields ~2.0 tokens. Our measured serial (width 1) decode is
~35 ms/token. So the second row adds roughly **~20 ms** — but it is what lifts yield from 1.0 to ~2.0.
That is why MTP pays, and it is consistent with the clean A/B (+18.5% at 1k, +5.6% at 8k): the row is
cheap, the *acceptance* of that row is what varies.

## Finding 3 — caveat that limits what I can conclude about depth

**Yield varies with prompt, not cleanly with depth** — 2.10 / 1.81 / 2.17. The 8k window is consistently
the worst in both runs (identical 67 rounds, yield 1.81, survival 0.552/0.239), which is a property of
**that corpus segment**, not of 8k depth.

`fnbench.py` samples *different text* at each size, so cross-size yield differences are confounded with
prompt difficulty. **I therefore cannot claim "acceptance falls with depth" from this experiment** — and
that is a correction to my own earlier framing, where I read the n-max sweep's acceptance decline as a
depth property. To attribute yield to depth you must hold the *text* fixed and vary only the prefix
length, which this harness does not do.

What I *can* say is the part that matters and is unaffected: **round cost is flat with depth.**

## What this changes

| candidate | status |
| --- | --- |
| indexer / sparse-attention optimisation | **deprioritised** — no measurable depth-dependent round cost |
| "something else grows with depth" | **not supported** — nothing in the round grows |
| acceptance as the multiplier | **still the lever**, but now must be measured with fixed text |
| marginal draft row cost | **measured**: ~20 ms for the 2nd row at ~55 ms/round |

Codex's remaining ranked items are unchanged: MoE routed-output replay (its largest predicted candidate,
20–50%), then GDN/attention-core replay, then one justified implementation change.

## Next
1. **MoE routed-output replay** — Codex's priority 3 and its largest candidate. Hook: the routed
   `ffn_moe_out` before the shared-expert add; substitute recorded output, keep shared expert + HC running.
2. **Fixed-text depth sweep** — same corpus prefix extended 1k→16k, so yield-vs-depth is not confounded
   with prompt identity. Cheap, and it makes Finding 3 conclusive rather than caveated.
