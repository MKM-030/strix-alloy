# Halogen 0.15.0 on Windows / WSL2

Version-pinned Strix Alloy adaptation for a 128 GiB Strix Halo Windows machine.
The service defaults to **129,024 context positions, one slot and continuous
serving**. Authentication, rotating logs, the clock-independent guard lease,
Windows file-sharing retries and independent startup-cache scheduling are retained.
This is not an upstream claim of WSL2 support.

## Start and connect

Use PowerShell 7 from the repository root after installation:

```powershell
.\backends\halogen-wsl2-0.15.0\Start.ps1
# Explicit equivalents and controls:
.\backends\halogen-wsl2-0.15.0\Start.ps1 -ContextSize 129024 -ServeSeconds 0
.\backends\halogen-wsl2-0.15.0\Start.ps1 -Status
.\backends\halogen-wsl2-0.15.0\Start.ps1 -Logs
.\backends\halogen-wsl2-0.15.0\Start.ps1 -Stop
```

Keep the serving window open. Wait for `READY` before sending requests. Context
accepts 4,096 to 262,144 positions, shared by prompt and output; changing it
requires restart. A parameter's accepted range is not a guarantee every workload
fits. `ServeSeconds 0` has no serving-duration cutoff. Startup has a separate
900-second timeout. Guards still stop the owned engine on unsafe conditions.

Local API base: `http://127.0.0.1:8731/v1`.
Model: `halogen-qwen3.8-flash-next`. Send `Authorization: Bearer <API token>`.
The generated token is in this package's ignored `.local/api-token.txt`.

The token is required on health, models, chat, Responses and metrics routes.
It is never included in Git or container environment variables. On an existing
machine, reuse the prior token through an explicit local copy only after checking
that the destination has no credential; fresh installs generate a new token.

```powershell
$token = (Get-Content '.\backends\halogen-wsl2-0.15.0\.local\api-token.txt' -Raw).Trim()
Invoke-RestMethod 'http://127.0.0.1:8731/health' -Headers @{Authorization="Bearer $token"}
.\app\test-backend.ps1 -Backend Halogen
```

A previously configured Tailscale Funnel can continue forwarding HTTPS to port
8731. Pause it during backend changes and before any unauthenticated diagnostic
profile. Resume only after local positive and negative authentication checks.
Public exposure is not enabled automatically by this installer.

## Existing weights, not an automatic model upgrade

This adaptation deliberately retains `qwen38-flash-next-w4b.hgn`, its matching
`qwen38-flash-next-w4b.overlay.hgn`, and the existing tokenizer. Both checkpoint
and overlay paths are explicit in the launch environment. The new engine's v2
checkpoint default cannot silently replace them. Upstream 0.15.0 supports the
older files; **the newer v2 checkpoint is not installed or qualified here**.
No model conversion or download is performed by these scripts.

## Fresh installation

Prerequisites: PowerShell 7, Windows Python 3.12+, 128 GiB Strix Halo with the
reviewed 64 GiB graphics carve, Ubuntu 24.04 WSL2 with a 56GB memory ceiling,
working DXG, GCC 13.3, OpenSSL headers and Docker Engine accessible to the selected
Linux user. Keep the model files on native WSL Ext4, not a Windows-mounted drive.
The [host guide](../halogen-wsl2/docs/setup.md#1-prepare-windows-and-wsl) explains
prerequisites; use the version-specific image and commands below, not its old tag.

Pull the exact official image inside the selected WSL distribution:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:28ef278ab621a67b02550d1f1bfecfe641552803b96dae588018425fcfe38f36
```

Then, from PowerShell 7, replace the example paths with your existing files:

```powershell
.\backends\halogen-wsl2-0.15.0\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
.\backends\halogen-wsl2-0.15.0\Start.ps1
```

`-LinuxUser` selects a nondefault user. `-AmdWheel` can replace `-DxgLibrary` for
the qualified AMD wheel. `-VerifyModelHash` hashes the large model files during
explicit installation; otherwise their sizes are checked. Setup does not need a
running model server. It extracts components from a stopped temporary container,
compiles original compatibility code, and verifies exact hashes. Engine binaries,
headers and generated machine files stay ignored under `.local/`.

The installer does not modify BIOS, drivers, WSL settings or Windows memory policy.
The 47 GiB physical / 121 GiB commit default admission and 12 GiB runtime floors
are retained. Never start both versions or another large inference engine together.

## Diagnostics and rollback

The explicit `Trace4k`, `Single4k` and `Serve4k` profiles are finite diagnostics,
not the normal continuous server. They retain their exact-source qualification
requirements. Keep public forwarding OFF when running those legacy diagnostic
profiles. Normal `Serve` uses the authenticated wrapper and validates the actual
engine/API version and reported context before advertising readiness.

The complete working 0.14.2 package remains at `../halogen-wsl2-0.14.2/`.
To roll back, pause Funnel, stop 0.15.0 and verify cleanup, then start the old
package explicitly. Do not delete unresolved locks or silently run both versions.
Restart Funnel only after the selected authenticated service is ready.

```powershell
python -B -m unittest discover -s backends/halogen-wsl2-0.15.0/tests -v
pwsh -NoProfile -File tests/publication/Test-PowerShellSyntax.ps1
```

Linux-only bridge and process fixtures are explicitly skipped on Windows; run
those tests in WSL to exercise them. A fresh checkout additionally skips the
installed-component tests until setup is complete. Source tests do not replace
a real model-start, authenticated request, streaming and stop/restart check.

[Release pins](profiles/release.json) identify the exact image and locally rebuilt
components. [Validation](validation-upgrade-20260929.md) records observed results
and limitations. [Notices](THIRD_PARTY_NOTICES.md) describe external components.
No model weights, proprietary engine, extracted API or driver bundle is published.
