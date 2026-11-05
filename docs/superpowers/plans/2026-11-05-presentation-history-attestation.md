# Presentation History Attestation Implementation Plan

> For agentic workers: use test-driven development and task-scoped independent review. Root has explicit autonomous/no-questions authorization; source authors perform no native/runtime actions.

**Goal:** authorize optional host-emission metadata without Guest protected-record access or changes to CREATE outcome.
**Architecture:** private per-session nonce; separately bounded caller-authenticated attestation operation on the existing token-first `/api/global/scc_voice_context/updates` resource; native issuance-snapshot grant; Guest finite metadata store; unchanged current secure consumer.
**Tech Stack:** existing Python asyncio/aiohttp/unittest and ES5 native candidates/Node VM tests. No dependencies.
**Spec:** docs/superpowers/specs/2026-11-05-presentation-history-attestation-design.md

## Global Constraints

Use the fixed API/request/receipt contracts in the spec verbatim. Defaults remain false. No old CREATE request/reply changes, OAuth retention beyond original45s, startup wait, token/nonce logs, Guest ACL/role grant, raw-record fallback, business mutation, actual backend-output suppression or native current-request join. Metadata request independent bound<=2s/no retry. Exact operation `attest_presentation_history_v1`; private lease purpose binds the full fixed HTTPS URL plus operation, never a URL fragment. Existing resource authentication metadata/provider checks remain unchanged; actual caller Bearer resolution must be qualified and otherwise fails closed. Native event TTL120s; grant maxAgeSeconds60..3600. Source authors have disjoint file ownership; Root owns Git commits, deployment and actual operations.

## Review Focus

- CREATE succeeds while optional attestation hangs/fails: cleanup and startup must proceed normally.
- A credential is cleared/expired or session stops between validation and task dispatch: no resurrection, foreign use or lost private task.
- Native time differs from host by90s: exact native receipt remains valid without host-time assumptions.
- Guest attempts changed binding/nonces/overflow/replay: no protected reads or unauthorized metadata overwrite.
- Current consumer ownership/profile closes or drifts after issue: history omitted; real outputs remain complete.

### Task1: private lease, optional attestation and producer

Files: modify voice/caller_binding.py,voice/bridge.py,voice/presentation_history.py; add focused voice/native-bridge/test_presentation_attestation.py and update directly affected tests only.
Interfaces: consumes exact spec attestation JSON/receipt and existing immutable CREATE binding. Produces Guest store body with grantNonce; original event DTO and stored receipt stay unchanged.
- [ ] Write failing tests for disabled inert path, exactly one original-deadline sublease, take/clear/expiry/cross-owner rejection, no Bearer/nonce representation or snapshot leak.
- [ ] Run focused tests; observe expected assertions fail before code.
- [ ] Implement separate private <=2s task after the validated owned CREATE gate; no await in startup; no changes to existing CREATE envelopes or outcome.
- [ ] RED/GREEN failure, cancellation, stop, late receipt, host-clock skew and original CREATE/cleanup/input behavior. Exact positive receipt alone enables history; failure erases optional nonce/lease.
- [ ] Run focused new plus affected caller-binding/Bridge regressions, record commands/counts and safe diff. Do not commit shared tree; hand Root files/report.

### Task2: native issuer and grant-scoped store

Files: modify servicenow/byollm/voice-presentation-history/SCCVoicePresentationHistoryV1.js,Context-resource.v1.candidate.js,presentation-history.test.cjs; retain Presentation-grant-resource.v1.candidate.js only as an uninstalled archived alternative; add focused native tests if separate fixture is clearer.
Interfaces: consumes the exact spec body/receipt and grantNonce store extension. Produces JSON issued grant bound to native graph/nonce hash and exact successful stored receipt; includeJSON signature/history flags and transformer contract remain unchanged.
- [ ] Write RED cases for a real caller issuing one exact grant, Guest unable to issue, Guest storing through public provider API with zero protected reads, mismatch/expiry/conflict and realistic serialized storage.
- [ ] Implement issueGrantJSON under current secure caller, disabled by default; existing /updates marked optional dispatch requires its unchanged App token/provider checks plus an actual valid32hex non-Guest GS caller equal to callerUserId, then delegates no business action. Success/failure return before legacy fallthrough; Guest store remains separate and grant-only.
- [ ] Replace Guest producer secure-binding dependency with grant verification and bounded repeated grant consistency checks. Keep consumer current secure ownership/open/profile checks and source provenance explicit.
- [ ] RED/GREEN tests for malicious bindings/nonces/text, native time bounds, stale/closed consumer, exact old resource/caller-note behavior, real output/receipt authority and no source/secret/error logs. All old source baselines preserved.
- [ ] Run affected Node suite, ES5 and Rhino reserved-binding check; report exact paths/hashes and no native action. Do not commit shared tree.

### Task3: Root integration and independent review

- [ ] Compare both task interfaces against the spec; resolve and ledger contradictions before any live change.
- [ ] Run the combined affected suites once after final changes, inspect default flags, sensitive-data paths and raw lineage (including exact mixed-EOL transformer reconstruction).
- [ ] Independent task/whole-feature review of the actual diff and evidence. Address material findings by RED/GREEN; preserve dated native/failed receipts.
- [ ] Root commits the source result only after green scoped evidence; no main integration or live activation implied.

### Task4: ordinary native and runtime qualification

Root only, separately prepared after Source GO: fresh metadata permissions/captures for the existing original resource and class (the new attestation operation is a source-only branch of existing /updates, not a new API parent/resource), HelperRev4/TransformerRev22 guards. No schema/role/ACL changes or readonly-derived field writes. Controlled default-disabled install; exact source/capture readback. Then fresh Bot+Native-only activation with correct private manifest/source pins and preserved model/Gateway/ASR/TTS; idle ownership gates and new once handles. One fresh no-approval call proves real attestation/store/read/include and improved overlap without losing required questions or completion. Goal remains open until appropriate qualification; real device/NAT/hearing limits stay explicit.

## Root route ruling after five-read/zero-write preflight

The ordinary native preflight found the proposed new resource parent immutable. Adapt the existing own `/updates` source only within its existing marked optional-history delta; preserve old token/provider checks and legacy source bytes. Do not create a new API parent/resource or change requires_authentication=false, roles or ACLs. Retain the uninstalled standalone grant-resource candidate as an archived alternative. Python sends the exact attestation operation to `/updates`; the explicit one-use purpose binds both full fixed URL and operation. Root must prove actual platform Bearer-to-GS non-Guest caller resolution on this existing resource in one fresh bounded qualification; otherwise the operation fails closed. Source-level route/lease/receipt tests do not establish that native behavior. The already completed native85 and P2-affected52 checks remain dated evidence; run only focused route-adaptation checks before re-review.
