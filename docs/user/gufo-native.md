# Optional native GUFO service (experimental)

This local research installation has a separate, opt-in GUFO wrapper for Qwen3.8 Flash Next. **Persistent serving is not qualified.** The current installed profile records `persistent_service_unqualified`, so `start` refuses with exit 2. Do not interpret a successful static check as permission to serve. The wrapper changes no client URL, model selection, system setting, or existing launcher.

## Prerequisites and commands

The profile is pinned to this machine's Python 3.12, controller, service-candidate runtime, model descriptors, and evidence paths. The existing 64 GiB GPU carve was the tested configuration; these commands do not change BIOS settings. Static staging and source/build instructions are in [GUFO setup](../../setup/GUFO.md); the [request-policy patch](../../engine-patches/gufo/README.md) describes the server limits. This is no clean-machine installer or compatibility claim for a rebuilt binary.

From this repository's root in PowerShell, provide the exact installed Python executable explicitly:

```powershell
$python = 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe'
& .\app\launch-gufo-flash-next.ps1 -Command print-only -PythonExe $python
& .\app\launch-gufo-flash-next.ps1 -Command start -PythonExe $python
& .\app\launch-gufo-flash-next.ps1 -Command status -PythonExe $python
& .\app\launch-gufo-flash-next.ps1 -Command stop -PythonExe $python
```

The `app/Launch GUFO Flash Next.cmd` entry point accepts the same `-Command` and `-PythonExe` arguments. It preserves the PowerShell wrapper's exit code. Only the four commands above are public; there are no extra GUFO flags or automatic retry. The wrapper resolves its adjacent controller and `config/gufo-service-profile.json`, imports the controller for that invocation only, and passes the controller's JSON result through unchanged. A missing Python executable, controller package, or profile is refused with exit 2 and its evidence path. Qualification evidence is at the profile's `evidence.acceptance` path; run records are at `evidence.runs`.

`print-only` inspects static prerequisites without starting a model. Exit 0 with `static_valid: true` means only that this inspection passed. `start` is successful only on exit 0 with `phase: "committed"`, `ready: true`, and an exact `run` path. The current unqualified profile returns exit 2. Exit 2 can also mean an indeterminate handoff; inspect the exact run with `status` and retain its evidence. Never retry `start` automatically. `status` reports the bounded controller snapshot, and `stop` requests authenticated shutdown of the owned GUFO run and waits for its terminal evidence. An unknown/stale phase, null cleanup, or `control_cleanup_incomplete` is not proof that the model stopped or that retry is safe. Do not stop a process by name or port.

After a separately reviewed real qualification, a ready run would serve at `http://127.0.0.1:8836/v1` with model name `gufo-flash-next`. Its client key is stored in `<run>/private/client-api-key.json`, JSON field `api_key` (`control.json` records this location). A client uses `Authorization: Bearer <api_key>`; the placeholder is not a real key. Read the protected file only for that request header, without printing or copying the key or persistently changing an environment variable or client configuration. GUFO receives the key on its process command line, so the file ACL does not hide it from the same Windows user or administrators. No request should be sent under the current unqualified state. Startup and readiness are distinct: a launched process or static-valid result is not a ready service.

If an opt-in use fails, preserve the run logs and failure records. Use `status`, then `stop` only for the exact owned GUFO run when authenticated control is available. Manually select the former client URL and model to roll back; the wrapper does not switch either setting. Keep failed/consumed attempt markers. See [GUFO setup](../../setup/GUFO.md#finite-service-policy-smoke) for the recorded recovery failure and [historical benchmarks](../benchmarks/gufo-native-20260927.md) for the older binary's measurements.

## Evidence boundary

The service candidate's static runtime was staged. The finite request-policy run loaded the model, executed the policy engine, answered the fixed request correctly, and confirmed owned exit code 0. Its memory recovery failed the 49 GiB floor, so that attempt remains failed and consumed. The installed store, lifecycle, control channel, and four-command CLI passed offline review; persistent service remains unqualified. The separately built output binary has not been executed or accepted by the staged runtime policy. Older-binary benchmark results are historical and do not establish this candidate's performance, stability, or general answer equivalence. The remaining qualification and benchmark markers in the linked documents remain open.
