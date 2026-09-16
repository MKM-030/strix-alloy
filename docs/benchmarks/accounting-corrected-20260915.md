# Corrected accounting: the shortfall is not a uniform 37% (2026-09-15)

Codex review correction, accepted. My earlier statement conflated **MTP** decode (35.5 t/s) with
**serial** decode (29.9 t/s) when computing "we run 35 t/s serial = 63% of the ceiling". Serial is
~30 t/s, so that number was wrong. Corrected below. Also applies the warm re-measure, which changes
the depth story.

## What was wrong

| claim | problem |
| --- | --- |
| "we run 35 t/s serial = 63% of the 235.7 GB/s ceiling" | 35.5 t/s is **MTP** (n-max 2). Serial is **29.9** t/s. |
| "the loss is uniform" | width-uniform **and** depth-declining are both true and were being merged into one word |
| "37% shortfall" | that is `100 − 63`, and 63 came from the wrong throughput |

## Corrected serial decode, weight-payload throughput

`4.219 GB/token` (exact GGUF census, weights only) ÷ measured serial ms/token:

| depth | serial t/s | ms/token | effective weight-payload GB/s | % of 235.7 |
| ---: | ---: | ---: | ---: | ---: |
| 1,024 | 29.9 | 33.44 | 126.2 | **53.5%** |
| 8,192 | 28.6 | 34.97 | 120.6 | 51.2% |
| 65,536 | 28.5 | 35.09 | 120.2 | 51.0% |
| 131,072 | 26.9 | 37.17 | 113.5 | 48.2% |
| 196,608 | 26.5 | 37.74 | 111.8 | 47.4% |
| 251,904 | **25.9** | 38.61 | 109.3 | **46.4%** |

Two corrections to the corrections:

1. **The 251k serial figure is 25.9, not 23.4.** 23.4 was the **cold** single-rep value; the warm
   re-measure gives 25.9. So the depth decline is **29.9 → 25.9 = −13%**, not the −22% Codex
   calculated from my cold number.
2. **At depth the denominator is wrong.** `4.219 GB` is the *weight* read set. At depth the real read
   set also includes KV (12 full-attn layers × selected keys) and the QSA indexer's pooled-key scan,
   both of which grow with context. So the true bytes/token at 251k is **> 4.219 GB**, and the true
   effective bandwidth at depth is **higher** than the 46.4% above. The table is a lower bound on
   efficiency at depth.

## What survives, restated correctly

- **Width-uniform.** At a fixed depth, byte efficiency is flat (~53–59%) across verify widths
  (serial / n-max 1 / n-max 2). That measurement stands — it is a *width* statement.
- **Depth-declining, gently.** Serial decode falls 29.9 → 25.9 t/s over a 246× context increase
  (1k → 251k), i.e. −13%. Real, moderate, and worth explaining — but not a collapse.
- **Not "uniform 37%".** The honest label is **"substantial unexplained effective-bandwidth loss:
  ~53% of peak at shallow depth, ~46%+ (lower bound) at extreme depth."**
- **The expert ablation identifies work that does not scale with expert count, not that work's
  composition.** Its intercept says "72% of the round is k-independent"; it does **not** say that 72%
  is one uniformly-inefficient thing. Dropping that inference.

## Consequence for the plan

The single "37% to recover" framing is retired. What replaces it:

1. **A depth effect** (53.5% → 46.4%, and the denominator is incomplete) — this is what the
   capacity/occupied-depth experiments target.
2. **A shallow-depth efficiency ceiling** (~53% of peak) — this is what the shape-matched operator
   benchmark targets (is it access pattern or kernel execution?).

Neither is assumed recoverable. Both are now separately measurable.

## Artifacts

Corrected numbers folded into `measured-baseline.json` (`serial_effective_bandwidth`) and the Codex
follow-up prompt. Raw: `results/lc-lcwarm-prefill.json` (warm serial decode at depth),
`results/dbl-*.json` (shallow serial).
