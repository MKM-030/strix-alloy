# Local Caller Create Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Native security writes wait for the explicit seven-record approval; source preparation proceeds now.

**Goal:** Create the Voice conversation in the verified original caller context while preserving the existing common SDK/WS and asynchronous dialog.

**Architecture:** A narrowly granted owned ServiceNow POST endpoint performs one native synchronous CREATE under the original OAuth caller. The local adapter binds its filtered response into the existing private create/refresh/start lifecycle. Existing clients and their original records remain intact; their additional own-endpoint relation is explicit and separately approved.

**Tech Stack:** Existing ServiceNow native UI/SDK, ordinary metadata/capture, Python/aiohttp Bridge, portable Node VM and Python tests, existing SDK/RTC probe.

**Spec:** `docs/superpowers/specs/2026-11-02-local-caller-create-design.md`.

## Global constraints

- No security metadata writes until concrete review and explicit approval.
- Exactly seven proposed new functional/security records; separate own WIP/captures.
- Fixed service8aa131d793f787105c8132d47aba1095, profilec623e20f93374354e7f2b9fa6aba1081, agent a6337ddf93f787105c8132d47aba1058, inbound scc-local-voice.
- Original authenticated GS admin; no SDK administrator proxy, client UID, role/ACL change, global B2B policy, useraccount scope or cloud route.
- Preserve old native client/profile/scope/source rows and all old relationships; add only the two reviewed new relationships to them.
- Do not write denied scope/package/namespace/parent fields. Use and verify normal native UI defaults.
- Preserve model, own voice and speech/runtime generations; no automatic model switch.
- No order submission, blind retries, uncertain native replay or automatic deletion.

## Review focus

- The new grant applies dynamically to all existing Voice Agent client tokens; server service/admin checks must remain exact.
- A public class is not proof of runtime cross-scope permission; fail closed on native denial.
- A synchronous native response may differ from callback shape; freeze the actual parser and reject ambiguity rather than fabricate IDs.
- A callback can race the synchronous response or cleanup; at most one refresh/start transition may occur.
- Creating under authenticated GS is a supported correction hypothesis, not proof that the later asynchronous worker runs as that user.

## Task 1 — freeze exact new source and security creation review

**Owner:** positive_name_backend_trace, coordinated with Root and contract reviewer.

**Files:** private `entry-workflow/local-caller-create/` source/tests/review package; later owned canonical `servicenow/byollm/voice-auth/` source/tests.

- [x] Read the stored public B2B processPayload sync contract and confirm filtered return schema with local owner.
- [x] Write failing portable tests for strict input, GS/service/admin authority, fixed empty CREATE, original headers, one native invocation and stripped genuine native tuple.
- [x] Implement only the owned resource candidate; preserve all existing sources.
- [x] Run focused source/syntax tests and inspect results.
- [x] Complete exact names/path collision checks and actual UI creation-field/default contract for seven new records; prepare review, parameters and reversal.
- [x] Root independent review; explicit seven-record security approval received before native writes.

## Task 2 — private original-caller synchronous CREATE transport

**Owner:** authenticated_voice_transport, isolated candidate until Root integration.

**Files:** `voice/bridge.py`, `voice/caller_binding.py`, focused `voice/tests/` regressions; existing Native interfaces remain unchanged.

**Interface:** consumes the exact approved POST path and filtered create result from Task1. Produces the same existing ConversationBinding and one guarded start/refresh transition.

- [x] Write failing tests for only-one credential use at exact destination, strict own request/cookie/caller binding, sync/callback duplicates, absent/malformed native tuple, deadline and cleanup races.
- [x] Add optional exact `caller_create_api_path` selection, one CREATE credential claim and strict filtered response handling. No fallback/retry.
- [x] Preserve distinct refresh and immediate credential retirement; keep later B2B requests credential-free.
- [x] Run meaningful local regressions and source checks; Root independently reviews the diff and freezes final pins.

## Task 3 — approved native creation and independent readback

- [x] Record actual approval before any new security/UI Save.
- [x] Select own Voice AIA WIP in both UI and SDK; preserve previous contexts.
- [x] Create only the seven reviewed records using normal UI/context for read-only-derived fields and normal rights for writable fields. Uncertain policy-save observation was independently read back; no save was repeated.
- [x] Independently compare complete old/new source rows, exact old memberships and new relation IDs, same-application captures and no deletes.
- [x] Integrate verified owned source/tests and new local path config; keep current runtime code untouched until idle activation.

## Task 4 — bounded real proof and durable completion

- [x] Exact idle activation of affected adapter only through normal venv launcher; preserve all other service/model generations.
- [x] New normal native Voice Agent PKCE in a fresh restricted folder, one new frozen SDK/RTC name-only probe with all updated source/config pins. V5 failed before any caller input; immutable failed receipt retained.
- [ ] Correlate actual conversation/plan/user/root/child/model/tool records using clock-adjusted native window; prove original caller and normal continuation, not merely CREATE/refresh acknowledgement.
- [ ] Require cleanup ACK/capacity0 and remove own temporary bearer; no order consent.
- [ ] Update docs/checkpoint, commit verified owned changes and restore both UI and SDK app/set contexts. Report physical-device limits separately.

Root integration: owned source d4b925b0..., integrated checks692/692 byollm +75/75 Python pass. Marcel approved Voice sign-in; all seven records and seven captures passed independent full readback and a second local audit. WIP6b0e4fb59314d3185c8132d47aba1090. Bot21648/Native26496 activated once, all other services/model generations preserved. V5 own CREATE succeeded, but its actual VA worker remained guest/guest and denied the original SCC child before any GenAI/tools or caller input. HTTP caller creation did not solve native channel session sign-in. No further probe without a concrete supported-protocol correction.

V5 cleanup ACK/capacity0 passed. Temporary token-file deletion was rejected twice by automatic approval review (including the exact single-file command); the restricted file remains and is not retried through another tool. Its token expires approximately21:58UTC. Full native sign-in, later continuation, context/progress, physical-device acceptance and final context restoration remain open.

Ruling: Strict v1 requires real complete response IDs plus ordinary stored ownership proof. The public native builder may return an empty success ACK; that remains uncertain/refused, with no stored-ID fallback or retry.
