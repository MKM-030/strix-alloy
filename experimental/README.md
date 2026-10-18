# Halogen 0.14.2 research controllers

This directory holds source-only integration experiments, **not** an installed
backend or a new Strix Alloy release. The native release ZIP does not include
Halogen. Start with the [backend status](../docs/user/backends.md) and the
[release-validation record](../docs/benchmarks/release-validation-20260929.md)
before interpreting any result.

`halogen0142/` contains the trace/smoke controller and bridge, entrypoint and
HIP-probe sources. `halogen0142_release/` adds the guarded release-candidate
lifecycle. `halogen0142_pp/` is the cold HTTP PP2048/PP8192 adapter, with a
local transport and calibration formula. `halogen0142_benchmark/` is older
deep-replay research, not part of the PP adapter's runtime dependency closure.

The controllers' default invocation is an **offline dry run**: it prints the
source/artifact seal and proposed bounded command. `--run` is a separate,
stage-specific action requiring independent review of that exact seal and
allocation. PP additionally requires a qualified release-smoke success marker.
Do not treat a printed command, offline tests or a model answer as a portable
installer or a supported persistent service.

The current code is bound to this research host and to external assets. It
requires the separately maintained [public WSL2 repository](https://github.com/MKM-030/strix-alloy-wsl2)
(including its packaging and startup-guard sources), a pinned Halogen 0.14.2
container image and patched engine, local bridge/private-HIP/probe binaries and
their source patches, a WSL2/Docker/DXG/AMD ROCm environment, and a separately
installed HGN checkpoint, overlay and tokenizer. The local smoke manifest hashes
these inputs but refers to absolute Windows and WSL paths, including a model
mount. **Weights, tokenizer data, generated binaries and container layers are
not included here.** Exact reproduction on a clean machine is neither promised
nor qualified; the [release-validation record](../docs/benchmarks/release-validation-20260929.md)
documents the evidence and remaining package limits. Review the external
engine, ROCm and model terms described in the WSL2 repository's
[third-party notices](https://github.com/MKM-030/strix-alloy-wsl2/blob/main/THIRD_PARTY_NOTICES.md)
before obtaining or distributing those assets; a checksum is not a license.
