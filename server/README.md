# Strix Alloy managed Windows endpoint

This controller gives a selected, locally owned inference engine a stable authenticated
OpenAI-compatible endpoint. Engines remain separate processes and keep their own weight
formats, allocators and kernels. It does **not** combine arbitrary kernels inside one
model execution, transfer a live KV cache between engines, or silently switch models.

## Current availability

Halogen 0.15.1 and a locally qualified GUFO Windows profile are implemented.
GUFO must use the [pinned build/qualification workflow](../backends/gufo-windows/README.md);
its current qualified build uses TheRock 10.2.0a20260930 with the pinned numerical compatibility patch.
The current GUFO profile supports the tested Chat Completions route and 262144 capacity.
PROJFIX has a [measured fast serial profile](../backends/projfix-windows/README.md): pinned-host expert placement, mapped lookup loading and microbatch512. Registration defaults to serial; explicit legacy MTP retains the older resident layout. Unqualified runtime replacements are refused.

Install the engine first using the version-specific backend guide. Then use PowerShell 7:

```powershell
.\server\Setup.ps1
.\server\Start.ps1 -Backend Halogen -Checkpoint v2 -ContextSize 262144
```

Defaults: v2, 129024 context positions, one active request, cache Off, continuous
serving. `-ContextSize` is allocated capacity, not the length of every input prompt.
The controller refuses to adopt an existing engine: stop any standalone backend and
confirm its cleanup before using this launcher. A second managed instance is locked out.

```text
Local API base: http://127.0.0.1:8840/v1
Public model:  halogen-v2 (or halogen-w4b when explicitly selected)
Backend:       http://127.0.0.1:8731/v1
```

The gateway reuses the backend's existing token in its ignored `.local/api-token.txt`.
Send it as `Authorization: Bearer <token>` (or `x-api-key` for Messages clients).
No API token is printed to managed logs. Read the key locally; do not put it into URLs,
committed configuration, screenshots or benchmark exports.

## Controls and switching

```powershell
.\server\Start.ps1 -Status
.\server\Start.ps1 -Logs
.\server\Start.ps1 -Stop
# Wait for STOPPED and confirmed backend cleanup before starting another profile:
.\server\Start.ps1 -Backend Halogen -Checkpoint w4b -ContextSize 262144
```

Changing checkpoint, context or engine is an explicit stop/start operation. New requests
during shutdown are rejected; existing streams are drained with a bounded shutdown
period. `-PromptCache Off|Exact|Flexible` maps to Halogen's 0/1/2 modes. Off is the cold
benchmark control and the default. The current Exact-cache experiment reported no
reused tokens, so no warm-cache speed benefit is qualified by this release. Exact/Flexible must be benchmarked separately as warm-cache workloads;
do not publish a cached-prefix rate as cold PP512 or PP2048 performance.

Only an explicitly configured native executable with a matching SHA-256 and qualified
local profile can use the native adapter. The qualification marker is a local operator
attestation, not proof produced by the adapter itself. Readiness must also match the
expected engine configuration. Runtime updates invalidate previous qualification.

## Networking and logging

The gateway binds only to IPv4 loopback. Existing Tailscale Funnel forwarding to 8731
continues to reach the backend directly, not this gateway. To expose the managed endpoint,
verify its authentication first, then explicitly point the tunnel at 127.0.0.1:8840.

Health, model discovery and all inference routes require authentication. Management,
logs and arbitrary upstream URLs are not exposed by the HTTP API. A 16 MiB body cap,
one active inference request and finite request/idle timeouts are enforced. Busy
requests return 429 instead of building an unbounded queue. No fallback sends data
to a cloud model. Readiness is checked in a separate task every two seconds; a stale
10-second readiness lease blocks or rechecks inference rather than adding a full
engine probe before every request. Upstream errors invalidate that lease immediately.

`server/.local/controller.log` rotates at 10 MiB with three backups. Per-child stdout
and stderr remain in the same ignored folder for failure investigation. They are not
a permanent archive policy: remove obsolete terminal-run logs manually after review.
The backend keeps its own rotating engine logs and independent memory/lease guard.

## Tests, reproducibility and updates

```powershell
.\server\.local\venv\Scripts\python.exe -B -m unittest discover -s server/tests -v
python -B -m unittest discover -s backends/halogen-wsl2-0.15.1/tests -v
python .\server\check_updates.py
```

The last command is a read-only, on-demand upstream inventory. It does not run a
scheduled updater, install a display driver, replace a binary or prove compatibility.
The policy is latest **qualified** versions: pin candidates, reproduce builds, check
numerics and lifecycle, run matched benchmarks, then promote with rollback available.

See the [research and implementation review](../docs/integration/unified-review-20260930.md)
and [measured checkpoint comparison](../docs/benchmarks/halogen0151-v2-262k-20260930.md).

## Measured prefix reuse

`-PromptCache Exact` is an opt-in for byte-identical cold/warm behavior. Repeated
system/document layouts were measured successfully with both serial and MTP;
the original exactly-8192-token case still missed in Exact mode. Flexible mode
hit that case but does not offer the same general reproducibility contract.
The gateway does not pad or rearrange messages to manufacture hits. See the
[measured cache follow-up](../docs/benchmarks/halogen-cache-gufo-followup-20260930.md).

During shutdown, status reports `stopping`; wait for `stopped` and confirmed
backend cleanup before another launch. Memory-recovery diagnostics include
the unchanged threshold and observed value rather than mislabeling a live guard.

## Select the tested GUFO profile

After explicit GUFO registration and STOPPED confirmation:

```powershell
.\server\Start.ps1 -Backend GUFO -ContextSize 262144
```

The public model ID becomes `gufo-flash-next`; endpoint and existing token remain unchanged.
Native executable and app-local runtime DLL hashes are verified before launch. This is
text-serving regression qualification, not certification of arbitrary models or every API route.

## Select the recovered PROJFIX profile

After explicit registration and a confirmed STOPPED state:

```powershell
.\server\Start.ps1 -Backend Projfix -ContextSize 262144
```

Model ID: `projfix-flash-next`. Registration and decode-mode selection are separate from starting the server. No different engine or model is substituted on failure.
