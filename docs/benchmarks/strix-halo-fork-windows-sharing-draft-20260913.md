# Sharing draft: the Strix Halo llama.cpp fork on **Windows/WSL** — measured (draft 2026-09-13)

Founder request: share our work, especially that it **works on Windows** (not native Linux), with
measures and honest pros/cons of the speed difference the WSL path makes.

Status of this draft: the **kernel A/B is measured**; the **custom-quant prefill number is pending**
(the 95.8 GiB model is still downloading). Nothing below claims the 1200 t/s figure as ours yet.

---

## The two-line summary

`pwilkin/llama.cpp` branch `strix-halo` is an open-source fork with hand-written **gfx1151 kernels**
(tiled Gated-DeltaNet, sparse lightning-indexer attention, HC fusions, bf16 WMMA dequant GEMM, and a
lazy "direct" PLE reader) that pushes Qwen3.8-Flash-Next prefill from ~50 t/s (vanilla llama.cpp) into
the hundreds. **We built that fork under WSL2 on Windows** — no native Linux — and it runs. The
custom ROCr/PM4 runtime their installer also builds needs `/dev/kfd` and does **not** work on WSL; we
get the kernel/prefill wins but not the full decode boost.

## Why this matters (the Windows angle)

The fork's own installer targets native Linux (`/dev/kfd`, `/sys/module/amdgpu`, `gfx1151` in KFD
topology). WSL exposes only `/dev/dxg`, so the installer refuses. But **llama.cpp itself** builds fine
against the ROCm 10 SDK over the DXG bridge (`HSA_ENABLE_DXG_DETECTION=1`). What we did:

- cloned `pwilkin/llama.cpp@strix-halo` at the pinned commit `f5daaa3c`
- configured with the fork's own flags:
  `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_HIP_NO_VMM=ON
   -DGGML_HIP_MMQ_MFMA=ON -DGGML_CUDA_FA=ON -DGGML_HIP_RCCL=OFF`
- built `llama-server` + `llama-bench` with the ROCm clang from the ROCm SDK venv
- ran it: the fork's kernels engage — the log prints `FORK_GDN_TILE`, `FORK_COMPACT`,
  `QSA_SCORE_BOUNDS active`, `MMB_BLK16` — proving the tuned paths are live on DXG, not falling back.

No custom ROCr/HIP build, no `sudo`, no replacing system ROCm.

## Measured on this box

Hardware: Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), 128 GB LPDDR5X, Windows 11 + WSL2 (Ubuntu 24.04).
GPU pool 81,564 MiB at the current carve. All numbers `llama-bench -ngl 99 -fa 1`, one model at a time.

### Flash-Next — stock quant (unsloth UD-IQ4_XS), *pending full A/B*

| Build | Prefill @~36k ctx | Decode | Notes |
| --- | ---: | ---: | --- |
| this fork (server, lazy-direct) | **300.8 t/s** | 6.97 t/s | mid-context prompt; PLE lazy-read |
| earlier Windows Vulkan (myhacsint) | ~200 t/s | ~20 t/s (MTP) | different runtime, MTP on |

(The clean `llama-bench` fork-vs-mainline A/B on Flash-Next was interrupted by a host restart; it is
being re-run. The **custom IQ4_NL quant** — the one their 1204 t/s was measured on — is still
downloading; that number is *theirs until we reproduce it*.)

### The honest kernel A/B: the fork is **not** universally faster

Run on two architectures we have locally, fork vs a mainline llama.cpp HIP build, same machine:

| Model (arch) | Build | pp512 | pp4096 | tg128 |
| --- | --- | ---: | ---: | ---: |
| **Qwen3.8-27B** (`qwen35`) | **fork** | 204.6 | 252.4 | **12.0** |
| | mainline | **244.8** | **265.2** | 10.8 |
| **Ornith 1.5 35B-A3B MTP-23G-ICE** (`qwen35moe`) | **fork** | 461.5 | **528.5** | 42.0 |
| | mainline | **505.8** | 514.7 | **46.3** |

**Reading:** the fork gives the 27B ~**+11% decode** (12.0 vs 10.8 t/s) at ~10–16% *lower* prefill, and
is *slightly slower* than mainline on Ornith. That is the expected shape — **the fork's optimizations
target the `qwen4exp` (Flash-Next) architecture**; on it they are worth multiples (their journey doc:
6.07× prefill overall, with tiled Gated-DeltaNet alone 2.37× and the lazy PLE reader 2.75×). On other
architectures there is little or nothing to gain, and measurement noise can put mainline ahead.

**So: use this fork for Flash-Next (and Qwen3.8-27B, where it still helps decode). For everything else,
mainline is fine.**

## Can we run *any* quant? Yes — with two caveats

- **Any GGUF loads.** We proved it by running the **stock unsloth `UD-IQ4_XS`** (not the author's
  quant) on this fork. No reprocessing needed.
- **But the fastest path wants their layout.** The 3–4× gap between our ~300 t/s and their ~1200 t/s is
  the quant: their `IQ4_NL` "PROJFIX" projection layout feeds the bf16 WMMA dequant path directly. A
  stock quant engages the kernels but less efficiently. To hit their number, use their quant.
- **Some quants need a *different* fork.** Ornith's `ROCmFP4` GGUF does **not** load in either build:
  `tensor 'output.weight' has invalid ggml type 101`. It needs `LaurentZuijdwijk/llama.cpp`
  (`vulkan/qwen4exp-rocmfpx`). So "any quant" means "any *standard* llama.cpp quant"; community
  fp4 variants can be fork-locked.

## Pros and cons of doing this on Windows/WSL (the key difference)

**Pros**
- Works with the **stock ROCm-over-DXG** path — no native Linux install, no custom ROCr build, no
  `sudo`, no touching `/opt/rocm`.
- The fork's **prefill kernels engage** on DXG (verified by the log lines), which is the hard part and
  the part a World Engine cares about.
- **Open source** (MIT fork) — unlike Halogen's closed binary, we can inspect and patch it.
- Any standard GGUF quant runs; swapping quants is a restart, not a rebuild.

**Cons / what you give up vs native Linux**
- **No PM4-replay / retained-graphs decode boost.** Their custom ROCr+HIP runtime needs `/dev/kfd`.
  We forgo the decode side of their tuning (their ~26 t/s decode vs our ~12 on the same model).
- **HSA_OVERRIDE_GFX_VERSION + unified-memory env are ours to manage**; the installer's driver checks
  are native-only.
- **Raw memory access is slower.** Weights on `/mnt/c` (9p) made a 87 GiB load take ~10–13 min; staging
  to WSL ext4 first is required for sane load times and lazy-read performance.
- **Memory pressure is real and can crash the host.** WSL's `memory=` cap plus concurrent heavy jobs
  can starve Windows. On a 128 GB box with a 32 GB carve (Windows sees ~95 GB), a 90 GB WSL cap plus a
  download + two benchmarks **hard-restarted the PC**. We now cap WSL at 72 GB and run **one heavy job
  at a time**.
- **Halogen Flash-Next does not work here at all** (for completeness): its pinned path needs ~68 GiB of
  contiguous host memory, and WSL's balloon-backed RAM fragments below 2 MiB, so `CreateContext` fails
  at every carve (0.5/8/16/32 GB tried). That is exactly why the mmap-based llama.cpp fork is the right
  answer on Windows.

## Reproduce it

```bash
# 1. in WSL, with a ROCm SDK that talks over DXG (we used a vLLM/ROCm venv)
git clone --filter=blob:none --single-branch --branch strix-halo https://github.com/pwilkin/llama.cpp
cd llama.cpp && git checkout f5daaa3cfa6358e5dd398911ec741813745a5440
cmake -S . -B build-hip -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_HIP_NO_VMM=ON \
  -DGGML_HIP_MMQ_MFMA=ON -DGGML_HIP_RCCL=OFF -DGGML_CUDA_FA=ON -DGGML_VULKAN=OFF
cmake --build build-hip --parallel 20 --target llama-server llama-bench

# 2. run (the two flags that matter)
export HSA_ENABLE_DXG_DETECTION=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1
./build-hip/bin/llama-server -m <flash-next>.gguf -ngl 999 -fa on --load-mode none --lazy-mode on-direct \
  -c 65536 -b 16384 -ub 16384 --jinja \
  --spec-type draft-mtp --spec-draft-model <draft>.gguf
```

## What is still missing from this draft

- The fork-vs-mainline `llama-bench` A/B on **Flash-Next** (re-running).
- The **custom IQ4_NL quant** prefill/decode (downloading ~95.8 GiB) to confirm the ~1200 t/s claim
  **on Windows/WSL**, which nobody has published — the author's number is native Linux.
