# Two MMVQ candidates tested on gfx1151 — both negatives (2026-09-15)

The handover's B2 named a "source-guided single-APU HIP candidate queue". Its two most on-point
MMVQ items are now **implemented, built, and A/B-measured on this box**. Both are negative, and one of
them explains why: gfx1151 is on the RDNA2 table, and that is already the best choice.

## Method

Kernel changes affect the **target** forward pass, so the A/B measures **serial decode** (no drafter),
where `decode_tps` is purely the target's cost per token. `kernel-work/decode-baseline.ps1`, PROJFIX,
`-c 32768 -b/-ub 2048`, prompt 8192, gen 256, 5 reps, median of reps 1–4 (rep 0 is cold). Baseline
spread was ±1% (28.34–28.97), so a >5% effect is clearly separable from noise.

**Baseline (upstream, unmodified): 28.75 t/s median → 34.78 ms/token.**

## Candidate 1 — "small-K" MMVQ for RDNA3.5 (SixVolts `mmvq_rdna4_small_k` class)

Upstream disables the small-K rows-per-block mode on **all** RDNA (`GGML_CUDA_CC_IS_RDNA(cc)` →
`use = false` in `should_use_small_k`). SixVolts reports it is a large win on RDNA4. Env-gated the
enable-on-RDNA3.5 path in `mmvq.cu` and A/B'd on one binary
(`GGML_MMVQ_RDNA35_SMALLK=1`).

| arm | decode median | ms/token |
| --- | ---: | ---: |
| upstream | 28.83 t/s | 34.69 |
| small-K enabled | 28.73 t/s | 34.81 |

**Negative — within noise.** And the source says why: `calc_rows_per_block()` only honours `small_k`
for the GENERIC/GCN/TURING/GB10 tables. gfx1151 uses the **RDNA2** table, whose `calc_nwarps()` returns
`nwarps = 1` for essentially every `ncols_dst==1` type — so `nwarps > 1` is false and the small-K
condition can never trigger. The patch was inert by construction on this arch.

## Candidate 2 — borrow the RDNA3.0 parameter table (nwarps = 8)

The obvious follow-up: gfx1151 gets `nwarps = 1` from the RDNA2 table, while RDNA3.0 returns `nwarps = 8`
for IQ4_NL/Q8_0 and RDNA4 returns 8 for many more types. So route gfx1151 to the **RDNA3.0** table
(both the `__device__` and host selectors, kept consistent so `__launch_bounds__` and the launch
geometry agree), rebuild, measure.

| arm | decode median | ms/token | vs baseline |
| --- | ---: | ---: | ---: |
| baseline (RDNA2 table) | 28.75 t/s | 34.78 | — |
| **RDNA3.0 table on gfx1151** | **22.81 t/s** | 43.84 | **−21%** |

**Strongly negative.** Widening the K split to 8 warps per output row hurts gfx1151. The RDNA2 table's
`nwarps = 1` is not a stale default here — it is the faster configuration for this part.

## What this means

- **The stock MMVQ configuration is already tuned for gfx1151.** Two plausible upstream-sourced
  "improvements" both fail, one by being inert and one by being 21% slower. There is no cheap
  parameter-table win to be had; a real gain would need a gfx1151-specific kernel, not a table switch.
- Combined with `decode-byte-accounting-20260915.md` (the loss is uniform across the whole 4.22 GB
  read set) and the closed indexer/PLE depth lines, the picture is consistent: **this box's decode is
  at its practical limit for the current kernels.** The remaining headroom is a research project
  (a new quantized-matvec kernel that beats the RDNA2-tuned one), not a tuning pass.
- Both experiments were reverted; the tree and the baseline DLL are clean. See the "reverted" note in
  `final-results.md` and the current fork hygiene check.

## Artifacts

- `kernel-work/decode-baseline.ps1`, `build-target.bat`, `results/build-*.log`
- `results/dbl-base-serial.json`, `dbl-armA-upstream.json`, `dbl-armB-smallk.json`, `dbl-armC-rdna3table.json`,
  `dbl-*.log`
- DLL snapshots: `bin/ggml-hip-baseline.dll` (upstream), `bin/ggml-hip.dll` (same, restored)
