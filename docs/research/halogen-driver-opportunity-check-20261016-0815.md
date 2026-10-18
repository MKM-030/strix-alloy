# Official and community opportunity check — 16 October 2026

Checked through **2026-10-16T08:24:13Z** against the retained15October17:06:10UTC snapshot. Next full check: **2026-10-16T10:24:13Z** (ROOT owns scheduling). This was read-only; the saved inventory hash still matches. It is historical, and this report does not identify the currently running server. ROOT separately owns the reported32K/9080 controller change.

No newer Halogen release was observed: the [changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md) and [quickstart](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/getting-started.md) still name0.18.5. The [public GHCR package page](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server) associates latest/0.18.5 with digest `94c9d76b6b938459e00805c61978808957703745fe573ca2d7f01e9157446b3d`. Direct registry and tags API reads failed; this metadata is not a local-image inspection.

The [Max395 driver page](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) still lists26.8.1 recommended and26.9.2 optional. The [26.9.2 notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html) retain GPU store32.0.32015.2008/NPU MCDM32.00.20102.3930, matching only the saved inventory. No driver change is admitted.

| Source | Observation since the baseline |
| --- | --- |
| [RyzenAI](https://github.com/amd/RyzenAI-SW/releases) | Stablev1.8.0/73c0457 unchanged. Installation-document reads failed, so driver-branch values remain retained evidence. |
| [MLIR-AIE](https://github.com/Xilinx/mlir-aie/releases) | New prereleasev1.4.5-alpha.1/cb6f2d1, displayed15October22:09; stablev1.4.4 unchanged. It is an IRON model-testing alpha, without a newly established kernel/interop mechanism. Exact publicationUTC was not revalidated. |
| [ROCm notes](https://rocm.docs.amd.com/en/latest/about/release-notes.html) and [matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html) |10.1.0, HIP7.16.0 and hipBLASLt1.4.1 unchanged; WSL support remains a technical preview with tooling limits. |
| [ROCm driver](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-ROCM-10-01.html) |26.10.41.05/store32.0.31041.5005 unchanged. Product list still names discrete Radeon families; Max395 package applicability remains unresolved. |
| [librocdxg](https://github.com/ROCm/librocdxg/releases) |v1.2.2/4955d12 unchanged. |
| [WindowsML](https://raw.githubusercontent.com/wiki/microsoft/WindowsML/Windows-ML-Execution-Provider-Releases.md) | Cached table still lists MIGraphX1.8.64.0 and VitisAI1.8.75.0; planned1.8.65.0/1.8.80.0 are not confirmed releases. The tool reports a5-day crawl age. |

The concrete new community delta is [rdna-boosts r65→r68](https://raw.githubusercontent.com/stew675/llama-cpp-rdna-boosts/main/release.json), tip`fc6dcad9f`. Its [worklog](https://raw.githubusercontent.com/stew675/llama-cpp-rdna-boosts/main/WORKLOG.md) describes queued input copies through pinned storage and a lazy dependency index for GDN gathers. Intermediate fixes address MoE duplicate handling and staging activation. These are author-documented ggml mechanisms on different hardware; no current Halogen seam, implementation audit or local gain was established. Oldr65 scheduler/output audits were not repeated.

A [newly resolved Reddit lead](https://www.reddit.com/r/StrixHalo/comments/1x67nso/qwen38_flashnext_prefill_on_strix_halo_gpu_xdna2/) points to [mikealanni/gufo's fork-enhancements documentation](https://raw.githubusercontent.com/mikealanni/gufo/fork-enhancements/README.md): selected projections use block-float8 NPU GEMMs with4096-token joins. The author discloses only23/30 matching long greedy completions. This is a Linux-XRT documentation lead, with no Windows/WSL bridge or frozen-target equivalence. Its publication after17:06UTC is not proved. [Hipfire](https://github.com/warpfront/hipfire/releases) remains0.4.2.1; its prior source audit was not repeated.

Eight bounded indexed searches also returned older posts and unrelated recipes. A [GB10 five-expert recipe](https://github.com/azampatti/Qwen3.8-Flash-Next-Int4-FAST) changes hardware/model and was excluded; an indexed PyTorch-NPU lead could not be resolved to primary implementation. Search coverage is not exhaustive.

Preserve current runtime ownership and installed stack. No install, pull, live retest, WSL/driver/power change, API call, continuation or server-state write occurred. Only newly observed mechanisms warrant separate source triage; neither community numbers nor the new alpha justify a hardware run.
