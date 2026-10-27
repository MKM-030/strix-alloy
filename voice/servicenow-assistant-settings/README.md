# Native Voice assistant settings projection (staged)

This directory contains a new server-only Script Include and a narrowly scoped opt-in addition to the existing Authorized Agents resource. Nothing here is installed or applied automatically.

Install the Script Include as LocalLLMVoiceAssistantSettings, API name sn_voice_aia.LocalLLMVoiceAssistantSettings, in the existing Voice application scope 022bd6e9b720a61081fee3fdde11a9df. It must not be client callable. Keep the resource in that same scope. Preserve its authentication requirement and ACL metadata.

The existing Authorized Agents operation is 66b97ca0ff6a6210129628ecf43bf1cf. Root's fresh baseline is mod_count 11, updated 2026-07-22 20:45:00, source SHA256 03473117c0f75ab338103256bf2708ea6fd0f791284aa86ff17120aa3a2f0467. Compare the live source and metadata again immediately before any application. Do not replace protected SNC sources or amend closed releases.

Requests without numeric assistantSettingsVersion: 1 retain the original array response. Version 1 retains the native service/auth checks, then requires an authenticated non-guest caller, a bounded JWT-shaped Bearer token, native VoiceServiceInfo binding to the requested service, and nonempty valid authorized agent IDs. JWT syntax is an additional gate; token authentication and service binding remain native server responsibilities. Opaque OAuth cannot request this projection.

The result contains authorized_agents and assistant_settings. The helper rereads the selected assistant configuration, ordered active native language configurations, TTS metadata, native description/introduction, key terms and VAD. Explicit behavioral settings are allowlisted; source-proven runtime CONFIG_DEFAULTS fill missing supported values. Numeric zero and boolean false are preserved. language_source distinguishes configured, tts and native_default language origins; behavior_sources distinguishes configured attributes from runtime defaults. Native nullable secondary-language prompts remain null. A consumer must not audibly render an English native-default retry/goodbye message without an applicable localized message. Missing mandatory language/selection configuration produces a bounded 503 response. No provider/connection/credential helper, cache builder or cache update is invoked.

First and secondary languages retain native sequence order, trigger phrases and both voice/DTMF selection prompts. This projection does not perform a language switch itself. The host must validate and consume the projection per call; it must not assume arbitrary BotToBot context variables are read by its planner.

Telephony authentication/fallback metadata is projected only as non-secret scalar configuration. This change does not implement SIP transfer, DTMF, identification, account lockout or native Cartesia voice synthesis in the local WebRTC transport. Host consumers must declare unsupported requested features and must not silently claim them as implemented. Provider routing IDs, x_snc_param and transfer destinations are deliberately excluded.

Run: node voice/servicenow-assistant-settings/test_assistant_settings.cjs

The tests execute the actual staged helper and resource in a Node VM with unavoidable ServiceNow platform doubles. The failing baseline and passing result are retained in red-test-receipt.json and green-test-receipt.json. These tests establish the JavaScript contract and authorization branches; they do not prove live ServiceNow scope/accessibility, platform authentication, native capture, mobile behavior, or end-to-end model adherence.
