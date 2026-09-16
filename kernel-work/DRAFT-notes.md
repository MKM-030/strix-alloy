# Decode-kernel design for Qwen3.8-Flash-Next on Bosgame M5 — measurement + concept (2026-09-13)

Status: DRAFT, numbers marked [EST]/[MEAS] as they land. Deliverable of the kernel follow-on session.
Work dir: `C:\Projects\REV-N-ornith-eval-20260911\kernel-work\` (scripts, logs, JSON).

## 1. TL;DR

(placeholder — fill at end)

## 2. What was measured this session (all [MEAS] unless noted)

- Env: WSL2 Ubuntu 24.04, ROCm 10 SDK over DXG (`HSA_ENABLE_DXG_DETECTION=1`), fork `pwilkin/llama.cpp@strix-halo`
  commit `f5daaa3c`, build `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_HIP_NO_VMM=ON
  -DGGML_HIP_MMQ_MFMA=ON -DGGML_CUDA_FA=ON -DGGML_HIP_RCCL=OFF`. Device: ROCm0, Radeon 8060S, gfx1151,
  wave32, 81,564 MiB pool. WSL cap 70 GB. One heavy job at a time. A curl download (IQ4_NL shard 7/9)
  ran on the same disk throughout (I/O-noise caveat for load times, not for decode A/B).
- GGUF inventory (parsed from the 3 shards, exact quant block sizes from ggml-common.h):
  176.94 B params, 87.24 GiB, 4.235 bpw. 48 layers; 512 experts, **top-k = 10** (+1 shared, FFN 640);
  emb 2560; vocab 248,320 (token_embd Q8_0 0.63 GiB, output Q6_K 0.49 GiB);
  36 GDN layers (state 128, inner 6144, group 16, conv 4, dt_rank 48), 12 full-attn layers every 4th
  (24 heads, 2 KV heads, head_dim 256, rope 64 dims/4 sections, indexer 4 heads key 128 top_k 2048);
  hyper-connections: 4 streams, low-rank 320 (hc_attn/hc_ffn up/down Q8_0 + inject F32 per layer);
  per-layer 160-dim embedding input; PLE n-gram table = `per_layer_token_embd.weight`, 320,001,536 rows
  × 160 dim IQ4_NL = **26.82 GiB, paged from disk (not resident)**; ngram_size 3, heads_per_ngram 8.
- Per-layer quant mix (unsloth dynamic): gate/up experts IQ3_S (343.75 MiB per layer per tensor),
  down experts IQ4_NL 450 MiB or **Q8_0 850 MiB** (4 of 48 layers are Q8_0 down: blk 2,4,30,46 + blk 47
  variant), attention/GDN weights Q8_0, router `ffn_gate_inp` **F32** (5 MiB/layer).
- **Active resident weight bytes per decoded token (k=10, computed from inventory):**
  routed experts ~1,108.6 MiB; attention+GDN ~3,476 MiB; shared expert ~239 MiB; router ~240.5 MiB;
  output head ~500 MiB; norms/embedding row ~15 MiB; total ≈ **5.4–6.1 GiB/token**.
  Weight-only ceiling at 200–240 GB/s: **~28–34 ms/token ≈ 29–35 t/s** (f16 KV read adds ≤4 ms at 36k
  if dense-scanned; GDN state ~108 MiB/token r+w ≈ 1 ms).
- Kernel facts (read from source): MoE decode path = router GEMV → `topk-moe` (device) →
  `mul_mat_vec_q_moe` gate+up fused (grid (ceil(640/8), 1), block (32, k=10): ~800 warps total) →
  `mul_mat_vec_q_moe` down → `moe_weighted_reduction_f32` (5 launches/layer; expert ids read on-device,
  graph-safe, no per-expert CPU dispatch). `FORK_GDN_TILE` requires n_tokens ≥ 16 → **decode uses the
  generic GDN kernel**, not the tiled one. `GGML_CUDA_GRAPH_OPT=1` exists (opt-in stream reordering).

## 3. Experiment A — HIP graphs on/off over DXG (the agreed first experiment)

Mechanism: `GGML_HIP_GRAPHS` is compile-time and ON in this build; runtime switch is
`GGML_CUDA_DISABLE_GRAPHS` (no rebuild). Warmup semantics: a graph key (= first node pointer) needs
2 consecutive calls with unchanged node properties (pointers/shapes/strides) before capture;
after capture, replay requires only `cgraph->uid` match — properties changes reset warmup.
Compatibility: the only graph blocker in the checker is the sync-requiring mul_mat_id fallback
(batch-1 quantized ids take `mul_mat_vec_q`, which does not sync).

Result table: (placeholder — fill from expA-summary.json)

## 4. Stage breakdown (LLAMA_GRAPH_TIMING / OP_TIMING)

(placeholder)

## 5. Ranked next experiments

(placeholder)

## 6. First kernel to build

(placeholder)

## 7. Kernel-architecture comparison for THIS hardware

(placeholder — table over mainline HIP, strix-halo, Halogen, Ciru/vLLM, chlorine-server, Vulkan forks,
ROCmFPX fp4, EngramHalo; Windows/WSL vs native Linux)

## 8. Reproduction

(placeholder — exact commands)
