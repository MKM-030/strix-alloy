# Codex prompt — next decode/prefill levers (2026-09-15)

Paste everything below the line into Codex. It is self-contained: every number is measured on one
machine by one operator, and the **negative results are listed explicitly so you do not re-suggest
them**. Where a conclusion is uncertain I say so.

---

You are a GPU-kernel and LLM-inference performance engineer. I run a Strix Halo box as an inference
server and I am trying to find the next real lever. Everything below is measured; I have marked what
is **trustworthy**, what is **closed (negative)**, and what is **open**. Give me a concrete, ranked
plan — and, importantly, **things I have not considered**. Do not re-propose the closed items; if you
think one was closed for the wrong reason, say why with a specific test.

## 1. Hardware and stack (fixed, do not propose changing)

- **AMD Ryzen AI Max+ 395**, Radeon 8060S iGPU (gfx1151, RDNA3.5, **wave32**, 40 CU), 128 GB LPDDR5X
  **unified**, **96 GB dedicated carve** (device pool reports 107.87 GB). Measured sequential-read
  ceiling **235.7 GB/s**, copy 208 GB/s combined.
- **Native Windows** is the fast path (TheRock 10.2 SDK, clang 24.0.0git, `GGML_HIP=ON`). WSL2 works
  but is slower and, critically, **must be shut down during benchmarks** or `vmmemWSL` corrupts
  numbers. No `/dev/kfd`, no PM4 replay. The SDK ships **no profiler** (no rocprof*).
- Fork: `pwilkin/llama.cpp` branch `strix-halo` (our head `891a923a`) + a thin Windows layer. Its
  HIP kernels are heavily customized for this part (an "MMB" large-batch path, fused PLE, sparse QSA
  decode).
- Model **Qwen3.8-Flash-Next**: 177 B MoE, ~6 B active. 48 layers, 512 routed experts (top-k=10) + 1
  shared, FFN width 640, `n_embd` 2560, **4 hyper-connection streams** (low-rank 320), **36
  GatedDeltaNet (linear-attention) + 12 full-attention** layers, **QSA lightning indexer** (top_k
  2048, ratio 4), and a **~27 GiB PLE n-gram table that is disk-paged, never resident**.
- Quant: "PROJFIX" = IQ4_NL nearly everywhere (67.9 GB of routed experts are IQ4_NL). LM head is Q6_K
  [2560, 248320]. MTP draft head = shared Q8_0 sidecar that **borrows the trunk's LM head**.
- Production decode runs **HIP graphs** (dispatch-free). Graphs are worth ~65 ms/token (35 t/s on vs
  10.7 off), so the compute path is already launch-clean.

## 2. Best measured production numbers (TRUSTWORTHY)

Native Windows, WSL down, page cache warm (reps ≥ 1), single instance.

| depth | prefill t/s | serial decode | MTP decode (n-max 2) | MTP acceptance |
| ---: | ---: | ---: | ---: | ---: |
| 1,024 | ~700 | 29.9 | **35.5** | 62.5% |
| 8,192 | ~985 | 28.6 | 30.2 | 54.5% |
| 65,536 | 984 | 28.5 | **35.0** | 74% |
| 131,072 | 688 | 26.9 | 28.8 | 61% |
| 251,904 | 648 | 23.4 | 28.7 | 67% |

Two shapes: `-ub 16384` no drafter (max prefill), `-ub 8192` + shared MTP head (production decode).
**251k context works end to end: ~6.5 min to ingest, then ~29 t/s interactive, no OOM.**

## 3. The central problem: a uniform ~37% bandwidth shortfall (TRUSTWORTHY)

I built an exact byte census of one decode token's read set from the GGUF tensor layout:

| component | GB/token | share |
| --- | ---: | ---: |
| routed experts (top-10 of 512 × 48 layers) | 1.327 | 31.5% |
| attention (qkv/q/k/v/output/gate) | 1.250 | 29.6% |
| output head (Q6_K) | 0.521 | 12.3% |
| hyper-connection (down/up ×4, norm, inject) | 0.367 | 8.7% |
| GDN / linear-attention | 0.330 | 7.8% |
| F32 norms (incl. MoE router `ffn_gate_inp`, F32 [2560,512]) | 0.252 | 6.0% |
| shared expert | 0.133 | 3.2% |
| QSA indexer | 0.039 | 0.9% |
| **total** | **4.219** | 100% |

**Ideal at 235.7 GB/s = 17.9 ms/token (~56 t/s). We run 35 t/s serial = 63% of the ceiling.**

Three independent measurements say the loss is **uniform, not concentrated**:
- byte efficiency is **flat 53–59% across every verify width** (serial, n-max 1, n-max 2, …);
- target round cost is **flat (54–59 ms) across a 16× context span**;
- decode t/s is nearly flat from 1k to 251k (29.9 → 23.4 serial).
- an expert-count ablation gives `target_ms/round = 35.4 + 3.56 × expert_GB`, i.e. experts ≤ 28% of
  the round; the other 72% is independent of expert count but scales with bytes.

My reading: no single component is the culprit, so the inefficiency is **in the quantized matvec
itself** (the fork's IQ4_NL "MMB" path at large T, and its `mmvq`/`mmvf` at decode), OR in something
structural I can't see from the byte census (memory-controller behaviour under ~150 small weight
reads per layer, L2/LDS behaviour, sector utilization on IQ4_NL).

**Ask:** how do I *distinguish* "the kernel is leaving 37% on the table" from "the memory subsystem
simply delivers 63% under this access pattern"? What is the cheapest decisive experiment? We have no
profiler and cannot install one.

## 4. Closed — these are tested negatives, do not re-propose without a new argument

| candidate | measured result |
| --- | --- |
| small-K MMVQ rows-per-block on RDNA3.5 (SixVolts' RDNA4 win) | **inert** — gfx1151 uses the **RDNA2** parameter table whose `calc_nwarps()` returns `nwarps=1`, so the small-K condition can never trigger |
| borrow the **RDNA3.0** MMVQ parameter table on gfx1151 (`nwarps=8`) | **−21% decode**. The RDNA2 table is genuinely the best for this part |
| lower `mmb_min_t` 512→128 so short prompts use the MMB fast path | ~0% change at every size; short-prompt slowness is per-request overhead, not the MMB threshold |
| MMVF 4-deep software-pipelined weight loads for `ncols_dst==1` (the F32 MoE router) | single run +1.9%, **interleaved A/B −0.9%** (noise). Router is only 6% of bytes |
| **QSA indexer depth-dependence** as a decode lever | closed: round cost flat across 16× context |
| **PLE host-side staging** | 0.054% of decode wall — not a lever |
| **FR-Spec 65k draft-vocab trim** (head reads its own 178 MB head vs borrowing the 521 MB Q6_K trunk head) | works, but ~neutral at n-max 2 — the MTP point is not bandwidth-bound |
| n-max 3…8 | monotonically worse (acceptance 86% → 32%) |
| Q6_K bf16 "shadow" costing decode traffic | no: shadow is only read in the MMB path (T ≥ 512), which decode never runs |
| LM head read more than once per forward | no: read 1×, last rows only |

Also closed as *unavailable to us*: a **retained-PM4 command-list runtime** (a ROCm userspace change
the fork author has on bare-metal Linux; we cannot use it on Windows) and **Vulkan-only** features
(the fork author's fastest numbers are Vulkan + FR-Spec; our fork is HIP).

## 5. Open questions I want your judgment on

1. **KV cache dtype.** We run `-ctk f16 -ctv f16`. The 12 full-attention layers hold KV; at 251k the
   cache is material (a large `-c` measurably costs ~15% of shallow prefill — see §6). Would
   **q8_0 KV** be a decode *and* long-context win here, and what is the quality risk on a hybrid
   GDN+attention model? Has anyone measured KV-quant on Qwen3-Next-class hybrids?
2. **The 12 full-attention layers at depth.** Sparse QSA caps attention at top_k 2048, yet long-context
   prefill still drops. Is the drop the KV *write* traffic, the indexer, or something else? What is
   the cheapest way to attribute it without a profiler?
3. **Hyper-connection structure.** 8.7% of bytes are HC weights (4 streams × down/up + norms +
   inject), and 4.6% is the shared expert. Could the HC low-rank projections be **merged or
   pre-multiplied** into fewer, larger matmuls (fewer weight streams, better sector utilization)?
   Is there a layout transform that helps on IQ4_NL?
4. **Draft-head quality.** Acceptance is 50–74% and depth-inconsistent. We have a harness that dumps
   `h_nextn` training data (`llama_set_embeddings_nextn`). If we trained a better MTP head, what is the
   realistic acceptance ceiling at n-max 2, and would it actually move decode t/s given the 80/16/0
   verify/draft/accept split? What training recipe would you use (data, objective, rank)?
5. **Anything structural I have missed.** Given the byte census and the closed list, where would you
   look that is not on my list at all? Examples of the *kind* of thing I mean: a different kernel
   decomposition for IQ4_NL GEMV, batched multi-layer weight streaming, expert-weight L2 pinning,
   async copy pipelining, a fused attention+GDN schedule, activation quantization to cut the F32
   router/norm traffic, or a graph-level reordering. Tell me which of these are real and which are
   noise, and in what order to try them.

## 6. Prefill shape (partly open)

Prefill peaks in the **32k–65k** band (~985 t/s) and settles to ~650–690 t/s at 128k–251k. A larger
`-c` costs ~15% of shallow prefill (862 vs 1021 t/s @16k for `-c 262144` vs `-c 32768`). Some of the
128k+ drop may be a **cold-cache artifact** (those rows were single-rep; rep-0 is known cold — at 16k
rep0=500 vs rep1=862), which I am re-measuring right now.

**Ask:** if the drop is real and not cold-cache, is there a prefill lever at depth (chunked attention
scheduling, KV-write batching, a different `-b/-ub` split at long context)?

## 7. Constraints (do not violate these in your plan)

- We may only run **repository/software experiments on this one box**. No paid APIs, no cloud.
- We must not change firmware, Secure Boot, TPM, the carve, or boot parameters.
- Do not propose anything requiring **retained-PM4**, **rocprof**, or **Vulkan-only** paths.
- Each experiment must be measurable as **serial decode t/s** or **prefill t/s** on this box with the
  instruments in §1 (we have an interleaved A/B harness for ~1–2% effects).
- Prefer **one-change-at-a-time** experiments with an env-gated build so we can A/B on one binary.

## 8. Deliverable

A ranked list of **new** candidates, each with: the mechanism, why it should help given the uniform
37% loss, the exact experiment to test it (flag/env/build change), and the expected magnitude. Rank by
(expected gain ÷ cost). Flag anything you believe is a **dead end** so I stop looking at it.
