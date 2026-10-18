# NPU memory fabric feasibility — 5 October 2026

**The NPU cannot be turned into additional GPU-addressable VRAM by an
algorithm.** Its private on-chip SRAM can reduce DDR traffic inside an NPU
workload. Published GPU/NPU sharing mechanisms share existing DDR allocations;
they do not expose that SRAM as a GPU memory bank or add system RAM. A useful
NPU layer would have to compute or compress useful results, preserve their
validity, and deliver them cheaply enough for the GPU consumer.

This is primary-source desk research for Ryzen AI Max+ 395 / Strix Halo on
Windows 11 with a WSL2 GPU engine. No hardware queries, provider calls,
inference, installation, server lifecycle change, or fabric experiment was
performed. The current GPU/NPU concurrency and ownership hold remains in force.

## Physical memory and lifetime

| Resource | Capacity / ownership | What it means for a cache |
|---|---|---|
| NPU memory tiles, L2 | Eight tiles, 512 KiB each: **4 MiB raw** | Software-managed local storage, reached through NPU streams/DMA |
| NPU compute-tile data memory, L1 | 32 tiles, 64 KiB each: **2 MiB raw** | Distributed storage also used by stacks, code data and workload buffers |
| Total above | **6 MiB raw data SRAM**, derived from topology and tile sizes | Neither a contiguous free allocation nor an exposed GPU heap |
| Host/NPU/GPU shared buffers | Existing system DDR pages | Sharing can avoid duplicate allocations or staging; it adds no physical capacity |

AMD's IRON device documentation explicitly assigns **Strix Halo** to `npu2`,
with eight columns, four compute rows, one memory row and one shim-DMA row.
The pinned compiler target model supplies the 64 KiB and 512 KiB sizes. These
are Strix Halo/NPU2 capacities, not an extrapolation from the larger Versal
development boards. [AMD device topology](https://xilinx.github.io/mlir-aie/dev/Devices/),
[pinned target model](https://github.com/Xilinx/mlir-aie/blob/b15f3508006988ea0252300a1feac447990ce6ec/include/aie/Dialect/AIE/IR/AIETargetModel.h#L833),
[core-memory allocation](https://xilinx.github.io/mlir-aie/dev/programming_guide/core_data_memory/).

The Linux driver architecture describes DMA between host DDR and NPU L2,
context-bound spatial partitions, dynamic repartitioning/time sharing, and
firmware reload after suspend. Its PCIe-visible identity does **not** mean
this integrated NPU uses a discrete card's off-chip PCIe data path: the
document describes a dedicated SoC fabric for host-memory traffic. The
listed SRAM BAR exposes mailbox ring buffers, not the tile memory pool.
Do not assume SRAM contents persist across context teardown, reconfiguration
or power events; a cache would need an explicit workload lifetime and
invalidation contract. This architecture is evidence about memory organization,
not a Windows buffer API specification. [Linux AMD NPU architecture](https://www.kernel.org/doc/html/next/accel/amdxdna/amdnpu.html).

No reviewed public API maps NPU tile SRAM into a GPU address space. The
GPU-facing mechanisms below map DDR pages. The conclusion that they provide
no SRAM-based VRAM expansion follows from those documented memory paths.
AMD describes Ryzen AI Max's graphics memory as a portion of its unified
system memory. [AMD Ryzen AI Max announcement](https://ir.amd.com/news-events/press-releases/detail/1232/amd-announces-expanded-consumer-and-commercial-ai-pc-portfolio-at-ces).

A software cache service could, in principle, keep a small working set in
an NPU workload and return hits through DDR. That inference is different
from direct GPU SRAM access: it pays the NPU request, DMA and completion
costs and needs a proven SRAM-residency contract. It is not a demonstrated
fast cache tier for this engine.

## Buffer contracts and platform boundaries

| Mechanism | Published contract | Applicability here |
|---|---|---|
| Windows Ryzen AI / VitisAI ORT | ONNX session, compiler-selected NPU subgraphs, CPU subgraphs and ordinary `run()` tensors | Supported Strix Halo processing; no documented generic HIP/DXG import contract in this interface |
| Windows native XRT / IRON | NPU2 native kernel dispatch through Windows NPU driver and Windows XRT SDK | Supported custom-kernel route; general XRT flags do not establish GPU peer access |
| Windows AMD super-resolution sample | Preallocated D3D I/O buffers supplied to the NPU library | Concrete Windows shared-DDR evidence; specialized library/sample, not a Halogen integration contract |
| Native Linux XRT + HIP | XRT host mapping registered with HIP; reverse direction uses pinned host pages and XRT user-pointer BO | Published experimental same-process implementation; not Windows/WSL sharing |
| Native Linux HSA + HIP | Shared allocation mapped to AIE and GPU; NPU can consume GPU allocation via exported DMA-BUF | Published experimental implementation requires Linux `amdxdna` and AIE-capable ROCR |
| Windows NPU + WSL2 GPU | Windows driver and guest `/dev/dxg` GPU path | No supported end-to-end NPU BO import and fence contract found in the reviewed sources |

Ryzen AI **1.8** explicitly includes Strix Halo under `STX`; Windows deployment
uses the NPU driver and VitisAI EP. The documented EP cache stores compiled
models and shortens session creation; it is not a GPU data cache. The native
IRON Windows guide describes Windows XRT/NPU dispatch separately.
[Ryzen AI 1.8 release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html),
[model deployment and cache](https://ryzenai.docs.amd.com/en/latest/modelrun.html),
[native Windows IRON](https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/).

XRT supports mapped host buffers, user-pointer buffers, directional `sync()`
and run completion. Its documentation now notes that Ryzen integrated-NPU
SVM does not require explicit host/device buffer transfers. **That does not
eliminate shim DMA between DDR and tile SRAM.** Nor does it establish peer
GPU ownership: XRT warns that buffer flags are device/host-specific. Its
generic DMA-BUF export discussion uses file descriptors and Unix IPC; it
does not specify a Windows NPU-to-WSL/DXG contract. A mapped pointer, exported
handle or `p2p` enum alone is insufficient. [XRT native buffer APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html).

AMD's published `shared.py` implements XRT-to-HIP sharing by
`hipHostRegisterMapped` plus `hipHostGetDevicePointer` on BO host pages.
It explains that importing an `amdxdna`-exported DMA-BUF into KFD/HIP fails,
so host registration avoids that import path. HIP-to-XRT uses
`hipHostMalloc` plus a user-pointer BO; HIP device allocations instead
use the HSA AIE DMA-BUF route. The current HIP loader searches Linux
`libamdhip64.so`, including `/proc/self/maps`; it supplies no native Windows
loader or cross-VM translation. These are implementation-specific findings,
not a claim that every conceivable Windows host-registration solution is
impossible. [Pinned shared-buffer implementation](https://github.com/amd/Triton-XDNA/blob/694d60d4f336952b9a8e7210ebd352086f8b6f44/amd_triton_npu/backend/shared.py#L207).

The HSA backend requires an `amdxdna` kernel device and a ROCR AIE agent;
IRON explicitly says the agent is **Linux-only**. Triton-XDNA requires an
AIE-capable nightly ROCR from **2026-07-16 or later**. A named Max+ 395
validation matrix is not supplied: Strix Halo's documented NPU2 membership
establishes architecture eligibility, not validation of this host. The
single in-order AIE queue requires serialized host dispatch, with completion
signals and system-scope acquire/release packet fences. GPU producer and
consumer ordering still needs explicit synchronization.
[Pinned Triton-XDNA README](https://github.com/amd/Triton-XDNA/blob/694d60d4f336952b9a8e7210ebd352086f8b6f44/README.md#launch-runtime-xrt-default-or-hsa),
[IRON HSA requirements and ordering](https://xilinx.github.io/mlir-aie/dev/programming_guide/hsa_runtime/),
[pinned Linux-only HSA discovery](https://github.com/Xilinx/mlir-aie/blob/b15f3508006988ea0252300a1feac447990ce6ec/python/utils/hostruntime/hsaruntime/discovery.py#L27).

WSL2 GPU access through `/dev/dxg` differs from native Linux GPU access.
The IRON WSL guide builds device code in WSL and runs Windows host code; it
does not supply Linux NPU passthrough or shared XRT BOs. No reviewed source
proves that a Windows XRT allocation can be consumed by Halogen's WSL HIP
GPU without staging. This remains **unestablished**, rather than a measured
failure or a hardware impossibility. [Microsoft WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq),
[IRON Windows/WSL workflow](https://xilinx.github.io/mlir-aie/dev/buildHostWin/).

## One bounded Windows lead and its break-even condition

The one concrete Windows lead is **reuse a preallocated D3D DDR I/O buffer
through AMD's NPU library**, avoiding a staging allocation/copy. AMD's
January 7, 2026 super-resolution article describes BOs referencing an
existing buffer, sub-BOs and DDR stride addressing. It publishes
`gaming_sr::OrtBuf` inputs/outputs backed by D3D resources and specifies
Windows 11 with AMD GPU/NPU drivers. The linked sample redirects to AMD
SharePoint sign-in, so this review could not inspect its allocator,
synchronization or library redistribution contract. It is a lead for a
native Windows processing interface, **not an admitted Halogen/WSL fabric**.
[AMD shared-D3D NPU example](https://www.amd.com/en/developer/resources/technical-articles/2026/super-res-acceleration-on-ryzen-ai-npu.html).

A cache that merely relays original DDR bytes cannot add capacity and incurs
additional reads/writes. A useful producer must save more GPU work or DDR
traffic than it adds. For a serialized substitution:

`GPU work avoided > producer execution + layout/preparation + transport + synchronization + cache maintenance`.

For overlapped work, the producer must stay ahead of the consumer and the
total engine request must improve after shared-memory contention. Reuse must
amortize preparation and mapping; buffers stay alive until every consumer
finishes, with explicit validity/versioning and producer-completion ordering.
No bandwidth or concurrency benefit is assumed here.

The [retained Halogen component result](halogen-useful-npu-decision-20261005.md)
is GPU **0.487170 ms** versus NPU session **1.850025 ms**. The latter is a
session timing, not isolated compute or a complete live-engine substitution.
Shared I/O alone cannot be claimed to recover that gap. This research
demonstrates possible shared-DDR mechanisms, **no additional GPU memory tier
and no measured prefill/decode gain**.

Source snapshots reviewed on 2026-10-05: Triton-XDNA
`694d60d4f336952b9a8e7210ebd352086f8b6f44` (2026-10-04), MLIR-AIE
`b15f3508006988ea0252300a1feac447990ce6ec` (2026-10-04), XRT master
`2bfd112944d30647ae66f350466791ad9e224786` (2026-09-30). The linked rolling
documentation may change; the source links above are pinned where available.
