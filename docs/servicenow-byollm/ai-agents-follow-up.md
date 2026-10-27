# Planned article brief: AI Agents and custom LLM routing

**Status: planning brief, not a published article or a completed validation report.** No agent migration, runtime test, or supported custom-orchestrator configuration is established by this document.

Working title: **ServiceNow AI Agents and BYOLLM: Skill Tools, Group Defaults, and Orchestration Limits**

## Scope

Explain the distinction between an agent calling a custom-model skill as a tool and the model used by the agent orchestration engine. Cover provider policy, the AI Agent Skills / AI agents group default, capability eligibility, scoped overrides, and runtime verification. Use the actual UI labels and supported providers for the tested release.

The [official agent-provider procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) documents global agent/workflow selection and provider-specific requirements. The employee [external-LLM support guide](https://www.servicenow.com/community/servicenow-otto-articles/using-external-llms-with-now-assist-including-byok-byollm/ta-p/3218103) excludes BYOLLM from supported custom and out-of-box AI Agent configurations. Any deeper custom routing must be assessed separately and described with its support limits. It must not be presented as a generally supported engine option.

## Planned structure

1. Map the execution: user entry point, orchestration, tool selection, skill invocation, and final response.
2. Compare the documented supported-provider path with a custom-model skill used as a tool.
3. Inspect policy, group defaults, and overrides. Explain that an instance-level change can replace existing customizations.
4. Walk through one controlled scenario using synthetic data, if later authorized and verified.
5. Present the evidence, unsupported paths, remaining gaps, and rollback approach.

## Evidence required before writing the finished article

- Record the release, patch, app versions, entitlements, relevant roles, agent type, and entry point.
- Capture the permitted providers, fallback setting, approval state, affected-system impact, and intended group/skill defaults. Compare with [Manage model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html).
- Identify the selected orchestration provider separately from any custom-model skill's provider, model, prompt, conditions, and tool configuration.
- Correlate agent execution, tool invocation, capability/prompt metadata, and receiving-endpoint evidence. Establish which request reached which model; a provider label alone is insufficient.
- Verify the business outcome and tool side effects with the intended user permissions. Include an unavailable-endpoint case and check the intended fallback behavior.
- Keep a coverage table marking each route verified, unsupported, or untested. Obtain required reviews before publication. Do not infer universal support from a single successful scenario.

These are evidence requirements for future work, not instructions to run tests as part of this brief.

## Proposed screenshots

| Image | Capture after verification | What it should establish |
| --- | --- | --- |
| 1 | Supported-provider choices and affected agents for the tested release | The actual supported menu and its limitations. |
| 2 | AI Agent Skills / AI agents group and relevant overrides | The intended administrative selection and scope. |
| 3 | A custom-model skill configured as an agent tool | The tool's provider is distinct from the orchestration provider. |
| 4 | Controlled execution trace with tool calls | Which stages executed and how they relate to the scenario. |
| 5 | Sanitized model/capability metadata and final result | Runtime evidence for the specific route and outcome. |

Use synthetic records and neutral names. Remove instance URLs, identities, sys_ids, credentials, confidential prompts, and internal endpoint details. Keep failures that explain a limitation visible after redaction. Do not claim performance improvements without a defined, separately reportable evaluation.

## Publication and link replacement

The repository overview links here with **planned follow-up** in its link text. Keep that label while this remains a brief. When pasting the overview into ServiceNow Community before the follow-up exists, replace the local Markdown link with plain text saying the article is planned; local file links are not publication URLs.

After the finished follow-up is reviewed and published by the author, copy its real canonical Community URL. Replace the overview's relative link with that verified URL and remove the planned label. Check the published link and add a reciprocal link to the overview. Do not invent a future public URL or publish this planning brief as if it were the validated article.
