# GUFO native Windows: qualified build toolchain

This integration pins the compiler/runtime combination that passes the original
Flash-Next numerical tests. It does not patch the kernel equations or relax assertions.

- Source: `thomas9120/gufo` at `7e924c2d787aabf640db3c0f818cb824dc18ec8e`.
- Build SDK: **TheRock 10.0.0 / AMD clang 23**, not the incompatible 10.2 build.
- Tested display driver: **32.0.32015.2008**. This is independent of the build SDK;
  no display-driver downgrade is needed. Other engines may keep their own SDKs.
- Model tests: existing Unsloth UD-IQ4_XS Flash-Next and shared Q8_0 MTP sidecar.
  Operator correctness and serving consistency are not independent model-quality certification.

[Resolution, controlled comparisons and measurements](../../docs/integration/gufo-toolchain-resolution-20260930.md)
records the exact scope. The older 10.2 failures remain historical evidence.

## Build prerequisites

Use Windows, PowerShell 7, Python 3.12+, CMake, Ninja and Visual Studio C++ Build Tools.
Clone the upstream repository and check out the pinned revision into a separate directory.
Use its pinned `vcpkg.json` to install the required x64-windows dependencies. This wrapper
reuses a classic `VcpkgDirectory/installed/x64-windows` dependency tree; it does not update
packages during an A/B test or silently reuse a different compiler's build directory.

Obtain the official SDK archive from:

```text
https://stable.repo.amd.com/rocm/core/tarball/therock-dist-windows-gfx1151-10.0.0.tar.gz
SHA256: 1293927b06b3b8d4bd7e0265823fb998bc9e0d83c68f33dcfa5d32663b30ce38
```

Verify that checksum before extracting to its own directory. Do not overwrite your
10.2 SDK. [Upstream Windows setup](https://github.com/thomas9120/gufo/blob/7e924c2d787aabf640db3c0f818cb824dc18ec8e/docs/WINDOWS.md)
describes the prerequisite tools and model files.

## Build, test and register

The following paths are examples; select your actual source/SDK/dependency locations.
Stop existing inference before building or running GPU tests. The build wrapper refuses
an active process from its destination and a mismatched compiler or runtime DLL.

```powershell
$Gufo = 'C:\Projects\gufo'
$Sdk = 'C:\AI\sdk\therock1151-10.0.0'
$Vcpkg = 'C:\Projects\vcpkg'
$Build = Join-Path $Gufo 'build\gpu-test-100'
$Proof = '.\backends\gufo-windows\.local\qualification'

.\backends\gufo-windows\Build.ps1 `
  -SourceDirectory $Gufo -SdkDirectory $Sdk -VcpkgDirectory $Vcpkg

python .\backends\gufo-windows\qualify_operators.py `
  --sdk $Sdk --source $Gufo --build $Build --output $Proof
```

Use a new output directory for each qualification. Both tuning modes must pass all
15 original tests. Original test hashes, compiler bytes and app-local runtime hashes
are checked; a passing result is not inferred merely from a version string.
The native runtime directory is **local-use only**: Visual Studio's OpenMP DLL may
come from `debug_nonredist`. Do not redistribute this directory without a separate
runtime/license audit. This repository distributes source and sanitized evidence only.

After selecting your existing target GGUF, matching shared MTP sidecar and a strong
API-token file, explicitly register the local experimental profile:

```powershell
$Model = 'C:\AI\models\Flash-Next\model-00001-of-00003.gguf'
$Draft = 'C:\AI\models\Flash-Next\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$Token = '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt'
python .\backends\gufo-windows\register_profile.py `
  --sdk $Sdk --source $Gufo --build $Build --model $Model --mtp $Draft `
  --token-file $Token --qualification "$Proof\qualification.json" --context 262144 --register

.\server\Start.ps1 -Backend GUFO -ContextSize 262144
```

Registration checks the matching operator receipt and binary/runtime hashes. It does
not claim independent quality certification for arbitrary GGUF files. On a fresh machine,
perform a controlled model/API test before relying on the endpoint. The token file above
is only an example reusing an installed Halogen key; another strong existing local token
file is accepted. The key's value is injected at launch and is not written to the profile.

The managed API is `http://127.0.0.1:8840/v1`; model ID **`gufo-flash-next`**.
GUFO itself listens only at `127.0.0.1:8836`. Existing Funnel forwarding to 8840 needs
no port change. Only the tested Chat Completions route is enabled in this profile.
Serving is continuous; individual requests retain a separate 30-minute deadline.

```powershell
.\server\Start.ps1 -Status
.\server\Start.ps1 -Logs
.\server\Start.ps1 -Stop
# After STOPPED, another registered engine can be selected explicitly.
```

Do not rebuild or replace DLLs while an engine is running. The profile records exact
executable/runtime bytes and refuses drift. Re-run qualification before replacing an old
profile; the registration command intentionally does not overwrite an existing one.
No model weights, SDK, runtime DLLs or API-key values are included in Git.
