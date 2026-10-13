# Native voice startup on the demo PC

Run `voice/Install-NativeVoiceShortcuts.ps1` once to install the SCC desktop
shortcuts. They use the existing Python environments and installed binaries;
no packages or models are downloaded. Each shortcut leaves its PowerShell
window open so loading progress and errors remain visible.

| Shortcut | Action |
| --- | --- |
| SCC - HaloGen Modell | Start/verify STT and TTS, register the selected German voice, then start the guarded Voice text-only model |
| SCC - Speech to Text | Start/verify only Whisper on 8861 |
| SCC - Text to Speech | Start/verify only Qwen3-TTS on 8862 and register the selected German voice |
| SCC - Voice Bridge | Start/verify Bot on 8850/8853 and native authenticated adapter on 8860 |
| SCC - Gateway | Start/verify the existing 8841 gateway with the approved no-thinking mode |
| SCC - Alles starten | Speech, model, gateway, voice bridge, then check health and existing Funnel routes |
| SCC - Status | Read-only stack health; no conversation is created |
| SCC - ServiceNow Voice Demo | Open the native ServiceNow test page; microphone/call start remains manual |

The command-line equivalent is `voice/Start-NativeVoice.ps1 -Action All`.
Other actions are `STT`, `TTS`, `Model`, `Gateway`, `Voice`, and `Status`.
Model startup may take several minutes. The Voice shortcut selects
`serving0181-full262-exact-text-voice-candidate-20261013.json`: Halogen 0.18.1,
v2, context 262144, one slot, Exact cache, and an explicit text-only setting.
Other HaloGen profiles keep their existing vision default.

A new Model start requires 36 GiB available physical RAM and 131 GiB commit
headroom, as configured in `model-start-policy.json`. The runtime physical
and commit reserve stays at 18 GiB. Healthy running models are reused.

The documented terminal incident `a596d8b7119f4875b07ea1fedbc9768b` was
archived only after exact owned-container cleanup, absent process/port/WSL
owners, the controller lease, pinned evidence and fresh 36/131 GiB restart
checks passed. Its historical baseline-recovery failure remains recorded.
A different retained ownership lock blocks startup and requires operator
review; no active or unknown owner is stopped.

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

Startup checks service readiness without creating a conversation or
submitting a ServiceNow utterance or order. Open the native Voice action to
verify the German dialog and the selected voice on the device.
