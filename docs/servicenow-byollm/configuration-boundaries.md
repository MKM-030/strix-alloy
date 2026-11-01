# ServiceNow BYOLLM configuration boundaries

Reviewed 28 October 2026. Use this with the [master manual](master-manual.md), [Community overview](community-post.md), [source register](sources.md), and [batch status](batch-status.md). Product labels and available controls vary with the platform release and installed Store application versions.

## Configuration responsibilities

| Layer | What it establishes | What still needs verification |
| --- | --- | --- |
| AI Control Tower | Allowed-provider policy and fallback. Formal model-asset approval is a separate Builder controls setting. | Impact on unsupported systems, required asset approval, and other processing controls. See [ServiceNow AI settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html). |
| Skill Kit: Providers and Models | Model registration, connection/credential alias, and request/response transformation. | Endpoint reachability and the actual request/response contract. See [Create a model](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html). |
| Skill Kit: skills and prompts | A compatible model and prompt for each eligible target skill, with deliberate default and usage conditions. | Required inputs, output schema, conditions, and deployment behavior. See [clone eligible ServiceNow skills](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html) and [configure a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html). |
| Now Assist Admin / AI Admin Hub | Instance, skill-group, and skill provider selections available for the capability. | Provider eligibility, regional availability, impact, and failed updates. See [Manage AI models](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/manage-large-language-models.html). |
| Calling experience | The configured route used by a record UI, flow, script, agent tool, or voice experience. | A controlled invocation and correlated ServiceNow/endpoint evidence for that entry point. |

Allowing Custom LLM Provider does not itself approve each model asset or establish the receiving endpoint for every invocation. With fallback disabled, active systems without allowed-provider support must be deactivated; inspect the [impact summary and support matrix](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/ai-model-providers.html). An allowlist is not evidence that every cloud call has stopped. Data sharing, overflow processing, guardrails, search, tools, speech services, and telephony require their own assessment.

## Selection and activation

Set the instance provider first, then apply intended skill/group customizations. Those customizations override the instance choice, but a **later instance-level provider update overwrites existing skill/group customizations**. Recheck scoped selections after any broad change. This precedence and the impact review are documented in [Manage model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html).

Model registration does not generate a compatible prompt for every capability. The documented authoring path finalizes prompts, publishes skills and activates them in Admin Hub; see [publish a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html) and [activate a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html). The separate [custom existing-skill path](prompt-mirror.md) retains the skill/capability identity and adds a provider-specific graph. Its native generators, lifecycle and deployed route need release-specific verification. Required approvals, permissions and validators remain applicable to both paths.

The documented model-management feature begins with Admin version 6.2 and Yokohama Patch 6. Relevant roles include `sn_ai_governance.ai_steward`, `sn_skill_builder.admin`, `sn_skill_builder.sb_model_admin`, and the applicable Admin roles. Verify task-specific permissions in the linked release documentation; authoring and activating are separate responsibilities.

The installed `CustomLLMPromptMirror` serves eight Business Rules and a manual Fix Script. The helper and three false execution gates were read on 28 October; its code matches the final Validation 1.0.1 revision. Keep the gates false until the target instance is qualified. A selected-capability or all-eligible dry run needs reviewed coverage, safe repeated execution and protection for deliberate edits. `custom_llm.prompt_mirror.default_model` supplies an administrative copy template; it does not select the active provider or the concrete model of every prompt. See the [operation and evidence limits](prompt-mirror.md).

## Technical inspection ledger

These are observations from the examined configuration and preserved source documentation. They are version-dependent inspection clues, not a public SDK or universal database contract.

| Table / field | Recorded boundary |
| --- | --- |
| `sys_gen_ai_routing_selection.selected_providers` | The 27 and 28 October native observations showed Custom LLM Provider only; the actual policy row is absent from the exported batch and must be configured on the target. |
| `sys_gen_ai_routing_selection.fallback` | The observed field was `fallback`, with value false. Do not substitute an assumed field name. |
| `sys_gen_ai_routing_selection.selected_routing` | The observed display value was Global. This does not prove local-only processing. |
| `sys_gen_ai_provider.integration_type` | Inspect the installed dictionary and supported integration UI. Do not infer model eligibility from this field alone. |
| `sys_gen_ai_control_setting_data` | The two captured versions concern the Gen AI metadata-updated flag, both true. They do not transport the ACT provider allowlist, fallback or routing-region policy. |
| `sys_generative_ai_provider_mapping` | Inspect the relevant mapping, including Active and External Visibility, against the native UI and capability graph. Matching display names are insufficient. |
| `sys_generative_ai_model_config.provider` | Preserved examination identified the actual provider-mapping reference as the model membership relationship. Confirm it on the target release. |
| Mapping `model_configs` | Earlier examination found it unreliable as an inventory source: it can be empty or stale. Public documentation reviewed here does not establish a universal deprecation contract. |

Use supported product controls for policy and routing changes. The official [generic connector procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-generic-llm-connector.html) does document form-based model, prompt, and transformer records for that connector. This is not authority for arbitrary routing-table patches, direct SQL, global provider replacement, or deletion of original prompt graphs.

## Agents, voice, and transport

The AI Agent Skills / AI agents group deserves its own review. The official [agent provider selection](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) documents named providers, global agent/workflow selection, affected-agent review, and retesting. A custom-model skill used as a tool does not establish that an arbitrary BYOLLM is supported as the agent's orchestration model. See the [AI Agents follow-up](ai-agents-follow-up.md).

Voice adds speech recognition, synthesis, assistant settings, authentication, and a media/telephony path. The generic connector's text-generation support does not qualify those stages. Use the [AI Voice follow-up](ai-voice-follow-up.md) for that separate work; the [voice deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) defines its product-specific choices.

Update sets transport captured ServiceNow metadata. They do not supply model weights, host services, credentials, or compatible product entitlements. A completed source batch does not establish successful target preview/import or runtime acceptance. The 19 October baseline and the 28 October completed 2.1 candidate have distinct evidence and release status, recorded in [batch status](batch-status.md).
