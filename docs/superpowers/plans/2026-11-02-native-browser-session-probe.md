# Native browser session diagnostic implementation plan

> **For agentic workers:** Use superpowers:executing-plans or subagent-driven-development task by task. Marcel delegated autonomous execution; do not repeat a design preference question.

**Goal:** Test native same-origin browser session authentication and acknowledged cleanup without initializing agent work.

**Architecture:** A pure browser protocol module follows the observed native widget contract. An own administrator-only ServiceNow page hosts a one-shot diagnostic; credentials remain in the original browser.

**Tech stack:** Existing Node portable tests, browser fetch/AbortController, ordinary ServiceNow Jelly/UI-page defaults and SDK readback. No dependency installation.

**Spec:** `docs/superpowers/specs/2026-11-02-native-browser-session-probe-design.md`.

## Global constraints

- Exact lab origin, fixed c623 profile, native vendor c2f0 and mweb device type.
- No new OAuth grants/roles/ACLs, SDK-admin proxy, identity fields or vendor edits.
- Source-derived native endpoint and DTO shapes only; no guessed REST grant.
- One session attempt, one EndChat, sync initialization always false, no text/input/actions/order.
- No load-time networking, retry, redirects, guest fallback or fabricated IDs.
- No credential output/export or calls to local/media/model services.
- Preserve the seven-record installation, frozen V5 artifacts and running services.

## Review focus

- Create success with missing/guest/contradictory native binding stays failure.
- Cancellation or error after creation still attempts the one legitimate cleanup.
- Wrong channel/session or stale serial cannot authorize publication or completion.
- Response/error content and object diagnostics never reveal the CSRF sentinel.
- A TopicFinished event for another conversation cannot establish cleanup.

### Task 1: Portable native protocol and offline tests

**Files:** Create `servicenow/byollm/voice-auth/Native-browser-session-probe.js` and `.test.cjs`.

**Interface:** `createNativeSessionProbe({origin, csrfToken, fetchImpl, uuid, now, monotonic, sleep})` returns `{run({signal} = {})}`. Export `createNativeSessionProbe` through CommonJS for tests and browser global `SccNativeSessionProbe.createNativeSessionProbe`. The one-shot result is `{version:1, passed, authenticated, binding:{sessionId, consumerAccountId, conversationId, channelSuffix}, cleanup:{attempted, acknowledged, completed, uncertain}, phases:[{phase, elapsed_ms}], failureCode}` with credential-free safe scalar fields; absent bindings are null. `failureCode` is a fixed enum, never remote error text. No automatic run on module load. The wrapper labels `passed` as this isolated protocol diagnostic, never full Voice success. Task1 must preserve legitimate cleanup under cancellation using a separate bounded cleanup reserve.

- [ ] Read the exact native source extracts for session request/response, publish, sync, action control and EndChat; settle response unwrapping against the source rather than assumptions.
- [ ] Write failing tests for the spec's exact request, authentication, bound EndChat, false-only initialization and matching TopicFinished result. Include the five review-focus cases, duplicate run, response bounds and failure/cancellation cleanup.
- [ ] Run `node --test servicenow/byollm/voice-auth/Native-browser-session-probe.test.cjs`; confirm meaningful missing-feature failures.
- [ ] Implement the smallest protocol module. If the native source cannot substantiate a required wire detail, report that exact blocker before implementing a guessed contract.
- [ ] Run focused tests, then the existing byollm suite. No live endpoints are contacted by tests. Root independently reviews source and results before integration.

### Task 2: Source-only diagnostic UI wrapper and normal preflight

**Files:** Create `servicenow/byollm/voice-auth/Native-browser-session-probe.ui-page.xml`, `.client.js`, and private deployment/preflight evidence under a NEW native-browser-session-probe folder.

**Consumes:** Task1 module and safe result. **Produces:** one own page source with a single Start diagnostic button, no networking before its user gesture, server administrator guard and credential-free result display.

- [ ] Write failing portable wrapper tests proving no load-time call, single-click admission, fixed settings, server admin guard, text-only result rendering and no credential display.
- [ ] Implement the wrapper using ordinary platform Jelly/page behavior. No injected vendor module or browser hidden-state automation.
- [ ] Run focused and byollm tests; independent review checks the one-session/one-end/init-false behavior.
- [ ] Read normal UI-page schema/create rights and current app/set preferences. Prepare exact own page fields and separate own WIP; stop on denied fields, never use a more privileged writer.

### Task 3: Normal installation and one bounded browser diagnostic

- [ ] Record source hashes and review; create only the new own page through normal UI/defaults in its separate WIP. No security metadata changes.
- [ ] Independently read back exact source, normal scope/package/defaults, capture and all preserved previous rows/relations. Restore previous UI/SDK context when native writes finish.
- [ ] Open the page without starting the test; verify server guard, no network operation on load and fixed profile visible without credentials.
- [ ] Execute one bounded native browser diagnostic. Send no business or user input. Preserve any failed/uncertain receipt without replay.
- [ ] Independently correlate actual native session/conversation/consumer identity, fixed profile, completed state and zero GenAI/tools. Do not promote the native flag alone to AIA-worker proof.
- [ ] Update docs/checkpoint and commit verified sources. Keep full Voice/media/context/device acceptance explicitly open until separately proven.
