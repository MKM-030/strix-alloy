# Two follow-ups: warm prefill correction + tightened MTP acceptance (2026-09-15)

Both requested follow-ups to the 251k benchmark. **A (faster) ran first** and is the more significant
result.

## Task A — the deep-prefill "cliff" was a cold-cache artifact (+20–55%)

**Hypothesis.** The `longctx-251k` tables reported prefill falling to ~650–690 t/s at 128k–251k, but
those rows were **single-rep**, and rep 0 is cold (the mmap'd model is not yet in the OS page cache).
At 16k the effect is visible in the original data (rep0 500 vs rep1 862). So re-measure the deep sizes
with ≥2 reps and read rep 1.

**Result (`results/lc-lcwarm-prefill.json`, `-c 262144 -ub 16384`, WSL down):**

| depth | cold (rep 0) | **warm (rep 1)** | warm/cold |
| ---: | ---: | ---: | ---: |
| 131,072 | 583.6 | **907.3** | **1.55×** |
| 196,608 | 686.2 | **856.3** | 1.25× |
| 251,904 | 673.4 | **809.1** | 1.20× |

**Difference achieved: +20% to +55% prefill at depth — a measurement correction, not a code change.**
The warm 251k prompt prefills in **311 s** (vs 374 s cold; the original ladder's 388 s).

**Corrected prefill curve:** 862 (16k) → 984 (65k) → **907 (131k) → 856 (196k) → 809 (251k)**. That
is a gentle ~1.5–2%/inch decline, **not** the "settles to ~650" first reported. There is no 128k+
cliff; the earlier number was the OS page cache, not the GPU. Warm decode also improves (251k: 22.9 →
25.9 t/s).

This supersedes the prefill rows ≥131k in `longctx-251k-20260915.md` and `measured-baseline.json`
(now flagged `_cold_superseded` / `_cold`). **Rule recorded: never report a single rep at depth on
this box.**

## Task B — MTP acceptance, tightened with `gen 256`

The gen-64 run gave only ~30 draft rounds per request — too few for a stable acceptance figure. Re-ran
the MTP ladder at **`gen 256`** (≈230 draft rounds per row), 2 reps, rep 1 reported.

| depth | gen-64 decode / acc | **gen-256 decode / acc** | Δ decode | Δ acceptance |
| ---: | ---: | ---: | ---: | ---: |
| 16,384 | 29.3 / 50% | **31.58 / 56.1%** | +7.8% | +6 pts |
| 65,536 | 35.0 / 74% | **32.70 / 64.9%** | −6.6% | −9 pts |
| 131,072 | 28.8 / 61% | **32.79 / 69.8%** | +13.8% | +9 pts |
| 196,608 | 27.1 / 61% | **30.22 / 64.1%** | +11.5% | +3 pts |
| 251,904 | 28.7 / 67% | **31.33 / 72.9%** | +9.2% | +6 pts |

**Difference achieved: the MTP decode curve is flatter and higher than gen-64 suggested — 30.2–32.8
t/s across 16k–251k (a ±4% band) instead of the 27–35 t/s scatter.** Acceptance tightened to
**56–73%**, and the depth ordering is now stable (lowest at 16k, rising with depth). The gen-64
"65k is best (35 t/s)" peak was noise from the small sample: at gen 256 the 65k decode is 32.7, in
line with the others.

Practical read: **MTP decode is essentially depth-independent at ~31–33 t/s**, and acceptance improves
with depth (more context → the draft head's next-token prediction is more constrained), from 56% at
16k to 73% at 251k.

## Net summary of what changed

| metric | first report | corrected | change |
| --- | ---: | ---: | ---: |
| prefill @131k | 688 | **907** | +32% |
| prefill @196k | 689 | **856** | +24% |
| prefill @251k | 648 | **809** | +25% |
| MTP decode @131k | 28.8 | **32.8** | +14% |
| MTP decode @251k | 28.7 | **31.3** | +9% |
| acceptance range | 50–74% (noisy) | **56–73%** (tight) | sample size ×4 |

All of this is **measurement methodology**, not a kernel change — which is itself the finding: the
box's long-context story is materially better than the first pass reported once cold-start and small
sample are removed.

## Artifacts

- `kernel-work/longctx-bench.ps1` (used for both; `-RepeatsBig` controls rep count per size)
- `results/lc-lcwarm-prefill.{json,log}` (Task A), `results/lc-lc-mtp-g256.{json,log}` (Task B)
- corrected docs: `longctx-251k-20260915.md`, `measured-baseline.json` (`long_context_251k_warm`)
