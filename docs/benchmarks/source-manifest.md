# source-manifest.md — handover v2 Candidate-B source queue (B2)

Sources located by web research on 2026-09-15, plus what is verifiable in **our** tree
(`~/strix-llama`, branch `win-native`, base `40a9f4d0`). Purpose: a ranked, source-backed queue of
single-APU / gfx1151 HIP improvements, each with a stated mechanism and an applicability verdict.
Nothing here is applied yet; this is the "patch applicability" input.

## Top candidate — PR26: give MTP targets their recurrent rollback slots back

- **Source:** `halo-box/strix-llama.cpp` PR #26 — *"speculative: give MTP targets their recurrent
  rollback slots back"* (author LaurentZuijdwijk). One file, `common/common.h`, +1/−1.
- **Mechanism:** PR #18 (`f169e0b7d`) dropped `COMMON_SPECULATIVE_TYPE_DRAFT_MTP` from
  `need_n_rs_seq()`. With `n_rs_seq = 0` the MTP target has no recurrent rollback slots, so on every
  *partial* draft acceptance the server takes the checkpoint/restore path and **re-decodes the
  accepted tokens as a replay batch — a second target forward pass on most steps.** PR26 re-adds MTP
  to the list so the target rewinds state in place and the replay disappears.
- **Reported gain:** 9.6–9.9 → 12.0–12.2 t/s (Vulkan, Strix Halo), cost 150 MiB → 750 MiB rs_seq at
  `n_max 4`. Backend-independent (it is a scheduler/state change, not a kernel).
- **Applicability to us: ALREADY PRESENT.** Our fork's `common/common.h:394` already reads:

  ```cpp
  uint32_t need_n_rs_seq() const {
      bool needs_rs_seq = std::any_of(types.begin(), types.end(), [&](auto t) {
          return t == COMMON_SPECULATIVE_TYPE_DRAFT_MTP || t == COMMON_SPECULATIVE_TYPE_DRAFT_EAGLE3 ||
                 t == COMMON_SPECULATIVE_TYPE_DRAFT_DFLASH || t == COMMON_SPECULATIVE_TYPE_DRAFT_DSPARK;
      });
      return needs_rs_seq ? draft.n_max : 0u;
  }
  ```

  and `common/common.cpp:1724` wires `cparams.n_rs_seq = params.speculative.need_n_rs_seq();`.
  **Action: PRESERVE — do not regress.** This is exactly the fix the handover said to keep. If we
  ever merge upstream speculative code, this line must survive the merge.

## Next candidates — MMVF / matvec bandwidth (the 55%-efficiency hot path)

Our decode is bandwidth-bound (`mul_mat_vec`-family), and every source below attacks the same
latency-bound single-APU matvec. Ranked by fit to our measured profile.

1. **halo-box PR #18 `mmvf.cu` (+189/−34)** — *"Optimize ROCM Prefill and Decode"*, merged
   2026-09-05 (`c7af5c6c`). Adds an **HIP-only prefetch-4 weight-load loop** for `ncols_dst == 1`,
   exact `ncols_dst` specializations 2/3/4, an `exact_batch` op-param hint, and a
   `mul_mat_vec_bf16_wave` kernel (one wave per output row, 8 loads in flight/lane) dispatched only
   when `block_size_best == 256 && ncols <= 512 && warp_size == 32` on RDNA. Comment states
   bit-identical (accumulation order unchanged). Reported: K=512 MoE down projections ~145 GB/s →
   keeps 8 loads in flight; 93 → 67 µs for 8×2048 rows of K=512. **Directly relevant** — our router
   (`[512,K]`) and hc-inject (`[4,K]`) shapes are exactly the flagged "small-M" case.
2. **SixVolts `llama-halo-hybrid` commit `a8c74df8`, `mmvf.cu` (+66/−3)** — the same 4-deep
   software-pipelined load idea, applied unconditionally in the f32 / f32-from-half / bf16
   accumulation paths, gated `!has_fusion`. `MMVF_MAX_BATCH_SIZE` is **unchanged (8)** here — the
   handover's "MMVF_MAX_BATCH_SIZE change" is not in this fork. **Relevant and small.**
3. **halo-box PR #56 (OPEN, unmerged)** — *"HIP: RDNA3.5 MMVQ/MMQ kernels and per-type dispatch
   thresholds"*. Two output rows per block (four for codebook types) in MMVQ, bit-exact; MMQ J=16
   prefetch; re-measured MMVQ/MMQ crossover thresholds; `GGML_MMVQ_THR` override. Reported tg128
   +12.1%, tg128 @d32000 +10.4%. **Most on-point for gfx1151 decode matvec**, but open/unreviewed —
   treat as a patch to evaluate, not adopt.
4. **ggml-org PR #28875 (OPEN)** — *"CUDA: use mmvf for tiny-N F32/F16 weights at decode batch
   sizes"*, raises the MMVF N limit 16 → 64 so `[K,4]` hc inject/gate and GDN β/α `[2560,32]` avoid
   cuBLAS+split-K. **Directly relevant to our hc inject matvec**; small, upstream-tracked.

## Hyper-connection fusion candidates

5. **halo-box PR #18 `hyperconn.cu` (+366)** — fused `hc_mix_reduce_f32`, `hc_combine_f32`,
   combine+rms_norm; uses **AMD inline asm** (`v_mul_f32_e32`) to forbid FMA contraction so the fused
   result is bit-identical to the unfused chain. Supersedes SixVolts' `hc.cu` (`k_scale_silu`,
   `k_hc_mix`, `k_hc_combine`, `k_mul_sigmoid`, `k_weighted_sum`, `k_gdn_gate`), which additionally
   passes a **q8_1 side-copy** into `mul_mat_vec_q` via an 8 MB arena to skip a separate
   `quantize_row_q8_1_cuda` pass (kill switch `GGML_CUDA_NO_Q8_SIDE`).
   Our fork already carries an upstream analogue: `ggml/src/ggml-cuda/dsv4-hc.cu/.cuh`
   (ggml-org PR #25585). **Evaluate whether our qwen4exp HC blocks are already fused or still launch
   5–6 tiny ops each** — that accounting is open (see the "hyper-connection cost" todo).
6. **SixVolts `mmvq.cu` RDNA4 small-K** — `ggml_cuda_mmvq_rdna4_small_k()` fixes short-K matvecs on
   RDNA4 (`MMVQ_PARAMETERS_RDNA4`). Reported Q8_0 `[10240×320]` row 23 µs/150 GB/s → 7 µs/490 GB/s.
   **RDNA4-specific, not gfx1151** — possibly informative but not directly applicable.

## Prefill-side (B3 background)

7. **halo-box PR #18**: RDNA3.5 MMQ tile retune (`mmq-config-rdna3-5.cuh`), register prefetching
   (`mmq-load-tiles.cuh`), D=256 WMMA FA (`fattn-tile-rdna3-5.cu`). Reported D=256 prefill
   +28% @32k. **Relevant to our 16.4% prefill gap**, larger patch.
8. **halo-box PR #38 (OPEN)** Q6_K via MMQ to `ne11 = 1024`; **PR #40** ROCmFP4 MMQ tiles gfx1151;
   **PR #55 (merged)** keep FA head 192 off WMMA. Niche.

## QSA / indexer

9. **ggml-org PR #28213 (OPEN)** gather-based sparse attention for QSA decode; **PR #28699 (OPEN)**
   incremental pooled-key cache for the QSA indexer; issues #28734 (decode slows with context),
   #28497 (QSA top-k nondeterministic). Our fork already has `d67d5883` "hip: enable sparse QSA
   decode and incremental indexer state" and `0f295019` "skip unused HIP decode indexer work", so
   some of this is already in. **No RDNA3.5-specific QSA kernel PR found.** Note: #28497 (QSA top-k
   nondeterminism) is directly relevant to the A0 near-tie finding.

## Negative / not-found (don't chase)

- No SixVolts repo named `halo-box`; "PR18"/"PR26" resolve only to `halo-box/strix-llama.cpp`.
- No `MMVF_MAX_BATCH_SIZE` change in any fork — the constant is 8 everywhere inspected.
- Upstream tile-tuning PRs for gfx1151 (#24022, #21344) are **closed/unmerged**; issue **#24438**
  ("HIP backend only ~40% of memory bandwidth on gfx1151 for MoE token generation") is the canonical
  statement of our exact problem and worth reading before writing any new kernel.

## Recommended order

1. **PR26** — verify present (done: yes) and protect it. No work needed, high regression value.
2. **PR #28875** (tiny-N MMVF) and **halo-box PR18 `mmvf.cu` prefetch** — smallest, most on-point
   matvec changes for our measured 55%-efficiency decode.
3. **hyperconn/hc fusion audit** — first measure whether our HC blocks are already fused; only then
   consider porting #18's `hyperconn.cu`.
4. **halo-box PR #56** — evaluate only as an experiment (open/unmerged).
5. Prefill MMQ retune — larger; sequence after the decode candidates.
