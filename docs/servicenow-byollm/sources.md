# Sources and documentation reconciliation

Reviewed 27 October 2026. This register supports the [Community draft](community-post.md) and [configuration boundaries](configuration-boundaries.md). Versioned ServiceNow documentation defines product behavior; local observations establish only the inspected state. A public documentation URL is not evidence that this project's draft or package has been published.

## Primary product references

| Subject | Reference | Use in this documentation |
| --- | --- | --- |
| Governance | [Configure ServiceNow AI settings](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/aict-configure-servicenow-ai-settings.html) | Provider policy, fallback, and separate asset-approval controls. |
| Policy impact | [AI model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/ai-model-providers.html) | Unsupported systems, support matrix, and routing boundaries. |
| Model setup | [Create a model](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/servicenow-large-language-model-now-llm/create-model.html) | Guided model registration. |
| Credentials | [Generic LLM credentials](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-api-credentials-for-a-generic-large-language-model-llm.html) | Connection and credential alias setup. |
| Connector | [Configure a generic LLM connector](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/configure-a-generic-llm-connector.html) | Model, prompt, transformer records; text-generation scope. |
| Custom skills | [Create a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-new-skill.html) | Skill provider and API choices. |
| OOTB customization | [Clone and edit a ServiceNow skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/clone-and-edit-servicenow-skill.html) | Eligible skills and preserved deployment contracts. |
| Prompt settings | [Configure a skill prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/configure-skill-prompt.html) | Model, token settings, and usage conditions. |
| Prompt selection | [Create a prompt](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/create-prompt-template.html) | Multiple prompts and default behavior. |
| Publication | [Finalize and publish a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/publish-skill.html) | Prompt finalization before publication. |
| Activation | [Activate a skill](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/now-assist-skill-kit/activate-skill.html) | Admin activation after publication. |
| Availability | [Manage AI models](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/manage-large-language-models.html) | Version, role, and regional prerequisites. |
| Defaults | [Manage model providers](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/edit-model-providers.html) | Instance/group/skill precedence and overwrite caveat. |
| Agent models | [Select the model provider](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/select-aia-llm.html) | Agent-specific choices and required retesting. |
| Voice | [Deploy AI agents for voice](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/deploy-ai-agents-for-voice.html) | Separate voice capability restrictions. |
| Verification | [Generative AI Controller tables](https://www.servicenow.com/docs/r/zurich/intelligent-experiences/generative-ai-controller/generative-ai-controller-tables.html) | Runtime log fields; correlate with endpoint evidence. |

Store applications can introduce changes within a release family. Record actual app versions with any reproduction. Current documentation may use AI Skill Kit, AI Admin Hub, or Otto where an installed UI still says Now Assist. Unversioned links can resolve to a newer release; the Zurich links above deliberately preserve the selected release context.

## Community editorial comparators

These articles informed article structure and scale. Counts are approximate editorial measurements of the main article body, excluding navigation and comments; they are not ServiceNow publication limits.

| Comparator | Approximate body length | Editorial relevance |
| --- | ---: | --- |
| [Using external LLMs with Now Assist, including BYOK/BYOLLM](https://www.servicenow.com/community/servicenow-otto-articles/using-external-llms-with-now-assist-including-byok-byollm/ta-p/3218103) | 2,087 words; 5 images | Employee-authored support and connection-type context. |
| [Model Choice Without Lock-In: Keeping Your LLM Options Open](https://www.servicenow.com/community/servicenow-ai-platform-articles/model-choice-without-lock-in-keeping-your-llm-options-open-on/ta-p/3609982) | 876 words | Focused model-choice overview. |
| [From Planning to Go-Live: Now Assist Implementation](https://www.servicenow.com/community/servicenow-otto-articles/from-planning-to-go-live-now-assist-implementation/ta-p/3494920) | 1,180 words | Practical implementation sequence. |
| [AI Voice Agents Are Here: Autonomous Service That Delights](https://www.servicenow.com/community/servicenow-otto-articles/ai-voice-agents-are-here-autonomous-service-that-delights/ta-p/3448126) | 1,594 words; 4 images | Voice-specific follow-up scale. |

The overview keeps agents and voice as linked follow-ups. Comparator body lengths do not validate this project's implementation, screenshots, transport, or runtime claims.

## Reconcile earlier snapshots

Customer Update (CU) versions, unique CU names, update-set identities, and serialized XML headers count different things. Counts from successive snapshots must not be added as if they were disjoint deliverables.

| Documentation stage | What it represented | Current interpretation |
| --- | --- | --- |
| Earlier 120-CU material | A narrower historical implementation snapshot. | Retained as history; it is not the current consolidated inventory or proof of a complete public installer. |
| Infrastructure 1.0 / Validation 1.0.1 | 39 baseline CU versions plus one later validation version of an existing artifact. | 40 versions did not mean 40 independent source artifacts. |
| Core 1.1 plus Compatibility-Private | 293 core CUs and 17 protected compatibility entries. | Historical paired scope and dependency evidence. The protected companion was not a general public dependency bundle. |
| Six-family 19 October Voice 2.0 baseline | Infrastructure 1.0, Validation 1.0.1, Core 1.1, Gemma 1.2, Foundation 1.0, and Voice 1.3. | 31 unique sets, 812 CU versions, and 783 unique names. There are 32 serialized headers because the root repeats identically. The 17 protected compatibility entries remain excluded. |
| Platform 2.1 candidate, 28 October | Native parent and all 36 sets Complete; one native XML export with 868 CU versions. | Private source freeze for target preview. The generic infrastructure, newer mapping/adapters and context are included; target dispositions and acceptance remain separate. |

The 19 October inventory contains 29 additional version occurrences across 26 shared names. Those occurrences explain why CU versions and unique names differ; they do not establish duplicate runtime objects. Later host/runtime work is also separate from captured ServiceNow metadata. Re-exporting a baseline cannot prove that later changes were included.

## Preserved evidence and publication

Original native exports, historical drafts, manifests, field ledgers, hashes, and read-only observation receipts are preserved locally for provenance. This public register intentionally omits private storage locations, instance URLs, record identifiers, credentials, and raw runtime data.

The preserved records support narrow claims: the baseline inventory, inspected provider-policy state, and the origin of reviewed source fields. They do not turn an old draft into a published Community article. A technical source snapshot is not an installer, and a source batch marked Complete is not a target-import acceptance result.

There are exactly three full English publication drafts: the general platform overview, AI Agents and AI Voice. Their coordinated plan has 17 pending author screenshots. Public release of software still requires the relevant dependency, privacy, target preview/import and acceptance decisions in [batch status](batch-status.md).

## Consolidated 28 October evidence

The latest revision reconciles the documentation chat and **ServiceNow AI Skill Configuration**, the newer 27 October technical revision and its repair-delta plan, and fresh native source/capture observations. The earlier claim of missing repair capture was correct for the frozen exports examined then. The current Greeting branch contains those repairs, and six fields across the provider mapping, Halogen, Gemma and SCC Vision helper now match the new native export exactly. Both findings remain dated rather than overwriting their provenance.

The [generic mirror manifest](../../servicenow/byollm/prompt-mirror/GENERIC-SOURCE-MANIFEST.json) identifies the installed helper, eight native rules and Fix Script, with baseline 39 plus Validation 1. The [current-field manifest](../../servicenow/byollm/current-20261028/SOURCE-MANIFEST.json) is separate from the original 17-field snapshot. The English [master manual](master-manual.md), [prompt-mirror procedure](prompt-mirror.md), [coverage matrix](transport-coverage.md) and [target runbook](transport-runbook.md) supersede the older parallel documentation entry points.

The expanded [chat audit](chat-reconciliation.md) recovered the exact final capability-based copier from native history, including its request-token comparison correction and 14-capability no-change repetition. The [copier guide](capability-prompt-copy.md) separates that executed source from later manager proposals. The current target artifact is the derived 2.2 fresh-instance NO DELETE package; the 868-version aggregate is preserved history, not a target cleanup instruction. A later native notice-language export closes an additional source-version gap found during preview. Source-local execution mappings remain target-local.

The resulting final snapshot verifies seven code fields across five records. [Final release verification](release-verification.md) records complete native payload readback and five unresolved source-preview findings, with no application commit or new-target acceptance. The eleven reconciled legacy source chats were archived separately after verification on 1 November; the canonical task remains open.

Three primary documentation pages were rechecked on 28 October: prompt model configuration (Zurich), the generic connector (Zurich), and Manage model providers (the unversioned link currently resolves to Brazil). The prompt-level model field, connector response contract and broad-update overwrite caveat remain distinct from this project's custom no-skill-clone implementation. The unversioned provider page must not be treated as proof of an installed release or exact UI labels.
