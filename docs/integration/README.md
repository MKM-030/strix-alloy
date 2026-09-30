> Current managed entry point: [server/Start.ps1](../../server/README.md).
> Current Halogen package: [0.15.1 with w4b and v2](../../backends/halogen-wsl2-0.15.1/README.md).
> The original consolidation notes below retain historical commands; use the current guides for new installs.

# One source repository: installation and testing

This is a **source integration checkpoint**, not an all-engine serving release.
The published native runtime remains v0.1.1. The current Halogen package is pinned
to **0.15.0**, with configurable context (default 126K), one slot, authenticated
continuous serving and live logs. The unchanged 0.14.2 and 0.13.8 packages
remain explicit rollback/compatibility options, not the selected current version.
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

## Halogen 0.15.0: configurable context and continuous serving

Use the version-pinned 0.15.0 package with the existing w4b model and overlay.
[Upgrade validation and limits](../../backends/halogen-wsl2-0.15.0/validation-upgrade-20260929.md).

Follow the [Halogen installation and service guide](../../backends/halogen-wsl2-0.15.0/README.md)
for prerequisites and the explicit installer. Reuse your existing HGN weights
and obtain the new pinned 0.15.0 image. Setup does not require a running server.
After installation:

```powershell
.\backends\halogen-wsl2-0.15.0\Start.ps1
# Equivalent default context: -ContextSize 129024 (126 * 1024)
# No serving timer: -ServeSeconds 0
```

The model loads, passes short startup checks, then prints READY, the endpoint,
and the generated local API token. The API remains `http://127.0.0.1:8731/v1`.
Configure model `halogen-qwen3.8-flash-next` and put the printed token in your
client's API-key field. Authentication is enforced, not a placeholder.
The secret is stored locally in this package's ignored `.local/api-token.txt`.

Context is configurable from 4096 to 262144 positions, with a single slot and
memory admission sized for the chosen context. The 126K default is 129024 tokens;
use `-ContextSize 126000` for exactly 126,000. The window includes prompt and output.
A context change requires stopping and restarting the server. The accepted range
is not a guarantee that every size fits every busy desktop.

Engine and API activity appear live in the terminal and rotating log files.
`Start.ps1 -Logs` follows the current engine log; `-Status` reads service status;
`-Stop` requests owned-service shutdown. Ctrl+C also requests cleanup.
Positive `-ServeSeconds` values are optional; the default does not stop at 300
seconds. A startup timeout, memory guard and controller/guard liveness lease
still stop a failed or orphaned server. There is no automatic restart loop.

The older `Trace4k`, `Single4k` and `Serve4k` profiles remain finite diagnostic
commands. They are not the normal server. The separate 0.13.8 package is an
explicit compatibility fallback; never run both versions at the same time.

## Send a short API request in a second terminal

After the selected server is ready, use exactly one of:

```powershell
.\app\test-backend.ps1 -Backend Projfix
.\app\test-backend.ps1 -Backend Halogen
```

The helper verifies `/v1/models` and sends one small, non-streaming request.
Halogen requests explicitly select serial drafting and disable thinking.
It does not load or stop a server. It reads the Halogen token automatically and rejects GUFO and non-loopback destinations,
uses no cloud fallback, and follows no HTTP redirects. PASS means nonempty final
answer text; `exact_ok` separately reports whether the answer was exactly `OK`.
Whole-request time is not decode tokens/second or time to first token.

## Switching and remaining release gates

Stop the current backend and confirm its own cleanup before starting another.
The selector does not enforce mutual exclusion across launchers. Switching between
the published native and WSL2 memory profiles may require a supported manual
carve change and reboot; that is not automated or newly qualified here.
Do not restart the historical three-full-260k experiment. The normal Halogen service stays running until stopped, but must not be wrapped in an automatic restart loop.

GUFO's service qualification, its portable runtime/model installation, a cross-engine shared endpoint and common ownership controls remain open.
A model-load benchmark or a successful offline test is not a substitute for
those gates. The 141-commit local GUFO research history is not force-pushed or
rewritten by this checkpoint. No new GUFO speed or correctness claim is made.

## Offline validation and provenance

```powershell
python -B -m unittest discover -s tests/publication -v
pwsh -NoProfile -File tests/publication/Test-PowerShellSyntax.ps1
python -B -m unittest discover -s backends/halogen-wsl2-0.15.0/tests -v
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
is historical rollback evidence, not the current 0.15.0 upgrade validation.
