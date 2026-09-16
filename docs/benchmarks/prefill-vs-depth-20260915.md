# Prefill vs prompt depth: the "gap" is a depth/shape effect, and short prompts are slow (2026-09-15)

## Measurement (WSL fully down — required; see note)

`kernel-work/prefill-shape-sweep.ps1`, PROJFIX, max-prefill shape (`-b/-ub 16384`, no drafter,
`-c 32768`), gen 16, 3 reps, median of reps 1–2 (rep 0 cold). WSL `--shutdown` beforehand; the runbook
rule that WSL must be down for native runs is load-bearing (vmmemWSL memory starves the prefill phase —
it already corrupted three prior runs).

| prompt tokens | prefill t/s |
| ---: | ---: |
| 256 | **407** |
| 1024 | **690** |
| 4096 | 844 |
| 8192 | 984 |
| 16384 | **1021** |

## What this says

1. **Prefill throughput rises monotonically with prompt depth** on this box: 407 → 1021 t/s from 256 to
   16384 tokens. So a single "prefill t/s" figure is only meaningful with its depth attached.
2. **The published comparison was depth-mismatched.** ilintar's 1204 is quoted at ~0 depth on a
   16k-token batch; our 1057/1021 is at 16k tokens. At *matched* 16k our number is ~1021–1057 vs their
   1086 @40k — i.e. the real gap is on the order of ~6%, not 14–16%. The larger part of the apparent
   gap was our own @16k vs their @0 framing.
3. **Short prompts are slow, and that is a real, separate finding.** At 256 tokens we get 407 t/s. The
   shape is consistent with the MMB fast path's entry threshold: `mmb_min_t() = 512` in
   `ggml/src/ggml-cuda/mmb.cu` gates `ggml_cuda_mmb_supported_mm` / `_mmid`, so any batch with
   `T < 512` skips MMB entirely and falls back to the stock `mmvq`/`mmvf` kernels. Small prefills and
   small batched requests land under it.

## Consequence

- **Do not quote a single prefill number.** Report `(prefill t/s @ depth)`; the depth-dependence is
  ~2.5× across the range we measured.
- **The remaining prefill headroom vs ilintar is small** (~6% at matched depth) and their residual
  advantage is most likely the retained-PM4 command-list runtime (per `ilintar-rebase-result-20260915.md`),
  which is a ROCm userspace change we cannot use — not a kernel we can port.
- **The actionable prefill item is the short-prompt regime**, addressed by the `mmb_min_t` experiment
  (`mmb-min-t-short-prefill-20260915.md`). This matters because interactive/chat workloads frequently
  use prompts of a few hundred tokens, exactly where we are slowest.

## Caveat

The 256-token wall time is sub-millisecond, so the *absolute* cost is tiny; the value of the finding is
(i) it explains the misleading comparison and (ii) it identifies a concrete, cheap knob for the
small-prompt regime. The monotone rise past 512 also means the short-prompt slowness is not *only* the
min_t cliff — batch efficiency at small T contributes — so lowering the threshold is necessary but may
not be sufficient.

## Artifacts

`kernel-work/prefill-shape-sweep.ps1`; `kernel-work/results/pfs-prefill-ub16384.{json,log}`;
this doc.
