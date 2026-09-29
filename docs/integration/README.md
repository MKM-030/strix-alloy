# One source repository: installation and testing

This is a **source integration checkpoint**, not an all-engine serving release.
The published native runtime remains v0.1.1. The current Halogen package is pinned
to **0.14.2**, with guarded 4K single-session profiles. The unchanged 0.13.8
package remains an explicit compatibility option, not the selected current version.
GUFO persistent service remains unqualified and is not enabled or substituted.

## Fresh checkout and prerequisites

```powershell
git clone --branch codex/unified-source-20260929 --single-branch `
  https://github.com/MKM-030/strix-alloy.git C:\AI\strix-alloy
Set-Location C:\AI\strix-alloy
```

Use PowerShell 7 for the new discovery command and Halogen package. Python 3.12+
is needed for Halogen setup and offline Python tests. Models and compatible engine
binaries are external: cloning this source does not download or install them.
Never run multiple large engines together. This checkpoint does not implement
cross-engine ownership, automatic shutdown or a no-reboot hot switch.

The native published configuration uses a 96 GiB graphics carve. The WSL2
configuration uses 64 GiB and a 56GB WSL memory ceiling. These are distinct
qualified configurations, not permission for a script to change your BIOS.
No BIOS, driver, pagefile, security, service or WSL configuration is changed by
the selector. See each backend's prerequisites before attempting inference.

## Inspect the available backends without starting anything

```powershell
.\app\select-backend.ps1 -Backend Projfix -Action Describe
.\app\select-backend.ps1 -Backend Halogen -Action Describe
.\app\select-backend.ps1 -Backend GUFO -Action Describe
```

`Native` and `Projfix` are explicit aliases for native llama.cpp with PROJFIX.
`Describe` returns JSON and performs no installation, process or network probe.
Native `PrintOnly` validates explicit absolute paths and returns the original
launcher's argument vector; it does not invoke that launcher or claim model validity.
Halogen and GUFO refuse `PrintOnly`. All `Start`/`Stop` actions on the selector
are rejected; use the backend's own qualified workflow instead.

## Native PROJFIX: obtain the runtime, load the model, test

Obtain the compatible native runtime from the existing
[v0.1.1 release](https://github.com/MKM-030/strix-alloy/releases/tag/v0.1.1),
or follow the [native build guide](../../setup/README.md). Obtain all nine PROJFIX
GGUF shards and optionally the matching shared MTP head using the
[native setup guide](../user/README.md). No full model is bundled here.

Replace the example paths with your existing runtime and weights:

```powershell
.\app\select-backend.ps1 -Backend Projfix -Action PrintOnly `
  -ModelDir C:\AI\models\qwen38-flash\projfix -RuntimeDir C:\AI\strix-runtime
.\app\launch-flash-next.ps1 -PrintOnly `
  -ModelDir C:\AI\models\qwen38-flash\projfix -RuntimeDir C:\AI\strix-runtime
```

After confirming the native host profile and stopping other inference, start:

```powershell
.\app\launch-flash-next.ps1 `
  -ModelDir C:\AI\models\qwen38-flash\projfix -RuntimeDir C:\AI\strix-runtime
# Optional: append -DraftPath C:\AI\models\qwen38-flash\projfix\mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
```

Keep the server window open. The native UI is `http://127.0.0.1:8826` and its
API is `http://127.0.0.1:8826/v1`, model ID `Qwen3.8-Flash-Next`. Use the
API test below from a second PowerShell terminal after the model is ready.
Stop only the instance you started using the original launcher's `-Stop` with
its matching `-RuntimeDir` and port. Do not use global process-kill commands.

## Halogen 0.14.2: install, qualify, then serve briefly

Follow the [0.14.2 setup guide](../../backends/halogen-wsl2-0.14.2/README.md)
for the pinned image, host prerequisites and external HGN/overlay/tokenizer.
This version has its own ignored `.local` installation and reuses model files
without copying another checkout's machine configuration. No running model
server is needed for installation. The examples below require an already
obtained qualified DXG library; replace the Linux paths and distro/user as needed.

```powershell
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1

# Run each command only after the previous one exits successfully.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Trace4k
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Single4k
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Serve4k -ServeSeconds 300
```

Use `-AmdWheel` instead of `-DxgLibrary` for the qualified downloaded AMD wheel.
`-VerifyModelHash` on explicit installation adds full hashes of both large model
files; default model checks verify sizes. Install builds three pinned adapters
and extracts local dependencies from a stopped container, not from a model server.

The first profile validates the exact trace and exits before model registration.
The second loads the model, checks two short serial answers, then verifies clean
shutdown and memory recovery. The third requires both exact-source passes and
exposes one **4,096-position slot** on `http://127.0.0.1:8731/v1` for 30–300
seconds after its initial smoke answers, subject to a 600-second total container
deadline. Keep the supervising terminal open; this is not an always-on service.
Failed or unresolved runs retain their evidence and block automatic retries.

The older [0.13.8 package](../../backends/halogen-wsl2/docs/setup.md) remains
unchanged at `backends/halogen-wsl2/`, including its separate `Serve32k` profile.
It is an explicit fallback, not a silent alternative. Stop and verify cleanup
before using another version. The 0.14.2 update does not inherit 0.13.8's larger
context qualification or activate the historical full-context research tests.

## Send a short API request in a second terminal

After the selected server is ready, use exactly one of:

```powershell
.\app\test-backend.ps1 -Backend Projfix
.\app\test-backend.ps1 -Backend Halogen
```

The helper verifies `/v1/models` and sends one small, non-streaming request.
Halogen requests explicitly select serial drafting and disable thinking.
It does not load or stop a server. It rejects GUFO and non-loopback destinations,
uses no cloud fallback, and follows no HTTP redirects. PASS means nonempty final
answer text; `exact_ok` separately reports whether the answer was exactly `OK`.
Whole-request time is not decode tokens/second or time to first token.

## Switching and remaining release gates

Stop the current backend and confirm its own cleanup before starting another.
The selector does not enforce mutual exclusion across launchers. Switching between
the published native and WSL2 memory profiles may require a supported manual
carve change and reboot; that is not automated or newly qualified here.
Do not restart the historical three-full-260k experiment. Do not turn bounded
Halogen serving into an unattended service with a restart loop.

GUFO's service qualification, its portable runtime/model installation, a shared
long-running endpoint, and common start/status/stop ownership remain open.
A model-load benchmark or a successful offline test is not a substitute for
those gates. The 141-commit local GUFO research history is not force-pushed or
rewritten by this checkpoint. No new GUFO speed or correctness claim is made.

## Offline validation and provenance

```powershell
python -B -m unittest discover -s tests/publication -v
pwsh -NoProfile -File tests/publication/Test-PowerShellSyntax.ps1
python -B -m unittest discover -s backends/halogen-wsl2-0.14.2/tests -v
# The unchanged 0.13.8 package also retains its own tests/ directory.
```

The API tests use a tiny fake loopback server, not a loaded model. Linux-only
C fixtures are skipped on Windows and must not be counted as Windows passes.
The [source manifest](halogen-source-manifest.json) records every imported
legacy 0.13.8 WSL2 file against commit `6b35ef80445d426237f87175258c7ceab724b252`.
Original licenses and third-party notices remain inside that package.
[Validation record](validation-20260929.md) separates rerun tests from historical
inference evidence and lists what was not executed for this publication.

[Halogen 0.14.2 validation](../../backends/halogen-wsl2-0.14.2/validation-20260929.md)
records this update separately; the earlier source-integration validation remains historical.
