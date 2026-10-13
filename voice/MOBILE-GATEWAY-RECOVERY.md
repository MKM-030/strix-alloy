# Mobile voice gateway: deployment and recovery

Status at 2026-10-12 22:45 UTC: **gateway deployed and public authentication verified; complete voice demo still under integration test.** The Windows gateway listens on loopback 8854. Existing Funnel root and callback routes are preserved. The added `/scc-demo` HTTPS route serves the gateway. Actual public page/assets returned 200, unauthenticated API access returned 401, protected-file password login/logout returned 200, and secure cookie attributes were verified without recording credentials. The 13 gateway integration tests passed on Windows.

This is a mobile browser interface to the existing SCC voice bridge. It does not add custom speech directly inside the native Now Mobile application. ServiceNow dialog correctness, catalog behavior, and existing callback routing remain separate integration checks. The ITSM laptop example in the interface is display text; it does not submit an order or create an incident.

## Exact deployment inputs

| Setting | Value |
| --- | --- |
| Windows device | `DESKTOP-8M583SI` |
| Existing worktree | `C:\Projects\strix-alloy-scc-voice` |
| Existing Python 3.12 executable | `C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe` |
| Existing protected callback password file | `E:\SCC-Voice\secrets\callback-password.txt` |
| Existing bridge configuration | `E:\SCC-Voice\bridge.json` |
| Existing bridge listener | `http://127.0.0.1:8850` |
| Existing callback listener | `127.0.0.1:8853` |
| New gateway listener | `http://127.0.0.1:8854` |
| Public origin | `https://strix-alloy.tail7f425a.ts.net` |
| Public base path | `/scc-demo` |
| Intended browser URL | `https://strix-alloy.tail7f425a.ts.net/scc-demo/` |

The password file is reused, read as UTF-8, and never copied into the archive, README, command line, URL, or browser script. The gateway rejects passwords outside 24–512 characters. It reads the file at process startup; any credential rotation requires a coordinated restart. Preserve its existing file protection.

## Files to copy and review

Copy only these files into the same relative locations under the existing worktree:

```text
voice/mobile_gateway.py
voice/tests/test_mobile_gateway.py
voice/mobile_static/index.html
voice/mobile_static/app.js
voice/mobile_static/style.css
voice/MOBILE-GATEWAY-RECOVERY.md
voice/Start-MobileVoice.ps1
```

The original transfer ZIP contains the first six files; the coordinated launcher was added and syntax-checked during deployment. A separate SHA256 manifest covers the original transfer files. Review `git status --short` before copying: do not overwrite another person's changes if any destination now exists. There are no dependency-file, bridge source, or credential modifications in this bundle. The separate launcher manages the owned bridge and gateway processes only. Use UTF-8 for all Windows text reads/writes. No new Python package is required beyond the existing `aiohttp` environment.

## Offline verification first

These tests create isolated mock servers on ephemeral loopback ports. They do **not** call the live bridge or allocate its only session slot.

```powershell
Set-Location 'C:\Projects\strix-alloy-scc-voice'
$gatewayPython = 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe'
& $gatewayPython -m unittest voice.tests.test_mobile_gateway -q
& $gatewayPython -m py_compile voice\mobile_gateway.py
node --check voice\mobile_static\app.js
git diff --check
```

Expected Python result: 13 passing integration tests. They cover authentication and cookie attributes, exact Origin/Host and CSRF checks, proxy allowlists, bounded login attempts and one session, idle/absolute expiry, audio forwarding, upload limits, long-poll concurrency, reset/audio credential rotation, safe GET recovery, and no replay of failed mutations. JavaScript syntax must pass if Node is available on the device. Local staging also passed two helper checks and a mocked UI lifecycle check; those temporary harnesses are not installed runtime files.

The checks do not prove actual phone microphone permission, Safari playback, rendered layout, ServiceNow dialog completion, or successful request creation. Those remain required end-to-end verification steps.

## Coordinate bridge and gateway lifecycle

The private bridge permits one local session. The gateway retains one server-side cookie jar and CSRF token across mobile logout and reset; the browser never receives the bridge cookie. Restarting **only** the gateway discards that cookie while the still-running bridge can retain its occupied slot. Restart the bridge and gateway together. The initial gateway deployment also needs a fresh bridge if a previous local UI session occupies that slot.

The coordinated launcher is:

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-MobileVoice.ps1' -Action Status
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-MobileVoice.ps1' -Action Restart
```

`Restart` preflights ownership of all three ports, stops only Python processes with exact owned bridge/gateway script paths, archives their previous logs, then starts both services. It leaves ASR, TTS, HaloGen and Funnel routes untouched. `Start` starts missing services; use `Restart` when either service has lost its shared session. `Stop` stops these two owned services only. Credentials are read from the existing protected file, never command-line values.

Do not use a broad process stop or the general voice launcher Stop action to recover a gateway session. Keep ASR/TTS workers running. The general `Start-Voice.ps1 -Action Start` starts audio workers and bridge but does not start this gateway.

The bridge reads the configured speech name from settings.tts_voice in its protected configuration JSON. Existing installations default to Ryan; this demo sets the value to scc-demo and keeps model alias qwen3-tts-0.6b. The TTS worker must have the corresponding synthetic profile loaded. On 2026-10-13 the coordinated restart applied this setting; 38 voice tests passed, including the configured-voice request and existing default-voice behavior.

The SCC deployment does not send a greeting topic. Its first authenticated, request-matched ActionMsg with actionType StartConversation marks only the pending START_CONVERSATION as ready for the user's first utterance. Other ActionMsg controls and normal message turns do not unlock input. This is covered by matching-start, unrelated-request, and mid-turn regression cases. The complete voice test suite has 41 passing tests.

Bridge logs retain request IDs, HTTP ACK status/key names, callback match status and control types for support. They do not contain credentials, session cookies, prompt contents or spoken text.

## Exact gateway command

After the existing bridge has a fresh slot, run the gateway in the foreground for its first verification:

```powershell
Set-Location 'C:\Projects\strix-alloy-scc-voice'
& 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe' `
    'C:\Projects\strix-alloy-scc-voice\voice\mobile_gateway.py' `
    --password-file 'E:\SCC-Voice\secrets\callback-password.txt' `
    --public-origin 'https://strix-alloy.tail7f425a.ts.net' `
    --base-path '/scc-demo' `
    --backend-origin 'http://127.0.0.1:8850' `
    --port 8854
```

The bind address is fixed at `127.0.0.1`. There is no public-bind option. Do not pass the password value as an argument. The process must fail closed if the password file is missing or too short. The default mobile limits are one session, one-hour absolute lifetime, 15-minute idle lifetime, five login attempts per minute globally, six API requests in flight, at most two audio requests, and at most two event polls. Request-body reads time out after 30 seconds. Mutations are never automatically replayed after uncertain failures.

## Verify locally without consuming a bridge session

Use the exact public Host header on loopback checks. GET authentication status and unauthenticated API requests do not initialize a bridge session.

```powershell
curl.exe --silent --show-error --include `
    -H 'Host: strix-alloy.tail7f425a.ts.net' `
    'http://127.0.0.1:8854/auth/session'
curl.exe --silent --show-error --include `
    -H 'Host: strix-alloy.tail7f425a.ts.net' `
    'http://127.0.0.1:8854/api/session'
curl.exe --silent --show-error --include `
    -H 'Host: wrong.example' `
    'http://127.0.0.1:8854/auth/session'
```

Expected results respectively: HTTP 200 with `authenticated:false`; HTTP 401; HTTP 403. Responses must have `Cache-Control: no-store`. The root page must contain `/scc-demo/app.js` and `/scc-demo/style.css`, with no unresolved `__SCC_BASE_PATH__` marker. All listeners must remain on loopback. Avoid logging into the local bridge directly during the mobile test, because that would compete for its single slot.

## Public routing contract

Preserve the existing Funnel handlers and add only the new demo path when the local checks and integration review pass:

| Public path | Existing/intended target | Requirement |
| --- | --- | --- |
| `/` | Existing service on `8841` | Preserve |
| `/scc-voice` | Existing callback on `8853` | Preserve existing prefix stripping |
| `/scc-demo` | New gateway on `8854` | Strip `/scc-demo`; preserve public Host |

The gateway receives `/`, `/auth/session`, and `/api/...`, while the browser uses `/scc-demo/`, `/scc-demo/auth/session`, and `/scc-demo/api/...`. Its secure cookie has path `/scc-demo`. The proxy must preserve `Host: strix-alloy.tail7f425a.ts.net`; the gateway does not trust forwarded headers. Do not loosen Host, Origin, cookie, or CSRF checks to work around an incorrect proxy mapping. Do not expose `8850`, `8851`, or `8852` directly. The deployed command was `tailscale funnel --bg --set-path /scc-demo http://127.0.0.1:8854`. Actual public authentication and assets verified prefix stripping and the Host contract. Both original handlers were verified afterwards.

After adding the route, verify the public root page and assets load, `/scc-demo/auth/session` reports unauthenticated, and `/scc-demo/api/session` returns 401 before login. Recheck that the two existing handlers still behave as before. These results validate routing/authentication only, not demo readiness.

## Phone verification and readiness

Use one browser/device at a time. Log in through the HTTPS page using the existing protected password. Check that the cookie is Secure, HttpOnly, SameSite=Strict, and scoped to `/scc-demo`; do not copy cookie values into logs.

1. Confirm login starts or resumes the fixed operator's bridge conversation. Choice buttons must submit the original opaque values. Waiting for long polls must not block sending.
2. Use the ITSM laptop example. Verify the assistant stays in the intended ITSM flow and reaches an actual, confirmed outcome. This gateway does not resolve a ServiceNow dialog ending early.
3. On mobile Safari, tap “Sprechen”, grant microphone access, speak briefly, and tap “Aufnahme stoppen”. Confirm the resulting German transcript is editable. With “Text vor dem Senden prüfen” enabled, transcription must not submit automatically.
4. Confirm assistant captions, spoken replies, and “Erneut anhören” work. If automatic playback is blocked, the explicit replay gesture must work. Check narrow-screen layout and keyboard behavior on the real device.
5. Use “Neu starten” after the bridge is no longer busy; verify a second conversation works without occupying an extra backend slot. Log out and back in; verify the single retained backend session still works. A second unauthenticated browser cannot use the APIs.
6. Record any uncertain submission outcome before retrying. Do not automatically resend an order/message after a timeout. Diagnose using the existing ServiceNow and bridge tools.

Only report the demo ready once routing, authentication, speech, actual dialog progression, reset/reconnect, and the required ServiceNow outcome have all been verified. Gateway deployment and authentication are verified. Phone microphone/playback and the full ServiceNow order remain separate acceptance checks.

## Rollback and common recovery cases

- If the new public path fails verification, remove only the `/scc-demo` handler using the installed verified path-handler command. Do not reset the whole Funnel configuration; preserve `/` and `/scc-voice`.
- Stop only the identified gateway process. Remove or restore only the seven allowlisted files if rolling back code. Preserve all other worktree changes and credentials.
- A backend “session capacity” problem after restarting the gateway alone requires a coordinated bridge/gateway restart. Do not run repeated `/api/session` calls or start extra gateway instances to recover it.
- A 403 from every gateway request usually means wrong Host/Origin or incorrect prefix handling. Check the exact routing contract before changing anything.
- A 409 at login means the one mobile session is already active. Log out in that browser or allow its session to expire. A 429 means the configured attempt/concurrency limit is active; wait rather than bypassing the limit.
- A 502 after an upstream session failure is not permission to resend a mutation. The gateway may refresh a safe GET once, but does not replay start/message/reset/audio POSTs.
- Keep ASR/TTS workers, the existing callback route, and unrelated public services running throughout gateway rollback. Bridge restart, if needed to clear the retained slot, must use the verified existing launcher lifecycle.
