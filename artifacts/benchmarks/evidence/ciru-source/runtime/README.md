# Ciru Halo Agent pinned runtime

Install from the release root using the instructions in [INSTALL.md](../INSTALL.md).

This directory supplies the exact vLLM and AITER wheels, their matching source archives, dependency lockfile, runtime environment setup, and installer used for Ornith1.5 Ciru Halo Agent. Stock vLLM is not a compatible substitute for this custom quantization path.

The installer creates a new isolated runtime and refuses to overwrite an existing one. It downloads pinned Python, PyTorch and ROCm dependencies. `INSTALL-ORNITH-RUNTIME.sh` supplies the bundle's expected runtime layout; `INSTALL-RUNTIME.sh` installs the pinned engine packages.

- vLLM: `0.1.0rc2.dev9+g9255fd9fb9.rocm100`, base `9255fd9fb9fedf4b29d574a8d8bb21d93892cc98` with included cache overlay notes.
- AITER: `0.1.0rc1`; source archive preserves its release modifications and Composable Kernel submodule contents.
- Python: 3.14.3; ROCm SDK 10.0.0; PyTorch `2.13.0+rocm10.0.0`.

Archive directories and upstream package identifiers retain their compatibility names. They do not name a different model. Licenses and preserved notices are included inside the source archives.
