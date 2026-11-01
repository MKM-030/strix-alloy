# Existing skills: generic Custom LLM prompt preparation

The installed `CustomLLMPromptMirror` adds a provider-specific configuration graph to an existing capability. It does **not clone the skill or capability**, change its active provider selection, or run a model. This is the project's generic platform infrastructure; Voice is one separate consumer of the resulting configuration.

The native helper was read on 28 October 2026: 65,210 characters, Global, active, server-only, SHA-256 `adb86cc1463fd0249df3e68a20626c9a001d0a2b024f7ba0f16bb1e4d8de3865`. Its three execution gates were observed false. This confirms the helper and current controls, not successful execution across every skill, every Business Rule event or a target instance.

Use the [documentation hub](README.md) and [batch status](batch-status.md) for the full platform transport. The unchanged [17-field source manifest](../../servicenow/byollm/SOURCE-MANIFEST.json) remains the dated 19 October snapshot. The separate [generic manifest](../../servicenow/byollm/prompt-mirror/GENERIC-SOURCE-MANIFEST.json) adds the generic rules, manual script, native identities and complete historical infrastructure inventory.

## What is added to an existing capability

The helper discovers definitions through active **Now LLM Generic** mappings belonging to **Now LLM Service**, with the supported Flow implementation contract. It resolves the explicitly configured Custom LLM model and its actual provider mapping, transformer, model alias and definition connection. Matching display names or the first active model are insufficient.

For each eligible source definition it plans the additional Custom LLM definition, prompt configurations and their related options, bindings and validators. Existing capability inputs are verified dependencies. Native definition and prompt insert rules generate their own child records; the helper verifies those real identities instead of duplicating native children or writing calculated read-only fields. Shared validators remain shared dependencies unless an explicitly reviewed contract says otherwise.

The existing `sys_one_extend_capability` identity and its skill remain in place. Existing provider selections, active/default choices and the source graph are checked for drift and preserved. New graph records can carry native `active=true` while the provider remains unselected; those states must not be confused with a platform routing decision. Configuration preparation and choosing which provider/model actually executes a skill are separate actions.

This is a custom implementation with reviewed platform contracts. It is not a universal ServiceNow feature or a promise that every OOTB capability qualifies. The source discovery and Global graph path have bounded historical evidence. Other scopes, protected fields, generator versions and skill-specific input/output contracts require their own review.

## Exact installed components

The common helper is `sys_script_include` **CustomLLMPromptMirror**, ID `2ab7ecdc93441b505c8132d47aba10b1`.

All eight rules below are Global, after insert/update, order 100, with delete/query disabled in the completed infrastructure snapshot. Each has the same [BusinessRule.js](../../servicenow/byollm/prompt-mirror/BusinessRule.js) body and calls `onSourceChange(table, id, previous)` on that helper. Previous routing links make reparenting visible. The native list observation on 28 October confirms the eight existing identities; their full script bodies were not all freshly reread.

| Rule | Source table | Native rule ID |
| --- | --- | --- |
| Custom LLM - Mirror prompt configuration | `sys_generative_ai_config` | `07b7ecdc93441b505c8132d47aba10f8` |
| Custom LLM - Mirror prompt bindings | `sys_generative_ai_prompt_config` | `cbb7a01093841b505c8132d47aba1049` |
| Custom LLM - Mirror definitions | `sys_one_extend_capability_definition` | `cbb7a01093841b505c8132d47aba10a9` |
| Custom LLM - Mirror definition options | `sys_one_extend_definition_config` | `8bb7a01093841b505c8132d47aba10b2` |
| Custom LLM - Mirror definition inputs | `sys_one_extend_definition_attribute` | `8bb7e01093841b505c8132d47aba1012` |
| Custom LLM - Mirror request validators | `sys_generative_ai_request_validator` | `8bb7e01093841b505c8132d47aba1059` |
| Custom LLM - Mirror response validators | `sys_generative_ai_response_validator` | `47b7e01093841b505c8132d47aba1062` |
| Custom LLM - Check shared validators | `sys_generative_ai_validator` | `43b7e01093841b505c8132d47aba10c2` |

The manual entry point is `sys_script_fix` **Custom LLM - Synchronize prompts**, ID `47b7e01093841b505c8132d47aba10f0`. Its exact [FixScript.js](../../servicenow/byollm/prompt-mirror/FixScript.js) source starts with `APPLY=false` and `CAPABILITY_IDS=[]`. An empty list means all definitions found by the qualified source discovery, not all platform capabilities.

The unchanged [16 October record descriptors](../../servicenow/byollm/prompt-mirror/native-record-descriptors.20261016.json) retain their original `prepared_not_installed_or_natively_validated` design status. That field is historical. The completed native export, later receipts and current helper observation are separate installation evidence; the descriptor must not be presented as a current live-status report.

## Controls and state

The helper reads four private, admin-controlled local settings:

| Setting | Meaning |
| --- | --- |
| `custom_llm.prompt_mirror.default_model` | Explicit target model record used as the administrative template; not the active platform provider or a global runtime switch |
| `custom_llm.prompt_mirror.automation_enabled` | Permits event-triggered reconciliation; observed false on 28 October |
| `custom_llm.prompt_mirror.apply_enabled` | Permits product metadata writes; observed false on 28 October |
| `custom_llm.prompt_mirror.serialized_execution_verified` | Required qualification gate for serialized execution; observed false on 28 October |

The current template points to the existing Gemma model record. That observation does not establish the model used by every skill or change any provider choice. The 28 October native export contains no `sys_properties` rows: create all four private, admin-controlled settings deliberately on the target, with the three gates false and an explicitly reviewed target model reference. Source observation of those settings does not mean the export installs them.

Origins, baselines, operation journals and insert-only claims use `u_custom_llm_prompt_mirror_state`. The schema contains `u_key` (64), `u_kind` (16) and `u_payload` (4000), a physical unique index, four table ACLs, two field ACLs and their admin role bindings. Runtime state rows are excluded from transport. A dictionary `unique=true` flag alone does not prove a functioning database index or concurrent claim behavior on a new target.

Normal record and field permissions remain active through `GlideRecordSecure`. The helper does not create its schema, bypass ACLs or disable native Business Rules. An unknown generator, ambiguous relation, protected field, mismatched scope/package, missing prerequisite or manually changed managed target stops the plan. Existing unowned Custom LLM definitions require an explicit reviewed adoption decision; the helper does not silently claim them.

## Dry run and backfill workflow

The preserved manual script is a review source, not an instruction to replay an old installer. Before a future authorized run:

1. Verify the actual installed helper/rules, native generator and dictionary contracts, state schema/index/ACLs, target model, provider mapping and both aliases. Record current source revisions and a private rollback plan. The packaged historical hashes do not establish current live equality for every component.
2. Choose a small set of existing capability IDs and keep `APPLY=false`. The manual script calls `run({capabilityIds: CAPABILITY_IDS, apply: APPLY})` and prints a `CUSTOM_LLM_PROMPT_MIRROR` JSON result. Review each definition's status, issues, artifact count and plan hash. Missing state/model configuration can legitimately block planning.
3. Check that the proposed graph retains capability identity, inputs, validators, conditions, source text and existing provider selection. Resolve `NeedsAdoption`, manual drift, ownership and unsupported-scope findings explicitly. A successful discovery is not permission to apply every discovered variant.
4. After the applicable native execution qualification and an authorized write decision, use a fresh plan. The helper rechecks revisions and claims before writing. Verify native generated children, source/selection invariants and exact readback, then a separate repeated run with no product or state writes. Do not infer idempotency from an HTTP success or a local Boolean.
5. Exercise the intended skill prompt and model route with appropriate positive and negative cases. Only then consider a broader backfill or event automation. This documentation task did not enable gates, run the Fix Script, execute a Business Rule probe or call a model.

Historical source acceptance includes an own Global graph fixture, prompt insert/update through the real rules, a separate NoOp, shared-validator fixtures, state-store checks and overlapping claim transactions. Those are narrow dated proofs. They do not establish all eight event paths, every discovered source scope, live model/agent/Voice acceptance or a clean target import.

## Infrastructure inventory and transport

Infrastructure 1.0 contains **39 Customer Update versions**: 33 Global and six Generative AI Controller. Its root is `933568d093441b505c8132d47aba101d`; the children are Global `d73568d093441b505c8132d47aba101d` and GenAI `ea67e45c93441b505c8132d47aba10dc`. The Global child includes the helper, eight rules, manual Fix Script, one model transformer and the state schema/index/ACL metadata. The GenAI child contains two model records, two aliases, a model transformer and the provider mapping.

Validation 1.0.1 is a later Complete Global set, `6108f2189340db505c8132d47aba10a5`, containing one newer version of the same helper. It adds effective dictionary-field-length checks. Consequently **39 + 1 means 40 transported versions of 39 metadata identities**, not 40 independent records. The baseline helper hash remains historical; the final Validation helper is the `adb86cc…` source preserved here.

Both families already belong to the six-family 19 October 2.0 baseline. Do not add their 40 versions again when counting the working 2.1 hierarchy. The generic manifest verifies their original per-set payload inventories against that unchanged public export and records native identities, code hashes, source revisions, capture applications and composite documentation keys. It does not reconstruct an XML or approve a current target installation.

The documentation revision completed late on 27 October identified later repairs to provider mapping `07ca9d94c3550210b0939bc8a840ddeb` (`prompt_transformation_script`) and Global transformer `bc126377936f8750e7f2b9fa6aba1012` (`request_transformer`), plus a reported duplicate mapping deletion. Those older documentation files correctly retain their then-missing capture evidence. Separate native observations on 28 October now compare the repaired fields with existing captured Customer Updates and show equal field hashes. This resolves that narrow field/capture comparison; it does not by itself prove complete batch membership, safe target deletion, dependency closure or target acceptance. Follow [batch status](batch-status.md) for the current transport decision. Do not restore the older adapter fields over repaired sources.

Native providers, flows, generator rules, dictionary behavior and validators remain target prerequisites. Connections, credentials, local template settings, operational routing, runtime claims and protected compatibility payloads remain private. The later `CustomLLMManager`/worker design is a separate uninstalled approach and must not be substituted for this installed helper and its direct rules.

## Evidence and preserved history

The generic manifest binds the source files to the original public native export and records the current helper/control observations. The original `SOURCE-MANIFEST.json` and 27 October archive remain unchanged.

The ignored `server/.local/byollm-consolidation-20261028` archive preserves the later 27 October technical document, quickstart, three German Community drafts, revision/source-review receipts, original attached evidence and the updated append-only change history. `ARCHIVE-MANIFEST.json` records original paths, hashes and timestamps. Earlier history remains in the separate 27 October archive; newer documents do not retroactively change old source, capture or acceptance claims. No protected/opaque XML was opened.
