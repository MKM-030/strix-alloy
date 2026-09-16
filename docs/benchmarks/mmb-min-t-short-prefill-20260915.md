# mmb_min_t short-prefill experiment — negative (2026-09-15)

Follow-up to `prefill-vs-depth-20260915.md`, which found short prompts run at ~40% of the deep-prompt
prefill rate (407 t/s @256 vs 1021 @16k). The suspected cause was the fork's MMB fast-path threshold
`mmb_min_t() = 512` (`ggml/src/ggml-cuda/mmb.cu`): any batch with `T < 512` skips MMB and falls back
to the stock `mmvq`/`mmvf` kernels, which is exactly the short-prompt regime.

## Experiment

Env-gated `mmb_min_t()` (`GGML_MMB_MIN_T`), one binary, A/B at `-c 8192 -b/-ub 16384`, gen 16, 3 reps,
median of reps 1–2, WSL down. Arm B sets `GGML_MMB_MIN_T=128` (smallest size measured is 128, so the
whole sweep is at or above the new threshold); arm A leaves it unset (512).

| prompt tokens | A: threshold 512 | B: threshold 128 | Δ |
| ---: | ---: | ---: | ---: |
| 128 | 267.6 | 259.2 | −3% |
| 256 | 389.0 | 380.7 | −2% |
| 384 | 453.3 | 444.0 | −2% |
| 512 | 516.4 | 541.3 | +5% |
| 768 | 632.3 | 617.2 | −2% |
| 1024 | 698.6 | 694.5 | −1% |

**Negative — no material change at any size.** Lowering the MMB threshold does not rescue short-prompt
prefill.

## What that means

The short-prompt slowness is **not** the `mmb_min_t` cliff. It is per-request / small-batch fixed
overhead: at 128 tokens the whole prompt is one tiny batch, and the prefill rate is dominated by
launch, scheduling and graph-replay overhead rather than by which matmul kernel runs. The monotone rise
from 407 → 1021 t/s over the range is a batch-efficiency curve, not a single threshold being crossed
(the knee is spread across the range, not sharp at 512).

So the item is **closed as not-actionable via this knob**. A real improvement for the small-prompt
regime would need to reduce fixed per-request cost (fewer kernel launches, longer-lived graphs, or
batching concurrent requests), not to change a matmul threshold.

## Reverted

The experiment is fully reverted: `git checkout` in `~/strix-llama` (tree clean at `891a923a`),
`ggml-hip.dll` restored from `bin/ggml-hip-baseline.dll` and rebuilt, and a confirmation run reproduced
the baseline exactly (**28.77 vs 28.75 t/s**, median, 8192-token prompt).

## Artifacts

`kernel-work/prefill-shape-sweep.ps1`; `results/pfs-mmbt-128.{json,log}`,
`results/pfs-mmbt-base.{json,log}`, `results/dbl-confirm-restored.json`; `results/build-mmbt.log`.
