# ServiceNow BYOLLM: A Practical Guide to Custom LLM Providers

Connecting an LLM endpoint is one part of a ServiceNow BYOLLM setup. A usable configuration also needs provider policy, model registration, compatible prompts, defaults, and evidence of where requests actually ran.

**ServiceNow supports custom LLMs only partially.** Available routes depend on the release, installed applications, and individual capability. Technical knowledge of APIs, authentication, JavaScript transformations, and ServiceNow configuration is needed. This approach does not promise that every Now Assist feature, AI Agent, or voice interaction can use an arbitrary model. ServiceNow's [external LLM support guide](https://www.servicenow.com/community/servicenow-otto-articles/using-external-llms-with-now-assist-including-byok-byollm/ta-p/3218103) distinguishes those cases.

The following method brings the platform configuration layers together. It describes configuration and verification, without claiming a completed platform-wide migration. Documentation and instance observations were reviewed on 27 October 2026; check the corresponding documentation for your release.

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

## 3. Provide Custom LLM Provider prompts for eligible skills

A registered model does not create a compatible prompt for every skill. Start with one custom skill or one eligible ServiceNow skill, then expand coverage deliberately.

For a new skill, choose the custom provider and provider API as described in [Create a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-new-skill.html). For an existing ServiceNow skill, use the supported [clone-and-edit workflow](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html) when available. Preserve the required inputs, outputs, and deployment behavior.

Under **Custom LLM Provider → Prompts**, or the equivalent prompt view in your version, review each target prompt's model, input placeholders, usage conditions, output format, and default status. The [prompt configuration documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html) describes model settings and usage conditions. Do not assume a prompt written for another model will satisfy the same output contract unchanged.

Coverage can target **selected skills** or **all eligible skills**. All eligible means the reviewed set that permits this customization; it does not mean every platform capability.

For each candidate, compare the source and custom-provider prompt side by side. Preserve required input names and the output keys consumed by the calling experience. Test usage conditions with matching and nonmatching inputs. If the caller expects JSON, validate the returned keys and types before accepting the prompt. A readable answer that breaks a downstream parser still needs work.

If you use prompt mirroring to maintain that set, make it an explicit opt-in operation. The companion mirroring automation is disabled by default; keep it disabled until qualified for the target instance. Before enabling it, review a preview showing the source prompt, target skill, intended provider, defaults, conditions, and proposed changes. Start with selected skills, make repeated runs safe, and protect deliberate custom edits. Expanding to all eligible skills requires another coverage review. Do not bulk-delete original prompts or bypass provider policy to make a test pass.

After testing, [finalize the prompt and publish the skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html). Then have an administrator [activate it through AI Admin Hub](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html) in the correct application scope. Complete any required data-steward review and approval before activation. Publishing alone does not make the skill available to users.

[Screenshot 3: Custom-provider prompt coverage and conditions]

## 4. Align instance, skill-group, and skill defaults

Open **Now Assist Admin → Settings → Manage AI models → Manage model providers**, or its equivalent in your release. Inspect the instance default, then inspect skill-group and skill overrides. Supported choices depend on the capability and provider eligibility; a custom provider need not appear in every selector.

Apply changes at the intended scope and review the resulting impact and failures. ServiceNow's [Manage model providers procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html) explains how customization overrides the instance selection. A later instance-level provider change overwrites existing skill and skill-group customizations. Reapply only reviewed overrides and reverify the affected routes.

Also inspect the prompt that will actually be selected. Multiple prompts and usage conditions can change execution; see [Create a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-prompt-template.html). Separately built flows or scripts may use Generative AI Controller capability defaults. Those have their own [provider configuration procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-provider-for-a-generative-ai-capability.html). Review the relevant route instead of assuming one administrative default controls them all.

[Screenshot 4: Instance and scoped provider defaults]

## 5. Treat the AI Agent Skills group separately

Inspect the **AI Agent Skills / AI agents** group, using the label shown in your version. Its default is relevant to agent-related skill execution, but it does not establish that the agent orchestration engine accepts any custom provider.

The official [AI Agent provider selection procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) describes a global agent/workflow setting and lists Now LLM Service, AWS Claude, Azure OpenAI, and Google Gemini. It also requires retesting existing agents after a change and warns that some agents require specific providers.

The employee support guide excludes BYOLLM from its supported out-of-box and custom AI Agent configurations. A custom-model skill called as a tool is therefore a different claim from replacing the agent's own orchestration model. Any deeper customization needs separate support assessment and runtime evidence.

See [AI Agents and custom LLM routing — planned follow-up](./ai-agents-follow-up.md).

[Screenshot 5: AI Agent group default and affected capabilities]

## 6. Keep AI Voice's LLM and audio stages distinct

Voice assistants combine speech-to-text, an LLM, and text-to-speech; the [voice-assistant documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/create-an-ai-voice-service.html) describes those stages. Changing an LLM route does not replace the speech services or telephony integration.

The [AI Voice deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) lists supported LLM providers. It does not establish arbitrary Custom LLM Provider compatibility. A successful text response cannot demonstrate audio quality, caller authentication, tool execution, or live-agent transfer.

See [AI Voice: LLM routing, STT, and TTS — planned follow-up](./ai-voice-follow-up.md).

## 7. Verify execution, then make the configuration portable

Run a harmless, identifiable test through the intended user experience. First verify the grounded prompt and response with [Test a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/test-prompt-template.html). Then repeat through the deployed entry point: an editor test and a production-facing invocation can follow different configuration paths.

[Screenshot 6: Controlled skill test and response]

Correlate the execution time and capability with available ServiceNow logs and endpoint-side evidence. Check model identity, prompt configuration, status, errors, and response shape. ServiceNow's [Generative AI Controller reference](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/reference-for-generative-ai-controller.html) identifies the request logs, metadata, and model-version mappings useful for this inspection. Model names are evidence to correlate, not a substitute for confirming the receiving endpoint.

[Screenshot 7: Runtime provider/model evidence]

Keep a coverage list with one result per entry point: verified, unsupported, or still untested. Include negative tests for unavailable endpoints and confirm the intended fallback behavior. Evaluate representative examples for output correctness and schema compliance before expanding coverage.

For example, track incident summarization in its record UI separately from the same skill called by a flow. Record the expected route, observed route, result, and remaining issue for each. Check access using the intended user roles as well as the builder account. If a route fails, investigate policy, eligibility, prompt selection, and transformations in that order; changing several layers together makes the cause harder to establish.

For transport, capture supported configuration changes in a native update-set batch with children per application scope. Review dependencies and preview results on the target instance. Rebind environment-specific endpoints and credentials, recheck provider policy, and repeat runtime tests. Keep rollback information with the change record. Portable configuration becomes useful only when the target environment can reproduce the verified behavior.
