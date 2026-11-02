# Local original-caller conversation entry

This is Root's proposed design under Marcel's autonomous repair request. It is
not approval to add security metadata. The earlier workflow approval remains
valid for that completed workflow; this additional endpoint grant needs its own
concrete review before any native write.

## Evidence and selected boundary

V4 correctly maps the caller and requests the normal native refresh, but its
actual asynchronous VA/AIA user remains guest. The SCC child fails access
verification before any GenAI or tools. Completing the account-link topic can
mean only that a profile already exists. The local CREATE currently enters
through the shared-provider-token B2B endpoint.

The Voice Agent OAuth client already used by desktop, iOS and Android is
`36a2defaff332210f540ffffffffff23`; its profile is
`80696efa37332210f5404f8be2924bb5`. It has the AI Voice auth scope and four native
policy links. Its current token restrictions do not establish permission for
the generic B2B endpoint. Do not add a global B2B policy or change its existing
scope rows, profiles, sources or flags.

A normal authorization-code/S256 exchange for the separate native WebRTC client
succeeded locally without visiting its cloud cookie-ticket callback. However,
its token fails the API scope gate: Missing required api access scope: AI Voice.
That client has no registered AI Voice mapping. A token-request parameter cannot
replace a registry permission. Its temporary token was removed. This route is
not selected, and no scopes or claims will be added to it.

The chosen proposal adds a small own endpoint and an explicit additional grant
for the existing Voice Agent caller. It preserves the existing client-side
authentication and common media path on all platforms. These auth scopes are
resolved from client registration at runtime, so the additional own-endpoint
permission would apply to all that client's tokens. The endpoint itself is
limited to this service and an authenticated administrator; it exposes no tools
or later business input.

## Seven new records, plus ordinary capture container

All source/configuration records are newly owned in the Voice AIA application
`022bd6e9b720a61081fee3fdde11a9df`. Use the normal selected-application creation
context; never set denied namespace, parent, scope or package fields by script.

1. Scripted REST API: SCC Local Voice Caller, API ID `local_voice_caller`.
2. Authenticated POST `/create` resource, resulting path
   `/api/sn_voice_aia/local_voice_caller/create`.
3. Own auth scope: SCC Local Voice Caller.
4. API auth-scope binding for that own API's exact POST create endpoint.
5. API access policy for that same exact endpoint.
6. New relation between that policy and the existing Voice Agent auth profile.
7. New relation between that own auth scope and the existing Voice Agent client.

No OAuth client, user role, old ACL, existing policy field, global feature or
generic B2B API binding changes. Preserve all original profile/scope relations.
Use a separate own WIP set, proposed name
`Custom LLM Voice 2.6 - Original Caller Create - NO DELETE 20261102`, with normal
capture/audit records. Confirm normal UI materialization and read back every
actual new identity; stop on an unexpected record or denial.

## Endpoint contract

The only accepted JSON body is
`{version:1,requestId,clientSessionId,clientMessageId}` with three lowercase
32-hex IDs. No caller UID, user name, email, model, tool, text, profile or
business objective is accepted from the client.

Require normal platform authentication, original Bearer, a nonguest GS caller
with `admin`, native service authorization, active/unlocked own user and a unique
readable email mapping. Native authorized-agent checks must include
`a6337ddf93f787105c8132d47aba1058` for service
`8aa131d793f787105c8132d47aba1095`. The central settings profile must equal
`c623e20f93374354e7f2b9fa6aba1081`. Preserve the existing SCC workflow/agent/data
ACLs and dynamic data roles.

Construct the native B2B payload on the server: fixed inbound `scc-local-voice`,
fixed service/profile and central language, provider alias `voice-` plus the
private clientSessionId, own GS email, empty typed message, CREATE_CONVERSATION,
and documented `syncResponse:true`. Never set USER_REF, actual_user, VA cached
user or arbitrary objective. Pass the unchanged original Authorization and
existing provider-token header to the public
`sn_va_as_service.VABotToBotRestMessageHandler.processPayload` routine. Do not
read provider secrets or call protected helpers. Normal cross-scope execution
must be allowed; a refusal stops the run.

Return only a bounded successful-create envelope. The proposed adapter shape is
`{status:'success',created:{requestId,clientSessionId,userId,body,...}}`, where
userId is the generated provider alias and body contains exactly one filtered
native ActionMsg/CreateConversation with conversation/message/interaction IDs.
Only a genuine native nowSessionId may be retained when required by the actual
public return contract. Strip userDetails, names, emails and unrelated outputs.
The Source/Transport owners must freeze the exact native return parser together
before packaging. Never treat HTTP success or this receipt as runtime auth proof.

## Local transport

Keep the existing one-call original-Bearer binder for WS and SDK. Under the same
private 45-second ticket, claim the credential once for CREATE at the exact own
instance/path, then once for the distinct existing native refresh. Clear it on
all success, expiry, failure, cancellation, reset, end and shutdown paths.

The configured own CREATE path is optional before activation. When selected,
failure cannot fall back to anonymous B2B or retry. Set the private provider
alias to `voice-` plus the existing Bridge cookie/session ID. Bind a synchronous
create receipt only to its current request, caller, private cookie and complete
native tuple, then use the existing single start/refresh transition. Duplicate
or stale callbacks cannot change or repeat that transition. START, MESSAGE,
END and context messages never receive the caller Bearer through the B2B path.

No media/frontend DTO or authentication flow changes. Model/controller, Gateway,
ASR and own TTS stay loaded. Activation may replace only the exactly identified
idle affected adapter processes after metadata/config/source readback.

## Acceptance and reversal

Offline tests must reproduce wrong destination, changed request/caller/tuple,
duplicate sync/callback, deadline and cancellation/end races before fixes.
Native source tests cover original-GS authority, exact fixed payload, source
rights/denials, stripped responses and at most one public native CREATE call.

After explicit security approval and independent complete native readback, run
one new immutable normal-authorized bounded SDK probe. Require actual non-guest
access verification, real root Orchestrator before the original SCC child,
Halogen logs, name-only confirmation and normal continuation. No order consent
or later data input. Require acknowledged cleanup and zero capacity, then remove
the temporary credential. Physical phones/network/acoustics remain separate.

Reversal disables the new own API/resource/policy/binding where native active
flags exist and removes the local create-path selection. Preserve original
records and capture history. No automatic delete, role change, native-client
flag change or broad access workaround is part of this proposal.
