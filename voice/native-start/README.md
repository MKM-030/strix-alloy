# Native voice startup on the demo PC

Run `voice/Install-NativeVoiceShortcuts.ps1` once to install the SCC desktop
shortcuts. They use the existing Python environments and installed binaries;
no packages or models are downloaded. Each shortcut leaves its PowerShell
window open so loading progress and errors remain visible.

| Shortcut | Action |
| --- | --- |
| SCC - HaloGen Modell | Start/verify STT and TTS, register the synthetic voice, then start the original guarded model |
| SCC - Speech to Text | Start/verify only Whisper on 8861 |
| SCC - Text to Speech | Start/verify only Qwen3-TTS on 8862 and register its existing synthetic voice |
| SCC - Voice Bridge | Start/verify Bot on 8850/8853 and native authenticated adapter on 8860 |
| SCC - Gateway | Start/verify the existing 8841 gateway with the approved no-thinking mode |
| SCC - Alles starten | Speech, model, gateway, voice bridge, then check health and existing Funnel routes |
| SCC - Status | Read-only stack health; no conversation is created |
| SCC - ServiceNow Voice Demo | Open the native ServiceNow test page; microphone/call start remains manual |

The command-line equivalent is `voice/Start-NativeVoice.ps1 -Action All`.
Other actions are `STT`, `TTS`, `Model`, `Gateway`, `Voice`, and `Status`.
Model startup may take several minutes. Its original memory guard, profile
and retained-lock behavior remain active. A retained model lock requires
inspection using the existing runbook; these shortcuts never remove it.

An OS file lock prevents overlapping SCC starts from simultaneous clicks.
Healthy intended services are reused after command-line, executable,
loopback-listener and health checks. Unexpected port owners cause an error;
the launcher never stops or restarts them. A verified gateway receipt from
a previous Windows boot may be backed up when port8841 is free. This does
not alter any process or model ownership lock.

Bot/native output and ownership receipts are in `native-start/runtime/`.
Speech retains `native-speech-validation/runtime/`; gateway retains its
existing `server/.local/scc-gateway*` logs. Credentials are loaded from the
existing configuration files and are never placed in shortcut arguments.

Do not use the legacy `Start-Voice.ps1`: its CPU workers on8851/8852 conflict
with the native demo memory budget. These launchers refuse that situation.
They make no changes to Tailscale/Funnel routes, firewall or browser permissions.

Healthy services do not prove the complete natural voice dialog: generic
hello continuation and English upstream progress remain documented limitations
in `../native-bridge/README.md`. Startup does not submit a ServiceNow utterance
or order.
