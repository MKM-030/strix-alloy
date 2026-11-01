> Superseded for target installation by the [2.2 fresh-instance NO DELETE delivery](batch-status.md). This page preserves the source-aggregate audit; its nine deletes must never be taken as target instructions.

# Historical 2.1 source aggregate — not the target delivery

Verified 28 October 2026. **The native source batch is Complete and exported.** It is a private candidate for target preview; target import, runtime acceptance and public package release have not been established.

## Central source and native batch

The sole Git worktree remains `C:/Projects/strix-alloy-clean`. The [documentation hub](README.md) consolidates the prior documentation chat, **ServiceNow AI Skill Configuration**, Community overview, screenshot plan and platform transport. Historical workspaces and original exports remain dated evidence.

Native parent: **Custom LLM Platform 2.1 - Consolidation 20261027**, ID `310e1af39388db545c8132d47aba104b`. The native completion confirmation completed the entire batch. Both membership pages were read back: **36 unique sets, all Complete, four direct branches**.

| Direct branch | Scope / hierarchy | CU versions |
| --- | --- | ---: |
| Custom LLM Voice 2.0 - Consolidated 20261019 | Preserved six-family baseline; 31 sets | 812 |
| Local LLM Voice - Greeting Context Fix - 2026-10-20 | Generative AI Controller; includes later platform/provider repairs | 19 |
| Custom LLM Foundation 1.0 - Custom skill graph 20261018 | Global; existing empty AI Agents child retained | 32 |
| Custom LLM Platform 2.1 - Global context delta 20261027 | Global; context plus current Halogen and SCC Vision captures | 5 |
| **Total** | Parent has zero CUs | **868** |

These are Customer Update versions, not 868 independent artifacts. The 27 October observation of 849 versions used Greeting 10, graph 24 and Global 3; it is historical. The new export establishes current transport membership.

The XML contains 37 serialized headers for 36 unique sets because the root repeats. Existing Customer Update payloads were preserved; no bulk CU moves, synthesized repair XML or source-script edits were used. The completed 2.0 baseline was not reopened. All 812 baseline record-name/payload-hash multiplicities match the new export exactly.

## Native export

The installed **Export Update Set Batch to XML** action produced one native file:

| Property | Value |
| --- | --- |
| File | `Custom-LLM-Platform-2.1-20261028.xml` |
| Bytes | 5,600,083 |
| SHA-256 | `16bd719d2ed1edc4ed28a8f87e4ac76db7504eb4e7252c519514ccfa58159e8d` |
| Contents | 868 CUs; 36 unique sets; 37 serialized headers |
| State | Source candidate; no target preview or import performed |

The private release folder is `server/.local/byollm-consolidation-20261028/release/`. No user import ZIP is provided for this historical aggregate. Its unchanged XML remains private evidence; the current target package is the separate 2.2 fresh-instance delivery.

## Platform coverage

The baseline includes **Infrastructure 1.0: 39 CUs**, followed by **Validation 1.0.1: one later helper revision**. Together they contain the generic provider/model infrastructure, `CustomLLMPromptMirror`, eight native Business Rules, manual backfill Fix Script, state schema/index/ACL metadata and qualification guards in code. The four private property rows are absent from the export and require target-local setup. This is general existing-skill prompt preparation, not Voice-only configuration. See [prompt-mirror operation](prompt-mirror.md) and the [coverage matrix](transport-coverage.md).

Other families and later branches add model-specific transformers, prompt graphs, validators, context/agent/Voice metadata, provider registration and mapping repairs. The actual ACT allowlist/fallback/routing row is **absent** from the export and remains an explicit target configuration step. The two captured `sys_gen_ai_control_setting_data` versions are the metadata-updated flag; they do not replace ACT policy. Captured provider integration metadata likewise does not choose every skill's runtime model.

## Fresh source and capture verification

The main mapping and Halogen transformer already had 27 October native Customer Updates in Greeting. The older documentation's missing-capture conclusion referred to earlier frozen exports. Fresh readback establishes current capture and field equality.

Two native list captures added the current Global Halogen transformer and `SCCVisionRequestTransformer` to the existing Global delta. With its earlier API, resource and caller-context helper, it contains five CUs. The original mixed-container capture remains preserved for preview comparison.

Six fresh native fields across four records match the selected export fields and canonical copies exactly:

- Main mapping: prompt transformation, revision 6, 27 October 21:43:32 UTC.
- Halogen: request/response transformers, revision 19, 27 October 21:39:50 UTC; selected Global capture.
- SCC Vision helper: script, revision 4, 15 October 21:05:43 UTC; newly captured Global.
- Gemma: request/response transformers, revision 19, 24 October 18:18:14 UTC; existing Voice/business logic preserved.

The [current-field manifest](../../servicenow/byollm/current-20261028/SOURCE-MANIFEST.json) records hashes, scopes and provenance. The original 17-field 19 October manifest remains unchanged. The current Mirror helper also matches final Validation 1.0.1; all three execution gates were read false. No mirror/backfill, skill inference, Vision input, audio or business action was executed for this consolidation.

## Mandatory target preview decisions

The candidate preserves historical versions for review through the native preview process:

- **Nine existing DELETEs:** obsolete separate Vision model, duplicate Custom LLM mapping, and seven Now LLM/Guardian mappings. Review actual target identity, ownership and inbound references. No blanket deletion by display name or copied source ID is approved.
- **Conflicting update/delete:** one Now LLM mapping has a stale Greeting update and later graph deletion. The source form returns Record not found. Avoid resurrecting it by accepting the wrong action; both payloads are inactive, which does not remove the existence conflict.
- **Container scope differences:** 15 differences, including a composite UI-section owner, are recorded. CU application agrees with payload scope in all observed differences. Review them deliberately; a containing-set mismatch alone does not establish invalid code. Prefer the new Global Halogen capture when resolving its identical duplicate.
- **Other overlaps:** compare intended agent/context/prompt/transformer versions and the two metadata-control revisions. Do not infer effective version order from branch names.
- **Security/environment:** review role/ACL/ECC authorizations and custom token/conversation ownership checks; resolve source-specific provider-application, catalog/OneAPI/search bindings and private example references.

The [target runbook](transport-runbook.md) and [coverage matrix](transport-coverage.md) give the detailed decisions. Successful source export does not establish target acceptance of these dispositions.

## Prerequisites and preservation

Compatible release, Store apps, schemas, entitlements, native generators and shared validator/provider/flow records remain prerequisites. Two external native parent AI configurations and 17 protected compatibility entries are not supplied as a universally qualified public dependency bundle. Opaque private XML was not opened. The historical Vision dispatch references an AI configuration absent from this export: capturing its helper closes helper coverage, not the private example graph. Target credentials, connections, endpoint/TLS/network settings, concrete prompt models, provider policy and host/speech runtime require separate configuration and verification.

Original 2.0 XML remains 5,028,890 bytes, SHA-256 `7cce5efc22353bb64f5f3ef36de54d4092c3d7c59dc961bfe8d412647b6e7003`; its ZIP remains 1,326,504 bytes, SHA-256 `4a9d059b2d4c5c985b7094635df2cb5f81395d8c3fee350b51d2298e6fb094ca`. Original manifests and archive copies were not replaced; newer documentation and chat evidence have a separate archive.

The application remains Global. Batch completion moved the current set to **Default [Global]**, verified in the native selector; completed sets were not reopened to restore an obsolete working selection. Halogen, TTS/ASR and host services were not started, stopped, switched or unloaded by this task.

The [Community overview](community-post.md) remains an English draft with [seven pending author screenshots](screenshots.md). AI Agents and AI Voice remain separate linked article briefs. No Community content, Git changes or package was published remotely.
