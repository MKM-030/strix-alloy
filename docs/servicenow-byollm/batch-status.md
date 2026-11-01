# Fresh-instance BYOLLM batch

The target delivery is **Custom LLM Platform 2.2 - Fresh Instance - NO DELETE 20261028**. Use this delivery for a compatible new instance. The earlier [2.1 aggregate](historical-batch-2.1.md) is retained as source history and is not the import package.

**Later source maintenance, 1 November:** the separate **Custom LLM Platform 2.3 - Halogen Agent Delta - NO DELETE 20261101** is partially applied and not transfer-ready. All 66 reviewed active Agent prompts and the Halogen transformer are updated; the Ledger and WIP application/capture corrections remain. See [the post-run audit](../../servicenow/byollm/halogen-agents-20261101/POSTRUN.md). The sealed 2.2 package, its hashes and preview findings below remain unchanged; it does not contain these later changes.

## Delivery contract

- **809 unique INSERT_OR_UPDATE Customer Updates** in 36 transport headers.
- **Zero DELETE updates, zero embedded delete/delete_multiple transport actions, zero insert/delete conflicts.**
- One selected version per update name. Every deleted source identity is excluded entirely, including its earlier INSERT version.
- Retained application identities, configuration fields, scripts and nondestructive translation/price inserts remain tied to native source evidence. Scope changes affect transport wrappers only.
- This is an explicitly **derived** fresh-instance delivery, not an untouched native export or an upgrade/cleanup package for an already customized instance.

The builder uses the unchanged native 868-version export and the later completed native notice-language correction. It removes historical deletion actions and duplicate versions, preserves their selection/exclusion ledger, and replaces the older notice helper with its verified native revision. It never reconstructs source code from chat output or opens opaque compatibility XML.

The [transport coverage](transport-coverage.md), [target runbook](transport-runbook.md), [source manifests](../../servicenow/byollm/README.md) and private delivery manifest distinguish exported configuration from target-local prerequisites.

## Native verification

The derived XML has been loaded into the source instance's Retrieved Update Sets area without committing application changes. SDK readback confirms the 36 headers, 809 unique updates and retained payload text; the native batch preview is recorded separately from target acceptance. No remote updates have been blindly accepted, skipped or committed.

A same-source preview is a format/dependency check, not acceptance on a fresh target. The known native parent configurations and source-specific runtime bindings require deliberate target resolution. Current preview details and final artifact hashes are recorded in the release manifest and target runbook.

The [final verification record](release-verification.md) confirms all 809 payloads and wrapper identities match the final 4,542,611-byte XML. Native preview completed with five unresolved errors: two newer LOCAL ONLY deployment versions and three references to two absent native parents. No finding was accepted or skipped and no application change was committed.

## Platform content and final script

The package covers the general provider/model/transformer/prompt infrastructure, the installed [Prompt Mirror with eight Business Rules and manual Fix Script](prompt-mirror.md), state schema/index/ACL records, model migrations, and captured Agent/Voice metadata. It is broader than Voice configuration.

The separately preserved [final executed capability-based copier](capability-prompt-copy.md) is the exact source that completed the 14-capability repetition with 292 unchanged records and 13 retained validator relations. Its computed request-token correction is preserved. It is different from the later Mirror and from uninstalled manager proposals. Configure its source-specific values and review its write/default behavior before any target execution; it has no dry-run switch and is not auto-run by this package.

## Target-local setup

The native export does not supply the actual ACT provider allowlist/fallback/routing row or any of the four private Mirror property rows. Set those deliberately on the target; keep all three Mirror execution gates false until qualified. Concrete prompt model selection remains separate from the administrative model template.

Credentials, aliases/connections, endpoints/TLS/network configuration, operational execution mappings and host/model/speech services remain target-local. The intentionally LOCAL ONLY execution-mapping branch is not copied as a fixed default. Compatible Store apps, entitlements, native flows/generators/validators and the two external parent AI configurations remain prerequisites. A captured SCC Vision helper does not supply its missing private example configuration.

No model, speech service, microphone, inference request, business action, backfill or runtime test was started by this consolidation. No configuration was committed on the source or a new target. Native received-update-set staging and preview are metadata-only verification.

## Documentation and provenance

The [technical documentation](master-manual.md) is the primary operating manual. There are exactly three full English Community drafts: [general platform](community-post.md), [AI Agents](ai-agents-follow-up.md), and [AI Voice](ai-voice-follow-up.md), with [17 pending author screenshots](screenshots.md).

The [chat reconciliation](chat-reconciliation.md) records referenced sources, recovered final implementations, dated results and retrieval limits. Historical code/export/manifests remain intact in the central worktree and separate private archives. Public article publication and a generally supported installer are not implied.
