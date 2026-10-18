# SCC Local Voice bridge

This adapter reuses the standard asynchronous Virtual Agent Bot Integration API. It does not modify or impersonate a supported native ServiceNow Voice provider. Existing HaloGen skills remain in ServiceNow; the local browser supplies utterance-based ASR/TTS. Full duplex, telephony and the native Voice preview are not implemented.

## Run

Use Python 3.12 and `aiohttp==3.14.3` (the existing server virtualenv is suitable):

```powershell
& C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe C:\Projects\strix-alloy-scc-voice\voice\bridge.py --config E:\SCC-Voice\bridge.json
```

Open **http://127.0.0.1:8850/** on the machine. `localhost` is deliberately not an alternative hostname. The UI listens only on loopback. Do not publish port 8850 through a tunnel. Only the separate callback listener on port 8853 may be published through authenticated HTTPS.

### Configuration

```json
{
  "settings": {
    "service_now_enabled": true,
    "user_id": "DEDICATED_DEMO_USER",
    "email": "DEDICATED_DEMO_EMAIL",
    "inbound_id": "scc-local-voice",
    "ui_port": 8850,
    "callback_port": 8853,
    "callback_username": "scc-voice",
    "session_seconds": 1800,
    "turn_seconds": 180,
    "max_sessions": 8
  },
  "servicenow_token_file": "E:\\SCC-Voice\\secrets\\servicenow-token.txt",
  "audio_token_file": "C:\\Projects\\strix-alloy-clean\\server\\.local\\servicenow-api-token.txt",
  "callback_token_file": "E:\\SCC-Voice\\secrets\\callback-password.txt"
}
```

Credential files are read once at startup. Each must contain at least 16 characters. Never commit them. The instance is fixed to `https://soprasteriaassvsdemo14.service-now.com`. The browser cannot select another upstream, user identity or model, and never receives service credentials.

Before ServiceNow authentication is configured, set `service_now_enabled:false`; only `audio_token_file` is required. In this mode the page explicitly reports that ServiceNow is disabled. Audio playback, microphone transcription and a local TTS→ASR test still work. Bot requests and callbacks fail closed.

## ServiceNow wiring

1. Dedicated Provider Channel Identity with inbound ID `scc-local-voice`, provider VA Bot to Bot Provider, and its own message authentication. The adapter sends the static inbound token in the documented `token` header.
2. Map that identity to the SCC Local Voice chat deployment through the standard deployment channel configuration.
3. Configure VA API 4.1+ outbound REST connection for this provider application. Endpoint is the externally published HTTPS route leading exclusively to `http://127.0.0.1:8853/callback`. Use Basic auth with `callback_username` and the callback password file. An empty `callback_username` instead requires `Authorization: Bearer <callback secret>`.
4. Keep response streaming disabled initially. The bridge suppresses START/INPROGRESS and only displays/speaks final OutputText. It also recognizes the documented top-level streamState END.
5. Start one dialog, verify greeting callback, submit a harmless question, verify the relevant ServiceNow skill and HaloGen logs, then test microphone and speech output. An HTTP 200 ACK alone is not a successful dialog test.

The callback ACKs authenticated valid envelopes immediately; audio synthesis happens separately. Only callbacks for a known current request/session and the configured identity are accepted. Duplicate payloads are ignored. OutputText is read from `body`, never from the echoed `message.text`. `completed:true` means the conversation ended. InputText/pickers indicate the bot is awaiting input; stream END closes a streamed answer. There is no fabricated turn-complete property. An unresolved request times out visibly and requires a new dialog.

## Limits and operation

- One local session when ServiceNow is enabled, since all requests use one fixed demo identity. Audio-only mode allows up to 8 sessions. Fixed 30-minute lifetime, 200 retained events each. Data exists only in RAM and is not written to logs.
- One pending request per conversation. Enabled picker values are validated server-side and sent with `message.typed:false`. Unknown rich controls are shown as an unsupported-control notice; HTML is never rendered. SECURE input/output controls stop the dialog with a generic notice; their values are not retained, displayed or spoken. This client does not support password/secure steps.
- Mono PCM16 WAV recording, maximum 60 seconds / 20 MiB. ASR uses `qwen3-asr-0.6b` on 8851. TTS uses `qwen3-tts-0.6b`, Ryan preset, WAV on 8852. No arbitrary URLs or browser-supplied keys are forwarded.
- Speech output is limited to 1500 characters per bot message. Longer answers remain readable. The separate audio-test field allows 500 characters. Audio workers can be slow on CPU; failures leave the text available.
- Native browser microphone access requires the user to accept the microphone prompt. Recording starts and stops explicitly. The initial voice is a model preset, not a clone of a real person.
- Reset invalidates in-flight polling and queued speech; old event identifiers cannot be applied to a new session. On restart sessions are discarded. No automatic resend of uncertain deliveries, to avoid duplicate ServiceNow actions.

## Tests

```powershell
Set-Location C:\Projects\strix-alloy-scc-voice
& C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe -m unittest discover -s voice/tests -p test_bridge.py
```

Tests use real loopback HTTP fake upstreams. They verify request/ACK separation, callback auth, CSRF/origin/Host enforcement, independent callback route, duplicate and previous-turn handling, selections, completion, streaming final text, audio-only isolation, credentials remaining server-side and chunked WAV integrity.

Reference contracts: ServiceNow [Virtual Agent Bot Integration API](https://www.servicenow.com/docs/r/api-reference/rest-apis/bot-api.html), [supported features](https://www.servicenow.com/docs/r/zurich/conversational-interfaces/virtual-agent/virtual-agent-api-whats-new.html), and [message authentication](https://www.servicenow.com/docs/r/xanadu/conversational-interfaces/virtual-agent/set-up-message-auth-va-api.html).
