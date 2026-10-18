# Halogen and driver opportunity check — 15 October 2026, late

**No compatible new driver update or low-cost Halogen compute adapter was established.** Keep the pinned 0.18.5 image, Fixed2 policy and existing driver/runtime/plan while collecting the prepared representative application results. A new community source delivery was found, but its immediate changes address llama.cpp integration correctness. Full observations, candidate costs and limitations are in the [JSON receipt](halogen-driver-opportunity-check-20261015-late.json), checked through 15:00:27 UTC.

This reviewer read public sources and saved local receipts only. Root supplied the fresh 14:56:52 UTC host inventory: Radeon 8060S driver`32.0.32015.2008` dated 28 September, NPU`32.0.20102.3930` dated 5 July, and active `REV:N Performance`. USB entries from the broad query were excluded. No hardware query, engine request, restart, driver installation, WSL/Docker command, credential read, loaded-source change or STATE write was performed here.

## Official release comparison

| Channel | Current observation | Change against 12 October source check |
|---|---|---|
| Max+395 GPU driver | Adrenalin 26.8.1 recommended; 26.9.2 optional, 29 September | None observed |
| Ryzen AI | 1.8.0; NPU installation page retains production`32.0.203.376` for StrixHalo | None observed |
| MLIR-AIE | 1.4.4 /`e5c705c`; Windowscp312 asset dated6October | None observed |
| ROCm Core | 10.1.0, release notes dated 5 October; HIP 7.16.0 and hipBLASLt 1.4.1 listed components | None observed |
| ROCDXG | 1.2.2 /`4955d12`, displayed 5 August | None observed |
| Halogen | Changelog still begins 0.18.5 | Updated since 12 October, already installed; no newer section than this morning |

The processor's [official download listing](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) and [26.9.2 package notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html) match root's GPU/NPU versions. The separate [Ryzen AI driver branch](https://ryzenai.docs.amd.com/en/latest/inst.html) does not establish supersession of the installed Adrenalin MCDM branch. [Ryzen AI releases](https://github.com/amd/RyzenAI-SW/releases), [MLIR-AIE releases](https://github.com/Xilinx/mlir-aie/releases).

The [ROCm matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html) lists 8060S/gfx1151 and driver 26.10.41.05, but the linked [driver package page](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-ROCM-10-01.html) names discrete Radeon families. This applicability mismatch remains unresolved. Its NPU package is the same`32.00.20102.3930`. The [Core SDK notes](https://rocm.docs.amd.com/en/latest/about/release-notes.html) retain technical-preview WSL support, bundled ROCDXG and automatic DXG detection; WSL profiling/debugging/KFD tooling remain unsupported. None is a new publication since the retained check. [ROCDXG releases](https://github.com/ROCm/librocdxg/releases).

The [Windows ML table](https://raw.githubusercontent.com/wiki/microsoft/WindowsML/Windows-ML-Execution-Provider-Releases.md), cached five days, still calls MIGraphX 1.8.65.0 and VitisAI 1.8.80.0 upcoming. A planned October entry is not treated as a released compatible runtime. The live container's pinned libraries were not replaced.

## Concrete configuration screen

`HIP_FORCE_DEV_KERNARG=1` already appears in the extracted 0.18.5 image configuration. AMD [documents](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/env_variables.html) it as device-memory kernel arguments, with2–3microseconds possible savings on some kernels. This benefit is already requested; toggling it is not a new optimization.

Halogen's [documented adaptation](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md) remains `32,0.35,64`; it disables drafting temporarily after low-acceptance windows. Aggregate acceptance cannot establish those windows or fallback. The completed natural 16K ledger supplies no new reason to repeat an adaptation-off screen. The same page retains the shipped tuned GEMM plan. The [earlier custom-plan comparison](../benchmarks/halogen0162-matmul-20261004.md) was slower and changed output; 0.18.5 explicitly refuses its unqualified private receipts. Retuning needs a new version-bound plan and quality result, and is not recommended without new shape/runtime evidence.

## Reddit leads and fresh primary source

The recent indexed [RDNA3.5 post](https://www.reddit.com/r/StrixHalo/comments/1x3s2t9/strixllama_new_branch_prompt_processing_2154_over/) is the 12 October lead already [assessed locally](strix-llama-rdna35-speed-assessment-20261012.md). Its attention/GDN/quantized-matmul paths depend on ggml tensor formats, dimensions, masks and rollback rules. No new current Halogen argument/layout seam was established. The latest asf0 branch commit was not independently resolved in this pass. Other returned posts offer anecdotal rates, socket reports or the already-assessed NPU routing workflow; none adds controlled local Flash speed evidence.

A useful new source delta is [rdna-boosts release.json](https://raw.githubusercontent.com/stew675/llama-cpp-rdna-boosts/main/release.json):`v12-097cf33d9-r64`, canonical patched tip`5eeff4da53a34a8f9f1b7cde40938a5a1df19920`. The [dated worklog](https://raw.githubusercontent.com/stew675/llama-cpp-rdna-boosts/main/WORKLOG.md) records r62 upload-stream ordering and r64 staging-ring ownership, segmented-write and image/MTP fixes. These teach precise buffer/fence lifetime requirements. They belong to ggml Meta/HIP loader and graph contracts; transplanting them into Halogen requires a proven native seam. Low-cost source comparison is useful; deployment is high-cost and unqualified. README still says r62, so the release manifest and worklog govern this observation.

Strict-tool grammar drafting remains a supported 0.18.5 opportunity only when a real client uses supported strict tools. Artificially adding tools to an ordinary ServiceNow prompt changes the task. The [completed MTP bracket](../benchmarks/halogen0185-natural16k-mtp-20261015.md) already supports retaining Fixed2 on that workload; it does not close every coding workload. No direct GPU-to-NPU memory capability, new acceptance guarantee or transferable community speed percentage follows from this research.

Browser freshness is limited: no late registry revalidation, exhaustive Reddit inventory or exact UTC publication time for the community delivery was obtained. Negative observations mean no applicable update was found in these checked channels, not that every possible upstream development was excluded.
