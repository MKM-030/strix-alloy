# ServiceNow AI Voice and BYOLLM: Separate the Model, Speech, and Channel Layers

A voice assistant connects several systems: audio transport, speech recognition, language-model processing, business tools, and speech synthesis. A successful text response proves only part of that path. Introducing a custom model therefore starts with identifying which stage is being changed and which stages retain their existing services.

**ServiceNow supports custom LLM and voice configurations only partially.** The available provider and channel options depend on release, applications, entitlements, and integration type. Custom work requires technical knowledge of APIs, authentication, WebRTC or telephony, speech formats, model contracts, and platform permissions. A generic text connector is not an official approval for an arbitrary custom voice pipeline.

This article explains the project's integration approach and the checks needed to qualify it. Earlier device observations remain tied to their tested versions; they do not establish complete current phone, model, or parallel-agent acceptance. Read the companion [platform overview](./community-post.md), [AI Agent article](./ai-agents-follow-up.md), and [master manual](./master-manual.md) for the related configuration.

## 1. Map one utterance through the complete path

The standard voice-assistant model combines STT, an LLM, and TTS. The [assistant configuration documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/create-an-ai-voice-service.html) explains voice personas, languages, channels, agents, caller controls, and fallback.

For a customer-developed media route, make the stages explicit:

    Caller / browser / mobile client
        → communication channel and media adapter
        → speech-to-text
        → ServiceNow dialogue, agent, and skill processing
        → selected model endpoint and business tools
        → response text and text-to-speech
        → audio delivery to the caller

Record the owner, input/output format, identity, and failure behavior at each boundary. In the project's local-speech approach, the host speech engines are separate from the phone's system speech services. The media adapter carries the interaction; ServiceNow retains the intended business execution path.

The [AI Voice deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) lists supported providers and communication options. It does not establish arbitrary Custom LLM Provider compatibility. Keep the documented native route and any project-specific extension clearly identified.

[Voice Screenshot 1: Voice assistant, associated agents, language, and voice]

## 2. Configure the assistant and identities deliberately

Start with one assistant and a small scenario, such as checking a synthetic incident's status. Record the release, app versions, assistant, associated agents, tools, language, and intended channel. Configure the relevant welcome message, voice persona, caller verification, fallback, and call constraints through the native controls available on that version.

A voice persona is not necessarily the local TTS engine or model. Likewise, permission to open a native voice session does not automatically establish the identity under which every downstream tool executes. In the custom integration, native SDK admission and the bot integration's platform identity are separate boundaries.

Document that distinction and test the actual user and tool permissions. Preserve normal access controls. An authenticated channel connection must not be treated as blanket authorization for every record operation.

[Voice Screenshot 2: Communication channel, caller verification, and fallback]

Keep ACT policy separate from assistant setup. Review allowed providers, fallback, and required asset approvals using [ServiceNow AI settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html). A custom-only allowlist does not demonstrate where speech, search, guardrails, or telephony processing occurs. Establish each service's processing route independently.

## 3. Choose the LLM route independently of speech

Register the intended model and its connection through [Providers and Models](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html). Check model identity, credentials, endpoint reachability, request settings, and response transformation. The [generic connector documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-generic-llm-connector.html) defines a text-generation integration; its scope does not qualify audio transport or speech replacement.

Select the concrete model at the actual skill prompt and review conditions and defaults through [prompt settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html). The immediate dialogue, agent orchestration, and a tool skill can be different model roles. Changing one prompt does not establish a universal switch across them.

The historical **CustomLLMPromptMirror** implementation can prepare additional provider-specific configuration beneath an existing skill/capability. It retains the skill identity while copying or remapping supporting definitions, prompts, and bindings. Native generators create protected child relationships. This differs from cloning a skill and remains customer customization with target-specific contracts.

Its eight BR callers and manual backfill do not configure STT, TTS, media, or voice orchestration. Keep automation/application/serialization gates off until qualification. Use the [prompt-mirror guide](./prompt-mirror.md) for selected previews, dependencies, and model-template settings.

[Voice Screenshot 3: Actual prompt/model and separate speech-service configuration]

## 4. Diagnose media startup and turn boundaries in order

For a WebRTC route, trace session creation, offer/answer exchange, ICE connectivity, data-channel state, incoming audio, generated output, and playback. A ready model server cannot explain a failure that occurs before media negotiation completes.

One inspected iOS SDK contract required HTTP 200 for session creation; a 201 response stopped that historical flow before the offer. The repair concerned the examined contract, not a universal rule for every SDK. Preserve the expected nested response structure and check the version actually installed rather than applying broad format changes.

Speech endpointing also needs a precise contract. In the recorded Android path, DTX could stop further audio packets after speech. Waiting only for later silent PCM blocks could therefore stall a turn. The implementation also considered elapsed time since the last detected speech input.

Bound input and processing queues and define overflow behavior. Interruption of spoken output must not automatically resubmit an already accepted backend action. On input loss or a new call, track the outstanding work until its outcome is known instead of releasing capacity prematurely.

These are integration lessons to reproduce on the target, not claims that the repaired combined system has passed a current device matrix.

## 5. Preserve context, confirmation, and business meaning

A spoken greeting should agree with the context given to the dialogue and agent. Verify the greeting, selected business agent, subsequent input, and any correction as one conversation. An early audible greeting alone does not show that the planner received the same information.

The project's caller-context helper carries supplementary notes and can acknowledge their inclusion in a returned prompt. That acknowledgment is not understanding, approval, or successful execution. A corrected name must remain a corrected input, not permission to place an order.

Preserve required confirmation, identity checks, action schemas, and validators. Render only recognized result envelopes into speech; stripping arbitrary JSON punctuation can change meaning or hide an error. Unknown or malformed structures need a controlled response rather than an invented success message.

The recorded helper expects a single matching active plan per conversation. Its configuration does not establish a general scheduler for several simultaneous plans. Retain that constraint until a separately reviewed implementation replaces it.

## 6. Separate responsiveness from parallel execution

A fast conversational model, a planner, and a specialist tool may need different resources. A model list or prompt assignment does not establish independent queues, sufficient host capacity, or delivery of delayed results to the right conversation.

Earlier bridge snapshots selected one backend and correlated output with the latest dialogue request. Those observations are dated. The project has also prepared a separate responsive-conversation runtime, whose source documentation keeps independent qualification and activation open. Pure source or ownership checks do not demonstrate live coexistence or audible phone behavior.

For background work, bind each job to its conversation, originating turn, model, and authorized operation. Define how later results are presented after the caller has continued, disconnected, or corrected the request. Handle duplicate and late callbacks without repeating business effects. Keep spoken delivery separate from business completion.

Stopping TTS or barging in does not cancel an operation already submitted to ServiceNow. Establish the operation's outcome before retrying. Full parallel multimodel acceptance remains separate from having these controls represented in source.

## 7. Measure each stage without overstating the result

Use distinct timestamps for speech ending, transcription completion, ServiceNow submission, model response, first synthesized audio, and actual playback. Measure the route exercised rather than combining unrelated component intervals into an end-to-end figure.

A synthetic TTS-to-ASR roundtrip can validate a limited speech-component contract. It cannot establish microphone recognition, accent/noise performance, interruption handling, network behavior, or phone audibility. Similarly, accepted PCM bytes and a generated TTS chunk do not prove that a caller heard the response.

[Voice Screenshot 4: Controlled session timeline and clearly identified test channel]

Evaluate the actual spoken result as well as the transcript. Check corrections, missing information, silence, interruption, hangup, and a subsequent call. Keep internal timings, customer audio, personal voices, raw prompts, and transcripts out of public screenshots. Any performance comparison needs comparable conditions and a defined measurement method.

## 8. Install and accept the target in separate stages

For a fresh instance, use the **Fresh Instance NO-DELETE** delivery identified by the current installation guide and manifest. Native metadata transport and host deployment have separate prerequisites. Review app versions, entitlements, native APIs, parent configurations, validators, and assistant bindings before preview/import.

Configure target-local endpoints, credentials, ACT policy, mirror settings, bot/assistant relationships, speech services, TLS, signaling, and media reachability. A model or alias name does not establish those resources. Keep source examples and personal voice assets out of a generic deployment.

Document acceptance in three stages: authenticated backend/model behavior; platform prompt/tool/permission behavior; then the actual device or telephony journey. Test unavailable services and the configured fallback or handoff. Preserve the distinction between browser text testing, browser audio, mobile audio, and a real phone integration.

[Voice Screenshot 5: Sanitized transcript, correlated execution, and checked outcome]

A successful mapping repair or source capture does not establish post-repair Voice, Vision, or parallel-agent acceptance. Publish the evidence for the specific tested route and retain the remaining limits. The resulting architecture is understandable and reviewable even while some combinations remain unsupported or untested.
