# Halogen official update check — 11 October 2026

Checked at 19:18:31 UTC; next scheduled source check is 21:18:31 UTC. This was a source-only check. No hardware, serving lifecycle, driver installation, models, or continuation state were changed.

The [official changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md) now adds 0.17.5 and 0.18.0 beyond the retained 0.17.4 baseline. 0.17.5 reports faster prefill and drafted decode with unchanged checkpoints and greedy output. 0.18.0 adds NPU speech transcription, named sessions, and cache fixes. These claims require local verification.

Anonymous authenticated GHCR metadata verified both tags with HTTP 200. No image layer was fetched:

| Tag | Immutable manifest digest | Image config creation time | OCI revision |
|---|---|---|---|
| 0.18.0 | `sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9` | `2026-10-11T05:32:02.604217078Z` | `c31448922f6e` |
| 0.17.5 | `sha256:df161433d825e901d91811fe28561bc3ef830a552bbb59c1aaf58f8fd4e9bc1d` | `2026-10-10T14:35:13.391383441Z` | `9699708c1765` |

These are build metadata times; an exact publication time was not established. The [README](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/README.md) identifies 0.18.0 as published and uses its pinned image tag. The GitHub Releases page has no releases. The browser's cached changelog history was too old to establish chronology.

The changelog does not identify HC6 or disclose its kernel changes. The 0.17.4 HC6 split is therefore suspended as the immediate candidate while the newer native engine is prepared. It is neither proven obsolete nor safe to transplant: its body, descriptor, dispatch mapping, and binary seals must be compared against the actual new engine before any later experiment.

The [AMD 395 driver listing](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) still lists recommended 26.8.1 and optional 26.9.2. [RyzenAI-SW](https://github.com/amd/RyzenAI-SW/releases) remains v1.8.0 / `73c0457`; [MLIR-AIE](https://github.com/Xilinx/mlir-aie/releases) remains v1.4.4 / `e5c705c`. No driver/toolchain update was identified.

The [Windows ML provider table](https://raw.githubusercontent.com/wiki/microsoft/WindowsML/Windows-ML-Execution-Provider-Releases.md) now yielded parseable MIGraphX and VitisAI versions; the old receipt had no extracted versions, so a change cannot be established. Planned October versions are not treated as released. [MIGraphX GenAI support](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers) remains explicitly unavailable there.

Reddit's [NPU agent workflow report](https://www.reddit.com/r/StrixHalo/comments/1x0wx70/the_npu_in_your_strix_halo_is_finally_doing_real/) was already assessed in `halogen-npu-reddit-retrieval-assessment-20261009.md`; its separate search/routing tasks do not establish a Flash token-rate gain. A [new Gufo report](https://www.reddit.com/r/StrixHalo/comments/1x25x4j/gufo_engine_seems_a_good_open_source_choice_vs/) uses a different setup and supplies no transferable controlled Halogen result. Neither reopens a closed local screen.

Full receipt, direct raw files, registry manifests, image configs, and the preserved initial sandbox socket-denial receipt are under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/updates-20261011-resume/`. The final update receipt SHA-256 is `f94e77711c25589cb8a59d0d4ebde9cee0b2289f18473a365740886a0ce1d9b4`.
