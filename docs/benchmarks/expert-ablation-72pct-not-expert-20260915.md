# Expert ablation: 72% of a decode round is NOT expert cost — and ~23 ms/round is not weight bandwidth at all (2026-09-15)

Codex proposed a routed-output replay harness (60–90 min) to measure how much of a round the expert path
costs. I got the answer with a **one-flag ablation** instead: `--override-kv
qwen4exp.expert_used_count=int:K` changes top-k at load, leaving everything else identical.

**This is a reduced-model ablation.** Fewer experts = a different model; acceptance and output quality
change. Only the *timing* delta is meaningful, and it is labelled as such.

## Measured (warm, width 2, 8k)

| top-k | target ms/round | notes |
| ---: | ---: | --- |
| 10 | **49.27** | baseline |
| 5 | — | **model collapsed** (acceptance 2/6, 3 rounds/req) — excluded |
| 3 | **39.60** | valid |

k=5 is unusable: with 5 of 512 experts the model degenerated to near-garbage, so its round mix is not
comparable. Only k=10 vs k=3 is a valid pair. (First attempt also used cold page cache and was discarded —
k=10 read 62.81 ms instead of 49.27.)

## Corrected arithmetic

My first pass used the **single-row** expert delta (1.327 − 0.398 = 0.929 GB). Wrong: at width 2 the
target verifies **three rows**, each selecting its own experts, so the round's expert payload is the
**union across rows**.

```
per-expert-layer bytes = 1.327 GB / (10 experts × 48 layers) = 2.765 MB
U(k,w) = 512·(1 − (1 − k/512)^w):
  k=10, w=3 → 29.4 experts/layer → 3.904 GB/round
  k= 3, w=3 →  8.9 experts/layer → 1.187 GB/round
  delta = 2.716 GB removed for 9.67 ms saved
```

## Result

```
target_ms/round = 35.4 + 3.56 × expert_GB
```

| component | value |
| --- | ---: |
| **expert-dependent** at k=10 | **13.9 ms (28% of the round)** |
| **k-independent remainder** | **35.4 ms (72% of the round)** |

Of the fixed 35.4 ms, the dense weight bytes (2.927 GB) would take **12.4 ms** at the measured 235.7 GB/s
ceiling. So:

> **~23 ms per round is not explained by weight bandwidth at all** — activations, attention traffic, norms,
> the LM head, and non-weight work.

## The union model overestimates, which strengthens the conclusion

`1/3.56 ms/GB` implies an expert-path bandwidth of **281 GB/s — above the 235.7 GB/s streaming ceiling I
measured.** That is impossible, so the union figure must be too high: real routing overlaps **more** than
uniform-independent predicts, and/or the kernel reuses a distinct expert across rows. Either way the true
expert payload is **smaller** than 3.904 GB, so the true expert share is **below 28%**.

## What this changes — the plan inverts

| prior | now |
| --- | --- |
| expert path is the prime suspect (byte model said 31% of payload; Codex ranked replay #3 predicting 20–50%) | **expert path is ≤28% of the round, likely less.** Making it *entirely free* would gain ≤28%. |
| "find the uniform 45% loss" | still true, but the mass is **not** in the experts. It is in the **72% k-independent part**. |
| Codex item #3 (routed-output replay) | **deprioritised** — the ablation already bounded it at ≤28%, and replay cannot exceed what removal measured. |
| Codex item #H (hyper-connections + **target LM projection**) | **now the top candidate.** The LM head is Q6_K `[2560, 248320]` = 521 MB; if verification needs logits at all 3 rows, that is ~1.56 GB/round ≈ **6.6 ms at ceiling** — a single, concrete, checkable cost inside the unexplained 23 ms. |

**Note the two independent lines agreeing:** the width fit gave a k-independent part of **20.9 ms**; this
ablation gives **35.4 ms**. Different two-point solves from different experiments, same qualitative shape —
**most of a round does not scale with rows or with k.** Both point at the same place: fixed per-round work.

## What I would measure next (cheap → expensive)

1. **Is the LM head read 1× or 3× per round?** Direct: count rows requesting logits, or watch the projection
   in the round ledger. If 3×, that is ~6.6 ms/round of avoidable traffic (only the accepted suffix needs
   logits) — a concrete, implementable win.
2. **Hyper-connection cost** (Codex item #H): replay the mixed stream + injection at selected layers.
3. **Activation/attention traffic accounting** at width 2–3 (Codex item #E) — the remaining unexplained
   mass.

## Honest limits

- One prompt (8k), one width (2), two k values, single reps after a warm pass. The two-point solve is fragile
  to noise; the *qualitative* split (large k-independent part) is robust because it shows up in two
  independent experiments.
- k=3 is a reduced model, so its round mix (attention/activation behaviour) may differ slightly from k=10
  beyond the expert bytes — a confound that would make the expert share look *bigger*, not smaller.
- Expert-union statistics would replace the assumed `U(k,w)`. Since the assumption is provably too high,
  measuring it can only lower the expert share further.
