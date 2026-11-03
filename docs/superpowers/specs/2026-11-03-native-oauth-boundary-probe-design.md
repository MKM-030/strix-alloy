# Original-caller native OAuth session diagnostic

## Purpose and authority

Marcel explicitly requested autonomous repair and synthetic self-testing of the
Voice assistant. The next bounded experiment tests the existing original-user
Voice bearer at the native CS session boundary. It is an inactive diagnostic,
not a production transport, new authorization grant or completed Voice repair.

The existing B2B V5 worker remained guest. A normal browser Test used the real
user but a misleading static name question entered general search instead of
SCC. Both real greeting sources have now been corrected and the public Voice
introduction independently matches. A newly issued original Voice bearer also
performed the observed native support_queue GET with HTTP200. This proves that
read alone; neither missing scope metadata nor that read establishes v2 POST
admission. No extra grant is justified before measuring the actual boundary.

## Chosen experiment and limits

Use the genuine native v2 session request with the original bearer, no browser
cookies or CSRF substitution, a fresh device UUID and ordinary current-caller
metadata reads as an independent oracle. Compare real returned values against
safe record IDs entirely in RAM before one EndChat. Keep client initialization
false. Send no text, task selection, confirmation, media or business action.

Independent AMB-channel-to-record mapping remains unproven; the exact native
response supplies the channel and the native message service authorizes it.
Suppressing client initialization is source-backed, but absence of automatic
server initialization is an observation to verify, not a guarantee. Unexpected
activity fails the experiment while preserving legitimate own cleanup.

Partial creation, guest response, mismatched binding, refused proof or failed
cleanup can leave an uncertain result. Identify safe owned residue using the
generated device correlation; never fabricate a cleanup tuple, change database
state, repeat create/end or launch a replacement UI. No end-only browser
fallback is established. This limitation is acceptable for the bounded spike;
it is not a production acceptance claim.

## Fixed constraints

- Origin `https://soprasteriaassvsdemo14.service-now.com`; vendor
  `c2f0b8f187033200246ddd4c97cb0bb9`; profile
  `c623e20f93374354e7f2b9fa6aba1081`; device type `mweb`.
- Existing Voice service `8aa131d793f787105c8132d47aba1095`, existing authorized
  agent `a6337ddf93f787105c8132d47aba1058`, existing public original-user PKCE.
- Preserve installed security/workflow/model records, both repaired greetings,
  prior immutable attempts, active services and own TTS. No model adoption,
  service activation, new UI page, role, ACL, OAuth grant or private helper.
- No SDK administrator business proxy. SDK execution may only inspect normal
  metadata under its actual original GS caller with explicit read checks.
- Use actual `caller_binding.user_id` from the already installed, public
  `agents_authorized` opt-in `callerBindingVersion:1`, with existing
  `assistantSettingsVersion:1`. Hash in RAM and compare to an independently
  derived current-GS hash. No client user ID is accepted by the oracle or sent
  in the native session body. Never serialize caller name/email/ID or tokens.
- Before create, require complete current own snapshots, no active/unknown
  conversation and no row for the new device. Bounds:16 consumers,512 accounts,
  512 user profiles,512 conversations and512 sessions; refuse overflow/denial.
- Reject explicit lastMessage/history/resume state, old IDs, competing deltas,
  changed old conversations, wrong principal, vendor/profile/device/account or
  consumer, and any missing DTO-to-record equality. Potential HTTP-session
  strings must never reach an SDK argument, script, log or receipt.
- Native JSON≤64KiB, messages≤128, create≤15s, independent cleanup reserve45s
  including oracle verification≤15s, End≤10s, at most6 sync GETs≤3s each.
  Metadata command≤15s per call. Request budgets consume the reserve.
- Existing PKCE/public-settings/token-response bounds remain unchanged.
  New tokens stay in process RAM; immediate finally revocation requires issuer
  HTTP200 and a normal same-token authorization HTTP401. No old-token file,
  refresh, POST replay or raw-response export. This diagnostic does not change
  production's private45s handoff or introduce call-long credential retention.
- Public results: fixed codes, booleans, counts, HTTP statuses and durations.
  Only safe record IDs/generated UUIDs may be stored privately for residue.
  Raw native DTO/session strings, errors, headers, messages and credentials stay
  out of artifacts. Unknown activity is not zero activity.

## Oracle contract

`createNativeOAuthOracle({gs, GlideRecord, GlideDateTime, GlideDigest,
GlideImpersonate}).inspect({version:1, phase, attemptId, deviceId})` is pure with
respect to persisted state. Phases are `before`, `after`, `terminal` and do not
alter authority. The ES5 module works in Node tests and as an own inline source
inside an ordinary read-only SDK script. It invokes no runtime or private API.

Successful output has exactly version, phase, attemptId, deviceId, ok,
failureCode, principalHash, server, contextUnchanged, counts, conversations,
sessions, deviceConversations, deviceSessions, unownedDeviceRows, activity and
messageSessionLinks.
`server` has `startedMs/finishedMs`; counts has `activeConversations` and
`unknownStates`. `principalHash` is lowercase SHA256 of actual GS user ID, with
non-guest administrator/non-impersonation and unchanged effective context.
Failure uses a fixed enum, null principalHash and empty data arrays; no partial
snapshot can be treated as complete.

Conversation rows contain `id,consumerId,accountId,vendorId,profileId,deviceId,
state,createdMs,updatedMs,modCount`. Session rows contain
`id,consumerId,accountId,vendorId,deviceId,deviceType,createdMs`. All returned
rows are proven owned through actual current-GS consumer/account relationships;
only safe IDs are exported. Empty reference fields become null, but each row
must have a proven own consumer or account; nonempty references must be32hex.
Historical device strings are compared in memory: `deviceId` is the requested
generated UUID on exact equality and null otherwise. Historical device values
are never exported. `deviceType` retains the source-known `mweb`, `ios`,
`android`, `nowassistpanel` values and is null otherwise. Matching candidates
must still satisfy every fixed tuple field in the protocol. Query with normal GlideRecord and check each row
and required element before reading values, so denied rows cannot vanish into
an apparently complete secure-query snapshot. Include the known union of own
consumer and user-profile account paths. Active states are `open`,
`chatInProgress`, `autoPilotInProgress`; terminal states are `completed`,
`faulted`, `canceled`, `chatEnded`, `deleted`. Empty session end_time proves
nothing. Unknown state refuses admission.

Device queries inspect the generated UUID only. Unowned matches yield a count,
never unowned IDs. Activity is `{available,messages,plans,genai,tools}` using
only the exact already evidenced conversation query paths. Unavailable counts
are null with available=false; do not invent a query/zero. Read actual
message.session references when available, without reading payload/text.
`messageSessionLinks` contains deduplicated `{conversationId,sessionId}` safe
record references for messages on the generated device's owned conversations;
an empty session is represented by null. A link must name the candidate
conversation; a non-null session reference must name its proven session.
A null session reference supplies no corroboration and is not a contradiction;
it never replaces mandatory direct DTO-to-record session equality.
If message activity is unavailable,
links are empty and `activity.available` is false. Missing links are never
proof of no messages. Activity is restricted to those device conversations,
using `sys_cs_message.conversation`, `sn_aia_execution_plan.conversation`,
`sys_generative_ai_log.conversation`, and tools joined through
`sn_aia_tools_execution.execution_plan_id`. Each count query is bounded to512;
overflow or denied activity makes all activity counts null, available=false,
without weakening mandatory ownership-snapshot checks.

Oracle failureCode is null for success; failures use only `INVALID_REQUEST`,
`INVALID_DEPENDENCIES`, `PRINCIPAL_REFUSED`, `CONTEXT_DRIFT`, `READ_DENIED`,
`SCHEMA_UNAVAILABLE`, `READ_LIMIT`, `INVALID_DATA`, `READ_FAILED`. Active and
unknown-state counts are observations for the consumer to refuse, not oracle
failures. A failure retains validated phase/UUIDs (otherwise null), emits null
principalHash/server bounds, false contextUnchanged, null counts, empty arrays,
unownedDeviceRows null and unavailable activity. No raw exception is exported.

## Protocol and driver contract

`createNativeOAuthSessionProbe({origin, fetchNative, inspect, callerHash, uuid,
now, monotonic, sleep}).run({signal}={})` is a one-shot portable Node protocol.
`fetchNative` is an authenticated original-bearer-only transport injected by
the private driver; no browser module is repurposed with fake CSRF.
`inspect(request)` returns the exact oracle contract. No successful default
oracle exists. Before-create principal hash must equal real public binding;
all later proofs retain that identity and fresh generated device correlation.

The private driver alone owns PKCE/token capture/revocation and the normal SDK
read-only execution transport. Use existing tested source patterns; never edit
old helper/receipt files. SDK scripts contain only the own oracle source and
validated phase/UUID arguments, never raw DTO/session/user/token. Shell
arguments must be correctly escaped, with no JSON-as-shell-escaping. Parse only
the own marked JSON output, discard incidental SDK logs, bound stdout, and
persist only validated allowlisted metadata. No dependency installation.

One exclusive explicit-execution marker precedes network/credential actions.
The final independent metadata read establishes terminal conversation state
and own-active count separately from End ACK/TopicFinished. Do not infer native
session retirement from end_time, conversation completion or a local counter.

The protocol returns exactly `{report,residue}`. `report` is public-safe with
exact keys `version,status,failureCode,native,metadata,durations,limitations`.
`version` is1; status is `passed`, `refused`, `failed` or `uncertain`. `native`
has `createAttempted,createHttpStatus,authenticatedFlag,freshBindingProven,
endAttempted,endHttpStatus,endAcknowledged,topicFinished,syncPolls`; status
fields are null or HTTP100..599, authenticatedFlag null or boolean, syncPolls
an integer0..6, other fields booleans. `metadata` has
`beforeComplete,afterComplete,terminalComplete,principalMatches,
unexpectedInitialization,terminalConversation,activeConversations,
unknownStates,ownedDeviceConversations,ownedDeviceSessions,unownedDeviceRows,
messages,plans,genai,tools`; first four booleans, next two null/boolean, rest
null/nonnegative bounded integers. Counts reflect the final complete snapshot
available, and `unexpectedInitialization` is true if any observed plans,
genai or tools are nonzero, false only with available evidence, otherwise null.
`durations` has `beforeMs,createMs,verifyMs,endMs,syncMs,terminalMs,totalMs`,
each null or finite nonnegative integer milliseconds. `limitations` always
has `ambMappingIndependent:false,serverInitializationGuaranteedFalse:false,
sessionRetirementProven:false`. No raw identifier/hash/error is public.
`residue` is private-only, exactly `attemptId,deviceId,conversationIds,sessionIds`,
using generated UUIDs and independently proven own device-row IDs only.

Protocol failureCode is null or `INVALID_CONFIG`, `CANCELLED`, `TIMEOUT`,
`PRECHECK_REFUSED`, `IDENTITY_MISMATCH`, `HTTP_ERROR`, `REDIRECT`,
`RESPONSE_LIMIT`, `INVALID_RESPONSE`, `INVALID_BINDING`, `UNAUTHENTICATED`,
`EXISTING_CONVERSATION`, `INVALID_SEQUENCE`, `BINDING_UNPROVEN`,
`UNEXPECTED_INITIALIZATION`, `ACTIVITY_UNAVAILABLE`, `CLEANUP_UNCONFIRMED`,
`TERMINAL_UNCONFIRMED`, `REQUEST_FAILED`. Retain the first failure. `passed`
requires no failure, authenticated null flag plus independently fresh binding,
End ACK, TopicFinished, complete terminal metadata showing terminal exact own
conversation and no own active/unknown states, and no observed initialization.
A pre-create refusal is `refused`; any ambiguous create or unconfirmed cleanup
is `uncertain`; a measured failure with proven terminal cleanup is `failed`.
Create HTTP rejection does not prove absence of side effects; still perform
bounded device metadata correlation and keep that limitation honest.

Cleanup reserve45s starts once create settles, fails or times out; it never
inherits user cancellation. Reserve the final15s for terminal metadata, using
remaining budgets for after-proof, End and at most six sync reads. The caps
are maxima, not an entitlement to all six polls. If proof is refused, retain
safe residue and skip End. A subsequent terminal read cannot retrospectively
authorize End or erase an earlier uncertainty. Unknown activity prevents pass
but does not prohibit cleanup of an independently proven fresh own tuple.

## Evidence

Authoritative exact native wire extracts, source hashes and metadata evidence
are in `entry-workflow/v5-original-caller/authenticated-chat-contract/` and
`entry-workflow/native-browser-session-probe/preflight/fresh-binding-preflight/`.
The offline judgment `native-profile-test-20261103/native-oauth-boundary-design/
BOUNDARY-DESIGN-REVIEW.md` recommends conditional preparation with the explicit
unknowns above. Existing browser diagnostic remains inactive and unchanged.
