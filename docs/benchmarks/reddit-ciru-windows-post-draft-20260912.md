# Reddit post draft — r/StrixHalo

**Status: DRAFT ONLY — not published.** Publishing is an external side effect; it needs the
founder's explicit go-ahead for that exact action. This file is the reviewable draft.

---

## Title (pick one)

1. **Ornith1.5 Ciru Halo Agent running on Windows via WSL2 — 2.3k tok/s prefill at 64K, 269 tok/s aggregate at C8**
2. **Ciru's vLLM/ROCm Ornith build on a Windows Strix Halo box (WSL2 + /dev/dxg): how I got it working and what it measures**
3. **Windows Strix Halo: Ciru Halo Agent under WSL2 — full 262K/44 GiB profile, measured prefill and concurrency**

Recommended: **#2** (specific, honest framing).

---

## Body

**TL;DR** — I got Ciru's `Ornith1.5-Ciru-Halo-Agent` (the custom vLLM/ROCm gfx1151 build that the
author validated on NixOS and warns "stock vLLM does not reproduce") running on a **Windows 11
Strix Halo machine inside WSL2**, on the **full production profile: 262,144-token context, 44 GiB
shared KV pool, 8 active sequences**. Measured **~1.6–2.4k tok/s cold prefill (32K–64K)** and
**269 tok/s aggregate at C8** on short coding tasks. Two fixes were needed: the DXG bridge library
path, and working around a false low-memory report from the ROCm runtime under WSL.

### Hardware

| | |
| --- | --- |
| APU | Ryzen AI Max+ 395 / Radeon 8060S (gfx1151) |
| System | BOSGAME BeyondMax, 128 GB unified memory (8×16 GB) |
| Split | BIOS/driver: **32 GB system RAM / 96 GB GPU carve-out** |
| OS | **Windows 11 (build 26200)** + WSL2 `Ubuntu-24.04` (kernel 6.18) |
| Windows driver | AMD 32.0.31041.1004 |
| Runtime | Ciru's pinned vLLM `0.1.0rc2.dev9+g9255fd9fb9.rocm100`, AITER, ROCm SDK 10.0.0, Python 3.14.3 |

### The problem

Ciru's release targets **native Linux on Strix Halo**. The shipped wheels are
`cp314-linux_x86_64`; the author's validated host is NixOS with kernel 7.2.2. Stock vLLM does not
reproduce the build. The earlier attempt on this box failed with:

```
Cannot load librocdxg.so: cannot open shared object file
dlsym failed: libhsa-runtime64.so.1: undefined symbol: hsaKmtOpenKFD
Segmentation fault (exit 139)
```

### How it runs on Windows (WSL2)

Everything runs inside **WSL2 Ubuntu 24.04**, which reaches the GPU through **`/dev/dxg`** (there is
no `/dev/kfd` on WSL). Two things were needed:

**1. The DXG bridge (`librocdxg`) — the real blocker.**
The distro's ROCm 7.2.0 tree is inconsistent (a downgraded `libhsa-runtime64 5.7.1` leaves
`hsaKmtOpenKFD` unresolved). The trick: use the **ROCm 10.0.0 SDK libraries that the Ciru runtime
venv itself installs** — those ship `librocdxg.so` — and point the loader at them plus
`/usr/lib/wsl/lib` (which has `libdxcore.so`):

```bash
export CIRU_HOST_LIBRARY_PATH="$SP/_rocm_sdk_devel/lib:$SP/_rocm_sdk_core/lib:$SP/_rocm_sdk_libraries/lib:/usr/lib/wsl/lib"
export HSA_ENABLE_DXG_DETECTION=1
```

After that, `rocminfo` reports `AMD RYZEN AI MAX+ 395 w/ Radeon 8060S`, and `torch` runs on the GPU.

**2. A false low-memory report breaks vLLM's startup guard.**
vLLM refuses to start when `free_memory < total_memory * gpu_memory_utilization`. Under WSL/DXG the
ROCm runtime reports only **~16 GB "free"** of the 119.9 GB it claims total — but the memory is
really there: an allocate-and-fill test commits **~88 GB**. With the default 0.8 that becomes
`0.8 × 119.9 = 89 GB > 16 GB` → startup refused even though the allocation succeeds.

Fix: make `gpu_memory_utilization` overridable and set it low **only to satisfy the guard** — the KV
size is explicit (`--cache-gib 44`), so the cache does not shrink:

```python
# bundle/plugin-site/ornith_g256/launch.py
gpu_memory_utilization=float(os.environ.get('ORNITH_GPU_UTIL', '0.8'))
```
```bash
export ORNITH_GPU_UTIL=0.10   # 0.10 * 119.9 = 12 GB < 16 GB reported
```

Also: WSL's `.wslconfig` memory cap raised to 30 GB (the model is 24.5 GB on disk, 21.17 GiB resident).

### Result — full production profile

```
reserved 44.0 GiB memory for KV Cache
GPU KV cache size: 1,521,544 tokens
Maximum concurrency for 262,144 tokens per request: 5.80x
Model loading took 21.17 GiB memory
```

Measured **on this Windows/WSL2 host** (server-reported counters; cold, reduced-warmup):

**Cold prefill (single request):**

| Context | This Windows/WSL2 host | Ciru's native-Linux figure |
| ---: | ---: | ---: |
| 32K | 1,581 tok/s | 1,509 |
| 64K | **2,359 tok/s** | 1,287 |
| 128K | 1,691 tok/s | 983 |
| 200K | 1,736 tok/s | ~668 @256K |

**Decode (C1, greedy, thinking off):**

| Workload | This host | Ciru published |
| --- | ---: | ---: |
| Short coding (natural EOS) | 78.7 tok/s | 178 (their 10-task screen) |
| Coding, 1024 tok | 81.3 tok/s | — |
| Prose, 1024 tok | 40.2 tok/s | 49.9–63.3 |

**Concurrency (short coding burst):**

| Concurrency | Mean per-request | Aggregate |
| ---: | ---: | ---: |
| C1 | 78.7 tok/s | 77.6 tok/s |
| C2 | 45.3 | 83.7 |
| C4 | 57.9 | 190.0 |
| **C8** | 43.8 | **269.0 tok/s** |

### For comparison, same box, llama.cpp (Vulkan) At C1:

| Model / quant | prefill 8K | prefill 32K | prefill 64K | decode 32K |
| --- | ---: | ---: | ---: | ---: |
| Ornith ROCmFP4 | 1,452 | 1,045 | 712 | 85.0 |
| Ornith 23G-ICE | 1,490 | 1,070 | 725 | 74.0 |
| Ornith q4xl (UD-Q4_K_XL) | 1,429 | 1,075 | 725 | 75.9 |
| Qwen3.8-Flash-Next UD-IQ4_XS | 458 | 303 | 258 | 41.4 |

So Ciru's prefill at 64K is **~3× the fastest local llama.cpp Ornith quant** and **~9× Flash-Next**.
For agent workloads that read a big context every turn, that is the number that matters.

### Honest caveats

- **This is WSL2, not native Windows.** The model runs in the Linux VM and reaches the GPU over
  `/dev/dxg`. I am not claiming native Windows ROCm.
- **The 178 tok/s C1 figure is not reproduced** here (we see ~81 tok/s on 1024-token generations, and
  269 tok/s aggregate at C8 vs their 295). Their 178 is a 10-question HumanEval screen where answers
  stop naturally and TTFT is subtracted from short generations; longer generations have a declining
  tail. The **C8 aggregate and the prefill rates land essentially at parity with the native figures**.
- **Coding is the strong case; prose is ~half.** Ciru's own notes say the same (49.9–63.3 tok/s prose).
- **Thinking matters.** Use `enable_thinking: false` and the shipped chat template; a naive request
  without it goes through a reasoning pass first.
- The prefill numbers come from short-output requests; treat them as backend prefill rates, not
  sustained throughput.
- Correctness under load was not independently graded here (Ciru reports 60/60 base+extended health
  on their screen).

### Reproduce (WSL2)

1. `hf download jcbtc/Ornith1.5-Ciru-Halo-Agent-vllm-strix-halo --local-dir ./ciru-halo-agent`
2. `bash runtime/INSTALL-ORNITH-RUNTIME.sh "$PWD/installed-runtime"`
3. Set `CIRU_HOST_LIBRARY_PATH` (SDK libs + `/usr/lib/wsl/lib`) and `HSA_ENABLE_DXG_DETECTION=1`;
   make `gpu_memory_utilization` env-overridable; `export ORNITH_GPU_UTIL=0.10`.
4. `bash bundle/serve.sh --host 127.0.0.1 --port 8000`

Thanks to Ciru (`jcbtc`) for the build and to AMD for the hardware program — this is just getting
their work to run on the other side of the fence.

### What's next

Same setup, next model: **Qwen3.8 27B "Halogen"** — I will run it through the identical WSL2/DXG
stack and post a matched Windows-vs-native comparison (and it should need far less memory, so the
44 GiB KV profile should be easy).
