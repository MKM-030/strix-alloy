# Unified Windows inference: evidence, implementation and remaining gates

Reviewed 30 September 2026 against the local Strix Alloy publication checkout.
This report distinguishes external claims, code inspected, changes implemented, and
measurements actually completed. A successful build is not runtime qualification.

## Architecture decision

Use one stable authenticated endpoint and a Windows lifecycle controller, with isolated
engine adapters behind it. Halogen, GUFO and llama.cpp/Projfix are engines with different
weight layouts, allocators, KV/recurrent state and command-line contracts, not interchangeable
DLL kernels. Sharing their best individual kernels inside one forward pass would require
new integration and numerical validation. The current work shares the control and HTTP
interface, not model state or in-flight sessions. Only one large model is admitted at a time.

The managed Halogen adapter passes checkpoint/context/cache choices explicitly, preserves
the independent backend guard, and uses an owned Windows job. The native adapter requires
an operator-qualified profile and pinned executable. Unsupported backends fail closed.
The gateway supports incremental SSE forwarding, backpressure, cancellation, body/concurrency
limits, model-ID translation and authenticated readiness. Management is local-only.

## Source-by-source audit

All supplied URLs were attempted. The two unavailable Reddit pages below were not inferred
from their titles. Repository findings are supported by the linked source, not by assuming
that a Reddit headline's highest number transfers to this hardware configuration.

| Supplied discussion | Repository / evidence examined | Applicable lesson and boundary |
|---|---|---|
| [Windows Flash-Next attempt](https://www.reddit.com/r/StrixHalo/comments/1wqsv03/) | First-hand post and comments; no complete reproducible repository identified in the retrieved post | Match power, sampling, real prompts and occupied depth. Repetitive-copy MTP peaks are not ordinary chat throughput. |
| [Strix Llama 1180 t/s](https://www.reddit.com/r/StrixHalo/comments/1wqag3o/) | [Rulith Inference](https://github.com/rulith-dev/rulith-inference), renamed from Strix Llama; README, measurement guide, rejected ideas | Quant-specific expert kernels, sparse-attention paths, prefix reuse and per-pass MTP timing. Native 96 GiB carve results are not this 64 GiB/DXG configuration. |
| [Full-quality FLUX.2](https://www.reddit.com/r/StrixHalo/comments/1wsgaq2/) | [N5 Max homelab](https://github.com/Mensra/n5-max-homelab) | GPU ownership handoff and memory supervision transfer; Proxmox/image-generation throughput does not establish LLM decode speed. |
| [Vulkan versus ROCm](https://www.reddit.com/r/StrixHalo/comments/1wql1ru/) | Discussion and linked benchmark context | Backend choice is model/quant/build dependent, not a universal Vulkan or HIP win. Preserve compiler and loaded-DLL identity in every result. |
| [GUFO versus Halogen](https://www.reddit.com/r/StrixHalo/comments/1ws2un3/) | First-hand same-quant, sampled Python-task comparison; official engine benchmark methods | Compare the same weights and sampling, report acceptance and multiple task shapes. A 153-token prompt at 126K capacity is not a 126K occupied-context test. |
| [27B three serving profiles](https://www.reddit.com/r/StrixHalo/comments/1wt0fmd/) | [PaoAI strix-v4](https://github.com/guevae2/paoai-strix-engine/tree/strix-v4) | Verification packing and KV-row padding are specific kernel work. Separate chat/code/long profiles are useful; 27B/Mesa/DFlash flags cannot simply be pasted into Flash-Next/Halogen. |
| [Flow Z13 two-day measurements](https://www.reddit.com/r/FlowZ13/comments/1wpybxc/) | [Windows LLM bench](https://github.com/ihanesman/strix-halo-windows-llm-bench) | Per-model microbatch sweeps, real agent traces, per-request versus aggregate throughput, and one endpoint over different engines. Its Auto carve differs from this host. |
| [A better home for Qwen](https://www.reddit.com/r/StrixHalo/comments/1wpizbi/) | Retrieved discussion; no additional repository identity confirmed from that page | Treat it as a workload/packaging discussion, not an independently reproducible kernel benchmark. |
| [GUFO Windows testers](https://www.reddit.com/r/StrixHalo/comments/1wqix0w/) | [pixmaate Windows port](https://github.com/pixmaate/gufo), docs/WINDOWS.md | WDDM budget reporting, NTFS random-read behavior, explicit command display, model-header discovery, compiler-specific correctness checks. |
| [Owl naming discussion](https://www.reddit.com/r/StrixHalo/comments/1wsx3ed/) | Page retrieval failed | No implementation or performance conclusions attributed to inaccessible content. |
| [AMD iGPU performance](https://www.reddit.com/r/StrixHalo/comments/1wtl5wb/) | Reddit retrieval failed; AMD-authored Linux PerfOpt patch discussions reviewed separately | Linux IOMMU/AMDGPU change, not a Windows DXG or WSL environment toggle; no BIOS/IOMMU security changes applied. |
| [Halogen/GUFO flags](https://www.reddit.com/r/StrixHalo/comments/1wpos8f/) | Discussion plus official Halogen flag reference | Distinguish sampled from greedy decode, single-session from aggregate totals, cache hits from cold prefill; test one factor at a time. |

## Repository-specific changes worth adopting

**pixmaate and thomas9120 GUFO:** the native port implements overlapped cached random
reads for the n-gram table where mapped-file/direct-I/O interactions hurt NTFS throughput;
uses actual WDDM budget rather than an unreliable free-memory calculation; reduces copy-engine
handoffs and redundant rollback graph construction. Thomas adds packaging, GUI and newer
continuation/reasoning-cache fixes. The port's guide qualifies TheRock 10.0.0 and warns that
newer compilers can change fused-kernel rounding. Those are explicit compatibility boundaries,
not a reason to assume every new SDK is faster and equally correct.

**Local result:** Thomas commit `7e924c2d787aabf640db3c0f818cb824dc18ec8e` built with
TheRock 10.2 after removing HIP debug information (`-g0`, optimization retained). Thirty
operator runs tested Windows tuning on/off: 26 passed; attention preparation and projection
failed exactness in both modes. At 131069 positions, one fused query value differed from its
reference. Tests were not weakened. This build remains unqualified; no whole-model GUFO speed
or quality result is claimed. Compiler attribution is a hypothesis, not a demonstrated cause.

**Rulith:** use per-dispatch timing to locate work, then measure normal graph replay;
track draft acceptance alongside tokens/s; evaluate long-context numerics and output
length, not only short perplexity. Its rejected experiments are useful controls: fewer
graph nodes can be neutral, requantizing an already quantized trunk can lose quality,
and vocabulary pruning can change acceptance strongly across languages. None is promoted
solely because another author's headline shows a gain.

**PaoAI:** separate workload profiles and verify-packing suggest future kernel experiments,
but the cited changes target a dense 27B Vulkan model. Its experimental FA staging was
neutral and is not in its recommended profiles. This does not justify enabling analogous
flags in a different runtime. KV padding and quantized KV require separate quality and
occupied-depth tests before adoption.

**llama-swap:** an existing, mature alternative for a common front door. It can launch and
swap OpenAI/Anthropic-compatible backends and was inspected as an architectural reference.
The present controller was kept small to preserve this repository's independent Halogen
memory guard, exact source pins, process ownership and explicit cleanup. It is not claimed
to match llama-swap's model catalog, GUI or dynamic scheduling feature set.

## CPU, NPU, memory and SSD: maximize useful throughput, not utilization bars

CPU, iGPU and NPU share the machine's memory and package power. An idle CPU/NPU is not
independent extra DRAM bandwidth that can simply be added to a bandwidth-bound decode.
Moving layers or draft steps can add copies, synchronization and competing memory traffic.
Treat a split as a measured latency/quality experiment, not an objective of 100% utilization.

CPU work that fits the current pipeline includes tokenization, HTTP, checksum streaming,
lookup-row scheduling and asynchronous disk reads. The v2 uploader now retains one contiguous
device address while staging bounded 64 MiB chunks. This is not a claim that every byte is
inside dedicated VRAM. The full-file verifier now hashes in 8 MiB buffers and advises only
its consumed file ranges out of cache; it does not drop global caches or rewrite model data.

The SSD's free space is capacity, not IOPS or bandwidth. The 47.7 GiB lookup table is
already disk-backed, and model startup reads large files. Persisting conversation/prefix
snapshots can reduce repeated work, but turning hot weights into page-fault-driven SSD
loads is usually the wrong direction for decode. Store weights in native WSL Ext4 for
this Halogen path. For native Windows GUFO, benchmark its overlapped n-gram reader rather
than transplanting the WSL file-cache policy. Cold and warm page-cache runs must be named.

AMD Ryzen AI 1.8 supports Strix Halo and adds small-model workloads such as embeddings
and speech. Its ONNX Runtime GenAI/NPU paths require supported/compiled models. It does
not make these existing Flash-Next HIP kernels execute on the NPU automatically. An NPU
embedding or ASR side service is a plausible later experiment; no such offload is claimed
implemented or benchmarked here. Test combined latency and power before assuming it is free.

## Version policy and driver validation

The read-only inventory records exact upstream commits. On this review, Halogen 0.15.1
is pinned; Thomas GUFO is pinned at 7e924c2, while pixmaate had advanced to aeee89a.
The installed display driver is 32.0.31041.1004. AMD's newer 26.9.2 Optional notes list
32.0.32015.2008; the installed NPU driver 32.0.20102.3930 matches the NPU version listed
in that package. No display driver, BIOS, clock, IOMMU or WSL-memory setting was changed.
Driver installation is a separate A/B and rollback operation, not an automatic server-start
step. Keep the qualified binary/toolchain tuple while a newer candidate is tested.

The PerfOpt sources are Linux IOMMU/AMDGPU patches. A later September 28 revision removes
an earlier optional policy knob and enables it for supported identity-mode integrated GPUs.
This is another reason not to copy an old article's flag. It does not apply directly to
this Windows WDDM/DXG route. No attempt was made to disable DMA isolation to obtain a score.

## What was implemented versus what remains

Implemented: v2 integrity checks and bounded staging, checkpoint-specific RAM admission,
PP512/PP2048 reproducible comparisons, the managed Halogen gateway/controller, token-safe
logs, owned-process cleanup, and read-only upstream inventory. Actual results are in the
separate benchmark and lifecycle report; source-test passes are not inference benchmarks.

The Exact-cache trial preserved output identity but failed its reuse gate: repeated
8192-token prompts reported zero cache hits. Cache Off remains the default; this
experiment is retained as a failed optimization, not marketed as a speedup.

Remaining gates: repair or independently qualify the two GUFO numerical failures, then
run its full-model short/deep-context, sampled, cancellation and stop/restart tests. Qualify
a matching Projfix native profile. Add on-demand switching only after safe drain/unload
is proven for each engine. NPU offload, disk continuation-cache sweeps, alternative drivers,
MTP depth/vocabulary changes and cross-engine kernel fusion remain separate experiments.
No unmeasured improvement is represented as a throughput win.

## Primary references

- [Halogen 0.15.1 flags](https://github.com/peonist-ai/halogen-flash-server/blob/82c92af2289f6f1086ab8362b18669ccff36968b/docs/FLAGS.md)
- [Halogen release changes](https://github.com/peonist-ai/halogen-flash-server/blob/82c92af2289f6f1086ab8362b18669ccff36968b/CHANGELOG.md)
- [GUFO Windows memory and compiler notes](https://github.com/pixmaate/gufo/blob/windows-port/docs/WINDOWS.md)
- [Thomas Windows port](https://github.com/thomas9120/gufo/tree/7e924c2d787aabf640db3c0f818cb824dc18ec8e)
- [Rulith measurement pitfalls](https://github.com/rulith-dev/rulith-inference/blob/main/docs/measuring.md)
- [Rulith rejected experiments](https://github.com/rulith-dev/rulith-inference/blob/main/docs/dead-ends.md)
- [llama-swap architecture/configuration](https://github.com/mostlygeek/llama-swap)
- [AMD 26.9.2 official release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html)
- [AMD Ryzen AI 1.8 release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html)
- [AMD NPU LLM deployment overview](https://ryzenai.docs.amd.com/en/latest/llm/overview.html)
- [AMD-authored initial PerfOpt patch series](https://lore-kernel.gnuweeb.org/amd-gfx/20260908041207.38113-1-mario.limonciello%40amd.com/T/)
- [September 28 PerfOpt revision](https://lkml.iu.edu/2609.3/10980.html)

[Recorded GUFO operator results](gufo-qualification-20260930.json)
[Publication validation record](validation-20260930.md)
