You are reviewing a GPU-kernel design for decode acceleration of Qwen3.8-Flash-Next
(qwen4exp MoE: 48 layers, 512 routed experts, top-k=10 + 1 shared expert, emb 2560, expert FFN 640,
hybrid attention: 36 GatedDeltaNet layers (state 128, inner 6144, group 16) + 12 full-attention
layers every 4th (24 heads, 2 KV heads, head_dim 256, sparse lightning-indexer top_k=2048),
hyper-connections (4 streams, low-rank 320), per-layer 160-dim embedding with a 26.82 GiB n-gram PLE
table paged from disk, vocab 248,320).

Hardware: AMD Ryzen AI Max+ 395, Radeon 8060S iGPU, gfx1151 RDNA3.5 wave32, 40 CUs, 128 GB LPDDR5X
~200-240 GB/s. Runtime: Windows 11 + WSL2 over /dev/dxg (HIP over DXG; NO /dev/kfd, no PM4 replay).
llama.cpp fork pwilkin/llama.cpp@strix-halo (MIT) with hand-written gfx1151 kernels: tiled GDN
(prefill, n_tokens>=16), QSA sparse attention, bf16 WMMA dequant GEMM (MMB), fused gate/up MMVQ MoE
("mul_mat_vec_q_moe": grid (80,1) x block (32,10) = ~800 warps for gate/up at batch-1), device-side
topk-moe, moe_weighted_reduction. HIP graphs (GGML_HIP_GRAPHS) compiled in and working over DXG.

MEASURED THIS SESSION (all real, same binary/quant/flags unless noted):
- Decode tg128 @p0: graphs ON 12.00+/-0.42 t/s (tg64: 15.19); @2048 ctx: 13.85+/-0.39 t/s
  (pp2048 117.5 t/s). Prior session server @36k: prefill 300.8 t/s, decode 6.97 t/s.
- Graphs OFF on Flash-Next: 5/5 attempts hard-reset the WSL VM mid-load/warmup (no OOM traces, clean
  teardown, GPU pool intact after; WSL caps 70/72/76/92 GB all failed). Control: 21 GB Ornith 35B-A3B
  MoE ran graphs-OFF fine (41.42+/-0.76 t/s) and graphs-ON ~75-100 t/s (rep1 includes capture).
  => non-graphed submission at Flash-Next scale (87 GiB UMA-mapped, 7.3k-node graphs) is unstable
  over DXG; graphs are mandatory, not just faster.
- Decode graph: 7,322 nodes. Lifecycle: 2 direct warmup evals (eval2: submit 13.6 ms + gpu_wait
  56.6 ms), 1 capture (record 183 ms; instantiate ~1.76 s), then PURE REPLAY: 96.9% graph=1,
  exactly 2 upd=1 (the captures), ZERO rebuilds across all tokens (expert ids/positions change).
- Steady replay per token (median): gpu_wait 49.2 ms (min 44.5, max 97.6), hostgap 3.4 ms,
  submit 0.3 ms. At 2k ctx: hostgap 8.6 ms (PLE row reads), gpu_wait 45.5 ms.
- Correctness: capture/instantiate/replay exact vs direct (micro-test, replay1 err=0; production
  pattern with device-side state chaining is exact). Caveats: a 64K-element micro-test once showed
  stale data after host-memcpy mutation and one hang in hipDeviceSynchronize; DXG event timing
  under-reports (direct 2-kernel loop "measured" 555 GB/s - impossible). Trust model-level checks.
- Active weight bytes/token (k=10, parsed from GGUF, exact block sizes): routed experts 1108.6 MiB
  (IQ3_S gate/up 343.75 MiB/layer each + IQ4_NL down 450 MiB / Q8_0 850 MiB on 4 layers),
  attention+GDN weights 3476 MiB (Q8_0), shared expert 239 MiB (Q8_0), router 240.5 MiB (F32, fully
  read per token), output head ~500 MiB (Q6_K 248k vocab), norms ~15 MiB. Total ~5.45 GiB/token =>
  weight-only ceiling ~35-42 t/s at 200-240 GB/s (NOT the 63-75 t/s from the earlier 6B/4.25bpw
  estimate). Measured GPU 49 ms @p0 => ~15-20 ms/token kernel inefficiency above the ~29-34 ms floor.
- KV f16: 24 KiB/token (12 full-attn layers); 0.84 GiB at 36k if dense; QSA top_k=2048 should cut
  reads ~17x. GDN state ~108 MiB/token f32 read+write.

DESIGN UNDER REVIEW (post-graphs ranking):
D': fused MoE decode chain - one kernel for gate/up GEMV + SiLU-mul (h_e 640 floats), one for down
    GEMV + expert-weighted reduction; grid = experts(10) x row-tiles x K-slices for contiguous
    per-slice reads; replaces 3 launches + h_e materialize + reduction re-read (~24 MiB/token
    avoidable D2D traffic); requires a codebook-preserving (expert, K-slice, row-tile) weight
    repack sidecar; graph-capture-compatible (no syncs). Expected +20-35% decode at p0.
E:  MTP speculation (draft model exists; 100% observed acceptance on the Vulkan build). k=10 caveat:
    4-token draft union = 512*(1-(1-10/512)^4) = ~38.5 experts vs 10 => verify-phase expert traffic
    ~3.9x. Must verify exact sampling + state rollback, not just acceptance.
F:  PLE hot-row cache (26.82 GiB table, 320M rows x 160 dim IQ4_NL, demand-paged mmap): measured
    hostgap 3.4->8.6 ms going p0->2k ctx; bounded cache ~78 MiB + prefetch overlap.
G:  KV Q8 for the 12 full-attn layers (only ~0.2-2 ms unless QSA bytes/token turn out large).
C:  fp4/mxfp4 for the Q8_0 attention/GDN weights (3.4 GiB/token bucket): dequant-cost play,
    ~-4-8 ms/token, NOT a bandwidth play vs IQ4_XS.
Questions:
1. Where do you think the measured 49 ms/tok GPU time (vs ~29-34 ms weight floor) goes, given the op
   mix (240 MoE-chain nodes, ~1,000 attention/GDN nodes, ~2,000 norm/add/mul/rope nodes)? What single
   measurement best discriminates dequant cost vs small-kernel latency vs GDN serial chain?
2. For D': with 40 CUs wave32, emb 2560, FFN 640, k=10, IQ3_S/IQ4_NL blocks of 256: is the proposed
   grid (10 experts x 10 row-tiles x 5 K-slices, 4-warp CTAs, atomic/second-pass K-reduce) right, or
   would you tile differently? Expected ms/layer for gate/up and down?
3. For E: given the expert-union math and measured expert bucket ~1.09 GiB/token, what draft depth
   maximizes accepted tokens per unit expert-traffic? Is MTP worth building before D'?
4. Rank D'/E/F/G/C by expected decode gain per effort on THIS runtime (graphs work; PM4 absent).
5. Anything in the measurements or interpretation above that looks wrong?
Answer concisely with numbers.
