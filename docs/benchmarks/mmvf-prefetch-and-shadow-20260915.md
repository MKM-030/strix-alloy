# MMVF prefetch (F32 router) negative, and the Q6_K shadow does not cost decode traffic (2026-09-15)

Two follow-ups to the MMVQ negatives, both closed.

## 1. MMVF 4-deep prefetch for single-column F32 matvecs — negative

**Hypothesis.** The fork's `mul_mat_vec_f` (`ggml/src/ggml-cuda/mmvf.cu`) does one dependent `float2`
load per K-loop trip for `ncols_dst == 1`. The halo-box PR18 / SixVolts work adds a 4-deep
software-pipelined load loop for exactly this case, reporting large gains on the small-M shapes. Our
**MoE router** `blk.*.ffn_gate_inp.weight` is `F32 [2560, 512]`, read every token, and is the one
genuinely MMVF-eligible hot tensor in the decode read set (`decode-byte-accounting-20260915.md`, 6% of
bytes). So it was worth a test.

**What I did.** Added the prefetch loop (four `x2`/`y2` loads issued before consuming them; per-thread
accumulation order unchanged, so bit-identical) for `!has_fusion && ncols_dst == 1`, built, and
measured.

**Single run looked positive:** 29.30 vs 28.75 t/s (+1.9%).

**Interleaved A/B says it is noise.** `kernel-work/interleaved-ab.ps1` alternates base and patch arms
(base, patch, base, patch) and compares medians, so thermal/cache drift hits both arms:

| arm | runs (decode median t/s) | median |
| --- | --- | ---: |
| base | 29.107, 29.175 | 29.11 |
| patch | 28.859, 29.596 | 28.86 |
| **delta** | | **−0.9%** |

**Verdict: negative.** The single-run +2% was the tail of normal variance (the base arm alone ranged
28.63–29.26 across reps). The mechanism predicted a small ceiling (the router is 6% of bytes, and a
latency win there is worth ~2% at most *if* it fully hides), and at that scale it is not separable from
run-to-run noise on this box. Note also that production MTP runs the target at **3 rows** (`ncols_dst=3`),
where this `ncols_dst==1`-only patch does not apply at all — so even the optimistic case would only
touch the two draft steps, not the dominant verify pass.

**Lesson recorded:** effects of ~2% need the interleaved harness, not a single 5-rep run. The
`decode-baseline.ps1` single-arm spread is ±1%, which is the same size as the effect.

## 2. The Q6_K MMB shadow does not add decode traffic — closed

**The concern.** `mmb_shadow_prepare` (mode 2) converts resident Q6_K weights to a **bf16 shadow**
(0.82 → 2 bytes/elem, a 2.4× inflation). Our model has two Q6_K tensors — `output.weight` (521 MB) and
`blk.*.attn_output.weight` (155 MB) — read every decode token. If the *shadow* were read at decode, that
would be ~900 MB/token of extra traffic (~21% of the 4.22 GB budget) — a real bug, not a tuning miss.

**It is not.** Two facts from the source close it:

- **`output.weight` is not shadow-eligible.** `mmb_is_resident_q6k` requires `w->ne[1] <= 32768`;
  `output.weight` is `[2560, 248320]`. So the biggest Q6_K tensor never gets a shadow.
- **The shadow is only read inside MMB.** `mmb_shadow_lookup` is consulted in `ggml_cuda_mul_mat_mmb`,
  which the dispatcher only reaches when `T >= mmb_min_t()` = **512** (`ggml_cuda_mmb_supported_mm`).
  Decode is `T <= 12`, so decode never runs the MMB path and never reads a shadow. The shadow exists for
  the prefill case, where it can pay off; the allocation is device memory, not decode bandwidth.

**Verdict: no decode-traffic impact; not a defect.** (Consistent with the empirical result that decode
sits at ~63% of the bandwidth ceiling with a uniform loss — there is no hidden 900 MB/token.)

## Combined with the MMVQ negatives

Four kernel hypotheses have now been implemented and measured on this box, all negative:

| # | candidate | result |
| --- | --- | --- |
| 1 | small-K MMVQ on RDNA3.5 | inert (`nwarps=1` on the RDNA2 table) |
| 2 | RDNA3.0 parameter table on gfx1151 | **−21%** |
| 3 | `mmb_min_t` 512→128 (short prefill) | ~0% at every size |
| 4 | MMVF 4-deep prefetch (F32 router) | −0.9% (noise) |

This is a consistent picture: **gfx1151's stock kernel configuration is already tuned for this part**,
and the small remaining inefficiency is not reachable by porting another arch's parameters or inserting
prefetch. The one place the byte census pointed — the uniform ~37% bandwidth shortfall across all 4.22
GB — would need a genuinely new quantized-matvec kernel, which is a research project.

## Reverted

All experiments reverted: `~/strix-llama` is clean (`git status` empty, HEAD `891a923a`), `ggml-hip.dll`
rebuilt from clean source (86,770,688 bytes — the upstream size), and no experiment strings remain in
the binary. A confirmation run reproduced the baseline.

## Artifacts

`kernel-work/interleaved-ab.ps1` (the high-confidence A/B harness); `kernel-work/decode-baseline.ps1`;
`results/dbl-armD-mmvfpf.json`, `results/iab-{base,patch}-r{1,2}.json`, `results/interleaved-ab.json`,
`results/build-mmvfpf.log`.
