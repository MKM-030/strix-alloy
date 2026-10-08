# Third-party components and attribution

The root MIT license covers this repository's original adaptation code and documentation, not independently obtained engines, drivers, models or their trademarks.

- **Peonist AI Halogen Flash Server:** separately downloaded official image; [EULA](https://github.com/peonist-ai/halogen-flash-server/blob/main/LICENSE.md) and [trademarks](https://github.com/peonist-ai/halogen-flash-server/blob/main/TRADEMARKS.md). No engine binary, extracted kernel or modified image is shipped. Upstream benchmark tools are invoked from the user's official image, not bundled as our code. Historical logs are benchmark outputs, not engine source. Compatibility references do not imply endorsement or support.
- **AMD ROCm / TheRock / ROCr DXG:** separately obtained from AMD; [ROCm](https://github.com/ROCm/ROCm), [TheRock](https://github.com/ROCm/TheRock). The qualified wheel carries the ROCr NCSA notice. Retain the original archive and its notices when extracting the allowlisted dependency. Neither archive nor binary is redistributed here. Hash verification identifies bytes, not a grant of different license rights.
- **Microsoft Windows / WSL:** installed separately under their terms. A read-only mount of the installed `libdxcore.so` does not redistribute it. [WSL](https://github.com/microsoft/WSL).
- **Qwen models:** obtain checkpoint, quality overlay and tokenizer from their official distribution and observe the artifacts' applicable terms. No weights are included. [Qwen](https://github.com/QwenLM).
- **Native sibling references:** [pwilkin/llama.cpp](https://github.com/pwilkin/llama.cpp/tree/strix-halo) and PROJFIX work underpin the separate native backend, not this project's engine.

The process-local preflight bridge is original interoperability glue, gated on an exact engine hash. It changes one live instruction's demand source without relicensing or redistributing the target. Review upstream terms before use. The project name is distinct from upstream product names.

## 0.16.2 packaging

The installer extracts the engine, upstream entrypoint and HIP headers from the
user-obtained exact official image into ignored local storage. The engine is not
modified on disk. A hash-gated transformer generates a local WSL entrypoint and
the original interoperability bridge is compiled for the pinned 0.16.2 engine.
Neither extracted engine/API code nor AMD headers/binaries are committed here.
The exact source commit and artifact hashes are recorded in profiles/release.json.
The retained 0.13.8 package has its own independent notices and qualification.

## Inactive 0.17.2 preparation

This successor contains original adapter source only. Its exact engine and site
bindings refer to separately obtained official 0.17.2 bytes; no engine, API code,
model, AMD header or driver binary is included in this source tree. The three
new CPU adapter builds are separate private outputs and are not live runtime
qualifications. Historical 0.16.2/0.17.0 attribution and evidence remain reference
material; the successor has its own manifest and unresolved runtime pins.
