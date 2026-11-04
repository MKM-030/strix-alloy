# Native Authoritative Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve fast conversation while requiring a heard native Boolean before dispatch, delivering actual backend information, and finishing already audible sentences across harmless updates.

**Architecture:** Add authenticated per-event provenance and request-owned lifecycle state at the existing Bridge boundary. A pure Native barrier owns confirmation freshness and held originals; separate queue admission from active-sentence ownership. Keep legacy callback consumers compatible.

**Tech Stack:** Existing Python3.12, asyncio, aiohttp, unittest, Pipecat1.13; existing Native venv only.

**Spec:** `docs/superpowers/specs/2026-11-04-native-authoritative-handoff-design.md`

## Global Constraints

- Source-only until Root reviews the design and implementation; no canonical integration or live actions.
- ServiceNow is the sole business executor. No fabricated yes/no, data, order replay, model retry or automatic release of held input.
- Typed controlType is authoritative; no keyword classification of approval or success.
- Existing `on_reply(str)` and `Dialog.turn` list-of-string return remain compatible.
- First PCM needs full release checks; active PCM retains hard call/source/generation guards.
- Use `C:/Projects/strix-alloy-clean/voice/native-bridge/.venv/Scripts/python.exe -B` and the execution worktree cwd. No installs or repeated unrelated full-suite campaigns.
- Claim commit8790 remains separate until Root chooses integration order.

## Review Focus

- A VAD onset predating full control emission must remain held even if ASR finishes afterward.
- A new Boolean arriving between Native's check and POST must cause zero Bridge dispatch.
- Full summaries and identical text in distinct control types must retain their typed provenance.
- Reordered final OutputText without completed=True must speak despite four pending turns; ended only closes input.
- A changed presentation scope must finish active PCM, while a replaced source/socket/generation must stop it.

---

### Task1: Carry authenticated event and lifecycle ownership

**Files:** Modify `voice/bridge.py`, `voice/native-bridge/native_bridge.py`; create `voice/native-bridge/native_backend.py`; create `voice/native-bridge/test_native_backend_events.py`; extend `voice/native-bridge/test_terminal_callback_drain.py` and `test_callback_state_cursor.py`.

**Interfaces:** Polling adds bounded `backendEvents` under the existing shared high-water cursor; legacy `events` and its text deduplication remain unchanged. `Bridge.send(...) -> str` returns the exact minted request ID; callers not using its result remain compatible. `BackendEvent` is immutable `(event_id, business_request_id, ui_type, text)` after strict validation of source and streamComplete. `BackendState` is immutable `(request_id, action, busy, ended, failed)`. `Dialog.turn(text, on_reply=None, voice_context=None, *, on_event=None, native_control_binding=_UNSET)` returns the existing list. Typed callback receives only validated `BackendEvent` for the exact ACK request and Dialog owner. Native uses that callback rather than releasing legacy strings as well.

- [ ] Write failing loopback tests for exact metadata from real Bridge callbacks: OutputText vs Boolean, identical text in different types retaining two typed receipts but one legacy display event, context alias normalized to original request, duplicate callbacks once, typed-only cursor advancement, and old request/session rejected.
- [ ] Add lifecycle tests: OutputText with completed absent is delivered immediately while busy remains true; terminal-before-final and final-before-terminal both drain once; ended is request-owned closure with no success field; secure/partial text never reaches the typed lane.
- [ ] Run the new modules and existing terminal/cursor tests; confirm the new assertions fail for missing provenance rather than fixture errors.
- [ ] Implement provenance at authenticated consume time, MESSAGE ACK request ID, request-owned polling state, strict Native immutable parsing and optional callback. Keep legacy event fields/callback behavior and existing bounded queue size; reset typed per-request deduplication without discarding retained receipts.
- [ ] Run new tests plus existing Bridge, context-alias, conversation-binding and terminal-drain suites. Commit this independently reviewable transport change.

### Task2: Add a universal input barrier at typed Boolean controls

**Files:** Extend `native_backend.py`, `native_bridge.py`, `native_duplex.py`, `voice/bridge.py`; create `test_native_boolean_barrier.py`; update focused raw-delivery fixtures.

**Interfaces:** `ControlBinding(business_request_id, control_type, label)` is immutable. `ControlGate.observe(binding)`, `mark_emitted(binding)`, `admit(turn, onset_binding)` and `retire()` return explicit hold/dispatch decisions without interpreting text. Held records preserve the original envelope and language/context snapshot. Native passes `nativeControlBinding` on every submission; Bridge returns structured409 `dispatch:not_started` before `send()` on a mismatched current Boolean.

- [ ] Write failing tests with a full summary ending in a confirmation. Queue exact caller texts `Wie geht jetzt weiter`, `Ja und was ist jetzt damit? Sind wir jetzt fertig oder`, `Ja`, a correction and a date before the question. Assert zero backend requests, original envelopes held in order, no later replay or supplemental approval publication.
- [ ] Test new onset during synthesis, onset after synthesis but before PCM drain, ASR final after drain from an earlier onset, and a local question after the native one. All remain unbound. A genuinely new onset after full exact control emission dispatches raw text once without converting it to a Boolean choice.
- [ ] Add an actual Bridge race fixture: Native supplies None or an old binding, then a Boolean callback arrives before POST. Assert structured not-dispatched409 and no fake bot request. Missing/uncertain ACK never retries.
- [ ] Run these tests RED. Implement the pure gate, held ledger, exact-question priority and dispatch-time comparison. Native held inputs must not count as dispatchable pending work or invalidate the control's emission proof.
- [ ] Verify empty labels fail closed, newer controls retire older ones, repeated callback does not reset a heard identical binding, non-Boolean FIFO data still reaches the backend exactly once, and close clears per-call held state. Commit.

### Task3: Deliver authoritative information independently of local backlog

**Files:** Modify `native_duplex.py`; create `test_native_backend_delivery.py`; extend `test_terminal_callback_drain.py`.

**Interfaces:** `_admit_backend_event(event: BackendEvent, owner)` queues one immutable receipt in a separate per-call backend ledger/priority queue, outside local `_outputs` clearing/revocation. `_backend_event_current(receipt)` checks owned conversation and event provenance, not latest caller task/pending/epoch. `_settle_backend_state(state: BackendState)` closes input without discarding legitimate receipt speech. Delivery states are pending, active, fully host-emitted, interrupted or retired by explicit call close; interrupted receipts are retained, not automatically restarted.

- [ ] Port the existing final_callback_probe into a failing test with an exact typed OutputText fixture, four later originals pending, changed local task revision, and ended false. Assert actual unwrapped output reaches fake synthesis once while all pending originals remain intact.
- [ ] Test stale InputText/Boolean questions remain held while a genuine complete OutputText informational question is delivered as information. Bare strings or bad metadata cannot use privileged receipt admission.
- [ ] Test a new real caller turn clears optional local speech but preserves an as-yet-unstarted backend receipt once; a caller interruption during receipt audio stops it immediately and records interrupted instead of automatically restarting it.
- [ ] Test completed-before-final, final-before-completed, output-without-completed and explicit close. Ended stops business input but preserves final audio; explicit close/input loss stops audio and records incomplete delivery. No business calls are replayed.
- [ ] Confirm RED, implement receipt priority and typed lifecycle settlement, then run backend delivery, raw-delivery, terminal-drain and existing cleanup tests. Commit.

### Task4: Keep one active sentence across harmless state changes

**Files:** Modify `native_duplex.py` and `pipecat_dialogue.py`; extend `test_native_duplex_output_ownership.py` and `test_pipecat_eos_identity.py`.

**Interfaces:** `PipecatDialogue.is_source_current(identity)` delegates to underlying Omni `is_stream_current` plus Pipecat owner/closed checks. Native's immutable active-sentence lease captures output, generation, source owner and identity only after first accepted PCM. `_active_speech_current(item, lease, generation)` checks hard invalidations; queue admission retains `_valid`'s full freshness checks.

- [ ] Reproduce both saved two-chunk probes with production-style bound observation and identity: backend observation advance and pending FIFO advance between chunks. Assert prefix+tail emitted, no premature complete-history claim, and any queued next stale sentence is rejected.
- [ ] Add a real offline Pipecat scope-update case: change presentation scope after first accepted chunk without changing source ownership. Assert the active tail survives. Then change source session/socket/generation, replace/close owner, interrupt caller, or close the call; each stops the tail.
- [ ] Test native information/control arrival waits for the current single local sentence boundary, then takes priority. A genuine control invalidation stops an older active control; caller interruption remains immediate.
- [ ] Confirm RED, implement leases and source-current API, and use lease validity at synthesis completion. Keep all pre-first-PCM hard/soft guards and the separate claim guard unchanged.
- [ ] Run all `test_native_duplex*.py`, new pure/backend tests and existing Pipecat EOS tests once. Add structured hold/result/stop reason evidence beyond the generic eight-discard budget. Commit.

### Task5: Source review and bounded activation handoff

**Files:** Only a private execution review under Root's existing repair artifacts; no product/config edits in this task.

- [ ] Review the combined diff for original-envelope retention, no implicit replay, strict event provenance and source identity. Confirm every review-focus case above has a real assertion.
- [ ] Record commit IDs, exact allowed files, hashes and commands/results. Do not claim the entire unrelated Native suite passed.
- [ ] Require Root's coordinated Bridge+Native installation/reload review; model and capability configuration remain unchanged. Do not treat the old Native-only claim-guard reload plan as sufficient.
- [ ] Root may run one synthetic no-approval conversation after installation. At the first native Boolean, verify it is voiced and stop without sending approval. Physical iPhone/Android playback requires later device evidence; host PCM proves only server emission.
