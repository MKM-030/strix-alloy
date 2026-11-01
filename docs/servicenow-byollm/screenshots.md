# Screenshot plan for the three ServiceNow BYOLLM articles

All **17 images are pending and author-provided**: seven for the platform overview, five for AI Agents, and five for AI Voice. The insertion markers in each complete article draft identify their placement. This checklist does not record completed captures, successful runtime tests, or configuration writes.

Use the UI labels present on the tested release. Record the release and relevant app versions in the publishing notes. Replace names with neutral examples where practical. Keep field labels, provider/model relationships, selected values, and useful status messages readable. Avoid full-desktop captures when a focused application panel explains the step.

## Platform overview: seven images

Article: [community-post.md](./community-post.md). Its markers are `Screenshot 1` through `Screenshot 7`.

| No. | Suggested filename | What to capture | Suggested caption |
| --- | --- | --- | --- |
| 1 | `01-provider-policy.png` | AI Control Tower's AI model providers edit view: Custom LLM Provider as the only allowed provider, fallback unchecked, and the routing value visible. Include the impact panel or a focused technical form detail with the observed table/field labels if legible. Do not change settings for the image. | Provider policy and fallback are distinct from model registration, prompt selection, and formal asset approval. |
| 2 | `02-custom-model.png` | The registered custom model with its actual provider-mapping relationship, connection/credential alias, and transformer association. Use the guided model view or equivalent record form. Avoid relying only on matching display names. | The model's provider relationship and connection define its technical membership and endpoint contract. |
| 3 | `03-existing-skill-provider-graph.png` | The existing skill/capability with the original provider configuration and the additional Custom-LLM provider-specific graph. Show prompt/model and binding relationships where readable. Use consistent neutral identity labels after redaction. | The original skill/capability is retained. Additional provider-specific definitions, prompts, and bindings are separate configuration records. |
| 4 | `04-mirror-preview-and-gates.png` | A focused view of the customer Fix Script's `APPLY=false` and explicit selected capability list, together with disabled automation/application/serialization gates or a clearly labelled read-only plan result. A legible composite is acceptable. Capture a plan only after an authorized preview; do not run a script solely for this checklist. | The backfill and eight BR callers share CustomLLMPromptMirror. Preview and disabled gates do not establish runtime qualification. |
| 5 | `05-provider-defaults.png` | Admin provider management with the instance selection and a scoped skill or group override, plus the affected-skill summary. Preserve unavailable choices or relevant failures. | Provider policy, scoped defaults, and a concrete prompt's model remain separate decisions. |
| 6 | `06-skill-test.png` | A controlled skill test with harmless input, the selected model where displayed, and a readable response. A short synthetic incident is suitable. | A controlled test checks the prompt and returned output for this skill; the deployed entry point requires its own test. |
| 7 | `07-runtime-evidence.png` | A log or metadata view for an actual controlled invocation, showing capability/prompt configuration, model identity, status, and enough timing context to correlate it with endpoint-side evidence. Capture only after that invocation has been verified. | Runtime evidence links the invocation to its model configuration and result. Correlate it with the receiving endpoint before claiming the route is verified. |

## AI Agents: five images

Article: [ai-agents-follow-up.md](./ai-agents-follow-up.md). This is a complete companion article draft; its markers are `Agent Screenshot 1` through `Agent Screenshot 5`.

| No. | Suggested filename | What to capture | Suggested caption |
| --- | --- | --- | --- |
| 1 | `agents-01-provider-and-impact.png` | The release's supported agent-provider menu, AI Agent Skills / AI agents group default, and affected-agent impact. Keep restrictions and unavailable options visible. | Agent orchestration uses its supported provider configuration; a custom skill's provider is a separate selection. |
| 2 | `agents-02-skill-and-tool.png` | An existing skill/capability with its additional custom-provider prompt/model and the corresponding agent tool configuration. Preserve relationships using consistent neutral identity labels. | The existing skill is retained while provider-specific configuration is added. Tool configuration does not select the orchestration model. |
| 3 | `agents-03-authority-and-result.png` | The tool's relevant permission/confirmation settings and, after a controlled scenario, the authoritative operation result. Use synthetic records and conceal identities. | Proposed, authorized, submitted, and confirmed outcomes must remain distinguishable. |
| 4 | `agents-04-execution-correlation.png` | Execution-plan/tool-request correlation and the actual background-route qualification state. If background work remains unqualified, show that state explicitly rather than a fabricated completed parallel trace. | Execution correlation and background qualification need their own evidence. A prepared source path is not a live concurrency result. |
| 5 | `agents-05-runtime-route.png` | Correlated orchestration/tool execution metadata, prompt/model identity, receiving-endpoint evidence, and the checked outcome for one harmless scenario. | The evidence applies to this tested entry point and tool route, not every agent or custom provider. |

The article makes no completed agent migration or parallel-runtime claim. Do not run an agent, enable mirroring, alter permissions, or submit a business action solely to fill a placeholder. If required runtime evidence is unavailable, retain the marker until the author has the appropriate verified result.

## AI Voice: five images

Article: [ai-voice-follow-up.md](./ai-voice-follow-up.md). This is a complete companion article draft; its markers are `Voice Screenshot 1` through `Voice Screenshot 5`.

| No. | Suggested filename | What to capture | Suggested caption |
| --- | --- | --- | --- |
| 1 | `voice-01-assistant-and-voice.png` | Voice assistant, associated agents, language, and voice-persona settings. Identify the actual release and channel without exposing customer data. | Assistant configuration describes the native experience; it does not by itself identify every external speech or model service. |
| 2 | `voice-02-channel-and-caller.png` | Communication-channel, caller-verification, and fallback settings, with numbers, endpoints, tokens, and identities concealed. | Channel admission, platform execution identity, and fallback are separate boundaries to validate. |
| 3 | `voice-03-model-and-speech.png` | The actual skill prompt/model and separately identified STT/TTS configuration. Use a legible composite if necessary, without credentials or personal voice-reference details. | The LLM route, speech recognition, and synthesis are configured and qualified separately. |
| 4 | `voice-04-session-timeline.png` | A sanitized real controlled-session timeline, clearly identifying browser text, browser audio, mobile audio, or telephony. Keep component timestamps separate. | This timeline identifies the channel and stages actually exercised. Component timing is not a phone-quality or end-to-end speedup claim. |
| 5 | `voice-05-transcript-and-outcome.png` | A synthetic-data transcript, correlated platform/tool execution, and checked final outcome. Any assertion of heard output or handoff needs the corresponding observation. | Transcript, model response, business completion, and audible delivery are distinct results. |

All Voice captures remain pending. No call, microphone capture, audio playback, service restart, model invocation, or device test is part of producing these documents. Do not reuse an old device screenshot as evidence of current post-repair acceptance, and do not replace unavailable audio evidence with a text-only result.

## Redaction before publication

- Remove instance hostnames and URLs, user names, email addresses, avatars, record identifiers, browser profiles, bookmarks, and unrelated tabs.
- Conceal API keys, authorization headers, tokens, credential values, connection URLs containing secrets, and query parameters with sensitive data. Retain only neutral alias names and labels needed to explain the setup.
- Use synthetic record data. Remove customer text, personal data, confidential prompts, tool payloads, internal hostnames, and unrelated log rows.
- Crop identifiers from record URLs and related-list columns. Do not display session information or developer-tools network headers.
- Do not publish internal performance numbers. Any future performance claim needs a separately defined test method and results.
- Apply opaque redactions to the final exported image, then reopen it to confirm that hidden material cannot be read. Recheck the image at its intended article size.

## Platform capture-specific checks

For screenshot 1, the authenticated form observation on 27 October 2026 exposed `sys_gen_ai_routing_selection.selected_providers`, `sys_gen_ai_routing_selection.fallback`, and `sys_gen_ai_routing_selection.selected_routing`. The observed values were Custom LLM Provider only, false, and Global. This was a read-only configuration observation, not a write or proof that every processing path uses a custom endpoint. Do not copy private field values or identifiers into the image.

For screenshot 2, do not squeeze several wizard steps into unreadable text. Prefer the final configuration summary or model record. If `sys_generative_ai_model_config.provider` or `sys_generative_ai_provider_mapping` is shown, label it as a relationship observed on the tested version. Do not present an empty or stale mapping inventory field as proof that no models exist. Omit credentials and proprietary transformer content.

For screenshot 3, distinguish the retained skill/capability from the new provider-specific records. Retain a private exact identity/revision comparison behind the public illustration; replace identifiers with consistent neutral labels in the image. A matching name alone does not establish that the original skill was retained. Native after-insert generation of DefinitionConfig and PromptBinding children belongs to the implementation explanation, not a claim that protected references were manually copied. A list of prompts is not proof of universal eligibility or successful execution.

For screenshot 4, the historical recorded mechanism consists of CustomLLMPromptMirror, eight BR callers, and a shared-service Fix Script. Do not conflate it with the later manager design or with the latest mapping repair. The template gates are `custom_llm.prompt_mirror.automation_enabled=false`, `custom_llm.prompt_mirror.apply_enabled=false`, and `custom_llm.prompt_mirror.serialized_execution_verified=false`. This checklist prescribes disabled defaults until target validation; it does not report a fresh live-state check. Do not enable gates or trigger backfill for an image. Label any preview as proposed changes, show `APPLY=false`, and prefer an explicit small selection over an empty all-eligible selection for the example. Conceal the actual capability identifiers.

For screenshot 5, retain visible unsupported-capability or failed-update information relevant to the explanation. Avoid captions suggesting that a global selection overrides feature eligibility. Note in the accompanying text that a later instance-level provider change overwrites existing skill/group customizations.

For screenshots 6 and 7, use the same harmless test scenario and preserve a private correlation note outside the published images. If runtime verification is still pending, keep the insertion markers; do not substitute a configuration screen for execution evidence.

The [master manual](./master-manual.md) and [prompt-mirror guide](./prompt-mirror.md) hold the detailed procedure and evidence requirements. Agent and Voice captures belong to their separate full article drafts above. Keep historical device evidence, source preparation, resolver checks, and current runtime acceptance labelled by their actual scope and date.

## Final publishing pass

Confirm that all 17 images match their article and marker, captions explain the visible evidence, and every public image has been checked after redaction. Remove each insertion marker only when its final image is inserted. There are exactly three complete English Community article drafts: platform overview, AI Agents, and AI Voice. They have not been published by this documentation work.

Before copying an article to Community, replace relative companion-article and manual links with their real public destinations. If a companion is not yet published, use plain text describing the complete draft as awaiting publication; do not create a guessed public URL. Recheck product documentation and the tested release. Installation references must identify the current Fresh Instance NO-DELETE delivery and its actual manifest, rather than presenting a historical source-candidate export as the fresh-target package.
