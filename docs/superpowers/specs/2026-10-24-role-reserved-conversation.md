# Selected design: role-reserved Conversation slots

Root-selected source addendum, 24 October 2026. Product baseline `9368574ccac18f0a34557ab6753b496fd0c98016`. This replaces the earlier forced cross-role preemption design prospectively, before final source/semantic freeze. It authorizes no launch, profile mutation, live experiment or qualification claim.

Read committed admission/router/planner/coordinator/native/readiness source, TASK audit/preflight/spec/finalizer design, stable Task17 readiness handoff, and the existing consumer clone's `WindowsHost` boundary. The only network reads were immutable public upstream b10690 source requested to settle missing API/order facts. No product files, tests, runtime calls or closed data were changed/run/read.

## Decision and limits

Use **one existing small Conversation model process with two explicitly reserved slots**: classifier `id_slot=0`, grounded planner `id_slot=1`. Desired total context8192/parallel2 must actually expose exactly4096 context per slot. Main32768/parallel1 and>=18GiB reserve remain unchanged. So do route3584/24, planner3072/128, byte bounds, exact count-before-completion, ordinary nonstream transport, no retry and original model2s/route max2.2s.

One shared model owner holds two independent role leases. A cancelled/uncertain planner blocks only planner slot1. Classifier slot0 remains usable when its own state is proven available. Runtime identity loss blocks both. A role's inference attempt remains unresolved until sufficient terminal/release evidence exists; idle-first never clears it. No call/job detach resets leases. Immediate audio stop and stale business/output prevention remain independent of model cleanup.

This isolates logical capacity, not GPU compute. Shared decode can delay route admission/execution. Real contended route latency, memory/Main coexistence and audio gates remain unproved and mandatory. No old single-slot evidence qualifies this selected variant.

## Reviewed pinned API basis

At b10690, OAI parsing preserves remaining request properties, including `id_slot`. [server-common.cpp1296–1305](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-common.cpp#L1296).

The inference task reads that ID. A busy requested slot is deferred; lookup wraps IDs. Therefore allow only literal integers0/1 and never submit another unresolved request to the same role. During decode yielding, completion admission is postponed. [Task ID parsing](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L3899), [slot lookup](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L1390), [scheduling](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L2147).

The normal nonstream handler waits for final results. Both ordinary and speculative stop paths send the final result before releasing the slot. Hence a complete valid response followed by a fresh idle GET is sufficient; response alone races release. [Nonstream handler](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L3922), [ordinary stop](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L3501), [speculative stop](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-context.cpp#L3614).

The reader posts tasks once, records their stop results and ends its wait after all finish. Cleanup does not cancel a completed set. [server-queue.cpp483–574](https://github.com/ggml-org/llama.cpp/blob/bdf3955159d7184f44b76091973eeff532890a35/tools/server/server-queue.cpp#L483). These are source facts, not measured performance.

## Minimal implementation/API

Keep the owner/lease implementation inside `conversation_admission.py`, already in Task17's source attestation set. Do not build a general scheduler, second HTTP framework, session/proof hierarchy or new consumer API.

Suggested private interfaces:

```python
model.slot_owner = SharedSlotOwner(host_boundary, owner_pid, owner_created,
                                  endpoint, model, token_file)
await model.slot_owner.initialize(deadline)  # one startup GET for both slots
run_admitted_chat(request, ..., slot_owner=model.slot_owner, role='route')
run_admitted_chat(job.admission, ..., slot_owner=model.slot_owner, role='planner')
```

`run_admitted_chat` acquires the requested role lease **before creating its preparation/auth/count worker**. `slot_owner=None` preserves the feature-off legacy path. Grounded-enabled production requires the owner; `GroundedAnswers` must reject its absence. Both callers pass the exact same object. All production `LoopbackConversationModel` entry points use it when enabled, including direct classify calls.

Native derives owner PID/creation only from its genuinely validated readiness proof. The existing evaluator derives them from its actual isolated OwnedServer and the same OS boundary; it does not forge a four-label readiness proof to qualify itself. The gate is ownership enforcement, not qualification authority. Create one gate per actual owned PID+creation session and reuse it across semantic fixtures/calls; fresh Stores must not reset unresolved leases. Both entry paths use the same gate/transport code and actual process observations.

Within the gate, role is immutable and maps only to0/1. Insert `id_slot` in the prepared JSON before `PreparedChat.payload` is frozen and counted. Count and inference send identical payload bytes, including that role ID. Reject contradictory/missing/out-of-range/bool IDs in an enabled admission. Explicitly enforce single completion (`n=1`/no child tasks) and ordinary nonstream/non-resumable request shape; no automatic slot assignment, borrowing, migration or retries. Role labels alone are insufficient if the actual wire body omits the ID.

A lease covers the full count→inference transaction. Use one short critical section or a documented consistent lock order for lease identity, seal/retirement and inference-attempt accounting. Mark potential server ownership before send. Never hold that lock across I/O. A zero-inference release must atomically seal future inference; a still-finishing count/auth worker cannot later infer. Retain worker/socket facts independently.

Each role may have one bounded local waiter at most; further same-role arrivals fail locally. No application queue in the server. Foreground slot0 never waits for slot1 release. A read-only slot probe for slot1 cannot reserve or poison slot0 merely because its caller await timed out; only uncertain process identity or actual shared transport/resource corruption blocks both. Probe socket ownership is separate from inference sockets.

## Exact release matrix and delayed submission race

`AdmissionRequest.dispatch('inference')` currently counts an attempt before `sendall`. The server may parse/tokenize/enqueue after a later GET has reported idle. Closing the client socket or ending its worker cannot prove future server insertion impossible.

| Per-role fact | Result |
|---|---|
| Atomically sealed with inference attempts=0 | Release local lease; do not claim observed server cancellation. |
| Inference attempted, no full terminal response or correlated active witness | Keep role unresolved, even after idle snapshots/client-worker terminal. |
| Full bounded validated nonstream response for this exact request, then fresh same-owner target-slot idle | Release role. No bare-response release. |
| Exclusively associated target-slot active task, then causally later same-owner target-slot idle | Release role; retained idle task ID is allowed. |
| Unexpected task on the role slot, malformed observation, missing proof or identity drift | Role unresolved; process/binding drift invalidates both. |

Association requires initial verified target-slot idle, exclusive endpoint writer ownership, exactly one submitted request under that lease and no earlier unresolved request for that slot. Slots0/1 may both be active: associate each only with its fixed role. Never equate OAI completion ID and numeric server task ID. Never treat activity in the other known role as an unexpected task or as evidence for this role. An unfamiliar task or a violation of exclusive-writer assumptions fails closed.

Initially require existing complete HTTP framing, matching counted usage and admitted response validation for full-terminal evidence. Truncated/body-error/partial responses, arbitrary HTTP errors, malformed model result or worker exceptions are insufficient. A late valid response may inform cleanup only while still verifiably received within the existing transport bounds; it never restores stale publication permission or extends either caller deadline.

An early cancelled request with idle-first but no terminal/active witness latches **only that role**. A second idle, elapsed time, count result, process existence, job removal, new call or repeated polls cannot clear it. Existing owner recovery can create a freshly verified process generation after explicit lifecycle cleanup; the gate never automatically kills/restarts/retries or calls recovery cancellation success.

## Real production wiring and cheap current-owner guard

`native_bridge.create_app` currently discards the validated readiness proof. Retain it. When grounded sharing is requested, construct one shared gate bound to proof PID/exact unchanged creation identity, selected endpoint/model/token file and the canonical verified source/profile. Initialize once before offering enabled routing, then pass it to the shared model already used by both `ConversationRouter` and `GroundedAnswers`.

Startup continues to use the genuine existing provider and canonical `GroundedReadinessProof`. No fake passed receipt/boolean in main. Missing finalizer or measured evidence still rejects requested startup. Tests can replace explicit lower boundaries, not production proof requirements.

**No new GroundedRuntimeBinding, session record or consumer finalizer API.** The real provider already loads canonical `conversation_runtime`. Lazily reuse that module's existing `WindowsHost()` read boundary. Source reviewed in TASK `native-start-consumer/conversation_runtime.py`: `process(pid)` returns `{pid, created, exe, argv}` at lines830–835; `listeners(port)` returns `{pid, ip}` entries at826–828. This supplies the needed observations without changing the consumer API.

At gate construction, under the validated proof identity, capture complete executable and argv, exact creation identity and bounded private token-file digest. Require exclusive listener entries for the selected port to belong to that PID and literal127.0.0.1; reject wildcard/foreign/absent listeners. Repeat process observation around capture and require equality. The trusted startup verifier binds profile/assets/source; this narrow guard does not mint readiness or reread multi-gigabyte model assets.

Before acquisition and immediately before each count/inference dispatch, compare fresh process/listener/token observations with that retained identity. Before and after every slots GET perform the same checks, including exact creation identity with no rounding, complete executable/argv equality and pinned endpoint/model/token identity. Freeze the token bytes used for this transaction, reject drift, and never log credentials/digest material as ordinary diagnostics. OS access errors, malformed facts or a failed read reject; a fallback bool is forbidden. Run bounded guard work under the caller's remaining deadline; late guard results cannot authorize dispatch.

Configuration/profile/source remain those bound at startup; do not reload them in place and carry the old proof. A configuration reload requires the existing verified startup path. The original native process and reviewed source are trusted; this is an ownership freshness guard, not a hostile-Python attestation system. If canonical WindowsHost cannot be resolved, fail closed, rather than import a second runtime universe or add a new owner registry.

## Slot observation and deadlines

Parameterize/reuse the existing socket/auth/framing parser for `GET /slots`, with its own probe record. No fake count or inference phase. Enforce bounded request/response wire/body bytes, complete HTTP framing, strict JSON duplicate keys/types and authenticated fixed loopback destination. Require exactly slot IDs0/1, each effective `n_ctx=4096`, and valid task/processing fields. Disable debug prompt/output exposure; record structural facts only. Total8192/par2 does not prove per-slot4096 under every KV setting: the actual slot geometry is mandatory.

Caps per owner/lease:

- Startup: one GET establishing both idle slots under the current owner, prior to first inference.
- Normal full-terminal completion: one fresh GET to resolve its target slot. A busy/error/late result leaves that role unresolved; no implicit normal polling loop.
- Cancellation: at most two GET attempts total for that cancelled lease. Preserve the preflight anti-interference schedule: first at cancel+80ms, response deadline cancel+100ms; optional follow-up no earlier than1100ms after previous probe result/termination. A first idle without witness never releases. A first busy may witness and a later idle may release. If the second first reveals busy, no third probe is added.

These are maximum attempted requests, including failures. Distinct callbacks or new same-role callers cannot reset the cap. At most one observer worker per role; account/close its socket and prove local observer terminal before starting its follow-up. Different roles may share a serialized read-only observation resource only if its bounded wait consumes the requesting role's own deadline and does not create a global inference lock. A snapshot may carry evidence for both already-known active leases, but must be recorded once with its actual attempt owner, correlation and timing; do not double-count or fabricate extra attempts.

Do not add continuous pre-cancel watching. First post-cancel busy can provide the active witness; early idle stays unresolved. Existing owned correlated server logs are not a callable evidence source in the inspected product, so no grep/log assertion grants release. Stock nonstream1s polling and shared result wakeups make aggressive GET polling counterproductive. Cancellation continues to close the exact inference socket; no new cancel endpoint or streaming protocol.

All acquisition/guard/count/inference/parse/release work needed to return a usable model result consumes its already-created absolute2s deadline. Outer router waits must use remaining time, not start another2s after gate acquisition. Planner local wait remains at most100ms within its original2s. Route overall max2.2s remains. Any same-role successor waiting for release uses its own original2s, not a renewed timeout. Cleanup observations after a request deadline, if retained within the fixed cancellation cap, are cleanup only; their bounded receive timeout and ownership must be explicit and they cannot dispatch a late successor. Audio invalidation never waits for any of this.

## Task18 handoff: exact geometry and evidence change

Preserve canonical record fields, class universe, source tuple order and `verify_grounded_stage(expected)` signature. Change **only the selected Conversation expected pair to `context_parallel=(8192,2)`**; Main pair remains `(32768,1)`. Source code pins enforce fixed role0/1 and per-slot4096; actual capability evidence must verify them. No new proof/session/API dependency is required from Task18.

The four evidence labels remain admission/grounding/cancellation/coexistence, but their selected-version interpretation must be reconciled prospectively before freeze. Admission includes fixed role ID in identical count/completion body and actual role-bound execution. Cancellation includes immediate stale-output revocation, no same-role queued reuse, honest unresolved/cleanup state, and routing success while planner cancellation or uncertainty exists. It no longer requires planner release before **other-role** inference. Same-role reuse still requires true release. Coexistence must verify actual simultaneous planner/route compute against Main and>=18GiB, with original route deadlines; logical slot assignment cannot stand in for performance.

No existing single-slot profile/receipt satisfies this geometry. Task18 updates the one existing consumer/finalizer/normalizer path and Root-selected qualification contract; no wrapper chain/new campaign is created here. Root separately ratifies slot-observer HTTP totals for source/qualification before measurements. The416 count-plus-completion cap is not permission to hide extra GETs. No actual profile/selection/launch edit occurs in this source addendum.

Root has now ratified the classified maximum envelopes:184 cases <=208 inference+208 count+209 slotGET=625 HTTP, including one startup baseline; the existing24 Conversation coexistence trials <=24 inference+24 count+25 slotGET=73 Conversation HTTP, plus existing6 Main requests. Lifecycle/health/auth remains a separate explicit ledger. Cancellation preflight22 cap stays unchanged, with two-slot/target-role interpretation and other-role foreground permission; same-role reuse still requires release. These caps are not live GO, retries or extra-case credits.

## Accounting and focused regression requirements

Keep existing count/inference totals intact. Add separate slot-observer counts and all-HTTP totals, plus any existing lifecycle traffic separately. Record role/fixed slot, lease/request IDs, owner generation, wait timestamps, predecessor, absolute deadline, dispatch seal/cancel/close/worker-terminal, full-terminal evidence, witnessed task and basis, GET send/receive bounds, release basis/time, unresolved reason. Retain bounded owner diagnostics after old job/coroutine removal. `_observe_admission` remains passive; it has no release authority. No prompt/output/token in ordinary diagnostics.

Required service-free regressions through real common gate/native construction:

1. Both callers use one owner; role0/1 is present in identical count/inference bytes; missing/mutated/bool/out-of-range IDs reject. No same-role second dispatch while unresolved, no cross-role borrowing.
2. Early planner cancellation, delayed server insertion and idle-first leave slot1 unresolved while a new classifier request actually reaches slot0. Old job removal/detach/new call cannot clear slot1.
3. Zero-inference retirement seals delayed count completion; inference-attempt accounting/retirement race has no gap. Close/worker-terminal never releases an attempted lease.
4. Full validated response then fresh idle releases once; bare response does not. Busy→idle association releases target only; retained idle task ID works; unfamiliar target task rejects.
5. Startup two-slot geometry exact; wrong slotcount/IDs/context, missing auth, malformed/duplicate/oversized/late GET fails. Fixed GET caps and spacing survive new callers/timeouts, with no loop.
6. Process PID reuse/exact creation/executable/argv/listener/token drift before or after GET/dispatch blocks; no full finalizer/asset rehash per request; production main never supplies a fake passed proof.
7. Original2s includes waiting/current identity/count/parse/GET; expiry sends no later count/inference, no timer renewal. Other-role uncertain observer cannot hold a global inference lock.
8. Immediate audio invalidation during held planner inference still clears only owned output; late results cannot refill PCM/publish transcript/write business. Foreground routing remains useful with planner role latched.
9. Feature-off is compatible and adds no owner/probe traffic. Route's own ambiguous timeout honestly latches slot0; no fake guarantee that two slots eliminate all failures.

Use fake transport/OS/clock boundaries with barriers; run focused changed modules then one appropriate integrated service-free suite on final bytes. These tests prove state/traffic invariants, never actual b10690 latency, physical audio or memory reserve.

## Why selected over the simpler alternatives

One-slot close+latch is fewer lines but ordinary barge-in can disable all model routing. One-slot bounded read-drain improves terminal evidence yet requires splitting three cancellation layers and still spends foreground time waiting on stale planner work. Two reserved slots retain existing exact-socket cancellation, isolate planner uncertainty and avoid a cancellation-speed dependency for foreground admission. It is the better product contract despite the explicit capacity/resource qualification work. No read-drain fallback is added.

Remaining live facts are exact served per-slot capacity and role-ID capability, contended route performance, same-role cancellation/release/cleanup, actual Main/reserve coexistence and physical audio. Source implementation can complete with production readiness still false pending that evidence. The selected design supplies real wiring and honest failure behavior; it does not pretend the stock runtime guarantees preemption.

## Root precedence and source protocol

This is the selected Task17 source addendum and supersedes earlier single-Conversation4096/1/cross-rolepreemption prescriptions for grounded-enabled operation. Main32768/1 remains fixed. Canonical role labels classifier/planner, fixedslots0/1. Readiness Expected pair8192/2, actualper-slot4096. Historicalfeatureoff path unchanged. No secondproof/session/consumerAPI is added. Exact existing6Main/24Convo refinement is in SDD/task-17-addendum-brief.md; total15classifier/9planner, original>=6classifier/Main inferenceoverlaps plus>=6planner/classifier overlaps, all originaldeadline/reserve/cleanup gates. No runtimeorprofilechange/GO follows fromthisspec.

## Final bounded-drain precedence and one qualification witness

Root's prospective bounded-drain ruling supersedes the earlier no-read-drain/immediate-close statements above for ordinary GroundedJob invalidation. Invalidation immediately sets active=False, revokes publication and seals new dispatch. `AdmissionRequest.revoke_for_drain(reason='cancelled') -> bool` returns true only for an already-attempted planner with no hard abort and time remaining on its original deadline. It leaves the exact existing socket, reader and outer job running within that deadline. A full valid terminal response followed by a fresh target-idle observation releases the role; all late output remains stale. There is no replacement reader/request, renewed timeout, retry or new scheduler. Before inference, invalidation hard-retires and seals the count-to-inference transition. Explicit `GroundedJob.retire(reason, abort=True)`, transport failure, timeout and shutdown hard-close; uncertain attempted inference remains latched. Repeated invalidation cannot clear a hard abort.

An old drain may not overwrite a newer job's diagnostic. `GroundedAnswers.shutdown(timeout_seconds)` aborts and boundedly joins the existing job registry, including detached jobs, and reports actual outstanding transport workers, observer workers and scheduled cleanup. `TaskCoordinator.shutdown` invokes it even with no current Legacy owner, sharing the original shutdown budget. Outer-task completion is not transport termination or server release. No new job registry is introduced.

For the predeclared active-slot cancellation trial only, `await owner.observe_active(current_planner_admission, absolute_deadline)` permits at most one authenticated GET per current exclusive attempted planner lease before terminal/hard abort. It returns an immutable AdmissionSnapshot after the same owned transport/parser/identity checks and task-association logic. Ordinary native paths do not invoke this method. It neither grants readiness nor supplies a synthetic release flag. Its deadline is bounded by the original admission deadline. Normal terminal cleanup waits for an outstanding same-role witness worker within that deadline before its one fresh GET. A witness failure or absent active window is not permission to repeat it.

Admission receipts expose `publication_revoked_at`, `drain_started_at`, `cleanup_outstanding`, `witness_get_attempts`, `cleanup_get_attempts`, total `slot_get_attempts`, and all previous structural timing/release fields. `slot_get_attempts = witness_get_attempts + cleanup_get_attempts` per lease; owner totals also include its one startup GET. Normal cleanup max1 and hard-abort cleanup max2 share the cleanup allowance, so normal1 followed by abort cannot become3. The optional witness is separate. The 1100ms hard-abort follow-up spacing uses preceding cleanup-worker termination, not witness termination; no same-role observers overlap. Probe records include `kind`, owning admission `request_id`, and actual observer `probe_request_id` for exact transport capture joins. Attempt timestamps precede socket send and must not be interpreted as successful sendall completion.

The two-trial functional screen remains inside the unchanged22 ceiling: Trial A early after actual inference sendall completion max8 HTTP, Trial B after actual associated active-slot witness max9, plus two negative-auth GET checks once = max19. Successful normal drains total17 including auth. Each trial has at most one planner and one classifier inference with their counts; startup and all GETs are charged. If A remains latched, B may use a fresh sequential owned generation only after proven old-owner cleanup. No simultaneous second model, extra final-idle GET, replacement trial, third planner reuse request or spare-credit reuse. Source tests prove next-planner reuse; live windows must retain failed/inconclusive outcomes. Actual NativeCall tests use injected audio and fictional services; they do not prove physical phone audio or runtime performance.
