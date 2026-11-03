# Caller CREATE admission implementation plan

> **For agentic workers:** Use test-driven development and the recorded ownership split. User explicitly delegates execution/design and opts out of questions.

**Goal:** Reject a known caller CREATE access failure before allocating a Voice session.
**Architecture:** Shared fixed-route malformed-body access preflight after trusted settings, consumed by SDK admission and WSS authorization.
**Tech Stack:** Existing Python asyncio/aiohttp, no new dependency.
**Spec:** docs/superpowers/specs/2026-11-03-voice-caller-admission-design.md

## Global constraints

- Exact original caller authority only; fixed own deployment; no provider/admin token, real CREATE, retry, cookie or caller content.
- Only normally closed exact malformed400 grants this preflight; all uncertain outcomes reject admission.
- Preserve one10s total deadline, unrelated deployments and legacy behavior.
- Source isolation only; no live/canonical change until review plus finite wire proof and reload.

## Review focus

- API permission check must precede shared capacity, TURN, peer, model and audio work.
- Shared WSS HTTP cookie jar must never supply authority to this helper.
- Foreign/duplicate/extra/encoded/oversize response envelopes fail closed.
- Cancellation and slow close remain within the original admission budget.
- Post-preflight expiry during actual CREATE still retains UNKNOWN; no replay.

### Task1: Shared access probe and integration (registrar_integrated_validation)

Files: newvoice/native-bridge/caller_create_preflight.py, sdk_admission.py, native_bridge.py and focused tests.

- [x] Write failing tests proving401 after native metadata rejects before allocation and side effects.
- [x] Implement the exact fixed conditional predicate and bounded own-client probe.
- [x] Integrate real SDK and WSS entrypoints without speculative extra calls for other configurations.
- [x] Exercise malformed/closure/deadline/cancellation and existing entry contracts.
- [x] Run focused and full Native suites with existing jsonschema target; record all results.

### Task2: Independent review and integration (Root)

- [x] Fresh whole-change review and meaningful regression verification.
- [x] Obtain separately reviewed bounded malformed400 wire proof with a fresh native client token.
- [ ] Commit/integrate only after GO and prepare a distinct exact idle Native reload; preserve model/speech owners.

Verification:150focused and1173full Native tests pass after the independently reviewed shared-deadline correction. Root independently reran150focused. ScopedreviewSHAe1aa20aad4a224f3469abe8cccd63b2f3515ba3a134f140bf5722c8b7175db38. Existing jsonschema test dependencies were reused; no new runtime dependency.

The finite fresh Voice Agent wire observation passed against installed resourceSHA d4b925b05fdd066fa105fae7c522cea45b2e5cb7b668c260ae1151b30b571e88: agents200, exact malformed400 envelope, own new token revoke200 then same-token401. ResultSHA0c91be6dfb2fce31cbecb79881bc0d33421866369d009e8e4ff006e81efaf56d. No session, real CREATE, model/audio or business call occurred. Ordinary SDK admin credential resolution may renew its own authority; the result explicitly records that possibility.
