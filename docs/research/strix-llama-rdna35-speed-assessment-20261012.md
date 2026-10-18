# RDNA3.5 speed lead from the supplied Reddit link — 12 October 2026

The supplied [share link](https://www.reddit.com/r/StrixHalo/s/IIvnOdsNoL) was resolved by the in-app browser to [strix-llama new branch: prompt processing +21–54% over Vulkan and up to 2.7× over stock ROCm at 128k](https://www.reddit.com/r/StrixHalo/comments/1x3s2t9/strixllama_new_branch_prompt_processing_2154_over/). This is a GPU kernel lead. The separately discovered Gufo NPU post is **not** this link's target.

The linked [asf0/strix-llama.cpp rdna35-perf branch](https://github.com/asf0/strix-llama.cpp/tree/rdna35-perf) was inspected at `44d574a8c6ee3f4c29138255c0c19b01613d0200`, dated 2026-10-12T01:35:07Z, ten commits above `6aa81b88e14aa753c1c7e1a9ff27c9d50fd3c673`. Independent source workers assessed kernel eligibility and Windows/WSL portability. This assessment contains no local engine-rate measurement or implementation claim.

## What the published numbers mean

The post reports llama-bench results for Qwen3.6 35B-A3B, Qwen3.8 27B and Qwen3.5 2B, with Q8_0 weights and q8_0 KV, flash attention enabled. Its prompt tests add 2,048 or 4,096 tokens at an existing KV-cache depth of 0–128K. That differs from our natural whole-prefix 16K/128K/260K Flash-Next workloads and native HGN checkpoint. A depth of 128K is not a measured cold 128K prefix.

Author-reported prompt throughput improves 21–54% relative to Vulkan, with the largest relative gain against stock ROCm at deep context. Generation is near Vulkan, rather than 2.7× faster: for the dense 27B, the 128K row is 6.7 tok/s versus Vulkan 6.8 and stock ROCm 5.2. These figures are not projections for Halogen.

The title's “same outputs” is stronger than the tabulated quality evidence. The post reports 99.7% same top token versus stock ROCm for the dense 27B and similar perplexity, not universal token identity. This does not establish exact output parity or improved MTP acceptance on our request. No local acceptance result follows.

## Mechanisms worth retaining

| Priority | Source mechanism | Potential contribution | Applicability limit |
|---|---|---|---|
| 1 | RDNA3.5 Flash Attention with specialized tiling and split/combine scheduling | Long-context Prefill; small verifier batches where eligible | Attention tensor/KV formats, masks, dimensions and dispatch must match. Halogen may already optimize this path; its savings are unmeasured. |
| 2 | Keep target features on the GPU for DFlash | Remove host transfer and idle time from draft preparation | Applies to a compatible DFlash context/backend, not automatically to Halogen native MTP or a Windows NPU sidecar. |
| 3 | Fuse Gated DeltaNet normalization/SiLU, decode operations and residual reductions; grouped expert matvec for verification | Reduce launches and intermediate memory traffic in Prefill/Decode | Requires the engine's graph, rollback semantics and layouts. Greater acceptance is not implied. |
| 4 | Tune quantized Prefill GEMMs and long-row Decode matvec; compare graph execution overhead | Better work per dispatch on gfx1151 | Q8_0/llama.cpp tuning is not a direct configuration for HGN/Halogen. Disable-graph advice is backend-specific. |

The [Flash Attention implementation](https://github.com/asf0/strix-llama.cpp/blob/44d574a8c6ee3f4c29138255c0c19b01613d0200/ggml/src/ggml-cuda/fattn-rdna35.cu) limits eligible head dimensions and tensor formats, rejects selected-key/max-bias cases, and requires aligned KV lengths. Automatic dispatch targets wide Prefill and selected deeper-context cases; single-token F16 has a deliberate fallback. Blindly replacing all attention kernels would ignore those conditions.

The [device feature commit](https://github.com/asf0/strix-llama.cpp/commit/0f9ea70) reports removing about 105 ms of GPU idle per 4,096-token chunk and Prefill 2,350→2,620 tok/s on its workload. Its source uses the shared target/draft context condition, GPU row gathers and event-protected feature lifetime. These are author-reported results, not our measurements. This is more useful to our DFlash work than another serial host-copy consumer.

The [Gated DeltaNet Prefill change](https://github.com/asf0/strix-llama.cpp/commit/087fab3) retains only final recurrent state for wide Qwen35/Qwen35MoE Prefill. The implementation explicitly disallows partial rollback after that path and keeps the necessary history for short verification. Any adaptation must preserve this distinction. The newest decode-fusion commit itself reports no meaningful DFlash improvement; a fusion alone is not evidence of useful speed.

## What can be done in this project

These kernels are integrated into ggml/llama.cpp. Their flags do not configure the closed-source Halogen 0.18.1 binary, and the existing LD_PRELOAD bridge handles WSL memory registration/placement rather than supplying a general replacement for its compute graph.

The useful next source work is a narrow compatibility comparison: native attention layouts/dispatch and whether our DFlash path can retain target features on the GPU without host round trips. Pursue a kernel adaptation only after identifying that concrete native seam or an engine-supported extension. A separate HIP llama.cpp comparison would require compatible existing GGUF assets and its own source/quality qualification; the current HGN asset is not a GGUF input. Do not download another large model or swap the public server merely to copy these benchmark percentages.

The branch is GPU-only and provides no direct NPU mechanism. A separate [Gufo asynchronous Prefill source audit](gufo-async-prefill-source-audit-20261012.md) retains an independent NPU lead: persistent bulk GEMM with deferred waits. Its Linux fabric prerequisites and Windows/WSL buffer/fence integration remain unqualified; prior slow per-token consumers remain disabled.

No server restart, model request, driver/clock/power change or GPU/NPU experiment was made for this link assessment. Halogen 0.18.1's completed installation is separate from runtime qualification. No new Prefill, Decode or acceptance value is published.
