# ServiceNow BYOLLM master manual

Revision: 1 November 2026 (later source-delta status); sealed fresh-instance delivery remains dated 28 October. This manual brings together the platform configuration, existing-skill prompt mirroring, model contracts, and transport work. It is an operating guide and evidence map, not an automatic installer or a report that every route has passed.

Start with the [quickstart](quickstart.md) and the [final executed capability-copy guide](capability-prompt-copy.md). The fresh-instance delivery is **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028**. Use [batch status](batch-status.md) for its artifact and qualification state, [configuration boundaries](configuration-boundaries.md) for field-level limits, and [sources](sources.md) for product references and historical reconciliation. The [reviewed source snapshot](../../servicenow/byollm/README.md) and [source manifest](../../servicenow/byollm/SOURCE-MANIFEST.json) identify native records and exact preserved code without duplicating instance identifiers here.

The later **Platform 2.3 Halogen Agent Delta** is now applied and independently capture-verified: 66 active prompt selections plus the Halogen transformer and Ledger, with 69 unique no-delete captures including a native metadata signal. It remains a separate WIP delta; it has not been folded into the sealed 2.2 delivery or accepted on a new target. See the [dated execution audit](../../servicenow/byollm/halogen-agents-20261101/POSTRUN.md). Separate TTS, STT, local conversation and Agent configurations remain; full phone/context/progress acceptance is still open.

## 1. Read the evidence by date

Four implementation states must remain distinct.

| State | Established evidence | Limit |
| --- | --- | --- |
| Historical prompt mirror | The existing `CustomLLMPromptMirror`, eight Business Rules, Fix Script, and state infrastructure were installed and captured in October. An owned Global fixture exercised prompt insert/update and an unchanged repeat. | This does not qualify every installed OOTB skill, trigger table, scope, or model invocation. |
| Later manager design | `CustomLLMManager` was developed separately with discovery, contracts, adoption, and worker concepts. | Its native installation was not established. It is not the installed mirror's new name. |
| 27 October repair | The user supplied a completed repair log for the Custom LLM mapping, Halogen request transformer, and duplicate mapping. Batch/single provider resolution then agreed and exposed both active models. | The log explicitly reported `live_skill_tested=false`. Resolver verification is not a text, vision, or voice acceptance test. |
| Fresh-instance delivery | Final derived Platform 2.2 contains 809 unique INSERT_OR_UPDATEs and 36 headers, with zero outer/embedded deletes, version conflicts or scope/container mismatches. Seven current source code fields across five records are verified. | Final source reload and full SDK payload readback passed. Native preview completed with five unresolved findings; no new-target import or commit is established. |

The 28 October review verified all 809 selected primary-field contracts and seven current source code fields across five records with two independent parsers, including preserved Gemma adapter logic. Five wrapper reroutes leave zero scope/container mismatches. The final artifact combines the untouched native 868-version Platform 2.1 export with an exact same-identity native notice-helper overlay. The older aggregate is historical source evidence, not the fresh-target delivery; Platform 2.2 is not an upgrade package for used targets.

The overlay supplies revision 4 of `LocalLLMVoiceAssistantSettings` in its existing wrapper, without adding a header or CU identity. Its exact source and script hash are recorded in the [current seven-field manifest](../../servicenow/byollm/current-20261028/SOURCE-MANIFEST.json). The final XML loaded on the source and SDK readback matched all 809 payload texts and wrapper IDs. Final native preview completed with five unresolved findings: two newer LOCAL ONLY deployment versions and three missing-parent references. The notice-helper conflict is resolved; see [release verification](release-verification.md). Two newer deployment versions in the LOCAL ONLY set are intentionally excluded; the two absent native parent configurations remain prerequisites.

Historical device tests, local API checks, and earlier source hashes remain evidence for their own versions. They do not qualify the repaired combined system automatically.

## 2. Prepare a compatible environment

Inventory the intended entry points before choosing defaults: record UI skills, flows, scripts, agent tools, agent orchestration, voice assistants, and mobile channels. For each, record the installed product, capability, provider, prompt/model, activation state, owner, and intended result. A provider change does not assess an unlisted route.

Record the platform release, patch, Store application versions, entitlements, regions, and execution roles. Product labels may read Now Assist Skill Kit or AI Skill Kit, and Now Assist Admin or AI Admin Hub. The documented model-management feature starts with Admin 6.2 and Yokohama Patch 6; installed application compatibility must still be checked. See [Manage AI models](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/manage-large-language-models.html).

Assign task-specific access: AI steward for governance, Skill Kit authoring access, model administration for custom model registration, and the appropriate platform/Admin access for installation and activation. The mirror itself uses administrative checks and normal secure record access. A broad user authorization does not change native ACL, scope, or protection behavior.

Prepare an approved endpoint, network reachability, TLS, authentication, and capacity. Runtime services, model weights, speech engines, drivers, DNS, proxies, and credentials are operator prerequisites. Work first in a test environment, retain the prior configuration, and identify a rollback owner.

## 3. Keep configuration responsibilities separate

| Decision | Authoritative configuration |
| --- | --- |
| Which providers are permitted; fallback and required asset approval | AI Control Tower |
| Provider/API, model identity, aliases, credentials, transformers | Native model management / Skill Kit / Generative AI Controller |
| Provider assigned to instance, skill group, or skill | Admin model-provider management |
| Concrete model and generation settings for a prompt | The selected prompt's settings in Skill Kit |
| Which prompt executes | Prompt defaults, conditions, and the caller's capability contract |
| Model version replacement | Native model-version management |
| Whether users can invoke the result | Publication, deployment, activation, and access controls |
| Model used to prepare mirrored configurations | Target-local mirror configuration |
| Voice dialogue versus background agent work | Their independently verified runtime routes |

Selecting Custom LLM Provider does not choose between two models registered under that provider. A mirror template is not a platform routing default. A model display name is not proof of the endpoint that received the request.

## 4. Review AI Control Tower governance

Open the release-appropriate **AI Control Tower → Settings → ServiceNow AI** controls. Review the current provider policy and impact summary. If the agreed policy is custom-provider-only, retain Custom LLM Provider, deselect other providers deliberately, and review fallback before saving. Compare affected systems with the inventory; do not perform a blind instance-wide change.

With fallback enabled, affected systems can continue on previously configured providers. Without it, unsupported active systems must be deactivated. Review the resulting support matrix and any systems that cannot be activated. [AI model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/ai-model-providers.html) documents these outcomes.

Provider allowlisting and formal model-asset approval are separate controls. Complete required model/system approvals through the configured governance workflow. Reopen settings after an authorized change and verify the saved state. See [ServiceNow AI settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html).

The 27 October observation showed Custom LLM Provider only, fallback false, and Global routing. It was a read-only observation, not a routing mutation or proof that all processing is local. The routing table, `sys_gen_ai_routing_selection`, is absent from the export; configure and verify ACT policy on the target. Assess sharing, overflow, search, guardrails, tools, speech, and channel services separately. Technical routing fields in the boundaries ledger are version-dependent observations, not a public scripting API.

## 5. Register the provider, model, and connections

Where available, use **Skill Kit → Providers and Models → Add model**. Supply the actual provider/API, model identifier, supported languages, context limits, connection, credentials, and transformer configuration. The [Create a model procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html) describes the guided path.

For the generic connector, use the documented [credential and alias setup](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-api-credentials-for-a-generic-large-language-model-llm.html). Store secrets in credential records. The [generic connector procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-generic-llm-connector.html) also describes model, prompt, and transformer forms; its stated scope is text generation.

Verify actual relationships. The examined model configuration references its provider mapping through `sys_generative_ai_model_config.provider`. The mapping's implementation and connection alias and the model's HTTP alias are separate dependencies. Inspect both. Do not use an empty or stale `model_configs` list as the sole inventory.

Preserve owning scope and package independently. Use supported owning-application contexts for creation and capture. Do not repair scope restrictions by assigning ownership fields, copying protected standard flows, or changing ACLs. Provider integration type, Active, and External Visibility need interpretation against the installed dictionary and native UI; none alone proves an effective model route.

## 6. Set Admin provider scope deliberately

In **Admin → Settings → Manage AI models → Manage model providers**, inspect instance, group, and skill selections. Available choices depend on capability support, policy, and region. A custom provider may not appear in every selector.

Apply an intended instance baseline first, then reviewed group/skill customizations. Scoped customization overrides the instance choice, but a **later instance-level change overwrites existing skill/group customizations**. Save the intended exceptions before a broad change, review affected systems and failures, and recheck the resulting routes. See [Manage model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html).

Flows or scripts using Generative AI Controller can have capability-provider selection outside the record UI's administrative path. Trace the actual caller rather than assuming one setting controls all entry points.

## 7. Add Custom LLM configurations without cloning skills

### Final executed capability-based copy

The [capability-copy guide](capability-prompt-copy.md) and [exact source manifest](../../servicenow/byollm/capability-prompt-copy/SOURCE-MANIFEST.json) preserve the final executed one-time copy script. Its historical repeat processed **14 capabilities**, reported **292 unchanged records** and **13 existing validator links skipped**, with zero writes. The final fix excludes computed `sys_generative_ai_config.request_tokens` from both copying and change detection. It adds the provider definition/prompt graph beneath existing capability identities. Its historical default-changing and Business-Rule-suppression behavior needs the guide's target review; it is separate from the installed eight-rule mirror below.

### Installed prompt mirror

The project's mirror extends **existing installed capabilities** with provider-specific definition and prompt configurations. It preserves the OOTB skill/capability identity. Copying this supporting configuration graph is different from using the UI to clone a skill.

The installed historical implementation is `CustomLLMPromptMirror`, a Global, server-only Script Include. Eight after-insert/update Business Rules, order 100, and **Custom LLM - Synchronize prompts** call that same implementation. The rules cover:

- Capability definitions, definition options, and definition inputs.
- Prompt configurations and prompt bindings.
- Request-validator relations, response-validator relations, and shared validator changes.

They are not delete/query rules. The shared caller supplies the changed table/record and readable previous routing references, allowing reparenting to be assessed. Generated Custom LLM targets are excluded by exact source qualification. Imports that suppress Business Rules need an explicit later scan.

### Selection, planning, and backfill

Discovery qualifies the installed Now LLM Service / Now LLM Generic provider, mapping, and implementation relationships. It does not merge implementations by similar names. A selected list contains existing capability references; an empty list covers all qualified accessible source variants. Historical discovery found 379 variants, which was a census rather than 379 successful migrations.

The manual Fix Script starts with `APPLY=false`. Its service call is:

```javascript
new global.CustomLLMPromptMirror().run({
    capabilityIds: [],
    apply: false
});
```

For selected backfill, populate `capabilityIds` with reviewed target-local capability references. Read each variant's plan and blockers before considering apply. The service also exposes `scan(selection)`, `plan(definitionId)`, and `apply(plan)`. These examples document the installed interface; they are not instructions to enable automation during documentation work.

Manually configure the target's four private administrative settings. The candidate contains no `sys_properties` rows, so none of these settings is transported:

| Setting | Purpose |
| --- | --- |
| `custom_llm.prompt_mirror.default_model` | Explicit eligible model record used to prepare mirrored configurations. |
| `custom_llm.prompt_mirror.automation_enabled` | Enables source-change reconciliation when qualified. |
| `custom_llm.prompt_mirror.apply_enabled` | Gates product metadata writes. |
| `custom_llm.prompt_mirror.serialized_execution_verified` | Records separately established target serialization acceptance. |

The three gates were observed false on 28 October. The helper's fail-closed defaults do not prove that the target settings exist; verify all four explicitly. There is no hardcoded model fallback. Changing `default_model` does not switch active skills, group routing, or agent orchestration.

### Preserve the native graph contract

Native rules generate definition-option and prompt-binding children. The mirror verifies their real identities, calculated references, ownership, and nondefault status instead of inserting duplicate children or writing protected fields. The supported historical source contract requires one definition configuration and one binding per prompt; ambiguity blocks.

Inputs are read through the existing capability and fingerprinted as shared dependencies. Shared validator programs remain unchanged; required request/response relations are preserved or adapted under reviewed contracts. Preserve placeholders, roles, input/output schemas, conditions, and caller expectations.

The target needs a unique eligible Custom LLM mapping, its native implementation, an active eligible model, complete transformers, both aliases, installed capabilities, and readable referenced metadata. Existing unowned Custom definitions require reviewed adoption; occupied identities, missing references, manual target drift, protection, and field-length violations stop planning or application.

State belongs in `u_custom_llm_prompt_mirror_state`, with restrictive admin ACLs and a verified physical unique index on `u_key`. Dictionary `unique=true` alone was historically insufficient proof. Origin hashes, operations, and claims are runtime state, not transport seeds. Claims are not stolen on timeout; interrupted work requires explicit recovery review.

Normal secure writes, native Business Rules, and audit remain active. Defaults and provider activation are preserved. A repeat that is truly unchanged returns NoOp before product/state writes. Historical acceptance demonstrated this for the owned Global fixture, not all scopes or trigger types.

### Choose the correct implementation version

The historical Infrastructure 1.0 baseline contains the earlier mirror; Validation 1.0.1 refines the same helper with field-length preflight. The fresh 2.2 delivery consolidates repeated versions into one reviewed update per identity, including the final helper. Do not add the historical 39+1 versions to it. Neither the historical `CustomLLMCapabilityManager` proposal nor the later uninstalled `CustomLLMManager` replaces that evidence.

ServiceNow also documents a [clone-and-edit workflow](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html) for eligible skills. That is a separate product option. It is not a prerequisite for this project's additive mirror, and it does not make the custom extension a universally supported OOTB migration mechanism.

## 8. Select the prompt model and deploy intentionally

Open the skill, select **Edit prompt**, choose the actual prompt, and inspect **Prompt settings → Model**, or the equivalent Configurations view. Verify provider/API, concrete model, token settings, temperature, output format, conditions, and default status. The examined prompt stores its model string in `sys_generative_ai_config.model`; use native controls rather than assuming a model-reference field.

Test both matching and nonmatching usage conditions, including the default route. A skill can contain multiple prompts, so changing one does not change all its invocations. [Prompt configuration](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html) and [prompt selection](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-prompt-template.html) describe those settings.

For skills managed through the authoring lifecycle, finalize the prompt, publish the skill, and have an administrator activate the deployment in the correct scope, completing required review. [Publication](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html) and [activation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html) are separate. The mirror does not perform them. An active/published prompt can coexist with an inactive in-product skill.

Model-version management is another layer. Review default/target version mappings for the intended skills and models; it does not replace provider selection or concrete prompt configuration. Preserve explicit choices when reviewing updates or deprecated versions.

## 9. Keep text, vision, and business contracts intact

The execution path is: selected prompt and skill inputs → native rendering → provider transformation → model request adapter → endpoint → response adapter → validators/postprocessing → caller result.

Define normal, empty, truncated, and error responses. Preserve message roles and rendered input values. An OpenAI-compatible URL does not prove payload compatibility. The response adapter must return the platform contract expected by that capability. Adding a global `model_output` wrapper is not a substitute for satisfying its validator.

Keep endpoint parsing and generation parameters in adapters. Business requirements such as identity confirmation, permissions, approved actions, and ordering belong in the relevant skill/agent contract. Existing Gemma adapter logic contains some such behavior; preserve it until a reviewed refactor moves it without regression.

The SCC Vision example used its own `SCCVisionRequestTransformer` dispatch. Its missing `VISION_CAPABILITY` flag alone was not proof of a defect; later analysis corrected that earlier diagnosis. The image dispatch, authorized image representation, downstream adapter, and model must agree. Do not add a standard vision flag indiscriminately or replace the adapter with a text-only version.

The October repair restored the reported dispatch and corrected ambiguous provider resolution. The current Global helper is captured, but its historical referenced AI configuration is absent from the public export; the private/example graph remains a prerequisite. Neither repair nor capture proves that the model consumed an image. Reuse the authorized regression case, establish extraction from the image itself, and keep fixed example references outside a generic release.

## 10. Treat agents and voice as separate routes

A custom-model skill called by an agent is distinct from the agent's orchestration model. Review the AI Agent Skills / AI agents group and the release's supported agent provider menu. The [agent-provider procedure](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) requires affected-agent review and retesting. It does not establish an arbitrary per-agent BYOLLM switch.

Voice includes STT, dialogue/model work, TTS, caller controls, and a browser/mobile/telephony channel. The [voice deployment documentation](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) has its own support boundary. Text success does not qualify audio, authentication, handoff, or device behavior.

The reviewed historical bridge selected one backend and could overwrite the request model. Caller-context logic expected one active plan per conversation. The ReAct helper's model-specific condition did not itself change the model. These observations identify work needed for independent dialogue and background-agent routing; they do not establish that parallel multimodel operation is complete.

That target needs job/conversation/turn correlation, capacity limits, result delivery after later turns, duplicate/late-result handling, and confirmation before business effects. See the full [AI Agents article](ai-agents-follow-up.md) and [AI Voice article](ai-voice-follow-up.md).

## 11. Verify each entry point and target import

Use harmless synthetic data. Record expected provider/model, actual entry point, prompt/conditions, response schema, validator status, and observed receiving endpoint. Correlate ServiceNow logs and endpoint evidence; a model label alone is insufficient. Verify permissions with the intended user identity and test an unavailable endpoint. Keep raw prompts, images, audio, credentials, and private correlation details out of public material.

For transport and target installation:

1. Select **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028** and its manifest from [batch status](batch-status.md). Preserve the original native 2.1 XML as historical evidence; do not load that aggregate as the fresh-target package.
2. Confirm target apps, scopes, licenses, schemas, native flows, validators, and the two absent native parent configurations. Newer LOCAL ONLY deployment versions are not substitutes for those parents.
3. Confirm the 809 unique updates and 36 headers against the derived-artifact audit. All nine deleted identities, the stale insert and 49 older repeated inserts are excluded; 95 embedded serializer deletion nodes were removed. There are zero outer/embedded deletes or conflicts, and five wrapper reroutes leave zero scope/container mismatches.
4. Load the final derived XML through the supported Retrieved Update Sets workflow on a fresh compatible target. Preview the entire batch, resolve collisions and missing dependencies, and preview again. Final source reload/readback passed and native preview completed with five unresolved findings. These source checks are separate from fresh-target acceptance. No commit has occurred.
5. Commit only the reviewed compatible hierarchy. Verify actual target records, references, calculated children, publication, and activation afterward.
6. Configure target-local aliases, credentials, endpoints, all four mirror properties, provider policy, assistant/channel bindings, and runtime services. Neither mirror property rows nor ACT routing selections are included in this export.
7. Perform selected dry-run backfill, review its graph and blockers, then qualify any intended controlled apply separately. Keep automation gated until target acceptance.
8. Repeat text, vision, agent, voice, access, and fallback checks for the routes in scope; record rollback and unresolved limitations.

The final delivery file is `Custom-LLM-Platform-2.2-Fresh-Instance-NO-DELETE-20261028.xml`, 4,542,611 bytes. It is explicitly derived from the untouched 868-version native export plus the exact native notice overlay, not itself an original native export. It is for fresh instances, not upgrades of used targets. Final source reload/preview, actual new-target import and runtime acceptance remain open. The package contains no universal host installer. The full [platform article](community-post.md), [AI Agents article](ai-agents-follow-up.md), and [AI Voice article](ai-voice-follow-up.md) are separate publication documents.
