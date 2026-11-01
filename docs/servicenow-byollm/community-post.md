# ServiceNow BYOLLM: A Practical Guide to Custom LLM Providers

Connecting an LLM endpoint is one part of a ServiceNow BYOLLM setup. A usable configuration also needs provider policy, model registration, compatible prompts, defaults, and evidence of where requests actually ran.

**ServiceNow supports custom LLMs only partially.** Available routes depend on the release, installed applications, and individual capability. Technical knowledge of APIs, authentication, JavaScript transformations, and ServiceNow configuration is needed. This approach does not promise that every Now Assist feature, AI Agent, or voice interaction can use an arbitrary model. ServiceNow's [external LLM support guide](https://www.servicenow.com/community/servicenow-otto-articles/using-external-llms-with-now-assist-including-byok-byollm/ta-p/3218103) distinguishes those cases.

The following method brings the platform configuration layers together, including a customer-developed way to add provider configurations to existing skills without creating skill clones. It does not claim a completed platform-wide migration. This draft consolidates documentation reviewed on 27–28 October 2026; the policy observation below is dated 27 October. Check the documentation for your release. The companion [English master manual](./master-manual.md) and [prompt-mirror implementation guide](./prompt-mirror.md) provide the detailed procedures and evidence boundaries.

## Start with the right connection type

| Option | What you configure |
| --- | --- |
| ServiceNow-managed model | A supported provider delivered through ServiceNow's managed connection. |
| Bring Your Own Key (BYOK) | Your account and credentials for a supported provider integration. |
| Bring Your Own LLM (BYOLLM) | A custom endpoint and the request/response contract needed to integrate it. |

An OpenAI-compatible endpoint can reduce transformation work, but compatibility must cover the actual payload and response, not just the URL. Keep a small sample request and expected response as your integration contract.

Before making changes, inventory the use cases you intend to move: custom skills, eligible ServiceNow skills, flows, agent tools, orchestration, and voice. Record their current provider and activation state. Confirm the required entitlements and installed app versions, assign the appropriate governance and builder roles, and check that the instance can reach the endpoint. Start with a development or test environment and retain the existing configuration for rollback. This inventory becomes the boundary of the work: a skill absent from it has not been assessed simply because an instance setting was changed.

## 1. Set the provider policy in AI Control Tower

Open **AI Control Tower → Settings → ServiceNow AI → AI model providers**. Review the impact summary before editing. For a custom-provider-only policy, allow **Custom LLM Provider**, deselect the other providers, and disable fallback. Keep a valid allowed provider selected. ServiceNow documents allowed providers, fallback, and the affected-system view in [Configure ServiceNow AI settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html).

With fallback enabled, an affected system can retain its previous provider. With fallback disabled, active AI systems unsupported by the allowed providers must be deactivated. Inspect the support matrix and review the impact before saving. The [provider overview](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/ai-model-providers.html) also explains routing and audit history.

Compare the affected-system list with your inventory. Decide which unsupported systems will remain inactive and communicate that outcome to their owners. Do not enable another provider as an unnoticed workaround. After saving an authorized policy change, reopen the settings and inspect the resulting state rather than relying only on the confirmation message.

The provider allowlist and formal model-asset approval are separate controls. Complete the required asset approval workflow as well; selecting a provider does not approve every model or skill that uses it.

The inspected instance showed only Custom LLM Provider selected, fallback unchecked, and routing set to Global. No routing write was performed for this article. Global is a routing setting, not proof that cloud processing is disabled. Check other data controls and feature-specific processing separately.

**Advanced inspection tip:** the observed form used `sys_gen_ai_routing_selection.selected_providers`, `sys_gen_ai_routing_selection.fallback`, and `sys_gen_ai_routing_selection.selected_routing`. These are instance observations, not a stable API contract. Use the supported UI and verify the dictionary before any diagnostic scripting.

[Screenshot 1: Provider policy and fallback]

## 2. Register the custom provider and model

In **Now Assist Skill Kit / AI Skill Kit → Providers and Models**, use **Add model** where available. Select the custom provider, identify the model, configure its connection and credentials, and associate the transformers. The official [Create a model procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html) covers that workflow.

ServiceNow's employee guide associates guided setup with Zurich Patch 4 and Skill Kit 7.0.0. That is dated rollout guidance, not a universal prerequisite for every installation. The [Zurich Skill Kit release notes](https://www.servicenow.com/docs/r/zurich/release-notes/now-assist-skill-kit-rn.html) describe the corresponding custom-model enhancements.

For installations using the generic connector, follow the separate [credential configuration procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-api-credentials-for-a-generic-large-language-model-llm.html). Use a credential record and connection alias instead of placing secrets in scripts.

Define what your endpoint accepts: model identifier, messages or prompt, token settings, and any required headers. Define what it returns: generated text, errors, and expected structured content. Implement request and response transformations accordingly. The [generic connector documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-generic-llm-connector.html) provides the underlying pattern and limits this controller route to text generation.

Test that contract before introducing business prompts. Check a normal answer, an empty result, and a provider error. The response transformer must extract the expected text and handle failures explicitly; an HTTP success with an unexpected payload is not a successful skill response. Keep endpoint-specific parsing in the transformer so prompts can stay focused on the business task.

For advanced inspection, check the model's provider reference in `sys_generative_ai_model_config` and the relevant provider mappings in `sys_generative_ai_provider_mapping`. These table names are inspection clues from the examined configuration, not a version-independent integration contract. Confirm their relationships on your instance; a matching display name alone is insufficient.

[Screenshot 2: Custom model, connection alias, and transformers]

## 3. Add provider prompts to existing skills, or use the documented clone workflow

A registered model does not create compatible prompts for every skill. ServiceNow documents [creating custom skills](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-new-skill.html) and [cloning eligible ServiceNow skills](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html). Those UI workflows remain separate from the customer customization described here.

The historical installed implementation uses a Script Include named **CustomLLMPromptMirror**, eight narrow after-insert/update Business Rules, and the **Custom LLM - Synchronize prompts** Fix Script. It retains the existing skill/capability and adds a Custom-LLM provider-specific configuration graph alongside the original provider graph. **No skill clone does not mean no configuration copying:** provider-specific definitions, prompts, bindings, and relevant relationships still need to be created or remapped.

The earlier [final capability-based manual copier](./capability-prompt-copy.md) is also preserved separately. Its recorded repeat run covered 14 capabilities with zero writes, 292 unchanged records and 13 existing validator relations. The final correction excluded the computed `request_tokens` field from both copying and change detection. That source has no dry-run switch and can change defaults; it is historical implementation evidence, not a universal installation script or the later Mirror.

The implementation preserves shared capability inputs and existing validator implementations. Native after-insert generators create the DefinitionConfig and PromptBinding child records after their parents are inserted. The mirror reads and verifies those generated relationships instead of manually copying protected child references. This is version-dependent customer code, not an additional officially documented cloning mode. Its target instance must satisfy the recorded dictionary, generator, permission, and dependency contracts.

[Screenshot 3: Existing skill and additional provider-specific prompt graph]

For the initial or later backfill, the Fix Script calls the same service as the BRs. Its recorded preview controls are `APPLY=false` and `CAPABILITY_IDS=[]`. An empty selection discovers all eligible existing capability variants; supply an explicit selection to start narrowly. Review the plan for identities, dependencies, model, defaults, conditions, and conflicts before considering application. Eligible means compatible with the reviewed custom contract, not every platform skill.

Keep `custom_llm.prompt_mirror.automation_enabled`, `custom_llm.prompt_mirror.apply_enabled`, and `custom_llm.prompt_mirror.serialized_execution_verified` false until target qualification. These are separate gates; enabling a flag does not prove serialization or compatibility. `custom_llm.prompt_mirror.default_model` supplies an administrative model template for new provider configurations. It does not select the active skill provider or override every prompt's model. Follow the [prompt-mirror guide](./prompt-mirror.md) for the qualification sequence.

Require repeated unchanged runs to avoid duplicate graphs and unnecessary updates. Preserve deliberate target edits, report ambiguous relationships as conflicts, and retain the original provider graph. The mirror must not silently switch ACT policy, Admin defaults, deployments, or skill activation. Do not bulk-delete original prompts or disable validators to force compatibility.

[Screenshot 4: Disabled automation and selected-skill backfill preview]

Under **Custom LLM Provider → Prompts**, or its version-specific equivalent, check the concrete prompt's model, inputs, conditions, output schema, and default status. The [prompt settings procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html) explains the authoring controls. Test matching and nonmatching conditions, required output keys, and validator behavior; a readable answer can still break its caller's contract.

For authoring workflows that require publication, [finalize the tested prompt and publish the skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html), then have an administrator [activate it through AI Admin Hub](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html). Complete required review and approval. For the same-skill custom graph, preserve existing deployment state and verify its actual selection lifecycle; creating configuration records is not permission to activate the product automatically.

## 4. Align instance, skill-group, and skill defaults

Open **Now Assist Admin → Settings → Manage AI models → Manage model providers**, or its equivalent in your release. Inspect the instance default, then inspect skill-group and skill overrides. Supported choices depend on the capability and provider eligibility; a custom provider need not appear in every selector.

Apply changes at the intended scope and review the resulting impact and failures. ServiceNow's [Manage model providers procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html) explains how customization overrides the instance selection. A later instance-level provider change overwrites existing skill and skill-group customizations. Reapply only reviewed overrides and reverify the affected routes.

Also inspect the prompt that will actually be selected. Multiple prompts and usage conditions can change execution; see [Create a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-prompt-template.html). Separately built flows or scripts may use Generative AI Controller capability defaults. Those have their own [provider configuration procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-provider-for-a-generative-ai-capability.html). Review the relevant route instead of assuming one administrative default controls them all.

[Screenshot 5: Instance and scoped provider defaults]

## 5. Treat the AI Agent Skills group separately

Inspect the **AI Agent Skills / AI agents** group, using the label shown in your version. Its default is relevant to agent-related skill execution, but it does not establish that the agent orchestration engine accepts any custom provider.

The official [AI Agent provider selection procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) describes a global agent/workflow setting and lists Now LLM Service, AWS Claude, Azure OpenAI, and Google Gemini. It also requires retesting existing agents after a change and warns that some agents require specific providers.

The employee support guide excludes BYOLLM from its supported out-of-box and custom AI Agent configurations. A custom-model skill called as a tool is therefore a different claim from replacing the agent's own orchestration model. Any deeper customization needs separate support assessment and runtime evidence.

See [AI Agents and custom LLM routing — companion article draft](./ai-agents-follow-up.md).

## 6. Keep AI Voice's LLM and audio stages distinct

Voice assistants combine speech-to-text, an LLM, and text-to-speech; the [voice-assistant documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/create-an-ai-voice-service.html) describes those stages. Changing an LLM route does not replace the speech services or telephony integration.

The [AI Voice deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) lists supported LLM providers. It does not establish arbitrary Custom LLM Provider compatibility. A successful text response cannot demonstrate audio quality, caller authentication, tool execution, or live-agent transfer.

See [AI Voice: LLM routing, STT, and TTS — companion article draft](./ai-voice-follow-up.md).

## 7. Verify execution, then make the configuration portable

Run a harmless, identifiable test through the intended user experience. First verify the grounded prompt and response with [Test a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/test-prompt-template.html). Then repeat through the deployed entry point: an editor test and a production-facing invocation can follow different configuration paths.

[Screenshot 6: Controlled skill test and response]

Correlate the execution time and capability with available ServiceNow logs and endpoint-side evidence. Check model identity, prompt configuration, status, errors, and response shape. ServiceNow's [Generative AI Controller reference](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/reference-for-generative-ai-controller.html) identifies the request logs, metadata, and model-version mappings useful for this inspection. Model names are evidence to correlate, not a substitute for confirming the receiving endpoint.

[Screenshot 7: Runtime provider/model evidence]

Keep a coverage list with one result per entry point: verified, unsupported, or still untested. Include negative tests for unavailable endpoints and confirm the intended fallback behavior. Evaluate representative examples for output correctness and schema compliance before expanding coverage.

Historical installation, a successful resolver check, and a later mapping repair are different evidence. None alone establishes a successful post-repair skill invocation, complete agent orchestration, or voice acceptance.

For example, track incident summarization in its record UI separately from the same skill called by a flow. Record the expected route, observed route, result, and remaining issue for each. Check access using the intended user roles as well as the builder account. If a route fails, investigate policy, eligibility, prompt selection, and transformations in that order; changing several layers together makes the cause harder to establish.

For transport, capture supported configuration changes in a native update-set batch with children per application scope. Review dependencies and preview results on the target instance. Rebind environment-specific endpoints and credentials, recheck provider policy, and repeat runtime tests. Keep rollback information with the change record. Portable configuration becomes useful only when the target environment can reproduce the verified behavior.
