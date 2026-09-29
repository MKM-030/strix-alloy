# Halogen 0.14.2 on Windows / WSL2

A local, authenticated Halogen server for a 128 GiB Strix Halo Windows PC.
The normal launcher defaults to **129,024 context positions (126 Ã— 1,024), one
session slot, and continuous serving**. It does not stop after five minutes.
This is an experimental WSL2 adaptation; it is not an upstream WSL support claim.
**The 126K service now passed live startup and authenticated inference after a
Windows heartbeat-file replacement fix. See the [current validation record](validation-heartbeat-fix-20260929.md)
for the tested lifecycle and remaining limits.**

## Start the installed server

From the repository root in PowerShell 7:

```powershell
.\backends\halogen-wsl2-0.14.2\Start.ps1
```

That command loads the model, checks API/engine identity and two short answers,
then prints `READY`, the endpoint, the token, and the active context size.
Keep the terminal open. Engine output, requests and memory status appear there.
The model is loaded once and stays loaded until you stop it or a health/resource
failure triggers shutdown. There is no automatic restart loop.

The previous `Serve4k` command was a finite qualification test, not the normal
interactive server. It remains available explicitly; `Serve` is now the default.

## Choose context and lifetime

```powershell
# Default: 126K in binary units; prompt and generated output share this window.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -ContextSize 129024

# Other examples; only one server may run at a time.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -ContextSize 65536
.\backends\halogen-wsl2-0.14.2\Start.ps1 -ContextSize 126000

# Continuous (default). StartupTimeoutSeconds limits loading, not serving.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -ServeSeconds 0 -StartupTimeoutSeconds 900

# An optional finite serving window, measured AFTER readiness.
.\backends\halogen-wsl2-0.14.2\Start.ps1 -ServeSeconds 1800
```

`ContextSize` accepts 4,096â€“262,144 positions and sets both `HALOGEN_CTX` and
`HALOGEN_KV_POOL_POSITIONS`. Slot count stays one. The launcher checks `/health`
for the actual context, slot context, pool size and slot count; it refuses a
silently reduced context rather than advertising the requested number.
Changing context requires stopping and restarting the server; it is not a
per-request change. Larger values need more memory and may fail admission on a
busy desktop. Accepting a parameter is not proof that every workload fits.

`ServeSeconds 0` has no wall-clock serving cutoff. `StartupTimeoutSeconds`
defaults to 900 and accepts 120â€“3600. A positive `ServeSeconds` is optional and
accepts up to 604800 seconds. These are not client request timeouts.

## Endpoint and API token

| Client field | Value |
|---|---|
| OpenAI-compatible base URL | `http://127.0.0.1:8731/v1` |
| Model ID | `halogen-qwen3.8-flash-next` |
| Authentication | `Authorization: Bearer <token>` |
| Token location | `backends/halogen-wsl2-0.14.2/.local/api-token.txt` |

The first normal start generates a cryptographically random 256-bit token.
It persists across restarts and is printed after readiness. It is not a dummy
key: missing, invalid and duplicate authorization headers receive HTTP 401.
The API token belongs in the client's API-key field. `/health`, `/v1/models`,
chat, Responses and the other HTTP API routes are authenticated.

The token file is excluded from Git. On Windows its inherited permissions are
removed and access is restricted to the current user and SYSTEM. It is mounted
read-only inside the owned container; its value is not placed in Docker arguments,
container environment variables, source manifests, or application log records.
Do not commit it or paste it into an issue. Anyone who can read your user account's
private files can use this local credential; this is not isolation from that user.

In a second PowerShell terminal at the repository root:

```powershell
$token = (Get-Content '.\backends\halogen-wsl2-0.14.2\.local\api-token.txt' -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod 'http://127.0.0.1:8731/health' -Headers $headers
.\app\test-backend.ps1 -Backend Halogen
```

The test helper reads the same token automatically. It also accepts `-ApiToken`,
`-ApiTokenFile`, or `HALOGEN_API_TOKEN`. The API is bound to loopback: use this URL
on the Windows PC, not on another device. No cloud fallback or public binding is
configured. The native engine's internal port is not published.

## Logs, status and stopping

```powershell
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Status
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Logs
.\backends\halogen-wsl2-0.14.2\Start.ps1 -Stop
```

Ctrl+C in the serving terminal also requests shutdown. `-Stop` targets the
recorded service run, not all Python, WSL or Docker processes. Wait for `STOPPED`
and confirmed recovery before starting another engine.

The status record is `.local/current-service.json`. It identifies the current
run under `.local/services/<run-id>/`, including `engine.log` and `service.log`.
Engine output is shown live and written to rotating files. Application log files
rotate at 10 MiB with five backups; Docker also has a bounded log rotation policy.
The host guard records rotating memory telemetry. Request logs include method,
path, status and elapsed time, not authorization headers, query strings, prompt
bodies or response bodies. The startup token is printed separately to the
terminal and is not sent to the file logger. Treat engine diagnostics as local
operational data, not material to upload indiscriminately.

## Memory and crash handling

The single-slot, 48 GiB copy policy, 44 GiB cgroup, pinned engine/bridge,
read-only model mounts and 12 GiB physical/commit runtime floors are retained.
Admission scales with context. The default 129,024-position profile plans for
47 GiB Windows available physical memory and 121 GiB commit headroom. A refusal
prints both required and measured values. Close an unused memory-heavy app or
choose a smaller context; the launcher will not close your applications.

Continuous serving does not remove orphan-process protection. A separate host
memory guard and controller heartbeat maintain a lease read by a supervisor
inside the container. Loss of either process stops renewal; a stale lease stops
the owned engine instead of leaving it running indefinitely. Normal shutdown
verifies the exact container's terminal state and baseline-relative memory recovery.
An unresolved failure retains its evidence and lock. Do not delete a lock merely
to get past a refusal. Save work before inference; guards cannot guarantee against
all driver failures. Never reproduce the historical three-full-260K experiment.

## Fresh installation

Required: Windows 11, PowerShell 7, Windows Python 3.12+, 128 GiB Strix Halo,
reviewed 64 GiB graphics carve, Ubuntu 24.04 WSL2 with a 56GB ceiling, working DXG,
GCC 13.3, OpenSSL headers and Docker Engine accessible to the chosen Linux user.
See the [host prerequisite guide](../halogen-wsl2/docs/setup.md#1-prepare-windows-and-wsl).
No script changes BIOS, drivers, services, pagefile, security policy or WSL settings.

Reuse the matching HGN checkpoint, overlay and complete tokenizer on native WSL
Ext4. Obtain the qualified DXG library or AMD wheel separately. Models and binaries
are external; the installer neither downloads a model nor requires a running server.
The required image is pinned, not `latest`:

```sh
docker pull ghcr.io/peonist-ai/halogen-flash-server@sha256:f3f99aa48f3a051f18da9ee24b333ca108fe745773fd036a365fe1875871d0be
```

Pull only when absent. From the repository root, replace the example paths:

```powershell
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
.\backends\halogen-wsl2-0.14.2\Install.ps1 -Install -Distribution Ubuntu-24.04 `
  -ModelDirectory /srv/models/flash-next -DxgLibrary /opt/rocm/lib/librocdxg.so.1
.\backends\halogen-wsl2-0.14.2\Start.ps1
```

Use `-LinuxUser` when the default user is not the intended one. `-AmdWheel`
is an alternative to `-DxgLibrary`; `-VerifyModelHash` performs full weight hashes
on explicit installation. Otherwise the two large weight files are size-checked.
Setup extracts pinned dependencies from a stopped temporary container, builds
three small adapters locally, and verifies their hashes. No driver is replaced.

## Diagnostics, rollback and validation

`-Profile Trace4k`, `Single4k`, and `Serve4k` retain their original finite,
exact-source qualification contract. They do not accept a custom context.
Use the default `Serve` profile for the authenticated interactive service.
The 0.13.8 compatibility package in `../halogen-wsl2` remains unchanged and
must not run at the same time. Stop and verify recovery before uninstalling.

```powershell
.\backends\halogen-wsl2-0.14.2\Uninstall.ps1
python -B -m unittest discover -s backends/halogen-wsl2-0.14.2/tests -v
```

Uninstall removes only manifest-owned generated installation files. Local run
logs, the separately generated service credential and user model files are retained.
[Earlier 4K validation](validation-20260929.md) is historical evidence, not a claim
that every context or prolonged runtime was tested. [Third-party notices](THIRD_PARTY_NOTICES.md)
cover the separately obtained engine and dependencies; the API wrapper leaves the
pinned engine and upstream API file unchanged.

Reinstallation note: after uninstall, retained service logs and the token make
the version directory nonempty. The unchanged installer refuses to overwrite
those files. Use a fresh checkout for a clean reinstall and preserve the previous
checkout as evidence; no automatic service-state migration is implemented.
