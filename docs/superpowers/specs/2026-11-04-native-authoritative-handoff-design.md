# Native authoritative conversation handoff

Status: source investigation and proposed design only. No production code, live request, model action, or installation is part of this document.

Base: `835bb6c3a4d53e3b0743643506dd46b3a5d8388a`. The separate local claim guard remains commit `8790ce36d7fd3d28d7f4a0f2c3a03ba99806d9b3` and is not integrated here.

## Intent and evidence

Keep fast local conversation, while ServiceNow remains the sole business executor. A caller must hear the genuine native confirmation before any later utterance can be submitted against it. Native must deliver actual ServiceNow information despite queued local conversation, and an already audible local sentence must finish across harmless observation changes.

Saved call `b975256a795e` demonstrates three distinct failures:

- The Boolean control contained a full employee/manager/date/location summary followed by the confirmation question. Neither that full summary nor mixed caller remarks reliably matches the existing `_polar` / `_polar_answer` heuristics. Unheard queued remarks reached native Boolean `searchText`; an actual request and item were created. This is not merely slow speech.
- An actual complete `OutputText` reached Native before input-track loss, but local task-revision/pending-FIFO admission suppressed it. Its callback had no `completed=True`. It must be delivered without inventing a success classifier or requiring conversation end.
- Active conversation PCM stopped at a callback/FIFO change without caller speech. CPU probes reproduce both observation-revision and pending-FIFO invalidation midway through synthesis.

Evidence: canonical `server/.local/voice-repair-20261102/real-call-b975-20261104/` contains the saved actual messages, timeline, source audit and CPU probes. Private data stays there; no caller names or order identifiers are needed in source fixtures.

## Current protocol and ownership loss

`voice/bridge.py` authenticates callbacks and resolves the exact current request or its explicitly bound context alias before consumption. It then flattens both `OutputText` and `Input*` controls into events with only `id`, `kind`, and `text`. The polling response separately exposes the latest typed input boundary and scalar busy/ended flags.

`Dialog.turn` consumes that scalar state before delivering `on_reply(str)`. Native cannot recover each event's original type/request by labeling the string with the latest state. OutputText alone does not settle a turn under `wait_for_input_control=True`; `completed=True` closes input and opens the existing bounded final-text drain. Conversation end proves closure, never business success.

`NativeDuplex._business` gates only text matching both polar heuristics. Its result admission additionally requires the original local task revision and an empty pending queue. `_valid` applies the same context freshness checks before speech and after every PCM chunk. All three decisions need separate ownership rules.

## Approaches

1. Extend text heuristics or adjust prompts. Small but cannot prove which question the caller heard or classify authoritative events; rejected.
2. Stop concurrent conversation and serialize all caller speech with business execution. Simpler, but loses the already improved interaction and still needs explicit confirmation provenance; rejected.
3. Preserve authenticated event provenance, add a typed Boolean input barrier, and distinguish queued-output freshness from an active sentence's hard ownership. Recommended. It fixes the demonstrated mechanisms without choosing business data or interpreting approval locally.

The user has delegated implementation choices and opted out of questions. This recommendation is an engineering proposal for Root's source review, not a new user approval request.

## Bounded file responsibilities

- `voice/bridge.py`: attach callback provenance when events are created, report request-owned lifecycle state, return the accepted business request ID, and compare Native's expected Boolean binding before dispatch.
- `voice/native-bridge/native_backend.py` (new): strict immutable event/state/control-binding types and a pure Boolean barrier/held-input ledger. It has no network, speech, model or business tools.
- `voice/native-bridge/native_bridge.py`: optional typed event callback, exact ACK/event/state validation and an explicit not-dispatched conflict result. Existing `on_reply(str)` and list-of-string return stay compatible.
- `voice/native-bridge/native_duplex.py`: use the typed lane, prioritize native control/information, hold unbound input, and issue active-sentence leases after the first accepted PCM.
- `voice/native-bridge/pipecat_dialogue.py`: expose source-generation ownership separately from mutable presentation scope, using the existing Omni source identity check. No controller/Omni generation protocol change.

## Authenticated handoff contract

Existing bot events and their text-only deduplication stay unchanged. Add an independent bounded `backendEvents` lane at authenticated creation time. Each immutable receipt contains numeric `id`, exact source `servicenow_bridge_event`, normalized `businessRequestId`, exact `uiType`, `text`, and `streamComplete: true`. Both lanes use the existing shared monotonic cursor; a typed-only change advances that cursor without duplicating legacy display speech. Deduplicate typed receipts per request/type/text, not just display text, so identical OutputText and Boolean labels retain separate provenance. Reset only the per-request dedup set on a new dispatch, not retained already emitted receipts.

The producer boundary is the matched authenticated callback or an already validated direct START response; the Native MESSAGE lane additionally requires its exact accepted MESSAGE request. Only already accepted, nonpartial, nonsecure controls receive a typed receipt. Empty controls still appear through the genuine input-boundary state; no question is fabricated. If an OutputText and current input-control label match exactly in both text and original request, Native may coalesce their speech into the genuine control item while retaining both receipts. It may never infer a control from text alone.

The MESSAGE ACK adds its actual `businessRequestId`, returned by the same `send()` invocation that minted it, not sampled from a later session request. Typed event IDs come from the authenticated envelope after alias normalization, not from a later Native caller turn. Polling adds `backendEvents` filtered by the same requested cursor and request-owned state with source `servicenow_bridge_state`, `requestId`, `action`, `busy`, `ended`, and `failed`; its values are produced from the existing Bridge state machine. Native validates typed events/state against the ACK and its immutable Dialog/conversation owner. Context aliases remain bound to their original still-current business request. Old-session, old-request and malformed metadata cannot enter this lane. Native's typed path uses on_event for privileged output and must not also release the same legacy string callback.

The optional `Dialog.turn(..., on_event=..., native_control_binding=...)` path leaves legacy callers unchanged. Native always supplies the binding argument. A `None` value asserts that it has no heard Boolean to answer; an exact binding asserts the genuine control it heard. Bridge compares this optional field with its current Boolean boundary, including the exact full label, under `session.lock` and before `send()` mutates request state. A mismatch returns structured HTTP409 with `dispatch: not_started` and the current genuine control. No ServiceNow request was sent; Native holds the original. Missing ACK or uncertain HTTP remains unknown and is never retried. Clients omitting the optional Native field retain their current behavior.

## Boolean control barrier

Use typed `controlType == Boolean`, never words in the question or caller reply. A binding is `(businessRequestId, controlType, full exact label)`. Its lifecycle is unspoken, speaking, awaiting fresh input, dispatched, or retired.

When a new Boolean appears, remove every queued prequestion/unbound turn from the dispatch FIFO into a held-original ledger. Preserve the entire original envelope, onset, voice/language snapshot, ordering and hold reason. Held means not sent, not approval, not consumed as an answer. Do not later replay it, rewrite it into yes/no, or publish it as supplemental approval context. An in-flight older context update cannot be unsent; its receipt remains context-only and must never open the barrier.

The same rule applies to every utterance arriving while the control is unheard or incomplete, including pure yes, mixed yes-plus-question, dates, corrections and arbitrary meta speech. Raw local conversation/history may retain it as held context. The ledger itself does not keep Native business-busy or invalidate the question. Existing non-Boolean raw delivery is unchanged.

At a sentence boundary, speak the complete exact current native control label ahead of optional queued local speech. Drop queued optional replies that would otherwise speak after this handoff and imply an answer to older input. Do not start/restart optional model responses for held prequestion input while this handoff is pending, and do not allow older in-flight candidates or their fallback to speak after the control and steal its answer context. A genuinely new, bound utterance can resume ordinary dynamic local/native conversation. Newer native controls retire older queued questions.

The control becomes answerable only after synthesis completed normally and all accepted host PCM samples were emitted, without interruption, for that exact binding. This is server-side emission evidence, not proof of physical phone playback. Reuse the existing onset envelope so a VAD onset before completion cannot become fresh merely because ASR finishes later. A local question that supersedes the native question cannot lend its answer binding to ServiceNow.

Only a new onset carrying that complete current binding may dispatch its original text once. Native does not infer BooleanTrue, select an option, or fabricate consent. Mark the binding dispatched before I/O; uncertain outcomes do not replay. If the control changes before POST, Bridge's comparison rejects before dispatch. A control with no public label remains held and unavailable for spoken confirmation.

## Authoritative information and conversation end

Every typed complete `OutputText` from the owned accepted business request is an immutable informational receipt. It can contain an outcome, explanation or error; its words do not determine its authority. The existing exact generic-filler presentation suppression can remain, but cannot be used to classify success or discard concrete output. Queue its actual text ahead of optional local output even if later caller turns changed local revision, pending count or output epoch. Bind it to its original Dialog/conversation/request/event, never relabel it as the latest caller turn.

Keep a separate per-call receipt ledger and priority queue, outside `_outputs` and the local-turn clear/revoke paths. New local input cannot erase a receipt that has not started speaking. Receipt delivery states are pending, active, fully host-emitted, interrupted or retired by explicit call close. One event enters the ledger once. An interrupted receipt remains audit evidence and is not automatically restarted over the caller.

Do not wait for ended or turn settlement to admit such text. The demonstrated final OutputText had neither. Stale `Input*` questions remain fenced by the latest control binding. Missing or malformed typed metadata gets no privileged bypass.

An actual owned `ended=True` stops further business dispatch and retires input controls. It does not clear queued legitimate informational receipts or call the generic unavailable interruption path. Keep the existing final-text drain and do not synthesize a success claim from closure. Explicit local close, input loss and call failure still stop audio.

A real caller interruption stops current audio immediately. Retain receipt delivery status as interrupted rather than claiming it was heard; do not issue a new business request or silently replay an order. A retained interrupted receipt can support a subsequent user-requested explanation. This wave guarantees priority over queued local talk, not unconditional audible delivery after the caller closes or interrupts.

## Active sentence ownership

Before the first accepted PCM, retain all existing admission, epoch, context, source and identity checks. After that point, the single sentence holds a lease on its exact output, playback generation and model owner/source-generation identity. Harmless observation, pending-FIFO advance and local task-revision changes cannot truncate that sentence. A newly admitted native reply waits for this sentence boundary; it does not cancel it.

The lease still stops on caller epoch/generation interruption, local close/input loss/failure, model owner replacement/closure, source session/socket/turn/generation mismatch, or invalidation of a genuine active control. `PipecatDialogue.is_source_current(identity)` delegates to the existing Omni `is_stream_current` ownership check while deliberately omitting only Pipecat's mutable presentation scope. It must not merely compare strings or assume a closed source remains current.

Queued later sentences continue to require full context freshness. The lease neither rescues unreleased stale candidates nor relaxes claim, number, markup, identifier or business-completion guards. `_finish_speech` uses the same active lease rules; transcripts distinguish intended text, accepted PCM and complete emitted PCM.

## Observability and acceptance

Record IDs, reasons and counters for barrier creation, held inputs, exact control emission completion, bound dispatch, receipt queue/delivery and active hard-stop. Avoid raw private text in routine logs. Important control/result decisions must remain observable after the existing eight-message generic discard budget is exhausted.

Acceptance is CPU-first: exact unsafe caller remarks cause zero outbound business requests before the exact confirmation is emitted; a genuinely new bound raw answer reaches the fake backend once; held originals never reappear later. A complete typed OutputText reaches fake synthesis with four later originals pending and ended false. Existing two-chunk reproductions finish both chunks for harmless changes and stop on real hard invalidations.

Then Root may review a coordinated Bridge+Native installation. No model change, capability reassignment, cloud inference, microphone recording or business replay is needed. Any subsequent live test must stop before an approval boundary; physical iPhone/Android playback remains a separate device acceptance check.
