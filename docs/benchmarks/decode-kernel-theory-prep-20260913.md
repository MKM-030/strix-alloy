# Decode-kernel theory prep + overnight runbook (2026-09-13, late evening)

Status: written **without WSL access** (GPU/WSL held by the other session, which is running
Flash-Next). Everything here is theory, arithmetic, design and prepared-but-unverified code. All
re-verification steps are in §8 (the runbook). Companion to `decode-kernel-design-20260913.md`.

---

## 1. Re-interpreting tonight's measurements under the co-tenant hypothesis

The other session was **running Flash-Next under WSL during my measurements**. Two Flash-Next
instances need ~2×61 GiB of pinned (unreclaimable) WSL memory plus KV/compute — no `.wslconfig` value
tried tonight (70–92 GB) can hold both. This changes the interpretation of the session's anomalies:

| Observation | Tonight's reading | Re-interpretation |
| --- | --- | --- |
| 5/5 graphs-off Flash-Next attempts died mid-load (exit 137) | "dxg submission-storm instability at scale" | **Co-tenant memory collision** is now the dominant hypothesis: every failed load was racing another Flash-Next instance for ~61 GiB of pinned memory. Balloon death kills the VM silently (clean `exit.target`, no OOM traces) — matches everything observed. |
| Correctness-server processes SIGKILLed at 2 s–8 min (even Ornith, after ~20:36) | Docker tenant pressure | Same collision mechanism, plus the Docker stack as a second memory tenant. |
| Ornith graphs-off ran clean (19:35) | "small graphs are safe" | Simply a moment when the co-tenant was between loads (21 GiB fits alongside one Flash-Next… barely). |
| 0 teardowns in 41 min of graphs-ON exposure | "graphs-on is safe" | Lucky scheduling, not a property of graphs. |

**What still stands (valid regardless of co-tenant):**
- The graph **mechanics** results: 7,322-node decode graph, capture once, replay with `upd=0` across
  all tokens, submit 0.3 ms vs 13.6 ms direct, hostgap/submit/gpu_wait *structure*. These are
  host-side and relative measurements from single-process runs.
- The micro-test correctness results (bit-exact replay).
- The GGUF inventory and the byte model (pure file parsing).

**What is now confounded and must be re-measured on an exclusive box:**
- The absolute `gpu_wait ≈ 49 ms` (co-tenant GPU contention could inflate it — although a *second*
  Flash-Next could not have been resident at the same time, its **loads** (disk paging through the
  same memory controller) and its **decode** (if our runs overlapped only with its load phases) could
  still have inflated memory latency; the relative A/B stays valid, absolutes don't).
- The graphs-off A/B number — **the central open question of experiment A**. It must be re-attempted
  exactly once on an exclusive, freshly-booted box (§8 step 3). If it dies *with nothing else
  running*, the dxg-instability finding becomes real; if it completes, we finally have the true A/B.

**New operational law for this machine (survives every hypothesis):** *one Flash-Next instance per
box, ever.* Coordinate the two sessions through the founder; a second instance cannot fit, and its
failure mode is a silent VM teardown that kills both sessions' work.

## 2. Cost structure of the 49 ms — the arithmetic closes

The exact byte model (§3 of the design doc) decomposes the measured GPU time cleanly. At the
**effective bandwidth implied by the measurement** (5.85 GB weights / 49 ms = **119 GB/s**), every
bucket's predicted time sums to the measurement — there is **no pathological outlier kernel**; the
whole pipeline runs at a uniform ≈55 % of the 200 GB/s low-end ideal:

| Bucket | Weight bytes/token | Ideal @200–240 GB/s | At measured 119 GB/s | Nodes |
| --- | ---: | ---: | ---: | ---: |
| Attention + GDN weights (Q8_0) | 3.645 GB | 15.2–18.2 ms | **30.6 ms** | ≈1,000 |
| Routed experts (k=10, IQ3_S/IQ4_NL) | 1.14 GB | 4.8–5.7 ms | **9.6 ms** | ≈240 |
| Shared expert + router (F32) | 0.503 GB | 2.1–2.5 ms | **4.2 ms** | ≈96 |
| Output head (Q6_K, 248k vocab) | 0.537 GB | 2.2–2.7 ms | **4.5 ms** | 1 |
| **Total** | **5.85 GB** | **24.3–29.1 ms** | **≈48.9 ms ✓** | 7,322 |

Implications, in order of leverage:

1. **The attention/GDN Q8_0 bucket (3.645 GB, 30.6 ms) is the biggest target** — 62 % of decode time.
   A uniform bandwidth uplift (better Q8_0 GEMV: wider contiguous loads, more ILP, dp4a paths,
   packing) moves the whole bucket. A Q8_0→fp4 requant of only this bucket would cut its bytes ~45 %
   (ideal −7.6–9.1 ms; realistic ~half that at the same effective bandwidth).
2. **D′ (fused MoE chain) ceiling is ≈4–5 ms**: the expert bucket's excess over ideal is only
   9.6 − 4.8..5.7 = ~4–4.9 ms *even if* bandwidth-limited; launch/dispatch savings are ≲0.3 ms
   (240 nodes × ~1 µs device dispatch) and the D2D fusion saving is ≈0.1–0.13 ms. This confirms the
   Codex downgrade: D′ is a **small, clean win**, not the headline.
3. **MTP is the only strategy that attacks the whole 49 ms at once** (amortizes the 4.71 GB
   non-expert traffic across drafted tokens) — see §5. It should be prototyped first.
4. **Raising effective bandwidth is the cross-cutting theme.** 119 GB/s on an LPDDR5X platform whose
   copy ceiling is 200–240 GB/s means the weight-reading GEMVs are latency/ILP-limited, not DRAM-
   limited. The op micro-bench (§3) tells us *which* GEMVs are worst; the fix set is: weight layout
   for wave32-contiguous reads, dp4a/integer-dot where the quant format allows, occupancy tuning
   (VGPR budget), and splitting the F32 router (0.503 GB, F32 reads = 2× the bytes of bf16) into
   bf16.

## 2b. The 34-byte stride: why the GEMVs run at 119 GB/s, and the planar-repack fix

The uniform ~55 %-of-ceiling across all buckets has a concrete, testable candidate cause in the
batch-1 GEMV path: **GGML quant blocks are interleaved (AoS) with non-power-of-2 sizes**, and the
MMVQ kernels walk them with one block per lane:

| Type | Block (AoS) | Size | Alignment | Warp of 32 lanes reads blocks kbx…kbx+31 at stride… |
| --- | --- | ---: | --- | --- |
| Q8_0 | d(2B) + qs[32] | **34 B** | 2 B | 34 B → every lane's 32-B payload straddles cache lines; ~35 % of each 64-B sector wasted on average |
| Q8_1 | d+d(4B) + qs[32] + sums[8] | 44 B | 4 B | 44 B stride, same disease |
| IQ4_NL | d(2B) + qs[16] | 18 B | 2 B | 18 B stride |
| IQ3_S | d + qs[64]+qh+signs+scales | 110 B | 2 B | 110 B stride |
| IQ4_XS | d + sh + sl + qs | 136 B | 8 B | 136 B stride (best of the lot, still not 64/128-aligned) |

A GEMV is pure weight streaming — the arithmetic (dp4a on int8 after Q8_1 activation quant) is
negligible — so its time should be ≈bytes/DRAM-bandwidth. At 34-B strided per-lane reads, sectors are
partially wasted and the LSU issues more transactions than necessary, which is exactly the "uniform
119 GB/s instead of ~200" signature. This also explains why the fork's *prefill* (MMQ/MFMA tile path,
different access pattern) is good while batch-1 decode lags.

**Fix: planar (SoA) repack — zero extra bytes, numerics bit-identical.** For Q8_0, store all
`qs` bytes contiguously ([n_blocks][32] uint8) and all `d` scales contiguously ([n_blocks] f16).
Then a warp of 32 lanes reads: 1 KB of contiguous qs + one 64-B contiguous ds line — both perfectly
coalesced. Same d, same q values, same K-loop order ⇒ bit-identical results by construction (still
run the harness). Apply first to the **attention/GDN Q8_0 weights (3.645 GB/token, 30.6 ms bucket)**,
then the MoE down tensors (IQ4_NL: planar qs[16]+d), then IQ3_S gate/up (planar
qs/qh/signs/scales/d streams) inside D′'s repacker.

Expected: if planar + dp4a lifts the Q8_0 bucket from 119 to 150–180 GB/s effective, decode at p0
goes from ≈49 ms to ≈36–40 ms → **+20–30 % decode without speculation**, and it composes with MTP.
This becomes the primary kernel target if the op micro-bench (§3) confirms the per-op effective GB/s
pattern; the sidecar-repack mechanism is the same one D′ already needs (§4), so the two share
infrastructure.

Micro-bench addition for tonight: the harness as written measures AoS (the status quo). The planar
comparison needs the new kernel — so the decision path is: (1) micro-bench confirms per-op GB/s;
(2) build one planar Q8_0 GEMV kernel for the single biggest tensor (attn_qkv, 26.56 MB × 48);
(3) re-bench that op through both layouts. One kernel, one repack, one number.

## 3. The op micro-bench (prepared, uncompiled — `kernel-work/op-microbench.cpp`)

Standalone program: links the fork's `libggml*`, builds one compute graph per op family at Flash-Next
**decode shapes**, fills weights with random bytes (timing-valid, numerics-invalid by design), and
wall-clocks 100–200 synchronous iterations per op — no graphs needed, no 87 GiB model, ~600 MB of
weights total. Because it never builds the full 7,322-node graph, it sidesteps both the graphs-off
instability question and the co-tenant scale problem (it fits alongside almost anything).

Ops and shapes (all batch-1, k=10):

| Op | Shape (src0) | Type | Bytes read/iter | In-model equivalent |
| --- | --- | --- | ---: | --- |
| moe gate+up | [2560, 640, 512] | IQ3_S | 14.08 MB | 1 of 48 layers |
| moe down (IQ4_NL) | [640, 2560, 512] | IQ4_NL | 8.70 MB | 43 layers |
| moe down (Q8_0) | [640, 2560, 512] | Q8_0 | 17.41 MB | 4–5 layers |
| attn_qkv GEMV | [2560, 10240] | Q8_0 | 26.56 MB | ×48 |
| attn_gate GEMV | [2560, 6144] | Q8_0 | 15.94 MB | ×48 |
| ssm_out GEMV | [6144, 2560] | Q8_0 | 15.94 MB | ×48 |
| hc up+down | [320,10240]+[10240,320] | Q8_0 | 6.64 MB | ×48 |
| router GEMV | [2560, 512] | F32 | 5.00 MB | ×48 |
| output head | [2560, 248320] | Q6_K | 500 MB | ×1 |

Outputs: µs/iter per op, effective GB/s per op, and a predicted per-token total to compare against the
measured 49 ms. **Decision rule:** any op family whose effective GB/s is far below the others is the
packing/ILP target; if all are uniform ≈119 GB/s, the fix is architectural (layout+integer-dot across
the board) and D′ stays small. Also run the same table with `-n 8` (batch 8) to see the batch-scaling
curve for the MTP verify pass.

Build (when WSL is free):

```bash
hipcc -O2 -o ~/kernel-work/op-microbench ~/kernel-work/op-microbench.cpp \
  -I/home/revn/strix-llama/ggml/include \
  -L/home/revn/strix-llama/build-hip/bin -lggml -lggml-base -lggml-cpu -lggml-hip \
  -Wl,-rpath,/home/revn/strix-llama/build-hip/bin
LD_LIBRARY_PATH=$HOME/strix-llama/build-hip/bin ~/kernel-work/op-microbench
```

Risk notes: written blind against the public ggml API (ggml_init no_alloc ctx + backend alloc +
`ggml_build_forward_expand` + `ggml_backend_graph_compute`); needs one smoke run on the Ornith
shapes first (§8 step 4). If `ggml_backend_alloc_ctx_tensors` semantics differ in this fork, fall
back to `ggml_backend_alloc_buffer` + `ggml_tensor_malloc` per tensor.

## 4. D′ kernel theory (fused MoE decode chain), post-downgrade

Scope unchanged from the design doc §7 (two kernels: fused gate/up+SiLU-mul → h_e; down + weighted
reduction), **no split-K** (partials must fully sum before SiLU-mul; atomics cannot order that inside
one kernel). What theory adds:

- **Per-stage bytes and time targets** (per layer, k=10): gate/up 14.08 MB → 70 µs @200 GB/s; down
  IQ4_NL 8.70 MB → 44 µs; down Q8_0 17.41 MB → 87 µs. Whole-model expert bucket: 4.8–5.8 ms ideal vs
  ≈9.6 ms at today's effective bandwidth → **D′ total upside ≈4–5 ms/token (≈+8–10 % at p0)**, only if
  the micro-bench shows the expert GEMVs are bandwidth-limited (not latency-limited). If they are
  latency-limited (likely at 70 µs/layer across 200–400 CTAs — each CTA reads only ~35 KB), the
  better lever is **coalescing the reads across CTAs** (row-major expert weights are already
  contiguous per expert; the mmvq kernel's per-warp strided block reads are the inefficiency).
- **Occupancy plan:** 200–400 CTAs × 4 warps = 800–1,600 warps over 40 CUs = 20–40 warps/CU —
  healthy. Register budget: reuse the fork's existing `vec_dot_q_*` device functions (IQ3_S codebook
  lookup is register-hungry); target ≤128 VGPRs/thread, verify with the compiler's `-W`-style VGPR
  report; keep the h_e staging (640 f32 = 2.5 KB) in registers/LDS per expert-tile.
- **Repack format (concrete):** one new tensor per layer, `blk.N.ffn_gate_up_exps.fused`, same
  quant type as source, shape [512 experts][640 rows][2 × 2560] where each row-pair is
  (gate_row, up_row) interleaved. 2560 cols = 80 IQ3_S blocks per row → block alignment survives the
  interleave. Down stays as-is (its own tensor). Sidecar GGUF; loader falls back to unfused tensors
  when absent. Zero requantization, byte-preserving permutation → numerics identical by construction
  if the kernel reads paired rows (still run the bit-comparison harness).
- **Verdict:** build **after** the micro-bench + MTP prototype. It is the third-priority kernel
  target; the attention/GDN Q8_0 GEMV uplift (62 % of time) outranks it.

## 5. MTP theory (k=10) and the prototype plan

**Expert-union arithmetic** (independent-routing approximation, E[union] = 512·(1−(1−10/512)^d)):

| Depth d | E[union] | Expert traffic ×single | Expert bytes / accepted token (perfect accept) |
| ---: | ---: | ---: | ---: |
| 1 | 10.0 | 1.00× | 1.00× |
| 2 | 19.8 | 1.98× | 0.99× |
| 4 | 38.9 | 3.89× | 0.97× |
| 8 | 74.7 | 7.47× | 0.93× |

**Whole-model traffic per accepted token** (perfect acceptance, batched verify — non-expert weights
read once per verify block, experts read as the union):

- depth 2: 4.71/2 + 1.13 = **3.49 GB** → **1.68×** ideal weight-traffic speedup
- depth 4: 4.71/4 + 1.11 = **2.29 GB** → **2.56×**
- depth 8: 4.71/8 + 1.09 = **1.68 GB** → **3.48×**

At tonight's effective 119 GB/s and 100 % acceptance, depth 4 would take ≈19–20 ms/accepted-token of
weight time → **~2.5× decode**, IF the fork's MTP verify (a) batches the drafted tokens into the same
graphs (M=5-row GEMVs — batch also *improves* bandwidth), (b) keeps the GDN recurrence correct across
the batch (the generic GDN kernel handles n_tokens < 16 as a batch — the tiled one needs ≥16, so
verify runs the generic path: correct but slower per token), and (c) rolls back state exactly on
rejection.

**Sensitivity to acceptance (depth 4, geometric acceptance):** 100 % → 2.56×; 70 % → (4.71+4.43×(0.7
adjusted union))/… ≈ 1.6–1.8×; 50 % → ≈1.2×; the crossover where MTP stops paying is ≈35–45 %
acceptance at depth 4. The 100 % acceptance observed on the *Vulkan* build must be re-measured here
(it was greedy decoding there; greedy verify makes output **identical** to non-spec at temp 0 — that
identity is itself the correctness test).

**Prototype runbook (no new kernels needed):**

1. Draft model staged at `/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf`
   (verify; else `/mnt/c/AI/models/qwen38-flash/mtp-Qwen3.8-Flash-Next-Q8_0.gguf`).
2. Server: fork `llama-server -m <flash-next> -md <draft> -ngl 99 -fa on --spec-type draft-mtp
   --spec-draft-model <draft> -c 4096 -b 2048 -ub 2048 --no-webui` (verify the fork's exact flag
   names in `common/arg.cpp` first — the sharing draft used `--spec-type draft-mtp`; depth knobs:
   look for `--spec-draft-n-max`/`--spec-p-min` or equivalents).
3. **Correctness gate:** temp 0 greedy with spec ON vs OFF (same seed): outputs must be **identical**
   (greedy verify identity). If not, the implementation is not greedy-exact → do not trust its
   acceptance numbers; inspect rollback (GDN state, conv cache, KV pages, positional offsets, PLE
   n-gram context).
4. Sweep draft depth 1–4 (or the fork's knob), measure: accepted-token rate from the log, t/s at
   p=0 and @2k, and (log-derived) per-verify-block expert-union if printable.
5. Compare against the non-spec exclusive-box baseline from §8 step 2/3.

## 6. PLE hot-row design (F)

Facts: table = 320M rows × 160 dim IQ4_NL = **90 B/row**, 26.8 GiB, `per_layer_token_embd.weight`,
paged by demand-faulted mmap (bench) or explicit preads (server `--lazy-mode on-direct`, WSL-
supported). Per token the PLE gather touches only a few rows (heads_per_ngram = 8 ⇒ O(8–16) rows ≈
0.7–1.4 KB quantized) — **bytes are trivial; the cost is fault/serialization latency** (measured
hostgap growth 3.4 → 8.6 ms p0→2k ctx ⇒ ≈5 ms/token attributable).

Design (three layers, cheapest first):

1. **Overlap (no cache):** the row IDs for token t+1 are known as soon as sampling finishes — issue
   the preads immediately after sampling and complete them before `cudaGraphLaunch`. The GPU has
   ~49 ms of work to hide under; NVMe pread (~10–50 µs warm) disappears entirely. Expected: the
   5.2 ms hostgap growth → ~0. Requires hooking `llama-lazy-reader::gather` behind an async worker +
   adding a "prefetch(ids)" call in the sampling path.
2. **Hot-row cache:** open-addressing hash row_id → 90 B quantized row, 128 MiB (≈1.5 M rows, 0.5 %
   of the table) + a small pinned staging ring for the current gather. Natural-text n-gram rows reuse
   heavily; expected hit rate >90 % after warmup (measure first — add two counters to the reader).
3. **Device-side micro-cache** (only if 1+2 insufficient): last 8–16 k rows resident on device
   (0.7–1.4 MiB bf16) with an on-device hash — probably unnecessary given 1+2.

Note: none of this needs the 26.8 GiB resident; do **not** try to cache the table in RAM (it would
collide with the weights' pinned memory).

## 7. Operator-family ablation (only if the micro-bench is inconclusive)

If per-op costs from §3 don't reconcile with the in-model 49 ms (co-tenant contention, interaction
effects), the in-graph ablation attributes them: patch the fork (mirroring the `op-timing` branch
pattern — same anchors, `ggml-cuda.cu`) with `LLAMA_ABLATION=real|load|stub` applied to the
`mul_mat_id` families:

- **load** variant: same grid mapping as `mul_mat_vec_q_moe`, but each CTA reads its expert's byte
  range (ids read on-device) and atomicXors into a scratch — same bytes, no vec_dot arithmetic.
- **stub** variant: minimal kernel writing zeros to dst (dependency-preserving, reads nothing).
- real − load = dequant/compute; load − stub = memory-subsystem cost; stub = scheduling/dispatch.
- All variants must stay graph-capturable (no syncs). Written-blind risk is higher than the timing
  patches; smoke-test on Ornith before Flash-Next. Prefer the micro-bench (§3) — it needs no fork
  changes and no 87 GiB model.

## 7b. Chlorine-server + Halogen BYO-GGUF intelligence (2026-09-13, late)

Two related r/StrixHalo announcements examined (sources: [chlorine-server
repo](https://github.com/Heretek-AI/chlorine-server), [commit
feed](https://github.com/Heretek-AI/chlorine-server/commits/main.atom), its
`docs/halogen/KERNELS-DEQUANT.md` and `ARCHITECTURE.md`, and the [Halogen 0.7.0 BYO GGUF
post](https://www.reddit.com/r/StrixHalo/comments/1wf9joo/byo_gguf_to_halogen_070/) →
[halogen-flash-server#bring-your-own-gguf](https://github.com/peonist-ai/halogen-flash-server#bring-your-own-gguf)).

### 9.1 chlorine-server (Heretek-AI, AGPL-3.0) — a bit-exact reverse-engineering lab for halogen

Clean-room rebuild of the closed halogen 0.1.3 engine (Qwen3.8-27B, .hgn, token-port protocol).
Still ~1 t/s scaffold, but its commit history documents **halogen's actual weight formats and kernel
techniques**, recovered bit-exactly:

- **`i4l` = Hadamard-rotated int4 (QuaRot-style)**: weights rotated by an orthogonal 256-block
  Hadamard at quantization; int4 two's-complement codes; fp16 scales per 256-chunk = absmax/7
  exactly (8-bit mantissa, tensor-shared exponent 2⁻⁸); **GPTQ act-order k-permutation**; activations
  rotated by the same H at runtime via `k_actq` — an xor-butterfly **fast Hadamard transform in f32**
  (64 lanes × bf16 loads → u8 codes + u16 scales). `W'·a' = W·a` exactly → **W4A4** with integer dot.
- **`q4c` = NVFP4-style codebook int4** (16-entry f32 codebook = ±e2m1×c; e4m3 scales per 16
  elements, per-row interleaved) — the GEMV twin; **each i4l tensor ships with a q4c shadow** (gemm
  path vs gemv path both resident → the ~18 GB weight pool).
- **`fp8r`** = row-major fp8 e4m3 + per-row bf16 scales, absmax/scale = 448 exactly.
- **WMMA iu4 fragment maps for gfx1151**, documented thread-by-thread (D 16×16 i32; k-encoding =
  8·vgpr + nibble), and — the key design move — **weights stored [N,K]-major "natural" so the WMMA
  fragment reads the global layout RAW** (the 16-byte global record is one n-row's 16 consecutive k's).
  Layout designed around the instruction, zero shuffling in the kernel.
- **Fused dequant-GEMV for decode: 13.6 s → 1.1 s per token (12.4×)** in their rebuild — the single
  biggest lever they found, confirming the fused-dequant-GEMV direction.
- Engine behavior: mmap'd .hgn (demand paging), KV pool + LM-cache of prefill snapshots auto-sized
  from MemAvailable, batch-1 serial with 503 for a second request, MTP + DFlash2 drafters,
  **"batched decode and a drafter cannot share the DeltaNet ring"** (speculation vs batch-parallel
  decode are mutually exclusive — relevant to our MTP plans).

**License caution:** AGPL-3.0. Their *docs describe halogen's formats* (halogen's EULA permits RE);
reading them is fine, **copying their code into the MIT strix-halo fork is not** — techniques only.

### 9.2 Halogen 0.7.0/0.8.0 "Bring Your Own GGUF" — our exact file, native Linux only

The closed flash server now loads **llama.cpp GGUFs directly**, and for **exactly our model**:
Qwen3.8-Flash-Next, with **unsloth UD-IQ4_XS as the tested/reference file**. Accepted types: the
IQ4_NL/IQ4_XS/IQ3_S/Q4_0 family (experts), Q8_0 (dense), Q6_K (output) — precisely our quant mix.
Details that matter to us:

- **"Losslessly repacks every tensor into the layouts its kernels read — the file's own quantized
  values, moved, not requantized"**, 18 s at startup, with an optional validated on-disk repack cache
  (~70 GiB) and a `--repack` export. **This is our §2b/§4 planar-repack design, shipped in the
  closed engine** — independent confirmation that layout repacking (not requantization) is where the
  decode win lives, and that the sidecar-cache pattern works.
- **Numbers on our file** (reference Strix Halo machine, MTP on): prefill within 1 % of the native
  .hgn (1,246 / 1,423 t/s @8k/32k); **serial decode 25.4 t/s** short-context (~28 % slower than the
  native 4-bit trunk's 35.4, because the GGUF keeps the dense layers at Q8_0 → +~2 GB/token);
  coding-agent turns with both drafters 42–45 t/s; quality *better* than their own calibrated 4-bit
  checkpoint (PPL −0.7…−2.1 %). vs stock llama.cpp on the same file/machine: 1.1× serial decode
  short-ctx, 1.3× @32k, 1.9× drafted coding turns.
- The GGUF carries no draft head → a **1.4 GiB MTP head sidecar** is loaded (`qwen38-flash-next-mtp.hgn`);
  prose draft acceptance drops to 45 % (vs 59 % on native trunk); code acceptance unchanged.
- Memory: ~**72 GiB RAM** for repacked weights; KV pool in unified memory via **KFD/GTT**.
- **WSL2 is explicitly refused** ("read-only mapping registration is rejected there") — native Linux,
  kernel 7.0+, amdgpu/KFD, podman run with /dev/kfd. **Nothing changes for this split box**; halogen
  stays a dedicated-native-Linux-machine option — but now **without any .hgn download**: our existing
  GGUF + a 1.4 GiB head works.

### 9.3 What this changes in our plan

1. **Planar-repack thesis validated by both engines.** Halogen's entire GGUF path is "repack the
   file's own values into kernel-native layouts" — the same design as our §2b. Their published
   numbers let us set concrete targets (below).
2. **The bandwidth gap, corrected and sharpened.** LPDDR5X on Strix Halo is 256 GB/s theoretical
   (~230–240 achievable — the brief's 200–240 was conservative). Halogen's GGUF-path serial decode
   implies **~230 GB/s effective** weight streaming (5.85 GB / 25.4 t/s), i.e. ≈90 % of achievable —
   while our fork measures **119 GB/s (≈46 %)**. The 2× gap is coalescing/layout, exactly what
   planar-repack addresses. Ceiling at perfect bandwidth: **~44 t/s** on our file.
3. **Concrete parity targets for our fork** (same file, same machine class): 25.4 t/s serial =
   halogen-GGUF parity; ~35 t/s = halogen-native (requires 4-bit dense — see 4); 42–45 t/s = with
   drafters. Our current 12–15 t/s sits at ~half of halogen-GGUF parity.
4. **The dense-layer quant is the native-vs-GGUF delta**: native .hgn carries 4-bit (i4l/fp8r) dense
   weights (~2 GB/token less than our Q8_0 dense). That elevates the **C-strategy** (requantize
   attention/GDN Q8_0 → fp8r/i4l-style) from "nice" to "halogen-native parity" — after planar + MTP,
   since halogen's own GGUF path chose to keep Q8_0 dense and eat the 28 %.
5. **DFlash2/MTP + "prompt lookup" drafter works on the GGUF path** (byte-identical-to-greedy
   guaranteed); our fork's MTP head GGUF already exists — no new artifacts needed for step 5 of the
   runbook.
6. **For the founder (infrastructure decision, not code):** a dedicated native-Linux box running
   halogen 0.8.0 against our existing GGUF would deliver ~1,250–1,400 t/s prefill and 25–45 t/s decode
   today, no quantization work. On this split Windows/WSL box, our fork remains the only path.

### 9.4 Update to the engine-comparison table (design doc §7)

| Engine | Correction/upgrade |
| --- | --- |
| Halogen | **0.7.0+ BYO GGUF: loads our exact UD-IQ4_XS** (Flash-Next), lossless repack + cache, 25.4 t/s serial / 42–45 drafted, prefill ~1,250–1,400 t/s; **still native-Linux-only (WSL2 refused)**, ~72 GiB RAM; W4A4 i4l/q4c/fp8r internals per chlorine's RE |
| chlorine-server | Bit-exact RE of halogen's formats (i4l QuaRot W4A4, q4c NVFP4-codebook, fp8r, WMMA iu4 fragment maps, fused dequant-GEMV 12.4×); engine itself still ~1 t/s, 27B/.hgn only; **AGPL — reference, not mergeable into MIT fork** |

## 7c. Ecosystem scan (2026-09-13, late): drluoto Vulkan fork + FR-Spec MTP, pwilkin's lab notes, froggeric templates, harness quality

Sources: [vincentkelleher/qwen3.8-flash-next-halo](https://github.com/vincentkelleher/qwen3.8-flash-next-halo)
(a docker-compose deployment with benchmarks), [drluoto/llama.cpp](https://github.com/drluoto/llama.cpp)
(`strix-halo-vulkan` branch, pinned `ba5354d46`), [pwilkin.github.io/strix-halo](https://pwilkin.github.io/strix-halo/)
(the fork author's lab site), [froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates),
and r/Dimaginar community posts.

### 7c.1 drluoto `strix-halo-vulkan` + FR-Spec MTP head — best measured Flash-Next decode in class

vincentkelleher's deployment (docker, Vulkan/RADV — **no ROCm/HIP**) runs **our exact UD-IQ4_XS
GGUF** with drluoto's branch — "the only build that loads the FR-Spec MTP head"
(`mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf`, 3.64 GiB). Measured (llama-benchy, 2,048-token
prompts, 3 runs, **MTP on**, `--spec-draft-n-max 3`):

| Context | Prefill t/s | Generation t/s |
| ---: | ---: | ---: |
| 0 | 570.8 | **35.8** |
| 8,192 | 506.1 | **36.7** |
| 32,768 | 405.4 | 33.5 |
| 128,000 | 230.9 | 25.7 |

Operational notes that transfer to any engine: **f16 KV is required for acceptance** ("a quantized
cache costs acceptance" — this demotes the KV-Q8 strategy G further whenever MTP is on); `-lm dio`
(O_DIRECT loading, never with `--no-mmap`); `--ctx-checkpoints 8`; `--parallel 2` (~132k tokens/slot);
kernel args for 128 GB hosts (`amdgpu.gttsize=126976 ttm.pages_limit=32505856`); and a cautionary
bug: `GGML_VK_DISABLE_GDN_CACHE_FUSION=1` — a GDN cache-fusion kernel **corrupts output on the
8060S** in the Vulkan path. Fusion bugs are real on this GPU; our fork's fused kernels must keep the
bit-comparison harness (they do).
**Because this is Vulkan/RADV, it runs natively on Windows** — the same class of setup as our earlier
myhacsint measurement (22.1 t/s with MTP). 35.8 t/s with the FR-Spec head on our GGUF is the best
third-party Flash-Next decode published for this hardware class, and it is available to the founder
**without WSL**.

### 7c.2 pwilkin's lab site — the retained-PM4 design, honestly quantified

The fork author's site (we build on his fork) confirms and extends our experiment-A picture:

- Standard ROCm runtime "still re-encodes the PM4 packets for every node on every launch" — graphs
  materialize packets once via **vendor APIs** (`hsa_ven_amd_graph_command_list_create`,
  `..._materialize_packet`, `..._get_capabilities`) + packet-batch merging; 5 commits on a
  `rocm-systems` branch, experimental, env-gated, validated on two targets. **The retained path pays
  off in decode**; and "for Flash prefill, graphs never engage since capture needs two consecutive
  graphs with unchanged properties, and each prefill chunk shape occurs once" — matches our graph
  analysis exactly.
- His own Flash-Next numbers (93 GiB IQ4_NL, native Linux, **no speculation**): prefill 1,204 t/s
  @0k (1,086 @40k — 90 % retained, sparse attention working); **decode 26.28 t/s @0k, 16.63 @40k** —
  and "decode runs roughly 8 % below what the same kernels achieve out of tree" with the retained
  runtime — an **acknowledged open gap**. So the author's native path is 26.3, retained-PM4 ≈ +8 %,
  and our WSL number (12–15) is ~2× below native for reasons the co-tenant contamination does not
  fully explain (quant/layout and DXG-vs-KFD remain candidates; the runbook's step 1/2 re-measurement
  is the discriminator).
- Mainline tracks relevant to us: RDNA3 MMA flash attention (#22880), RDNA3/RDNA3.5 MMQ configs
  (#26199/#26284), **routed-MoE MMQ N-tiles on RDNA3 (#28552)**, gfx1151 CI runner (#26544).
- 27B with DFlash2 drafter (IQ4_XS drafter): 60.7 % acceptance, 26.26 t/s — again: speculation is
  where the headline decode lives.

### 7c.3 froggeric fixed chat templates — adopt for every server run

Universal drop-in Jinja covering **Qwen3.8 Flash-Next** (Apache-2.0): fixes duplicated blank
`<think>` blocks in history, hardcoded xhigh reasoning, tool-call crashes on JSON-string arguments,
multiple leading system messages, and guarantees **100 % prefix KV-cache hit rate**. Usage with our
fork's server:

```bash
llama-server ... --jinja --chat-template-file chat_template.jinja --reasoning-format deepseek
```

The drluoto deployment treats it as **required** (server exits without it). Action: drop
`chat_template.jinja` next to our server configs; use it in runbook steps 3/5 (the graphs A/B is
template-invariant, but MTP acceptance and real harness behavior are not).

### 7c.4 Community quality signal (r/Dimaginar) and the harness layer

r/Dimaginar posts (the founder's community) report Flash-Next "feels like a frontier model" when run
with a proper harness — reinforcing that for the World Engine the harness/template layer (fixed chat
template, reasoning routing, tool-call handling) is worth as much as raw t/s, and that decode-speed
work must not trade quality away (acceptance-preserving MTP, f16 KV). Community datapoints for
calibration: 50+ → ~30 t/s @150k on a 5090/192 GB (r/LocalLLaMA), and a Medium writeup claiming
~30 t/s on Windows Strix Halo — both consistent with the 25–36 t/s band the dedicated engines hit.

### 7c.5 Consequences for our plan

1. **Founder decision item (infrastructure):** for the World Engine on THIS box, the **Windows/Vulkan
   path (drluoto branch + FR-Spec head + froggeric template) measures 35.8 t/s today** — 2–3× our
   WSL/HIP numbers, no WSL fragility. Our HIP/kernel research continues as the open-source
   contributions track; it should not block the World Engine choice.
2. **Runbook step 5 upgrade:** try the **FR-Spec MTP head** (3.64 GiB GGUF) in our fork's
   `draft-mtp` path alongside the shared-Q8_0 head — it is a plain GGUF and our fork loads draft
   GGUFs; the FR-Spec head is what the 35.8 t/s measurement used.
3. **G (KV-Q8) demoted harder**: quantized KV costs MTP acceptance (both drluoto and halogen's
   native-vs-GGUF deltas support f16 KV where MTP is on).
4. **Retained-PM4 (native) ≈ +8 %** — real but small; DXG graphs already give us replay; no action.
5. **Mainline PR #28552 (routed-MoE MMQ N-tiles)** is worth reading before building D′ — it may
   already implement part of the MoE decode tiling on RDNA3.

### 7d. Should we build an own Vulkan engine to fix drluoto's prefill? (assessment)

The gap is real: drluoto Vulkan prefill **570 t/s @0k / 405 @32k** vs pwilkin HIP **1,086–1,204** and
Halogen **1,246–1,423** (chlorine has no prefill performance yet — it is a parity project). But
prefill is **compute-bound, not bandwidth-bound**, which changes the lever entirely: at batched
prefill, weights are read once per ubatch, so 570 t/s × ~12 GFLOP/token (6 B active × 2) ≈
**6.8 TFLOPS effective** vs pwilkin's ≈14.5 and Halogen's ≈17.1 — against an 8060S bf16-WMMA peak of
roughly 30 TFLOPS [EST]. So Vulkan runs at ~23 % MFU where the leaders run 41–57 %: **the gap is GEMM/
attention kernel quality and quant-layout, not the Vulkan architecture itself.**

Named causes, cheapest first:

1. **Quant layout (the one we already own):** our WSL HIP fork measured only **300 t/s @36k** on
   UD-IQ4_XS vs the author's **1,086–1,204 on his IQ4_NL "PROJFIX" quant** — the custom layout feeds
   the bf16 WMMA dequant-GEMM path directly (our earlier docs: "the 3–4× gap is the quant"). The
   IQ4_NL download (ilintar) died at shard 7/9; **finishing it and re-benching is a ~3× prefill win
   on the HIP fork for the price of a download**. This also cleanly separates quant-layout effects
   from engine effects in every later comparison.
2. **Missing Flash-Next kernels in the Vulkan path:** the HIP fork's prefill wins are tiled GDN
   (2.37×), QSA sparse attention (1.71×), head-size-256 WMMA FA, HC fusions, lazy PLE (2.75×).
   drluoto's Vulkan branch has a GDN cache-fusion that **corrupts output on the 8060S and is
   disabled**; QSA/FA-256 status unknown. Porting those three kernels to Vulkan compute shaders is
   the real project if Windows-native *prefill* ever becomes a requirement — weeks of shader work
   with an uncertain coopmat ceiling (RADV int8/float cooperative-matrix support on gfx1151 is
   usable but unproven at these tile shapes).
3. **Backend maturity:** llama.cpp's Vulkan coopmat/MMQ pipelines on RDNA3.5 lag the HIP MMQ/WMMA
   paths (the author's own branches — `0cc4m/vulkan-coopmat-int8`, `vulkan-repack`,
   `vulkan-slang-flash-attention` — show this is known and in progress upstream).

**Recommendation:** do **not** build a clean-room Vulkan engine (chlorine-server has spent months
reaching ~1 t/s of parity work; the ecosystem already has four active engines — pwilkin HIP,
drluoto Vulkan, Halogen closed, chlorine AGPL — and moves faster than any of us alone). Instead:

- **Tier 1 (this week, no new code):** resume the IQ4_NL download (shards 7–9), re-bench HIP-fork
  prefill on it; expected ~300 → ~1,000+ t/s on WSL. Also re-bench Vulkan prefill on IQ4_NL if its
  loader accepts it — same question applies there.
- **Tier 2 (contribution, not engine):** feed our findings upstream (graphs diagnostics, planar
  repack, op micro-bench numbers) into pwilkin's HIP fork and drluoto's Vulkan branch; the MoE-decode
  and prefill kernel work lands where the users are.
- **Tier 3 (only if forced):** port GDN-tile/QSA/FA-256 to Vulkan shaders in drluoto's branch if
  long-context *prefill* on Windows-native becomes a hard REV:N requirement. Decode (the NPC-dialogue
  bottleneck) is already solved better there (35.8 t/s) than anything we can build in WSL.

### 7e. The PROJFIX path to Halogen-class speeds (founder decision: focus everything here)

The ilintar **IQ4_NL "PROJFIX" quant is complete on disk** (all 9 shards, 93.16 GiB, plus the
shared-Q8_0 MTP head — the earlier session's curl finished before dying; parsed and validated with
`gguf_inventory.py`, inventory in `gguf-inventory-iq4nl.json`). What PROJFIX actually is, from the
header: **every tensor moved to IQ4_NL — including the attention/GDN projections that unsloth kept
at Q8_0 (8.5 bpw)** — uniform 1,350 MiB/layer experts, all in the layout that feeds the fork's bf16
WMMA dequant-GEMM. Per-tensor comparison (`compare-quants.py`):

| Bucket | unsloth UD-IQ4_XS | ilintar IQ4_NL PROJFIX |
| --- | ---: | ---: |
| attention + GDN weights | 3,476 MiB (Q8_0) | **1,332 MiB (IQ4_NL)** |
| routed experts (all 512) | 55.43 GiB (IQ3_S gate/up + IQ4_NL/Q8_0 down) | 63.28 GiB (uniform IQ4_NL) |
| shared expert | 239 MiB | 124 MiB |
| total file | 87.24 GiB, 4.24 bpw | 93.16 GiB, 4.52 bpw |
| **active bytes / decoded token (k=10)** | **5.44 GiB = 5.84 GB** | **4.30 GiB = 4.61 GB (−21 %)** |

(Exact formula: total − 26.82 GiB PLE − 505/512 of expert bytes − token embedding minus one row.
Sanity check: 5.84 GB at the measured 119 GB/s effective = 49.1 ms — matches the measured gpu_wait.)

**Speed ladder for the founder's goal** (Halogen: 25.4 t/s serial on our GGUF, 35.4 native, 42–45
drafted):

| Configuration | Expected decode |
| --- | --- |
| PROJFIX at our current 119 GB/s effective | **25.8 t/s serial — halogen-GGUF parity from the quant alone** |
| PROJFIX at the author's measured efficiency (~175 GB/s; his 26.28 t/s on this quant) | **30–35 t/s serial — halogen-native class** |
| PROJFIX + MTP (FR-Spec head, depth 3, acceptance 0.45–0.75) | ×1.43–2.00 → **37–50 t/s** |
| PROJFIX + MTP + planar/IXA4 layout work (later, uncertain) | beyond 50 t/s |

The optimization stack, in order (all anchored to this quant):

1. **MTP built in:** the shared-Q8_0 head is staged; the **FR-Spec head
   (`mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf`, the one drluoto's 35.8 t/s run used) is
   downloading** from `drluoto/Qwen3.8-Flash-Next-MTP-GGUF`. Greedy temp-0 identity gate (spec vs
   non-spec must be byte-identical), then depth 2–4 sweep. f16 KV only — quantized KV costs
   acceptance.
2. **froggeric fixed chat template** with `--reasoning-format deepseek` — affects acceptance and the
   harness layer, not just cosmetics.
3. **PLE**: run the server with `--lazy-mode on-direct` (preads are supported on WSL) and add the
   post-sampling prefetch overlap (§6) — worth ~5 ms/token at depth, free.
4. **Sidecar layout work (phase-2):** with PROJFIX there is no Q8_0 bucket left to planar-repack —
   the remaining lever is IQ4_NL itself (18 B AoS blocks) and the expert tensors. Tempered
   expectation (see the §2b caveat below): test via the op micro-bench on `moe_gate_up` before
   building anything.
5. **Memory note:** resident weights are 66.3 GiB (vs 60.4 unsloth) — at 70 GB WSL caps this is
   tight with UMA; ensure cap ≥ 76 GB or trim KV/compute buffers.

Honest caveat added to §2b: the "34-byte stride wastes 35 % of sectors" claim overstates — when 32
lanes read *consecutive* blocks, the union of their loads covers all bytes (transaction *shape*
penalty, not unused bytes), so planar-repack gains are likely 10–30 %, not 2×. The measured 119 GB/s
deficit is spread across kernel ramp, latency, activation traffic and dequant throughput; the
micro-bench (step 4) attributes it.

## 8. Overnight runbook (when the other session releases WSL)

Every step has a gate; abort the sequence rather than share the box. One session, one Flash-Next
instance, ever.

```bash
# STEP 0 — exclusivity gate (go/no-go)
wsl -e bash -c "ps aux | grep -E 'llama|flash|dockerd' | grep -v grep; free -g | head -2"
# GO if: no llama/flash processes, no dockerd, avail >= 55G.
# Also confirm with the founder that the other session is paused.

# STEP 1 — uncontaminated graphs-ON absolutes (~12 min)
wsl -e bash -c "bash /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA-arm.sh on-p0x '' -p 0 -n 128 -r 3"
wsl -e bash -c "bash /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA-arm.sh on-tx 'LLAMA_GRAPH_TIMING=1 LLAMA_GRAPH_DIAG=1' -p 0 -n 64 -r 1"
# Record: tg128, gpu_wait median (compare 49.2 ms), hostgap, submit. If gpu_wait drops materially,
# tonight's earlier absolutes were co-tenant-contaminated — update the design doc.

# STEP 2 — the open A/B: graphs OFF, once, exclusive (~12 min, abort-once rule)
wsl -e bash -c "bash /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/expA-arm.sh off-p0x GGML_CUDA_DISABLE_GRAPHS=1 -p 0 -n 128 -r 3"
# If it dies with NOTHING else running: dxg instability is proven -> document and never retry on this OS config.
# If it completes: this is the true experiment-A number; update the doc.

# STEP 3 — correctness text capture (~15 min ON, +15 OFF if step 2 survived)
wsl -e bash -c "bash /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/correctness-server.sh on /home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf"
# (+ the off arm only if step 2 survived; then diff_correctness.py)

# STEP 4 — op micro-bench (~10 min build+run) -> decides D' and the GEMV-uplift target
wsl -e bash -c "source /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/env.sh && hipcc -O2 -o /home/revn/kernel-work/op-microbench /mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/op-microbench.cpp -I/home/revn/strix-llama/ggml/include -L/home/revn/strix-llama/build-hip/bin -lggml -lggml-base -lggml-cpu -lggml-hip -Wl,-rpath,/home/revn/strix-llama/build-hip/bin && /home/revn/kernel-work/op-microbench"
# Smoke first on smaller shapes if any op errors; fix shapes from the error message.

# STEP 5 — MTP prototype (~30 min incl. loads)
# server command per theory-prep §5; gates: greedy temp-0 identity vs non-spec, then depth sweep 1-4.

# STEP 6 — update decode-kernel-design-20260913.md with: uncontaminated absolutes, the OFF-arm
# outcome, the micro-bench table, MTP numbers. Then the next session decides D' vs GEMV-uplift work.
```

Prepared artifacts (written tonight, **all unverified until step 4+**):
`op-microbench.cpp` (complete source), this runbook, the re-interpreted design doc. The `op-timing`
branch (2 commits on `f5daaa3c`) builds and ran correctly; its in-graph event mode is dead (DXG
returns 0.0) and can be ignored.
