# shapebench confound check: the epilogue was the artifact — ALU-bound claim RETRACTED (2026-09-16)

Codex asked me to check `shapebench` for a per-block epilogue confound before drawing conclusions from
the B/D gap. **The confound was real, it affected more than B, and correcting it retracts my previous
headline.**

## The confound (Codex's suspicion, confirmed)

Every shapebench kernel ended with a shared-memory tree reduction plus **one `atomicAdd` into a single
global scalar**. Variant B launched up to 4096 blocks *per buffer* while D capped at 256, so B performed
16× more contended atomics against the same counter — a benchmark artifact that production does **not**
have (real `mmvq` writes per-row results, no atomic).

Test: same kernel, same grid, same loads — only the epilogue changes (contending `atomicAdd` vs writing
the partial to a per-block slot).

| variant (12 GB, cache-proof) | contending epilogue | **fair epilogue** |
| --- | ---: | ---: |
| B fragmented, big grid | 87.2% | **100.9%** |
| D fragmented, small grid | 97.5% | 100.2% |
| **I dp4a GEMV** | **79.5%** | **99.7%** |
| F 32× float FMA GEMV | 48.5% | 48.1% |

Measured epilogue cost for B: **~8.0 ms** on 12 GB, consistent across runs.

So **B's "short-loop" deficit was entirely the contended atomic**, not memory behaviour and not loop
depth. Codex's caution was correct.

## What this retracts

My previous doc (`decode-alu-bound-dp4a-20260916.md`) concluded **"decode is ALU-issue-bound at the
per-weight level, and dp4a recovers most of it (80.8% ceiling → ~45 t/s)."** That conclusion is
**withdrawn**, for two reasons:

1. **The 80.8% was my benchmark's epilogue, not the algorithm.** With a fair epilogue, dp4a reaches
   **100.8–101.0% of contiguous bandwidth** at the cache-proof 24 GB (two stable runs).
2. Therefore **the dequant arithmetic is not the limiter** when expressed the way production does it
   (`ggml_cuda_dp4a` → `sudot4`, plus the real `get_int_from_table_16` v_perm dequant).

## What survives

- **The 32-float-FMA formulation is genuinely ALU-limited at ~50%, and the epilogue does not change
  that** (48.5% → 48.1%). This is a real property, but it is **not what production runs** — production's
  IQ4_NL dot uses dp4a. So it explains nothing about our 52%.
- **Addresses, launch count and grid shape remain cleared** (G = 101%, C = 99%, D = 100%, and now
  B-with-fair-epilogue = 101%).
- **The measurement methodology finding stands**: the interleaved harness, warm-up discipline, coverage
  probe, and now an epilogue-fairness check are all required before trusting an in-vitro number.

## Where production's 52% now stands

**Unexplained by both of the candidates shapebench could test.** Memory is fine; the real arithmetic is
fine. The remaining candidates are things shapebench does **not** model:

| candidate | how to test |
| --- | --- |
| **Per-block work is tiny.** attn_q `[2560,12288]` IQ4_NL = 1.44 KB of weights per output row, i.e. per block at `rpb=1`. A block that reads 1.4 KB may pay ramp/drain comparable to its useful work. | Real kernel in vitro at production shapes, sweeping `rpb`/K-split — but note `rpb=2` already tested **negative** (`rpb2-covered-negative-closed-20260916.md`), which argues against pure block-ramp. |
| **Activation quantization overhead.** Real `mmvq` first runs `quantize_row_q8_1_cuda` on x for every call; shapebench never pays that. | Add it to the in-vitro loop. |
| **MoE gather / `ids` indirection** on the expert matmuls. | Real-kernel in vitro with ids. |
| **The real reduction/epilogue** (shared `tmp_shared` + `buf_iw` spin-locks across nwarps). | Real-kernel in vitro. |
| **Something outside the GEMV** entirely (norms, router, HC, attention, graph overhead). | 80/16/0 phase split says target verify = 80%, so this is second-order, but not excluded. |

**The decisive next step is Codex's step 5: build the actual `mul_mat_vec_q` (not a fresh kernel) into
the standalone bench at production shapes, and time it there.** Until that is done, I have no measured
explanation for 52%.

## Honest scorecard on this claim

| claim | status |
| --- | --- |
| "decode loss is the scattered access pattern" | **retracted** (earlier) |
| "decode loss is per-block K-loop depth / grid shape" | **retracted** (B's gap was the epilogue) |
| "decode is ALU-bound at the per-weight level; dp4a gives ~1.5×" | **retracted** (dp4a reaches 100% with a fair epilogue) |
| "the 32-float-FMA dequant formulation is ALU-limited ~50%" | **holds**, but production does not use it |
| "`rpb` 1→2 on RDNA2 = no effect" | **holds** (covered and negative) |

Three successive mechanisms, three retractions — each caused by a measurement artifact (cold rep,
untouched code path, contended epilogue) rather than by the GPU. The pattern is clear enough to name:
**on this box, every in-vitro result must be checked for epilogue contention and code-path coverage
before it is allowed to explain anything.**

## Artifacts

`kernel-work/shapebench.hip` (now carries `read_kernel_nc`, `gemv_dp4a_nc_kernel`,
`gemv_arith_nc_kernel` and the epilogue-cost print). Repro: `shapebench.exe 24.0 150 realistic`.
