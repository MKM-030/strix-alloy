# Faster-decode kernel design for Qwen3.8-Flash-Next on Bosgame M5 — measurements + concept (2026-09-13)

Session: kernel follow-on (experiment A first, then design). Workspace:
`C:\Projects\REV-N-ornith-eval-20260911\kernel-work\` (all scripts, raw logs, JSON). This document is
self-contained; every number says `[MEAS]` (measured here) or `[EST]` (derived/estimated).

---

## 1. TL;DR

1. **Experiment A (HIP graphs on DXG): graph capture/instantiate/replay works and is numerically
   exact; replay is stable and cheap.** The Flash-Next decode graph has **7,322 nodes**, is captured
   **once** (two warmup evals + capture), and is then **replayed with zero updates** across every
   token — expert IDs and positions change per token while the graph is reused. Replay submission
   costs **0.3 ms/token** vs **13.6 ms/token** for direct per-op submission (`[MEAS]`). Graphs ON
   measured **12.00 ± 0.42 t/s** tg128 (15.19 tg64; 13.85 @2k ctx). The OFF arm could not complete:
   all five attempts died mid-load — now attributed primarily to **co-tenant memory collision**
   (another session was running Flash-Next in WSL concurrently; two instances cannot fit), not to a
   dxg defect — the A/B number remains open pending an exclusive box (§4.4, theory-prep §1).
2. **The prior bandwidth ceiling (63–75 t/s) was wrong for this quant.** The real active weight traffic
   is **≈5.45 GiB ≈ 5.85 GB/token** (top-k **10**, not 8; Q8_0 attention/GDN weights; an F32 router
   fully read per token; Q6_K output head over 248k vocab) → weight-only ceiling **≈34–41 t/s** at
   200–240 GB/s `[EST from measured tensor sizes]`. Measured GPU execution is ~49 ms/token median at
   zero context → **effective weight bandwidth ≈119 GB/s**, i.e. ~55 % of the low-end ceiling; the
   gap is dequant cost, scattered loads, device-side dispatch and dependency stalls `[EST]`.
3. **Ranked next steps (post-A, incorporating the second Codex review):** graph-preserving
   operator-family **ablation** to attribute the ~20 ms gap → **MTP prototype at depth 2 and 4** (E —
   the union math does *not* penalize per-accepted-token efficiency, and experts are only ≈20 % of
   weight traffic, so verify amortizes the other 80 %: ideal weight-traffic speedup 1.67×/2.54×) →
   **F PLE hot-row cache** (0–11 %) → **D′ fused MoE chain without split-K** (low-single-digit ms
   provisionally) → C fp4 on the Q8_0 bucket (−7.6–9.1 ms ideal) → G KV-Q8 (≈0.1 ms under perfect
   QSA sharing).

---

## 2. Environment and method

- Hardware: Bosgame M5, Ryzen AI Max+ 395, Radeon 8060S (gfx1151, RDNA 3.5, wave32, 40 CUs),
  128 GB LPDDR5X, firmware carve 32 GB → HIP device pool 81,564 MiB (`llama-bench --list-devices`
  shows ~48.9 GiB free when idle) `[MEAS]`.
- Runtime: Windows 11 + WSL2 (Ubuntu 24.04) over `/dev/dxg` only (no `/dev/kfd`). ROCm 10 SDK from the
  Ciru venv (`_rocm_sdk_*`), sourced via `kernel-work/env.sh` with `HSA_ENABLE_DXG_DETECTION=1`,
  `GGML_HIP_ENABLE_UNIFIED_MEMORY=1` (UMA is **required**: the device pool free space (~11–49 GiB
  observed) is far below the ~61 GiB resident weights, so weights must live in WSL host memory).
- Build: `pwilkin/llama.cpp@strix-halo` commit `f5daaa3c`, configured
  `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_HIP_NO_VMM=ON
  -DGGML_HIP_MMQ_MFMA=ON -DGGML_CUDA_FA=ON -DGGML_HIP_RCCL=OFF`. Branch `op-timing` (this session)
  adds `LLAMA_OP_TIMING` instrumentation (see §5).
- Model: `~/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS` (3 shards, 87.24 GiB), staged on
  ext4. Control model: `Ornith-1.5-35B-MTP-23G-ICE.gguf` (qwen35moe, 21.26 GiB), staged this session.
- Protocol: one heavy job at a time; page caches dropped between arms
  (`sudo sysctl vm.drop_caches=3`); A/B arms differ **only** in the graph runtime switch
  (`GGML_CUDA_DISABLE_GRAPHS`), same binary/quant/flags (`-ngl 99 -fa 1 -t 8`).
- Caveat: a background download of the IQ4_NL PROJFIX quant (shard 7/9, started by the earlier
  session) was running during the first measurements and was killed by a VM reset mid-session; it was
  **not** restarted. It affects load times, not the decode A/Bs (both arms ran without it).

## 3. The model, instrumented (from the GGUF headers, exact quant block sizes)

Parsed with `kernel-work/gguf_inventory.py` (type sizes cross-checked against `ggml-common.h`):

| Fact | Value |
| --- | --- |
| Params / size / bpw | 176.94 B / 87.24 GiB / **4.235** |
| Layers | 48 (36 GatedDeltaNet + 12 full attention, every 4th) |
| MoE | **512 experts, top-k = 10** + 1 shared expert, FFN 640, emb 2560 |
| Attention | 24 Q heads, 2 KV heads, head_dim 256; lightning indexer 4 heads, key 128, **top_k 2048** |
| Hyper-connections | 4 streams, low-rank 320 (Q8_0 up/down + F32 inject per layer) |
| Router | `ffn_gate_inp` **F32**, 2560×512 = 5 MiB/layer |
| PLE n-gram table | `per_layer_token_embd.weight` 320,001,536 × 160, IQ4_NL = **26.82 GiB, paged** |
| Vocab | 248,320 (token_embd Q8_0 0.63 GiB — only 1 row read/token; output Q6_K **0.49 GiB — fully read** |
| Per-layer quant mix (unsloth dynamic) | gate/up experts IQ3_S (343.75 MiB each), down experts IQ4_NL 450 MiB (Q8_0 850 MiB on 4 layers), attention/GDN Q8_0 |

### Active weight bytes per decoded token (k=10) — the corrected bandwidth model

| Component | MiB/token | Notes |
| --- | ---: | --- |
| Routed experts (10×) | 1,108.6 | ≈2.2 MiB avg/expert (IQ3_S gate/up + IQ4_NL/Q8_0 down) |
| Attention + GDN weights | 3,476.0 | Q8_0; attn_qkv 26.6, attn_gate/out 15.9, hc ~13, ssm_out 15.9 MiB/layer |
| Shared expert | 239.1 | Q8_0, always read |
| Router (F32) | 240.5 | full 2560×512 read every token |
| Output head (Q6_K) | ~500 | 248,320×2560 GEMV |
| Norms, per-layer emb row | ~15 | |
| **Total** | **≈5,580 ≈ 5.45 GiB = 5.85 GB** | floor **29.3 ms @200 GB/s … 24.4 ms @240 GB/s** |

- Weight-only decode ceiling: **≈34–41 t/s** `[EST]` (add ~1 ms GDN state r+w ≈ 108 MiB f32).
- KV f16: 24 KiB/token (12 full-attn layers); 0.84 GiB total at 36k if dense-scanned; the QSA indexer
  (top_k 2048) should cut this ~17× → tens of MB/token `[EST, kernel-dependent]`.

## 4. Experiment A — graph-enabled vs graph-disabled decode `[MEAS]`

Mechanism (from source): `GGML_HIP_GRAPHS` is compile-time (ON in this build); the runtime switch is
`GGML_CUDA_DISABLE_GRAPHS`. A graph key (= first-node pointer) needs 2 consecutive evals with identical
node properties (pointers/shapes/strides) before capture; afterwards, replay only needs `cgraph->uid`
to match. The only graph-compat blocker in the backend is the sync-requiring `mul_mat_id` fallback;
batch-1 quantized MoE takes `mul_mat_vec_q` (device-side ids, no sync) → compatible.

### 4.1 Headline A/B (llama-bench, same binary/quant/flags, tg128 @ p=0)

| Config | Result | Status |
| --- | --- | --- |
| Flash-Next, graphs **ON** | **12.00 ± 0.42 t/s** (83.3 ms/tok); tg64 run: 15.19 t/s | ✅ 2/2 runs |
| Flash-Next, graphs **OFF** | — | ❌ **5/5 WSL VM teardowns** (see §4.4) |
| Ornith 35B-A3B, graphs OFF | **41.42 ± 0.76 t/s** | ✅ control: non-graphed mode works at smaller scale |
| Ornith 35B-A3B, graphs ON | 75.02 ± 49.82 t/s | ✅ rep 1 includes graph capture; steady-state reps ≈100 t/s → **≈2.4×** vs OFF |
| Flash-Next @ 2048 ctx, graphs ON | pp2048 117.47 t/s; tg128 **13.85 ± 0.39 t/s** | ✅ |

Reference points from the earlier session (same binary): server prefill 300.8 t/s @36k; server decode
6.97 t/s @36k.

### 4.2 Graph lifecycle on Flash-Next decode (`LLAMA_GRAPH_DIAG`/`LLAMA_GRAPH_TIMING`, 65 evals) `[MEAS]`

- Decode graph: **7,322 nodes** (`hc_init` → `result_output`), graph-compatible, enabled.
- Lifecycle: eval 1 direct (kernel JIT warm-up, submit 1755 ms), eval 2 direct (clean measurement),
  eval 3 **capture** (submit 183 ms; `cudaGraphInstantiate` ≈1.76 s), then **pure replay**.
- Steady state: **graph=1 on 96.9% of evals, upd=1 on exactly 2 (the captures) → zero rebuilds while
  decoding.** A second graph (n=1, `input_embed`) coexists; alternating uid-31/38 pairs are the
  warmup vs steady graphs, each warmed once.
- Per-token backend split (median over ≥60 replayed tokens): **gpu_wait 49.2 ms** (min 44.5, max
  97.6), **hostgap 3.4 ms** (max 36.7), **submit 0.3 ms**.
- Direct-mode sample (the eval-2 line): **submit 13.6 ms + gpu_wait 56.6 ms** — i.e. per-op submission
  of 7,322 nodes costs ≈**1.9 µs/node** of host time that replay eliminates, and replay also removes
  ~7 ms of inter-kernel GPU gaps.

**Interpretation.** At zero context the token time budget is ≈49 ms GPU + ≈3.4 ms host + ≈0.3 ms
submit (backend) + ≈13 ms llama.cpp-level host work (sampling over 248k logits, detok, PLE row reads)
≈ 66 ms ↔ 15.19 t/s. The submission-overhead hypothesis is **dead**: graphs already cut it to 0.3 ms.
The GPU 49 ms vs the ≈29–34 ms weight floor leaves **~15–20 ms/token of kernel inefficiency**
(small-kernel latency, dequant, GDN serial chain, QSA, reduction ops) — that is the kernel target.
At 2k ctx, hostgap grows to 8.6 ms (PLE row reads appear on the host path); gpu_wait unchanged.

### 4.3 Micro-test over DXG (`kernel-work/hipgraph-microtest*.cu`) `[MEAS]`

- Capture → instantiate → replay of a 2-kernel graph: **exact** (max abs err 0 vs direct execution);
  replay after *device-side* data changes: exact (llama.cpp's production pattern).
- **Caveats found:** in a 64 K-element variant, replay after *host-memcpy* data mutation returned
  stale data once, and one `hipDeviceSynchronize` after a small graph hung until killed. The original
  "555 GB/s event-timing artifact" flag was **overstated** (Codex catch): a 4 MiB working set is
  cache-resident, so an apparent super-DRAM rate is not by itself proof of broken event timing — but
  it does mean the micro-benchmark could not distinguish execution from enqueue, so it never measured
  what it claimed. Practical rules: trust model-level correctness checks over micro-benchmarks; do
  not use event intervals over DXG for cross-run timing; the llama.cpp graph path (device-side state
  chaining) is the reliable pattern.
- Model-level ON-vs-OFF text diff: **not obtainable on this box tonight.** Graphs-off is unrunnable at
  Flash-Next scale (§4.4), and after ~20:35 a concurrent Docker/containerd tenant appeared in WSL and
  every fresh llama-server process began getting SIGKILLed within minutes (3 attempts, no OOM traces,
  including an Ornith control that had run fine earlier) — a shared-machine confound documented here
  rather than resolved. Correctness therefore rests on: the micro-test results above, the prior
  session's coherent graphs-ON server output (same build, correct text), and 4 stable graphs-ON bench
  runs.

### 4.4 Stability finding: graphs-off Flash-Next resets the WSL VM `[MEAS]`

**UPDATE (late 2026-09-13, after session context):** the founder confirmed another session was
**concurrently running Flash-Next under WSL all evening**. Two Flash-Next instances (~61 GiB pinned
each) cannot fit any WSL cap tried — so the dominant hypothesis for the 5/5 teardowns is now
**co-tenant memory collision**, not a dxg submission defect. Consequences: (a) the graphs-ON numbers
(12.00–15.19 t/s, gpu_wait ≈49 ms) are valid as *relative* A/B (both arms equal conditions) but the
absolute gpu_wait may be contaminated by co-tenant GPU/memory contention — re-measure on an exclusive
box before quoting absolutes; (b) **"graphs-off is unstable at scale" is unproven** — the real A/B
number is still open and requires an exclusive box; (c) the operational rule that survives: **one
Flash-Next instance per box, period** (see `decode-kernel-theory-prep-20260913.md` §1 for the full
reinterpretation and the overnight re-measurement plan).

## 5. Per-op GPU split of the 49 ms — attempted, and what replaced it

**In-graph event profiling does not work over DXG** `[MEAS]`: the `op-timing` branch records event
pairs *inside* the captured graph (they become graph nodes; replay re-emits them at zero cost), the
run completes and replays normally — but `hipEventElapsedTime` returns **0.0 for every segment**.
DXG does not timestamp graph-embedded events. This is consistent with §4.3 (event intervals over DXG
under-report) and closes event-based profiling here. (Raw log: `expA/expA-on-ig.log`.)

**Replacement: arithmetic attribution from the exact byte model** `[EST from MEAS sizes]`:

| Op class | Weight bytes/token | Floor @200–240 GB/s | Nodes/token |
| --- | ---: | ---: | ---: |
| Routed experts (k=10) | 1,108.6 MiB | ≈4.8–5.8 ms | ≈240 (5/layer) |
| Attention + GDN weights | 3,476.0 MiB | ≈15.2–18.2 ms | ≈1,000 |
| Shared expert + router | 479.6 MiB | ≈2.1–2.5 ms | ≈96 |
| Output head | ≈500 MiB | ≈2.2–2.6 ms | 1 |
| Norms / rope / add / mul / embed | (activations only) | ≈0.5 ms | ≈5,900 |
| **Floor total** | ≈5.45 GiB = 5.85 GB | **≈24.4–29.3 ms** | **7,322** |

Measured steady GPU time ≈ **49 ms/token (median)** → **effective weight bandwidth ≈119 GB/s**
(≈55 % of the 200 GB/s low end). Candidates for the gap — dequant instruction cost, scattered
per-block loads, occupancy limits, device-side dispatch and dependency stalls — overlap and cannot be
separated by one aggregate scalar. At an illustrative 1 µs of device dispatch per node, 7,322
sequential nodes already cost ≈7.3 ms even with graph replay (replay removes *host* submission, not
device dispatch/dependencies).

**The discriminating experiment (from the second Codex review):** a **graph-preserving
operator-family ablation**, timed by CPU wall clock over completed steady replays — compare real
kernels against (a) same-address load/checksum variants (isolates arithmetic/dequant cost) and (b)
dependency-preserving stubs (isolates scheduling/dependency overhead); isolate the GDN chain the same
way, preserving routing, shapes and working sets. Real→load-only = compute cost; load-only→stub =
memory cost; stub graph total = scheduling cost.

**Window reconciliation (Codex catch):** summed medians (49.2+3.4+0.3 = 52.9 ms) do not equal the
measured per-token mean (tg64 run: 15.19 t/s ↔ 65.8 ms; tg128: 12.00 t/s ↔ 83.3 ms). The difference is
the mean-vs-median tail (gpu_wait max 97.6 ms), llama.cpp host work outside the backend window
(sampling over 248k logits, PLE row reads) and rep-count differences. Use means over identical
windows when quoting throughput; use medians only for the split's structure.

## 6. Ranked decode strategies (post-A + second Codex review), with expected gain / effort / risk

Submission overhead is solved (0.3 ms replay). The budget to attack: GPU execution ≈49 ms median
(p0) / ≈143 ms (36k server). Ranked by expected decode gain per unit effort:

| Rank | Strategy | Expected gain | Effort | Risk | Next experiment |
| ---: | --- | --- | --- | --- | --- |
| 0 | **Operator-family ablation** (instrumentation, not a speedup) | Attributes the ~20 ms gap into compute / memory / scheduling; everything downstream is sized by it | medium (stub + load-only kernel variants inside the captured graph) | low | build 3 graph variants (real / load-checksum / stub), CPU-wall-clock steady replays |
| 1 | **F — PLE hot-row cache + prefetch** | Recovers part of the measured 5.2 ms hostgap growth (3.4 → 8.6 ms p0→2k ctx): **≈0–11 %**; removes latency spikes at depth | low–medium | low | count PLE row reads + miss attribution in the lazy reader; size a bounded cache (≈78 MiB) |
| 2 | **E — MTP prototype, depth 2 and 4** | Largest upside: ideal weight-traffic speedup **1.67×/2.54×** at depth 2/4 (experts are only ≈20 % of weight traffic — the union costs are per-accepted-token ≈flat: 0.99×/0.97×); net gain unknown until drafted | medium | must verify exact sampling + full state rollback (GDN/conv/KV/positional), not acceptance | run the fork's MTP path on WSL (draft gguf staged), depth sweep, measure accepted tokens × latency |
| 3 | **D′ — fused MoE decode chain, no split-K first** | **Low-single-digit ms provisionally** (Codex challenge accepted: the 24 MiB/token fusion saving is only 0.10–0.13 ms; a 20–35 % claim needs the ablation to first show the MoE chain actually costs that much) | high | numerics (IQ codebooks), graph compat | after ablation; see §7 tile plan |
| 4 | **C — fp4/mxfp4 on the Q8_0 bucket** | Q8_0 attention/GDN 3.4 GiB → halved ≈ **−7.6–9.1 ms ideal**; fp4 storage alone doesn't guarantee faster arithmetic — needs the integer-dot path to actually win | medium | quant quality; fork-locked quants | requant attention/GDN tensors only, microbench dequant+dot |
| 5 | **G — KV Q8_0 (12 full-attn layers)** | With perfect QSA sharing: 2,048 positions ≈ 48 MiB/token → halving ≈ **0.1 ms**; head duplication or gather inefficiency could raise it | low | kernel support | measure actual QSA KV bytes/token in the ablation first |

The three kernel techniques from the Astra review, updated by measurement + review:

1. **Selected-expert × output-tile scheduling** — still the D′ core, but: (a) the "40 CUs idle"
   premise is unverified (the fork's MoE GEMV runs ~800–3,200 warps at batch-1); (b) **split-K has a
   correctness boundary** — gate/up partials must be fully summed *before* SiLU-mul, which plain
   atomics cannot order inside one kernel → **start without split-K** (full-K tiles, §7).
2. **Decode-specific weight packing** — highest-leverage on the Q8_0 attention/GDN weights (3.4 GiB
   of 5.45 GiB/token); IQ4_NL blocks are 32 weights vs IQ3_S 256 — K=640 needs no 256-element padding.
3. **Register/occupancy-aware GEMV tiling** — the 16-column WMMA waste warning stands; wave32 means
   no wave64 fallback; check VGPR spills and LDS bank conflicts before persistence.

## 7. The first kernel to build (concrete), after the E prototype

**Sequencing note (second Codex review, accepted):** prototype **MTP at depth 2 and 4 first** — it
needs no new kernels, the draft model is staged, and its ideal weight-traffic bound (1.67–2.54×)
dwarfs anything D′ can promise provisionally. Build D′ after the ablation (§5) confirms the MoE chain
actually costs enough to matter.

**D′-phase-1: fused MoE decode GEMV chain for gfx1151, batch-1, on `pwilkin/llama.cpp@strix-halo` —
without split-K.**

- **Why no split-K (correctness boundary):** gate/up K-partials must be fully summed before the
  SiLU-mul, and ordinary atomics cannot provide that global ordering inside one kernel. Full-K tiles
  keep the fusion legal and the numerics bit-comparable.
- **Stage 1 — `moe_fused_up` (replaces gate GEMV + up GEMV + SiLU-mul, 2→1 launches):**
  grid = 10 selected experts × (640/16..32 paired rows) = **200–400 CTAs**, 4 warps (wave32) each;
  each CTA owns 16–32 paired output rows across the **full K=2560**; gate and up weights are read in
  the same K loop (paired rows, contiguous), SiLU-mul applied in registers, `h_e` written once.
- **Stage 2 — `moe_fused_down_reduce` (replaces down GEMV + weighted reduction, 2→1 launches):**
  grid = 2560 output rows / 32–64 rows = **800–400 CTAs** over full K=640, each CTA looping the 10
  selected experts, multiplying by the routing weight, accumulating — the weighted reduction is the
  final row pass (replaces `moe_weighted_reduction`). Alternative variant to benchmark: 160 CTAs each
  owning 16 output rows × **all 10 experts** (no inter-CTA reduction at all).
- **What it saves:** 144 launches/token (marginal under replay), the h_e materialize + reduction
  re-read (~24 MiB/token ≈ 0.10–0.13 ms — **small**), and — the part that could matter — contiguous
  full-K row reads instead of per-warp strided block reads. Honest expectation: **low-single-digit
  ms/token**, contingent on the ablation showing the MoE chain is a real cost center.
- **Weight layout prerequisite:** one-time pre-packer reblocking `ffn_{gate,up,down}_exps` into
  (expert, row-tile) order with scales inline — **codebook-preserving** (IQ3_S 256-blocks,
  IQ4_NL 32-blocks; no padding needed at K=640). Sidecar file the loader mmaps; no requantization.
- **Numerics gate:** bit-comparison harness vs the current `mul_mat_vec_q_moe` path on random
  activations before any benchmarking (a changed reduction order requires fresh validation, not just
  the replay-exactness result); graph must stay capture-compatible (no sync nodes).
- **Effort/risk:** ~1–2 weeks for phase-1 + harness; risk: IQ3_S vec_dot throughput on wave32, LDS
  bank conflicts in the reduce, and the possibility the ablation shows the MoE chain was never the
  bottleneck (experts are only ≈20 % of weight traffic).

## 8. Kernel-architecture comparison for THIS hardware

| Engine | Kernel approach | Flash-Next decode on this box | Pros here | Cons here |
| --- | --- | --- | --- | --- |
| **llama.cpp mainline HIP** | generic GGML kernels | not viable at Flash-Next scale (graphs-off instability §4.4; earlier session's A/B "interrupted by host restart") | portable, maintained | no Flash-Next-specific kernels; graphs off by default on HIP |
| **pwilkin strix-halo fork** (this work's base) | hand-written gfx1151: tiled GDN (prefill), QSA sparse attention, HC fusions, bf16 WMMA dequant GEMM, lazy PLE, fused MoE MMVQ, **HIP graphs over DXG work** | **12–15 t/s (p0) `[MEAS]`, 6.97 @36k**; prefill 300 t/s @36k | only open engine with Flash-Next-targeted kernels that runs on Windows/WSL; graphs replay works; MIT; we can patch (did) | decode still 3–4× off the weight ceiling; graphs-off unusable (also a robustness cliff); no PM4 replay path over DXG |
| **Halogen** (closed) | own .hgn; **0.7.0+ BYO GGUF: loads our exact UD-IQ4_XS** (lossless repack — "the file's own quantized values, moved, not requantized" — + on-disk cache); i4l (QuaRot W4A4) / q4c / fp8r internals per chlorine-server's RE | 0.32 t/s streaming here; BYO-GGUF on native Linux: **25.4 t/s serial / 42–45 drafted, prefill ~1,250–1,400 t/s** (their numbers) | fastest published decode; our GGUF now supported, no .hgn needed; quality better than their native 4-bit on this file | **WSL2 explicitly refused (mapping registration rejected); native Linux, ~72 GiB RAM** — dedicated-box only; closed |
| **Ciru (vLLM ROCm10)** | vLLM + DFlash2, batch-N oriented | runs; prefill-oriented | biggest prefill; DFlash2 drafter exists for speculation work | batch-N kernels; server-class memory model; decode-at-1 not its target |
| **chlorine-server** | AGPL clean-room halogen rebuild; bit-exact RE of halogen's formats (i4l Hadamard-rotated W4A4, q4c NVFP4-codebook, fp8r, WMMA iu4 fragment maps, fused dequant-GEMV 12.4×) | ~1 t/s scaffold | kernel-format reference for gfx1151 (AGPL — techniques only, nothing mergeable into the MIT fork) | 27B/.hgn scope; pre-product |
| **myhacsint/kyuz0 Vulkan forks** | Vulkan compute + MTP | 22.1 t/s decode @55k, 100 % MTP acceptance `[MEAS]` | **best measured decode today**; native Windows (no WSL fragility) | Vulkan: no HIP-graph equivalent measured here; fork-locked quant paths; less hackable for kernel R&D |
| **drluoto `strix-halo-vulkan` + FR-Spec MTP head** (via vincentkelleher deployment) | Vulkan/RADV llama.cpp, FR-Spec 3.64 GiB MTP head, froggeric template required | third-party measured on our UD-IQ4_XS: **35.8 t/s gen @0k with MTP (33.5 @32k, 25.7 @128k)**, prefill 570/506/405/231 | best third-party Flash-Next decode in class; native Windows possible; plain GGUF + head | Vulkan-only; GDN cache-fusion corrupts output on 8060S (env-disabled); deployment config, not upstreamed kernels |
| **Laurent ROCmFPX / agentionai fp4** | fp4 dequant kernels | not loadable (fork-locked GGUF types) | fp4 GEMV path exists for gfx1151 | fork-locked; 200k-ctx crash reports |
| **EngramHalo** | QSA + chunked GDN prefill | not tried (native-oriented) | kernel ideas | native-Linux orientation |

**Read:** for the World Engine on THIS box today, the **Windows/Vulkan path (drluoto
`strix-halo-vulkan` + FR-Spec MTP head + froggeric template) measures 35.8 t/s on our exact GGUF** —
2–3× our WSL/HIP numbers, no WSL fragility (founder decision item; theory-prep §7c). For kernel R&D
and the open-source contribution track, stay on **strix-halo + HIP graphs over DXG** for planar
repack, D′, F, G, C; our fork's MTP step should also try the **FR-Spec head** (3.64 GiB GGUF).
**MTP is the speculation baseline to verify (E)** — halogen's drafters on our file give 42–45 t/s.
Concrete fork targets from Halogen's BYO-GGUF run on the same file: **25.4 t/s serial = parity**,
~35 t/s = native-4-bit-dense parity (requires the C-strategy requant), 42–45 = drafted. Halogen 0.8.0
is a one-command native-Linux deployment of our GGUF (theory-prep §7b). Biggest structural WSL
disadvantages: the UMA pinned-memory requirement (weights in WSL RAM, caps KV at depth) and
tonight's unresolved graphs-off question (§4.4).

## 9. What the prior review (Codex "Astra") got wrong / right, updated — and what the second review caught

1. **Wrong — bandwidth model:** 6B active @4.25 bpw → 3.19 GB/token → 63–75 t/s ceiling. Actual:
   **k=10** (GGUF header), Q8_0 attention/GDN, F32 router, Q6_K head → **≈5.85 GB/token → 34–41 t/s
   ceiling**. The "63–75 t/s" ceiling overstates headroom ~2×.
2. **Right — graphs first:** experiment A was the correct first move, and it paid: graphs engage,
   replay stably, submission is solved. What the review could not know: graphs-off mode is not just
   slower, it is **unrunnable at this scale** over DXG.
3. **Partly wrong — "40 CUs idle" MoE premise:** the fork's MoE GEMV has ~800–3,200 warps at batch-1;
   occupancy is not obviously the problem. The D-kernel case still stands but on fusion/traffic
   grounds, and its expected size was **downgraded** by the second review (§6, §7).
4. **Right — MTP expert-union caveat, then refined by the second review:** the union growth is
   *total* traffic, not per-accepted-token inefficiency (0.99×/0.97× at depth 2/4), and experts are
   only ≈20 % of weight traffic — so MTP moved **up** the ranking, ahead of D′.
5. **Right — measure experts/layer split/tensor sizes:** done (§3, §5); router-in-F32 and
   Q8_0-down-4-layers were not in any prior analysis.
6. **Caught by the second review — my errors, fixed above:** (a) summed medians ≠ throughput mean —
   the 52.9 ms median split does not reconcile with the 83.3 ms/65.8 ms mean token times without the
   tail + uninstrumented host work (§5); (b) the "555 GB/s is impossible" claim (§4.3); (c) split-K
   before SiLU-mul is not implementable with plain atomics (§7); (d) QSA top-k selects ~17× fewer
   positions but not necessarily ~17× fewer KV bytes (§6 G row); (e) D′ +20–35 % was a forecast, not
   an attribution — now gated behind the ablation.
7. **New finding (not in any review):** DXG event timing inside replayed graphs returns 0.0 ms for
   every segment (§5) — event-based per-op profiling is closed on this runtime; CPU wall-clock over
   steady replays is the workable instrument.

## 10. Reproduction

```bash
# WSL, ROCm-over-DXG env (paths local to this machine)
source /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/env.sh   # sets VLLM_*/AITER_* + HSA_ENABLE_DXG_DETECTION=1 + UMA
cd /home/revn/strix-llama && git checkout op-timing   # f5daaa3c + LLAMA_OP_TIMING instrumentation

# A/B: graphs on/off (one heavy job at a time; drop caches between arms)
sudo sysctl vm.drop_caches=3
GGML_CUDA_DISABLE_GRAPHS=1 build-hip/bin/llama-bench -m ~/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf -ngl 99 -fa 1 -t 8 -p 0 -n 128 -r 3
build-hip/bin/llama-bench -m ~/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf -ngl 99 -fa 1 -t 8 -p 0 -n 128 -r 3

# graph lifecycle + per-token split (graphs on)
LLAMA_GRAPH_TIMING=1 LLAMA_GRAPH_DIAG=1 build-hip/bin/llama-bench -m ...gguf -ngl 99 -fa 1 -t 8 -p 0 -n 64 -r 1
# per-op in-graph split
LLAMA_OP_TIMING=2 build-hip/bin/llama-bench -m ...gguf -ngl 99 -fa 1 -t 8 -p 0 -n 32 -r 1

# GGUF inventory / bandwidth model
python3 kernel-work/gguf_inventory.py <shard1> <shard2> <shard3> --out inv.json && python3 kernel-work/gguf_summary.py inv.json && python3 kernel-work/layer_detail.py
```

Artifacts: `kernel-work/expA/*.log` (all arms incl. on-p2k and on-ig), `expA-summary.json`,
`gguf-inventory-udiq4xs.json`, `layer-detail.json`, `hipgraph-microtest{,2}.cu`,
`codex-review-raw-20260913.txt`, branch `op-timing` (2 commits on `f5daaa3c`: graphs-off per-op
timing + in-graph event timing; tip builds and runs).

## 11. Session incidents (for the record)

- **Shared-machine confound, documented:** this session ran alongside at least one concurrent actor.
  `.wslconfig` memory changed 76→72 GB (my one edit, restoring the documented safe value) → 92 GB →
  ~80–88 GB during the session; WSL was restarted externally at least twice (once killing a running
  graphs-ON server at 2 s, consistent with a `wsl --shutdown` to apply config); at ~20:35 a
  Docker/containerd stack started inside WSL, after which every fresh llama-server process was
  SIGKILLed within minutes (3 attempts, no OOM traces, including an Ornith control that had run fine
  40 minutes earlier). The graphs-off VM-teardown statistics (§4.4) predate the Docker tenant, and the
  0-deaths-in-41-min graphs-ON exposure makes pure chance unlikely, but the attribution is
  accordingly hedged.
- 5 WSL VM teardowns on Flash-Next + graphs-off attempts (§4.4). Host never went down; pool and
  journal clean after each.
- The IQ4_NL PROJFIX download (shard 7/9 of 9) died with a VM reset and was not restarted; resume it
  (`curl -C -`) when the box is idle if that quant is still wanted.
- One on-t attempt aborted by my own ≥55 GB availability guard during a post-run reclaim window;
  retried cleanly on the next boot.

Second-opinion artifact: `kernel-work/codex-review-raw-20260913.txt` (gpt-6-astra, reasoning effort
high, 45.8k tokens; integrated throughout §1, §5–§7, §9).
