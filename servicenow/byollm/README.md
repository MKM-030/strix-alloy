# BYOLLM ServiceNow source snapshot

These are exact reviewed copies of the project's own native ServiceNow code as of 19 October 2026, consolidated locally on 27 October. The source manifest binds every copied field to the existing final field ledger. No source was deployed or freshly compared with the live instance by this local consolidation.

`model-adapter/` preserves the JSON-boundary chat adapter, its request delegator and the matching response transformer. `prompt-mirror/` prepares suitable existing prompt graphs while preserving provider selection. `voice-policy/` projects native assistant settings, resolves the private persona route and validates policy references. `voice-auth/` preserves the final native authorization resource with the opaque-OAuth correction.

Automation, apply and serialized-execution gates default to false. These files are review sources, not an installer or an activation command. Pending `CustomLLMManager`, private bootstrap files and older JWT-shaped-only variants are excluded.

`SOURCE-FIELD-LEDGER.json` preserves all 17 final code-field hashes and 14 message hashes. All 17 code fields have exact sources here: eleven unchanged standalone files and six AIA prompt fields extracted from the existing public 2.0 XML. Every extracted UTF-8 field exactly matches its final ledger hash; its original record, scope, field and export hash are in the source manifest. The original native export remains the transport artifact.

The existing ServiceNow Voice 2.0 export contains 31 unique update sets and 812 customer-update versions from six public families. Its original XML/ZIP and historical audits are preserved privately. Compatible native applications, licenses, schemas, provider/flow/validator records, two external parent AI configurations, private target connections and execution bindings remain prerequisites. Fresh target preview/import, complete dependency resolution and universal application are unproven. The 17 protected compatibility entries remain excluded.

See the [canonical BYOLLM documentation](../../docs/servicenow-byollm/README.md) for the consolidated status and future delta-batch work. See [SOURCE-MANIFEST.json](SOURCE-MANIFEST.json) for exact provenance and limitations.
