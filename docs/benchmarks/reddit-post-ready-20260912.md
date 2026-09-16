# Reddit post — READY TO PUBLISH (English)

**Not published.** Posting is an external action and needs the founder's explicit go-ahead for that
exact action. Everything below is paste-ready.

---

## TITLE

**Ciru's Ornith Halo Agent on a Windows Strix Halo box: full 262K / 44 GiB profile in WSL2, ~2.4k tok/s prefill at 64K**

_(Alternatives: "Windows Strix Halo: running Ciru's vLLM/ROCm Ornith build in WSL2 — how I did it and what it measures" · "I got Ciru's Ornith 35B agent running on Windows (WSL2, /dev/dxg): numbers + method")_

## FLAIR

`Guide` or `Discussion` (r/StrixHalo)

---

## BODY

I got Ciru's **Ornith1.5-Ciru-Halo-Agent** — the custom vLLM/ROCm `gfx1151` build that Ciru
validated on NixOS and warns that *stock vLLM does not reproduce* — running on a **Windows 11
Strix Halo machine inside WSL2**, on the **full production profile: 262,144-token context, 44 GiB
shared KV pool, 8 active sequences**.

Measured on this box: **~1.6–2.4k tok/s cold prefill (32K–64K)** and **269 tok/s aggregate at
C8** on short coding tasks. Two non-obvious fixes were needed, both Windows/WSL-specific, and I
think they'll help anyone else trying to run these Linux/ROCm agent builds on a Windows Strix Halo.

### Hardware

| | |
| --- | --- |
| APU | Ryzen AI Max+ 395 / Radeon 8060S (`gfx1151`) |
| Machine | BOSGAME BeyondMax, 128 GB unified memory (8×16 GB) |
| Memory split | **32 GB system RAM / 96 GB GPU carve-out** |
| OS | **Windows 11 (build 26200)** + **WSL2 `Ubuntu-24.04`** (kernel 6.18) |
| Windows GPU driver | AMD 32.0.31041.1004 |
| Runtime | Ciru's pinned vLLM `0.1.0rc2.dev9+g9255fd9fb9.rocm100` + AITER, ROCm SDK 10.0.0, PyTorch 2.13.0+rocm10.0.0, Python 3.14.3 |

### The problem

Ciru's release targets **native Linux on Strix Halo** — the shipped wheels are
`cp314-linux_x86_64` and the author's validated host is NixOS with Linux 7.2.2. On this Windows box
the first attempt died before loading anything:

```
Cannot load librocdxg.so: cannot open shared object file
dlsym failed: libhsa-runtime64.so.1: undefined symbol: hsaKmtOpenKFD
Segmentation fault (exit 139)
```

### Fix #1 — the DXG bridge (`librocdxg`), inside WSL2

Everything runs in **WSL2**, which reaches the GPU through **`/dev/dxg`** — there is **no
`/dev/kfd`** on WSL. `librocdxg` is the library that carries the KFD calls over DXG, and it was
missing from every library path.

The distro's ROCm 7.2.0 tree didn't help: it's inconsistent (a downgraded `libhsa-runtime64 5.7.1`
leaves `hsaKmtOpenKFD` unresolved). The key realization: **the ROCm 10.0.0 SDK libraries that the
Ciru runtime venv itself installs do ship `librocdxg.so`** — so point the loader at *those* plus
`/usr/lib/wsl/lib` (which has `libdxcore.so`):

```bash
SP=$VIRTUAL_ENV/lib/python3.14/site-packages
export CIRU_HOST_LIBRARY_PATH="$SP/_rocm_sdk_devel/lib:$SP/_rocm_sdk_core/lib:$SP/_rocm_sdk_libraries/lib:/usr/lib/wsl/lib"
export HSA_ENABLE_DXG_DETECTION=1
```

After that, `rocminfo` reports **`AMD RYZEN AI MAX+ 395 w/ Radeon 8060S`** and PyTorch runs on the
GPU (`torch.cuda.is_available() == True`).

### Fix #2 — a false low-memory report breaks vLLM's startup guard

vLLM's worker refuses to start when `free_memory < total_memory × gpu_memory_utilization`. Under
WSL/DXG the ROCm runtime reports only **~16 GB "free"** out of the **119.9 GB** it claims total.
But the memory is really there — an allocate-and-fill test committed **~88 GB** without OOM.

With the default `0.8` that becomes `0.8 × 119.9 = 89 GB > 16 GB` → refused, even though the
allocation succeeds. Make `gpu_memory_utilization` overridable and set it low **only to satisfy the
guard**; the KV size is explicit (`--cache-gib 44`), so the cache does **not** shrink:

```python
# bundle/plugin-site/ornith_g256/launch.py
gpu_memory_utilization=float(os.environ.get('ORNITH_GPU_UTIL', '0.8'))
```
```bash
export ORNITH_GPU_UTIL=0.10   # 0.10 × 119.9 = 12 GB < 16 GB reported
```

Also raise the WSL VM memory cap (`.wslconfig`) — the model is 24.5 GB on disk, 21.17 GiB resident:

```ini
[wsl2]
memory=30GB
processors=24
swap=48GB
```

### Result — full production profile, on Windows/WSL2

```
reserved 44.0 GiB memory for KV Cache
GPU KV cache size: 1,521,544 tokens
Maximum concurrency for 262,144 tokens per request: 5.80x
Model loading took 21.17 GiB memory
```

**Cold prefill (single request, server counters):**

| Context | This Windows/WSL2 host | Ciru's native-Linux figure |
| ---: | ---: | ---: |
| 32K | 1,581 tok/s | 1,509 |
| **64K** | **2,359 tok/s** | 1,287 |
| 128K | 1,691 tok/s | 983 |
| 200K | 1,736 tok/s | ~668 @256K |

**Decode (C1, greedy, thinking off):**

| Workload | This host | Ciru published |
| --- | ---: | ---: |
| Short coding (natural EOS) | 78.7 tok/s | 178 (their 10-task screen) |
| Coding, 1024 tokens | 81.3 tok/s | — |
| Prose, 1024 tokens | 40.2 tok/s | 49.9–63.3 |

**Concurrency (short coding burst):**

| Concurrency | Mean per request | Aggregate |
| ---: | ---: | ---: |
| C1 | 78.7 tok/s | 77.6 tok/s |
| C2 | 45.3 | 83.7 |
| C4 | 57.9 | 190.0 |
| **C8** | 43.8 | **269.0 tok/s** |

### Why this matters (context for agent users)

For worker/agent workloads that read a big context every turn, **prefill dominates wall time**. Same
box, llama.cpp (Vulkan), C1:

| Model / quant | prefill 8K | prefill 32K | prefill 64K | decode 32K |
| --- | ---: | ---: | ---: | ---: |
| Ornith ROCmFP4 | 1,452 | 1,045 | 712 | 85.0 |
| Ornith 23G-ICE | 1,490 | 1,070 | 725 | 74.0 |
| Ornith UD-Q4_K_XL | 1,429 | 1,075 | 725 | 75.9 |
| Qwen3.8-Flash-Next UD-IQ4_XS | 458 | 303 | 258 | 41.4 |

So Ciru's prefill at 64K is **~3×** the fastest local llama.cpp Ornith quant and **~9×**
Flash-Next on the same machine — exactly the property you want when several agents each load a
working history.

### Honest caveats

- **This is WSL2, not native Windows ROCm.** The model runs in the Linux VM and reaches the GPU over
  `/dev/dxg`. I'm not claiming native Windows ROCm support.
- **I did not reproduce Ciru's 178 tok/s C1 figure.** I get ~81 tok/s on 1024-token generations and
  **269 tok/s aggregate at C8 vs their 295**. Their 178 is a 10-question HumanEval screen with
  short, naturally-ending answers and TTFT subtracted; longer generations carry a declining tail.
  The **C8 aggregate and the prefill rates land essentially at parity with the native numbers**.
- **Coding is the strong case; prose is roughly half** (~40 tok/s here; Ciru's own notes say
  49.9–63.3 tok/s prose).
- **Use `enable_thinking: false`** with the shipped chat template. A naive request without it goes
  through a reasoning pass first (you'll see `<think>` in the output).
- Prefill numbers come from short-output requests — treat them as backend prefill rates, not
  sustained throughput.
- I did not independently grade correctness (Ciru reports 60/60 base+extended health on their screen).
- Thanks to **Ciru (`jcbtc`)** for the build and to **AMD** for the hardware sponsor program — this
  is just getting their Linux work to run on the other side of the fence.

### Reproduce (WSL2)

```bash
# 1. weights
hf download jcbtc/Ornith1.5-Ciru-Halo-Agent-vllm-strix-halo --local-dir ./ciru-halo-agent

# 2. pinned runtime (no stock vllm)
cd ciru-halo-agent
bash runtime/INSTALL-ORNITH-RUNTIME.sh "$PWD/installed-runtime"

# 3. the two fixes above, then:
export ORNITH_GPU_UTIL=0.10
bash bundle/serve.sh --host 127.0.0.1 --port 8000
```

The OpenAI-compatible endpoint is then on `127.0.0.1:8000` and reachable from Windows.

### Next up: Qwen 3.8 27B "Halogen"

Same approach, next model — **`peonist-ai/halogen-qwen3.8-27b`** (Qwen3.8-27B, `gfx1151`/ROCm build).
I'll run it through the **identical WSL2 + `/dev/dxg` stack** and post a matched
**Windows-WSL2 vs native-Linux comparison**. It should need far less memory than the 35B, so the
44 GiB KV profile should be easy to fit. If anyone here has already run Halogen on Strix Halo and has
known-good launch parameters, I'd love to hear them.

---

## Notes for the poster (not part of the post)

- r/StrixHalo rules: check the sidebar for a self-promotion/no-low-effort rule; this is original
  measurement content, so it should be fine. Flair as Guide/Discussion.
- If the founder prefers shorter, cut the "Honest caveats" into 3 bullets and drop the llama.cpp
  comparison table.
- Do **not** claim native Windows ROCm anywhere — the community will (correctly) push back.
- The Halogen repo is `peonist-ai/halogen-qwen3.8-27b` (34 GB `.hgn`, tags: halogen, strix-halo,
  gfx1151, rocm, amd, base Qwen/Qwen3.8-27B, Apache-2.0). There is also a
  `peonist-ai/halogen-qwen3.8-flash-next`.
