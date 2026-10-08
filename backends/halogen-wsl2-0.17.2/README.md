# Halogen 0.17.2 WSL2 backend

This isolated backend contains the reviewed exact 0.17.2 adapter rebinding. The four CPU artifacts were compiled and pinned, and normal installation completed with exit code 0 and `completed: true` in the version-specific install manifest. See [source and artifact notes](portable-source-notes.md) for the exact hashes and evidence.

The pinned image is `ghcr.io/peonist-ai/halogen-flash-server@sha256:0c83ef1093520f0d5b5a00285e59e7ac6b85b1922917fc4a3df95ac5a2638cdd`, with runtime revision `8351ef2dc12d`. [Release pins](profiles/release.json) and the [source manifest](profiles/sources.json) seal this package. Static review and installation evidence are separate from the [fixed-depth-2 runtime comparison report](../../docs/benchmarks/halogen0172-fixed-depth2-20261008.md); they make no performance or global adapter runtime qualification claim. No NPU acceleration is claimed.

## Installation

Use an existing Ubuntu 24.04 WSL distribution, Docker image, GCC 13.3, Windows Python 3.12+, model/tokenizer files on native WSL ext4, and the pinned DXG library. The preflight checks the existing global WSL `memory=56GB` setting. The installer does not download models or change drivers or global WSL configuration; it extracts dependencies from a stopped container and compiles the four local CPU artifacts without starting a model.

From the repository root, activate the project Python environment so `python` resolves to it. The normal Windows PowerShell 5.1 wrapper command for this machine is:

```powershell
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -NoProfile -File .\backends\halogen-wsl2-0.17.2\Install.ps1 `
    -Distribution Ubuntu-24.04 -LinuxUser revn `
    -ModelDirectory /home/revn/halogen-models-native `
    -DxgLibrary /home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocdxg.so.1 `
    -NgramSource /mnt/c/AI/models/halogen-flashnext/qwen38-flash-next-w4b.hgn `
    -Checkpoint v2 -Install
```

Paths are machine-specific. Omit `-Install` for preflight only. An existing version-specific installation must be stopped and deliberately uninstalled before reinstalling. `Install.ps1` delegates to the same `portable.py install --install` path used by the completed installation receipt.

## Serving and comparison controls

V2 startup at context 262144 requires **35 GiB physical availability and 131 GiB commit headroom**. The independent runtime guard enforces **18/18 GiB**. These are admission thresholds, not reservations or evidence that startup succeeds at exactly the floor. W4b and bounded diagnostic budgets remain separate in [memory_budget.py](scripts/memory_budget.py).

The fixed comparison uses v2, context 262144, one slot, prefill chunk and arena 8192/8192, explicit MTP depth 2, PLD `3,3`, cache Off and thinking Off. Keep depth 2 explicit; omission permits the upstream adaptive policy. The normal managed launcher supports these controls. Refer to the separate runtime report for comparison outcomes and restoration evidence.
