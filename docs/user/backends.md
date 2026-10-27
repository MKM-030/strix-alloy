# Backends and release status

29 September 2026. This page describes the integration branch, not a newly
released all-in-one runtime.

This page preserves that historical release snapshot. Current measured profiles
and entry points are listed in the [main README](../../README.md); the latest
Halogen phase results are in the [26 October 8K/16K report](../benchmarks/halogen01816-natural-8k16k-20261026-evening.md).

## One project, distinct engines

The consolidation decision is **one Strix Alloy repository** with independently
selectable backends, not a new repository per kernel. This remains an integration
target until its adapters and packages pass qualification. Engine selection and model
selection are different things: **PROJFIX is a GGUF model profile used by the
native llama.cpp engine**, whereas Halogen and GUFO are separate engines.
CIRU Flash has its own model/runtime pairing. A shared launcher cannot make
their weights, kernels or command-line options interchangeable.

| Selection | Execution / weights | Available today |
|---|---|---|
| Native llama.cpp + PROJFIX | Windows HIP; IQ4_NL PROJFIX GGUF, optional shared MTP head | Published native `strix-alloy` v0.1.1 launcher; newer upstream build and matched PP measurements still need qualification |
| Halogen | WSL2; HGN checkpoint, overlay and tokenizer | Separate [`strix-alloy-wsl2`](https://github.com/MKM-030/strix-alloy-wsl2) package on 0.13.8; patched 0.14.2 candidate passed repaired 4K lifecycle and three-repeat cold PP2048/8192 on 29 September. Portable installer qualification remains open |
| GUFO | Native Windows; existing IQ4_XS GGUF and optional compatible shared MTP head | Measured historical research binaries; persistent-service entrypoint intentionally refuses until qualified. Upstream stable v0.1.1 plus the Windows port has now built on HIP, but has no new inference measurements or release qualification yet |
| CIRU Flash | CIRU's own Flash IU4 model/runtime | Upstream comparison only; matching local weights, launcher and measurements are missing. The installed Ornith Ciru Halo Agent is a different model |

Currently there is **no supported four-way `-Backend` switch**. The native
launcher is `app/launch-flash-next.ps1`; Halogen uses the separate repository's
`Start.ps1`; GUFO has `app/launch-gufo-flash-next.ps1`. The native release ZIP
does not contain the Halogen or GUFO runtimes.

The consolidation target is a thin selector in `strix-alloy`, separate
per-engine install/launch/status/stop adapters and explicit model profiles.
Existing commands and the WSL2 repository remain compatibility paths; there is
no repository rename or silent default/client-endpoint switch. Installation
must remain opt-in per engine, with weights external and no automatic large
downloads. Backend-specific qualifications must pass before their start
options become available.

The existing `strix-alloy-wsl2` repository stays available as the published
Halogen compatibility path while its installer and patches are integrated.
We are not renaming either repository or claiming that a shared launch flag
already packages all engines. The existing 27B workflow is preserved separately
from Flash-Next model profiles; engine updates do not automatically qualify it.

## Safe commands already present

Native published launcher, using a separately installed compatible runtime:

```powershell
.\app\launch-flash-next.ps1 -PrintOnly -ModelDir C:\AI\models\qwen38-flash\projfix
```

This prints the native command; it does not load a model. Follow the native
[installation guide](README.md) for its tested configuration. The historical
96 GiB carve recommendation is not an instruction to change the present
machine's 64 GiB carve for these release checks.

GUFO's current profile can be inspected with:

```powershell
.\app\launch-gufo-flash-next.ps1 -Command print-only -PythonExe C:\Path\To\Python312\python.exe
```

Its current persistent start is not qualified. See [GUFO usage](gufo-native.md)
and [setup](../../setup/GUFO.md); do not edit acceptance markers to enable it.
Halogen installation and bounded serving are documented in its own repository.
The 0.14.2 research scripts are not yet a portable installer.

## What the comparison can honestly say

Our closest historical common-input comparison is the frozen GUFO
mixed/repetitive workload, replayed on Halogen. Its token-count,
quantization and timing differences prevent an engine-only ranking; those
older research reports are not bundled in this documentation checkpoint.

Cold HTTP PP2048/PP8192, synthetic llama-bench, cached-prefix follow-ups and
repetitive prompt-lookup decode are different measurements. Old PROJFIX results
and CIRU publisher claims must not be inserted into a latest-build matched
table as though we ran them under identical conditions.

The [29 September integration validation record](../benchmarks/release-validation-20260929.md)
separates live Halogen lifecycle evidence from offline test results and the
remaining backend/package gaps. The 0.14.2 research controllers and their
machine-bound artifacts are not part of this documentation-only checkpoint.
Passing offline tests or a model load alone does not qualify a persistent
server, a clean-machine installation, or a new performance claim.
