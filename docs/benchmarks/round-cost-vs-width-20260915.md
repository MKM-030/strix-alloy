# Round cost vs verification width: the wide-verify penalty is *proportional*, and uniform 55% efficiency is the real finding (2026-09-15)

Cheap bound obtained with **no new code** — one server, same 8k prompt, `n-max` 1/2/3, using the round
accounting added earlier. This bounds the expert/attention cost that Codex's routed-output replay (60–90 min
of hook work) was proposed to measure.

## Measured

| n-max | verified rows | yield/round | target ms/round |
| ---: | ---: | ---: | ---: |
| 1 | 2.00 | 1.53 | 46.16 |
| 2 | 3.00 | 1.83 | 54.80 |
| 3 | 3.99 | 2.40 | 70.15 |

At n-max *k* the drafter proposes *k* tokens and the target verifies *k+1* rows (k drafts + one resample),
so the x-axis is **rows**.

## Fit

```
target_ms/round = 20.93 + 12.05 × verified_rows
```

- **width-independent part `c0 = 20.9 ms`** — 37% of a 3-row round
- **marginal verified row `c1 = 12.0 ms`**

**Independent consistency check:** the fit extrapolated to 1 row gives **33.0 ms**; serial decode was
measured separately at **~35 ms/token**. **6% agreement outside the fitted range**, which is real
validation that the two-term model is right and not a curve fitted through three points.

**The first row costs ~33 ms; each additional row costs ~12 ms — 2.7× cheaper.** Dense weights (2.927 GB)
are read once per round regardless of width, so they are paid by the *first* row; marginal rows only carry
the extra expert/attention work.

## The important result: byte-model efficiency is FLAT across width

Cross-checking against the union model — union `U(w) = 512·(1 − (1 − 10/512)^w)`, payload
`W = 2.927 + 1.327·U/10` GB, bandwidth 220 GB/s:

| rows | union | payload | ideal | fitted | **efficiency** |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10.0 | 4.25 GB | 19.3 ms | 33.0 ms | **59%** |
| 2 | 19.8 | 5.56 GB | 25.3 ms | 45.0 ms | **56%** |
| 3 | 29.4 | 6.83 GB | 31.0 ms | 57.1 ms | **54%** |
| 4 | 38.8 | 8.08 GB | 36.7 ms | 69.1 ms | **53%** |

**Efficiency is 53–59% at every width.** Two conclusions follow, and they change the plan:

1. **The wide-verify penalty is *proportional*, not disproportionate.** Expert-union saturation is behaving
   essentially as theory predicts. There is **no "wide verify is disproportionately expensive" anomaly** —
   the earlier framing (including mine, from the n-max sweep) overstated it.
2. **The real problem is a uniform ~55% bandwidth efficiency at ALL widths.** We are ~1.8× off the byte
   ceiling everywhere, not at width specifically. That reframes the target: it is not "make 3 rows cheaper
   than 3 rows" (they already are, proportionally) but **"find the uniform 45% we are losing."**

Caveat, stated because it strengthens rather than weakens the point: the union model assumes near-worst-case
independence (union 29.4 of a max 30 at 3 rows). If real routing overlaps *more*, the true payload is
*smaller*, the ideal time is *lower*, and the measured efficiency is **even worse than 53–59%**. So 55% is an
upper bound.

## What this means for Codex's ranked plan

| Codex item | revised status |
| --- | --- |
| #3 routed-output replay (predicted 20–50%) | **still the right next measurement, now with a sharper question.** It does not need to tell us "is expert work big" — it needs to tell us **whether the lost 45% is inside expert evaluation or outside it**. That is a narrower, more decisive ask. |
| #4 index replay | **closed** by the depth result (round cost flat across the dense→sparse transition) |
| #6 "is wide verify fundamentally expensive?" | **answered**: proportionally so, consistent with the union model; the anomaly is uniform inefficiency, not width scaling |
| acceptance as the multiplier | unchanged |

**Also implied:** because efficiency is flat, an optimisation that fixes the uniform loss benefits *all*
widths including serial decode (where we separately measured 55–66% of ceiling — the same number). One
cause, three symptoms.

## Honest limits

- Single sample per width, one prompt (8k). The fit's internal consistency (33.0 vs 35 ms) is the strongest
  evidence; a repeat sweep would tighten `c0`/`c1`.
- `target_ms/round` covers the **target phase only** — draft is the other ~16%. The fitted model is about the
  target rounds, which is what we want.
- Union is *assumed*, not measured. Codex's expert-union statistics would replace the strongest assumption in
  the cross-check.

## Next (unchanged, but sharper)

1. **Expert-union statistics** (cheap: record selected-expert IDs, count distinct per layer per round) —
   replaces the assumed union and turns the efficiency figure from bounded to exact.
2. **Routed-output replay** — with the question now "is the uniform 45% in the expert path or not?"
