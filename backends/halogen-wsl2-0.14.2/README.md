# Halogen 0.14.2 on Windows / WSL2

Experimental, version-pinned Strix Alloy adaptation for a 128 GiB Strix Halo
Windows PC. This package uses **Halogen 0.14.2**, not the 0.13.8 compatibility
package in `../halogen-wsl2`. It is independent of native PROJFIX and GUFO.
Upstream Halogen does not support WSL2; this adaptation is not an upstream release.

The packaged profiles use **4,096 context positions, one slot, and bounded
serving**. Larger-context, multi-slot and unattended operation are not enabled
by this update. The first-party smoke tests use serial drafting. Do not infer
MTP, arbitrary client workloads or prolonged stability from those tests.

## Prerequisites

Use Windows 11, PowerShell 7, Windows Python 3.12+, a 128 GiB Strix Halo machine
with the reviewed 64 GiB graphics carve, Ubuntu 24.04 WSL2 with a 56GB memory
ceiling, working `/dev/dxg`, GCC 13.3, OpenSSL development headers and Docker
Engine in that distro. The chosen Linux user must already have Docker access.
Models must be on native WSL Ext4, not a Windows-mounted drive.

The existing [WSL2 prerequisite guide](../halogen-wsl2/docs/setup.md#1-prepare-windows-and-wsl)
explains the host setup. Its 0.13.8 image and launch commands are **not** the
0.14.2 commands. Do not run both packages together. No installer here changes
BIOS, drivers, services, security policy, pagefile, or WSL configuration.

Obtain the official HGN checkpoint, matching overlay and complete tokenizer:

```text
/srv/models/flash-next/
  qwen38-flash-next-w4b.hgn
  qwen38-flash-next-w4b.overlay.hgn
  tokenizer/tokenizer.json
  tokenizer/tokenizer_config.json
  ... retain all other supplied tokenizer assets
```

The existing model files can be reused. No model download, model conversion or
cloud fallback is performed. Obtain the qualified AMD DXG library or wheel
separately, following the [dependency instructions](../halogen-wsl2/docs/setup.md#2-obtain-the-dependencies).
Models, the Halogen image and AMD components retain their own license terms.

The exact required image is below. Pull it manually **only if it is not already
present**, from a shell inside your selected WSL distro:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:f3f99aa48f3a051f18da9ee24b333ca108fe745773fd036a365fe1875871d0be
```

No floating `latest` tag is accepted. [Release pins](profiles/release.json)
identify the image, engine, entrypoint, compiled adapters and HIP header.

## Install this version explicitly

From the repository root in PowerShell 7, replace the example paths:

```powershell
# Checks prerequisites; does not build, write configuration or load the model.
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1

# Extracts pinned dependencies locally and builds the reviewed adapters.
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
```

Use `-LinuxUser <user>` for a nondefault Linux user. Instead of `-DxgLibrary`,
`-AmdWheel <absolute-path-to-the-qualified-wheel>` extracts only its pinned DXG
library. Add `-VerifyModelHash` on explicit installation to hash both large HGN
files; otherwise the installer verifies their sizes. It does not silently claim
that a size check is a fresh full model hash check.

Installation creates a **stopped** temporary container to extract the exact
engine, entrypoint and HIP headers, then removes that owned container. It never
starts that container, launches the model, or writes an installed driver. Three
small adapters are compiled locally and must match their pinned SHA-256 values.
Generated assets and machine configuration stay under this version's ignored
`.local/` directory. The other package's installation is not overwritten or
silently migrated. Installation does not require a running model server.

## First run: qualify, then serve

Run these sequentially. Each command must finish successfully before the next:

```powershell
# Confirms the exact preflight vector, then exits before model registration.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Trace4k

# Loads the model, checks two short answers and verifies shutdown/recovery.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Single4k

# Loads the model, checks readiness, then exposes a bounded serving window.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Profile Serve4k -ServeSeconds 300
```

The last command prints `READY` after its two smoke answers. From a second
PowerShell 7 window at the repository root:

```powershell
.\app\test-backend.ps1 -Backend Halogen
```

The API is `http://127.0.0.1:8731/v1`. The helper requests serial drafting,
thinking off, and a small non-streaming answer. Keep requests inside the 4K
context and remaining serving window. A larger context or extra slots are not
accepted as launcher arguments. Serving lasts 30–300 seconds after the initial
smoke answers and has an independent 600-second total container deadline.
Slow startup can therefore refuse a long serving window rather than extending
the deadline. Outstanding requests may be interrupted when serving ends.

`Single4k` requires a successful **current-source** `Trace4k`. `Serve4k` requires
both successful trace and smoke qualifications for the exact installed source,
artifacts and configuration. A changed source/configuration or incomplete prior
run cannot inherit an old pass. Do not edit state files to bypass this check.

After installation, `Start.ps1 -Profile Serve4k -PrintOnly` prints the sealed
command without launching a model or contacting WSL. The shared repository
selector remains read-only discovery; it does not start or hot-switch engines.

## Resource and lifecycle controls

Prelaunch admission requires a stable 45 GiB Windows available-physical and
117 GiB commit-headroom window, with a new immediate sample before container
creation and start. Runtime floors remain 12 GiB for both counters. The pinned
copy policy, one-slot KV pool, read-only mounts, 44 GiB cgroup, loopback port and
process-tree deadline are not relaxed to make a launch pass. These are observed
experimental limits, not a guarantee that driver behavior cannot freeze a host.
Save work before inference. Never repeat the historical three-full-260k test.

Ctrl+C requests the controller's cleanup. Normal shutdown drains the sampler,
stops only the verified owned container, verifies terminal state and memory
recovery, then waits for the host guard to exit. A success marker is written only
after that sequence succeeds. The independent container deadline remains if the
console is lost. Do not wrap this bounded profile in an automatic restart loop.

Full local run evidence is retained under `.local/attempts/`; failed attempts
remain failures. An unresolved `.local/runner.lock` blocks further runs and
uninstall. Inspect the exact owned container and recovery evidence before any
manual reconciliation; never delete the lock merely to get past a refusal.

## Rollback and tests

After stopping this version and verifying cleanup, the original package remains
available at `backends/halogen-wsl2/`, with its separate installer and 0.13.8
`Serve32k` profile. Nothing silently falls back or runs both versions together.

```powershell
.\backends\halogen-wsl2-0.14.2\Uninstall.ps1
python -B -m unittest discover -s backends/halogen-wsl2-0.14.2/tests -v
```

Uninstall removes only hash-verified manifest-owned generated files; model files,
Docker images, retained attempts and unrelated data remain. Offline tests use
fixtures, not a model. Two local-asset checks are skipped in a fresh clone until
explicit installation. [Validation](validation-20260929.md) separates source,
build, fresh-checkout and live checks. [Notices](THIRD_PARTY_NOTICES.md) identify
external components; no engine, driver, header bundle or model is redistributed.
