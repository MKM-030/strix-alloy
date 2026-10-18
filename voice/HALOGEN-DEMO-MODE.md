# Temporary HaloGen demo mode

This optional gateway mode removes thinking latency for requests to the existing ServiceNow model alias `halogen-v2` on gateway 8841. It affects **all callers of that shared alias** on `/v1/chat/completions` while enabled; it is not restricted to one agent or voice session. It does not change the ServiceNow transformer, engine defaults, memory reserve, context size, output-token limit, tools, or response format.

The default is off. Gateway JSON accepts `"demo_no_thinking_model": "halogen-v2"` to enable it, or an absent/empty value to disable it. A nonempty value must exactly match the selected public model alias. The original inbound model value is checked before model rewriting. Requests that explicitly name the upstream model and requests to other routes remain unchanged. Matching requests set only `enable_thinking=false` and `reasoning_effort="none"`, including when the incoming request explicitly requested thinking. These fields are supported by the installed HaloGen 0.18.1 `api/serve_api.py` request model and chat-kwargs handling.

## Controlled activation

Only restart after gateway `active_requests=0`, `queued_requests=0` and engine `busy=false`, `in_flight=0`, `queued=0`. Coordinate with the voice test owner so no new call enters during the restart. The launcher verifies its saved PID/start time, executable, exact worktree/config/port command, and direct child before controlling processes.

```powershell
& C:\Projects\strix-alloy-scc-voice\voice\Start-QueuedGateway.ps1 -Action Stop
& C:\Projects\strix-alloy-scc-voice\voice\Start-QueuedGateway.ps1 -Action Start -DemoNoThinking
```

This restarts only the owned 8841 sidecar. It reuses the loaded 8731 backend; no model restart is required. The 8840 gateway is untouched. A start request that asks for a different demo mode while the sidecar is already running refuses rather than silently changing or ignoring the mode. After start, verify the owned listener, the config target `halogen-v2`, and authenticated gateway/engine health before resuming voice calls. Do not log credentials or request/response bodies.

## Rollback

After the same idle checks, stop the owned sidecar and start without the switch:

```powershell
& C:\Projects\strix-alloy-scc-voice\voice\Start-QueuedGateway.ps1 -Action Stop
& C:\Projects\strix-alloy-scc-voice\voice\Start-QueuedGateway.ps1 -Action Start
```

An absent/empty mode passes existing thinking settings through unchanged; engine defaults remain the original enabled/medium settings. Runtime configuration before activation was copied byte-for-byte to `server\.local\scc-gateway.before-demo-no-thinking-20261013.json`, SHA-256 `e9b49616f226879c4ec04783e0e4ea516982c9311543201423adecbb50357f87`. Source backups are adjacent `gateway.before-demo-no-thinking-20261013.py` and `Start-QueuedGateway.before-demo-no-thinking-20261013.ps1`. They contain no new credentials. Functional rollback uses the switch-free launcher; exact file rollback, if needed, requires restoring these backups while the sidecar is stopped, then starting it with the original launcher.

## Verification before activation

A real loopback fixture receives the forwarded JSON and proves target override, default/explicit off, upstream-name exclusion, other-route exclusion, unknown-model rejection, invalid configuration rejection, and preservation of token/tool/response-format fields. The new tests failed against the original gateway, then passed after the patch. All 28 gateway and queue tests passed. The existing intentional peer-disconnect fixture emits `ClientConnectionResetError` when its test backend writes to a closed socket; that test still passes and releases the slot.

Prepared source and passing fixture tests do not establish improved real ServiceNow latency. That requires the controlled voice test after activation.
