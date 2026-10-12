# SCC Local Voice

Local speech adapter for existing ServiceNow skills. Repository branch: codex/scc-local-voice-20261012. HaloGen0.18.1 continues in the original checkout.

## Current verified state

- Existing public HaloGen hostname now routes to the authenticated queued gateway on8841. Two simultaneous requests both succeeded. Original8840 and model processes remain running.
- Qwen3-ASR0.6B on127.0.0.1:8851, CPUfloat32.
- Qwen3-TTS0.6B CustomVoice on127.0.0.1:8852, CPUbfloat16, Ryan speakingGerman.
- Browser client on http://127.0.0.1:8850/ is deliberately AUDIO-ONLY until separate ServiceNow credentials and channel are configured. No credentials reach browserJavaScript.
- Actual German bridge roundtrip returned the exact original sentence: TTS6.77s, ASR1.50s. Two worker-level samples also matched exactly. BF16TTS is about2.2times faster thanfloat32; this is utterance-based speech, not full duplex or realtimeTTS.
- ServiceNow main and quick planners now both succeed with halogen-v2. The original HRvoiceagent cannot execute in this NAVA path: strategyTopic is empty. A normal chat AIagent using the same existing HRtools is being prepared inStudio. End-to-end ServiceNow voice success is NOT yet established.

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

## Remaining ServiceNow handoff

Create these two credentials through ServiceNow's standard UI; never paste their values into chat:

1. Token Verifications [token_verification]: name `SCC Local Voice Inbound Token`, generate a secure static token and save.
2. Basic Auth Credentials [basic_auth_credentials]: name `SCC Local Voice Callback`, username `scc-voice`, unique password of at least24characters and save.

Choose a dedicated active ServiceNow demo user with the HRpermissions required by the reused tools. Its email must match exactly one active unlocked user. The adapter fixes this identity on the server; the browser cannot choose another user. Avoid using an administrator as the public demo identity.

Store the same two values locally using the hidden prompts:

```powershell
.\Configure-Voice.ps1
```

This protects E:\SCC-Voice\secrets with a DACL permitting only the currentWindows account andSYSTEM. Existing explicit directory/file access is removed. Only credentialpaths are stored in bridge.json.

`servicenow-setup.js` is preparation code, not executed yet. Once the credentials exist and the dedicated channel is approved, it creates/reuses standard records for the identity, messageauthentication, callbackalias, HTTPconnection, outboundconfiguration and assistantchannel. New outbound/channel/connection records are inactive until tested. No new ServiceNowtables or protectedscript modifications.

Proposed callbackURL: https://strix-alloy.tail7f425a.ts.net/scc-voice/callback. The callback-only listener is127.0.0.1:8853/callback and requiresBasicAuth. Its precise Funnel path mapping must be tested before enabling the outboundconnection. The UI must remain unexposed.

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

## Prepared ServiceNow draft (19:49 UTC)
`HR case creator SCC Local Voice` is now created as a normal Chat agent, ID `e850ba4f933b4354e7f2b9fa6aba105d`. Its configuration and all five copied tool bindings are inactive. Existing HR tools and their inputs are retained; no shared tool code was edited. Studio requires an explicit user-access ACL before completion. After the user identifies the demo account and confirms access, configure the ACL and current-user data access through Studio, activate the five bindings and agent, then replace the voice-only example asset in the SCC Local Voice assistant with this Chat agent. Validate a non-writing conversational turn before authorizing any case creation.

Credential forms are prepared in the browser, not submitted: Token Verification `SCC Local Voice Inbound Token`; Basic Auth `SCC Local Voice Callback`, username `scc-voice`. The user must enter/submit the two secrets, then run Configure-Voice.ps1 locally with the same values (not in chat). Inbound token and callback password must each contain at least 24 characters. Channel/connection activation and public callback mapping remain pending confirmation. No end-to-end ServiceNow voice success is claimed yet.
