# Voice repair — 2 November 2026

Status update, 3 November 2026: the generic own-voice welcome is restored.
VA Input Response Generation and the two downstream Planner defaults were
corrected to Halogen. The outer role-mask repair subsequently allowed both
the native workflow and its SCC child through access checks; the earlier
Guest diagnosis alone did not explain the complete execution failure.

The bounded V10 name test passed: it retained the exact raw synthetic-name
ASR, completed the local readback and accepted one local name-only Ja.
ServiceNow then asked its separate required name-confirmation question.
That local Ja was not replayed against the later backend question. V11,
which can answer that fresh backend name question once and then observe the
next concrete field question, remains unrun.

The managed-ICE WSS V3 probe observed its first voiced PCM at 3.484 seconds
and an offer/answer interval of 1.015 seconds. These are measurements from a
synthetic host-only client, not physical phone/browser startup or full
introduction-playback acceptance.

The verified combined reload receipt c93527e5… loaded owned-CREATE draining,
exact END-completion handling and complete four-ID metadata publication.
That dated receipt preserved the controller, Halogen, Gateway, ASR and own
TTS. Its process IDs are historical generation evidence, not restart recipes.

A different subsequent SDK call (e770…) reserved capacity after a failed
CREATE-only operation. Its client and peer closed; no ASR, queued speech,
START or END was observed. Remote allocation remains unknown. A negative
visibility read does not establish that no remote conversation exists.
The safe fixed-stage CREATE diagnostics are promoted to canonical source,
but their runtime activation is pending. The failed CREATE has not been
replayed, and V11 preflight refused the occupied slot without starting V11.

The full Voice goal remains open: physical iPhone/Android/desktop parity,
real microphone/noise/name-correction and repeated-call behavior, requester
context, native business execution and sustained progress still require
acceptance evidence. The sections below retain earlier dated diagnoses and
results; this update supersedes their stale runtime and blocker descriptions.

## Demonstrated causes

`Dialog.open()` selected the configured initial topic and returned its first
employee-name question. Native Voice treated that question as its greeting and
waited for initialization before speaking. Actual failed calls spent 14–29.3
seconds in that initialization; first TTS chunks afterwards took 47–264 ms.
The routing behavior dates to Task73, before the Halogen Agent migration.

The processing failure has a separate configuration cause. **VA Input Response
Generation** (`aca5634f4312121038520464dbb8f236`) resolves through the Custom LLM
definition `e0f1b0cb9373cf14e7f2b9fa6aba1073` and prompt binding
`24f1b0cb9373cf14e7f2b9fa6aba1076` to active published AI configuration
`e8f1b0cb9373cf14e7f2b9fa6aba1074`. At failure time it requested
`Gemma 4 26B-A4B`. The local Gateway correctly rejects that fixed model when
Halogen is selected. Failed GenAI executions and Gateway409 corroborated this.
After its repair, the actual VA Input invocation succeeded on Halogen; separate
successful ReAct executions alone would not establish that result.

This conversational dependency is outside the 66 Agent prompts. It is also not
the controller of every audio frame. The current local conversation follows
`NativeCall → NativeDuplex → PipecatDialogue → OmniConversation → LocalTextSocket`
and the central local model selection. The native external Voice provider
resolver instead shares AIA ReAct (`f6f9e6e71bc38210f4200d81ec4bcb30`) and returns
provider/connection information without a Voice-only model field. TTS, STT,
conversation and Agent configuration remain distinct.

## Active adapter behavior

- Exactly one call-owned startup task runs concurrently with the configured
  native introduction. Independent local conversation can proceed while that
  startup completes. Business input is held until real ServiceNow readiness.
- The subsequent genuine input question retains its request/control binding.
  Partial startup metadata cannot authorize a stale question or a business
  response. Early input retains its original order and meaning.
- A genuine person-name input is read back exactly before submission. A fresh
  explicit confirmation must belong to that completed readback and current
  request/revision. Rejection asks for spelling. The adapter neither guesses
  spelling nor invents ASR confidence. An early intent or an unbound yes/no
  cannot become a later person's name.
- Cleanup requires successful media-peer closure and acknowledged backend
  cleanup before releasing capacity. Fixed phase/timing logs identify a blocked
  stage without logging credentials or conversation payloads. Submitted work
  is not retried or discarded to free the slot.

The old 12:20 input-free SDK test remained reserved after DELETE 202. Its exact
native process was replaced during authorized maintenance. The actual old hang
is not proved fixed by the new logs or the independent cleanup-exception fix.
The initial proposed TURN→RTCP causal chain was withdrawn after correcting the
asynchronous transport boundary; no dependency update or monkeypatch was made.

The first replacement attempt incorrectly used the observed base Python
executable, which lacked aiohttp. It exited before app initialization. Recovery
used the normal virtual-environment launcher through `start_services.start_python`
for Native alone. New native PID26472 was ready with zero sessions; exact process
identities of controller, Gateway, bot, ASR and own TTS were preserved. The owner
receipt and private activation evidence record this distinction.

## ServiceNow change boundary

Three normal repair preflights each wrote zero source/header/capture rows. They
must never be rerun. Native readback then compared 1,030 fields on 40 rows,
including actual field types, Boolean 0/1 and null; no unexpected difference remains.
An initial claim of damaged frozen Unicode was a local diagnostic decoding
mistake and has been explicitly corrected in the private evidence.

The target/model ACLs deny ordinary writes. Its native form remains disabled,
and this platform capability has no demonstrated eligible SkillKit entry
(`type` empty, no SkillConfig). Marcel explicitly approved the administrative
capability repair. The owned default configuration now selects `halogen-v2`,
revision 4. Native calculated `request_tokens` changed from 28,422 to 257,798;
the script did not write that calculated field. Prompt, schema and all 39
surrounding guard rows remain unchanged.

The completed repair has one `INSERT_OR_UPDATE` Customer Update in its separate
scope-correct WIP Update Set. Native header application ACL behavior and capture
context required guarded continuations; submitted artifacts were never replayed.
The final continuation moved only the newly generated capture, with its payload
unchanged, and restored/preserved the original current-set context. Fresh typed
readback verified all 1,030 fields on 40 rows, seven exact relationship
memberships, the header contract and the one-record no-delete XML payload.
No role, ACL, protected manufacturer source, completed 2.3 Agent batch or sealed
2.2 package changed.

Reusable [capability model maintenance scripts](../servicenow-byollm/capability-model-management.md)
provide preview-first switching and additive model alternatives with independent
prompt lineage. Their current complete byollm test run passed 231/231. Native
Switch, Add-existing and Add-new-draft previews also passed with zero writes;
no reusable bulk apply was run.
It intentionally reports a broader active/published selection than this repair,
including the separate nondefault Gemma prompt left unchanged here.

## Verification and remaining acceptance

The broad offline run passed 971/973 checks. Two untouched narrow deadline tests
had differing current/immutable-HEAD outcomes; their source dependencies are
byte-identical. The evidence records those outcomes without presenting the
entire suite as green. Subsequent focused name/bootstrap checks passed 52/52,
final lifecycle/startup/SDK checks passed 70/70, and Root's integrated current-source
startup/name/cleanup/SDK run passed 80/80. Synthetic DC/sine unit
fixtures isolate denoising only at their timing/wiring boundary; real pinned
RNNoise and actual-speech coverage remain. Production DSP was not relaxed.

The native Test Assistant was genuinely attempted in Voice mode. The embedded
browser reported **No microphone found** before any native call or request.
This does not test Voice latency. The normal native PKCE authorization flow
subsequently succeeded through the existing SDK alias and unchanged native
client/assistant claim; ServiceNow confirmed the required agent and current
assistant settings. No scope or permission was added. A first local attempt
failed before authentication because numeric Windows SIDs require an asterisk
prefix in icacls; a new one-shot artifact corrected only that prefix and its
output path. The token folder/file were independently checked to allow only
the current Windows SID.

A bounded synthetic SDK-HTTP/RTC probe then used that fresh native authorization
against the running adapter. Its first run ended early because its waiting
condition counted old backend audio before the new help response. The tested
correction binds fresh model TTS start/finish markers and subsequent fresh audio
quiet. The original failed receipt and executed bytes remain preserved.

The corrected frozen run completed **two SDK calls**. First received audio was
8.375 and 8.922 seconds after each SDK create began; this includes the probe's
complete ICE gathering, and is not a physical-mobile timing claim. The native
greeting was synthesized concurrently with real ServiceNow initialization.
The first hearing reply occurred before backend readiness in the initial run.
Actual controller-selected conversation output was released in the corrected
run, with two current completed TTS segments, rather than a deterministic help
fallback. Their ASR caller identity and fresh native-log window are recorded.

The second call produced an exact readback of the actual recognized name. Its
negative answer interrupted that readback and produced the spelling question;
no positive confirmation or business input was sent. This verifies rejection
and interruption, not complete heard playback of every name/spelling segment.
Client quiet plus emitted PCM cannot establish that full playback. Both calls
closed with acknowledged backend cleanup in 0.828/0.858 seconds and zero native
sessions, allowing the second call to begin. Configuration hashes stayed fixed.
The original 12:20 remote-call hang is still not fully explained by these local
results. The in-process fallback remains unused.

The corrected probe receipt's `passed` means this bounded contract passed. It
does not establish complete model-terminal observation, physical phones, public
Funnel/NAT, real microphone/noise quality, positive name submission or business
context/progress acceptance. No old bearer, fake authorization or historical
settings substituted for the native contract.

After the metadata repair, one new genuine SDK/RTC probe received the configured
introduction and actual name question, read back the exact raw synthetic-name
ASR, and waited for full current TTS completion, conservative queued-audio drain
and fresh received PCM quiet before sending one name-only `Ja`. No later input
was sent. The next backend response did not arrive within 40 seconds, so the
probe failed. Correlation through the actual native conversation subsequently
proved VA Input succeeded on `halogen-v2`, accepted the exact raw name and
returned control to the agent (7,307ms, no error). Two downstream capability
invocations then failed with error `200000`: the current default prompts for
AIA Unified Planner Quick and AIA Unified Planner still selected Gemma. Their
definitions were absent from the earlier four-definition Agent allowlist.
The first host-time-based query missed these records because the native table
clock is approximately 88 seconds behind the host. Match actual conversation
and payload identity, rather than assuming synchronized clocks. Cleanup was
acknowledged in 1.078 seconds and capacity returned to zero.

The approved targeted continuation now changes only those two Planner prompt
models to Halogen. A separate scope-correct WIP header contains their exact two
no-delete Customer Updates; source revisions advanced 4→5 and 6→7. Fresh external
typed readback compared 97 original rows, 2,726 fields and all unchanged query
memberships, with no unexpected difference. The two captured XML payloads match
every source field except native calculated `request_tokens`, which was never
manually written. Original application/current-set selection is restored.
The new bounded post-repair positive-name observation is separate from the
first failed receipt. It received backend content after the name confirmation,
but then the native completion-error text and an automatic retry announcement.
The overall probe remained failed. Actual conversation correlation proved all
six model invocations successful on Halogen. Native application logs instead
identify an undefined subtask/cache value in `AgentReActivePlannerUtil`.

The initial native plan and first task already contain objective `undefined`.
The configured picker choice is a promoted standalone-agent skill. Native
`InvokerUtil` has a central objective fallback for a selected workflow, while
that standalone entry supplies neither a typed task nor that workflow binding.
A dedicated native workflow containing the same SCC agent is prepared, with
an explicit ReActive Planner strategy and central `promoted_skill_objective`.
Marcel approved the finite native workflow/security/profile/test scope. One
normal modern AIUX Save created the own SCC Laptop Onboarding Voice Workflow,
its dedicated team with the original SCC agent, published V1, one proper
workflow execution ACL with an admin link, and dynamic identity restricted to
the existing itil and scc_voice_context_reader data roles. Both existing
agent ACLs and their role links are unchanged. The native ReActive Planner
strategy was already correct. The initial ten Customer Updates landed in the
previous Global set because the browser and SDK capture contexts differed;
the exact unchanged-payload reconciliation is complete. The central objective,
generated skill/configuration and sole added Voice-profile membership are also
complete and independently verified. The Global set contains sixteen captures,
including one ordinary native metadata-dirty flag. The skill's displayed name
is virtual and must not be manually populated to match its older capture. See the
[entry design](../superpowers/specs/2026-11-02-voice-entry-context-design.md).

The revised V3 diagnostic rejects the actual native error and automatic-retry
phrases immediately. Its one live run failed before any caller input: the new
workflow was advertised and selected with the correct objective/team, but native
access verification ran as guest and rejected the original SCC agent. No GenAI
or tools ran. First audio was 10.578 seconds including full client ICE gathering;
owned cleanup was acknowledged in 0.766 seconds and capacity returned to zero.

The channel profile already points to the verified caller, and the interaction
is already verified. Replacing static email alone is therefore not a demonstrated
cure. The normal native Voice manager performs an additional own-session sign-in
after CREATE. Direct local B2B CREATE followed by START_CREATED omitted that step.
The repair uses the original Voice caller bearer and that native routine, without
assigning a user identity, changing ACLs or using the SDK administrator as a proxy.

The existing authorized-agent resource now has an explicit private caller-binding
opt-in, based on the authenticated GS user and an unambiguous native email mapping.
It was deployed normally in the own Voice AIA set and verified using the original
Voice bearer. The token's subject is a user name, not an email. The Voice token
cannot use ordinary Table API; its scope must not be broadened for this repair.

The active local transport forwards the original credential once to the
loopback Bridge, independently resolves the caller, and keeps a private ticket
for at most 45 seconds across CREATE. The authenticated CREATE callback must
bind the pending request, private cookie, conversation, interaction and creation
message. One distinct native refresh is required before START_CREATED. Returned
identity and all bindings are rechecked after the await. Failure, cancellation,
reset, end, expiry and shutdown retire the ticket. No identity or credential
enters public SDK state, model context or logs. Fresh focused local checks passed
55 Bridge/caller/refresh plus 94 Native/SDK/lifecycle tests. Independent review
found a partial-CREATE observation race: a poll could freeze incomplete metadata
and reject its later interaction ID. Native now publishes only a complete
immutable tuple. The new regression failed before the fix and passed afterward.

The server resource's owned-session refresh opt-in is deployed at revision 17.
One normal update produced a complete automatic capture in the same working
Customer Update. The wrapper stopped because native history replaced its current
entry rather than prepending it. Fresh readback proves exact source/capture,
all six older history entries and all unrelated records/captures preserved.
No repeated update or additional manual capture was needed. The full current
tracked byollm test run passed 474/474.

One exact idle cutover activated only Bot and Native plus two Bridge settings.
Model/controller, Gateway, ASR and own TTS generations stayed unchanged. The new
V4 probe ran once and again failed before caller input. Its native refresh
response allowed START_CREATED, but the initial selected workflow did not reach
its input control. Correct introduction arrived after 9.078 seconds including
full client ICE gathering; acknowledged cleanup took 0.453 seconds, leaving
capacity zero. No name, confirmation or later input was sent. Its temporary
bearer was removed. Actual native identity/access and helper logs remain under
investigation; this result does not establish an authenticated runtime.

A refresh response means only that the native routine was requested. It cannot
prove the running VA session is authenticated. A future bounded probe must prove
actual access verification and a root Orchestrator task before the SCC child,
then name-only confirmation and normal continuation on Halogen. Previous failed
receipts are immutable. No order consent or later question answer is allowed.

Remaining: diagnose the failed native own-session handoff, prove normal post-name continuation,
then verify one genuine, bounded ServiceNow
context/progress sequence. Raw caller context requires matching
request identity plus `contextStored`, `inputBoundaryConfirmed`, `promptIncluded`
and `ingested` before retirement. Progress must reflect fresh ServiceNow work.
Common NativeCall/SDK contracts cover all clients; physical iPhone/Android
playback, microphone/noise quality and public-network behavior still require
their own evidence. After any deliberate central model change, audit the active
VA Input prompt separately from Agent prompts and verify a new native execution;
model health or a successful ReAct call alone is insufficient. Fixed Gemma
identities must not silently become aliases for Halogen.

Private investigation receipts live under
`server/.local/voice-repair-20261102/`; source and technical documentation contain
no OAuth tokens or private conversation dumps. Current handoff is TASK81.

## Original-caller CREATE installed; VA session authentication remains open

The V4 native records now prove guest/guest execution, one failed child-agent
access-verification task, and zero GenAI/tools. Completing the account-link
topic can mean only that a stored profile already exists. Entering CREATE as
the original HTTP caller was tested as a correction hypothesis; V5 shows that
it does not by itself authenticate the later VA worker.

Marcel explicitly approved the prepared seven-record package. The own route
`POST /api/sn_voice_aia/local_voice_caller/create` and its exact endpoint grant
are installed through the normal UI in a separate Voice AIA working update set.
Independent readback and a second local audit checked 37 complete typed rows,
17 complete query groups, seven captures and all 151 captured source fields.
Old source rows, captures and the original client/profile relationships remain
unchanged; only the two approved additional relationships were added. The
policy's displayed Version is ordinary update history, not an eighth security
record. Native description truncation and script CRLF normalization were
verified without repeating a save.

The installed source accepts only three private correlation IDs and version1,
requires the original authenticated GS administrator and fixed SCC service,
obtains its own user/email and central settings, then performs one normal public
synchronous empty CREATE. It requires genuine complete native IDs and normal
stored ownership proof. A success ACK without IDs cannot release START.

The local change is active with the exact own path selected. It forwards the original credential
once to only the exact own instance/path under the existing 45-second ticket,
binds the direct result to the private pending request/cookie/caller, and keeps
the distinct normal refresh. There is no anonymous fallback or retry. WS/SDK
front-end authentication and media behavior stay common.

Independent review found and closed exact-host and Bearer-scheme-case cases.
Fresh canonical checks passed 692/692 byollm tests and 75/75 Bridge/caller tests.
The new native source's 218 cases are included in that 692 total. These source
checks do not prove the asynchronous principal. One idle Bot/Native cutover
preserved the model/controller, Gateway, ASR and own TTS generations. One fresh
normal Voice Agent PKCE and one immutable V5 SDK/RTC test followed.

V5 created the conversation through the strict own endpoint and completed its
normal refresh/START transition, but failed before any name or confirmation
input. Actual native records prove that both worker user fields still equal
`guest`; the original SCC child fails ACL verification, with zero GenAI and
zero tools. First audio took 9.969 seconds including full client ICE gathering.
Acknowledged cleanup took 0.438 seconds and left native capacity zero. No order
or later data input was sent. This is an unsuccessful repair result, not a
passing authentication test.

The next investigation is the supported channel sign-in protocol and its
completion boundary. HTTP caller authentication, stored account ownership and
VA worker authentication are separate evidence. Do not repeat CREATE/START
experiments, alter roles/ACLs or substitute identity fields for an actual
native sign-in completion.

The V5 temporary token file remains in its restricted local test directory:
automatic approval review rejected both the combined cleanup and a single-file
delete with only `blocked by policy`. No alternate deletion method was used.
The single owned token was instead revoked once through ServiceNow's documented
issuer endpoint at 21:46 UTC. A subsequent ordinary read-only authorization
request returned 401, confirming that the retained credential is invalid.
Local file cleanup remains outstanding.
Private V5 installation, activation, test and runtime receipts are retained under
`server/.local/voice-repair-20261102/entry-workflow/`.

See the [design](../superpowers/specs/2026-11-02-local-caller-create-design.md)
and [plan](../superpowers/plans/2026-11-02-local-caller-create.md). Full Voice and
physical-device acceptance remain open.
