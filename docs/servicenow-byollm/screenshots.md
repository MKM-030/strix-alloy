# Screenshot plan for the ServiceNow BYOLLM overview

Capture these seven images manually after reviewing the article. The numbered insertion markers in `community-post.md` identify their placement. The captures are still pending; this checklist does not record successful runtime tests or configuration writes.

Use the UI labels present on the tested release. Record the release and relevant app versions in the publishing notes. Replace names with neutral examples where practical. Keep field labels, provider/model relationships, selected values, and useful status messages readable. Avoid full-desktop captures when a focused application panel explains the step.

| No. | Suggested filename | What to capture | Suggested caption |
| --- | --- | --- | --- |
| 1 | `01-provider-policy.png` | AI Control Tower's AI model providers edit view: Custom LLM Provider as the only allowed provider, fallback unchecked, and the routing value visible. Include the impact panel if it fits legibly. Do not change settings just to obtain the image. | Provider policy is one configuration layer. The selected providers, fallback setting, and affected systems need a separate review. |
| 2 | `02-custom-model.png` | The registered custom model with its provider, connection/credential alias, and associated request/response transformers. Use the guided model view or equivalent record form available on the instance. | The custom model connects a provider and credential alias to the endpoint's request and response contract. |
| 3 | `03-custom-provider-prompts.png` | Custom LLM Provider → Prompts, or the equivalent view, filtered to a small reviewed skill set. Show the target model, prompt identity, default status, and usage conditions where available. | Each eligible target skill needs a compatible custom-provider prompt and an intentional selection rule. |
| 4 | `04-provider-defaults.png` | Now Assist Admin's provider management view showing instance selection and a scoped skill or group override, with the affected-skill summary. If the custom provider is unavailable in that selector, show and explain that limit. | Instance defaults and scoped overrides must be checked against the providers each capability supports. |
| 5 | `05-ai-agent-group.png` | The AI Agent Skills / AI agents group default and its affected capabilities or supported-provider choices. Preserve the version's actual group label. | An agent-group default does not demonstrate that an arbitrary custom LLM is supported by the orchestration engine. |
| 6 | `06-skill-test.png` | A controlled skill test with harmless input, the selected model where displayed, and a readable response. A short synthetic incident is suitable. | A controlled test checks the prompt and returned output for this skill; the deployed entry point requires its own test. |
| 7 | `07-runtime-evidence.png` | A log or metadata view for an actual controlled invocation, showing capability/prompt configuration, model identity, status, and enough timing context to correlate it with endpoint-side evidence. Capture only after that invocation has been verified. | Runtime evidence links the invocation to its model configuration and result. Correlate it with the receiving endpoint before claiming the route is verified. |

## Redaction before publication

- Remove instance hostnames and URLs, user names, email addresses, avatars, record identifiers, browser profiles, bookmarks, and unrelated tabs.
- Conceal API keys, authorization headers, tokens, credential values, connection URLs containing secrets, and query parameters with sensitive data. Retain only neutral alias names and labels needed to explain the setup.
- Use synthetic record data. Remove customer text, personal data, confidential prompts, tool payloads, internal hostnames, and unrelated log rows.
- Crop identifiers from record URLs and related-list columns. Do not display session information or developer-tools network headers.
- Do not publish internal performance numbers. Any future performance claim needs a separately defined test method and results.
- Apply opaque redactions to the final exported image, then reopen it to confirm that hidden material cannot be read. Recheck the image at its intended article size.

## Capture-specific checks

For screenshot 1, the authenticated form observation on 27 October 2026 exposed `sys_gen_ai_routing_selection.selected_providers`, `sys_gen_ai_routing_selection.fallback`, and `sys_gen_ai_routing_selection.selected_routing`. The observed values were Custom LLM Provider only, false, and Global. This was a read-only configuration observation, not a write or proof that every processing path uses a custom endpoint. Do not copy private field values or identifiers into the image.

For screenshot 2, do not squeeze several wizard steps into unreadable text. Prefer the final configuration summary. If transformer code must be illustrated, use a small neutral request/response example in the article's explanation; omit credentials and proprietary prompts.

For screenshot 3, show selected coverage honestly. A list of prompts is not proof that all skills are eligible or tested. The companion prompt-mirroring automation is disabled by default and must remain disabled until qualified for the target instance. This describes the intended default, not a fresh live-state check. Do not activate it for a screenshot. A preview, if later captured, must be explicitly labelled as proposed changes.

For screenshots 4 and 5, retain any visible unsupported-capability or failed-update information relevant to the explanation. Avoid captions suggesting that a global selection overrides feature eligibility.

For screenshots 6 and 7, use the same harmless test scenario and preserve a private correlation note outside the published images. If runtime verification is still pending, keep the insertion markers; do not substitute a configuration screen for execution evidence.

AI Agent customization and AI Voice captures belong in their planned follow-up articles. No phone call, audio playback, STT/TTS test, or caller-data capture is required for this overview.

## Final publishing pass

Confirm that all seven images match their markers, captions explain the visible evidence, and every public image has been checked after redaction. Remove the insertion markers only when the final images are inserted. Keep the two follow-up links labelled as planned until their publication destinations exist. Recheck current documentation and the tested release before publishing.
