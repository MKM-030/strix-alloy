# Task 15: input ownership and deferred speech — design and implementation plan

Status: Root-ratified Task15 design; implementation starts only after Task14 independent fix review passes.
Baseline inspected: Task 14 HEAD `382df2dc9614fc88ee3a851b9848b26fc6542e56`; the three source files had no working diff.
Evidence: `silent-inference-inputepoch-audit.md`; real source and existing native/output tests inspected read-only.
No models, network, services, instance, closed evaluation data, product edits, or subagents were used.

## Product contract
1. A confirmed newer VAD onset permanently invalidates older transient local speech, even during silent inference.
2. Invalidation affects speech only: never add input identity to routing authority, store preconditions, or business acceptance.
3. Journaled backend replies that have not started speech wait through input resolution, then revalidate their own task/context.
4. A still-relevant retained reply speaks once; superseded speech is suppressed while all existing journal outcomes remain.
5. Once speech start has been claimed, interruption ends that delivery. Never replay its transcript, prefix, or full answer.
6. Transcript stays at permitted speech start; deferring an entry emits no transcript.
7. Preserve actual Silero/EndpointGate onset and noise policy, legacy mode, queue bounds, priorities, ownership, and cleanup.

## Scope and additive interfaces
Production edits: only `voice/native-bridge/native_bridge.py`, `conversation_output.py`, `task_coordinator.py`.
Tests: extend `test_responsive_native.py`, `test_responsive_output.py`, `test_responsive_coordinator.py`; add one focused integration module if cleaner.
No router/model/proposal/policy/store/config/runtime/assets changes. Task 14 decision and durable-acceptance semantics remain intact.
Public event FIELDS and existing plain `accept`, `publish`, `publish_guarded`, emit(event), interrupt(), and wait_idle() contracts stay available.

`ConversationAttachment.accept_guarded(utterance_id, text, *, output_validity, voice_context=None)` is additive.
It delegates to `accept_decision(..., output_validity=...)`; add that optional keyword without changing existing return contracts.
`accept()` remains the existing Route projection; its unguarded callers retain legacy behavior.
Native feature-detects accept_guarded and otherwise calls the existing accept signature for fake/legacy attachments.
`_queue(..., output_validity=None)` carries a private `_input_validity` callable for every acceptance-created local reply.
Do not store this callable/epoch in voice_context, Route, RoutingDecision, events, task records, logs, or business authority.

`OutputSink.interrupt_for_input()`, `publish_deferred(event, validity)`, and matching arbiter methods are additive.
`OutputArbiter(..., *, input_ready=None, control_ready=None)` defaults both readiness callbacks to true.
`OutputArbiter.notify_input_changed()` only sets the scheduler wake event; it never fabricates idle or changes business state.
`OutputArbiter.publish_control(event, validity=None, *, wait=False)` is the private native lifecycle publication lane.
When wait=True, await that entry's terminal disposition, not global queue idle; shield delivery ownership from waiter cancellation.
Existing callers and fake emitters receive exactly the original seven event fields and need no new methods.

## Native input identity
Maintain a monotonic call-local `_input_epoch`, independent of playback.generation, beginning at zero.
Advance exactly when the existing gate.feed(..., voiced=...) returns began; never on RMS alone, ASR completion, or acceptance.
Capture that epoch in the microphone worker's per-utterance local variable; do not read the current epoch at endpoint time.
Carry it through queued PCM, ASR, recognized text, language controls, and the actual acceptance call.
Use private immutable tuple-compatible envelopes for audio (the existing two values) and recognized turns (the existing five values). An immutable wrapper with the same unpacking/sequence behavior is allowed; actual tuple subclassing is not required.
Each envelope has immutable input_epoch metadata; transcript tuple unpacking, playback generation, and existing helpers remain compatible.
Legacy-mode producers retain ordinary tuples. For old synthetic injected tuples in responsive tests, use fixed epoch zero, never the current epoch.
Production responsive microphone entries must always be tagged; tests explicitly assert this invariant.
At dequeue create the closure `origin == call._input_epoch` plus call liveness, capturing origin as a value before any await.
An older queued recognized turn remains eligible for normal business acceptance but cannot acquire a newer speech identity.
The acceptance interrupt still advances playback; it cannot alter or invalidate the captured input epoch by itself.

## Activity readiness and notifications
Ordinary input_ready is true only when call live, no confirmed active VAD, no queued audio, no active recognition,
no recognized-turn backlog, and no actual acceptance in progress.
Track acceptance with a private counter/flag around the awaited attachment call, balanced in finally on every exit.
Update input state and enqueue its next pipeline stage synchronously before waking the output worker: no false idle handoff gaps.
Notify after onset, endpoint/finish (including a discarded short utterance), audio enqueue/drop, ASR enqueue/empty/error/finally,
recognized dequeue, acceptance finally, queue discard, receiver retirement/replacement, input loss, failure, and close.
An endpoint that returns no PCM must still release the activity condition and notify.
If receivers can overlap during replacement, derive responsive VAD readiness from active receiver identities, not one overwritten bool.
Retire each receiver's identity in finally; never clear another receiver's active state to manufacture idle.
The existing legacy vad_active behavior can remain; responsive readiness must reflect all live receivers accurately.
Terminal input loss/close uses the hard speech interrupt and cancels the output worker normally; pending waiters complete.
Business observation/END ownership and unresolved reservations follow the existing coordinator lifecycle unchanged.

## Lifecycle lane and concrete deadlock resolution
Native startup greetings, language selection/retry feedback, connection notices, and inactivity controls are lifecycle outputs.
Their private control_ready waits for physical input only: confirmed VAD, active ASR, and queued audio must all settle.
It deliberately excludes recognized-text backlog and acceptance, so greeting/language barriers can release the intake pump.
This exception is restricted to explicit native publish_control calls; ordinary local/status/backend output cannot opt into it.
Native backend-kind greetings are transient control entries, not durable task replies; event.kind alone never determines retention.
Pass the recognized origin guard to input-derived language/not-accepted notices; autonomous notices capture their own issuance epoch.
Replace responsive_notice(wait=True)'s global wait_idle with per-entry completion from publish_control.
Remove responsive_startup's redundant global wait_idle before greetings; the single arbiter already serializes synthesis.
Keep greeted/language_ready ordering and existing ready-before-dispatch discipline; do not rewrite the intake pump or add another queue.
A stale/interrupted control entry still completes its waiter, matching existing interrupted wait behavior.
Tradeoff: lifecycle speech may precede processing of already recognized text, but never physical VAD/ASR/audio input.
Include this ordering explicitly in tests; ordinary backend replies still wait for recognized backlog and acceptance to settle.

## Coordinator propagation and retention
Every local _queue call within accept_decision receives the same output_validity: help, clarification, status, acknowledgement,
cancellation acknowledgement, authority-change fallback, and StoreConflict rejection alike.
Combine it with existing help checkpoint/authority validity only at the output boundary; preserve their exact Task 14 logic.
Never feed the speech predicate into authority(), checkpoint decisions, counters, dispatch, cancellation, or durable_acceptance.
At _output, strip all private metadata before validating/emitting the event; bind closure variables per dequeued entry.
For local events, evaluate combined validity before legacy emission and use publish_guarded when available for downstream checks.
For backend events, build a repeated predicate checking attachment/owner and exact own task context_version in its authorized scope.
Do not substitute global focus/checkpoint equality: an unrelated current task must not invalidate this task's current backend result.
Use publish_deferred when available; otherwise keep the existing checked plain emitter behavior, without new emitter arguments.
Only coordinator-originated backend_reply entries receive deferred disposition; existing task/error semantics are not reclassified.

Make `_interrupt(*, preserve_deferred=False)` additive internally.
The acceptance preamble uses preserve_deferred=True, calling sink.interrupt_for_input when supported and retaining backend queue entries.
Use a synchronous bounded drain-and-restore of that existing max-eight queue; preserve order and current queue-full policy.
With old emitters fall back to their existing interrupt. No arbitrary await occurs during queue filtering.
Explicit stop_speaking additionally invokes the existing hard interrupt after its decision; detach/failure/close keep hard interruption.
This distinguishes speech-control cancellation from acceptance's normal playback interruption without changing business routing.

## Arbiter state machine
Use one existing max-eight pending list with private per-entry disposition, validity, generation, and optional completion future.
Dispositions: transient (existing publication), deferred backend (explicit publication), lifecycle control (explicit native publication).
Deferred entries have no playback generation until the first permitted start; transient/control entries keep enqueue generation fencing.
Input/onset interruption always advances playback and cancels active delivery, even when synthesis/PCM are currently empty.
It removes pending transient/control entries, preserving unstarted deferred entries; hard interrupt removes every speech entry.
Already-started backend speech is never returned to pending after interruption or failure.
Avoid the task-scheduling gap: retain an entry in pending until _speak atomically claims start, or implement an equivalent explicit
reserved/unstarted slot whose cancellation preserves deferred entries within the same existing bound and priority rules.
Claim start only after rechecking liveness, own-task validity, input/control readiness, and applicable generation with no intervening await.
Set started before invoking the transcript callback; this is the at-most-once boundary even if an async transcript callback yields.
Capture deferred generation at that claim; every later check uses that fixed generation and cannot restamp an interrupted delivery.
Repeat eligibility and validity immediately before transcript invocation, after any awaited transcript, and before every playback.put.
An onset during active speech cancels it; the predicate checks also fence chunks yielded concurrently with the cancellation.
A queued-but-unstarted entry whose readiness becomes false stays pending; it must not be permanently discarded merely for being paused.
Invalid ownership/context/origin, terminal liveness, overflow, hard stop, or close suppresses it permanently and resolves its completion.
On wake, prune permanently invalid entries and choose the highest-priority currently startable entry, preserving stable order.
Do not let an ineligible ordinary entry block an eligible lifecycle entry needed to release startup.
If nothing can start, return to Event.wait; notification producers update state before setting the event, avoiding polling/lost wakeups.
wait_idle remains false with retained pending entries and true only when no pending/active work remains; never clear state to satisfy it.
Preserve existing generated/sent counters and audio-failure handling; no audio-heard claims or new outcome journaling.
Resolve per-entry completion on all terminal paths, including eviction, rejected publication, pre-start cancellation, and close.
Keep overflow/error reporting bounded and avoid emitting a deferred backend transcript from diagnostic or cleanup code.

## Exact implementation sequence after Root ratification
1. Reconfirm clean three-file baseline at the accepted Task 14 commit; incorporate review fixes first if Root supplies a newer baseline.
2. Add deterministic failing integration cases to the real NativeCall harness before production changes; hold inference with asyncio Events.
3. Implement private origin envelopes and responsive input readiness/wake hooks in native_bridge.py without altering endpoint decisions.
4. Implement bounded arbiter deferred/control states, preserving default APIs and existing output tests.
5. Add coordinator accept_guarded/metadata combination, repeated backend validity, and selective acceptance interruption.
6. Wire native guarded acceptance/onset, lifecycle control readiness, and per-entry waiting; keep existing ready/observation ownership.
7. Run focused tests below; inspect the three-file diff for accidental routing, schema, configuration, or business-lifecycle changes.
8. Report actual tests and unresolved limitations; Root obtains independent review before closure or pinned-loader baseline changes.

## Required focused proof
A. Real NativeCall + actual coordinator/sink/arbiter + fake speech/dialog/router: held local inference, new actual microphone onset,
then old result released while VAD active: no old transcript, synthesize call, or bytes. Repeat after newer endpoint/ASR/acceptance.
B. Two queued utterance origins, older accepted only after newer onset: old local output remains suppressed; older business acceptance proceeds.
C. Silent queued output/onset before synthesis; scheduling gap immediately before _speak; onset between async transcript and first chunk.
D. Current local reply after clean input settles speaks; acceptance's own generation increment does not suppress its current reply.
E. Actual backend on_reply arrival while input active is journaled, emits no speech/transcript, survives a following acceptance interruption,
and speaks once after VAD, ASR, audio/text queues, and acceptance settle with unchanged own task version.
F. Change that backend task version while deferred: no speech; original journal preserved. Change only an unrelated task: own result remains valid.
G. Already-started backend interrupted by onset never replays; submitted fake dialog continues exactly once, with no retry/cancel call.
H. Short discarded onset, empty ASR, ASR exception, rejected acceptance, queue-full drop, receiver replacement, input loss, hangup:
no stuck pause/completion waiter and no false idle; old origin stays invalid even if the new utterance yields no text.
I. Startup/language controls with recognized backlog plus delayed open: no deadlock; no lifecycle speech during physical input;
readiness and language snapshot invariants pass; ordinary backend speech cannot use the lifecycle exception.
J. Bounds/priority/overflow, explicit stop, guarded fake/plain emitters, detach/cleanup/unknown outcome, and Task 14 help/status guards pass.
Use asyncio Events/barriers and timeout only as deadlock protection; assert production NativeCall methods, not extracted AST bodies.
Reuse synthetic frame/track patterns from existing native endpoint tests; mock speech classification for deterministic race ordering.
Existing Silero/noise integration may be run only under Root's permitted verification scope; this design requests no model loading/download.
Run output/coordinator/native suites plus input lifecycle, endpoint finish, mic gap, and language-selection regressions with service-free fixtures.
No new closed corpus access; Root separately controls Task 14 closure and future pinned-loader evaluation.

## Root disposition needed
Ratify the narrowly scoped lifecycle readiness exception and per-entry completion API described above.
No other product-choice blocker identified; implementation must stop for an unexpected additional production-file dependency.


## Root ratification — 24 October 2026

Root adopts this output-only fix under the user's delegated design/implementation authority. This is a technical Root decision, not a separate user approval or live proof. The lifecycle lane may speak only after physical VAD/ASR/audio input settles while recognized backlog/acceptance remains; only explicit native lifecycle publication can use it. Per-entry completion replaces global waiting for those notices to avoid startup/language deadlock. Backend durability is explicit coordinator provenance, never inferred from kind alone. Old local output is suppressed; unstarted current backend output is deferred; already-started interrupted delivery is never automatically replayed. Business acceptance, authority, observer ownership and journal remain unaffected.

The exact implementation baseline is the final independently reviewed Task14 commit supplied in the brief. The inspected382df2d baseline is design provenance only. Three product Python files plus focused tests and these Task15 docs are authorized. No additional source dependency without a concrete Root ruling. Existing service-free native/Silero regression fixtures are allowed; no serving models, real ServiceNow actions, downloads, private config, startup/activation or closed heldout data. Keep all existing queue bounds, noise policy and Main settings. Independent task review and final stopped-source freeze follow implementation; no qualification or deployment follows from this document.


## Root follow-up ruling � terminal failure feedback

During implementation review, Root ratified preservation of the explicit CONNECTION_FAILED lifecycle explanation while the transport remains live. The failed flag continues to suppress ordinary speech, obsolete controls and business intake. Only the private native CONNECTION_FAILED publication can use a terminal-control guard requiring failed state, unchanged issuance epoch, and no input loss/closing/closed state. It still waits for physical VAD/ASR/queued audio to settle; no call-wide liveness override is allowed.

Natural failed-intake cleanup waits for that explicit failure-control disposition. An unrelated intake failure cancels ordinary startup as before. Loss/close/cancellation still interrupts the control and cannot refill playback. Failed responsive receivers may continue measuring physical endpoints for this notice, while queueing of further business input remains rejected. Tests must use actual NativeCall startup failure, require one permitted explanation with zero dispatch, and prove input loss prevents refill. A previous full755 run predating this follow-up is only intermediate evidence; rerun full discovery on the final revised bytes.
