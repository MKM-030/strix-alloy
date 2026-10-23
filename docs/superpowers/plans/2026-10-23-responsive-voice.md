# Responsive ServiceNow Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Keep spoken conversation responsive during ServiceNow work, with durable correctly routed tasks and verified authority for business actions.

**Architecture:** An independent conversation router and output arbiter attach native calls to a process-owned durable task coordinator. LegacyVA remains serialized; a capability-gated owned ServiceNow contract supplies authoritative revisions and operation claims for full mode. Gemma remains the business engine; a qualified separate small model serves conversation.

**Tech Stack:** Python3.12+, asyncio/aiohttp/SQLite/unittest, existing aiortc/Silero/Whisper/QwenTTS, loopback llama.cpp, ServiceNow ES5 owned scripts/REST/update set.

**Spec:** docs/superpowers/specs/2026-10-23-responsive-voice-implementation-design.md

## Global Constraints

- ServiceNow remains the only business executor; no test orders, fabricated history/results or external user notifications.
- Preserve one in-flight LegacyVA request, existing busy/auth/callback/owned-cleanup protections; no KAA bypass or unverified native contract.
- No bearer/cookie/API key in task store, general logs or reports. Private configured store, no public ledger API. Do not print existing process command lines.
- Native legacy scope is one call: no inferred principal or cross-call task disclosure. Process-owned submitted work outlives detach; restart makes uncertain dispatched work outcome_unknown and blocks conflicting dispatch.
- Full-mode live writes require verified principal, agent/tool binding, authoritative revision fence, durable operation claim and reconciliation. Fake tests are not live proof.
- Maximum8tasks/32pending utterances per scope; user text<=4000characters; persistence precedes acceptance. Unknown submitted writes never auto-retry.
- Gemma concurrency1/context32768 and memory reserve>=18GiB remain; conversation inference is independent of Gemma gateway.
- Preserve Silero/noise fix, managed TURN policy11792b33…, startup ownership and pre-existing dirty work. Stage new files or baseline-relative hunks only; no whole-tree add/reset/clean.
- Existing native baseline465tests has1failure+26errors: compare names and show new failures separately.
- All tests synthetic/fake business executors until designated live safe-read checks. Audio and real ServiceNow claims require their actual evidence.

## Review Focus

- New call while an old detached request is unresolved must not acquire its identity, events or business slot (Tasks1,3,4).
- Same utterance/event ID with different content must conflict rather than silently deduplicate (Task1).
- A local status interruption must not permanently suppress future business audio or replay stale questions (Tasks3,4).
- Model mistakes, injection, cancellation-versus-audio-stop confusion and overloaded queues must never dispatch a guessed business action (Tasks2,3).
- Amendment and commit race must have one authoritative winner, with no replay after an uncertain write (Task5).

## File map

New flat native modules: business_tasks.py (types/validation), task_store.py (persistence), conversation_router.py (closed intent contract/model client), task_coordinator.py (workers/attachments), conversation_output.py (speaker arbitration), responsive_config.py (profile validation/model capabilities), servicenow_executor.py (legacy+qualified adapter contract). Native integration remains a focused seam in native_bridge.py. Tests use test_responsive_*.py to isolate the new acceptance suite. ServiceNow owned package in voice/servicenow/responsive-tasks/ and its Node contract tests. Startup extension in voice/native-start/conversation_runtime.py and starter seam; docs in docs/local-voice/RESPONSIVE-VOICE.md. No edits to REV-N services.

### Task 1: Durable task and operation journal

Create business_tasks.py,task_store.py,test_responsive_store.py under voice/native-bridge/.

**Interfaces (consumed by Tasks2–5):** immutable dataclasses `Scope(scope_id,call_id,call_generation,instance_id,assistant_id,principal_id='')`, `Agent(alias,agent_id,revision,capabilities)`; validated capabilities mapping explicit booleans. `TaskStore(path: str|Path)` owns SQLite connection(s), `close()`; all store calls synchronous and bounded, no awaits inside transactions. Snapshots are detached dictionaries with spec field names and canonical JSON values.

`create_task(scope:Scope,agent:Agent,objective:str,*,task_id:str|None=None)->dict`; `get_task(task_id,scope_id)->dict`; `list_tasks(scope_id)->list[dict]`; `accept(task_id,scope_id,utterance_id,text,*,kind='continue_task',voice_context=None)->dict` returns immutable operation; `pending(scope_id)->list[dict]` in accept order; `dispatch(operation_id)->dict` atomically persists submitted reservation before returning; `observe(operation_id,event_id,event_type,payload)->bool` exactly-once identical inbox; `settle(operation_id,*,replies:list[str],outcome='awaiting_input',evidence=None)->dict`; `mark_unknown(operation_id,reason_code)->None`; `detach_scope(scope_id)->None`; `recover()->dict` marks previously dispatched/unsettled unknown and returns counts; `has_unresolved()->bool`; `events(task_id,scope_id,after=0)->list[dict]`. `StoreConflict`, `StoreCapacity`, `StoreDenied`, `StoreInvalid` fixed exception classes, no sensitive messages.

Task creation/accept limits enforced transactionally across two store connections. New accepted business utterance increments context_version; operation records captured version and exact original text. Duplicate utterance same binding/content returns prior operation without version bump, different content/binding conflicts. Local status does not accept a business operation or bump version. `dispatch` has exactly one successful claimant and raises StoreConflict on every repeated/uncertain/terminal submission attempt. `settle` persists evidence/replies and marks awaiting_input (legacy result) without calling it business success. Repeated identical settlement is no-op; conflicting terminal result is rejected. `observe` requires existing operation and schema/bounds. Events sequence persists across reopen. Voice context is an explicit bounded language/assistant/profile allowlist, not arbitrary credentials. Store keeps no credential fields. `detach_scope` persists attachment state; dispatch rejects all unsubmitted work for detached scopes. `recover` is explicitly invoked once by the process coordinator at startup, never automatically when opening a second store connection.

- [ ] Add failing tests: accepted text survives reopen; sameIDchangedText conflicts; crossScopeDenied; duplicateCallbackOnce; sequenceMonotonic; twoConnectionPendingLimit; twoConnectionDispatchOnce; recoverUnknownNeverPending; detachedReservationBlocks; transactionRollback; invalidStateNoEvent; taskAndTextBounds. Assert exact context_version increments and zero duplicate operations.
- [ ] Run native Python `-m unittest test_responsive_store -v` from voice/native-bridge, expect missing module/behavior failure before implementation.
- [ ] Implement minimal validated models and WAL SQLite schema with unique identities/FKs, busy_timeout and atomic event+state writes; run test above green and existing pure core tests.
- [ ] Self-review, stage only these new files and commit `feat: persist responsive voice tasks and operation ownership`.

### Task 2: Independent conversation routing and model contract

Create conversation_router.py,responsive_config.py,test_responsive_router.py,test_responsive_config.py.

**Interfaces:** `Route(intent:str,task_id:str='',agent_alias:str='',reply:str='')` immutable; `RoutingContext(scope_id:str,tasks:list[dict],focus_task_id:str='',last_question:str='',agents:list[Agent]=[])`. `ConversationRouter(model=None)`; `async route(text:str,context:RoutingContext)->Route`. `LoopbackConversationModel(http,url,model,token_file,timeout_seconds=2.0)`; `async classify(text,context)->dict` using closed JSON response. `ResponsiveConfig` frozen with enabled=False,mode='legacy',store_file='',model configuration and registered `Agent`s, capability evidence manifest paths; `load_responsive_config(path)->ResponsiveConfig`. No environment-based implicit endpoint switch.

Model route schema has only intent/task_id/agent_alias/reply. Intent enum exactly spec8values. Every nonempty task/alias must exist in context, scope must match; status/amend/cancel/continue require unambiguous task; new_task requires registryalias or uncertain. Model output cannot mark success, add facts, URLs, tool IDs or change authority. `reply` usable only for clarification/uncertain,<=240chars and no fabricated action claim; critical/status feedback generated by coordinator templates. Caller model-input embedded as data in explicit system instruction. Reject unknown fields/duplicateJSONkeys/multipleobjects/markdown/nonfinite/oversize, context over budget and late responses. HTTP is pinned loopback, trust_env=False/no redirects, bounded request/response and token read privately. Never use8840/8841/8823 for conversation.

Deterministic precise audio-stop/status/repeat intents may bypass model. Do not classify all date-like strings as amendments without context; preserve Ja/Nein/name as continuation only with exactly one awaiting-input task. Without model, honest uncertain/clarification for open-ended intent, never pretend general comprehension. Cancel business command always distinct from audio stop; unsupported cancel becomes cancel_requested with truthful response in Task3. Config private paths resolve relative profile; inline secrets/unknown settings rejected; mode full fails unless evidence-backed authority capabilities; imported Omni/vision assets declare unqualified and cannot be enabled by a naked Boolean.

- [ ] Failing tests: German audioStopVsCancel; statusBypassesHeldModel; twoTaskDateAmbiguous; quotedInjectionNoAgentEscape; nameAndJaStayExact; unknownID/alias/schemaRejected; malformed/duplicate/hugeJSON; modelTimeout<2.2s; endpointNoRedirect; configInlineSecret/fullModeWithoutEvidenceRejected; missingProfileKeepsLegacy; unsupportedVisionHonest.
- [ ] Implement and run `-m unittest test_responsive_router test_responsive_config -v` green with fake local model HTTP, no business calls.
- [ ] Commit only new task files `feat: route voice follow-ups through an independent bounded dialogue model`.

### Task 3: Process-owned coordinator and output arbitration

Create task_coordinator.py,servicenow_executor.py,conversation_output.py,test_responsive_coordinator.py,test_responsive_output.py.

**Interfaces:** `ExecutorCapabilities(independent_context=False,checkpoints=False,status_lookup=False,durable_execution=False,authoritative_idempotency=False,version_fence=False,cancel_before_commit=False,compensate_after_commit=False)`. `LegacyVAExecutor(dialog)` exposes `capabilities`, `async turn(operation,on_reply)->list[str]` (calls existing dialog.turn exact text/context once), `async close()` preserves owned cleanup. Existing Dialog duck types remain usable in tests.

`TaskCoordinator(store,router,agents,executor_factory)` process owner; `async attach(scope:Scope,emit:async callable,*,executor=None)->ConversationAttachment`; `ConversationAttachment.async accept(utterance_id,text,*,voice_context=None)->Route`; `async detach()`; `TaskCoordinator.async shutdown(timeout_seconds=5)->dict`; `snapshot(scope_id)`. Tasks/operation methods from Task1. Emit payload closed mapping `{kind,task_id,operation_id,utterance_id,context_version,text,priority}`; `kind` local_reply/backend_reply/task_state/error; no transcripts outside attached scope. `OutputArbiter(speech,playback,emit_transcript,is_live)`; `async publish(event)`, `interrupt()`, `async close()`; bounded8output segments, max4000text. Real playback generation checked each chunk.

Worker owns submitted request, does not await speech generation (callback persists/queues); one legacy worker/context, no native call task cancellation propagation. Detach stops input/output; unsubmitted native messages remain durably suspended and cannot dispatch after hangup. Submitted request observation continues. Scope reservation remains until settled/owned-close acknowledged. On restart store unknown prevents another LegacyVA dispatch; explicit reconciliation surface is operator-private, no auto replay. New intent with unsupported independent context is stored queued and clearly announced; never sent into another awaiting-input workflow without supported switch or explicit closure. Continue/amend routes use exact caller text; amendments during busy are queued with honest pending delivery and no guarantee current action changed. If no authoritative fence, explain that limitation before acceptance and never fabricate cancellation; latest context invalidates stale question output. Cancellation before local unsubmitted dispatch is cancellable; after dispatch cancel_requested only. No write retry on output/model timeout. Expired/revoked full authority blocks new dispatch while permitted observation continues.

Output gives caller/local control priority and serializes all TTS; any new utterance invalidates current speaking generation, future backend result uses current generation if relevant. Superseded open question is persisted but not replayed before pending amendment delivered. Suppressed business text available for repeat/status; backend result after status interruption still audible. Generated/sent tracked, no heard assertion without ACK. Audio failure reported once, worker still settles.

- [ ] Failing tests: held120sFakeLocalStatusRespondsWithin100ms;32TurnsAcceptedNoDrop; newTaskNeverBusyContext; cancellationVsAudio; amendmentBeforeReplyNoStaleQuestion; detachObservesSubmittedNoSpeech; secondScopeNoDisclosureOrSlot; restartUnknownBlocksDispatch; callbackBeforeAckDuplicate/outOfOrder; TTSFailureNoBusinessRetry; statusInterruptFutureBackendAudible; staleChunksDropped; outputQueueBounded.
- [ ] Implement minimal scheduler/adapter/arbiter. `-m unittest test_responsive_store test_responsive_router test_responsive_config test_responsive_coordinator test_responsive_output -v` green.
- [ ] Commit new files `feat: supervise business tasks independently of native voice turns`.

### Task 4: Native call integration with compatibility preserved

Modify native_bridge.py only at config loading, app lifecycle, call attachment/recognized turns/output/close seams. Add test_responsive_native.py. Existing constructor positional contracts remain. New private responsive profile optional; default disabled preserves all legacy behavior. One coordinator in create_app lifecycle; enabled make_call receives attachment factory. Factories/tests remain injectable; no direct process global for fake calls.

After actual dialog.open/greeting, enabled process_turns runs responsive intake without awaiting business result. Language-selection controls stay local and serialized. Input/end and queue accounting remain correct. Store before acceptance/transcript acknowledgement. Recognized queue capacity32only enabled; ASR full response explicit. Attach scope binds config assistant and unique call/generation; no guessed principal. Ready callback/results through arbiter plus original SDK transcript event shape. Worker keeps Dialog ownership after media detach; NativeCall.finish_close must not close/cancel it prematurely. App shutdown bounded observation/unknown persistence. Old call capacity shared with SDK/browser; unresolved business reservation prevents conflicting new admission, with fixed actionable availability notice, no private data. Health adds only mode/model/capability/aggregate counts, never contents or paths/keys.

- [ ] Snapshot baseline tracked native_bridge.py/config source before edit; no unrelated refactor or import-semantic changes.
- [ ] Failing integration tests with actual NativeCall/fakeSpeech/Dialog+held turn: status spoken before backend release; second followup retained; real transcript ordering; languageSelectionNoBusinessTurn; hangupNoWorkerCancel; lateReplyNoOtherCall; greeting/repeatCall compatibility; failedStoreNoAcceptedAck; appCleanupUnknownPreserved.
- [ ] Run new suite plus targeted existing audio/input-loss/SDK/owned-cleanup/TURN/Silero/context suites; compare full native suite names to baseline1failure26errors. Fix any introduced differences.
- [ ] Stage only task-relative native_bridge.py hunks and new test; commit `feat: keep native ServiceNow calls conversational during agent work`.

### Task 5: Owned ServiceNow authority package and adapter

Use research exact metadata/source evidence at taskworkspace duplex-implementation-20261023/servicenow-contract.md (especially final addendum) and keep security/native contracts. Create voice/servicenow/responsive-tasks/ schema manifest, ES5 authority ScriptInclude, v2 authenticated registry/control resources, prepare-only order tool, guarded dispatcher, importable metadata/update-set package, README and Node contract harness. Extend servicenow_executor.py for explicit owned protocol, add test_responsive_executor.py. No business logic duplication: existing SCC order implementation remains authoritative beneath verified guard. An unguarded order binding must be unavailable to responsive full mode.

Exact immutable transition/operation identities, principal/service/agent/proposal/confirmation/payloadhash binding. UNIQUE predecessor_slot arbitrates expected revision for amend/cancel/commit. API `/tasks` create; `/tasks/{id}` bounded authorized status; `/tasks/{id}/commands` with command_id,expected_revision,kind and bounded proposal; `/operations/{id}` reconcile. Resource paths are proposed owned routes, never assumed deployed. Server returns evidence-backed capability revision. Local client sends exact configured origin/auth with no redirects, persists dispatch before IO, never sends a key/payload changed under same operation. Authority protocol stores owner/task refs; no arbitrary table/read/script execution. Callback/poll correlation includes task,operation,context_version,eventID and monotone sequence.

If trusted VA-context-to-toolbinding not wire-proven, use prepare-only VA tool and authenticated explicit proposal commit; do not insert guessed inputs into old tool. Confirmation bound to exact proposal version; new correction invalidates. Claim durability before dispatch and operation->RITM receipt requires transaction/lost-response qualification. Failed proof keeps full mode blocked, with explicit remaining steps. Authorized instance edits may deploy owned records using existing safe mechanism after backups/source comparison; no protected-source edits or role weakening, no orders. Live read/capability/schema verification only at this stage. Independent agents beyond current registry remain disabled until proven.

- [ ] RED Node race tests duplicateCommitOnce,sameKeyChangedPayloadConflict,amendWinsInvalidatesConfirmation,commitWinsCorrectionDeferred,wrongOwner/agent/toolDenied,expiredAuthDenied,uncertainNoReclaim; adapter tests lostACKNoRetry,staleCallbackStoredNotReattributed,capabilityEvidenceRequired.
- [ ] Implement owned package, GREEN harness and Python executor tests; record deploy/qualification status truthfully.
- [ ] Commit only task files/hunks `feat: add authoritative ServiceNow task revisions and guarded operation contract`.

### Task 6: Qualified models, startup and capability manifests

Create voice/native-start/conversation_runtime.py,test_conversation_runtime.py, private-profile example and docs/local-voice/RESPONSIVE-VOICE.md; extend start_current_voice.py seam baseline-relative. Use exact qualification manifest produced by independent model spike. Model candidate may be changed only by recorded measured ruling. Runtime hash/modelSHA,argv/help-verified options,loopback/auth/ctx<=4096/parallel1,memory>=18GiB,owner record and health+identity. Reuse matching own process; occupied unrelated port/model rejects; no stop existing owners. All-services Desktop command idempotently starts only selected qualified addition. No full argv/key in logs. check-only no starts. Prewarm safe synthetic context, no ServiceNow business turn.

Add optional Omni WebSocket adapter/capability manifest using REV-N protocol read-only reference (session.start,PCM16,input.commit,response.cancel,playback.state); test binding/generation/cancel/contextupdate with fake server. Do not turn prototype native-turn policy into unsupported claim. Vision model catalog lists local asset readiness and required attachment path; no dummy activated vision. Audio endpointing changes only if controlled same-corpus evidence beats baseline.

- [ ] RED startup tests foreignOwnerRefused,repeatedStartReuse,missingHash/memory/modelFailClosed,checkOnlyNoMutation; Omni protocol fake latechunks/cancel/textupdate tests. Qualified model corpus>=120routes+40formulations with report, plus concurrent Gemma bounded-load latency if reserve respected.
- [ ] GREEN new startup/protocol tests and current Desktop wrapper preflight; update operational profiles only after candidate passes, preserve private backups. Capture config changes/hashes without secrets.
- [ ] Commit task files/hunks `feat: start qualified independent conversation runtime with voice services`.

### Task 7: Whole-system qualification and activation

Create focused test_responsive_acceptance.py and reproducible safe replay/benchmark utility plus final operator guide. Cover spec acceptance via real local HTTP model+fake business work, restart/multiplecalls/unknowns/audio. Real safe ServiceNow greeting/status/capability read only; no order. Current native idle and Gemma active_requests0 before focused reload. Match owner PID/config, backup private deployment profiles, activate only proven mode/capabilities, rollback on readiness failure. Exact Windows Desktop wrapper test, all service health and no duplicate owner. Persist activation receipt and unresolved limitations in taskworkspace and doc.

- [ ] Run comprehensive responsive tests plus relevant regression suites once; compare old failures by name and record evidence. Independent final whole-change review and fix wave.
- [ ] Warm latency p50/p95 stage metrics with synthetic German audio/model corpus; distinguish firstserverchunk from actually audible phone. Ask for physical phone validation asynchronously after runnable activation, continue remaining checks. Do not declare true native duplex/full guard/vision passed without corresponding proof.
- [ ] Document actual enabled mode/model, tested outcomes, safe rollback and remaining physical/platform gates. Commit only task-owned artifacts `test: qualify responsive voice orchestration and rollout`.
