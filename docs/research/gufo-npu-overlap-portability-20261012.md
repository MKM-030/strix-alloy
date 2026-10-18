# Gufo NPU overlap portability and the supplied GPU lead — 12 October 2026

**Gufo provides a new bulk-prefill scheduling lead, but its native-Linux GPU/NPU path is not presently transferable to this Windows-NPU / WSL2-DXG Halogen deployment. The supplied Reddit post is a different, GPU-only llama.cpp branch. Its source is a plausible alternative-engine candidate; its reported percentages do not establish a Halogen gain.**

This was bounded desk research: repository reports and remote primary source were read. No hardware/provider call, process inspection or change, WSL/container command, build, installation, inference, driver, clock or power change occurred. Only this memo was written. No local `AGENTS.md` was found at the project root, in the scoped descendant search, or at the checked ancestors `C:/` and `C:/Projects/`. No pinned GPU/NPU source files were downloaded into the workspace; source was inspected through the GitHub connector.

## Distinguish the two leads

The supplied shortlink resolves to [asf0's GPU-only post](https://www.reddit.com/r/StrixHalo/comments/1x3s2t9/strixllama_new_branch_prompt_processing_2154_over/), linking [`asf0/strix-llama.cpp`, `rdna35-perf`](https://github.com/asf0/strix-llama.cpp/tree/rdna35-perf). The inspected branch head is [`44d574a8c6ee3f4c29138255c0c19b01613d0200`](https://github.com/asf0/strix-llama.cpp/commit/44d574a8c6ee3f4c29138255c0c19b01613d0200), committed 12 October 2026 at 01:35:07 UTC.

The separately discovered [Gufo NPU post](https://www.reddit.com/r/StrixHalo/comments/1x3gtdh/qwen38_flashnext_prefill_past_1800_toks_on_strix/) links [`mikealanni/gufo`, `fork-enhancements`](https://github.com/mikealanni/gufo). Its inspected head is [`afe7adee5b4acec5af6be73fd3f8169059bf9b8f`](https://github.com/mikealanni/gufo/commit/afe7adee5b4acec5af6be73fd3f8169059bf9b8f), committed 12 October 2026 at 01:30:45 UTC. They should not be described as the same optimization or evidence.

## What Gufo actually adds

The author's [pinned README](https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/README.md) reports 16,384-token prefill rising from 1,698 to 1,821 tok/s, about 7.24%, on a 128 GB Linux Ryzen AI Max+ 395 system using UD-IQ4_XS, 8,192-token prefill chunks, a held GPU fabric clock and NPU performance mode. This is author-reported measurement, not local reproduction. Thirty long greedy prompts reportedly generated the same output; this does not establish identical logits, tensor words or arbitrary workload quality.

The mechanism is **partial bulk matrix offload with a delayed dependency wait**. Selected linear-attention `z` rows, attention query/gate rows, and shared-expert gate/up projections are submitted before their first consumer while the GPU performs independent work. The shipped NPU design has fixed `M=4096, K=2560, N=1024` geometry. Larger prefill chunks use these slices. It is a different mechanism from replacing a synchronous count-one E/H projection with an NPU session.

The [pinned host interface](https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/npu_gemm.hpp#L12) and [implementation](https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/npu_gemm.cpp#L557) show:

- One persistent XRT hardware context and kernel, with instruction and weight buffer lifetimes retained across calls. Weights are finalized once; this is DDR/BO persistence, not all weights permanently resident in tile SRAM.
- HIP pinned mapped host pages, a GPU device pointer for those pages, and an XRT user-pointer BO importing the same host allocation. Normal mode avoids CPU staging copies. `GUFO_NPU_ISOLATE` uses private XRT pages and CPU copies instead.
- HIP stream host callbacks enqueue work to a worker; a later callback waits for completion. XRT launches overlap intervening GPU work. The implementation bounds outstanding runs, retains timed-out resources and marks failed results invalid.

This is useful source-level evidence for a real overlap schedule and reused buffers. Neither asynchronous dispatch nor persistent BOs is itself a new hardware feature. The valuable new element is the engine-specific dependency placement, BF8 packing/kernel and shared-page implementation.

## Windows and WSL contracts

| Question | Primary-source finding | Consequence for this deployment |
| --- | --- | --- |
| Can Windows submit custom NPU work? | AMD's [native Windows IRON guide](https://xilinx.github.io/mlir-aie/dev/buildHostWinNative/) documents the Windows NPU driver, XRT SDK, native host programs and Python JIT execution. [Ryzen AI 1.8 release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html) explicitly include Strix Halo under STX. | A native Windows custom-kernel route exists. Exact Gufo XCLBIN, BF8 design, API version and numerical behavior remain unqualified here. |
| Can submission be asynchronous and buffers reused? | [XRT native APIs](https://xilinx.github.io/XRT/master/html/xrt_native_apis.html#executing-the-kernel) say kernel invocation returns after submission; `wait()` blocks for completion and run objects can be started again. BO mappings and reusable user-pointer buffers are documented. | Windows need not be limited to synchronous ORT sessions. This does not prove useful GPU overlap or Gufo's exact runtime behavior on the installed driver. |
| Does an integrated NPU require duplicate host/device DDR buffers? | The same XRT document notes Ryzen integrated-NPU SVM can avoid explicit host/device transfers, while flag support remains host/device-specific. | Persistent DDR buffers are plausible; a `host_only` or `p2p` flag does not prove Windows-to-WSL sharing or remove DDR-to-tile DMA. |
| Does the IRON WSL guide expose a Linux NPU device? | Its [Windows/WSL workflow](https://xilinx.github.io/mlir-aie/dev/buildHostWin/) builds device code in WSL and builds/runs native Windows host code against the Windows XRT DLL. | A workflow launched from WSL is not Linux `amdxdna` passthrough or one shared Linux HIP/XRT process. |
| Is Windows GPU/NPU shared DDR possible? | AMD's [super-resolution example](https://www.amd.com/en/developer/resources/technical-articles/2026/super-res-acceleration-on-ryzen-ai-npu.html) supplies preallocated D3D resources as NPU I/O and describes sub-BOs/DDR stride addressing. | Concrete Windows sharing exists in that specialized library. It does not supply this Halogen/DXG allocation, import, fence or lifetime contract. |
| Do generic external-memory APIs close the VM boundary? | [HIP external interop](https://rocmdocs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/external_interop.html) documents native Windows handles or Linux file descriptors and external semaphore ordering, using HIP/Vulkan. | No inspected contract connects a Windows XRT NPU BO to Halogen's WSL HIP allocation and completion fence. Native-platform interop must not be assumed to cross the VM. |

The retained [Windows-to-WSL handoff](halogen-npu-wsl-handoff-20261007.md) demonstrates correct staged component transport, not shared BOs or production overlap. Its v3 complete diagnostic mean was 6.134 ms for one 5,120-byte BF16 row; this cannot be extrapolated to bulk prefill without measuring the real output shape and complete consumer path.

No inspected source supplies an additional GPU-addressable NPU SRAM heap. Sharing these buffers uses existing system DDR. See the [retained topology and memory-path audit](halogen-npu-memory-fabric-20261005.md) for the 6 MiB raw distributed NPU data-SRAM calculation and its ownership limits.

## The fabric condition is still decisive

Gufo's [NPU documentation](https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/docs/NPU.md) warns that GPU fabric transitions during NPU work can hard-hang the system. Its [clock helper](https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/tools/npu/fabric-clock.sh) sets Linux AMDGPU `power_dpm_force_performance_level=manual` and selects the top `pp_dpm_fclk` entry, then checks exactly one selected top state. It also requires NPU balanced/performance mode and avoiding runtime suspend. These are the author's requirements, not a Windows control contract or proof of a universal hardware failure.

AMD's current [experimental AMD SMI WSL documentation](https://rocm.docs.amd.com/projects/amdsmi/en/develop/how-to/amdsmi-wsl-mode.html) states that WSL lacks the native AMDGPU DRM/sysfs interfaces and reaches the GPU through WDDM/DXG; fabric features are unavailable. [Windows XRT-SMI](https://ryzenai.docs.amd.com/en/main/xrt_smi.html#xrt-smi-configure) controls NPU performance policy and reports NPU mode/power. It does not document a GPU FCLK hold or held-top-state readback. NPU performance, Windows power mode and the highest observed GPU clock are different evidence.

The existing [Windows fabric support audit](halogen-windows-fabric-support-20261005.md) already closes the inspected native/WSL routes. This lead introduces no supported FP11/395 Windows FCLK hold/readback/release interface. Repeating generic diagnostics would not supply the missing contract. GPU/NPU overlap remains unqualified.

## What would change the NPU decision

The retained [paired-projection result](halogen-useful-npu-decision-20261005.md) is GPU host 0.487170 ms versus NPU session 1.850025 ms before the bridge. That rejects the tested synchronous placement. It neither measures nor disproves a fixed-shape BF8 bulk kernel hidden behind substantial independent GPU work.

A transferable candidate would need all of the following concrete evidence:

1. Supported Windows fabric/coexistence semantics for this host and driver, including the required observation, hold and release behavior; or an authoritative supported design showing the requirement does not apply to the candidate.
2. A real generation-bound Halogen input-ready and first-consumer boundary for the selected bulk projection, with the dependency wait and GPU work removed identified.
3. An end-to-end allocation/import/fence/lifetime contract across Windows NPU and WSL GPU, or a measured complete staged route with sufficient margin.
4. Matching target arithmetic/quality for the actual HGN weights and layouts. BF8 output text equality on Gufo's quantization does not qualify unchanged Halogen prompt state.
5. A complete 64 GB resident-memory budget and matched engine measurement. Gufo documents about 3 GiB prefill scratch at 8,192 tokens and 9 GiB at 16,384, before independently accounting for packed offload weights and other engine memory; a 128 GB run does not establish fit here.

The relevant inequality is `max(0, P-L) + H + J + Q < G`: complete producer/packing cost `P`, real independent lead `L`, handoff `H`, ownership/validation `J`, target slowdown from contention `Q`, and GPU critical-path work actually removed `G`. The NPU's raw GEMM throughput and a large causal interval do not alone satisfy it. No new hardware test or live integration follows from this desk review.

## Actual supplied GPU post: portability disposition

The [author's post](https://www.reddit.com/r/StrixHalo/comments/1x3s2t9/strixllama_new_branch_prompt_processing_2154_over/) reports `llama-bench` results on a 128 GB Radeon 8060S system for Qwen3.6 35B-A3B, Qwen3.8 27B and Qwen3.5 2B, with Q8_0 weights, Q8_0 KV and FlashAttention. Its 21–54% versus Vulkan and 8–174% versus its stock ROCm are author-reported relative measurements at specified occupied KV depths. They are not comparisons to Halogen, the current Flash-Next 125B quantization, cold 128k ingestion or this 64 GB Windows/WSL host. The quality table's 98.5–99.7% same-top-token rates versus stock ROCm explicitly do not establish output equality; small KL/PPL changes also remain.

The primary [FlashAttention commit](https://github.com/asf0/strix-llama.cpp/commit/0a77f438d36991e6535ec6453be2ff32458eeed4) adds RDNA3.5-specific tiling, mask classification, quantized-KV preparation, and split/combine dispatch. [GEMM changes](https://github.com/asf0/strix-llama.cpp/commit/fc94088eef1ab2e54bf4fd891aa048fdeefbc707), [grouped verify matvec](https://github.com/asf0/strix-llama.cpp/commit/5e9c68c229aef823eda5aa271641691d718035d6), [GDN scheduling/fusions](https://github.com/asf0/strix-llama.cpp/commit/4f5fab79d941354a2f5c156eb64d4d4b9848de76) and [HIP graph default](https://github.com/asf0/strix-llama.cpp/commit/67287f9ee2a65cf6dc4b4d336e6cc7457ce05da3) integrate with ggml's graph, tensor types and runtime. Some GEMM changes alter intermediate precision; some GDN/FA changes alter summation order. They cannot be admitted as exact Halogen replacements from the public quality summaries.

**Blackbox Halogen integration:** these are implementation patterns, not flags available in Halogen. A kernel transplant needs its real tensor geometry/strides, packing, accumulation, scratch, mask/state ordering, launch ABI and complete downstream consumer contract. Grouped verify matvec needs actual expert/slot grouping and verifier layouts; GDN/residual fusion needs graph/liveness and rollback semantics. The ggml HIP-graph setting does not control Halogen. Without such bindings there is no reviewable direct transplant; changing a global HIP launch policy would not implement these source changes.

**Alternative engine:** technically plausible for the GPU path. The [pinned fork README](https://github.com/asf0/strix-llama.cpp/blob/44d574a8c6ee3f4c29138255c0c19b01613d0200/README.md) supports HIP builds targeting `gfx1151`; AMD's [ROCDXG WSL guide](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/wsl/howto_wsl.html) documents Strix Halo GPU support. This avoids the NPU fabric/interop issue. However Halogen's current native core is HGN, whereas llama.cpp takes GGUF. Existing HGN assets cannot simply be loaded by this fork; an already available suitable GGUF is a separate model/quantization candidate, or conversion must be qualified. The [prior Gufo source audit](gufo-upstream-review-20261002.md) likewise found no HGN loader. The fork README also retains a gfx1151 batched asynchronous-correctness warning and `HIP_LAUNCH_BLOCKING=1` workaround; installed-stack correctness must be assessed before claiming performance transfer.

Disposition: preserve the running engine. Treat the GPU branch as a pinned source candidate for a later isolated, memory-qualified alternative-engine comparison using a supported existing GGUF and matched workload. Treat Gufo's NPU schedule as a separately discovered research lead with unresolved platform contracts. Neither lead currently warrants a Halogen speed forecast, repeated closed NPU screens, or live substitution.
