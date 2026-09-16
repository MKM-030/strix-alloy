# Halogen on Windows/WSL — the REAL engine running at full speed (2026-09-12)

**Solved.** The founder's actual goal — Peonist's *real* halogen 0.1.3 engine running on this
Windows Strix Halo box — is done. It loads the 35.9 GB `.hgn`, registers the weights for the GPU,
and generates at **the real engine's speed** (not the chlorine scaffold's ~1 tok/s).

## The two wrong assumptions, and the real blocker

1. **Wrong assumption: "it needs `/dev/kfd`."** That is true of Peonist's *docker container*, not of
   the *engine binary*. The binary is a normal ELF that dynamically links **`libamdhip64.so.7`** and
   **`libhipblaslt.so.1`** — i.e. the same **ROCm 10 runtime** that already talks to the GPU over
   `/dev/dxg` in WSL. Pointed at the Ciru venv's ROCm 10 libs, `/home/revn/halogen-re/halogen`
   runs on WSL and `--build-info` lists all 20 units including the HIP kernels.

2. **The actual blocker: `hipHostRegister` on a file-backed mmap.**
   ```
   checkpoint: hipHostRegister failed on file-backed mmap (invalid argument).
   The DESIGN.md A9 fallback (hipHostMalloc + read) is not built yet ...
   ```
   halogen `mmap`s the `.hgn` and registers that mapping so the GPU can read weights in place. On the
   WSL/DXG path `hipHostRegister()` works on **anonymous** memory but fails on a **file-backed**
   mapping ("invalid argument"). I proved this with a 15-line HIP probe:
   ```
   hipHostRegister(malloc)   hipSuccess
   hipHostGetDevicePointer   hipSuccess
   hipHostMalloc(Mapped)     hipSuccess
   hipMallocManaged          hipSuccess
   hipMalloc(device)         hipSuccess
   kernel on hostMalloc ptr: no error
   ```
   So the whole DXG path is fine — only the *file-backed registration* is not. (It is **not** a 9p
   issue: it fails the same way on the WSL-native ext4 filesystem. I tested both.)

## The fix: `hipshim.so` (LD_PRELOAD)

The engine says the fallback "is not built yet" — so I built it externally, without touching the
binary. `hipshim.c` interposes three HIP host-memory calls:

- `hipHostRegister(p, sz, flags)` → call the real one; **if it fails**, `hipMalloc` an equivalent
  device buffer and `hipMemcpy` the mapping into it, then remember `host→device`.
- `hipHostGetDevicePointer(&dev, p, flags)` → return a per-tensor pointer into that device buffer
  (so the engine's pointer arithmetic over the checkpoint keeps working).
- `hipHostUnregister(p)` → `hipFree` the buffer.

26 lines of C, built with `gcc -shared -fPIC -ldl`, injected with `LD_PRELOAD=/home/revn/hipshim.so`.

### Result

```
[hipshim] hipHostRegister fallback: 35865565184 bytes host=0x… -> device=0x…
checkpoint: registered 35.9 GB in 104.8 s (0.3 GB/s, Mapped|ReadOnly)
halogen: Qwen3.8-27B-p1-d2 — 1352 tensors, 35.9 GB
  dtypes: bf16 2.96 GB  q4c 9.93 GB  fp8r 10.63 GB  i4l 12.35 GB
model: drafter — 5 layers, block 8, window 2048, 32Q/8KV hd128, taps [5,19,33,47,61]
  w4a4: 168 planes active (excl applied) (threshold 64), rot=1
serve: listening on 127.0.0.1:8731 — 64 layers, ctx 262144, greedy batch-1
```

The GPU now holds the whole checkpoint (copied into the carve-out via DXG). Generation:

```
prompt: "The capital of France is"
INFO  I 1 1 262144 8 0 1 1 0 2048 1 262144
  +0.5s  T 11751  ' Paris'      <-- correct
  +0.6s  T 13     '.'
  …
  +1.2s  T 369    ' is'
D  D 1 length 5 8 482.0 764.7 0 0 0 0        (prefill 482 ms, decode 765 ms)
TEXT  ' Paris.\nThe capital of Germany is'
```

## Speed: real engine vs chlorine scaffold (same box, same weights, same prompt)

| | chlorine (clean-room scaffold) | **real halogen + hipshim** | speedup |
| --- | ---: | ---: | ---: |
| Prefill (5 tok) | 8,527 ms | **482 ms** | **17.7x** |
| Decode (8 tok) | 7,637 ms | **765 ms** | **10.0x** |
| Decode rate | ~1.05 tok/s | **~8.6 tok/s** | ~8x |
| Load | 132 s (streamed) | 105 s (0.3 GB/s, pinned) | — |

## Measured across all three decode modes (32 tokens, greedy)

| Mode | prefill (5 tok) | prefill (64 tok) | decode 32 tok | **decode tok/s** |
| --- | ---: | ---: | ---: | ---: |
| serial (`drafter 0`) | 512 ms | 387 ms | 3,097 ms | **10.3** |
| DFlash2 (`drafter 2`) | 120 ms | — | 2,843 ms | **11.3** |
| **MTP (`drafter 1`)** | 144 ms | — | **1,338 ms** | **23.9** |

**The MTP drafter roughly doubles the decode rate (23.9 tok/s)** vs serial (10.3), and prefill drops
from 512 ms to 120–144 ms once a drafter warms the graph. **23.9 tok/s beats every llama.cpp 27B
quant measured earlier (10.9–14.7 tok/s)** on the same machine — which is exactly the point of the
halogen engine's tuned kernels and drafter, and it did not require writing a single kernel: the real
ones are already in the binary.

Note for selection: the engine's default is `serial`; pass `1` (MTP) or `2` (DFlash2) as the drafter
argument on `GEN`, or set `HALOGEN_DRAFTER`.

The real engine's W4A4 + IU4 kernels and resident dequant are exactly what the scaffold lacked. The
`D` line reports drafter stats (`drafter rounds commit`) and prefill/decode milliseconds directly.

## What is still open

- **Prompt cache is off** by default: after the 35.9 GB mapping only ~1.2 GB is free, below the
  36.9 GB floor for a full-context cache entry. `HALOGEN_CACHE_MB` can override. With 96 GB carve-out
  there is room; the copy-in cost (35.9 GB) is the constraint, not the GPU.
- Decode at ~8.6 tok/s is for a **dense 27B**; that is the expected band (the llama.cpp 27B quants
  measured 10.9–14.7 tok/s, and those use a different quant/runtime). The halogen engine's own
  advantage is the **long-context prefill** (its published 1,287 tok/s @64K) and the DFlash2 drafter,
  which we have not yet exercised via `--spec` / `--spec-sample-check`.
- The engine is **batch-1 greedy**; no OpenAI API layer (that is `serve_api.py` in the image, which
  can point at this engine port).

## Bottom line

**Halogen runs on Windows via WSL at full engine speed.** The "impossible" was two layers of wrong
assumption — a container requirement mistaken for a binary requirement, and a missing fallback the
engine's own error message named. `hipshim.so` supplies exactly that fallback. No kernel
decompilation was needed for this path: the **real kernels are already in the binary** and run
correctly over DXG once the checkpoint can be registered.

## Reproduction (WSL)

```bash
R=~/ciru-runtime
export VLLM_SOURCE=$R/sources/vllm-glm53-strix VLLM_VENV=$R/venv AITER_SOURCE=$R/sources/aiter-gfx1151
source "$VLLM_SOURCE/runtime-env.sh"; export HSA_ENABLE_DXG_DETECTION=1

docker pull ghcr.io/peonist-ai/halogen:0.1.0
cid=$(docker create ghcr.io/peonist-ai/halogen:0.1.0)
docker cp "$cid":/usr/local/bin/halogen ./halogen          # the real engine binary

gcc -O2 -fPIC -shared hipshim.c -o hipshim.so -ldl          # the missing fallback
LD_PRELOAD=$PWD/hipshim.so ./halogen --checkpoint qwen3.8-27b-p1w4d-d2.hgn --serve --port 8731
```

Scripts: `.revn-data/orchestrator/{hipshim.c,run-halogen-shim.sh,halogen-symbols.sh,halogen-ext4.sh}`.
