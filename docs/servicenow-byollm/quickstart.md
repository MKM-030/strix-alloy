# ServiceNow BYOLLM quickstart

Revision: 28 October 2026. The fresh-instance delivery is **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028**. Read [batch status](batch-status.md) for the exact artifact and [master manual](master-manual.md) for configuration.

The final derived XML contains **809 unique INSERT_OR_UPDATEs and 36 headers**, with zero outer/embedded deletes or conflicts. It combines the untouched native 868-version Platform 2.1 export with an exact same-identity native notice-helper overlay; the older aggregate is historical evidence only. **Use 2.2 for fresh compatible instances, not upgrades of used targets.**

1. **Inventory the fresh target.** Record release/patch, Store apps, licenses, roles, region, entry points, activation and recovery plan. Prepare approved model infrastructure and target-local credentials. Update sets do not install weights, speech services, DNS/TLS or host runtimes.

2. **Review governance in AI Control Tower.** Inspect allowed providers, fallback, required approvals and impact. For an agreed custom-only policy, deliberately select Custom LLM Provider. With fallback disabled, unsupported active systems must be deactivated. No `sys_gen_ai_routing_selection` rows are transported; configure ACT policy locally.

3. **Register models and connections.** In Skill Kit → Providers and Models, verify provider/API, technical model identity, mapping, implementation, both aliases, credentials, token limits and transformers. Preserve native protections and owning scopes.

4. **Use the correct capability-copy path.** The [final executed copier guide](capability-prompt-copy.md) and [source manifest](../../servicenow/byollm/capability-prompt-copy/SOURCE-MANIFEST.json) preserve the capability-based script: its historical repeat processed **14 capabilities**, with **292 unchanged records**, **13 existing validator links skipped**, and zero writes. Its `request_tokens` fix excludes that computed field from copy and change detection. Review its target adaptations and historical default-changing behavior before reuse. It preserves existing skill/capability identities.

5. **Treat the eight-rule mirror separately.** `CustomLLMPromptMirror` and **Custom LLM - Synchronize prompts** prepare qualified provider graphs while preserving existing provider selection. Keep the Fix Script's `APPLY=false`; review selected `capabilityIds`, generated children, validators, ownership and blockers. An empty selection means qualified sources, not every platform feature. Manually configure all four mirror properties: the export contains no `sys_properties` rows. `default_model` is a preparation template, not routing; keep all three gates false until qualified.

6. **Set provider scope deliberately.** Inspect Admin → Manage model providers at instance, group and skill levels. Apply an intended instance baseline before exceptions. A later instance-level change overwrites existing skill/group customizations. A provider alone does not choose among its registered models.

7. **Choose the concrete prompt model.** Skill Kit → skill → Edit prompt → selected prompt → Prompt settings → Model, or the release equivalent. Verify conditions, default, tokens, output format and business contract for each entry point.

8. **Load and preview the exact 2.2 artifact.** Follow the [transport runbook](transport-runbook.md) for the final 4,542,611-byte XML and hash. All nine deleted identities, the stale insert and 49 older repeated inserts are excluded; 95 serializer deletion nodes were removed. Five wrapper reroutes leave zero scope/container mismatches. Two parsers verified all 809 selected primary-field contracts and seven current source code fields across five records. The native notice helper is revision 4 in the same wrapper. Do not re-add historical repair/deletion branches or earlier mirror versions.

9. **Verify text, Vision, agents and Voice separately.** Preserve the SCC Vision dispatch. Its helper is included, but its historical referenced AI configuration is absent from the public delivery; resolve the private/example graph. Agent orchestration and tool-skill models have separate routes. Voice also needs STT/TTS, caller controls, media/channel validation and result correlation.

10. **Complete target acceptance and deployment.** Resolve native preview findings before commit, verify installed records and local bindings, then test, finalize, publish and activate through the supported lifecycle. Repeat actual endpoint/model, validator, access and fallback checks. Keep automation gated until qualified.

The final XML loaded on the **source**, with SDK readback confirming 36 headers, 809 unique CUs, exact payload-text/wrapper equality and zero deletes. Final native preview completed with five unresolved findings: two newer LOCAL ONLY deployment versions and three missing-parent references. The notice-helper conflict is resolved; see [release verification](release-verification.md). Two newer source deployment versions belong to a LOCAL ONLY set and are intentionally excluded. The two absent native parent configurations remain prerequisites. No commit or actual new-target import is established, and runtime acceptance remains open.

[Configuration boundaries](configuration-boundaries.md) · [Official sources](sources.md) · [Full platform article](community-post.md) · [Full AI Agents article](ai-agents-follow-up.md) · [Full AI Voice article](ai-voice-follow-up.md) · [Screenshot plan](screenshots.md)
