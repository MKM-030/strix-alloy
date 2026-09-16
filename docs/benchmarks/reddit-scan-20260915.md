# Strix Halo community scan — Reddit (2026-09-15)

Scanned r/StrixHalo (new + search for `halogen`, last month) and the directly linked threads. Focus:
Qwen3.8-Flash-Next throughput, gfx1151 kernels, Halogen, llama.cpp HIP/Vulkan forks, MTP/speculative
decode, new quants. Reddit blocks some of this behind a JS challenge; the findings below are from pages
that rendered.

## 1. The single most important find: `peonist-ai` (Halogen author) states the decode ceiling

In the **HipKittens** thread (`r/StrixHalo/1wgcro1`, 19 h old) the Halogen author commented directly.
This is the clearest public statement of where the hardware wall is:

> "decode is at the hardware wall, as you have pointed out. Strix Halo might have **5–10% more prefill
> left in the tank**… maybe. But that's only theory. (On Qwen4 architecture). Kernel development is very
> time consuming… **Nearly all the easy gains have been found. That last ~10% is a grind.**"

And on the specific idea of a wide-verify (which is exactly our MTP-depth question):

> "**Dynamic MTP works with dense models but my 'engineering staff' told me its not a viable technique
> for MoE.** N-gram indexing has been shipped in halogen since 0.6.0."
> …blockquote: "The sparsity that makes decode cheap is what makes a wide verify expensive; **that is the
> architectural fact, not a tuning gap.**"

**Why it matters to us:** this is independent confirmation of our own measured result — deeper MTP
(n-max 3–8) is monotonically *worse* on this MoE, and it is not a config bug we can tune around. The
"sparsity makes wide verify expensive" line is the same mechanism our `r ≈ 0.47` draft-step cost captures.
It also says **PLD (prompt-lookup decoding) is already in Halogen and already tuned to coexist with the
MTP drafter** — that is the "n-gram mod" lever, and it is a drafter *sidecar*, not a decode-kernel change.

## 2. A frontier-model suggestion worth testing: dynamic MTP width

From `SmartCustard9944` (maintainer of `MirkoCovizzi/ninfer-rtx5090-mobile`, also has a Strix Halo) in the
same thread:

> "experiment with **dynamic MTP**… When speculating highly regular text like code the acceptance rate is
> typically very high. In those cases, if the MTP width is increased (speculating more tokens) you might
> get a bigger speedup… you tune the MTP width based on what the model is currently inferencing. On the
> RTX 5090 Mobile I can easily get Qwen 3.8 27B to **k=15 and reach upward of 250 tok/s on code**, when
> normally k=3 would get to 130."

**Why it matters:** it is a cheap, testable idea we have *not* tried — a per-request **adaptive n-max**
(code/structured text wants deep drafts; prose wants shallow) rather than a fixed n-max 2. Our own data
*contradicts* the strong form (acceptance collapses with depth on this MoE), but the cheap version — detect
high-acceptance regimes and widen only there — is worth one measurement. Note `peonist-ai`'s reply says it
is **not viable for MoE**, which matches our measurements; treat this as a low-priority experiment.

## 3. Our own Windows port is already public

`CommunicationIll2357` (2 d old) posted a full write-up of porting ilintar's `strix-halo` branch
(`f5daaa3cf`) to **Windows** on a Strix Halo 395 (96 GB carve, TheRock ROCm 10.1, Clang 23):

- Builds with **one fix**: the `_WIN32` branch of `llama_lazy_reader` stubs `gather()` but not
  `prefetch()`, and `qwen4exp.cpp` calls `prefetch` unconditionally — a no-op stub is correct on the
  mmap fallback. *(This is exactly the `prefetch()` fix already in our fork at `424cd1b8`.)*
- All 35 gates on → fast but corrupted (`//////` flood at 1080–1250 t/s). **The single culprit is
  `LLAMA_MMB_HC16`; with `LLAMA_MMB_HC16=0` and everything else on it is fully clean at 964–1045 t/s
  prefill** (262144 ctx, ub 8192, unsloth UD-IQ4_XS). *(This is our `gates-test.sh` recipe verbatim —
  HC16=0 is the one known-bad gate.)*
- MTP: unsloth self-contained Q8_0 head loads and drafts (77–79% accept) but **net decode ~24 t/s**
  without on-device spec checkpoints — "which matches your note that PM4 is where decode lives."
- They run a **device-checkpoint MTP branch for interactive decode (~35 t/s)** and keep the HC16-off
  build for cold long-context ingest at ~1k t/s prefill.
- **`-ub` transferred to their other engine: 512→2048 was +20–40% prefill.**
- Repo: `github.com/olliehm/qwen-flash-next-windows` (MIT); issue:
  `github.com/pwilkin/llama.cpp/issues/24`.

**Why it matters:** this is a second independent Windows build at **~35 t/s decode and ~1k t/s prefill** —
i.e. **matching our numbers**, and it confirms `HC16=0` and the `prefetch()` stub are the two necessary
fixes. Their 77–79% acceptance vs our ~75% suggests head choice matters more than build.

## 4. ilintar's published config (our direct source, now open)

From ilintar's own post (`r/StrixHalo/1weo5s3`) and `pwilkin.github.io/strix-halo`:

| measurement | value |
| --- | ---: |
| Qwen3.8-Next-Flash prefill @0 depth (pp16384) | **1204.31 ± 2.31 t/s** |
| prefill @40 000 depth | 1086.29 ± 0.96 t/s |
| decode @0 depth (tg128) | **26.28 ± 0.29 t/s** |
| decode @40 000 | 16.63 ± 0.14 t/s |

Config: **ub = b = 16384** ("the whole prompt goes through as one batch"), `--load-mode none
--lazy-mode on-direct`, sparse lightning-indexer path holding 90% of depth-0 prefill at 40k.
Retained-PM4 runtime for decode. **Their honest caveat: HIP graphs never engage on prefill** (each chunk
shape occurs once per request) — the retained-PM4 pays off in *decode*. Decode is "about 8% short of what
the same kernels reach out of tree."
Quant recipe: "quantize everything you can to IQ4_NL unless it breaks model coherence" — i.e. **our
PROJFIX** (`huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo`).

**Why it matters:** their **decode at 0 depth (26.3) is *below* ours (35 t/s)** because they run a *fixed
plain* decode, while we run **MTP n-max 2**. Their prefill (1204) is *above* our best (1057) — the gap is
ub 16384 as one batch plus the retained-PM4 runtime. The controllable deltas are clear:
**ub 16384 (we have), PM4 retained command lists (we do not), MTP (we have, they do not).**

## 5. Halogen 0.7.0 now accepts BYO GGUF

`r/StrixHalo/1wf9joo` (2 d old, peonist-ai): Halogen 0.7.0 ships **Bring-Your-Own-GGUF**
(`github.com/peonist-ai/halogen-flash-server#bring-your-own-gguf`). Caveat from the author: "intent was
for Qwen 3.8 flash / Qwen 4.0 architectures. Other models might run, could just blow up."
On open-sourcing: "soon™… I'm validating the tuning loop. It's working, it just takes time."
A commenter reported Halogen at **41.65 t/s** (974 tok, 591 rounds, 1.65 commit/round) at **105 372
context** — that is the number to beat at depth.

**Why it matters:** BYO-GGUF means we can point Halogen at **PROJFIX** and get a clean, same-weights
prefill/decode comparison instead of cross-trunk numbers. This is the highest-value new experiment
available.

## 6. The IOMMU finding (prefill)

`r/StrixHalo/1wdrkrc` (baldlawyer, 4 d old, harness + raw data in
`github.com/baldlawyer/strix-halo-iommu-benchmark`): `amd_iommu=off` raises prefill **+1.8% to +31.6%
depending on model**, and **most of the "ROCm beats Vulkan at prefill" gap is the IOMMU**, not the
backend. Effect orders with **bytes read per forward pass** (hypothesis, not mechanism). **Decode is
unaffected** (±1%). Not a clock/power effect (package power pinned 99–100 W in both arms; shader clocks
*lower* with IOMMU off). Caveats: one machine, `llama-bench` not a served endpoint, and
**`amd_iommu=off` disables the NPU** machine-wide and hurts anyone using the NPU.

**Why it matters:** a cheap, reversible prefill lever — but it costs the NPU, which the founder wants to
use. Note their noise estimate *worsened* with replicates (0.2%→2.0% from 2→5 boots), a warning for anyone
quoting a noise floor from two runs (including us).

## 7. Other relevant pointers

- **`github.com/adelj88/rocm_wmma_gemm`** — an existing RDNA3/3.5 WMMA GEMM the author says is
  "competitive with hipblaslt and rocblas"; the same tile concepts apply elsewhere (HipKittens thread).
- **`github.com/shisa-ai/hipEngine/blob/main/docs/RDNA3-TUNING-GUIDE.md`** (randomfoo2) — "what I've
  learned from months of optimization loops on RDNA3."
- **`github.com/MirkoCovizzi/ninfer-rtx5090-mobile`** — the dynamic-MTP source above.
- **`github.com/mighty-studios/StrixHaloCluster`** — two Bosgame M5 over USB4 serving Flash-Next
  (3 concurrent users × 512k ctx).
- `HazyResearch/HipKittens` + arXiv 2511.08083 — CDNA-targeted tile kernels; **not** gfx1151-compilable,
  but the concepts map to wave32/WMMA.
- `halo-box/strix-llama.cpp` — the community fork doing most Strix Vulkan work (quantized coopmat at
  wave32, f16 B-operand MUL_MAT, mmid tiles).

## Net: what this changes for us

1. **Decode is confirmed at the wall** by the Halogen author — stop hunting decode kernel gains; the
   remaining ~5–10% is prefill.
2. **Prefill is where our gap actually is** (we 1057, ilintar 1204). Two levers: **retained-PM4 command
   lists** (their decode *and* some prefill) and confirming our ub-16384 one-batch path is as clean as
   theirs.
3. **Halogen BYO-GGUF is the new best experiment** — same weights, direct comparison.
4. **PLD (n-gram) is a shipped, tuned-in-Halogen drafter sidecar** — relevant to our Phase-4 NPU question:
   it is nearly free and could take the lookup work off the GPU entirely.
5. **Dynamic MTP width** is a cheap test the frontier model recommends; the MoE author says no, and our
   data agrees — low priority.
6. **IOMMU off** is a real prefill lever but trades away the NPU — a founder decision, not ours.
