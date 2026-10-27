# Consolidated ServiceNow batch status

Observed 27 October 2026. This page records source consolidation, not a completed platform migration or a generally installable Community package.

## Central source and native batch

The only Git worktree is the existing primary checkout. The [documentation hub](README.md) is the canonical entry point; [reviewed native sources](../../servicenow/byollm/README.md) and their manifest are maintained alongside it. Historical workspaces and original exports remain preserved as evidence. Active model, speech and external runtime assets were not moved or changed by this work.

The native working parent is **Custom LLM Platform 2.1 - Consolidation 20261027**, state **In progress**. The native UI shows **36 update sets and four direct branches**:

| Direct branch | Scope / hierarchy | Customer Update versions | Source state |
| --- | --- | ---: | --- |
| Custom LLM Voice 2.0 - Consolidated 20261019 | Completed six-family baseline; 31 sets | 812 | Complete |
| Local LLM Voice - Greeting Context Fix - 2026-10-20 | Generative AI Controller | 10 | In progress |
| Custom LLM Foundation 1.0 - Custom skill graph 20261018 | Global; one existing AI Agents child with no Customer Updates | 24 | In progress |
| Custom LLM Platform 2.1 - Global context delta 20261027 | Global | 3 | In progress |

The new parent has no Customer Updates of its own. These observed branch counts total **849 Customer Update versions**; this is a membership sum, not the result of a new completed 2.1 transport export. Versions can overlap by record name. Do not describe 849 versions as 849 distinct artifacts. The 31 baseline sets remain Complete; the working parent and four later sets remain In progress.

Existing branches were linked through native Parent references. Customer Update rows were not bulk-moved or rewritten. The completed baseline was not reopened. Its current batch-base metadata follows the new hierarchy; the preserved original export remains unchanged.

## Captured later metadata

The Global delta contains exactly three INSERT_OR_UPDATE Customer Updates:

- Scripted REST API **SCC Voice Context**.
- Scripted REST Resource **Append caller context**.
- Server-only Script Include **SCCVoiceCallerContext**.

The installed native Add to Update Set list action captured the API and resource together, then the helper. The form action first encountered a mandatory Default ACLs validation message; no security field was changed. The supported list capture serialized the existing records without editing them. The specific Global delta was temporarily current, and the original Global application/update-set context was restored and verified.

The additional existing custom-skill-graph branch holds later context, agent, transformer, execution-ledger and access metadata. It is included intact for review, including its empty scoped child. Inclusion in a working hierarchy does not approve its security design or make its bindings portable. Existing older and newly captured versions must be compared during target preview; choose the intended revision deliberately.

The Greeting Context Fix branch includes an existing DELETE Customer Update for an obsolete separate vision-model record. No model record was deleted by this consolidation. Review that existing target deletion before any eventual import. The context implementation also contains a source-specific provider-application binding that needs target resolution.

## Integrity and preservation

| Evidence | Verified scope |
| --- | --- |
| Canonical source snapshot | 17 exact code/prompt fields across 16 native records; all match the final 19 October field ledger. This snapshot is not presented as the latest live source. |
| Original 2.0 XML | 5,028,890 bytes; SHA-256 `7cce5efc22353bb64f5f3ef36de54d4092c3d7c59dc961bfe8d412647b6e7003`. |
| Original 2.0 ZIP | 1,326,504 bytes; SHA-256 `4a9d059b2d4c5c985b7094635df2cb5f81395d8c3fee350b51d2298e6fb094ca`. |
| Fresh baseline-only native export | All 812 pairs of record name and payload hash, including multiplicities, match the original. Header/export metadata differs. It does not contain the later deltas. |
| Later Global capture | Three exact rendered Customer Update payloads and the native membership observation are preserved privately. |
| Local evidence archive | Original artifacts, earlier documentation, manifests, native observations and a screenshot of the central hierarchy are retained outside public release content. |

The baseline contains 783 distinct CU names, 26 shared names and 29 additional version occurrences. Its 32 serialized headers represent 31 unique sets because the root repeats identically. The 17 protected compatibility entries remain excluded; their opaque XML was not opened. Two native parent AI configurations remain target prerequisites.

The source-snapshot directory has a scoped Git byte-preservation rule. Existing prompt whitespace and line endings are retained, and staged file bytes are checked against the ledger rather than normalized during consolidation.

## Remaining transport and acceptance work

Before releasing 2.1 and accepting it on a target:

1. Complete dependency and current-source coverage review, including actual payload scope versus each set's application. The known later branches are now grouped, but membership alone does not prove every live change has been captured.
2. Review overlapping revisions, the existing DELETE, role/ACL/ECC authorization metadata, and source-specific bindings. Preserve normal target access controls and establish the intended least-privilege configuration.
3. Confirm target release, Store app versions, entitlements and native parent configurations. Prepare the target-local credential, endpoint and operational-binding plan.
4. When source review is complete, close the reviewed sets using the native process, export the complete batch, and record its manifest and hashes. Source completion and export do not establish target acceptance.
5. Retrieve the exported batch on the target, resolve all native preview findings across the entire batch, and import only after review. Configure target-local credentials, endpoints and mappings, then record runtime acceptance. No target import was performed in this task.

The [Community article](community-post.md) explains the configuration layers and their limits. It is a draft for manual publication with [seven pending screenshots](screenshots.md). AI Agents and AI Voice have separate planned article briefs. No Community post or package has been published, no provider/model routing has been changed, and no inference, audio or business operation was run for this consolidation.
