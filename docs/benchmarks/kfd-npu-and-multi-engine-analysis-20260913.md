# /dev/kfd, "both advantages", and multi-engine ideas — analysis (2026-09-13)

Founder questions: (1) why can't we access `/dev/kfd`; (2) can we leverage both Windows and Linux
advantages; (3) could two models under different kernels "harmonize" to be faster, e.g. one doing prefill
+ experts X and the other experts Y?

## 1. Why there is no `/dev/kfd` on this machine (verified)

Measured on this box:

```
uname -a  → 6.18.33.2-microsoft-standard-WSL2   (a real Linux kernel, Microsoft-built)
lsmod | grep amdgpu → nothing
/sys/class/kfd → missing
/dev/dxg → present                                  (crw-rw-rw-)
/usr/lib/wsl/lib → libd3d12.so, libd3d12core.so, libdxcore.so
PNP: AMD RYZEN AI MAX+ 395 w/ Radeon 8060S  (OK) ; NPU Compute Accelerator Device (OK)
```

**`/dev/kfd` is the compute interface of the `amdgpu` *kernel driver*.** It exists only where that Linux
driver owns the GPU. In WSL there is no `amdgpu` module at all: Microsoft's kernel ships `dxgkrnl`
instead, which bridges GPU calls to the **Windows WDDM driver** through `/dev/dxg`. ROCm-on-WSL works by
translating KFD calls into DXG calls via `librocdxg.so`.

**The hard constraint: one PCIe/SoC device can be owned by only one driver at a time.** The iGPU belongs
to Windows (WDDM). Therefore nothing inside WSL can present `/dev/kfd` — not a config toggle, not a
kernel rebuild. WSL is using **GPU paravirtualization (GPU-PV)**, which by design exposes D3D12/DXG, not
KFD/PM4.

### Options that would actually give `/dev/kfd`

| Option | Gives `/dev/kfd`? | Cost |
| --- | --- | --- |
| **Dual-boot native Linux** | ✅ full (amdgpu owns the GPU) | no Windows at the same time; reboot to switch |
| **Linux host + Windows VM (GPU-PV)** | ✅ on the host; Windows guest gets paravirt only | complex; AMD iGPU paravirt for Windows guests is weak |
| **WSL kernel with amdgpu** | ❌ impossible | GPU is owned by Windows |
| **Pass the iGPU through to a VM** | ❌ impractical | the iGPU is part of the APU, not a discrete card |

**Honest conclusion:** "Windows + Linux at once, both with full GPU access" is not achievable for the
*iGPU*. The real choice is **which OS owns the GPU**, or **use the NPU as the second compute engine**
(§2).

## 2. The genuinely additive second engine: the **NPU** (this is the real "both advantages")

This box has a real, separate compute device that is **not** the iGPU:

```
NPU Compute Accelerator Device  (PCI VEN_1022&DEV_17F0 = AMD XDNA2)  Status: OK
```

- The NPU is **separate silicon** from the RDNA3.5 iGPU and shares neither the 40 CUs nor (fully) the
  scheduling path. It is rated in the tens of TOPS (integer-focused) and draws ~20 W vs the GPU's ~80 W.
- A community pattern we already found in the Reddit research runs a **35B-A3B model on the NPU
  concurrently with a GPU model** at that lower power (FastFlowLM). That is the only route on this
  hardware to "two models at once" that adds throughput instead of splitting one GPU.
- **Current gap:** no runtime is installed — no XRT, no FastFlowLM, no AMD Ryzen AI SW stack
  (`C:\Program Files\AMD\NPU` etc. absent). So the NPU is *available hardware, not yet usable*.
- **Caveats:** integer-oriented (quantized models only, MTP not supported yet); needs the NPU-enabled
  IOMMU posture (conflicts with `amd_iommu=off`); young tooling. It is a **fit-for-purpose helper** (e.g.
  a small draft/summarizer), not a replacement for the big MoE.

## 3. Can two models under different kernels "harmonize" to be faster?

**Short answer: the pattern is right, the physics on ONE iGPU says no for two full models — but the
pattern is already used, and the NPU version is real.**

**Why two full models on one iGPU cannot add up.** There is exactly one GPU, one set of CUs, and one
LPDDR5X pool (~200–240 GB/s). Two models time-slice or space-split that one pool; they do not create a
second one. Measured on this box: **1 stream ≈ 85 t/s, 2 streams ≈ 110 t/s aggregate**, saturating at
~120–128 t/s for 4–8 streams. So concurrency buys ~+30% aggregate from better utilization, **not 2×** —
and per-stream latency gets worse, which is the wrong trade for REV:N's few-hundred-ms brain.

**The versions of "two models harmonizing" that DO work:**

| Pattern | What it is | Status here |
| --- | --- | --- |
| **Speculative decoding** | small **draft** model proposes, big model **verifies** — literally two models cooperating | ✅ **already in use** (MTP / DFlash2). 1.3–2×. This *is* the founder's idea, realized |
| **GPU + NPU** | second silicon runs a helper/draft concurrently | ⚠️ hardware present, no runtime yet |
| **GPU + CPU MoE offload** | keep some experts on CPU (`--n-cpu-moe`) | ✅ available, but a **fit** mechanism (slower than full GPU) |
| **Multi-GPU expert parallelism** | split experts across 2+ GPUs, all-reduce activations | ❌ needs a second discrete GPU |

### The specific "Model A = prefill + experts X, Model B = experts Y" idea

**On one iGPU this does not help, for three reasons:**
1. **A token routes across many experts** (top-8 of 512). Splitting the expert pool between two engines
   means *both* must be consulted for most tokens, so you add coordination (activation transfer,
   combine) rather than removing work.
2. **The dense/attention layers would be duplicated** in both models (or shared with a coordination
   layer), i.e. you pay 2× for the non-expert part.
3. **Total bytes read per token is unchanged** (still top-8 experts of the same size), so the memory
   system — the shared bottleneck — does the same work. The GPU is the limit, not the model layout.

**Where the idea IS correct:** on a **multi-device** system, expert-parallel placement (expert X on
device 1, expert Y on device 2) is a real technique (that is how vLLM does expert parallelism). On this
box, the only genuine "second device" is the **NPU** — so the closest viable version is "big model on
GPU, small helper/draft on NPU," not "experts split across two kernels on one GPU."

## 5. Can MTP / DFlash2 run on the NPU? (founder question)

**No — and it would not help even if it could.** Verified:

1. **They run on the GPU.** Our own launch line proves it:
   `-dev ROCm0 ... --spec-draft-device ROCm0 --spec-draft-ngl 99` — target *and* draft are both on
   the GPU, all layers offloaded. MTP is the Flash-Next drafter (the 2.6 GB shared-Q8_0 head);
   DFlash2 is the 27B's separate draft block. Both were placed on `ROCm0`.
2. **WSL cannot see the NPU at all.** `ls /dev/accel` → absent (no `/dev/dri` either); the NPU is a
   Windows-side device with no DXG/ROCm bridge. So under WSL this is not a config change, it is
   unavailable.
3. **llama.cpp has no XDNA2/NPU backend.** There is no `-dev NPU`. The NPU is reachable only through
   AMD's Ryzen AI SW / XRT / **FastFlowLM**, which are separate runtimes.
4. **Speculative decoding needs per-token lockstep.** The draft proposes, the target verifies, every
   step. Splitting them across two devices adds a round-trip (NPU → host → GPU) each token *and* a
   second runtime. The draft is already tiny (~2B active), so the GPU work you'd offload is small —
   the coordination cost would very likely exceed the benefit.
5. **FastFlowLM (the NPU runtime we found in the Reddit research) does not support MTP yet** — so even
   its own path has no speculative decoding.

### Where the NPU genuinely helps for REV:N

The NPU's value is a **decoupled helper that does not sit in the per-token critical path**, running
concurrently at ~20 W while the GPU keeps the big model:

| Candidate side-task | Why it fits the NPU |
| --- | --- |
| **STT / transcription** | streaming, chunked, not lockstep with the LLM; already a separate stage |
| **Embeddings / memory retrieval** | encoder-style, integer-friendly; REV:N needs vector search over world memory |
| **Intent classification / routing** | tiny classifier; offloads the brain's first decision |
| **Scene/world summarization** | batched, latency-tolerant, can run behind the conversation |

That is the real "use both engines" design on this hardware — **not** moving the draft head, but giving
the NPU a **parallel, decoupled job** so the GPU is free for the model.

**Prerequisite:** none of this is installed (no XRT / FastFlowLM / AMD Ryzen AI stack on this box), and
the NPU posture conflicts with `amd_iommu=off`. It is a separate evaluation, not a quick win.

## 6. Decisions this suggests

1. **For Halogen's full speed (PM4 + pinning): native Linux.** Either dual-boot, or accept that
   Halogen Flash-Next is a Linux-only engine on this hardware. The Windows path stays on the
   `strix-halo` llama.cpp fork.
2. **For "two engines add up": use the NPU**, not a second GPU model. Next step would be installing an
   XDNA2 runtime and measuring a small model there alongside the GPU model. This is a *separate*
   evaluation (needs the IOMMU/NPU posture and a runtime that does not exist here yet).
3. **Do not pursue expert-split-across-kernels on one iGPU** — it duplicates dense work and coordination
   while the shared memory system stays the bottleneck.
