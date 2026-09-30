# GUFO on Windows with the latest qualified TheRock SDK

This integration uses **TheRock 10.2.0a20260930 / AMD clang 24** throughout:
compiler, device libraries, HIP and BLAS runtime. This was the latest official
Windows/gfx1151 nightly listed on 30 September 2026. It does not disguise a 10.0
compiler/object file behind newer runtime DLLs. The display driver tested is
**32.0.32015.2008 (Adrenalin 26.9.2)**; no driver rollback is required.

The pinned source is `thomas9120/gufo` at
`7e924c2d787aabf640db3c0f818cb824dc18ec8e`, plus the exact source patch in this
package. Unmodified upstream source still fails the relevant numerical checks
with this SDK. The patch preserves reduction, quantization and recurrent-math
rounding boundaries. Original upstream test files and tolerances are unchanged.

[Latest-SDK evidence](../../docs/integration/gufo-latest-sdk-20260930.md) records
operator checks, matched full-logit/perplexity results, native measurements and
serving tests. [Earlier 10.0 results](../../docs/integration/gufo-toolchain-resolution-20260930.md)
remain a historical baseline. `compatibility-10.0.json` preserves that previous
pin; it is not the active build policy.

## Prepare the source and SDK

Use PowerShell 7, Python 3.12+, CMake, Ninja and Visual Studio C++ Build Tools.
Check out the pinned upstream commit into a **separate clean source directory**.
Keep this source checkout LF-preserving (`git clone --config core.autocrlf=false ...`);
use a repository-local setting rather than changing global Git configuration.
The wrapper applies only the expected patch after checking every original byte;
it refuses partial patches, altered numerical tests and unrelated source changes.

Download the official archive and verify the retained SHA-256 before extraction:

```text
https://nightly.repo.amd.com/rocm/core/tarball/therock-dist-windows-gfx1151-10.2.0a20260930.tar.gz
SHA256 caf1a7f20b4a824e9410db273b9c3ee0ee18d90a315914fce066fd8514997e56
```

That archive digest was computed after downloading over official AMD HTTPS;
no publisher checksum sidecar was available. The manifest separately pins the
compiler and runtime DLL hashes. Extract into a version-specific directory,
without overwriting the working SDK. `.info/version` says `10.2.0`; the archive
date and exact compiler hash distinguish this nightly from earlier 10.2 builds.

Install the upstream pinned vcpkg dependencies first. The wrapper reuses the
selected classic `VcpkgDirectory/installed/x64-windows` tree; it does not update
packages during qualification. Do not rebuild a directory containing a running
engine. No SDK, model or runtime binary is committed here.

```powershell
$Gufo = 'C:\Projects\gufo-latest'
$Sdk = 'C:\AI\sdk\therock1151-10.2.0a20260930'
$Vcpkg = 'C:\Projects\vcpkg'
$Build = Join-Path $Gufo 'build\gpu-test'
$Proof = '.\backends\gufo-windows\.local\qualification-latest'

.\backends\gufo-windows\Build.ps1 `
  -SourceDirectory $Gufo -SdkDirectory $Sdk -VcpkgDirectory $Vcpkg

python .\backends\gufo-windows\qualify_operators.py `
  --sdk $Sdk --source $Gufo --build $Build --output $Proof
```

Use a new evidence directory on each run. All 15 original tests must pass in
both tuning modes. The receipt is bound to compiler, source-patch, executable,
original-test and application-local runtime hashes. A version string or successful
link alone is not qualification. Preserve full-model regression evidence as well.
The local build may use Visual Studio's `debug_nonredist` OpenMP DLL: it is **not
a redistributable binary package**. Public releases need a separate license audit.

## Register and serve

Select the existing target, matching shared MTP head and an existing strong key file:

```powershell
$Model = 'C:\AI\models\Flash-Next\model-00001-of-00003.gguf'
$Draft = 'C:\AI\models\Flash-Next\MTP\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf'
$Token = '.\backends\halogen-wsl2-0.15.1\.local\api-token.txt'
python .\backends\gufo-windows\register_profile.py `
  --sdk $Sdk --source $Gufo --build $Build --model $Model --mtp $Draft `
  --token-file $Token --qualification "$Proof\qualification.json" `
  --context 262144 --register

.\server\Start.ps1 -Backend GUFO -ContextSize 262144
```

Registration intentionally refuses to overwrite an existing managed profile. Stop
the controller, verify STOPPED, and archive the old `.local/qualified-gufo.json`
explicitly before registering a replacement. Keep that file and its original
runtime for rollback. The key is read only at launch and is not saved in the
command vector. Model quality for arbitrary GGUFs is not inferred from operator tests.

```text
API base: http://127.0.0.1:8840/v1
Model:    gufo-flash-next
Native:   http://127.0.0.1:8836/v1
```

The gateway's public address and API key do not change when this profile replaces
the previous GUFO runtime. Existing Tailscale forwarding to 8840 needs no change.
The registered profile supports the tested Chat Completions route, not an assumed
complete implementation of every API. Serving is continuous; requests retain a
separate 30-minute deadline. Context capacity is not occupied prompt depth.

```powershell
.\server\Start.ps1 -Status
.\server\Start.ps1 -Logs
.\server\Start.ps1 -Stop
```

Keep downloads, compilation, other inference and games out of timed benchmarks.
Do not replace executable/DLL files while their process is active. This package
qualifies one exact nightly, not every future 10.2/10.3 compiler. Recheck upstream,
build separately, run the numerical and model gates, then promote; never silently
accept a different compiler because its major version looks similar.

The numerical helper derives from ROCm Device Libraries and retains its
University of Illinois/NCSA license within the patched header. The surrounding
GUFO source remains under its upstream license. No captured model tensors,
SDK binaries, model weights, API-key values or developer runtime DLLs are shipped.
