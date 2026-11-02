# Voice repair — 2 November 2026

The direct failure report supersedes the earlier wait for a phone-test result.
The adapter repair is active. The approved ServiceNow VA Input and two Planner
model corrections are applied and independently read back; complete live
acceptance is not yet established.

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
failed receipt; its full continuation must still be established.

Remaining: verify the downstream post-name Planner continuation, then
verify one genuine, bounded ServiceNow
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
