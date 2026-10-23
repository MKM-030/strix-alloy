# Task17 — one-task grounded answers

Status: **Root-ratified, 24 October 2026; reviewed Task16 handoff at `1d786c82ec5586598bf3d7e2b164472b6786a227`.** This document specifies the implementation contract adopted after `grounded-conversation-prefreeze-decision.md`, not live activation or qualification. Additional source reads used only immutable Git blobs at `84a5cffe0212998b2762c40ac9083a2f751a76d9`. Task16's mutable files and transport were not inspected. Root's separately supplied source-cancellation finding is attributed below. No product edit, model/HTTP/service operation, instance, closed corpus, evaluator, old output, or subagent was used.

## Product result and boundaries

While the single LegacyVA workflow runs, the caller can ask a short question about one own task: what they said/corrected, whether that input is locally queued/submitted/uncertain, the actual current question, why this task waits in the local single-context queue, or what ServiceNow has already said. The answer selects supplied evidence and renders attributed statements with typed local-state qualifications. It cannot invent business rationale, current stock, a field mutation or a successful order. Missing evidence produces an honest short gap response. It never automatically forwards that question to ServiceNow.

Corrections, current answers, explicit new work and exact business-cancellation requests retain normal durable routing. The new route has no mutation, cancellation, dispatch or agent-selection authority. The executor, one inflight Legacy turn, unknown-outcome reservation/no replay and stored original caller wording remain unchanged. No call-wide generative answer, multi-task comparison, extra database, retrieval layer, second judge or general orchestration framework.

Finish/review Task16 first; implement this slice against its reviewed interfaces, then freeze the final enabled route/prompt/catalogue/token admission together. Production configuration remains disabled by default and live sharing is blocked until cancellation/slot release and coexistence are measured.

## Routing contract

Add `grounded_answer` to route/observation intent enums and one candidate with `meaning='explain'` per own task, including tasks without a current question. Only add these candidates when the feature is requested by the coordinator's read-only routing context. Append the optional `grounded_answers_enabled: bool=False` context/snapshot field so existing positional call sites retain meaning. Deep-freeze it with the snapshot. Do not derive the flag from caller text or agent descriptions. Task-scoped read permission is existing call ownership, not a new business capability.

The response stays one `choice` key, output24 tokens/64 UTF-8 bytes, with immutable request-local mapping. Keep **all competing options and hard70 maximum**. An enabled catalogue that needs71–78 options fails `context_budget` before inference; never omit a competitor or silently fall back to a different profile. Preserve the original maximum70 fixture and test enabled overflow. The actual enabled70-token shape must pass Task16's exact admission independently of the old catalogue's token fit.

Policy rejects a foreign/conflicting explicit task reference, mismatched selected task and recognized independent competing action. Focus cannot resolve genuine ambiguity. A unique implicit semantic task reference remains the model's qualified judgment, as in semantic status; option membership alone does not establish it. Bound task must remain in the same scope and current registry/ownership guard before scheduling. A current-question help option still renders its original definition/repeat behavior. `grounded_answer` does not require question eligibility and never reopens an answered question.

Enabled deterministic routing bypasses the existing broad status/help/retained-text/capability pattern branches, so a retrospective question is offered to semantic routing. Preserve deterministic audio/cancel and explicit correction paths. For unprefixed scalar answers retain exact yes/no, strict date and spelling fast paths; name/manager/location go through offered semantic answer selection when enabled. Immutable source shows name shape can accept “Warum” and location shape can accept “Weshalb wartet die Lieferung” without a question mark; those shapes cannot safely guarantee the absence of a grounded question. This bounded precedence choice is part of Root's spec ratification. Do not replace the bypass with another synonym/forbidden-word list. Update prompt obligations: current answer/correction means giving or changing business input; a read-only question about existing task evidence is grounded_answer; status is actual status; concrete field repeat/definition remains question help. An unsupported business reason may select grounded_answer and receive a gap. Explicit requests for new business work stay business routes. Mixed independent requests clarify rather than silently losing a component.

With no own task, no grounded option is offered; an ordinary clarification may include the existing fixed capability explanation without a planner call. Routing timeout/schema/unavailable/context-budget/rejected choices and generic clarify never invoke the answer planner. Disabled profile behavior stays compatible. Qualification applies to the enabled profile intended for use.

## Exact immutable objects and additive APIs

These are product contracts, not a guessed name for Task16's transport methods:

```python
TaskStore.grounded_snapshot(scope_id, task_id) -> GroundedSnapshot
TaskStore.grounded_revision(scope_id, task_id) -> EvidenceRevision
TaskCoordinator(..., *, mode='legacy', grounded_answers=None)
ConversationAttachment.invalidate_grounded(reason_code) -> None
ConversationAttachment.note_grounded_evidence_change() -> None
GroundedAnswers.plan(request: GroundedRequest) -> GroundedPlan  # async
OutputSink.publish_guarded(event, validity, *, grounded_id=None)
OutputSink.invalidate_grounded(grounded_id) -> None
```

Existing positional APIs and two-argument `publish_guarded`, plain `accept`/`publish`, seven event fields and legacy fake emitters remain available. The extension requires the guarded/targeted sink methods and a native origin predicate; its activation refuses missing support instead of emitting unguarded answers. Internal fake/service-free tests inject those dependencies. No callable, epoch, plan or private evidence is added to Store business payloads or public events.

`GroundedRequest` fields (all immutable):

- `request_id`, `utterance_id`, exact `utterance_text`; full local scope binding `(scope_id,call_id,call_generation,instance_id,assistant_id,principal_id)`; selected `task_id`; `job_id`.
- Captured `routing_checkpoint`, `evidence_revision`, registry identity/digest, focus/workflow identities, pinned `contract_version`.
- `origin_validity` (the existing native epoch/liveness closure), `playback_generation` captured after acceptance's interruption and before planning, and `deadline_monotonic`.
- `evidence` tuple and request-local reference maps; no live mutable Store/executor/attachment object. The orchestrating job retains the actual lifecycle predicates; none are serialized.

`GroundedSnapshot`: scope binding; all scope task headers (max8, including competing identities/objectives); selected task typed state/version; current question if actually bound; latest two operations and their acceptance provenance; latest eligible current-operation backend text; `evidence_revision`. Native input identity and coordinator workflow identity are captured separately without an intervening await and validated around the read.

`Evidence` fields: `ref`, `task_ref`, `kind`, `source`, exact `text`, `complete=True`, `fact_code`, `operation_ref`, `question_ref`, `context_version`, `historical`. Local mapping additionally retains source event ID/sequence, actual task/operation/question IDs and fingerprints. Model sees only short refs and the fields needed to select facts; never credentials, principals or raw identity tokens. Allowed `source`: `caller`, `backend`, `local_state`, `local_contract`. Allowed kinds cover `caller_statement`, `question`, `backend_message`, `dispatch_fact`, `task_fact`, `queue_fact`, `contract_clause`. `fact_code` exists only for deterministic local facts. Strings are data, including fake instructions and action-shaped text.

Planner response, exact keys/no prose:

```json
{"outcome":"answer","form":"change","evidence":["e1","e2","e3"],"gap":"none"}
```

- `outcome`: `answer|insufficient|needs_business|ambiguous`.
- `form`: `state|change|current_question|queue|attributed|none`.
- `evidence`: unique ordered request-local refs, maximum4, dynamic enum; empty for non-answer outcomes.
- `gap`: `none|rationale|missing_record|fresh_check|scope|conflict`.
- Answer requires nonempty evidence, non-none form and `gap=none`; non-answer requires `form=none`, empty evidence and non-none gap. Unknown/duplicate refs, extra keys, duplicate JSON keys, trailing content, invalid combinations or over-budget content fail closed with one fixed local fallback. No repair/retry call.

`GroundedResult`/private diagnostic record: request/job identity, selected refs/form/outcome/gap, disposition (`published|stale|unavailable|budget|invalid|insufficient|needs_business|ambiguous`), source revision/hash, measured elapsed values and no-write result. Keep raw caller/evidence only in existing private test/qualification result paths if authorized; do not create a new durable receipt database or general text logs. Model semantic correctness is unknown at runtime.

## Bounded coherent Store reads

Use the existing lock plus one SQLite read snapshot for capture, no schema migration or journal write. If reusing `_transaction`, its savepoint/BEGIN mechanism is permissible, but no accepted operation/event may be inserted by these methods. Project explicit allowed columns: never expose operation `voice_context`, `immutable_payload`, receipt/evidence blobs or arbitrary callback JSON to the model.

SQL bounds, all selected-task reads validate scope ownership in the same snapshot:

| Read | Bound and ordering |
| --- | --- |
| Scope binding/attached | One row by scope_id. |
| Scope task headers | `WHERE scope_id=? ORDER BY created_at,task_id LIMIT 9`; ninth is overflow, not discarded. Include identity/agent revision/capabilities and objective/state/version. |
| Latest operation identity per scope header | Correlated `ORDER BY operations.rowid DESC LIMIT 1`, at most8; identity/version/dispatch only, for bounded freshness. |
| Selected task operations | `WHERE task_id=? ORDER BY rowid DESC LIMIT 2`; reverse locally for chronological rendering. Do not use created_at to resolve insertion ties. |
| Selected task pending-delivery existence | `SELECT 1 ... WHERE task_id=? AND dispatch_state='unsubmitted' LIMIT 1`; do not infer absence of pending delivery from only the latest two operations. Include this Boolean in question eligibility and evidence revision. |
| Acceptance provenance | For each of those at most2 operation IDs, `WHERE task_id=? AND operation_id=? AND type='utterance_accepted' ORDER BY sequence DESC LIMIT 1`. |
| Current question | Scope question primary-key read, accepted only if same task, exact version and current eligibility; otherwise absent. |
| Latest observation and settlement | For latest selected operation only, each exact type with `ORDER BY sequence DESC LIMIT 1`; at most2 rows. A settled operation's nonempty final reply takes precedence over streamed observation. |
| Selected task event head | `WHERE task_id=? ORDER BY sequence DESC LIMIT 1`; sequence only. |

Do not scan `events()` or `operations()` to construct answer evidence. Decode only bounded rows; existing journal payload maximum16384 characters remains an outer cap, then whitelist `text`, exact answered-question metadata, and the last whole reply of a valid bounded replies list (existing max32 entries/max4000 chars each). No search backward through unbounded history to find a preferred quote. Missing/inconsistent provenance means the relation is unavailable.

`EvidenceRevision` is the tuple of attached full scope identity, all task-header identity/version/state/agent bindings and latest-operation identity/version/dispatch, exact scope-question identity/task/version/text/source, selected task event-head sequence and selected latest-two operation identity/dispatch/outcome. Runtime registry/focus/workflow and local contract hash are additional request guards. Revision reads have the same header/identity bounds but do not fetch message bodies. The selected event head catches same-version progress and an older-operation late callback. A current-question ABA changes its identity even when text returns to the same value. Conservative invalidation is acceptable; silent stale publication is not.

Each evidence package contains max12 records. Selected task history only; other headers do not grant access to their caller/backend text. Local queue fact may say another workflow occupies the single context without including its substantive history. Never discard competitors to fabricate a unique target.

## Relations and honest rendering

All output is at most4 complete fact segments and600 Unicode characters, including attribution and required qualifications. Individual source strings remain whole and at most4000 characters, matching the intake/journal boundary; a selected long string that cannot fit is unavailable for spoken quotation. Never silently slice a sentence/date/name/negation. Optional complete segments may be omitted; required source/dispatch/no-replay qualifiers cannot. If the form cannot fit, use a shorter valid form or a fixed gap response, not an incomplete claim. No normalization of caller values.

| Form | Necessary deterministic relation and required content |
| --- | --- |
| `state` | Selected task's typed current state and latest operation's dispatch/outcome. Say local saved/unsubmitted, submitted-unconfirmed, settled-awaiting-input, suspended/cancel-requested, cancelled-locally, or unknown as actually supported. Unknown includes no automatic replay. Never map backend “erfolgreich” text to succeeded. |
| `change` | Latest operation has accepted `amend_task` kind and its immediate same-task predecessor is present with acceptance provenance/consecutive operation versions. Quote them as caller statements; latest's local dispatch qualification is mandatory. If this relation is absent, an attributed chronology can be used, but not “you corrected X to Y”. Do not assert field replacement, commit fencing or remote amendment success: Legacy has no such authoritative proof. |
| `current_question` | Exact current question ID, task/version and eligible delivery binding; include actual question, optionally an accepted caller statement if it fits. It describes what is currently requested, not all remaining workflow requirements. No current question yields a gap/state answer, never revival of previous question. |
| `queue` | Selected latest input is unsubmitted, task nonterminal and attached; captured workflow context belongs to another own task and the existing worker's eligibility rule therefore excludes selected task. Combine this fact with pinned single-context contract. If this exclusion is not proven (e.g. readiness/unknown reason), give only saved/not-submitted state, not an invented cause. |
| `attributed` | Exact permitted caller/backend record, with source and historical/current-operation qualification. A backend statement is “ServiceNow meldet …”, not verified business truth. The planner's selection of a relevant statement is still semantic judgment. Quotation alone never proves that it answers the user's question or establishes a cause. |

There is no free `because` or business-rationale generator. If an available backend message explicitly supplies a reason, the planner may select it as an **attributed** message; independent scoring checks that its content actually supports the question. If no reason is supplied, `insufficient/rationale` says the reason is not present. Fresh stock/business lookup uses `needs_business/fresh_check` and creates no operation. Ambiguous target remains clarification. Injection-shaped evidence is quoted only as attributed data if useful, never obeyed. Contradictory backend claims cannot outrank typed unknown/no-replay state.

## Planner transport, budgets and ownership

Reuse/adapt **Task16's final reviewed admitted transport** and exact tokenizer/chat-template/schema admission. Do not implement another HTTP client, byte/token estimator, endpoint validator, runtime registry or model loader. At the Task16→Task17 handoff, record the reviewed commit and concrete callable interface before coding the adapter. If that interface requires a small general request/schema parameter, change it only after a concrete Root review; no guessed API or parallel edit of Task16.

Planner budgets: input at most 4000 characters unchanged; at most 12 evidence records, complete whole sources, four selected segments and 600 rendered characters. One exact admission counts the **full serialized/chat-templated input including schema/template overhead**, at most 3072 tokens; output at most 128 tokens; total context 4096 (896 remaining after these maxima). There is no separately counted evidence-token subcap, subset-token measurement or additional count request. Reuse Task16's single exact full-prompt admission; bytes remain an independent bound. Complete HTTP request body at most 16384 UTF-8 bytes; standard HTTP response JSON body at most 8192 bytes; inner plan at most 2048 UTF-8 bytes. HTTP framing/header bounds are separate and inherited from Task16's reviewed transport, not charged to or substituted for the 8192-byte JSON-body bound.

One model attempt, temperature 0, no queue/retry. Queue/owner admission wait at most 100 ms; model interval at most 2 s; admission to validated enqueue/publication preparation at most 2.2 s, or guarded fixed fallback/suppression. The 2.2 s bound does **not** abort a still-valid long TTS sentence or require its PCM to finish playing by that deadline. All input/evidence/generation freshness guards remain active during synthesis and physical buffer drain. Measure ASR-final to actual final-answer audio separately; the two routing/planning preparation stages can approach 4.4 s before speech delivery, whose duration is additional.

One attachment-owned answer job; no planner await while `_accept_lock`, Store transaction, output lock or business reservation is held. The acceptance path captures and schedules the job then returns. Keep the private current-answer identity/guard alive after planning finishes until its queued/speaking output terminates; clearing the coroutine handle must not make valid queued speech appear stale, or erase the identity needed to invalidate buffered PCM. The notice is omitted in v1 to avoid a separate low-value output race; existing final-answer/fallback publication is guarded. A future notice is not evidence of substantive-answer latency.

At a new acceptance attempt, cancel the previous answer job before routing; the prior native input predicate still governs its speech. Confirmed VAD onset calls `invalidate_grounded('input')` immediately after existing epoch advancement, including silent inference/empty ASR. Do not create another epoch or change business authority/preconditions. Explicit speech stop, input loss, detach, shutdown and owner/registry revocation also invalidate; never cancel Legacy `executor.turn`/observation. No auto-resume/replan after invalidation.

After successful Store mutations within this coordinator, call `note_grounded_evidence_change()` synchronously before publishing newer backend information. Cover accepted input/cancel, question note, dispatch, observed callback, settlement and unknown transition. It rechecks the current answer's evidence/authority guard and invalidates only if changed. The pending/speaking answer also rechecks before enqueue, transcript and each chunk. For any future external Store writer, an explicit notification is required before enabling that writer; this slice introduces no generic observer/event bus. Tests changing Store directly call the notification seam to represent the production write boundary.

Job cancellation is not server cancellation proof. Root's source follow-up found that stock non-streaming client disconnect is polled at approximately 1 s intervals and cancellation can also wait for decode yielding. This is a concrete live-sharing blocker: a closed socket/client task does not establish timely server-slot release, and that source behavior supplies no 100 ms guarantee. Until the existing runtime owner can cancel the low-priority request and prove bounded actual slot release, production grounded runtime readiness is false. Keep route deadline 2 s/max 2.2 s including wait, conversation 4096/par1, Main 32768/par1 and reserve >=18 GiB. Cancellation-to-slot-release within 100 ms remains a proposed, unproven later measurement target, not a current capability. No second resident model/process, concurrency increase, Main reduction or runtime profile change is authorized. Fake planner/owner objects prove product lifecycle only.

## Speech freshness and narrow PCM ownership

The answer uses existing `local_reply`, priority20, exact task/version and utterance identity. Normal backend priority10, local/control0 and the max-eight arbiter pending list remain. It is transient, never `publish_deferred` and never a lifecycle control. The combined validity guard binds attachment/owner, selected task/call scope, job identity, captured native origin, captured playback generation, routing checkpoint, evidence revision and registry/focus/workflow. Capture before planning, not at publication; check again with no await between final validity and queue insertion.

Validity stops future chunks but cannot withdraw already buffered PCM. The existing84a5cff arbiter has one untagged playback buffer, so add only grounded ownership metadata to that arbiter:

1. A queued grounded entry may claim speech only after a **genuine playback-buffer drain** (`len(playback.data)==0`) as well as its usual liveness/readiness/validity checks. It must not clear earlier backend/lifecycle bytes to manufacture drain. If not drained, leave the entry bounded in the same pending list; a wake/drain check may use the existing short playback pacing pattern, not a second queue. Higher-priority ready entries retain existing selection order.
2. With no await between last check and claim, set private owner `(grounded_id, captured_generation)` and started state. A stale scheduling reservation cannot claim a newer generation. Emit transcript only after this claim, then existing synthesis/chunk guards.
3. Keep ownership and the single active delivery through **final PCM drain**, including after synthesis has yielded its final chunk. Do not start backend/lifecycle/other speech while that grounded owner still has buffered bytes. This keeps the buffer exclusively attributable to that grounded entry. Do not hold any coordinator/Store lock while waiting. On own-task backend arrival, evidence invalidation clears the old answer first, then publishes the new backend normally.
4. `invalidate_grounded(id)` is synchronous: remove only matching pending grounded entries; cancel matching active synthesis. Immediately before clearing playback, recheck same grounded owner ID **and** generation, with no await before `playback.interrupt()`. If either changed, clear nothing. If ownership is still the grounded entry, all remaining bytes in that buffer belong to it by step1/3. Release its owner and wake the same arbiter. Preserve unrelated pending/deferred backend and lifecycle entries; never stamp them with a new generation merely to make them eligible.
5. Existing input/hard interrupts already handle their permitted broader semantics. Clear/revoke grounded ownership atomically with those interrupts; a delayed answer invalidation must not clear newer caller/lifecycle/backend audio. The targeted method cannot affect microphone PCM or input queues. All terminal paths/eviction/TTS failure/close finish the owned entry once. No prefix/full replay after start.

If Task16's reviewed source introduces an already sufficient narrow tagged ownership seam, reuse it; do not add a parallel mechanism. Physical audio already sent is not retractable. Counters remain generated/sent, never heard. A backend result remains journaled even if speech is deferred/suppressed.

## Configuration and source scope

Append `grounded_answers_enabled: bool=False` to `ResponsiveConfig`; accept only an actual JSON boolean under the existing strict whitelist. Missing field preserves old profiles and positional field ordering. `true` requires enabled assist mode, a configured conversation model and the extension's guarded native/output dependencies; full mode remains rejected. No second URL/model/token/profile setting and no environment-variable override.

The config flag is a request, not a qualification proof. Production wiring requires a trusted runtime-readiness result from the existing owner; absent that concrete later evidence, reject requested grounded startup with a clear local configuration error before offering enabled routes. Do not silently offer the route while having no usable planner, and do not disable otherwise healthy business state after attachment. Service-free tests inject a fake runtime-readiness provider explicitly at construction. Do not create a user-editable `qualified=true` bypass or a new manifest-validation framework. The later measured activation/wiring decision remains Root's concrete blocker.

Allowed production slice: `route_proposal.py`, `routing_policy.py`, `conversation_router.py`, `task_store.py`, new `grounded_conversation.py`, `task_coordinator.py`, `native_bridge.py`, `conversation_output.py`, `responsive_config.py`, plus a minimal reviewed Task16 transport adaptation only after its handoff. Existing relevant tests and one final `test_grounded_conversation_integration.py` are allowed; no Legacy executor mutation, database schema migration, runtime profile/deployment change or generic evaluator rewrite. Root decides any unexpected additional dependency before it is edited.

## Focused public proof and later semantic evidence

Use fresh fictional text/IDs and fake choices/planner/held Legacy operations. Failures must show a user-relevant invariant, not mirror helper code. Use real `ConversationRouter`→attachment→Store→OutputArbiter, and real NativeCall methods for onset/lifecycle. Async Events/barriers control races; timing limits detect deadlock, not simulate measured performance.

Required integration scenarios:

1. No current question and a real waiting current question both offer/readily execute grounded_answer for the chosen task; force the offered choice, never inject a finished route. A “what changed/why queued” utterance is not swallowed by local help/status. Exact yes/no and correction still durably retain original text once.
2. A correction plus dispatch state renders both exact statements and mandatory local qualification; submitted and unknown variants never claim a remote change or retry. Seed no correction provenance and prove safe chronology/gap instead of invented correction.
3. Current-question answer contains the actual identity-bound question; no-current-question cannot revive old text. Queue explanation requires the worker's actual different-context exclusion; mere delay does not produce that cause.
4. Supplied backend rationale is attributed; absent rationale/fresh stock request produces a gap and zero operations. Irrelevant true quote counts as unhelpful in semantic scoring, not “grounded success”. Older-operation success cannot mask current unknown outcome.
5. Two indistinguishable task targets, explicit foreign reference, fake command in evidence, forced business/answer versus grounded choices and mixed independent actions exercise policy boundaries. An explicitly selected different own task must not receive another task's history. Fake choices do not prove unrecognized semantic ambiguity detection.
6. Same-version backend event, question ABA, registry/detach and changed latest operation invalidate held planning. No stale transcript/chunk. New ordinary business input still accepts independently of the stale answer's origin.
7. Actual silent VAD onset during held planning, then empty ASR, suppresses output; a later input uses its own origin. Legacy work remains once-inflight and observed. Explicit stop stops speech but never business execution.
8. Evidence changes **after final synthesized chunk but before physical buffer drain**: targeted invalidation clears only that owned grounded PCM. Preceding backend/lifecycle PCM delays owner acquisition; it is never cleared. A delayed old invalidation after ownership changes leaves new audio intact. Pending deferred backend speaks once when still valid, without transcript replay.
9. Overlong source/needed qualification cannot be cut to fit600 chars; invalid plan/refs/extra prose/duplicate JSON and exact token/byte/catalogue overflow fall back with no model retry. Cap70 holds with all competitors; no fake token success claim.
10. Config missing flag works, true/non-bool/full-mode/unproven-runtime behavior is explicit, plain emitters remain compatible when disabled, and enabled routing cannot start without the guarded seams. Cancel-resistant fake planner returning late cannot refill speech or release an unproven server slot by assertion.

Run focused changed modules during implementation and one final appropriate integrated service-free suite with relevant existing router/policy/store/coordinator/output/native/config and endpoint/input-lifecycle regressions on final bytes. Do not repeat broader testing without a new change/failure. Report fake-test and source-review evidence honestly.

Root fixes later qualification as the existing authoring/loader/result path and **one integrated freeze, independent authoring and run of184 cases**: retain120 routing cases (12 strata x10) plus40 status cases and every existing gate unchanged, then append24 distinct grounded cases. Grounded cases:16 answerable (4 each correction/dispatch, current question, queue, attributed backend) plus8 gap/ambiguity/adversarial cases. Grounded usefulness must be>=14/16 and>=3/4 in each answerable family. All24 must have zero wrong-source/task, invented business claim, unintended write/cancel or stale published output; all8 gap cases must have a safe and correct disposition. Required facts, allowed sources and forbidden claims are frozen before outputs. Irrelevant true quoting/blanket abstention is not useful success.

Maximum accounting is184 classifier attempts plus24 planner attempts=208 inferences, and416 count-plus-completion HTTP requests; local bypasses and unused attempts are reported separately, never converted to extras. Root may make accounting more concrete before authoring but may not silently add calls. Extend the existing independent-author tool with a small grounded fixture/expected-evidence DSL distinct from its existing three-agent catalogue; do not build another framework or inspect/modify it during this source-only task. New authoring and adaptation are a later explicit task.

Deterministic race/authority proofs stay in service-free tests. Runtime coexistence retains its original6 Main+24 Conversation workload. Any focused planner-overlap/cancellation check needs a separate explicit call/HTTP budget before execution; it is not an implicit addition to coexistence or184-case semantic coverage. Physical iPhone measurements remain separate live prerequisites. Do not inherit the old60+24+12 campaigns or expand the independent test matrix beyond184. This specification authorizes no model run or GO.

## Root handoff after Task16 independent fix closure

Task16 is reviewed through1d786c82ec5586598bf3d7e2b164472b6786a227. Read .superpowers/sdd/2026-10-23-responsive-voice/task-16-task17-transport-handoff.md. Root ratifies its narrow shared admission extraction and the two immutable source budgets (route3584/24, planner3072/128), PreparedChat and run_admitted_chat interfaces, preserving existing public router APIs and existing controlled-transport test seams where needed. This explicitly permits changes to conversation_admission.py, its router adapter and directly affected admission tests within Task17; no second client/framework. Strict JSON can move once and be re-exported for old internal callers. All prior count/framing/deadline/usage/retirement invariants remain covered. New receipt budget-limit fields must be explicit, not a false runtime/template proof.

Task16's fixed public-ownership race also binds Task17: invalidating a grounded job must synchronously seal/retire its owned model admission at the outer owner boundary before relying on asynchronous task cancellation. A job whose count returns after onset/invalidation cannot initiate a new inference, even before its child cancellation handler is scheduled. Provide a narrow private job cancellation handle/token bound to that job; no second epoch and no Store/business write authority. Add this actual integrated late-count regression. Local controls must not wait on telemetry or an occupied thread pool. Do not reintroduce either finding during the shared-helper extraction.

The source-backed100ms slot-release target is stretch/diagnostic only. Hard live gates are unchanged model2s and next-routep95<2s/max2.2s including actual release wait, no next inference until observed release/no unobserved server queue,18GiB reserve, independent local audio stop/iPhonebargein targetp95<300ms and no stale effect. This decision precedes measurements; pinned nonstream source may observe disconnect only on a1s wait cycle. Do not silently switch to streaming, increase parallelism/context, change Main or relax2s.

Before implementing production readiness wiring, inspect the existing owner/config seam and name the exact trusted callable/proof mechanism. If no existing consumer interface can provide it without an additional source file/field, ask Root with the smallest concrete change; do not leave a fake readiness bit as production integration or create a second manifest framework. It is valid for actual final proof data to remain absent until later measurement, but the production verification path must be concrete and reviewable before the final semantic freeze.
## Root ruling for Task17 fix round1 (24 October)

Narrow output ownership and preservation of unrelated pending entries takes precedence over the earlier instruction to call shared `playback.interrupt()`. That method advances the global generation. Targeted grounded invalidation and exceptional/final cleanup must instead clear only exclusively owned PCM for the matching grounded ID and captured generation, without advancing the global generation or restamping unrelated entries. Existing job/chunk guards must prevent late refill. Preserve preceding/new-owner PCM and valid pending lifecycle, ordinary and deferred backend entries exactly once. This resolves the contradiction identified in task-17-review.md; no live permission or broader source scope is added.
