# SCC native voice instance customization

Inspected and edited through the ServiceNow native UI on 2026-10-13. Instance: `soprasteriaassvsdemo14.service-now.com`.

## Saved instance state

- Native assistant `SCC Native Voice`: `8aa131d793f787105c8132d47aba1095`, saved inactive. German/Deutsch, native Lena sound, greeting `Hallo, ich helfe Ihnen bei der Laptopdemo.` Native Test Assistant is available. No telephony number or portal launcher was added.
- Data Broker Server Script `Fetch voice assistant details`: `dfb09052b79df21081fee3fdde11a9af`. `Fetch-voice-assistant-details.js` is the exact original. `Fetch-voice-assistant-details.draft.js` is the saved customization, reopened and compared byte-for-byte via DOM text.
- Owned update set: `SCC Native Voice - native test routing - 2026-10-13`, `08d2bd5f93f787105c8132d47aba107e`, ServiceNow Otto for Virtual Agent (`sn_nowassist_va`), In progress. Native Add to Update Set action explicitly confirmed the data broker was captured.

| Property | Value at save | Record sys_id |
| --- | --- | --- |
| sn_nowassist_va.scc_native_voice.enabled | true (verified after save) | 270371df93f787105c8132d47aba10e5 |
| sn_nowassist_va.scc_native_voice.assistant_id | 8aa131d793f787105c8132d47aba1095 | 1e3371df93f787105c8132d47aba10ed |
| sn_nowassist_va.scc_native_voice.orchestrator_url | https://strix-alloy.tail7f425a.ts.net/scc-native | 40537ddf93f787105c8132d47aba1048 |

The override applies only when enabled is exactly `true`, the caller has admin, the configured valid sys_id equals the requested assistant, and the configured endpoint equals the exact pinned destination. Otherwise the native global AVA service URL remains the result. No global AVA service URL or original HR assistant was edited. Original SCC chat agent `a4a9438393738354e7f2b9fa6aba101d` remains unchanged and is the adapter's Bot API execution identity. Dedicated native Voice counterpart `SCC Laptop Onboarding Voice`, `a6337ddf93f787105c8132d47aba1058`, is attached to the native assistant and is the adapter's required authorization agent. This is native UI/media with the existing SCC chat backend; native Voice-agent orchestration has not replaced that backend.

The counterpart has active config `fa04fdd3933b87105c8132d47aba104d`, administrator-only execute ACL `6955311f933b87105c8132d47aba10c6`, Dynamic user identity with an ITIL-only role mask, and active Autonomous mappings to the original tools `15ebcb8f93738354e7f2b9fa6aba1072` and `8b5c4f0393b38354e7f2b9fa6aba10f7`. Original tool scripts were not changed. The native picker requires exact type Voice and excludes Omni. See `counterpart-evidence.json` for complete record IDs, settings, original-preservation check, and two unused native-wizard tool copies retained without deletion.

Native association was verified after a full page reload. Exact observed Test Assistant URL:
https://soprasteriaassvsdemo14.service-now.com/now/now-assist-with-va/voice-test/8aa131d793f787105c8132d47aba1095

## Native transport and authentication evidence

- `Start-voice-session.js`: sys_ux_client_script `b75ca5a73b71fe105237c1c643e45a24`, Voice test default macroponent `4838af0eb719f21081fee3fdde11a9f8`. Uses microphone audio, RTCPeerConnection, `transcripts` data channel, and WSS `<orchestrator host/path>/webrtc/connect/agent_operator`.
- Native query: `instance_name`, `voice_service_id`, `voice_service_language`, `receive_data=true`, `data_channel=true`, `diagnostics=admin`, `client_app=admin_test`, plus `auth_token` from the native OAuth flow. The selected path prefix `/scc-native` is compatible with the native string concatenation.
- Offer message: `{type:'offer',sdp:{type:'offer',sdp:<SDP>},client_timestamp:<milliseconds>}`. Answer message accepts `{type:'answer',sdp:<SDP or {sdp}>,iceServers:[...]}`. Candidate messages use `{type:'candidate',candidate:{candidate,sdpMLineIndex,sdpMid}}`.
- `VoiceTestingUIUtils.js`: UX client script include `ef074e8d0fe48310380dd9e530d1b2df`. Transcript data channel messages include `{type:'transcript',data:{role,content,message_id,caller_turn_id,latency_ms?,turn_num?}}`. Metadata uses `conversation_id`/`interaction_id`.
- `Oauth-flow.js`: native UX script `656f3a82b726321081fee3fdde11a9a9`. Uses authorization-code PKCE S256 with same-instance `/oauth_auth.do` and `/oauth_token.do`; requested claims include `voice_service_id`. No session tokens were extracted into this evidence.
- `Authorized-agents-resource.js`: sys_ws_operation `66b97ca0ff6a6210129628ecf43bf1cf`, POST `/api/sn_voice_aia/ai_voice_agent/agents_authorized`. Requires authentication=true; SNC Internal=false; resource ACL authorization=false. Script validates service ID and native per-service authorization before returning allowed agents.
- Adapter request: original native token as Bearer header; JSON `{serviceId:<configured assistant>,clientApp:'admin_test'}`. Pin the ServiceNow instance host and do not follow redirects. Reject opaque/non-JWT tokens before forwarding because the native helper's opaque-token branch does not enforce the service claim.
- `VoiceRestUtilsSNC.js` proves JWT service authorization uses `new sn_auth.VoiceServiceInfoRequestor().getVoiceServiceInfo()` and compares the resulting verified `voice_service_id` to the request serviceId. Do not replace this with local unverified claim decoding.
- `VoiceAgentUtilsSNC.js`: `getAuthorizedAgentIds` returns an array of unique agent sys_id strings, only for active agent configs linked to the voice assistant context profile and for which the current user has agent execute rights. Expected wire envelope is `{result:[<IDs>]}`; the source and native REST envelope convention are known, but a live authenticated wire response still needs verification. Require the configured actual Voice counterpart ID to be present, not merely HTTP 200.
- `Voice-system-config-resource.js` is KAA-only and is unsuitable for bearer-token verification. No custom auth resource was created.

## Validation and remaining gate

`node routing-draft.test.cjs` passed six local routing isolation checks: default native route, explicitly enabled correct assistant, unrelated assistant isolation, non-admin isolation, unapproved endpoint rejection, and trailing-slash normalization. The original source failed the two adapter-routing assertions before the draft was written. These checks do not execute ServiceNow Glide APIs or prove live voice media.

Enabled was initially false and changed to true only after root authorization following adapter readiness and native association verification. A fresh native test page was opened after this change. One native Start call attempt immediately showed the critical error `Microphone access is blocked by browser permissions.` The UI showed No active call, with no transcript or analysis. The test tab was closed, and the adapter workstream was released to run its independent audio harness. No utterance, tool, or order was initiated by this native browser probe. Because native getUserMedia precedes WebSocket creation, this probe does not prove OAuth/WSS acceptance or end-to-end native audio. No credential values were read.

HTTPS/WSS Funnel reachability alone does not establish a WebRTC media route: the intended demo browser needs the authorized Tailscale/private media path or suitable TURN. No firewall change is part of this customization. The user must complete the native microphone test in a browser with microphone permission and media connectivity.

Final update-set audit verified the enabled-property customer update `d423b5df93f787105c8132d47aba10be` (instance updated 2026-10-13 03:07:11, modcount 1) remains in owned routing set `08d2bd5f93f787105c8132d47aba107e`. The set contains the transform, all three properties, and the new assistant's goodbye_message/retry_prefix attributes. The Voice counterpart's configuration and assistant deployment are captured across the existing Generative AI Controller set `0fc415cb933fcf14e7f2b9fa6aba10fa` as documented in the JSON evidence. The primary deployment customer-update target label still reads `New voice assistant - 1`, although current native UI shows SCC Native Voice. This evidence is not a verified complete portable update-set export.

## Rollback

1. Set `sn_nowassist_va.scc_native_voice.enabled` to `false` and save. Reload any native test page to obtain native routing again.
2. For complete code rollback, open Data Broker Server Script `dfb09052b79df21081fee3fdde11a9af` in the correct application scope, replace Script with the exact contents of `Fetch-voice-assistant-details.js`, save, reopen and verify.
3. Leave the dedicated assistant inactive. The new properties may remain disabled for auditability; deletion is unnecessary. Do not modify the original HR assistant or original SCC chat agent as rollback.

UI proof in `screenshots/`: saved routing, initial disabled properties, final enabled property, final owned update set, saved native assistant, saved Voice-agent association, ready native test UI, and the microphone-permission failure. Native source originals and the saved patch are durable rollback evidence. `deployment-evidence.json`, `counterpart-evidence.json`, and `native-probe-evidence.json` record observations; no secrets or native tokens are included.
