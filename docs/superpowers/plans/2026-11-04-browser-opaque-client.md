# Scoped browser OAuth client selection plan

> **For agentic workers:** Use superpowers:executing-plans and TDD. Root supplies the actual inserted client ID, reviews, integrates and deploys separately.

**Goal:** Select the separately registered own opaque OAuth client only for the local SCC Voice browser path, retaining the native client everywhere else.

**Architecture:** An inert `derive(originalSource, ownClientId)` factory validates the exact retained OAuth source and a lowercase32hex own client ID, then replaces its one `APP_CLIENT_ID` declaration. Own selection requires `api.state.isVoiceMode === true`, service `8aa131d793f787105c8132d47aba1095`, and orchestrator `https://strix-alloy.tail7f425a.ts.net/scc-native`. The complete native PKCE/callback/claim/exchange/event flow stays intact.

**Tech stack:** Existing ServiceNow browser JavaScript; portable Node VM tests with real WebCrypto and mocked HTTP boundaries.

**Spec/provenance:** Root-approved source-only brief. Original OAuth record `656f3a82b726321081fee3fdde11a9a9`, revision7; LF SHA256 `9673f9b61867a007d14114976f7a9e11e78b8b8d1dcbd0758816a5c56357bef1`. Fresh saved receipt `browser-turn-credential-diagnosis-20261104/oauth-flow.preimage.json`, SHA256 `ddb0fd5916ba1431c397a7ae75ef7cc7ed96c806fce34a2dbbba3eecdb643d69`.

## Constraints and review focus

- Change only the client declaration in a derived candidate; preserve vendor78e, callbacks, S256, requested service claim, same-instance URLs and events.
- Missing settings, wrong service/endpoint, chat mode and nonboolean Voice mode retain native client78e.
- Reject malformed/vendor-reused client IDs and changed original bytes; never interpolate arbitrary source.
- No production candidate or placeholder OAuth source until Root supplies the actual new client ID.
- No SDK/auth/browser/model/runtime/primary writes or commit; source tests do not establish TURN or physical playback success.

## Single task

Files: retain `voice/native-servicenow/tests/browser-parity/Oauth-flow.original.js`; create `build-oauth-candidate.cjs` and `oauth-client-selection.test.cjs` there; add the original fixture to the existing `.gitattributes` whitespace exception; this plan.

- [x] Copy and independently hash the exact original fixture; compare saved revision7 after CRLF→LF only.
- [x] Add full-handler tests and observe own-client selection fail against an unchanged-source factory stub.
- [x] Implement the single-anchor strict derivative and test own/native selection in both auth URL and token exchange, real S256/state, unchanged callback/claims/events and rejected malformed IDs/source drift.
- [x] Run all browser OAuth, browser playback and native routing tests, `git diff --check`, and verify five-file scope plus production OAuth unchanged.
- [x] Report hashes and limitations without commit/deployment; actual client ID generation remains Root-owned.

**Results:** Targeted RED selected native78e instead of the expected fixture client in both requests. OAuth tests then passed15/15. Combined `node --test voice/native-servicenow/routing-draft.test.cjs voice/native-servicenow/tests/browser-parity/regressions.test.cjs voice/native-servicenow/tests/browser-parity/oauth-client-selection.test.cjs` passed57/57 with no skips. Production OAuth remains9673f9; no production candidate, actual grant, SDK request or runtime action occurred. The fixture-only whitespace exception preserves native bytes rather than reformatting them.

## Root integration, 4 November 2026

The own public client was created inactive, reconciled as exactly nine owned Global records with two existing scope memberships and five existing API policy memberships, then activated through the normal secure record API. Vendor client78e remains unchanged. Actual own authentication with the native consent form passed: access86bytes, completeTURNusername142bytes accepted by Chrome; caller metadata and restricted malformed-create preflight passed; test access/refresh pair revoked200/200 and original access rejected401.

Native consent occurs on every fresh authorization. The integrated source therefore supports the original same-origin ServiceNow approval page in an accessible modal iframe, keeps PKCE/state, checks state before exchange for this own branch and validates the returned token. A token-free window owner cancels superseded attempts across API wrappers. Cancellation/denial/timeout shows a fixed recoverable notice and clears connection progress. Other assistants keep their prior OAuth behavior.

The installed native macroponent already reuses auth_token on later Start clicks. A separate seven-case regression exposed failed preconnection WebSocket attempts leaving that cached token and call owner active. The Start derivative now routes a current preconnection error/close through its existing failure cleanup once and clears only that failed attempt's matching cached token; a later Start can authorize anew. No automatic conversation retry or token revocation was added. Existing successful media and established-close paths are unchanged.

Root combined validation:88/88 browser routing, OAuth selection/consent and Start playback/failure tests, source syntax and diff checks. Controlled actual WSS/Start17 test received the entire current greeting with real media playback and first voiced PCM4420.69ms after trusted Start; no physical microphone or user inputs. Its original aggregate receipt remains UNCERTAIN due an early test-worker process check. Separate fresh read-only proofs confirm the exact ServiceNow conversation completed/interaction closed and all owned test process generations gone. This does not establish physical iPhone/Android/full-page acceptance or reduce the still measured~37s backend name-question delay.

Source integration is separate from native deployment/readback. Keep rollback recording and the current voice/model/speech services. Remaining work includes normal scoped UI deployment, complete first-user UI acceptance, and business bootstrap/async latency improvement.
