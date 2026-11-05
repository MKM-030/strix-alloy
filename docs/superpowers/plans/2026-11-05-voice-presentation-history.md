# Voice presentation history implementation plan

> For agentic workers: execute task by task using test-driven development. Root has approved the conversation-scoped design and this isolated source implementation. Root alone owns native/SDK/runtime actions.

Goal: publish only completely host-emitted local assistant speech as bounded, untrusted conversation presentation history so the own SCC model can avoid redundant prefaces without removing any real backend output.

Architecture: a default-disabled asynchronous local lane publishes immutable finite event slots to a separate own native helper using the observed provider-user-context primitives. The existing own SCC context helper optionally appends typed history outside business memory; original caller notes, vendor MESSAGE, controls, results and audio remain intact. There is no current-native-task join claim.

Tech stack: existing Python/aiohttp/asyncio, ES5 Script Includes/resources, unittest and Node built-in test/vm. No dependencies or native calls are added for testing.

## Global constraints and DTO

* Defaults: Native `presentation_history_enabled=False`; Bridge same flag `False`; own native history class `enabled:false`. No current config, model, deployment, voice/greeting, vendor/global prompt or ACL edits.
* Exact event fields: `version=1`, `kind=local_conversation_history`, `local_output_state=host_emitted`, `owner_id` (32 hex native owner), `event_id` (32 hex), `sequence` (1..16), `caller_turn_id` (32 hex or null), `original_asr_sha256` (64 hex or null, paired with caller ID), `output_epoch` and `task_revision` (1..2147483647), `playback_generation` (0..2147483647; initial real generation is zero), `text` (nonblank well-formed Unicode, <=2000 UTF-16 code units AND <=8000 UTF8 bytes), `text_sha256`, `accepted_samples`, `emitted_samples` (positive equal <=43,200,000). A maximum of1000astral characters fits the UTF-16 cap;1001doesnot. This strict per-item limit keeps default ensure_ascii JSON including full metadata within the existing16384-byte local body limit. The consumer's separate4000-character aggregate remains measured in Unicode code points. `native_request_binding=unavailable` is fixed; no invented business request ID.
* Sixteen slots per conversation, no reuse/replay. At most three recent items/4000 text characters in the consumer, maximum120000ms native retention. No latest-pointer overwrite/CAS assertion. Conflicts/uncertain delivery disable only the optional lane.
* Producer captures the source lease, never a later current request/epoch. Partial/interrupted/control/backend/greeting/confirmation-ack speech is excluded. Original input, actual outputs and PCM code paths stay complete.

## Files and interfaces

* New `voice/presentation_history.py`: strict `validate_event(value)` and finite `PresentationOutbox(owner_id)` with `offer(...)`, `run(publisher)`, `close()`; bound queue and no retries, no logging. Producer DTO built once from completed PCM and original local turn. One coroutine, cancellation on close.
* Modify `voice/native-bridge/native_duplex.py`: optional `presentation_publisher=None`; integrate only after full emitted local `conversation` history boundary, start/close separate worker. No backend event logic changes.
* Modify `voice/native-bridge/native_bridge.py`: boolean flag; optional `Dialog.publish_presentation_history(event)` -> POST own local `/api/presentation-history`; verify exact stored receipt. Pass publisher only when flag true.
* Modify `voice/bridge.py`: boolean Settings flag; session local finite sequence/owner/disabled state plus dedicated lock; own authenticated route validates fixed own assistant/profile/session and DTO. POST existing owned context URL with `operation=presentation_history_store`, generated requestId, original CREATE binding, derived caller user and event. A timeout/bad acknowledgement disables only history. No MESSAGE/context alias state changes.
* New `servicenow/byollm/voice-presentation-history/SCCVoicePresentationHistoryV1.js`: default disabled own class, strict JSON API `storeJSON(payload)` and `includeJSON({conversationId,prompt})`; all new record reads secure and field canRead checked. Derive fixed own provider/user/profile/usecase chain. Store/read only namespaced provider-user-context event slots; no record writes/short-term-memory messages. Metadata store is not a business operation. Read-only consumer returns original prompt on failure.
* New `Context-resource.v1.candidate.js`: exact actual own resource baseline SHA3a36f08b6a65a3899c33352ce92f7393b8afa52fb8f25fb6d2353284d5a9252b plus narrowly dispatched new operation before unchanged old schema. No automatic install.
* New `SCCVoiceCallerContext.v1.candidate.js`: exact actual helper baseline SHAfc157a43f5246cdc99be80daf3ae969a9e213f8d18945f1b17995b2e950e123e plus isolated optional history wrapper at existing includeJSON result. Existing raw caller-note behavior stays exact, including failures/receipts.
* New `Halogen-Request-Transformer.v1.candidate.js`: Root-authorized minimal derivative of exact raw99cb baseline; accept separately validated historyIncluded/historyEventIds as an alternative prompt-adoption signal. Never reinterpret raw caller promptIncluded/ingested receipts. Without this explicit signal path, history-only results with no raw caller note would be discarded by the old adapter.
* New `SCC-agent-style-instructions.v1.appendix.txt`: proposed own-agent-only placement. Current agent source is not freshly captured, so do not alter its live instructions or invent a full replacement. Typed data block carries explicit non-authority provenance independently.
* New Python tests `voice/native-bridge/test_presentation_history.py`; Node tests `servicenow/byollm/voice-presentation-history/presentation-history.test.cjs`. Add focused existing audio/backend invariant tests as needed.

## Task 1: local DTO/outbox and emission integration

- [ ] Write failing tests: disabled constructor emits nothing; offered event publishes once only after full local PCM; interrupted/backend/control excluded; text/identity/sample/queue caps; exception makes lane stop with no retry; close cancels blocked publisher. Assert original backend/input fields unchanged.
- [ ] Run `python -m unittest discover -s voice/native-bridge -p test_presentation_history.py` with existing Native test environment; verify assertions fail for missing behavior.
- [ ] Implement strict DTO/outbox and the small optional hook; run new tests to green. No output suppression or generation changes.

## Task 2: private local/native transport

- [ ] Write failing fake-HTTP tests for default disabled route, correct stored receipt, wrong cookie/CSRF/assistant/profile, wrong owner/sequence, malformed/uncertain acknowledgement and no backend state mutation. Test Dialog default and bad receipt omission behavior.
- [ ] Implement separate local flag/route/forwarder; timeout bounded2s, single attempt, complete receipt identity/hash. Original MESSAGE shape is asserted unchanged.
- [ ] Run scoped transport, context-update and backend protocol suites once after changes settle.

## Task 3: native own candidates and read-only consumer

- [ ] Write failing Node VM tests for all-disabled no calls, valid stored event, foreign/denied ownership, conflict, unavailable getter/setter, failure omission, expired/mixed owner data, escaped hostile text, bounded recent view and exact unrelated/old caller-path preservation. Mocks reject every record update/insert/delete and every memory write in the new path.
- [ ] Implement own class plus minimal actual-source derivatives. Keep baseline files frozen; tests reconstruct and verify exact source deltas/hashes. Add the proposed own-agent style appendix only.
- [ ] Run Node tests and syntax/ES5 check using available local tools. Record real CPU results; no native test/installer is included.

## Completion and handoff

- [ ] Run scoped existing full-emission/Boolean/final/control/original-input regression tests and new tests. Inspect git diff for config/runtime/vendor changes and unchanged frozen Registrar/source baseline pins.
- [ ] Produce source-only handoff with changed file hashes, actual-source lineage, default flags and explicit unproved native storage/worker/lifetime/concurrency limits.
- [ ] Request Root's independent source review. No merge, deployment, service/model lifecycle, native/API call, physical-device or semantic-success claim is part of this assignment.

## Actual local progress

Local DTO/outbox/emission and private Dialog/Bridge transport implemented after visible failing tests. Root's early review found the outbox accepted arbitrary non-False results: new None/0/1/string/object RED cases reproduced it, then the implementation was tightened to exact `True` only. A failure-shaped wrapper around a success-shaped receipt is likewise rejected after RED/GREEN. The own provider user must equal the original CREATE's `voice-` plus session ID, with no latest/current-request substitution.

The final Python scoped run passed 61 tests (17 new plus 44 existing; model-free loopback fakes only), and broader existing NativeDuplex discovery passed 138 tests after the last Python change. Additional RED/GREEN cases enforce original CREATE provider/session identity and quiet optional-worker shutdown without new production warnings. Frozen actual source files and all existing Registrar artifacts remain unchanged. The disjoint acceptance agent completed native candidates with 52 Node tests and all four native JavaScript files parsed as ES5. Store producer identity is validated separately from the consumer's effective GS user; denied normal REST reads remain unavailable. Sixteen-slot contiguous storage/all-slot conflict validation remains conservative. All source is ready for one independent whole-feature review; no activation or native qualification is claimed.
