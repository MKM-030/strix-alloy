# Halogen update check — 5 October 2026, 15:03 UTC

The bounded official check began at **15:03:00 UTC**, two seconds after its 15:02:58 due time. Official observations finished at **15:06:43 UTC**; the checkpoint was prepared at 15:07 UTC. The next check is due at **17:03:00 UTC**, two hours after this check began. Baseline: the original checkout's [13:02 checkpoint](C:/Projects/strix-alloy-clean/docs/research/halogen-update-checkpoint-20261005-1300.md), with last start `2026-10-05T13:02:58Z` and completed source/runtime receipt at `13:12:29Z`.

**No checked official revision or release changed. No genuinely actionable fresh NPU memory/fabric or Halogen embedding-precompute support was established.** This check performed public source reads only. It made no installation, provider, hardware, model/engine payload, inference, lifecycle, or pinned source change. The only new file is this report in the isolated worktree.

## Official Halogen

The official [main ref](https://api.github.com/repos/peonist-ai/halogen-flash-server/git/ref/heads/main) remains `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`. The [first ten tags](https://api.github.com/repos/peonist-ai/halogen-flash-server/tags?per_page=10) still start with `v0.16.2`, resolving to that commit. Its [annotated tag ref](https://api.github.com/repos/peonist-ai/halogen-flash-server/git/ref/tags/v0.16.2) retains object `71b5339a1dc74c26dc0952989e64aee4b06a6546`. The [release collection](https://api.github.com/repos/peonist-ai/halogen-flash-server/releases?per_page=10) is empty, and the [default-branch commit query since 13:02:58 UTC](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits?since=2026-10-05T13:02:58Z&per_page=20) is empty.

These successful primary GitHub GETs establish an unchanged committed tree, so the unchanged README/FLAGS/NPU deep audit was not repeated. No new documented ready-row consumer, main-model NPU draft route, supported GPU/NPU overlap, or FP11 fabric hold/readback contract follows from this check. This is a scoped branch/tag/release observation, not an exhaustive claim about issues, discussions, uninspected branches, registries, or unpublished interfaces. The web-rendered tags page failed; the bounded official REST tags GET succeeded.

## Official AMD GPU/NPU channels

The parallel AMD source check began at 15:03:01 and finished at 15:06:43 UTC. Its observed versions agree with the 13:02 checkpoint:

| Official channel | Current observation | Change |
|---|---|---|
|[Ryzen AI Max+ 395 graphics](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html)|26.9.2 WHQL Optional, Sep 29; 26.8.1 WHQL Recommended, Aug 20|None|
|[26.9.2 release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html)|Driver 26.20.15.02 / Store 32.0.32015.2008; alternate packaged 25.10.45.11 / Store 32.0.21045.11001; bundled NPU 32.00.20102.3930, May 7|None|
|[RyzenAI-SW releases](https://github.com/amd/RyzenAI-SW/releases)|Latest listed `v1.8.0`, commit `73c0457`, July 23|None|
|[Ryzen AI installation docs](https://ryzenai.docs.amd.com/en/latest/inst.html)|Software 1.8.0; minimum NPU 32.0.203.280; separate production NPU 32.0.203.376 with Strix Halo listed|None|
|[Ryzen AI release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html)|Latest Version 1.8; existing embeddinggemma-300m and large-model low-memory notes|None|
|[Windows ML EP release table](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases)|Current VitisAI MSIX 1.8.75.0 / EP 1605, upcoming 1.8.80.0; current MIGraphX MSIX 1.8.64.0 / EP 7.2.2609.19, upcoming 1.8.65.0|None|

The Windows ML table was observed at 15:04:06 UTC. Current and upcoming remain distinct; upcoming entries do not establish an available supported release. The separate production NPU package is distinct from the bundled graphics-package NPU row. Existing small-model embeddings and low-memory notes do not establish a newly supported consumer for the main model's projected embeddings. No package index, installed-state, Windows Update entitlement, driver installation, or device operation was performed. Exact publication/edit timing within the two-hour interval is not established from web crawl labels.

## Reddit leads and upstream deltas

The [Rulith inference commit query](https://api.github.com/repos/rulith-dev/rulith-inference/commits?since=2026-10-05T13:02:58Z&per_page=20), [Rulith llama.cpp branch query](https://api.github.com/repos/rulith-dev/llama.cpp/commits?sha=rulith&since=2026-10-05T13:02:58Z&per_page=20), and [GSQHalo branch query](https://api.github.com/repos/Aristo94/GSQHalo.cpp/commits?sha=gsqhalo&since=2026-10-05T13:02:58Z&per_page=20) are empty. [Rulith releases](https://api.github.com/repos/rulith-dev/rulith-inference/releases?per_page=5) still start with `v0.4.5`, published 10:26:41 / updated 10:27:23 UTC, before the window. Its model-name/API change remains unchanged. The [GSQHalo release collection](https://api.github.com/repos/Aristo94/GSQHalo.cpp/releases?per_page=5) remains empty. Previously considered SSD prefetch, kernel fusion, and profiling hypotheses were not repeated or counted as fresh improvements.

Bounded past-day keyword searches and the [StrixHalo NPU/Halogen search listing](https://www.reddit.com/r/StrixHalo/search.json?q=NPU%20OR%20Halogen&restrict_sr=1&sort=new&t=day&limit=5) served only the already known [12:36 UTC unified-memory discussion](https://www.reddit.com/r/StrixHalo/comments/1wy7ffo/doom_for_unified_memory_pc/) and the [previous day's local Halogen benchmark post](https://www.reddit.com/r/StrixHalo/comments/1wxiwad/halogen_0162_on_windowswsl2_qwen38flashnext_at/). The served unified-memory comment fragment at 13:04:01 UTC concerns engagement style and supplies no code, primary implementation, memory contract, or embedding-precompute method. Reddit assertions about hardware or performance are not adopted as verified facts.

Freshness is incomplete: the [new listing](https://www.reddit.com/r/StrixHalo/new.json?limit=10) still starts with the 03:53:06 UTC eGPU question, while search serves a 12:36 post. The comments JSON rendering is truncated, so complete comment coverage was not established. Older hardware-buying threads and generic NPU discussions returned by narrow searches supply no newly actionable implementation. This check does not assert that no newer relevant Reddit post or comment exists.

## Runtime boundary

At dispatch, root reported work to restore the original controller 4832/backend 29440 after original memory recovery failed, and reported that neither the candidate nor NPU had run. This update check did not probe runtime identity, memory, health, containers, or readiness and cannot provide a fresh restoration receipt. Root owns that separate recovery/verification work. The source result adds no admission for the ready-row candidate and no numerical parity, acceptance, or performance claim.
