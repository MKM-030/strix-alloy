# SCC Local Voice

Local speech adapter for existing ServiceNow skills. Repository branch: codex/scc-local-voice-20261012. HaloGen0.18.1 continues in the original checkout.

## Current verified state

- Existing public HaloGen hostname now routes to the authenticated queued gateway on8841. Two simultaneous requests both succeeded. Original8840 and model processes remain running.
- Qwen3-ASR0.6B on127.0.0.1:8851, CPUfloat32.
- Qwen3-TTS0.6B CustomVoice on127.0.0.1:8852, CPUbfloat16, Ryan speakingGerman.
- Browser client on http://127.0.0.1:8850/ now has ServiceNow enabled. Inbound requests succeed; callbacks currently fail authentication because the password differs between ServiceNow and the local file. No credentials reach browser JavaScript.
- Actual German bridge roundtrip returned the exact original sentence: TTS6.77s, ASR1.50s. Two worker-level samples also matched exactly. BF16TTS is about2.2times faster thanfloat32; this is utterance-based speech, not full duplex or realtimeTTS.
- ServiceNow planners and the new normal Chat agent HR case creator SCC Local Voice run in the native assistant preview. The first HR question is displayed. Multi-turn and end-to-end voice remain unverified. The original voice-only agent is unchanged.

## Start/status/stop

Open PowerShell:

```powershell
cd C:\Projects\strix-alloy-scc-voice\voice
.\Start-Voice.ps1 -Action Start
.\Start-Voice.ps1 -Action Status
```

The existing HaloGen backend must already be running. Model snapshots are cached on E: and are reused without requiring a fresh model download. First startup can take time. Status distinguishes loading from listening; it does not claim a complete dialogue test.

Open http://127.0.0.1:8850/ on this PC. Use the local audio test, then microphone recording. The first microphone permission must be granted by the user. Recording is monoPCM WAV, max60seconds. Transcript can be edited before sending. Browserlocalhost spelling is intentionally rejected; use127.0.0.1.

```powershell
.\Start-Voice.ps1 -Action Stop
```

Stop affects only this worktree's audio/bridge workers. It leaves HaloGen and its gateway running. Do not expose8850 throughFunnel: the UI is intentionally local.

## ServiceNow connection and remaining credential correction

The user created both credentials and approved activation. The dedicated SCC assistant, context profile, normal Chat agent and five existing-tool bindings are active. The assistant now references the normal Chat agent; the voice-only example association was removed without changing that original agent.

The dedicated Bot Integration identity is `scc-local-voice`. User ID/email and callback username are `marcel.kaefke@soprasteria.com`. User-configured admin ACL and dynamic-user data access were retained. Inbound token verification works.

Standard message-auth, provider-application, connection alias, HTTP connection, outbound configuration and assistant channel records are created and active where applicable. No new tables or protected-script changes.

Funnel retains `/` -> 8841 and adds `/scc-voice` -> 8853. Callback URL: https://strix-alloy.tail7f425a.ts.net/scc-voice/callback. External authenticated probe returns200; unauthenticated probe401. UI8850 remains loopback-only.

Actual ServiceNow callbacks reach the bridge with Basic authentication. A value-free comparison confirmed username_match=True and password_match=False. Correct only the local callback password with the EXACT value saved in the ServiceNow credential SCC Local Voice Callback:

```powershell
& "C:\Projects\strix-alloy-scc-voice\voice\Update-CallbackCredential.ps1"
```

This hidden prompt preserves the existing restricted file ACL. Never paste secrets into chat. Reload only the bridge after correction; do not stop the working HaloGen/audio services unnecessarily. Configure-Voice.ps1 now preserves the existing callback username on reruns and accepts -CallbackUsername for fresh setup.

After correction: prove a real callback, a two-turn text conversation without case creation, and the full ASR -> ServiceNow -> TTS roundtrip. A successful HTTP ACK is not a completed voice test.

## Diagnostics and recovery

Logs: E:\SCC-Voice\logs. Audio measurements: audio-smoke.json and audio-smoke-bf16.json. Synthetic WAVexamples are stored beside them. No real microphone recordings are persisted by default.

Gateway configuration: server\.local\scc-gateway.json. Queue8, queue timeout120seconds. Existing token/upstream are preserved.

If a separate HaloGenlauncher changesFunnel back to8840, reselect the queue after8841 is healthy:

```powershell
tailscale funnel --bg --yes http://127.0.0.1:8841
```

Gateway rollback:

```powershell
tailscale funnel --bg --yes http://127.0.0.1:8840
```

Do not retry an uncertain case-creation request automatically. BotHTTP200 is only an acknowledgement; the answer arrives by callback. `completed=true` means the conversationended. Secure/unknown unsupported controls fail visibly instead of being spoken or guessed.

Latest native follow-up: second user message was accepted, then the conversation ended without an answer. This is an additional unresolved dialogue issue, independent of the callback password. Conversation ID 69dd7ecf933f4354e7f2b9fa6aba1035; input collector called capability aca5634f4312121038520464dbb8f236. User language in the runtime was en. No case was created. Investigate response-generation result and task completion before claiming multi-turn success.
