# Halogen Qwen3.8-27B under WSL — SOLVED via chlorine-server (2026-09-12)

**Result: Halogen runs under WSL2 on this Windows box.** Not through Peonist's closed-source
docker engine (which needs `/dev/kfd` and cannot run on WSL), but through
**`Heretek-AI/chlorine-server`** — a clean-room, AGPL-3.0 reimplementation of the halogen 0.1.3
engine built from the founder's decompiled specs. It **loads the real 35.9 GB `.hgn` checkpoint,
places the 17.8 GB weight pool on the GPU over `/dev/dxg`, and boots the engine on port 8730.**

This is the second "reported impossible, actually works" result of this project, next to Ciru Halo.

## What the founder provided

`https://github.com/Heretek-AI/chlorine-server` — describes itself as:

> "An independent, AGPL-3.0 reimplementation of the halogen 0.1.3 inference engine for Qwen3.8-27B
> on AMD Strix Halo (gfx1151) ... Same wire protocol ... Loads `.hgn` checkpoints ...
> Greedy token streams match the original engine on identical weights."

The repo ships the reverse-engineering docs the closed-source engine never had
(`docs/halogen/`: `CHECKPOINT-FORMAT.md`, `ARCHITECTURE.md`, `WIRE-PROTOCOL.md`, `HOST-LOGIC.md`,
`KERNELS-DEQUANT.md`, `CLI.md`, `REBUILD-PLAN.md`) plus real C++/HIP sources (`generator.hip`,
`trunk.hip`, `serve.cpp`, `hgn.cpp`) and a `.hgn` inspector/converter in Python.

## Why this unblocks the `/dev/kfd` problem

The Peonist container is closed source and demands `--device /dev/kfd` (real Linux amdgpu kernel).
WSL only exposes `/dev/dxg`. chlorine-server is **source we can build**, and its HIP kernels compile
with the **ROCm 10 SDK already inside the Ciru venv** — the exact stack that already talks to the GPU
through DXG (`HSA_ENABLE_DXG_DETECTION=1` + `librocdxg`). So the `/dev/kfd` requirement disappears.

## What was done

1. **Parsed the real `.hgn`** with the shipped `converter/hgn-inspect.py`:

   ```
   magic 0x314E4748 OK · version 2 · n_tensors 1352 · model 'Qwen3.8-27B-p1-d2'
   file_size 35,865,565,184 (matches)
   dtype histogram: bf16=493 f32=2 i32=2 q4c=222 fp8r=233 i4l=400
   qparam: 0=898, 1=54, 65792=400 (the i4l prefill twins)
   ```
   Confirms the format spec end to end: 64 trunk layers (48 DeltaNet + 16 full attention), hidden
   5120, MLP 17408, vocab 248320, and the **W4A4 "fenced to prefill"** layout (each quantized
   projection ships an fp8r/q4c decode tensor plus an `i4l` 4-bit prefill twin).

2. **Built chlorine-server in WSL** with the Ciru ROCm 10 SDK:
   `hipcc generator.hip --offload-arch=gfx1151` → `build/chlorine` (HIP kernels compiled for
   gfx1151, no `/dev/kfd` needed).

3. **Loaded the real checkpoint:**
   ```
   trunk: table 1352 tensors
   trunk: loading embed... · loading lm_head (fp8r dequant)...
   trunk: big tensors loaded (21.5s)
   trunk: weight pool resident (17.8 GB)
   trunk: ready (132.0s)
   serve: listening on 127.0.0.1:8730
   ```
   `weight pool resident` means the quantized projections were copied to device memory — the GPU
   holds ~17.8 GB of Halogen weights **through DXG**. The engine then serves the documented token
   protocol (`PING`/`INFO`/`CSTAT`/`GEN`).

## It generates — verified output + numbers

With the tokenizer in place (`tokenizer/tokenizer.json` from the same HF repo), a real greedy
generation through the engine's token protocol:

```
$ ./build/chlorine --checkpoint qwen3.8-27b-p1w4d-d2.hgn --serve --port 8730
trunk: table 1352 tensors · weight pool resident (17.8 GB) · ready (132.7s)
serve: listening on 127.0.0.1:8730

prompt_ids  [760, 6511, 314, 9338, 369]            # "The capital of France is"
INFO -> I 1 1 262144 8 2 1 1 0 2048 1 262144
GEN  -> GEN 1 8 1 248044 5 760 6511 314 9338 369
  +8.7s   T 11751  ' Paris'          <-- correct answer
  +10.1s  T 13     '.'
  +11.2s  T 198    '\n'
  +12.2s  T 760    'The'
  +13.2s  T 6511   ' capital'
  +14.3s  T 314    ' of'
  +15.3s  T 9564   ' Germany'
  +16.3s  T 369    ' is'
D -> D 1 length 5 8 8527.1 7636.6 0 0 0
full text: ' Paris.\nThe capital of Germany is'
```

**This is Halogen actually running under WSL.** The model produced a factually correct token
("Paris") and continued in coherent English. Reported timings: **prefill 8527 ms** for 5 tokens,
**decode 7637 ms** for 8 tokens.

Performance on the current scaffold:
- **Decode ≈ 1.05 tok/s** (8 tokens / 7.64 s) — about **10x slower** than the llama.cpp 27B quants
  measured earlier (10.9–14.7 tok/s).
- **Prefill ≈ 0.6 tok/s** (5 tokens / 8.5 s) — extremely slow, because the scaffold's forward path
  **dequantizes every projection per use** across all 64 layers instead of holding dequantized
  weights resident.
- The `T` lines arrive on a clean ~1-second cadence, so the engine is functioning correctly, just
  slow.

The slowness is **scaffolding, not DXG**: `generator.hip` is a bring-up build (`CXT = 448` context
scaffold) and re-dequantizes per token, whereas the real halogen engine keeps a resident dequant
pool and the W4A4 kernels. The repo's own `REBUILD-PLAN.md` calls the GPU kernels "the long pole" of
a phased rebuild — exactly this stage.

## Honest status: it loads and generates; throughput is early-stage

- **Works now:** loader, wire protocol, `INFO`, `GEN`, real correct token output, weights on the WSL
  GPU via DXG.
- **Not yet usable for interactive work:** ~1 tok/s. This is upstream maturity (dense dequant, 448
  context), not a WSL/DXG limitation.
- For a *fast* Halogen today, the options are (a) wait for chlorine's kernel work, or (b) run
  Peonist's original engine on a **native Linux** install where `/dev/kfd` exists.

## Bottom line

**Halogen *can* be used in WSL — the blocker was never the GPU, it was the closed-source container.**
chlorine-server removes it: the real 35.9 GB `.hgn` loads, the 17.8 GB weight pool lands on the WSL
GPU, and the engine produces correct greedy output. The remaining gap is throughput, which is a
known property of the current clean-room scaffold rather than anything about Windows or WSL.

## Reproduction (WSL)

```bash
# 1. weights (35.9 GB) + tokenizer
hf download peonist-ai/halogen-qwen3.8-27b --local-dir ~/halogen-models   # or the safe-download path used here

# 2. build chlorine-server with the Ciru ROCm 10 SDK
git clone https://github.com/Heretek-AI/chlorine-server
R=~/ciru-runtime
export VLLM_SOURCE=$R/sources/vllm-glm53-strix VLLM_VENV=$R/venv AITER_SOURCE=$R/sources/aiter-gfx1151
source "$VLLM_SOURCE/runtime-env.sh"
export HSA_ENABLE_DXG_DETECTION=1
cd chlorine-server
cmake -S engine -B build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$ROCM_PATH/lib/llvm/bin/clang++"
cmake --build build -j 20

# 3. inspect + serve
python3 converter/hgn-inspect.py /path/to/qwen3.8-27b-p1w4d-d2.hgn
./build/chlorine --checkpoint /path/to/qwen3.8-27b-p1w4d-d2.hgn --serve --port 8730
```

Scripts: `.revn-data/orchestrator/build-chlorine.sh`, `run-chlorine-serve.sh`, `cl-gen.py`,
`chlorine-client.py`.
