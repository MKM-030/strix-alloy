# Halogen and driver checkpoint, nominal 2026-10-04 19:36 UTC

Actual read-only online check: **19:38:06–19:42:03 UTC**. Compared with
`halogen-update-checkpoint-20261004-1730.md`, whose check began at 17:30:56 UTC.
No engine/provider, benchmark, hardware probe, install, model/asset read, BIOS,
voltage or global WSL change was performed. Only this note and its small source
receipt were written.

**No new official engine or driver release was found.** Two external source
repositories provide concrete leads newly recorded here, but their commits
predate 17:30; they are not new upstream Halogen releases or qualified gains.

## Live official sources

| Channel | Current public observation | Change since 17:30 |
|---|---|---|
| Halogen tags/main | `v0.16.2`, main `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`, commit 2026-10-03 04:29:22 UTC | None. Direct [tags metadata](https://api.github.com/repos/peonist-ai/halogen-flash-server/tags?per_page=3) and [main metadata](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits?per_page=1) rechecked at 19:38:50 UTC. [Commits since 17:30:56](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits?since=2026-10-04T17%3A30%3A56Z&per_page=10) returned `[]`; [updated issues](https://api.github.com/repos/peonist-ai/halogen-flash-server/issues?since=2026-10-04T17%3A30%3A56Z&state=all&sort=updated&direction=desc&per_page=10) also returned no entries at 19:39:40. |
| AMD Ryzen AI Max+ 395 GPU channel | Adrenalin **26.9.2 WHQL Optional**, 2026-09-29; Recommended remains **26.8.1**, 2026-08-20 | None. [Processor downloads](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html). |
| Adrenalin package | GPU store **32.0.32015.2008**; NPU MCDM **32.00.20102.3930**, NPU date 2026-05-07 | None. [26.9.2 release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html). No installed-device census was repeated. |
| Ryzen AI Software | **1.8.0**, notes updated 2026-09-28; separate production NPU driver branch **32.0.203.376** includes Strix Halo | None. [Release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html), [installation](https://ryzenai.docs.amd.com/en/latest/inst.html). Different branch version shapes do not establish compatibility or supersession. |
| Windows ML VitisAI | Current MSIX **1.8.75.0**, EP **1605**, release **2026 9D**; upcoming **1.8.80.0**, Insiders 9D / planned GA 10D | None. The upcoming row remains preview/planned, explicitly not guaranteed. [Microsoft release history](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases#vitisai-amd), edited 2026-09-25. |
| AMD direct Windows ML package channel | Download table still ends at **2026.8D** | None. [Installation page](https://ryzenai.docs.amd.com/projects/WinML/en/latest/installation.html), updated 2026-09-29; this table is a separate channel from the Microsoft MSIX history. |

The web tool opened the official documentation but failed on the GitHub API URLs.
Local PowerShell `Invoke-RestMethod` read only the small public metadata responses,
without credentials. The native response count for the empty commits list was
confirmed as zero, avoiding PowerShell's nested-array wrapper count ambiguity.

The [current Halogen changelog](https://github.com/peonist-ai/halogen-flash-server/blob/main/CHANGELOG.md)
still begins with 0.16.2 and its small-model NPU/cache changes. No later release
or public Flash MTP/full-head integration contract was found.
[Official NPU setup](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/NPU.md)
still describes small models beside Flash, shared memory/power costs, and Linux
fabric-clock controls. Those controls were not applied or inferred valid for
Windows/WSL. [AMD model support](https://ryzenai.docs.amd.com/projects/WinML/en/latest/model_support.html)
still allows FP32 Transformer graphs compiled to BF16, or A16W8 QDQ; neither
description establishes parity with Halogen's native boundaries or complete head.

## Reddit leads and source checks

The [Z13 discussion sorted by new](https://www.reddit.com/r/StrixHalo/comments/1ww407o/rog_flow_z13_2025_128gb_qwen38_flashnext/?sort=new)
was opened again. Its maintainer `HALOGEN_PREFILL_KEEP_TRUNK` suggestion and
discussion of short-turn costs, power, quant differences and acceptance at depth
are older than this interval. No fresh independently measured fix was established.
The [Strix Alloy post and comments](https://www.reddit.com/r/StrixHalo/comments/1wxiwad/halogen_0162_on_windowswsl2_qwen38flashnext_at/?sort=new)
describe this project's own work, including experimental NPU/JEV/Laya ideas;
they are not independent acceleration evidence.

Two other discussions led to source inspection. Their Reddit relative-age labels
and crawl timestamps disagree, so no assertion that they were published after
17:30 is made. GitHub commit timestamps were checked instead.

1. [Vulkan agent-loop discussion](https://www.reddit.com/r/StrixHalo/comments/1wusyi0/qwen38flashnext_125b_on_one_strix_halo_vulkan/)
   links [AIdevsmartdata/strixhalo-verified](https://github.com/AIdevsmartdata/strixhalo-verified).
   Its current main is `4d89ea681c64fa17995c80b4935c846d44f56565`, dated
   **2026-10-01 07:56:46 UTC**. These opportunities are source-confirmed:
   - [Patch 0054](https://raw.githubusercontent.com/AIdevsmartdata/strixhalo-verified/main/runtime/patches/0054-strixhalo-verified-production-runtime-of-30-09-2026-.patch)
     introduces CPU streaming loads for mapped Vulkan readbacks, a grammar
     single-token check before full-vocabulary fallback, sequence-start MTP
     carrier reset, and rejection of drafted tokens beyond end-of-generation.
   - [Patch 0056](https://raw.githubusercontent.com/AIdevsmartdata/strixhalo-verified/main/runtime/patches/0056-fixes-from-our-review-of-the-30-09-runtime.patch)
     adds an `MFENCE` and **disables streaming loads under `_WIN32`**. A Linux
     WSL build is not that Windows target, but DXG mapping behavior still needs
     proof. Opaque HIP device pointers must never be CPU-dereferenced to copy
     this idea; only an explicitly valid host mapping could qualify.
   - [Patch 0057](https://raw.githubusercontent.com/AIdevsmartdata/strixhalo-verified/main/runtime/patches/0057-context-keep-the-scheduler-reservation-across-reques.patch)
     retains scheduler reservations across matching sampler chains. This is an
     agent-turn/TTFT lead, not a cold long-prompt prefill or steady decode result.
   - [Patch 0053](https://raw.githubusercontent.com/AIdevsmartdata/strixhalo-verified/main/runtime/patches/0053-qwen4exp-hyper-connection-injection-scale-2-sigmoid-.patch)
     removes a duplicated hyperconnection scale from that fork. It supports
     checking arithmetic against reference logits; it does not identify the
     same bug in native Halogen.
   - [Patch 0055](https://raw.githubusercontent.com/AIdevsmartdata/strixhalo-verified/main/runtime/patches/0055-server-adaptive-MTP-draft-length-by-reasoning-phase-.patch)
     caps draft length outside the reasoning block, off by default. The
     [author's changelog](https://github.com/AIdevsmartdata/strixhalo-verified/blob/main/CHANGELOG.md)
     reports workload-dependent gains and code regressions, so this remains a
     tuning hypothesis rather than a universal acceptance improvement.
2. [BALANCED-2.1 discussion](https://www.reddit.com/r/StrixHalo/comments/1wrc4ti/qwen38flashnext_balanced21_78_gb_one_box_full/)
   links the [PaoAI ROCm engine](https://github.com/guevae2/paoai-qwen38fn-rocm-engine).
   Its [three-line fix](https://github.com/guevae2/paoai-qwen38fn-rocm-engine/commit/b8fe9e80d5b33a30415d6756a694029bc8c28738)
   is dated **2026-09-25 01:12:05 UTC**. In `ggml_cuda_should_use_mmvf`,
   RDNA3.5 keeps the mat-vector route through eight columns instead of sending
   thin F16 MTP verification to hipBLAS. The author reports a faster verification
   pass; this is not an equal percentage gain in total decode. Native Halogen's
   Q8 projections and original dispatch contract are different. It is primarily
   a lead for the project's llama.cpp-derived backends, not a drop-in Halogen
   patch or NPU route.

No downloaded models, imported patches, installed versions or qualified
performance/acceptance changes result from this checkpoint. The direct action
supported here is to retain these exact source leads for bottleneck-directed
work while continuing the existing guarded native arithmetic/full-head work.
