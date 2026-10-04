# Halogen and driver checkpoint, 2026-10-04 17:30 UTC

Read-only online check began at **17:30:56 UTC**, compared with the retained
15:26:15 UTC record in
`server/.local/optimization9h-20261004/update-check-20261004-1525.json`.
No engine/provider was started, and no model, package, driver, firmware, BIOS,
voltage or global WSL setting was changed. The earlier record is preserved.

No newer qualified engine or driver update was found. The current installed
Windows ML NPU provider already matches Microsoft's current public version.
No checked primary source establishes a new MTP/full-head integration API or
an acceptance/speed improvement for this machine.

## Official versions checked

| Channel | Observed version/date | Result and source |
|---|---|---|
| Halogen tags/main | `v0.16.2`; commit `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`, 2026-10-03 04:29:22 UTC | Same as 15:26. Live GitHub API returned no main commits since 15:26:15 UTC. [Tags API](https://api.github.com/repos/peonist-ai/halogen-flash-server/tags?per_page=3), [commits API](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits?per_page=1), [changelog](https://github.com/peonist-ai/halogen-flash-server/blob/main/CHANGELOG.md). |
| AMD Ryzen AI Max+ 395 Windows GPU channel | Adrenalin **26.9.2 WHQL Optional**, released **2026-09-29**; Recommended channel remains 26.8.1, 2026-08-20 | Same public channel as earlier. [Processor downloads](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html). |
| Adrenalin package contents | GPU driver store `32.0.32015.2008`; NPU MCDM `32.00.20102.3930` | Matches the installed versions recorded at 15:26; no installed device census was repeated by this source agent. [26.9.2 release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html). |
| Ryzen AI Software | **1.8.0**, release notes last updated **2026-09-28**; separate NPU production branch still lists **32.0.203.376** for Strix Halo | No supersession or compatibility inference from comparing version-number shapes across driver branches. [Release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html), [installation](https://ryzenai.docs.amd.com/en/latest/inst.html). |
| Windows ML AMD NPU EP | Current **VitisAI MSIX 1.8.75.0**, EP **1605**, release **2026 9D**; upcoming 1.8.80.0 is listed for Insiders 9D / GA 10D | Current public version matches the existing sealed installed package in `halogen-qmoe-registration-diagnosis-20261004.md`. The upcoming row is a preview/planned release, not a new qualified installation. Wiki edited **2026-09-25**. [Microsoft provider release history](https://github.com/microsoft/WindowsML/wiki/Windows-ML-Execution-Provider-Releases#vitisai-amd). |
| AMD Windows ML package documentation | Download table through **2026.8D**; page updated **2026-09-29** | This direct-package channel differs from Microsoft's current Store/MSIX table; do not silently substitute it for the installed provider. [AMD Windows ML installation](https://ryzenai.docs.amd.com/projects/WinML/en/latest/installation.html). |

GitHub tags/commits were read directly with local PowerShell `Invoke-RestMethod`
after the web tool could not open the API URLs. Responses were small metadata
only: latest tags were 0.16.2, 0.16.1, 0.16.0; current main equaled 0.16.2;
the `since=2026-10-04T15:26:15Z` commits query returned zero entries.

AMD's Windows ML model-support page explicitly describes original FP32
Transformer graphs being compiled with automatic BF16 conversion, or A16W8
QDQ graphs. That is a useful explanation for why provider precision must be
measured; it does not prove native Halogen BF16-boundary parity or support for
its complete sparse MTP head. [AMD model support](https://ryzenai.docs.amd.com/projects/WinML/en/latest/model_support.html).

## Official v2 quantization wording

For the Reddit post, describe it as **Halogen's native v2 HGN checkpoint:
4.16 bits per weight on average for the 62.1-GiB checkpoint, with 4-bit experts
and other model weights, 6-bit mixing layers, and 8-bit dense draft-head
projections; the separate 47.7-GiB n-gram lookup file is FP8**. Those are the
published tensor-family descriptions, and the publisher says the per-tensor
quantization map is not public. The source is
[QUANT.md, “The v2 checkpoint (0.15 on)”](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/QUANT.md#the-v2-checkpoint-015-on),
also fetched directly as the small
[raw official file](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/QUANT.md).
There is no basis here for calling v2 `IQ4_XS`; that is a separate GGUF label.

## Reddit approaches checked

The [Z13 power/context comparison and newest comments](https://www.reddit.com/r/StrixHalo/comments/1ww407o/rog_flow_z13_2025_128gb_qwen38_flashnext/?sort=new)
still supply three practical leads: record the actual package-power envelope;
separate serial decode at depth from MTP acceptance; and examine short follow-up
prefill costs separately from long initial prompts. The maintainer suggests
`HALOGEN_PREFILL_KEEP_TRUNK`. These are research leads, not evidence of a new
gain on this machine; comments are about two days old and were not established
as newer than 15:26 UTC. Existing stock/control measurements remain authoritative.

The [maintainer's NPU announcement](https://www.reddit.com/r/StrixHalo/comments/1wvfrj0/halogenflashserver_0160_strix_halo_npu_now_serves/)
was rechecked against [official NPU documentation](https://github.com/peonist-ai/halogen-flash-server/blob/main/docs/NPU.md).
The published NPU features serve small classifiers, embeddings, reranking,
moderation and text generation beside the Flash model. They do not establish
replacement of the Flash MTP head. Upstream documents shared memory/power cost
and a native Linux fabric-clock requirement. That Linux requirement is not a
verified Windows/WSL control and was not applied here.

A same-day [Strix Alloy post](https://www.reddit.com/r/StrixHalo/comments/1wxiwad/halogen_0162_on_windowswsl2_qwen38flashnext_at/)
also appeared in search. It describes this project's own results, so it is not
independent evidence or a new optimization source. No checked Reddit item
establishes an independent new fix released after the previous check.

Keep pursuing the guarded arithmetic/provider/full-head work. No version change,
install, overclock or throughput claim is justified by this checkpoint alone.
