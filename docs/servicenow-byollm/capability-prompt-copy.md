# Final executed capability-based prompt copier

The requested manual source is the [final executed capability-based script from 13 October 2026](../../servicenow/byollm/capability-prompt-copy/core-clone-delta-final--354c875b93ffc754e7f2b9fa6aba10c4.historical.js). Its exact source SHA-256 is `dc390ee11c3abfb71d8f4bcd252b2ff9bfa92b93b92bd844a69ca27787e25db2`.

This is the historically working manual script, not the later `CustomLLMCapabilityManager` proposal. It prepares provider-specific definition, prompt and binding records for **existing capability identities**. It does not clone a skill or insert another capability. Its preserved code is executable native Scripts - Background source, but this copy is an audit/reference artifact: it was not executed, adapted to a new instance or approved as a current installer by this consolidation.

The [source/provenance manifest](../../servicenow/byollm/capability-prompt-copy/SOURCE-MANIFEST.json) and [original provenance receipt](../../servicenow/byollm/capability-prompt-copy/core-clone-delta-final--354c875b93ffc754e7f2b9fa6aba10c4.historical.provenance.json) identify the exact execution and its limits. For the broader platform and fresh-instance transport work, start at the [BYOLLM hub](README.md) and [batch status](batch-status.md).

## What was actually executed

Native history `354c875b93ffc754e7f2b9fa6aba10c4`, dated **13 October 2026, 16:20:31 UTC**, contains this 38,034-character source. The preserved history entry is `live-history-sources-complete.json#/rows/228` in the private documentation evidence.

The final native result reports:

```json
{
  "ok": true,
  "capabilities": 14,
  "batch": "",
  "writes": 0,
  "unchanged": 292,
  "validatorLinksInserted": 0,
  "validatorLinksSkipped": 13
}
```

This establishes the reported successful repetition for the **14 configured capabilities**. It does not establish a successful run for every platform capability, current equality of all destination records, clean target import, atomic rollback, or live model/agent/Voice behavior. The empty batch value belongs to that no-change run; it is not a missing newly created export.

## The final change that removed false write churn

`sys_generative_ai_config.request_tokens` is calculated from the selected target model. The final script excludes it in **both** the field-copy loop and `hasChanges`. Excluding it only during assignment would still make the comparison report changes and cause repeated saves.

The preceding read-only [Request Tokens diagnostic](../../servicenow/byollm/capability-prompt-copy/request-token-diagnostic--2c4b8b1793ffc754e7f2b9fa6aba10a1.historical.js) is also preserved exactly. Native history `2c4b8b1793ffc754e7f2b9fa6aba10a1`, row 226, dated 13 October 16:16:04 UTC, identified 59 differences in that calculated field. Its diagnostic save path has no insert/update call. Earlier sources reported 92 and 65 writes; the final corrected source reports zero writes and 292 unchanged records.

The script also resolves Request and Response validator relations using the installed dictionary. In that historical schema, Request bindings support `document_table`, `document_id` and `definition`; Response uses `definition` as a Document ID and has no `document_table`. Existing matching relations are skipped. Validator scripts are referenced rather than generally copied or rewritten. A preceding native run added 13 relations; the final repetition skipped those same 13.

## Configuration in the preserved source

These are literal **historical source-instance values**, not settings to carry blindly to a fresh target:

| Parameter | Preserved value / scope |
| --- | --- |
| `capabilityIds` | The exact 14-ID selection in the source and manifest |
| `settings.nowFlow` | `936e514a53b3b110f028ddeeff7b128c` |
| `settings.customFlow` | `af9702d0c3110210b0939bc8a840dd2c` |
| `settings.alias` | `a7b19ad193ff43d05c8132d47aba10c7` |
| `settings.model` | `halogen-v2` |
| `settings.provider` | `Custom LLM Provider` |
| `settings.providerFilter` | `Custom LLMcustom_api` |
| `settings.mappingPrefix` | `custom_llm.clone.map.` |
| `settings.sourceDefinitions` | One explicit source-definition override |
| `settings.existingCopies` | Five previously established source/target identity mappings |

The script is self-contained JavaScript with no external code-file dependency. It does depend on existing native capabilities, source definitions, Flow implementations, model and alias records, dictionary contracts, validator relations and appropriate native scope permissions. The exact source uses the recorded native update-set context and capture APIs; those historical assumptions require fresh verification on any target release.

There is **no dry-run switch** in this final file. It plans the configured capabilities, then can insert/update metadata and change definition defaults. It uses `setWorkflow(false)` for direct writes. Defaults are changed after the copies; an error attempts to restore already changed defaults but does not transactionally undo earlier copies. Therefore, preserving this final source is not a recommendation to replay it over the current instance or a fresh installation.

## Relationship to Prompt Mirror and manager proposals

| Implementation | Evidence and role |
| --- | --- |
| This final manual copier | Actually executed on 13 October for 14 capabilities; final reported no-change repetition. Explicit capability list and source-instance configuration. |
| [CustomLLMPromptMirror and its eight Business Rules](prompt-mirror.md) | Separate later installed implementation, plus its own manual Fix Script. It discovers eligible sources, verifies native generated children and preserves active provider selections. Its execution gates are currently disabled. |
| `CustomLLMCapabilityManager` | Historical proposal and proposed UI actions; installation/execution was not established by the preserved audit. It is not this final manual script. |
| `CustomLLMManager` with worker/InitialCaller | Separate locally implemented manager design; its native installation remains unproven in the relevant historical receipts. |

The implementations must not be collapsed into one apparent version or executed together as a combined installer. The older manual copier changes defaults; the later Mirror is designed to preserve provider selection. Their source, configuration and acceptance evidence are different.

## Fresh-instance transport boundary

The final manual source and its diagnostic are now centrally available without changing their behavior or original evidence. The separate **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028** delivery was derived from the preserved native exports, verified against selected current records, and checked by an independent parser. It was not created by rerunning this historical script.

The historical aggregate contains obsolete DELETE versions and embedded keyed serializer `delete_multiple` actions in some otherwise INSERT_OR_UPDATE payloads. The separate derived delivery excludes all versions of deleted identities, selects one retained version per update name, and removes the reviewed destructive serializer nodes with an exact ledger. It contains 809 unique updates and no outer or embedded deletion actions. The manual script's no-change result is separate evidence and does not certify the package. Deleted source identities and stale earlier inserts must not be reintroduced by replaying historical provider-template or clone scripts.

Current adapter repairs, the newer Voice/agent business context, source-specific references, native prerequisites and target preview remain separate concerns. No model, business operation, historical script or instance update was run to create this source reference.
