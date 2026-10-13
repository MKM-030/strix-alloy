# Native ServiceNow voice transport adapter

This adapter implements the WebRTC signaling and `transcripts` data channel
observed in the instance's native **Test Assistant / Start call** client. There
is no separate webpage or manual chat input. It supplies a microphone receive
track and a continuous speaker send track. German transcription uses local
Whisper on 8861; streaming speech uses local Qwen3 TTS on 8862. The existing
ServiceNow SCC agent and order confirmation logic remain behind the existing
authenticated loopback bridge on 8850. No LLM or order decision is implemented
here.

## Status and limits

Core and transport tests passed on Windows on 2026-10-13, including two real aiortc peers,
native deferred offer, subsequent trickle ICE, RTP in both directions, native
data-channel messages, and wrong-token denial. The test substitutes speech and
conversation services and creates **no order**. This does not prove a native
ServiceNow UI call, speech recognition quality, a real order, or WAN media.

A separate real-speech transport probe subsequently passed using the benign
2.64 s `scc-native-smoke.wav` fixture, live Whisper and live Qwen3 TTS: first
received audible output after 5.703 s including input playback. Recognition
was `Guten Tag.` and `Wie kann ich helfen?`; the natural pause correctly made
two turns with the 550 ms endpoint. Its dialogue response was a fixed test
fixture, so this still does not verify ServiceNow or a human microphone.

The subsequent complete synthetic-microphone RTP test passed with live
Whisper, ServiceNow and Qwen3 TTS. It spoke the onboarding request, Alex
Sommer's name, and an explicit confirmation after the exact order summary.
ServiceNow reported the existing `REQ0010012` / `RITM0010011`; no replacement
order was requested. A second fresh call asked for the employee name again.
Both owned backend sessions were released. The full run took 322.437 seconds,
including the second call. See `VALIDATION.json` and the local runtime report.

With the separately configured temporary no-thinking gateway mode, first
received speech took 34.531 seconds from call start (22.533 seconds on the
second warm call). Substantive responses still took about 50–68 seconds after
recognition. ServiceNow progress announcements were English, while questions,
summary and result were German. These remain visible demo limitations. The
initial automated native UI check was blocked by browser microphone permissions.
The user's later real native-browser call passed platform authorization and
established LAN ICE, with visible microphone transcription and spoken output.
Production logs show successful ICE at 13:18:14 Berlin on 2026-10-13. A natural
hello then exposed a separate defect: the generic router replied in English
and supplied OutputText without the input control required by the bridge,
leaving the turn busy until its 180-second timeout.

The Bot adapter now sends the dedicated demo's configured `session_language`
through the documented `contextVariables.requester_session_language` field.
The actual emitted fallback transcript is passed once as initial Bot history
with the first real user message. This does not claim the complete audio was
heard if the caller interrupted playback. A backend capability flag enables
this only before a deferred first request; ordinary START_CONVERSATION clients
remain compatible. Ambiguous HTTP delivery never replays that history.
Bounded, allowlisted callback metadata diagnostics support investigation of
the generic-turn completion signal. These changes do not treat intermediate
task announcements as input-ready and do not alter order confirmation rules.

The real RTP hello probe at 11:40 UTC confirmed a German contextual reply
without a second greeting, with first audible output 6.239 seconds after
recognition. **Natural follow-up is still blocked:** that reply supplied no
input-ready control, so the diagnostic stopped after 60 seconds and ended its
own conversation. It did not send the next laptop intent. A separate laptop
first-turn probe reached the real employee-name question after 52.400 seconds
from recognition, but its earlier progress announcement remained English.

Callback comparison proves that `streamState: END` with `streamActive: false`
is insufficient: the laptop progress message has the same shape as the final
hello reply, then continues after 1.107 seconds and supplies InputText 36.980
seconds later. A temporary isolated `botToBot: false` probe also stalled after
the same generic reply. It was rolled back at 11:52:04 UTC; that experimental
setting is absent from production. No timer, text heuristic, or stream-END
shortcut releases the busy state. Finishing natural small-talk continuation
requires an actual ServiceNow terminal/input-ready contract or routing change.
The temporary diagnostic budget is configured as zero for future starts.

After the verified ServiceNow Chat/Voice instruction update, the 12:21 UTC
first-turn RTP probe reached the actual German employee-name question in
33.077 seconds after recognition, versus 52.400 seconds in the earlier
comparison. Genuine InputText readiness and owned session release passed;
all services were healthy and idle afterward. It sent no name or confirmation.
The earlier announcement still arrived in English, so that language defect
remains. This test did not repeat generic small talk or the later order steps.

Automatic turns use energy VAD (100 ms onset, 120 ms minimum voiced audio,
550 ms final silence). Short confirmation utterances are explicitly tested. Barge-in
clears queued audio and fences late audio immediately. An already submitted
ServiceNow request is allowed to finish, because cancelling an order request
could leave uncertain side effects. The next utterance queues behind it.
Complete ServiceNow response messages are spoken as soon as they arrive;
the adapter does not wait for the subsequent input prompt. A failed speech
request still allows the submitted ServiceNow turn to settle. The configured
native greeting is spoken once when the backend supplies none, unless the
caller has already begun speaking.

The 14:05 UTC update separates bounded microphone recognition from the single
ServiceNow request worker. Accepted subsequent speech now produces a visible
user transcript while the prior ServiceNow turn still waits for input readiness;
it is submitted only after that turn actually becomes ready. Two pending audio
utterances and two recognized turns are allowed. Overflow and ASR failures show
explicit German notices. Such notices use assistant transcripts because the
native client immediately disconnects on a protocol `error` message.

A failed backend turn stops further input and gives a German transcript and
bounded spoken notice asking the caller to end the call. It never retries or
automatically ends the submitted request. Late audio is fenced; unsent turns
are discarded explicitly after failure. This fixes local recognition starvation
and silent failure, **not ServiceNow's missing input-ready callback** or the
observed short-name misrecognition. Real-microphone follow-up remains to verify.
Content-free VAD/queue/timing logs and bounded numeric Whisper segment metrics
support that test. `verbose_json` explicitly disables token timestamps and
extra language-probability calculation; transcription validation and decoding
settings remain unchanged. No confidence cutoff, name prompt or audio recording
was added. See `INGESTION-VALIDATION-20261013.json` for the 43 native/56 Bot tests,
source-derived notice contract, isolated TDD failures, and Native-only activation.

This is full-duplex audio transport with interruption, not Omni joint inference.
The existing SCC bot account remains the fixed demo identity; native browser
authorization does not impersonate arbitrary employees in the bot backend.
Native conversation/interaction metadata is currently omitted: the existing
HTTP conversation bridge does not expose those identifiers. Do not interpret
the native test analysis panel as a complete Voice runtime execution trace.

One call at a time is supported. The adapter retains its own bridge cookie
for each call and releases that owned conversation at disconnect through the
CSRF-protected `/api/end` route. That route deletes the old session and cookie
without allocating another slot. Clean restarts and second calls can therefore
acquire a fresh session. Failed release blocks reuse until an explicit retry
succeeds. If another
client occupies the existing 8850 bridge session, calls fail explicitly; this
adapter never hijacks or clears an unknown client's session. After an abrupt
crash a restarted adapter cannot recover an old private cookie; wait for its
30-minute expiry or restart the verified project bridge under operator control.

## Authentication and networking

Production mode requires matching instance and dedicated voice assistant IDs,
the exact ServiceNow Origin, and a JWT-shaped OAuth token. The original token
is verified by POST to the fixed instance-native
`/api/sn_voice_aia/ai_voice_agent/agents_authorized` endpoint. Only HTTP 200 with
`{result: [valid agent sys_ids]}` containing the configured native SCC voice
agent `a6337ddf93f787105c8132d47aba1058` is accepted. The downstream existing chat
agent remains `a4a9438393738354e7f2b9fa6aba101d`.
The platform validates the voice-service token claim and agent execute rights.
JWT syntax alone never authorizes a call. Redirects are disabled. Query strings,
tokens and exception messages are never logged. The original source-derived
authorization contract subsequently admitted the user's real native calls.

Default mode denies access. Development credentials, if explicitly configured
through a file, require at least 32 characters and a loopback peer. Never use
development mode on any reverse-proxy route. Do not put credentials in git.

The HTTP listener binds only `127.0.0.1:8860`. A trusted TLS proxy can strip an
isolated prefix such as `/scc-native` before forwarding. Native UI config then
uses `https://<approved-host>/scc-native` as its orchestrator URL. Access logging
must also be disabled in any proxy for this path, since native OAuth arrives
as a WebSocket query parameter.

No STUN or TURN is configured. SDP contains host candidates only. The demo
browser must have direct connectivity to an advertised host interface, e.g.
the authorized Tailscale network. A public HTTPS tunnel transports signaling,
not UDP media. Do not claim a remote cloud browser works without testing media.

## Start and verification

Use a separate environment; existing model environments are untouched:

```powershell
Set-Location C:\Projects\strix-alloy-scc-voice\voice\native-bridge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s . -p 'test_*.py'
.\.venv\Scripts\python.exe test_transport.py --live-wav ..\native-speech-validation\runtime\scc-native-smoke.wav
.\.venv\Scripts\python.exe native_bridge.py --config config.example.json
```

Health is `http://127.0.0.1:8860/health`. An unauthenticated connect request must
return HTTP 401. Keep the dedicated native assistant deployment and conditional
ServiceNow routing change separate from this server. Production mode never
falls back to local credentials when platform authentication fails.

The optional `--probe-backend` flag runs one explicitly requested no-order
greeting before serving. It writes `runtime/backend-probe.json` and releases
its own greeting session without reserving the sole slot.
Do not repeat this flag while investigating an uncertain in-flight turn. The
HTTP listener starts after the probe finishes. A failed probe is reported in
the JSON file even if the transport listener subsequently starts.

The actual backend greeting probe on this date reached ServiceNow after 1.015 s
but produced no complete reply within 186.656 s. Investigation found the
HaloGen WSL backend stopped, with gateway connection errors. The probe ended
its owned conversation and was not retried. The model was subsequently
restored without lowering its context or memory guard. A real first-turn
audio baseline then passed, but needed 105 seconds from recognition to the
employee-name question. Its first complete ServiceNow announcement arrived
77 seconds earlier; progressive speech now removes that avoidable adapter
delay. Runtime reports distinguish backend latency from ASR and TTS latency.

`demo_audio_smoke.py --run-approved-audio-demo --output runtime/<unique-run>`
replays the authorized demo fixtures as microphone RTP through live ASR,
ServiceNow and TTS. It uses an isolated random loopback listener, never the
public route, and retains a WebSocket reader for heartbeat replies. A changed
order summary pauses for bounded operator review of its exact SHA-256 and
all supplied choices before the explicit spoken confirmation fixture. A
failed or ambiguous turn is never retried automatically. `--first-turn-only`
ends before sending a name or confirmation. These are synthetic audio tests,
not proof that the actual browser microphone or native OAuth works.
The additional `--hello-first --first-turn-only` diagnostic waits for the
actual fallback greeting, replays a natural hello as genuine microphone RTP,
and waits at most 60 seconds for backend input readiness before the laptop
intent. It never sends a name or order confirmation, and never bypasses a
busy backend. This shorter deadline applies only to the diagnostic harness.

The isolated Funnel path was added and independently checked by the coordinating
agent: `/scc-native/health` returned 200 in production auth mode; connect without
a token returned 401. The original three routes remained intact. To remove
only this route: `tailscale funnel --bg --set-path /scc-native off`.

Before demo acceptance, test on the actual microphone/laptop: connect through
the native UI, say the employee/laptop request, answer spoken questions, give
explicit confirmation, verify exactly one REQ/RITM, interrupt playback, end
the call, and repeat with a fresh conversation. Record actual timings.
