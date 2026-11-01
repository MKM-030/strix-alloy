# ServiceNow BYOLLM transport coverage

Revision: 28 October 2026. The fresh-instance delivery is **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028**. It covers reviewed metadata and examples for a fresh compatible instance. It is not an upgrade package for used targets or proof that every skill, agent and Voice route works with an arbitrary model.

Use [batch status](batch-status.md) for the current artifact and preview result, [transport runbook](transport-runbook.md) for the fresh-target procedure, [master manual](master-manual.md) for configuration, and the [executed capability-copy guide](capability-prompt-copy.md) for the final historical copier.

## Final delivery and preservation evidence

The final file `Custom-LLM-Platform-2.2-Fresh-Instance-NO-DELETE-20261028.xml` is **4,542,611 bytes**, SHA-256 `1025d336b001bec34fed957a4cab089a5b262a3fc20286eed4bef4e2ecba8ccd`. It contains **809 unique INSERT_OR_UPDATEs and 36 headers**, with zero outer deletes, embedded deletes, version conflicts or scope/container mismatches.

This is explicitly **derived from the untouched actual 868-version native Platform 2.1 export plus an exact same-identity native notice-helper overlay**, not an original native export itself. The old aggregate, its repeated versions and nine deletion identities remain historical evidence only. Do not load that aggregate or add its excluded versions to a fresh-target installation.

Two independent parsers verified all 809 selected primary-field contracts and seven current source code fields across five records, including preserved Gemma logic and the revision-4 native notice helper. The overlay keeps the same wrapper and adds no header or CU identity. Five wrapper reroutes leave zero scope/container mismatches. Historical container differences alone did not establish invalid code.

The final XML loaded on the **source**, with SDK readback confirming 36 headers, 809 unique CUs, exact payload-text/wrapper equality and zero deletes. Final native preview completed with **five unresolved findings**: two newer LOCAL ONLY deployment versions and three missing-parent references. The notice-helper conflict is resolved. See [release verification](release-verification.md); source preview is not fresh-target acceptance. No commit occurred, and an actual new target has not been imported.

## Record-category matrix

| Category | Retained evidence or prerequisite | Fresh-target responsibility |
| --- | --- | --- |
| Installed products and entitlements | Scope/application inventories describe the source. | Install compatible products, release, patches and licenses. |
| ACT allowlist and fallback | Source observation was Custom LLM Provider only, fallback false, Global; no `sys_gen_ai_routing_selection` rows are transported. | Set and verify target-local ACT policy and impact. |
| Formal approval | Approval workflow is separate from provider allowlisting. | Complete required model/system approvals. |
| Provider integration type | Retained Custom LLM Provider metadata includes `integration_type=BYOK`. | Review the installed native integration mode and account/credential requirements; BYOK does not select a concrete model. |
| Provider mapping and model membership | Repaired mapping and reviewed model relationships are retained. | Resolve implementation, API, both aliases, lifecycle and eligibility; inspect `sys_generative_ai_model_config.provider`, not only `model_configs`. |
| Concrete models | Retained model and prompt records contain identifiers. | Bind the intended target strings and verify the receiving endpoint/model. |
| Credentials and endpoints | Public activating secrets are not supplied. | Provision approved credentials, URL, TLS, network and access identity. |
| Request/response transformers | Reviewed repaired Halogen and preserved Gemma logic; one selected update per identity. | Verify text, structured output, empty/error responses and specialized image contracts. |
| Native Voice notice helper | Exact revision 4 of `LocalLLMVoiceAssistantSettings` replaces revision 3 in the same wrapper. Script SHA-256 `669a30b84d69c826827fb32d21dd628cf216fb1db69e415c58945b99fd7a5426`; [current source manifest](../../servicenow/byollm/current-20261028/SOURCE-MANIFEST.json). | Verify native goodbye/inactivity notice behavior on the target; source equality is not Voice runtime acceptance. |
| SCC Vision helper | Current Global helper is retained, 11,984 characters. Its historical referenced AI configuration is absent from the public delivery. | Resolve the private/example graph and target route; helper inclusion is not image-inference acceptance. |
| Executed capability copier | [Guide](capability-prompt-copy.md) and [exact source manifest](../../servicenow/byollm/capability-prompt-copy/SOURCE-MANIFEST.json) preserve the final executed script. Historical repeat: 14 capabilities, 292 unchanged records, 13 validator links skipped, zero writes. | Review source-specific inputs and default-changing behavior before adaptation. Computed `request_tokens` is excluded from copy and change detection. This is separate from the mirror. |
| Mirror helper | Final reviewed refinement is retained after consolidating historical baseline/Validation versions. | Verify helper/platform contracts; do not add the historical 39+1 updates again. |
| Eight mirror Business Rules | Retained infrastructure uses the shared mirror core. | Verify qualified after-insert/update behavior and owning scope. |
| Manual mirror backfill | **Custom LLM - Synchronize prompts**, dry run by default. | Review selected capability coverage; an empty selection covers qualified sources, not all features. |
| Mirror local settings | The template model and three gates are private settings; all four property records are absent because there are no `sys_properties` rows. | Configure all four manually; keep automation/apply/serialization false until qualified. Fail-closed code defaults do not prove presence. |
| Mirror state infrastructure | State table, dictionary, physical index, ACLs and role relations are retained. | Verify uniqueness, permissions and claim semantics; do not seed runtime state. |
| Native generated children | Definition-option and prompt-binding generator contracts remain prerequisites. | Verify actual generators and calculated relationships; do not duplicate generated children. |
| Shared inputs and validators | Capability inputs and shared programs remain dependencies; reviewed relation metadata is retained. | Preserve input/output contracts, order, programs and actual native parents. |
| Admin provider assignments | No universal assignment is certified by inclusion. | Set instance/group/skill policy deliberately; later instance changes overwrite scoped customizations. |
| Prompt model, conditions and lifecycle | Reviewed prompt/configuration updates are retained. | Choose concrete models, defaults and conditions; test, finalize, publish and activate through the supported lifecycle. |
| Agent definitions, versions and tools | Selected agent/version metadata is retained. | Verify orchestration provider, tool contracts, security and actual resolved models independently. |
| Voice context and access | Context API/resource/helper, role/ACL bindings, agent access and ECC authorization metadata are retained. | Rebind local applications/profiles and prove least-privilege caller behavior. |
| Voice/media/mobile | Assistant metadata and dated device evidence are available. | Provide STT/TTS, capacity, channels, media/network and fresh device acceptance. |
| UI layouts and deployment attributes | Selected layout/attribute versions are retained. Two newer source deployment versions are LOCAL ONLY and intentionally excluded. | Configure private execution-profile/settings choices locally; review optional UI changes and collisions. |
| Native parent AI configurations | Three retained prompt records refer to two absent native parents. | Resolve actual compatible parents; the excluded LOCAL ONLY deployment versions are unrelated to this prerequisite. No empty stand-ins. |
| Protected compatibility companion | Seventeen historical entries remain opaque and excluded from public distribution. | Use separately reviewed private dependencies, approved equivalents, or a reduced scope. |
| Host/runtime assets and data | Weights, engines, speech, drivers, conversations, claims and recordings are outside the metadata package. | Provision services separately and keep runtime data private. |

The [generic mirror manifest](../../servicenow/byollm/prompt-mirror/GENERIC-SOURCE-MANIFEST.json) and dated [source manifest](../../servicenow/byollm/SOURCE-MANIFEST.json) preserve earlier identity and code evidence. Neither uninstalled manager proposal substitutes for the executed copier or captured mirror.

## Exclusion ledger

These prefixes identify source records omitted from 2.2. They are **not target deletion instructions**.

| Source identity/group | Historical source material | Final 2.2 treatment |
| --- | --- | --- |
| Obsolete separate Vision model `60b7371f…1085` | Greeting deletion | Identity excluded; the main-model Vision helper path remains separately retained. |
| Duplicate Custom mapping `832dea5f…109e` | Greeting deletion | Identity excluded; retained mapping/model relationships need target verification. |
| Now LLM mapping `296c418f…10fc` | Stale Greeting insert/update followed by graph deletion | Both versions excluded; this delivery neither recreates nor deletes it. |
| Now LLM mapping `296c418f…10fe` | Graph deletion | Identity excluded. |
| Guardian mapping `616c418f…10fc` | Graph deletion | Identity excluded. |
| Now LLM mapping `616c418f…10fe` | Graph deletion | Identity excluded. |
| Now LLM mapping `a96c418f…10fd` | Graph deletion | Identity excluded. |
| Now LLM mapping `e16c418f…10fd` | Graph deletion | Identity excluded. |
| Now LLM mapping `ed6c418f…10fe` | Graph deletion | Identity excluded. |
| 49 older repeated inserts/updates | Duplicate historical versions, including older Halogen/container and other shared identities | Excluded; one reviewed update remains per retained identity, with zero version conflicts. |
| 95 serializer deletion nodes | Embedded serialized child-deletion directives | Removed; final outer and embedded delete counts are zero. |
| Source wrapper placement | Five wrapper reroutes in derivation | Zero final scope/container mismatches; no target duplicate-selection step is needed. |
| Two newer deployment versions | Captures in the LOCAL ONLY set `f1978a…102e` | Intentionally excluded; reviewed earlier deployment versions remain selected. Do not import the newer private execution-profile/settings choices as public defaults. |

The old and new Halogen captures had identical full payloads; 2.2 retains the reviewed Global placement. The repeated **Is Metadata Updated** versions represent one metadata-invalidation identity, not two provider policies. The final unique update does not import ACT routing.

## Qualification boundaries

The final artifact's local derivation and seven-field source checks are established. Final source reload/readback passed; native preview completed with five unresolved findings recorded in [release verification](release-verification.md). Actual new-target import/commit, resolution of the two absent native parents, target-local binding/security review, and selected model/Vision/Voice/agent acceptance remain open. Zero deletion directives do not prove arbitrary imported code or native platform behavior.

For an already used target, prepare a separate reviewed upgrade plan rather than applying this fresh-instance package. For a fresh target, use the exact 2.2 artifact and current [batch status](batch-status.md); retain the 2.1/nine-deletion aggregate only as history.

The full [platform article](community-post.md), [AI Agents article](ai-agents-follow-up.md), and [AI Voice article](ai-voice-follow-up.md) are publication documents, not evidence of successful target installation or universal runtime compatibility.
