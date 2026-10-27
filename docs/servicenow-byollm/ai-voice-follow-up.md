# Planned article brief: AI Voice, LLM routing, STT, and TTS

**Status: planning brief, not a published article or an audio validation report.** No phone call, voice quality result, custom-model compatibility, or complete voice migration is established by this document.

Working title: **ServiceNow AI Voice and BYOLLM: Separate the LLM, Speech, and Telephony Layers**

## Scope

Explain the voice path as separate speech-to-text (STT), LLM, text-to-speech (TTS), and communication-channel stages. Cover the voice assistant, associated agents and tools, caller verification, fallback, and the evidence needed for each layer.

The [voice-assistant procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/create-an-ai-voice-service.html) describes STT, LLM, TTS, languages, voice personas, channels, and caller controls. The [deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) names supported providers. It does not establish compatibility with any arbitrary Custom LLM Provider. A custom text endpoint must not be presented as a replacement for the entire voice pipeline.

## Planned structure

1. Diagram one utterance from the communication channel through STT, LLM/tool execution, and TTS.
2. Identify what provider policy and LLM configuration can affect, and what remains a speech or channel setting.
3. Describe the supported setup for the tested release and explicitly identify any custom or unsupported route.
4. Present a controlled voice scenario only after separate end-to-end validation.
5. Report evidence, failures, fallback behavior, remaining limitations, and portability requirements.

## Evidence required before writing the finished article

- Record the release, patch, installed apps, entitlements, voice assistant/agent configuration, and communication channel used.
- Confirm the documented supported LLM path. Record policy, fallback, model approval, selected model, and any relevant prompt or orchestration configuration without assuming that chat-agent settings apply identically.
- Establish the STT and TTS services separately from the LLM endpoint. Identify where audio and text are processed using applicable documentation and approved configuration evidence.
- Collect correlated evidence for transcription, LLM response, tool execution, speech output, caller verification, and the final business outcome. A text-only test covers only part of the path.
- Test the intended fallback or handoff and an unavailable-service case. Distinguish configuration inspection, text testing, browser voice testing, and an actual telephony session in the results.
- Define an evaluation method before making latency or quality claims. Use synthetic data and authorized test sessions; retain private correlation details outside public screenshots.
- Mark each layer verified, unsupported, or untested. Complete required reviews and verify the target environment again after transport.

These are prerequisites for a future validation effort. They do not authorize or request a call, audio playback, recording, runtime change, or model invocation now.

## Proposed screenshots

| Image | Capture after verification | What it should establish |
| --- | --- | --- |
| 1 | Voice assistant language, voice persona, and associated agents | The scope of the configured assistant and its speech settings. |
| 2 | Communication-channel configuration with sensitive details concealed | Which channel is used and which integration must be validated. |
| 3 | Agent tools, caller verification, and fallback configuration | The relevant action and access boundaries. |
| 4 | Clearly labelled test result for the actual channel tested | Which portions of the user journey were exercised. |
| 5 | Sanitized transcript and correlated execution metadata | Evidence connecting transcription, model/tool behavior, and outcome. |

Keep capture instructions distinct from completed results. Conceal phone numbers, user identities, instance URLs, sys_ids, credentials, internal hosts, customer speech, and confidential transcript content. Do not publish internal performance figures or describe intelligibility, audio quality, authentication, or live-agent transfer as successful before those outcomes have been verified.

## Publication and link replacement

The overview's relative link points to this separate **planned follow-up**. Keep that status until a finished article is reviewed. When preparing a Community post while the follow-up is still unpublished, render its reference as plain planned-article text rather than a local Markdown hyperlink.

After the author publishes the finished article, use its actual canonical Community URL to replace the overview's relative link and remove the planned label. Check that the public URL opens the intended article and add a reciprocal link to the overview. Do not create a guessed publication URL or present this brief as a completed voice implementation guide.
