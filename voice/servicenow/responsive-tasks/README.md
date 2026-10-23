# Responsive tasks v2 — inactive owned package

This is a reviewable, offline prepared package. Nothing was applied to ServiceNow. All Script Includes and REST resources import **inactive**. `LocalLLMVoicePlatform.authorize()` unconditionally denies control/commit even if a property or local manifest says qualified. The native voice principal is not established, and the existing voice agent still has its original unguarded submit binding. **Full mode, independent execution contexts and new business writes remain unavailable.**

## Package contents and installation boundary

`responsive-tasks.inactive.update-set.xml` contains actual Global table/dictionary, mandatory unique-field, deny-all ACL, append-only business-rule, Script Include and versioned REST resource records. `schema-manifest.json` records their names, constraints, source hashes and disabled routes. `build_package.py` builds deterministically offline; `validate_package.py` checks XML inventory, inactive state, uniqueness metadata and source parity. Dictionary `unique=true` requests a platform-created unique index. It is **not evidence** that an index exists or arbitrates real concurrent transactions. Update-set preview/import/schema compatibility and database-index installation have not been exercised on an instance.

Review the XML as a retrieved update set, preview collisions and platform schema/field compatibility, and verify every generated dictionary/ACL/index against the actual instance before any installation. The set contains restrictive ACLs but no roles, role assignments, cross-scope grants, credentials or changes to existing native records. Table data is append-only, including receipt evidence. The `u_data` envelope is immutable authoritative data; explicit owner/task/service/agent/tool/proposal/hash fields support bounded lookup and auditing. No public table/ledger API is provided.

The Global registry route is only a disabled-capability diagnostic: it deliberately returns no principal, service or authorized agents. It is **not** the completed native registry integration. `native-registry-v2.candidate.js` is a separate proposed read-only resource in existing `sn_voice_aia` scope `022bd6e9b720a61081fee3fdde11a9df`. It uses the source-proven same-scope native service/auth checks, rejects test mode, guest and opaque credentials, checks VoiceServiceInfo binding, and reads authorized IDs without a cache builder. The principal is explicitly a platform actor, never an inferred human caller. Its 60-second snapshot expiry is not token lifetime or a grant of write authority. Tool permission, cross-call resume and safe-write flags are false. New native REST definition/authentication/accessibility metadata has not been read back; therefore this source is deliberately excluded from the Global XML. Do not replace the existing Authorized Agents resource or v1 response.

`prepare-only-tool.js` is a prospective native tool body returning bounded **untrusted candidate** fields, without persistence, confirmation or order. Its native tool/binding metadata is not imported because that migration is not yet qualified. It must replace the responsive agent's ability to submit directly, not merely be added beside the old order tool.

## Static SCC delegation

`LocalLLMSCCOrderBusiness.js` contains the exact existing SCC IIFE body from `../scc-laptop-order-tool.js`, 4383 bytes, SHA256 `79f7a17ccc0887ade5004cf10bb12df4a78012ba583590474f84f6cb443f7ffe`, wrapped as a server method. No requester/manager/date/catalog/cart/receipt validation was changed. This is prospective source, not a second active business implementation. `legacy-wrapper.candidate.js` is the future static delegation to that one helper. No existing tool, M2M or source was edited.

A future joint migration must fresh-read/compare the legacy source and metadata, preserve a rollback export, install and verify the canonical helper, replace the legacy body with the static wrapper, and remove the unguarded order M2M from the responsive agent's allowed tools. Verify ordinary cross-scope accessibility to the helper; initial Script Include access is package-private, with no new access grants. Do not enable the wrapper alone. No stored script evaluation, caller-selected class/table/URL, SNC bypass or local CartJS implementation exists.

## Prospective API

Base: `/api/global/scc_voice_tasks/v2`. These are owned proposed routes, **not deployed native endpoints**. Global auth remains hard denied until a real platform policy is implemented and qualified.

| Method/path | Bounded contract |
| --- | --- |
| GET `/registry` | Disabled-capability diagnostic only, null capability revision |
| POST `/tasks` | `command_id`, `objective` (1–4000 characters), `context_version:1`; server allocates task ID and immutable owner/service/agent/tool/registry binding |
| GET `/tasks/{id}` | Authorized latest revision, operation receipt/status, one latest correlated transition event; does not claim complete historical delivery |
| POST `/tasks/{id}/commands` | `command_id`, `expected_revision`, `kind`, `context_version`; exact per-kind fields below |
| GET `/operations/{id}` | Authorized operation/claim outcome and authoritative stored request/item references; no dispatch/replay |

`prepare`/`amend` require a bounded proposal with employee_name, start_date, delivery_location and manager_name. `confirm` requires proposal_id and explicit utterance_ref; `commit` requires proposal_id, confirmation_id and immutable operation_key. `cancel` has no additional fields. Unknown/duplicate control fields, forged predecessor, stale revision, expired authorization/proposal and wrong owner/service/agent/tool fail closed. Preparation does no business work. Every successor consumes the mandatory unique `task-id:predecessor-id` slot; amendments clear old preparation/confirmation. A committed predecessor rejects corrections as deferred. Command identity hashes include exact bindings and payload. An operation has a separate mandatory unique dispatch claim. Null/failed insert cannot dispatch. Unknown claims are never reclaimed, even after expiry. Real request-only partial results remain unknown while retaining their request reference.

Events bind task, operation/command, context_version, event ID and sequence. Operation receipts are authoritative evidence only after the platform implementation and transaction behavior are qualified. Source tests do not prove claim durability before CartJS: a same-transaction insert could roll back after a side effect. This gap is deliberately blocked by the production policy, not hidden by the unique-index simulation.

## Local private adapter/store contract

`OwnedTaskExecutor` leaves `LegacyVAExecutor` unchanged. It uses exact configured HTTPS origin and private in-memory Authorization provider, disables redirects/proxy inheritance, bounds response bodies and rejects duplicate JSON fields. It persists the exact owned command and local dispatch before I/O. A repeated operation never resends; changed payload/task binding conflicts. Lost/malformed/redirected responses become unknown. Prepare acknowledgement means awaiting input, never a completed order. `commit()` and `qualify()` always deny; no JSON Boolean or source hash enables them. No native call is wired to this candidate adapter by this task.

Private `TaskStore.record_receipt(operation_id, *, request_ref='', execution_ref='', receipt=None)` accepts only bounded references and allowlisted statuses; bound values cannot change, and missing execution evidence may be added. A receipt alone does not settle. `record_owned_dispatch`, `executor_binding` and `observe_owned` are executor-private seams, never public routes. Event IDs and source sequences deduplicate durably; older context/out-of-order observations remain historical, without rebinding a newer question or regressing the source cursor.

Private reconciliation workflow when no live status adapter exists:

1. An authorized operator inspects the actual ServiceNow operation/request/item using ordinary authorized access, verifies its causal association with the exact local task/operation/context, and retains an external observation record. A recent similar RITM, timeout, HTTP 202 or local Boolean is insufficient.
2. The trusted operator integration calls `record_receipt` with the verified request/execution reference. No credentials or free-form source documents enter the journal.
3. It calls `reconcile_unknown(operation_id, outcome=..., evidence=..., replies=[])`, where outcome is succeeded/failed/cancelled and evidence has exactly source (`operator` or `authority`), observer_ref, observation_ref, task_id, operation_id, context_version, outcome and at least one matching bound request_ref/execution_ref. The private caller authenticates the operator/observation; the store enforces correlation, not human authentication.
4. The transaction records `operation_reconciled`, settles once, suspends queued follow-ups and releases the unresolved reservation without resubmission. Exact duplicates are idempotent; conflicting evidence/results reject. There is no automatic legacy reconciliation endpoint or retry command.

Global LegacyVA singleflight and global unknown blocking remain. No independent context ID is accepted from an alias/configuration, and no parallel agent claim is made.

## Required live evidence before any promotion

- Native resource authentication/accessibility metadata, actual service/actor binding, authenticated expiry/revocation and wrong-principal denial; no assumed human caller or admin-test shortcut.
- Current active agent/assistant binding, execution rights, deployment allowlist and exact tool-M2M membership at creation and dispatch; response source revision plus actual server capability qualification revision.
- Complete reviewed SCC static extraction/wrapper migration and removal of responsive unguarded submit bindings.
- Installed unique indexes and instance concurrent successor/operation/claim tests, including failed/null insert behavior and transaction rollback boundaries.
- A supported durable claim transaction committed before business dispatch, with exact operation→REQ/RITM causal linkage and lost-response reconciliation. The existing recent-RITM lookup is not that linkage.
- Actual safe-read wire envelope/status/event tests and native scope accessibility. Independent background continuation/collector/restart/two-context qualification remains a separate absent capability.

No orders, notifications, role changes, network calls, live deployment or models were used to create this package. Local Node/Python tests use synthetic executors and platform doubles only.
