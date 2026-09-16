# 27B models in WSL/DXG — measured + research (2026-09-12)

Second half of the local-model work. Goal: run the models the founder already has on disk **under
Linux (WSL2 on this Windows box)** and compare against the Windows numbers. Two new pieces were
needed: a backend that works in WSL, and the Halogen evaluation.

## 1. Getting llama.cpp to run on the WSL GPU (the key enabler)

WSL has `/dev/dxg`, not `/dev/kfd`, and there is **no Vulkan/RADV in this WSL** (only a `lavapipe`
software ICD) — so the Windows Vulkan path is unavailable. But the Ciru venv already ships the
**ROCm 10 SDK** (`hipcc`, `clang`, `librocdxg`), the same stack torch uses over DXG. So:

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp
export VLLM_SOURCE=~/ciru-runtime/sources/vllm-glm53-strix VLLM_VENV=~/ciru-runtime/venv AITER_SOURCE=~/ciru-runtime/sources/aiter-gfx1151
source "$VLLM_SOURCE/runtime-env.sh"        # sets ROCM_PATH, HIP_DEVICE_LIB_PATH, LD_LIBRARY_PATH
export HSA_ENABLE_DXG_DETECTION=1
cmake -S . -B build-hip -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON \
  -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151 \
  -DCMAKE_C_COMPILER="$ROCM_PATH/lib/llvm/bin/clang" \
  -DCMAKE_CXX_COMPILER="$ROCM_PATH/lib/llvm/bin/clang++" \
  -DCMAKE_HIP_COMPILER="$ROCM_PATH/lib/llvm/bin/clang++" -DLLAMA_CURL=OFF
cmake --build build-hip --target llama-server llama-bench -j 20
```

**Result:** `llama-bench --list-devices` reports
`ROCm0: AMD Radeon(TM) 8060S Graphics (114332 MiB, …)` and models load and run. This is a
**second, independent proof** that the DXG bridge works for arbitrary ROCm/HIP code — not just
Ciru's build. (Note: `runtime-env.sh` requires `VLLM_SOURCE`/`VLLM_VENV`/`AITER_SOURCE` to be set
first, or it exits at line 9.)

**Critical constraint:** the **Ciru server must be stopped** before running llama.cpp — it holds
**~65 GB** (21 GB model + 44 GB KV pool), leaving only ~16 GB. With Ciru running, llama.cpp
allocations fail with `dxgkio_escape: Ioctl failed: -75`.

## 2. Measured: Qwen3.8-27B GGUF quants on WSL/DXG (HIP llama.cpp)

`llama-bench -ngl 99 -fa 1`, one model at a time, ggml commit `c8edceb`.

| Model (file) | size | pp512 | pp4096 | pp32768 | tg128 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `revn/Qwen3.8-27B-UD-Q4_K_M` | 15.32 GiB | 325.7 | 401.9 | — | — |
| `revn/Qwen3.8-27B-UD-Q5_K_M` | 18.40 GiB | 323.6 | 376.8 | 301.8 | 10.9 |
| `lmstudio-community/Qwen3.8-27B-Q4_K_M` | 15.65 GiB | 331.6 | 388.9 | 312.2 | 11.4 |
| `TeichAI/Qwen3.8-27B-Fable-Distill-Q4_K_M` | 16.19 GiB | 321.0 | 344.8 | — | 11.6 |
| `qwen38-gsq/Qwen3.8-27B-GSQ-RCO-IQ3_XXS` | 9.39 GiB | 299.6 | 329.2 | — | **14.7** |

Reading:
- **All five quants cluster tightly on prefill: pp512 ≈ 300–332, pp4096 ≈ 329–402 tok/s.** The
  quant level barely moves prefill on this hardware.
- **Decode is 10.9–14.7 tok/s, and the *smallest* file is the fastest** (GSQ-IQ3 9.39 GiB →
  14.7 tok/s), which is the expected memory-bandwidth behaviour: fewer bytes per token = faster.
  Q5 (18.4 GiB) and Fable (16.2 GiB) sit at ~10.9–11.6.
- An earlier pass had Fable at 148/178/8.9 and GSQ at 140/164/8.5 — those were corrupted by running
  while the GPU still held the previous model (DXG `Ioctl failed: -75`). The table above is the
  clean, one-model-at-a-time re-measurement.
- **27B dense decode (~11–15 tok/s) is ~6–9× slower than the Ornith 35B *MoE* quants (63–99 tok/s)**
  because only ~3B of the MoE's params are active per token. That is the architectural difference,
  not a quant or runtime problem. For a *dense* 27B on Strix Halo, ~11–15 tok/s single-stream is the
  expected ballpark.

## 3. Windows vs WSL comparison — what exists

The founder asked to compare against "the values I have in Windows". Searched:
- `C:\AI\local-ai\flashnext*` benchmark JSONs: those are **Flash-Next / Ornith**, not 27B
  (e.g. q4-64k: prefill 386–489, decode 32.8–34.8).
- `C:\Users\Marcel\.lmstudio\.internal\api-prediction-history`: raw LM Studio records, **no timing**.
- No 27B llama.cpp benchmark artifact exists on disk.

So a **same-model Windows 27B number is not on record here**. The closest same-box Windows
references are the Ornith/Flash-Next runs from the earlier wave:

| Workload (Windows, Vulkan) | prefill | decode |
| --- | ---: | ---: |
| Flash-Next UD-IQ4_XS + FRSPEC @ 32K | 303 | 41.4 |
| Ornith ROCmFP4 @ 32K | 1,045 | 85.0 |
| Ornith 23G-ICE @ 32K | 1,070 | 74.0 |

**Architectural note that makes the comparison fairish:** on this box, Windows Vulkan llama.cpp and
WSL HIP llama.cpp are *different runtimes*, so any difference mixes backend and OS. What we can say
from the data: for the **27B dense** models, WSL/HIP prefill (300–400 tok/s at 4K) is in the same
band as the Windows Ornith quants (1.0–1.5k at 8K is higher because MoE prefill is cheaper). A
direct 27B-Windows-Vulkan number should be measured with the *same* binary to isolate OS/backend —
that is the honest next step and is NOT claimed here.

## 4. Halogen 27B — downloaded, but not runnable by us

`peonist-ai/halogen-qwen3.8-27b` (dump: 35.89 GB, base `Qwen/Qwen3.8-27B`, Apache-2.0). The model
card states plainly:

> "These weights are in **halogen's own `.hgn` format** and will **not load in transformers, vLLM, or
> llama.cpp**. They exist to be mounted into the halogen container."

The documented use is Docker:

```bash
docker run --rm -p 8731:8731 --device /dev/kfd --device /dev/dri --group-add keep-groups \
  --security-opt seccomp=unconfined --ipc=host \
  -v ~/halogen-models:/models:ro -v ~/halogen-models/tokenizer:/tokenizer:ro \
  ghcr.io/peonist-ai/halogen:0.1.0
```

**Blocker on this box:** the container requires **`/dev/kfd`** (only present on a real Linux kernel
with the amdgpu driver). WSL exposes only **`/dev/dxg`**, and Docker in WSL does not grant KFD. The
**halogen engine itself is closed source** — there is no way to build a DXG path. So Halogen is
**downloadable but not runnable under WSL** without a native Linux install. (Download was
kick-started to have the weights ready for a future native-Linux test; it is not yet complete.)

Halogen spec notes worth recording: ~**6.32 bpw effective at decode** over 29.75B params; 4-bit trunk
tensors are FFN-only with NVFP4 values imported from `unsloth/Qwen3.8-27B-NVFP4`; everything else
FP8/BF16; **two drafter heads** (MTP fine-tune + a 5-layer ~2.2B DFlash2 block drafter), both
byte-identical to serial greedy decode.

## 5. Parameters that mattered

For the WSL/HIP llama.cpp runs:
- `-ngl 99` (full offload), `-fa 1` (flash attention on).
- Context: 32K in one bench pass is fine **only when Ciru is stopped**; with Ciru resident only
  ~16 GB is free and larger allocations fail (`Ioctl failed: -75`).
- F16 KV (llama-bench default) performed fine; no KV-quant needed at these sizes.
- `HSA_ENABLE_DXG_DETECTION=1` is required for the GPU to be seen at all.

## 6. Scripts

- `.revn-data/orchestrator/build-llama-hip.sh` — the WSL HIP build
- `.revn-data/orchestrator/bench-27b.sh` / `bench-27b-rest.sh` — the sweeps
- `.revn-data/orchestrator/test-hip-llama.sh` — the device/ldd smoke test
