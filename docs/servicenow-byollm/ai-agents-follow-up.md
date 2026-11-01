# ServiceNow AI Agents and BYOLLM: Skills, Model Routing, and Practical Limits

An AI Agent can use a model to decide its next step and call a skill that uses another model. Understanding those two routes is essential when introducing a custom LLM. A successful custom skill does not establish which model planned the work or whether every tool can execute safely.

**ServiceNow supports arbitrary custom LLMs only partially.** Agent provider choices, skill customization, and supported channels depend on the release and installed applications. This work requires technical knowledge of ServiceNow capabilities, APIs, prompt contracts, permissions, and execution traces. The employee [external-LLM support guide](https://www.servicenow.com/community/servicenow-otto-articles/using-external-llms-with-now-assist-including-byok-byollm/ta-p/3218103) distinguishes custom skills from supported AI Agent provider configurations.

This article explains the configuration method and the limits of the project's customer-developed integration. It does not claim a completed agent migration or current parallel execution. The companion [platform overview](./community-post.md), [master manual](./master-manual.md), and [Voice article](./ai-voice-follow-up.md) cover the surrounding configuration and channel work.

## 1. Identify the model roles before changing anything

Start with a concrete scenario, such as an agent reading a synthetic incident, retrieving relevant knowledge, and preparing a proposed resolution. Map its execution before choosing a provider.

| Layer | Decision to establish |
| --- | --- |
| Governance | Which providers are allowed, whether fallback is permitted, and which assets need approval. |
| Orchestration | Which model selects the agent's next step and tools. |
| Tool skill | Which prompt and concrete model process the tool's inputs. |
| Adapter | Which endpoint receives the request and how its response is transformed. |
| Business execution | Which identity and permissions authorize the resulting operation. |

Record the release, patch, app versions, agent, tools, entry point, and expected outcome. Distinguish a record UI, a conversational experience, and a background trigger. The same skill name can participate in several routes with different configuration and access boundaries.

Keep a coverage ledger with one row per route. Mark each row verified, unsupported, or untested. This makes a limited successful example useful without turning it into a claim about every installed agent.

## 2. Establish the supported orchestration path

Use the release's native agent-provider configuration first. The Zurich [provider-selection procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) describes global selection for agents and agentic workflows, lists named providers, and requires retesting after changes. Some agents have specific provider requirements. It does not document a universal arbitrary-custom-model selector for each agent.

Inspect the **AI Agent Skills / AI agents** group using the label on your installation. Review the instance default and scoped overrides, the affected-agent list, and available provider choices. Do not infer engine compatibility from a Custom LLM entry elsewhere in Skill Kit.

The [Admin provider-management procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html) explains scoped customization and warns that a later instance-level provider change replaces existing skill/group customizations. Save the intended exceptions before a broad change and recheck them afterward.

[Agent Screenshot 1: Supported agent providers, group default, and impact]

Review ACT policy independently. Provider allowlisting and formal asset approval are separate controls; fallback can retain a previous provider. With fallback disabled, unsupported active systems must be deactivated. Use the [ServiceNow AI settings procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html) and inspect the resulting impact rather than assuming every request moved.

## 3. Add a custom-model skill without confusing it with orchestration

Register the custom model, connection alias, and transformations through the applicable [model setup](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html). Test its endpoint contract separately. A model display name alone does not prove the receiving endpoint.

For the skill itself, ServiceNow documents [creating a custom skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-new-skill.html) and [cloning eligible existing skills](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html). The project also has a distinct customer-developed route: **CustomLLMPromptMirror** adds provider-specific configuration beneath an existing skill/capability while retaining its identity.

The historical installed mechanism has eight narrow after-insert/update BR callers and a manual backfill Fix Script using the same service. Native generators create the definition-option and prompt-binding children. The mirror verifies those relationships instead of manually writing protected references. This copies supporting configuration; it is not a skill clone or a declaration of official support for every OOTB agent.

Use a selected-capability preview before considering broader coverage. Keep automation, apply, and serialized-execution gates false until target qualification. Preserve source prompts, shared inputs, validators, manual target edits, and deployment choices. The [prompt-mirror guide](./prompt-mirror.md) describes the exact interfaces and prerequisites.

[Agent Screenshot 2: Existing skill, custom-provider prompt, and agent tool]

A prepared provider graph does not select the agent's orchestration model. Verify separately that the agent can call this particular skill as a tool through the intended supported configuration.

## 4. Preserve the prompt and tool contracts

Select the actual prompt and inspect its concrete model, input placeholders, conditions, defaults, token limits, and output shape. [Prompt configuration](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html) describes these authoring controls. Different prompts in the same skill can retain different model assignments.

For an incident tool, define what the input contains and what the caller expects back: for example, a summary and proposed resolution with required keys. Test missing data, empty results, malformed JSON, truncation, and provider errors. Preserve the validator and postprocessor contract rather than forcing every capability into one generic response wrapper.

Native function/tool calling and prompt-driven structured action text are different protocols. An adapter that returns valid text or ReAct-style JSON does not thereby implement the engine's native function-call contract. Preserve tool identifiers and argument schemas, and report unsupported response forms explicitly.

Keep business instructions with the skill or agent wherever possible. Some preserved project adapter logic also contains caller and execution-context behavior. Retain that behavior until a reviewed refactor moves it with regression evidence; replacing the adapter with a minimal generic example could remove necessary controls.

For skills using the authoring lifecycle, [finalize and publish](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html), then have an administrator [activate the skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html), completing required reviews. The mirror itself does not activate products.

## 5. Keep execution authority in the platform

The proposed action, authorized action, submitted operation, and confirmed result are separate states. A model-generated sentence such as a success message is not evidence that a record was changed or a request completed.

Use the intended execution identity and normal record/field permissions. Test access with a representative user rather than relying only on an authoring administrator. If a tool needs explicit user confirmation, keep that confirmation tied to the actual proposed action and current inputs.

The project's caller-context helper can carry supplementary user notes into an existing conversation. Its inclusion receipt means that the text was included in a returned prompt. It is not proof of understanding, business approval, or successful execution. Corrections to a name or request must not silently authorize a new action.

[Agent Screenshot 3: Tool permissions, confirmation, and authoritative result]

Preserve correlation between conversation, execution plan, tool request, and result. On an ambiguous timeout, establish the submitted operation's outcome before retrying. A second model request must not duplicate a business write whose first outcome is unknown.

## 6. Treat background work and parallel models as separate engineering

A responsive dialogue model, an agent planner, and a specialized tool model can have different requirements. Registering all three models does not establish independent scheduling, sufficient capacity, or correct result delivery.

Historical project snapshots used a selected backend and caller-context logic expecting one active plan per conversation. Those are dated constraints, not a fresh diagnosis of the running host. A separate responsive-conversation runtime has since been prepared in source, but its documentation keeps independent qualification and activation open. Source checks do not establish a live cutover or concurrent operation.

For a future background route, define a stable job identity and its conversation, turn, model, and authorization binding. Bound the queue and capacity. Handle results arriving after later user turns, duplicated callbacks, disconnects, and uncertain operations. Keep a completion result separate from its notification or spoken delivery.

[Agent Screenshot 4: Correlated execution and background-state evidence]

A request scratchpad, model list, or background-channel setting cannot supply those contracts by itself. Qualify the actual combined implementation before claiming parallel multimodel support.

## 7. Verify the route and prepare the target

Run a harmless scenario through the deployed entry point. Use [prompt testing](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/test-prompt-template.html) to inspect grounded inputs, then correlate the agent execution with its tool invocation and endpoint evidence. The [controller reference](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/reference-for-generative-ai-controller.html) identifies useful logs and model metadata.

Record the expected and observed orchestration provider, tool prompt/model, result schema, validator status, permissions, and business outcome. Include an unavailable endpoint and a rejected or unsupported tool response. A successful resolver check or mapping repair is not a successful live skill test.

[Agent Screenshot 5: Runtime provider/model evidence and checked outcome]

For a fresh target, select the **Fresh Instance NO-DELETE** delivery identified by the current installation guide and manifest. Review app, native-flow, validator, parent-configuration, and scope prerequisites before native preview. Configure target-local credentials, ACT policy, mirror settings, and operational bindings. Keep gates off until the selected route is qualified.

Preserve raw logs privately and publish sanitized evidence for the specific demonstrated scenario. The source integration provides a method to investigate and configure these routes; full agent orchestration, Vision, parallel execution, and target acceptance require their own results.
