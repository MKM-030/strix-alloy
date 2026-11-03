# Native OAuth boundary diagnostic implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Marcel explicitly delegated autonomous implementation and tests; do not repeat an execution-preference question.

**Goal:** Prepare and independently review one original-bearer native session diagnostic with real ownership proof and bounded cleanup.

**Architecture:** A portable ES5 metadata oracle supplies complete original-caller snapshots. A separate OAuth-only protocol compares actual native DTO values in RAM; a private one-shot driver owns normal PKCE, metadata-only SDK execution and final token revocation.

**Tech Stack:** Existing Node tests, platform normal GlideRecord/read APIs, fetch/AbortController, existing SDK installation; no dependencies or service changes.

**Spec:** `docs/superpowers/specs/2026-11-03-native-oauth-boundary-probe-design.md`.

## Global Constraints

- Exact origin/vendor/profile/mweb and existing Voice service/agent from spec.
- No new grant/role/ACL/UI page, private runtime helper, identity override, SDK business proxy, model or service activation.
- One source-backed create, one legitimately proven EndChat, false-only sync initialization, no user text/confirmation/media/order/action acknowledgement.
- No fake CSRF, cookie export, raw DTO/session/user/token in SDK scripts, logs or artifacts.
- Complete bounded original-GS snapshots and actual DTO-record equality, no affirmative placeholder callbacks.
- Token RAM only, existing original-user PKCE, immediate finally issuer200 plus same-token401 cleanup; old attempts immutable.
- Partial/guest/mismatch/denied/late proof remains uncertain; no replay, fabricated cleanup, database lifecycle writer or UI fallback.

## Review Focus

- A denied row must refuse completeness rather than disappear through query filtering.
- Real HTTP-session-shaped DTO material must stay in RAM and never enter a generated SDK script.
- Existing/resumed/competing conversations never receive this diagnostic's EndChat.
- Post-create cancellation must retain an independent legitimate cleanup/revocation reserve.
- Missing activity or terminal evidence remains unknown, never promoted to zero/success.

### Task 1: Portable normal metadata oracle

**Files:** Create `servicenow/byollm/voice-auth/Native-oauth-session-oracle.js` and `.test.cjs`.

**Interface:** Export `createNativeOAuthOracle` through CommonJS and browser/platform global `SccNativeOAuthOracle`. Exact dependencies, inspect request, successful output and row schemas are defined in the spec. Consumers may not add fields silently. Any necessary message-session correlation field must first be ruled on in the ledger and spec.

- [ ] Read exact retained schema/ownership/state/query evidence. Settle activity query availability from the frozen reader rather than inventing fields.
- [ ] Write meaningful failing tests for owned union snapshots, denied row/field, guest/impersonation/principal drift, bounded complete IDs, active/unknown states, existing device, timestamps and safe output. Include empty historical session end_time and activity unavailable.
- [ ] Run focused tests and confirm RED before production code.
- [ ] Implement ES5 own read-only oracle with explicit rights and fixed failure enum; no mutation/runtime helpers. Test synthetic DB objects fail if any write is attempted.
- [ ] Run focused tests, then one byollm suite for the changed code. Commit only owned files and report exact tests/output/limitations. No live SDK invocation by implementer.

### Task 2: OAuth protocol and prepare-only driver

**Files:** Create `servicenow/byollm/voice-auth/Native-oauth-session-probe.js` and `.test.cjs`; prepare driver/tests/review under NEW `server/.local/voice-repair-20261102/entry-workflow/native-profile-test-20261103/native-oauth-boundary-probe/`.

**Consumes:** Task1 exact oracle and safe row schema. **Produces:** `createNativeOAuthSessionProbe` with the spec's injected interface and one-shot run. Fix its safe result enum/schema in its brief before dispatch. The private driver supplies real original-bearer transport, original-caller public binding and a genuine metadata oracle, with no successful default.

- [ ] Write failing exact-wire tests using injected native fetch/oracle, including direct DTO, guest/resume, stale or changed principal, wrong tuple, competing delta, sequence bounds, delayed response, cancellation and partial creation.
- [ ] Implement source-backed create/body/channel/End/sync semantics, actual RAM-only comparison and independent bounded cleanup. Keep native ACK, TopicFinished and metadata terminal evidence separate.
- [ ] Prepare exclusive-marker driver reusing reviewed normal PKCE early token capture and issuer cleanup. Add public callerBindingVersion:1 validation and compare its actual user ID hash to oracle. No production ticket or call-long retention change.
- [ ] Generate SDK scripts from exact own oracle source plus validated UUID/phase only. Test command escaping, output bounds/allowlist and absence of raw native/session/token/identity values in scripts/argv/files. SDK remains metadata-only.
- [ ] Cover all known-token failure cleanup and no extra endpoint/model/business call with injected tests. No live execution by implementer.
- [ ] Run focused tests and one appropriate full byollm suite. Commit owned tracked files; private driver report carries hashes and exact execution parameters for independent review.

### Task 3: Independent operational review and bounded execution

- [ ] Root reads implementation/reviews and runs a normal metadata-only oracle preflight once. Refuse on actual denial/schema gap; no alternate privilege/scope.
- [ ] Independent whole-package review covers own oracle, protocol, private driver, actual parameter/identity/retention bounds and the two explicit native unknowns.
- [ ] If all gates pass, Root runs exactly one existing-credential native boundary attempt. No new permission grant is part of this action. Preserve every failure/uncertainty receipt; no automatic retry.
- [ ] Independently correlate exact new own metadata/activity and terminal outcome; token revocation proof is mandatory. Do not claim AIA/Voice/device acceptance from this diagnostic.
- [ ] Update the durable continuation/status with actual results and smallest evidenced next correction, preserving current Code context and all services.

### Task 4: Correct the measured auth-response lifetime before a new version

The first Root execution failed before token dispatch/native CS. Preserve it.
Offline signal-linked streaming responses reproduce premature controller abort
before the unchanged core reads its body; controls retain the signal and pass.

- [ ] In NEW private sibling native-oauth-boundary-probe-v2/, prepare only the
  existing driver/helper/tests with unique v2 execution flag and the spec's
  bounded detached-byte auth-response handoff. No original attempt edits.
- [ ] RED/GREEN behavioral coupled-stream coverage, including direct and
  redirect/callback auth, token success/error/metadata failure and known-token
  finally cleanup, irrelevant redirect/error bodies, hanging/late/overflow,
  and actual CLI cancellation. Run focused private tests only; tracked oracle,
  protocol and unchanged original PKCE core are not edited.
- [ ] Independently review exact v2 diff/preparation and updated hashes/flags;
  only then Root may consider one distinct version invocation under fresh gates.
  No automatic retry or previous marker reuse. Record the actual bounded result.
