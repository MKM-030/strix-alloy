# Kernel architecture comparison + faster-decode concept for Flash-Next on Bosgame M5 (2026-09-13)

Session scope: this session runs Flash-Next well on Windows. This document is the **hand-off
concept** for a separate session to build a faster *decode* kernel. It contains: (1) a pros/cons
comparison of the kernel architectures we have access to, (2) the measured evidence, (3) a
consolidated optimization concept, and (4) the exact prompt to start the follow-on session.

Contributors to the concept: our own measurements; **Codex "Astra" (`gpt-6-astra`)** review
(`codex-astra-kernel-review-raw-20260913.txt`); GLM 5.3 was requested but **its CLI (`zai`) has no API
key configured** — see §7.

---

## 1. What we can run, and what each kernel family is good at

| Engine | Kernel approach | Open? | Prefill | Decode | Windows/WSL | Native Linux |
| --- | --- | --- | --- | --- | --- | --- |
| **llama.cpp mainline (HIP)** | generic GGML; portable kernels | ✅ | mid | mid | ✅ works | ✅ |
| **pwilkin `strix-halo`** | hand-written gfx1151: tiled Gated-DeltaNet, sparse lightning-indexer (QSA), HC fusions, bf16 WMMA dequant GEMM, lazy "direct" PLE | ✅ MIT | **best (targeted)** | modest | ✅ builds over DXG, **no PM4** | ✅ full (PM4) |
| **Halogen** | closed C++/HIP, pins weights, own `.hgn` | ❌ | best (published) | good | ❌ fragmentation | ✅ |
| **Ciru (vLLM/ROCm10)** | vLLM + DFlash2, batch-N tuned | partial | **highest** | batch-oriented | ✅ | ✅ |
| **chlorine-server** | AGPL clean-room HIP kernels | ✅ | (reference) | (reference) | ✅ builds | ✅ |
| **myhacsint / kyuz0 Vulkan** | Vulkan compute shaders | ✅ | good | good (MTP) | ✅ native Windows | ✅ |
| **Laurent ROCmFPX / agentionai** | fp4 kernels | ✅ | high | high | ⚠️ fork-locked | ✅ |
| **EngramHalo** | QSA + chunked GDN prefill | ✅ | high | mid | ❌ native-oriented | ✅ |

**Key architectural read:**
- **Prefill is fusion/attention-bound** → the `strix-halo` fork wins there (its journey: 191→1182 t/s,
  with tiled GDN 2.37× and sparse attention 1.71×). We see its kernels fire over DXG.
- **Decode is bandwidth/launch/recurrent-state-bound** → no kernel family moves it much; the wins come
  from *graphs, speculation, and fewer bytes/token*, not from bigger GEMMs.
- **Halogen's speed is real but not portable to our split box**: it requires ~68 GiB of contiguous
  host-side allocation the WSL balloon cannot give. (Codex note: the *pin* need not be contiguous; the
  engine's own `CreateContext` must allocate large contiguous blocks, and buddyinfo showed only 154–224
  free 2 MiB blocks where the engine wants thousands — that is the evidence, not the pin alone.)

## 2. Measured evidence (this box)

### Flash-Next
| Config | Prefill | Decode |
| --- | ---: | ---: |
| Halogen `.hgn` `Pin::None` (streaming) | 0.44 t/s | 0.32 t/s |
| Halogen `.hgn` pinned | ❌ | ❌ fragmentation |
| **strix-halo fork, stock UD-IQ4_XS @36k** | **300.8 t/s** | 6.97 t/s |
| myhacsint Vulkan UD-IQ4_XS + MTP @55k/164k | 201 / 105 t/s | 22.1 / 13.6 t/s (MTP 100%) |
| strix-halo fork, **custom IQ4_NL** | ~1200 t/s (author, native Linux) | ~26 t/s (author) |

### Kernel A/B (fork vs mainline, `llama-bench`, no speculation)
| Model | Build | pp512 | pp4096 | tg128 |
| --- | --- | ---: | ---: | ---: |
| Qwen3.8-27B (`qwen35`) | fork | 204.6 | 252.4 | 12.0 |
| | mainline | 244.8 | 265.2 | 10.8 |
| Ornith 35B-A3B ICE (`qwen35moe`) | fork | 461.5 | 528.5 | 42.0 |
| | mainline | 505.8 | 514.7 | 46.3 |

**Conclusion: the fork is Flash-Next-targeted.** Off-architecture it is neutral-to-slightly-worse.
So the decode concept must be built *on* `strix-halo` (for Flash-Next) rather than replacing it.

## 3. The decode problem, quantified (Codex Astra's arithmetic)

Using ~6B active params at **4.25 bits/weight** (IQ4_XS) → **3.19 GB/token** → 13–16 ms at 200–240 GB/s
→ weight-only ceiling **≈63–75 t/s**. We measure **6.97 t/s = 143 ms/token**. 

**So ~130 ms/token is unexplained by weight bandwidth** — that is the target: routing, expert scatter,
dequantization, recurrent state, launch overhead, and PLE waits.

**Correction Astra made to our draft:** a 4-bit weight format does **not** halve bytes versus IQ4_XS
(4.25 → 4.0 bits/weight = only ~6% saved; IQ4_NL is 4.5 bits/weight). FP4's value is *cheaper decode*,
not halved traffic — unless we go to a genuinely smaller format or prune experts.

## 4. Consolidated optimization concept

**Ranked by expected decode gain per unit effort (Codex Astra, endorsed):**

```
A > E > F > G > D > C > H > B      (G rises above F if long-context KV reads dominate)
```

| Rank | Strategy | What it is | Expected | Effort/Risk |
| ---: | --- | --- | --- | --- |
| **A** | **Verify HIP graphs on DXG** | Does `-DGGML_HIP_GRAPHS=ON` actually capture/replay over the standard runtime? A/B graph-on vs graph-off, same binary/quant/context. | 2–8% if launch-bound; more if gaps are larger | **low** — capability test then one A/B |
| **E** | **Speculative decoding (MTP/DFlash2)** | Target-verified draft; we measured 100% acceptance on GGUF. Tune depth 2–4, `-ub`. | largest practical (1.3–2×) *if* draft cost is low | medium; **must verify rollback/quality**, not just acceptance |
| **F** | **PLE/ngram caching + prefetch** | The 26.8 GiB table is random-read; ~100 serialized misses × ~100 µs = 10 ms. Cache hot rows / overlap fetches. | removes latency spikes | low–medium |
| **G** | **Q8 KV cache** | Halve KV bytes at long context. | 1.11× at f=20%, 1.33× at f=50% | low if kernels support it |
| **D** | **Fused MoE decode kernel** | gate/up + activation + **down** + weighted reduction, routing on-device (Astra: don't do one giant kernel; fuse a few stages) | moderate, after profiling | **high** effort |
| **C** | **FP4 weights** | Cheaper dequant + layout; port aiter kernels to gfx1151 | modest (see §3) | medium; check instruction/layout |
| **H** | **Own fork** | *Vehicle*, not a speedup by itself | — | — |
| **B** | **Recreate PM4 replay** | Needs `/dev/kfd`; no established gain over DXG graphs | lowest | **very high** |

**Plus three kernel techniques Astra flagged that we had missed (all batch-1 MoE relevant):**
1. **Selected-expert × output-tile scheduling** — one grid over selected experts *and* their output
   tiles, routing indices on-device, no per-expert CPU dispatch, no token sort at batch-1. Partition
   *within* an expert too, or most of the 40 CUs idle.
2. **Decode-specific weight packing** — prepack quant blocks/scales/gate-up rows for contiguous wave32
   loads with a separate down-projection layout; fuse unpack into accumulation; compare integer-dot vs
   fp16/bf16 paths (IQ codebooks need correct decode).
3. **Register/occupancy-aware GEMV tiling** — tune waves/workgroup, accumulators, optional split-K;
   stage activations in LDS; **beware 16-column WMMA wasting 15/16 of work at one token column**;
   check VGPR spills and LDS bank conflicts before adding persistence.

### The first experiment (agreed)

**A: graph-on vs graph-off decode A/B on the same Flash-Next binary + quant + context + warm PLE.**
Steps: (1) prove a tiny HIP graph captures/instantiates/replays and is numerically correct on this
runtime; (2) prove model execution *reuses* graphs across changing expert IDs/positions rather than
recapturing per token; (3) record ms/token, graph rebuild count, GPU gaps, PLE wait. Cheap, and it
separates submission overhead from kernel execution and host stalls.

## 4b. Halogen as a BLUEPRINT (not an oracle) — how to use a closed kernel

> **UPDATE 2026-09-13: Halogen 0.7.0 added "Bring Your Own GGUF" — the format barrier is gone** (on
> native Linux). From the release and its README:
> - `HALOGEN_CHECKPOINT` may now name a **standard llama.cpp GGUF**; the engine repacks tensors at
>   startup **losslessly** ("the file's own quantized values, moved, not requantized") and reads the
>   n-gram lookup table from the GGUF in place.
> - **Supported quant types** (kept losslessly): the `IQ4_NL` / `IQ4_XS` / `IQ3_S` / `Q4_0` family for
>   experts, `Q8_0` for dense, `Q6_K` for the output projection — i.e. **any `llama-quantize` output in
>   those types, and unsloth's `UD-IQ4_XS` exactly**.
> - **Refused by name**: K-quants (`Q4_K`, `Q5_K`, `Q5_1`, `Q4_1`) and IQ2/IQ1 — reading them "needs
>   kernels for their block layouts rather than a repack".
> - `HALOGEN_GGUF_CACHE=1` writes the repacked artifact (~70 GiB) so later starts use the normal load
>   path; startup repack is 18 s cold / 9 s cached.
> - **Measured with `UD-IQ4_XS`**: 94 GB disk, **72 GiB RAM**, perplexity 0.7–2.1% *better* than the
>   native checkpoint, fixture agreement 184/192 (vs 182/192), prefill unchanged, but **serial
>   short-context decode 25.4 tok/s (−28%)** and drafted coding turns 42–45 tok/s.
> - **Still refused on Windows/WSL**: "kernel 7.0+; native Linux on the amdgpu/KFD stack. **WSL2 via
>   `/dev/dxg` is unsupported (mapping registration is refused there).**" — which independently
>   **confirms our root cause** for Halogen's failure here.
> - Model scope: "intent was for Qwen 3.8 flash / Qwen 4.0 architectures. Other models might run, could
>   just blow up."

**What BYO-GGUF changes for us:** it removes the "closed format" objection — we can now point Halogen at
any supported quant, *ours included*. But it does **not** change the WSL blocker, and it *confirms* the
quant↔kernel coupling we reasoned about: the engine accepts exactly the block layouts its kernels can
decode, and refuses the rest **by name**. That is the concrete proof that a kernel and its quant layout
are co-designed, and it tells us precisely which layouts the fast path wants (`IQ4_*`/`Q4_0`/`Q8_0`/`Q6_K`).

Founder question: *if we knew Halogen's kernel, could we compare all kernels, find the gaps, and then
re-quant the model?* Answer: the comparison is valuable, the re-quant is a trap, and one of Halogen's
main advantages may not port at all.

### What is knowable about Halogen today (no source needed)

| Method | What it yields | Status |
| --- | --- | --- |
| `llvm-objdump` / `roc-obj-ls` on `flash_serve` | GCN ISA instruction mix, wave/workgroup shapes, LDS use, VGPR counts | available now |
| `strings` / env enumeration | ~168 `HALOGEN_*` knobs (cache, KV pool, pin, QSA, strip) | done |
| **`chlorine-server`** | AGPL **clean-room reimplementation** of the same gfx1151 kernels | cloned; the legitimate path |
| Container images | exact runtime libs, entrypoint, launcher flags | extracted |
| Full source | — | Peonist said on the Reddit thread they intend to open it |

**Rule: study behaviour and reimplement; do not decompile-and-copy.** `chlorine-server` exists precisely
so this is legal and clean.

### The comparison that is worth doing

Diff four kernel families **per layer** on the same weights: mainline HIP, `strix-halo` fork,
`chlorine-server`, Halogen. The question to answer: **why does our decode run at ~10% of the bandwidth
ceiling (~22 GB/s implied vs ~220 available)?** Candidate gaps: launch/scheduling, recurrent-state
serialization, PLE wait, dequant cost.

### The hypothesis (state it explicitly, then test it)

**Halogen's edge is probably scheduling, not math.** It pins weights and (native Linux) uses **PM4
command-buffer replay + retained graphs**. Our fork builds `-DGGML_HIP_GRAPHS=ON` but we have **not
verified graphs engage over DXG**. So Halogen functions as a blueprint for the *submission/scheduling*
tricks we cannot see — which is exactly the ~130 ms/token we cannot explain. **This makes experiment A
(more) important, not less.**

### Why "re-quant into their layout" is a trap

Halogen's dtypes (`q4c`, `i4l`) exist because its kernels consume them — quant and kernel are
co-designed, so learning the kernel does teach us the layout it wants. **But a layout change alone does
not reduce bytes/token** unless the bit-width drops, and 4.25 → 4.0 bits is ~6%. Better layout helps the
kernel *chew* more efficiently, not read less. Since we are only ~10% bandwidth-bound, a better layout
buys single-digit percent today — you would be perfecting the transmission while the engine stalls.
**Re-quant is worth doing only after A/E/F/G move decode closer to the bandwidth bound.**

### Why expert reweighting is a *fit* lever, not a *speed* lever

Bytes/token = `k × expert_size + dense + attn + shared_expert + PLE` — **the total expert count is not in
the formula.** A MoE reads only top-k, so 512 → 300 experts does not change per-token traffic. Pruning
shrinks the *file* (helps Fit) but not the *work* (does not help Speed). A real speed gain needs fewer
**active** params — lower top-k (quality risk, needs retuning) or distillation to a smaller active model.

### Can Halogen's advantages be ported to Windows/WSL?

Its two biggest edges — **weight pinning** and **PM4 replay** — are exactly the two that assume native
Linux. So knowing the kernel tells us *what to emulate*, and experiment A determines whether the DXG
runtime exposes an equivalent (HIP graphs are documented as separate capture/instantiate/replay ops, and
may work over DXG even though the custom ROCr path does not). **This is an empirical question — do not
assume yes or no.**

## 5. Corrections to the brief (from the Astra review — recorded so we don't repeat them)

- 92 GB/s of inferred MoE traffic **does not prove** launch limitation (scatter, occupancy, dequant,
  sync all lower effective bandwidth).
- "Their 26 vs our 12 t/s" is **not** a PM4 A/B — different model, quant, context, speculation, OS.
- Our data does **not** establish prefill is "generally fusion-bound" (true for the fork's target, not
  universally).
- A fused MoE kernel **must include the down projection**; cross-workgroup deps prevent one giant kernel.
- MTP/DFlash2 "100% acceptance" does **not** prove the target distribution is preserved — needs correct
  sampling + state rollback (arXiv 2211.17192).
- Pinned host memory need not be physically contiguous (the engine's failure is about *its* large
  contiguous allocations; buddyinfo is the evidence).
- We lack selected-expert counts, per-layer breakdown, and exact quantized tensor sizes for a precise
  bandwidth model — **measure those next**.

## 6. Assets and method

- Fork: `/home/revn/strix-llama` (`build-hip/`, commit `f5daaa3c`); mainline `/home/revn/llama.cpp/build-hip`.
- chlorine-server: `/home/revn/chlorine-server` (kernel reference + `.hgn` converter).
- ROCm 10 SDK over DXG: `~/ciru-runtime/venv/.../_rocm_sdk_*` + `runtime-env.sh`; `HSA_ENABLE_DXG_DETECTION=1`.
- Models: `~/models/flash-next-strix` (ilintar IQ4_NL, downloading), `~/models/flash-next-unsloth`
  (staged ext4), `/mnt/c/AI/models/*`.
- Constraints: WSL memory ≤72 GB, **one heavy job at a time** (parallel jobs hard-restarted the PC),
  stage models to ext4, no product Cloud/FiveM, no pushes.

## 7. Collaboration status

- **Codex (`gpt-6-astra`)**: ✅ done — full review saved. Codex CLI updated 0.149.1 → **0.154.0** to
  reach the Astra model.
- **GLM 5.3 via `zai` CLI**: ❌ blocked — `zai` reports *"API key required. Set ZAI_API_KEY"*. Set the
  key and the follow-on session can add a third opinion with:
  `zai -p "<prompt>" -m glm-4.6` (or the current GLM model id) after `zai config`.

## 8. Follow-on session prompt

See `FOLLOWUP-SESSION-PROMPT-KERNEL-20260913.md` (next file) — paste it to start the separate session.
