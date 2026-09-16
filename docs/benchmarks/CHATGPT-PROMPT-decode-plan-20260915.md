# Prompt for a frontier model (ChatGPT / GPT-5-class) — decode optimisation plan review

Paste everything below the line. It is self-contained: all measured facts, the current best configuration,
the specific ideas under consideration, and the questions I want answered. Ask for a concrete, ordered plan
with expected gains, not a survey.

---

## Context

I am optimising inference of **Qwen3.8-Flash-Next** on a single **Bosgame/Corsair Strix Halo** box and want a
review of my plan, my numbers, and my three open ideas. Be concrete and quantitative; correct me where I am
wrong; tell me what to do next and in what order.

### Hardware / runtime (fixed, cannot change)

- AMD Ryzen AI Max+ 395, Radeon 8060S iGPU, **gfx1151** (RDNA 3.5, wave32, 40 CU, 2 MiB L2, 32 MiB MALL).
- 128 GB LPDDR5X unified, ~256 GB/s theoretical, ~220–240 GB/s practical.
- **Windows 11** natively, plus WSL2 (which sees only `/dev/dxg`, no `/dev/kfd`, no PM4 replay).
- Firmware "carve" (dedicated iGPU memory) set to **96 GB** → Vulkan/HIP device pool **111.8 GiB**; Windows
  then sees only **31.6 GB** of RAM. WSL is kept **shut down** while benchmarking because `vmmemWSL` holds
  host RAM; all the numbers below are native Windows with WSL off.
- There is also an **XDNA2 NPU** on the die, currently unused.

### Model

Qwen3.8-Flash-Next (`qwen4exp` arch): ~177 B params, **~6 B active** MoE — 512 routed experts, **top-k 10**
+ 1 shared expert, expert FFN 640, emb 2560, 48 layers = **36 GatedDeltaNet (recurrent) + 12 full-attention**
(every 4th; 24 heads, 2 KV heads, head_dim 256, sparse "lightning indexer" with top_k 2048). Hyper-connections
(4 streams, low-rank 320). Vocab **248,320**. A per-layer 160-dim embedding with a **26.8 GiB n-gram table**
(`per_layer_token_embd`, 320 M rows × 160, IQ4_NL) that is paged from disk, never resident.

### Software stack (all open source, all built from source)

- `pwilkin/llama.cpp` branch `strix-halo`, commit **d67d5883** (hand-written gfx1151 kernels: tiled Gated
  DeltaNet, QSA sparse attention, bf16-WMMA dequant GEMM "MMB", fused MoE GEMV, sparse **decode** + incremental
  indexer state). Built natively on Windows.
- Toolchain: **TheRock 10.2 nightly Windows gfx1151 SDK**, `therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz`
  → **AMD clang 24.0.0**, hipcc. (This was worth +60–70 % prefill over the ROCm 7.2 / clang 21 SDK that ships
  for Windows.)
- Quant: **ilintar's IQ4_NL "PROJFIX"** (every tensor IQ4_NL, incl. attention/GDN; 4.52 bpw; 66.3 GiB resident).
  The alternative is unsloth UD-IQ4_XS (IQ3_S experts, Q8_0 attention; 4.24 bpw; 60.4 GiB resident), which is
  ~25 % slower on prefill and ~50 % slower on decode on this fork — the fork's fast kernels are written around
  resident IQ4_NL.
- Draft head: unsloth `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` (2.6 GiB), MTP speculative decoding.

### Measured results (token-exact prompts sized with /tokenize, cache_prompt=false, gen 256, 3 reps)

Best configuration: PROJFIX + the fork's compiled-in tuned defaults, **ub 16384** for prefill, **ub 2048 + MTP**
for decode (ub ≥ 8192 breaks the MTP draft load on this build).

| config | prefill @1k | @8k | @16k | @32k | decode @1k | @8k | @16k | @32k |
|---|---|---|---|---|---|---|---|---|
| ub 16384, no draft | 710 | 1021 | **1057** | **1035** | 30.1 | 28.9 | 29.2 | 28.8 |
| ub 8192, no draft | 705 | 1024 | 1019 | 998 | 29.8 | 28.4 | 29.2 | 28.9 |
| ub 2048 + MTP n-max 2 | 674 | 805 | 787 | 767 | **35.1** | 30.3 | 33.0 | 32.5 |
| ub 2048 + MTP + p-min 0.75 | 663 | 798 | 785 | 767 | 35.5 | 30.2 | 32.9 | 32.5 |

Draft acceptance: **61–62 % at 1k, ~51 % at 8k, ~60 % at 16k/32k** (e.g. 141/228 at 1k, 128/253 at 8k).

For reference, published figures on this hardware class: the fork author (native **Linux**, same quant, plus
a custom ROCr/**retained-PM4** runtime we cannot use) reports **1204 t/s prefill @0k, 1086 @40k, and
26.28 t/s decode**; a Windows port by another user reports **964–1045 t/s prefill** with the *stock* quant;
the closed **Halogen** engine (native Linux only) reports **~1250–1400 t/s prefill and 42–45 t/s decode with
two drafters**.

### What I have already tried, with results

1. **Toolchain**: clang 21 → clang 24 moved prefill +60–70 %, decode +1 %. Prefill is toolchain-bound; decode is not.
2. **Quant**: PROJFIX vs UD-IQ4_XS — +25 % prefill, +90 % decode (layout, not bits: PROJFIX is *bigger* at 4.52 vs 4.24 bpw).
3. **PR #28118** (keep speculative recurrent-state checkpoints on-device instead of host round-trip):
   ported, rebuilt, measured **no change** (33.0 vs 32.9 t/s @16k). Reason: this branch already sets
   `n_rs_seq > 0` and `llm_arch_supports_rs_rollback(QWEN4EXP) == true`, so it already uses the native
   rollback path rather than host checkpoints.
4. **`--spec-draft-p-min 0.75`**: **no change** in acceptance (identical 141/228) or speed.
5. **Standalone MTP head** vs shared head: same ~61 % acceptance.
6. **First-token/cache effects** ruled out: identical acceptance cold and warm.
7. A sparse-attention interaction: with the stock indexer budget the MTP acceptance collapsed to exactly 0 %
   beyond `n_kv > indexer_top_k + ratio − 1` (2051 tokens); setting `--override-kv
   qwen4exp.attention.indexer.top_k = ctx + margin` fixes it (0 % → 60 %). Not needed with PROJFIX, but it is
   a real upstream bug I found and can file.

### Bandwidth analysis (my own arithmetic, please check it)

Active weight bytes per decoded token for PROJFIX at k=10 ≈ **4.61 GB**.

- **Serial decode** 28.8 t/s → 28.8 × 4.61 = **133 GB/s**, i.e. **55–66 %** of the 200–240 GB/s ceiling.
- **With MTP** (n-max 2: verifies ~3 rows, emits ~2.6, so ~0.38 weight sweeps per emitted token) 32.9 t/s →
  32.9 × 4.61 × 0.38 = **58 GB/s**, i.e. **24–29 %** of the ceiling.
- KV is negligible: dense f16 KV would be 6.4 GB/token at 262k ctx, but QSA's top_k 2048 makes the actual read
  ~50 MB/token, **~1 %** of the weight traffic, and constant with depth.

**My conclusion from this:** serial decode is genuinely ~60 % bandwidth-bound (ceiling 43–52 t/s), but the
**MTP operating point has only 25–30 % bandwidth utilisation, so it is limited by per-round overhead, not
bytes.** Do you agree? If so, what is that overhead (verify-pass structure, sampling, state handling, launch
gaps) and how do I measure it?

### The three ideas I want reviewed

**(A) Multiple drafters, sequential cascade vs parallel.** The fork's speculative system builds drafters in a
fixed **priority order** and runs them in sequence per draft call; the first that returns a draft wins and the
rest are skipped (`NGRAM_SIMPLE → NGRAM_MAP_K → NGRAM_MAP_K4V → NGRAM_MOD → NGRAM_CACHE → DRAFT_SIMPLE →
EAGLE3 → MTP → DFLASH → DSPARK`). My plan is to enable a cheap n-gram drafter *before* MTP, so repetitive text
is drafted from a table at zero weight cost and prose falls through to MTP. Questions: is the cascade the right
architecture, or is there a better composition? What draft depth per stage? How do I model the expected
speedup given stage hit rates, and what should I measure to tune it?

**(B) Vocab compression / SSD-backed lookup.** Two sub-ideas. (i) The **draft head has a 248,320-token output
projection**; a "FR-Spec" variant scores only 65,536 tokens (3.8× smaller projection, hence a cheaper draft per
step) — I have ported the `d2t`/`t2d` vocab-mapping into the fork and can use that head. Is a trimmed draft
vocab the right lever, and what accuracy cost should I expect from the reduced candidate set? (ii) Could the
**big 26.8 GiB n-gram table** be compressed further or streamed from SSD to free RAM/bandwidth? My reading is
that it is already paged from disk, that its read is only a few KB per token so bandwidth is irrelevant, and
that the only real cost is latency — so a prefetch/cache would help, but re-quantising it would not. Do you
agree, and is there a smarter scheme (e.g. a hot-row cache, or an SSD-resident structure with better locality)?

**(C) NPU offload.** The XDNA2 NPU shares the same LPDDR5X, so in principle it could run a **lookup** (the
n-gram drafter) without consuming extra bandwidth. But llama.cpp has no NPU backend; the NPU needs
XRT/ONNX (Ryzen AI) which is a separate runtime and arena from HIP, so "same address space" is not achievable
today, and a per-step copy or a per-step sync would likely cost more than the lookup saves. My plan is a
bounded measurement first: measure what the n-gram drafter costs in isolation, and only prototype if it is
several ms/token. Is that the right decision rule? Is there any supported path for sharing one allocation
between a HIP context and the NPU?

### What I want from you

1. **Audit the numbers and the bandwidth conclusion.** Is the MTP point really overhead-bound? What is the
   single best measurement to attribute the remaining overhead, and what instrumentation should I add?
2. **Rank my remaining levers by expected decode gain per unit effort**: multi-drafter cascade, trimmed draft
   vocab, deeper MTP (we have not yet got a valid n-max sweep at the corrected carve), QSA decode tuning,
   anything I have missed. Include a realistic ceiling for each.
3. **Tell me the fastest path from 33 t/s to Halogen-class 42–45 t/s** (and what the theoretical ceiling is
   given the 4.61 GB/token and this memory system).
4. **Point out anything I have got wrong** — especially any place where my arithmetic or my causal story does
   not hold.
5. Give an **ordered checklist** for the next 6 hours of work, with the expected result and the abort
   condition for each step.
