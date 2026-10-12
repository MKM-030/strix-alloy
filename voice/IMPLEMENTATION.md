# SCC Local Voice — implementation record

Goal: reuse existing ServiceNow skills and HaloGen through standard VA Bot Integration, with local Qwen3 ASR/TTS and minimal platform changes. Native ServiceNow Voice provider enum remains unchanged.

Worktree: codex/scc-local-voice-20261012, base1268605. Preserve dirty primary checkout and running HaloGen0.18.1.

Plan
1. Bounded FIFO gateway queue, default off; standalone8841 trial before routing live requests.
2. Isolated Python3.12 CPU ASR8851 and TTS8852, cached models on E:, authenticated loopback only.
3. Generic utterance-based voice bridge: loopback browserUI8850; callback-only authenticated listener8853. Existing ServiceNow asynchronous BotAPI.
4. Dedicated SCC Local Voice assistant and provider identity, message authentication, callback connection, channel. Never reuse internal bot credentials.
5. Real parallel LLM test, German TTS→ASR test, Assistant Designer dialog, then full callback voice dialog. Document remaining blockers precisely.

Interfaces
- Audio models are qwen3-asr-0.6b and qwen3-tts-0.6b; mono PCM WAV; TTS Ryan baseline.
- Audio bearer secret read from existing local token file. No credential values in logs, browserJS or git.
- Bridge uses fixed server-side ServiceNow user/email identity. Browser cannot choose another identity.
- Bot HTTP success is ACK, callback body contains answer; completed means conversation end.
- Models remain independent from ServiceNow skill/model configuration.

Rulings
- Use separate audio environments: upstream transformers versions differ.
- CPU first to preserve current AMD/HaloGen runtime; measure latency before claiming demo readiness.
- Preset TTS first; custom voice requires user's reference recording later.
- Initial UI is push-to-talk, not full duplex.
- Browser credential creation requires user handoff; prepare all other work first.

Progress
- Gateway10newtests and full103-test suite passed; separate review found no important defect.
- Audio10contract tests passed; model download/load running.
- ServiceNow assistant SCC Local Voice c623a20f93374354e7f2b9fa6aba10fd created in prior turn. Its own NLQ and response streaming disabled to isolate functioning existing skills. Native preview previouslyblocked by gateway429.
- Bridge implementation delegated; outbound auth/config remains pending.

Live verification
- Queued gateway8841: unauth health/models401, authorized200. Exactly2concurrent real prompts succeeded200/200 in0.267/0.415s. Observed active1queued1 then0/0. Stop/start verified; currentlistenerPID1320.
- Existing Tailscale Funnel root switched from8840 to8841 after tests, preserving hostname/token/upstream. Rollback: tailscale funnel --bg --yes http://127.0.0.1:8840.
- ServiceNow native SCC assistant retest submitted19:25UTC: asksHRhelp, explicitly says do not create a case. Awaiting result.
- ServiceNow account linking already enabled on standard VA Bot to Bot Provider. Native AI Voice messageauth belongs nativeprovider and is not reused.
- Created preparation-only voice/servicenow-setup.js; NOT executed. Requires user-created credential names, writes inactive channel/outbound/connection.
- Start-Voice.ps1 status path executed successfully; configurecredentials requires manual user input and protects E:\SCC-Voice\secrets ACL.

Update 2026-10-12 19:45 UTC
- Both 0.6B speech models installed and running on native Windows, isolated Python3.12 environments, cache E:\SCC-Voice\models. Authenticated loopback only.
- CPU BF16 TTS verified on this machine: German sample synthesis 6.864/8.361s, exact ASR roundtrip 1.667/2.088s, ~25GiB free RAM. Live bridge audio-only sample also passed (6.77s TTS,1.50s ASR).
- Audio12 contract tests, bridge17 integration tests, gateway103 tests passed. Review found secure-output, UI reset race, exact choice-value, process quoting and credential ACL issues; all fixed with regression coverage. Lifecycle2 checks passed. Windows E: ACL applied via .NET setter because PowerShell Set-Acl requested unavailable SeSecurityPrivilege.
- ServiceNow native NAVA planner now succeeds on HaloGen after queue fix. Targeted HR voice-agent selection succeeded but execution failed Invalid dynamic Topic Block name: voice agent uses Voice strategy with empty strategyTopic in the chat execution path. No standard runtime script changed.
- Creating a separate normal Chat agent through AI Agent Studio, reusing existing HR tools, leaving original voice agent intact. Draft id e850ba4f933b4354e7f2b9fa6aba105d; tool association/security setup pending.
- ServiceNow Bot credentials have NOT been created. Bridge service_now_enabled=false. Full voice-to-ServiceNow dialog remains unverified until user enters dedicated credentials and selects a permitted demo identity. Native Voice enum remains unresolved by design; this is a separate standard BotAPI channel.

- Chat agent HR case creator SCC Local Voice created through Studio: e850ba4f933b4354e7f2b9fa6aba105d, internal, ReAct strategy f0bff21f9f13c6108f431597d90a1c74. Studio created config active=1 by default; immediately set config 2fa13ec3937b4354e7f2b9fa6aba1068 inactive before attaching tools.
- Five standard sn_aia_agent_tool_m2m bindings copied (same existing tools, all inactive) to preserve RAG search-profile and CRUD input configuration exactly. New binding IDs 9842fa47937b4354e7f2b9fa6aba10f6,14427687937b4354e7f2b9fa6aba10bf,98427687937b4354e7f2b9fa6aba10c0,10427687937b4354e7f2b9fa6aba10c2,18427687937b4354e7f2b9fa6aba10c3. Rollback context cc42fa47937b4354e7f2b9fa6aba10f1. User confirmation and demo identity required before activation/access/channel enablement. No HR case created.
- Existing User Criteria Access tool appears to pass mtom row IDs to UserCriteriaLoader, not referenced user-criteria IDs; preserve original shared tool, flag for targeted verification before demo. This may deny access rather than grant it; do not bypass.


## Current update 2026-10-12 (supersedes earlier pending/inactive states)
- User completed credentials and Studio security setup, supplied identity marcel.kaefke@soprasteria.com, and explicitly approved activation/Funnel callback exposure.
- Assistant and context profile active; normal Chat agent config and all five bindings active. Designer asset changed from original voice-only agent to normal Chat agent. Native preview selects the new agent and displays its first HR question. No HR case created; multi-turn not yet established.
- Standard Bot records created: message auth a80af60f93fb4354e7f2b9fa6aba107b; provider application 200af60f93fb4354e7f2b9fa6aba107d; alias 600af60f93fb4354e7f2b9fa6aba107f; HTTP connection 680af60f93fb4354e7f2b9fa6aba1081; outbound e40af60f93fb4354e7f2b9fa6aba10ff; deployment channel a40a3a0f93fb4354e7f2b9fa6aba1001. Setup rollback context e00af60f93fb4354e7f2b9fa6aba1079.
- Inbound token credential 6882f6c7937b4354e7f2b9fa6aba105e; callback Basic credential 5782fac7937b4354e7f2b9fa6aba10ea. Values never read/exported. User-configured callback username is the email; local configuration corrected to match.
- Funnel /scc-voice -> 8853 added, root / -> 8841 preserved. Public callback path tested: 401 unauthenticated, 200 with configured local Basic credentials.
- Bridge service_now_enabled=true. Real standard BotAPI START acknowledged202 and creates a conversation. Real callback rejected401: diagnostic booleans username_match=True, password_match=False. This is a credential mismatch, not a missing network route. No auth weakening; provide user-only hidden-password repair helper.
- ServiceNow smoke timed out visibly at180s and reset successfully. Full voice end-to-end remains unverified.
- Configure-Voice.ps1 preserves callback username; Update-CallbackCredential.ps1 writes only the existing protected local callback secret after user input. Both parse successfully in Windows PowerShell. Bridge17 tests passed after diagnostic addition.

Latest native follow-up: second user message was accepted, then the conversation ended without an answer. This is an additional unresolved dialogue issue, independent of the callback password. Conversation ID 69dd7ecf933f4354e7f2b9fa6aba1035; input collector called capability aca5634f4312121038520464dbb8f236. User language in the runtime was en. No case was created. Investigate response-generation result and task completion before claiming multi-turn success.
