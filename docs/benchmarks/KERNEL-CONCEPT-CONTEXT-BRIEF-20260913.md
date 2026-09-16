# Context brief: faster-decode kernel concept for Qwen3.8-Flash-Next on Bosgame M5 (Windows/WSL)

Hand-off context for a **separate session**. This session's job is only to run Flash-Next well on
Windows. The follow-on job is to design a **faster decode kernel** (prefill is already good; `tok/s`
decode is the weak point) and compare kernel architectures.

---

## 1. Hardware and OS (fixed)

- **Bosgame M5** mini-PC: AMD Ryzen AI Max+ 395, Radeon 8060S iGPU, **gfx1151** (RDNA 3.5, wave32),
  128 GB LPDDR5X unified.
- Windows 11 + **WSL2 (Ubuntu 24.04)**. WSL sees `/dev/dxg` only, **no `/dev/kfd`**, no Vulkan in WSL.
- Firmware iGPU carve currently **32 GB** → Windows sees 95.6 GB; GPU device pool 81,564 MiB (Vulkan) /
  79.7 GiB (HIP).
- Memory rule (measured): GPU pool ≈ `64 GiB + ½·carve`; pinned memory comes from host RAM.
- WSL `.wslconfig` **must stay ≤ ~72 GB** — a 90 GB cap plus concurrent jobs hard-restarted the PC.

## 2. The model

**Qwen3.8-Flash-Next** — ~125–177B-param MoE (`qwen4exp`), ~6B active. Architecture, verified by
`.hgn` inspection: hybrid attention (Gated DeltaNet + full attn), **512-expert MoE + shared expert**,
hyper-connection adapters, and a per-layer embedding with a **2.5M-row n-gram table (26.8 GiB GGUF /
47.7 GiB `.hgn`)** that is paged from disk, not resident.

## 3. Engines / kernel architectures to compare

| Engine | What it is | Openness | Windows/WSL status (ours) |
| --- | --- | --- | --- |
| **llama.cpp mainline (HIP)** | generic GGML kernels | open | ✅ builds + runs over DXG |
| **pwilkin/llama.cpp `strix-halo`** | gfx1151 kernels: tiled Gated-DeltaNet, sparse lightning-indexer (QSA), HC fusions, bf16 WMMA dequant GEMM, lazy "direct" PLE reader | MIT | ✅ builds over DXG; kernels engage; **❌ no PM4 replay** |
| **Halogen (peonist-ai)** | closed C++/HIP, pins weights, own `.hgn` | ❌ closed | ❌ pin needs 68 GiB contiguous host RAM; WSL balloon fragmentation → `CreateContext c000000d` at every carve |
| **chlorine-server** | AGPL clean-room reimpl + HIP kernels for gfx1151 | open | scaffold ~1 t/s; useful as a kernel reference |
| **Ciru (vLLM/ROCm 10)** | vLLM with DFlash2 drafter, tuned for gfx1151 | wheels | ✅ runs in WSL; huge prefill, batch-N oriented |
| **LaurentZuijdwijk `vulkan/qwen4exp-rocmfpx`** | ROCmFP4 fp4 kernels | open | ⚠️ Vulkan branch; 200k+ ctx crashes reported |
| **agentionai ROCmFP4-FAST-imatrix** | fp4 quant for the above | open | ⚠️ fork-locked |
| **EngramHalo** | HIP fork with QSA + chunked Gated DeltaNet prefill | open | native-Linux-oriented |
| **myhacsint `b10685`** | Vulkan fork; used for the GGUF Windows path | open | ✅ 201 t/s prefill, 22 t/s decode, MTP 100% |

## 4. What we measured (all on this box, all real)

### Flash-Next
| Config | Prefill | Decode | Notes |
| --- | ---: | ---: | --- |
| Halogen `.hgn` `Pin::None` | 0.44 t/s | **0.32 t/s** | weights streamed from disk; unusable |
| Halogen `.hgn` pinned | — | — | ❌ WSL fragmentation at every carve (0.5/8/16/32 GB) |
| strix-halo fork, **stock** UD-IQ4_XS, 36k ctx (server) | **300.8 t/s** | 6.97 t/s | kernels engage: `FORK_GDN_TILE`, `QSA_SCORE_BOUNDS active`, `MMB_BLK16` |
| myhacsint Vulkan, UD-IQ4_XS + MTP, 55k/164k (server) | 201 / 105 t/s | 22.1 / 13.6 t/s | MTP 100% acceptance |
| strix-halo fork, **custom IQ4_NL quant** | **~1200 t/s** (author's native-Linux) | 26 t/s (author) | **download in progress, not yet reproduced on Windows** |

### Kernel A/B, fork vs mainline (llama-bench, same machine, no speculation)
| Model (arch) | Build | pp512 | pp4096 | tg128 |
| --- | --- | ---: | ---: | ---: |
| Qwen3.8-27B (`qwen35`) | fork | 204.6 | 252.4 | **12.0** |
| | mainline | 244.8 | 265.2 | 10.8 |
| Ornith 1.5 35B-A3B ICE (`qwen35moe`) | fork | 461.5 | 528.5 | 42.0 |
| | mainline | 505.8 | 514.7 | **46.3** |

**Reading: the fork is architecture-targeted.** It helps `qwen4exp` (Flash-Next) a lot, the 27B's decode
~11%, and is *behind* mainline on Ornith. Prefill is kernel-fusion-bound (fork wins); decode is
bandwidth/launch-bound (fork barely moves it on non-Flash-Next).

### Reference: other models on this box (llama.cpp HIP, WSL)
- Dense 27B Q4: 10.9–14.7 t/s decode (≈6–9× slower than MoE).
- MoE 35B-A3B: 63–99 t/s decode.
- Parallelism saturates: 2 streams ≈ 110 t/s aggregate; 4–8 ≈ 120–128 t/s.

## 5. The problem to solve: decode is slow

Diagnosis (to be validated/extended by the follow-on session):
1. **Dense is near bandwidth ceiling** — 27B Q4_K_M = 15.3 GB/token at 12 t/s ≈ **184 GB/s**, close to
   the LPDDR5X ceiling (~200–240 GB/s). Little headroom without fewer bytes/token (fp4, pruning).
2. **MoE has headroom** — Ornith ~2 GB active/token at 46 t/s ≈ 92 GB/s, only ~40% of ceiling →
   launch/dispatch bound, not bandwidth bound.
3. **No PM4-replay / retained graphs on WSL** — the author's custom ROCr+HIP runtime needs `/dev/kfd`.
   This is the single biggest known decode lever we currently forgo (their ~26 vs our ~12 t/s).
4. **Disk-backed PLE/ngram** — lazy reads can stall decode; prefetch/hot-row caching is unexplored.
5. **Batch-1 kernel launch overhead** — hundreds of launches/token; graphs/PM4 amortize it.

## 6. Candidate strategies (rank these, pick a concept)

- **A. Verify HIP/CUDA-graph capture on DXG.** We built with `-DGGML_HIP_GRAPHS=ON`; does it actually
  capture over the standard runtime? Cheapest test, potentially large decode win at batch-1.
- **B. Replicate PM4/ROCr command-buffer replay without `/dev/kfd`.** Check whether the standard
  `libamdhip64`/ROCr over DXG exposes any retained-graph path; else document it as native-Linux-only.
- **C. FP4 weights.** Halve bytes/token → ~2× decode headroom. Borrow aiter/ROCmFPX dequant kernels.
- **D. Fused MoE decode kernel.** One kernel: gate → top-k → gather → GEMV → activation → scatter, to cut
  launches and intermediate traffic (targets the MoE headroom in §5.2).
- **E. Speculative decoding.** MTP/DFlash2 is target-verified (quality-neutral). We measured 100%
  acceptance on the GGUF; verify decode gain on Flash-Next and tune depth/`-ub`.
- **F. PLE/ngram prefetch** into VRAM or a pinned host buffer; measure stall contribution.
- **G. KV quantization (Q8)** for long-context decode.
- **H. Own fork.** Build on `pwilkin/llama.cpp@strix-halo` (MIT, already builds here) and add C/D/A.

## 7. Assets on disk (this machine)

- Fork source+build: `/home/revn/strix-llama` (`build-hip/bin/llama-server`, `llama-bench`), commit `f5daaa3c`.
- Mainline HIP build: `/home/revn/llama.cpp/build-hip/bin/{llama-server,llama-bench}`.
- chlorine-server: `/home/revn/chlorine-server` (`.hgn` converter, HIP kernels, docs).
- Halogen engines: `/home/revn/halogen-re/halogen` (27B), `/home/revn/halogen-flash/bins/flash_serve`.
- Shims: `/home/revn/hipshim.so`, `hipshim2.so`, `hipshim3.so` (+ sources in the REV-N repo).
- ROCm 10 SDK (DXG): `~/ciru-runtime/venv/.../_rocm_sdk_*` (source `runtime-env.sh`).
- Models: `~/models/flash-next-strix` (ilintar IQ4_NL, downloading), `~/models/flash-next-unsloth`
  (UD-IQ4_XS, staged on ext4), `/mnt/c/AI/models/{halogen-flashnext,halogen-27b,qwen38-flash,Ornith-1.5-35B}`.
- All the founder's Reddit research + our measurements are in `C:\Projects\REV-N-ornith-eval-20260911\docs\benchmarks\`.

## 8. Hard constraints

- **Never start the REV:N product Cloud/FiveM; no paid API/overage; no pushes.** Repository work only.
- WSL memory cap ≤ 72 GB; **one heavy job at a time** (parallel jobs hard-restarted the PC).
- Models on `/mnt/c` are slow (9p): stage to WSL ext4 before benchmarking.
- `HSA_ENABLE_DXG_DETECTION=1` + the ROCm venv's `runtime-env.sh` are required for GPU access.
- Do not run `flash_serve` under `hipshim*.so` (it over-allocates and can wedge the host).

## 9. Deliverable the follow-on session should produce

1. **Kernel architecture comparison table** (pros/cons per engine for *this* hardware, Windows/WSL vs
   native Linux), grounded in the measured data above.
2. **A concrete "faster decode kernel" concept** for Flash-Next on gfx1151 under Windows/WSL: which
   strategies (from §6), expected gain, effort, risk, and a first experiment to run.
3. **Second-opinion input** from `codex exec -s read-only` (see the collaboration note below).
