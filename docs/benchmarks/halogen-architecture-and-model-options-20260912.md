# Halogen: architecture, model options, and the IQ4 question (2026-09-12)

Answers the founder's three questions: what the setup actually is, whether other models can be
loaded, and whether an IQ4-style quant could be used for the Flash-Next model at Peonist-like speed.

---

## 1. The architecture — what we are actually running

**Two completely separate things, and only one of them is "halogen":**

| Layer | What it is | Our status |
| --- | --- | --- |
| **`.hgn` checkpoint** | Peonist's own model container format | We load it (both models) |
| **`halogen` / `flash_serve` engine** | Closed-source C++/HIP binary per model family | We run the real binaries under WSL |

### The `.hgn` container (verified against the real file)

A 104-byte header plus a `0xA0`-stride tensor table, then 64-byte-aligned blobs:

```
header  : magic "HGN1" (0x314E4748) | version 1|2 | n_tensors | table_off | data_off | file_size | name[64]
entry   : name[96] | (ndim<<32)|dtype | dims[4] | offset | size | (qparam<<32)
dtypes  : 0 bf16  1 f32  2 f16  3 i32  4 i64  5 q4c  6 fp8r  7 q8g64  8 i4l
```

Our 27B file parsed as: **1352 tensors**, `Qwen3.8-27B-p1-d2`, `bf16 493 / fp8r 233 / q4c 222 /
i4l 400`, qparam `65792` (=0x10100) marking the 400 `i4l` twins.

### The engine (`halogen`, 27B)

- Loads the checkpoint by **`mmap` + `hipHostRegister`** so the GPU reads weights **in place from
  pinned host memory**; `hipHostGetDevicePointer` gives per-tensor device pointers.
- 20 compilation units, incl. HIP kernels `gemm_i4.hip`, `gemv.hip`, `attn_sd.hip`, `attn_fa.hip`,
  `dn_chunk.hip` (DeltaNet), `dflash.hip`, `model.hip`, `verify.hip`.
- Wire protocol on 8730 (PING/INFO/CSTAT/GEN), greedy batch-1. The Python `serve_api.py` in the
  image is the OpenAI layer on 8731.
- Flags: `--checkpoint FILE [--verify|--spec|--prefill-bench|--forced|--serve|--cache-session|…]`,
  plus ~55 `HALOGEN_*` env vars (perf/kernel/sampler switches).

### The engine (`flash_serve`, Flash-Next)

A **different, newer binary** (0.6.1) with its own CLI (`--ck --port --bind --slots --ctx --max-tok
--kv-pool`). Critically, it does **not** require the mmap-pinning path:

```
checkpoint: mapped 35.9 GB, NOT pinned (Pin::None)
overlay: none … the bare checkpoint runs
HALOGEN_FLASH_PIN_TRUNK=0   ← run without pinning (slower decode, but no host-memory floor)
```

So the Flash engine is **more WSL-friendly than the 27B engine**: it has a built-in no-pin mode, and
our `hipshim` is not even needed for it.

---

## 2. Can we load other models? Yes — and there are exactly two

Only **`peonist-ai`'s own `.hgn` uploads** are loadable, because the format is proprietary and the
engine is model-family-specific:

| Model | Repo | Size | Tensors | Engine | Status |
| --- | --- | ---: | ---: | --- | --- |
| Qwen3.8-27B | `peonist-ai/halogen-qwen3.8-27b` | 35.9 GB | 1352 | `halogen` (0.1.0) | **running under WSL** |
| Qwen3.8-Flash-Next | `peonist-ai/halogen-qwen3.8-flash-next` | 115.55 GB + 2.4 GB overlay (+2.3 GB speed, +0.84 GB vision) | 1198 | `flash_serve` (0.6.1) | engine probes OK; weights not downloaded |

**You cannot feed arbitrary GGUF/safetensors to these engines.** They are not generic loaders.

### Can we convert our own weights?

`chlorine-server` ships `converter/hgn-convert.py` (safetensors → `.hgn`), but it supports only
**bf16/f32/f16/i32/i64, plus a simple fp8r and a simple q4c** — *not* `i4l`, not the NVFP4-imported
`q4c` layout, and not the Flash-Next MoE/ngram structure. It is a **write** tool for the chlorine
scaffold's own verification, not a way to reproduce Peonist quality. Converting our local GGUF
quantities (IQ4_XS etc.) to authentic halogen behaviour is **not** feasible with it.

---

## 3. The Q5 / IQ4 question — the concrete answer

**"Halogen Flash-Next in Q5" is a misunderstanding of what is on HF.** There is exactly one
Flash-Next weight file, `qwen38-flash-next-w4b.hgn`, and it is **already 4-bit**:

- **Trunk + experts: Q4C-P** (4-bit, per-column groups)
- **n-gram embedding table: FP8**, 47.7 GiB, paged rather than resident
- rank-1 / conv1d / PLE: BF16 pass-through
- **overlay sidecar**: 723 non-expert tensors re-quantized activation-aware, **twelve `o_proj` at
  8-bit**, and (0.6.0) the MTP head's 18 dense projections at 8-bit

The model card is explicit that **4-bit is a precondition, not a choice**: Flash-Next is ~125B params
+ a 51B n-gram table; BF16 would be **335 GiB** and FP8 **173 GiB**, neither of which fits Strix
Halo's ~124 GB. So there is no "Q5" to download and nothing "higher" to upgrade to — the shipped
file is the 4-bit one, and the extra bits live in the small overlay.

### Can we use an IQ4-style quant at Peonist-like speed?

**Short answer: no, not on this engine, and it would not be faster anyway.** Reasons, in order of
weight:

1. **The engine only decodes its own layouts.** `flash_serve` contains the Q4C-P dequant kernels and
   the MoE dispatch. It has no code path for llama.cpp's `IQ4_XS`/`IQ4_NL` (which are different
   block encodings: IQ-quants use a codebook + per-16 scales, Q4C-P here is per-column groups with an
   FP8 column scale). Feeding IQ4 weights would require a *different engine*, i.e. llama.cpp itself.
2. **IQ4 in llama.cpp is already the slow path for this model.** We measured it: Flash-Next
   UD-IQ4_XS on llama.cpp/Vulkan = **303 tok/s prefill @32K, 41 tok/s decode**, vs the halogen
   engine's published **1,287 tok/s prefill @64K**. The speed comes from halogen's kernels and its
   MoE/ngram handling, not from the quant level.
3. **The Flash engine's real speed levers are elsewhere:** `HALOGEN_FLASH_PIN_TRUNK` (pinning),
   `--kv-pool`, the MTP head (on by default; 51%→59% draft acceptance), and the request-text n-gram
   drafter from 0.6.0. Those are what make it fast.
4. **A "conversion" is architecturally pointless here.** Even with a perfect IQ4→Q4C-P converter, you
   would gain at most file size (irrelevant — 115 GB is the *deliberate* precision floor) and lose
   the calibrated overlay, i.e. exactly the 5–9% perplexity the card says the overlay buys back.

**Practical recommendation:**

- Want **Flash-Next at speed on this box?** Download the real thing and run `flash_serve`:
  `~118 GiB` (base + overlay), ~68 GiB resident, started with `HALOGEN_FLASH_PIN_TRUNK=0` on our
  30 GB WSL (or a larger `.wslconfig` memory). That is the intended path and it is what we proved
  works for the 27B.
- Want a **smaller/faster** model instead? Use the 27B halogen we already run (MTP, 23.9 tok/s) —
  it is 1/3 the size and already working.
- Want **llama.cpp GGUF** (IQ4_XS, Q3_K_XL, ROCmFP4)? Those already run in WSL via our HIP llama.cpp
  build at 10.9–14.7 tok/s (27B) — but they are a *different* engine and cannot borrow halogen's
  kernels.

**The honest bottom line on the core idea:** "use an IQ4 quant with halogen-like speed" conflates two
independent things — the *quant* (which encoding the weights use) and the *engine* (which kernels run
them). Speed comes from the engine, quality per byte comes from the quant. halogen pairs a
purpose-built engine with a *purpose-built* 4-bit layout; you cannot swap in a llama.cpp quant and
keep either half.

Sources: HF model cards `peonist-ai/halogen-qwen3.8-27b` and `…-flash-next`; `chlorine-server`
`docs/halogen/{CHECKPOINT-FORMAT,ARCHITECTURE,WIRE-PROTOCOL,CLI}.md`; live engine runs on this host.
