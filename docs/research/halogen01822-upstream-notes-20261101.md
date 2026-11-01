# Halogen 0.18.22 and AMD upstream review

Checked UTC: **2026-11-01 15:54:49**. Source review only: **no GPU/NPU driver,
Ryzen AI SDK, firmware or BIOS update was installed by this review**. Installed
machine versions and local engine measurements must be recorded separately.

## Halogen release changes

The official container listing identifies **0.18.22** as latest, digest
`sha256:273714ccb64dabb7fac0418ee1b6dd83eb57d2fd44cf286eb68a7c694a27c203`.
Release commit: `adf76ff3c5e9a565401bedf3a984c95c43b7e05e`, 31 October 2026.
[Image versions](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server/versions),
[release commit](https://github.com/peonist-ai/halogen-flash-server/commit/adf76ff3c5e9a565401bedf3a984c95c43b7e05e).

| Version | Relevant upstream change | Implication for this project |
|---|---|---|
| 0.18.17 | Conversation keep isolation, tool-call parsing, short-request admission during metrics reads, advertised modalities | Correctness and API improvements; no claimed serial speed gain |
| 0.18.18 | Tool-search prompt-cache reuse, queued request handling, tool parser, official IQ4_NL GGUF loading | Better agent follow-up latency where applicable; serial speed unchanged |
| 0.18.19 | Small decode improvement; further parser/image/admission fixes | Manufacturer measures about 0.4–0.9% single-request and 2.6–3.5% three-request aggregate decode improvement |
| 0.18.20 | Several drafts per request inside a shared decoding round; image schema/strict-tool support | Concrete concurrency candidate; single-request speed unchanged against 0.18.19 |
| 0.18.21 | User-supplied LFM3-1.7B NPU generation; scheduling long NPU requests between generation steps | Separate NPU service; Flash engine unchanged |
| 0.18.22 | User-supplied d1-2B NPU decisions over text, pictures and video | Separate NPU service; Flash engine unchanged |

Flash checkpoints remain unchanged across these releases. These summaries come
from the [pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/adf76ff3c5e9a565401bedf3a984c95c43b7e05e/CHANGELOG.md).

## Speed evidence and next candidate

The manufacturer's paired v2 0.18.19/0.18.20 measurements report **84.81/101.64
total tok/s for two simultaneous greedy requests**, and **98.26/107.23 for three**.
Its ten-shape single-request benchmark reports 66.14/66.12; 8K cache-off prefill
reports 1,874/1,875 tok/s. These are manufacturer workloads on 128 GB machines,
not measurements of our natural 8K/16K prefixes. A universal single-request
66 tok/s guarantee, or a local acceptance improvement, does not follow.
[Upstream measurement conditions and tables](https://github.com/peonist-ai/halogen-flash-server/blob/adf76ff3c5e9a565401bedf3a984c95c43b7e05e/docs/performance.md).

The concrete next independent candidate is **two concurrent independent
requests**, subject to normal memory admission and with aggregate throughput
separated from each request's latency and acceptance. It is not two parallel
MTP heads for one answer. Serial frozen cohorts remain the regression control.

## Official GPU and NPU updates

| Source checked | Published/current source state | Relevance and qualification boundary |
|---|---|---|
| [AMD Ryzen AI Max+ 395 downloads](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) | Adrenalin **26.10.2 WHQL Optional**, 30 October; **26.10.1 WHQL Recommended**, 20 October | Available update; availability does not prove a Halogen speed gain |
| [Adrenalin 26.10.2 notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-10-2.html) | Lists GPU driver-store versions **32.0.32015.12012** and **32.0.21045.20006**, plus NPU MCDM **32.00.20102.4480**, dated 3 October | Notes describe gaming/display/install fixes; no measured Halogen or WSL throughput uplift is stated |
| [Ryzen AI release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html) | Live documentation identifies **1.9.0**, adding longer NPU LLM context, models and Qwen dynamic LoRA support | Additional model/compiler capabilities; no drop-in replacement for Halogen's closed Flash kernels or MTP verifier |
| [Ryzen AI Windows installation](https://ryzenai.docs.amd.com/en/latest/inst.html) | Identifies SDK **1.9.0** and NPU version string **32.0.201.448**, dated 3 October | This differs in formatting from the Adrenalin notes; preserve the source strings rather than inventing a normalized local version |
| [AMD/Xilinx XRT 2.25.0](https://github.com/Xilinx/XRT/releases/tag/2.25.0) | Distribution/upstreaming release, 18 August; the feed also has an [official 2026.1 tag](https://github.com/Xilinx/XRT/releases/tag/202610.2.23.244), 12 October | Different release streams; neither establishes Windows-to-WSL NPU sharing or a local performance gain |

### New firmware finding for simultaneous GPU/NPU work

AMD maintainer `harkgill-amd` updated the existing Data Fabric issue on
30 October: the earliest PMFW containing the narrowed fix is **10.100.8.0**.
The issue remains open. This is an OEM firmware investigation route, not a
driver-only fix or proof our current machine can run the combination safely.
[AMD maintainer's update](https://github.com/ROCm/TheRock/issues/8709#issuecomment-6481404880).

The reviewed [Halogen NPU requirements](https://github.com/peonist-ai/halogen-flash-server/blob/adf76ff3c5e9a565401bedf3a984c95c43b7e05e/docs/NPU.md)
still require native NPU device access, XRT 2.20 or newer and supported fabric
clock handling. They warn that Flash can slow while the NPU works because it
shares memory bandwidth and power. The reviewed public flags and NPU interfaces
do **not document a supported external Flash draft-proposal API**. Separate
NPU model generation is therefore not evidence of Flash MTP offload or a
measured NPU-on/off tok/s improvement. Existing negative component results
remain negative; no new NPU overlap test or BIOS change is justified solely by
these release notes.

The firmware lead warrants checking the machine's actual version and OEM
availability before proposing a separately authorized update. Local policy,
runtime reserve and stable online service remain in force.

## Follow-up source check, 18:10 UTC

The official package listing still identifies 0.18.22 with the same digest.
The newly noticed [HEAD commit d64a233](https://github.com/peonist-ai/halogen-flash-server/commit/d64a2330f3f48ff0a447f3b03bddbe389fded982),
dated 31 October 17:02:44 UTC, updates separate NPU timing documentation and website
files; it contains no new Flash engine change. The AMD, Ryzen AI, XRT and
firmware sources above remain unchanged. Bounded Reddit searches yielded older
posts without a fresh concrete mechanism; this is not an exhaustive freshness
claim. No update was installed. Private source metadata is retained under
`server/.local/halogen-update-20261101/primary01822/source-refresh-1805/`.
