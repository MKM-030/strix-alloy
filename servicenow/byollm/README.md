# BYOLLM ServiceNow source snapshots

The original [source manifest](SOURCE-MANIFEST.json) preserves exact copies of 17 native code/prompt fields as of 19 October 2026, consolidated on 27 October. That frozen manifest and its sources remain unchanged.

The separate [generic mirror manifest](prompt-mirror/GENERIC-SOURCE-MANIFEST.json) adds the eight shared Business Rule callers, manual backfill script, installation provenance and infrastructure inventory. The current helper matches the final Validation 1.0.1 source. [Current sources](current-20261028/SOURCE-MANIFEST.json) preserve independently read 28 October mapping/adapter/helper fields and their native export comparisons. These dated manifests must not be merged into a claim that every historical file is the latest live revision.

`model-adapter/` preserves the JSON-boundary chat adapter, its request delegator and the matching response transformer. `prompt-mirror/` prepares suitable existing prompt graphs while preserving provider selection. `voice-policy/` projects native assistant settings, resolves the private persona route and validates policy references. `voice-auth/` preserves the final native authorization resource with the opaque-OAuth correction.

Automation, apply and serialized-execution gates default to false. These files are review sources, not an installer or an activation command. Pending `CustomLLMManager`, private bootstrap files and older JWT-shaped-only variants are excluded.

`SOURCE-FIELD-LEDGER.json` preserves all 17 final code-field hashes and 14 message hashes. All 17 code fields have exact sources here: eleven unchanged standalone files and six AIA prompt fields extracted from the existing public 2.0 XML. Every extracted UTF-8 field exactly matches its final ledger hash; its original record, scope, field and export hash are in the source manifest. The original native export remains the transport artifact.

The existing ServiceNow Voice 2.0 export contains 31 unique update sets and 812 customer-update versions from six public families. Its original XML/ZIP and historical audits are preserved privately. Compatible native applications, licenses, schemas, provider/flow/validator records, two external parent AI configurations, private target connections and execution bindings remain prerequisites. Fresh target preview/import, complete dependency resolution and universal application are unproven. The 17 protected compatibility entries remain excluded.

The completed native 2.1 export (868 versions) is historical source evidence. The **2.2 fresh-instance delivery** selects 809 unique records, excludes all deleted identities and older duplicates, removes embedded serializer deletion actions, and incorporates the later native notice-language fix. It contains zero transport deletes or insert/delete conflicts. Its derivation and target limits are explicit in [batch status](../../docs/servicenow-byollm/batch-status.md).

The [capability-based final manual copier](capability-prompt-copy/SOURCE-MANIFEST.json) is preserved separately and byte-exact from the successful native history entry. See its [operation and evidence guide](../../docs/servicenow-byollm/capability-prompt-copy.md). It must not be conflated with the installed eight-rule Mirror or later manager proposals.
