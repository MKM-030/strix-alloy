# Native browser session diagnostic

## Intent and authority

Marcel requested autonomous repair and independent self-testing of the Voice
assistant, with ServiceNow as the sole business executor and common behavior
on iPhone, Android and desktop. He explicitly delegated implementation choices.
The seven-record original-caller endpoint is installed, but V5 still ran its
VA worker as guest. This diagnostic tests the normal browser session boundary;
it is not a replacement Voice UI or a claim of completed repair.

## Evidence and chosen approach

The observed native widget asset SHA256
`e1fb0a8bfc326ff9f466ddd1790979f1edc05613c8d0204e319bfc4044b9298b`
uses same-origin `POST /api/now/v2/cs/session`, browser cookies and X-UserToken.
Its native authentication event requires `guestSessionIdentifier === null`.
Native context maps `sysparm_global_context_profile` into `contextData`; the
actual profile Test action also sets `sysparm_nowassist=true` for this LLM
profile. Message publication and EndChat use `/api/now/cs_message` with the
returned AMB channel. Sync is a separate explicit initialization boundary.
Exact source extracts and the native Test action are retained in
`server/.local/voice-repair-20261102/entry-workflow/v5-original-caller/authenticated-chat-contract/`.

Root's choice is a small same-origin, administrator-only diagnostic page. It
uses the existing browser account and keeps its cookies/CSRF inside ServiceNow.
Alternatives were another B2B principal-forwarding patch (V5 disproved that
approach) and new native-CS OAuth grants (the v2 route's exact normal grant
binding is not established). Neither is selected. No new OAuth, role or ACL
grant is part of this work. The existing seven-record package remains frozen.

## Bounded behavior

- Fixed origin `https://soprasteriaassvsdemo14.service-now.com`, context profile
  `c623e20f93374354e7f2b9fa6aba1081`, vendor
  `c2f0b8f187033200246ddd4c97cb0bb9`, device type `mweb`.
- The user gesture starts at most one session attempt. A new UUID is a device
  correlation, never a supplied user identity. Body contains native session
  fields and the fixed profile/nowassist context; no name, role, email or task
  objective is supplied.
- Only same-origin fetch with credentials `same-origin`, redirects refused,
  bounded JSON and X-UserToken from the normal page are used. No Bearer token,
  SDK-admin proxy, cookie extraction/export or local-service request.
- Strict authentication flag plus genuine bounded returned native bindings are
  required. Missing/guest/ambiguous response is a failed diagnostic.
- Never initialize conversation work: sync always has
  `shouldInitializeConversation=false`. No user text, name, confirmation,
  action-control acknowledgement or arbitrary action is emitted.
- After creation, perform exactly one bound native EndChat action through the
  received channel and session, then bounded GET sync with native sequence
  tracking. Require TopicFinished/completed state as a cleanup witness; a POST
  ACK alone is insufficient. No session DELETE, automatic retry or replay.
- Missing bindings after a partial create remain an uncertain failure, never
  fabricated cleanup. Surface that state and perform an ordinary independent
  native readback before deciding anything further.
- The page runs no networking on load. It displays only bounded status,
  correlation IDs, phase durations and explicit authentication/cleanup flags.
  It never displays cookies, CSRF, headers, user identity or raw conversation.
- Server rendering gates the diagnostic to the original normal administrator.
  No public exemption, new role assignment, privilege workaround or vendor
  modification. Creation, if normal rights allow it, uses a separate own WIP.

## Deliverables and limits

Portable browser protocol module, meaningful offline tests, and source-only
Jelly/client wrapper for one own UI page. Normal native field/default/schema
preflight and independent source review precede any UI-page Save. The test
requires independent native-state correlation and zero GenAI/tools. No live
call, model switch, microphone or speech service change is authorized by the
design document itself; Root executes the already user-authorized bounded
diagnostic only after the implementation and deployment gates pass.

This proves neither original-caller AIA execution nor Voice/media binding.
Those, fixed profile/context propagation, normal name continuation, and
physical-device/relay acceptance remain later requirements. The diagnostic
must not silently become a production business proxy or a new Voice entry.
