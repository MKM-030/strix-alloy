"""Process-owned legacy business observation, independent of native/audio tasks.

One attachment reserves one legacy context until submitted observation and owned
cleanup finish. The passed emitter must enqueue promptly (OutputArbiter.publish
does); callbacks are journaled before a separate output worker invokes it.
"""

import asyncio
import hashlib
import inspect
import time
from collections import Counter
from dataclasses import replace

from business_tasks import Scope, StoreConflict, StoreDenied, StoreInvalid, bounded_identifier
from conversation_router import RoutingContext, Route
from routing_policy import RoutingDecision
from servicenow_executor import LegacyVAExecutor


def render_grounded_status(state, latest_reply=''):
    """Finite presentation only; no state inference or authority from reply text."""
    descriptions = {
        'queued': 'Die Aufgabe ist lokal angenommen und wartet auf die Übermittlung.',
        'running': 'Die Aufgabe wird bearbeitet.',
        'awaiting_input': 'Die Aufgabe wartet auf weitere Angaben.',
        'ready_to_commit': 'Die Aufgabe ist zur verbindlichen Ausführung bereit; diese ist noch nicht bestätigt.',
        'committing': 'Die verbindliche Ausführung läuft; ihr Ergebnis ist noch nicht bestätigt.',
        'succeeded': 'Die Aufgabe wurde erfolgreich abgeschlossen.',
        'failed': 'Die Aufgabe ist fehlgeschlagen.',
        'cancel_requested': 'Der Abbruch ist vorgemerkt. Eine bereits übermittelte Aktion kann ich nicht sicher stoppen; eine Stornierung ist nicht bestätigt.',
        'cancelled': 'Die Aufgabe wurde abgebrochen.',
        'outcome_unknown': 'Das Ergebnis der Aufgabe lässt sich nicht feststellen. Die Anfrage wird nicht automatisch wiederholt.',
    }
    description = descriptions.get(state) if isinstance(state, str) else None
    if description is None:
        return 'Der Status der Aufgabe lässt sich nicht feststellen.'
    suffix = (' Letzte Antwort: ' + latest_reply) if latest_reply else ''
    return (description + suffix)[:4000]


class TaskCoordinator:
    def __init__(self, store, router, agents, executor_factory, *, mode='legacy', grounded_answers=None):
        if mode not in ('legacy', 'full'):
            raise ValueError('invalid coordinator mode')
        self.store, self.router = store, router
        self.agents = list(agents)
        self.executor_factory, self.mode = executor_factory, mode
        self.grounded_answers = grounded_answers
        self._owner = None
        self._shutdown = False
        self.routing_counts = Counter()  # Bounded nontext (disposition, reason, acceptance) keys only.
        self.proposal_counts = Counter()  # Bounded (status, intent, meaning, domain), before policy.

    @property
    def available(self):
        """Synchronous admission hint; attach still performs the authoritative check."""
        return (self.mode == 'legacy' and not self._shutdown and self._owner is None
                and not self.store.has_unresolved())

    async def attach(self, scope: Scope, emit, *, executor=None):
        if self.grounded_answers is not None and (not callable(getattr(emit, 'publish_guarded', None))
                or not callable(getattr(emit, 'invalidate_grounded', None))
                or not hasattr(emit, 'playback_generation')):
            raise StoreDenied('grounded answers require guarded native output')
        if self.mode == 'full':
            raise StoreDenied('full mode requires a verified owned runtime adapter; unavailable')
        if not isinstance(scope, Scope) or self._shutdown or self._owner is not None:
            raise StoreDenied('legacy context unavailable')
        if self.store.has_unresolved():
            raise StoreDenied('unresolved execution requires private reconciliation')
        # A call scope is never revived, even when its previous worker has closed.
        if self.store.list_tasks(scope.scope_id):
            raise StoreDenied('call scope already used')
        attachment = ConversationAttachment(self, scope, emit)
        self._owner = attachment  # Reserve before an async factory can yield.
        try:
            executor = executor if executor is not None else self.executor_factory(scope)
            if inspect.isawaitable(executor):
                executor = await executor
            if not isinstance(executor, LegacyVAExecutor):
                raise StoreDenied('only the owned legacy adapter is supported')
            attachment.executor = executor
            attachment._worker = asyncio.create_task(attachment._run())
            attachment._output_worker = asyncio.create_task(attachment._output())
            return attachment
        except BaseException:
            self._owner = None
            raise

    def snapshot(self, scope_id):
        """Private caller must provide its already-authorized scope; never a public ledger."""
        return self.store.list_tasks(scope_id)

    async def shutdown(self, timeout_seconds=5):
        self._shutdown = True
        deadline = time.monotonic() + max(0, timeout_seconds)
        owner = self._owner
        if owner is not None: await owner.detach()
        # A draining planner can outlive its detached Legacy owner. Its existing
        # job registry must be aborted/joined before the no-owner early return.
        close_grounded = getattr(self.grounded_answers, 'shutdown', None)
        grounded_pending = (await close_grounded(max(0, deadline-time.monotonic()))
                            if callable(close_grounded) else 0)
        if owner is None:
            return {'pending': grounded_pending, 'unresolved': self.store.has_unresolved()}
        done, pending = await asyncio.wait([owner._worker], timeout=max(0, deadline-time.monotonic()))
        return {'pending': len(pending) + grounded_pending, 'unresolved': self.store.has_unresolved(),
                'cleanup_acknowledged': owner._cleanup_acknowledged}


class ConversationAttachment:
    def __init__(self, coordinator, scope, emit):
        self.coordinator, self.scope, self.emit = coordinator, scope, emit
        self.executor = None
        self._attached = True
        self._wake = asyncio.Event()
        self._detached = asyncio.Event()
        self._accept_lock = asyncio.Lock()
        self._output_queue = asyncio.Queue(maxsize=8)
        self._worker = self._output_worker = None
        self._context_task = ''
        self._focus = ''
        self._cleanup_acknowledged = False
        self._executing = False
        self._closed = asyncio.Event()
        self.suppressed_count = 0
        self._grounded = None
        self._grounded_task = None
        self.grounded_result = None  # One bounded private diagnostic, no raw text.

    @property
    def store(self):
        return self.coordinator.store

    @property
    def execution_active(self):
        """Native idle gate: actual observation or dispatch-eligible work only."""
        if self._executing:
            return True
        if not self._attached or self.store.has_unresolved():
            return False
        return any(not self._context_task or op['task_id'] == self._context_task
                   for op in self.store.pending(self.scope.scope_id))

    def _interrupt(self, *, preserve_deferred=False):
        owner = getattr(self.emit, '__self__', self.emit)
        interrupt = getattr(owner, 'interrupt_for_input', None) if preserve_deferred else None
        interrupt = interrupt if callable(interrupt) else getattr(owner, 'interrupt', None)
        if callable(interrupt):
            interrupt()
        retained = []
        while not self._output_queue.empty():
            event = self._output_queue.get_nowait()
            if preserve_deferred and event['kind'] == 'backend_reply':
                retained.append(event)
            else:
                self.suppressed_count += 1
        for event in retained:
            self._output_queue.put_nowait(event)

    async def note_question(self, text, *, task_id=''):
        """Bind an actual greeting/backend question; no dispatch or heard assertion."""
        if not isinstance(text, str) or not text or len(text) > 4000:
            raise StoreInvalid('invalid question')
        async with self._accept_lock:
            if not self._attached:
                raise StoreDenied('scope detached')
            source = 'backend' if task_id else 'greeting'
            if not task_id:
                if len(self.coordinator.agents) != 1:
                    raise StoreDenied('question requires an explicit task')
                task_id = self._context_task
                if not task_id:
                    task = self.store.create_task(self.scope, self.coordinator.agents[0], 'Configured call workflow')
                    task_id = task['task_id']
                    self._context_task = task_id
            self.store.note_question(task_id, self.scope.scope_id, text, source=source)
            self.note_grounded_evidence_change()
            return task_id

    def invalidate_grounded(self, reason_code):
        job = self._grounded
        if job is None:
            return
        # The admission is sealed NOW. Child cancellation alone is too late:
        # a count worker may return before its coroutine sees CancelledError.
        job.retire('cancelled')
        self.emit.invalidate_grounded(job.request.job_id)
        self._grounded = None

    def note_grounded_evidence_change(self):
        self.invalidate_grounded('evidence')

    def _schedule_grounded(self, route, utterance_id, text, checkpoint, registry, authority, output_validity):
        from grounded_conversation import GroundedJob, make_request
        if (self.coordinator.grounded_answers is None or not callable(output_validity)
                or not callable(getattr(self.emit, 'invalidate_grounded', None))
                or not callable(getattr(self.emit, 'publish_guarded', None))):
            raise StoreDenied('grounded answers require native origin and guarded output')
        if not output_validity() or not authority():
            return
        snapshot = self.store.grounded_snapshot(self.scope.scope_id, route.task_id)
        request = make_request(snapshot, utterance_id=utterance_id, text=text, checkpoint=checkpoint,
            registry=registry, focus=self._focus, workflow=self._context_task,
            origin_validity=output_validity, generation=self.emit.playback_generation)
        if not output_validity() or not authority():
            return
        job = GroundedJob(request)
        self._grounded = job
        planner = self.coordinator.grounded_answers
        bind = getattr(planner, 'bind_job', None)
        if callable(bind): bind(job)
        def valid():
            try:
                from grounded_conversation import CONTRACT_HASH, CONTRACT_VERSION
                return (job.active and self._grounded is job and authority()
                    and request.contract_version == CONTRACT_VERSION and request.contract_hash == CONTRACT_HASH
                    and request.origin_validity() and request.playback_generation == self.emit.playback_generation
                    # The bounded revision contains every task/scope/question
                    # member of the captured routing checkpoint, plus progress.
                    and request.evidence_revision == self.store.grounded_revision(self.scope.scope_id, route.task_id))
            except Exception:
                return False
        job.task = self._grounded_task = asyncio.create_task(self._answer_grounded(job, planner, valid))
        job.task.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)

    async def _answer_grounded(self, job, planner, valid):
        from grounded_conversation import GroundedPlan, GroundedResult, FALLBACK, render
        from routing_policy import ContextBudgetExceeded
        request = job.request
        started, plan, child = time.monotonic(), None, None
        disposition, reply = 'unavailable', FALLBACK
        try:
            if not valid(): return
            child = asyncio.create_task(planner.plan(request))
            done, _ = await asyncio.wait((child,), timeout=max(0.,
                min(job.admission.deadline, request.deadline_monotonic)-time.monotonic()))
            if not done:
                job.admission.retire('timeout')
                disposition = 'unavailable'
            else:
                candidate = child.result()
                if type(candidate) is not GroundedPlan:
                    raise ValueError('invalid planner result')
                candidate.validate(request)
                plan = candidate
                reply = render(plan, request)
                disposition = 'published' if plan.outcome == 'answer' else plan.outcome
                if reply == FALLBACK and plan.outcome == 'answer': disposition = 'insufficient'
        except asyncio.CancelledError:
            job.admission.retire('cancelled')
            disposition = 'stale'
            raise
        except ContextBudgetExceeded:
            disposition = 'budget'
        except (ValueError, TypeError, KeyError, AttributeError):
            disposition = 'invalid'
        except Exception:
            disposition = 'unavailable'
        finally:
            if child is not None and not child.done():
                job.admission.retire('cancelled')
                child.cancel()
                child.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            release = getattr(planner, 'release_job', None)
            if callable(release): release(job)
            if self._grounded_task is asyncio.current_task():
                self.grounded_result = GroundedResult(request.request_id, request.job_id,
                    plan.evidence if plan is not None else (), plan.form if plan else 'none',
                    plan.outcome if plan else 'insufficient', plan.gap if plan else 'missing_record',
                    disposition if valid() else 'stale', hashlib.sha256(repr(request.evidence_revision).encode()).hexdigest(),
                    (time.monotonic()-started)*1000)
                self._grounded_task = None
        if not valid() or time.monotonic() > request.deadline_monotonic:
            return
        event = dict(kind='local_reply', task_id=request.task_id, operation_id='',
            utterance_id=request.utterance_id, context_version=request.snapshot.task['context_version'], text=reply, priority=20)
        # OutputSink inserts synchronously before its first suspension. The same
        # predicate is retained through synthesis AND physical buffer drain.
        try:
            accepted = await self.emit.publish_guarded(event, valid, grounded_id=request.job_id)
        except Exception:
            accepted = False
        if not accepted and self.grounded_result is not None and self.grounded_result.job_id == request.job_id:
            self.grounded_result = replace(self.grounded_result, disposition='stale')

    def _queue(self, kind, text, *, operation=None, task=None, utterance_id='', decision=None, checkpoint=None, authority=None, acceptance='local', output_validity=None):
        if not self._attached:
            return
        operation, task = operation or {}, task or {}
        event = dict(kind=kind, task_id=task.get('task_id', operation.get('task_id', '')),
            operation_id=operation.get('operation_id', ''),
            utterance_id=utterance_id or operation.get('utterance_id', ''),
            context_version=task.get('context_version', operation.get('context_version', 0)),
            text=text, priority=10 if kind == 'backend_reply' else 0)
        if output_validity is not None:
            event['_input_validity'] = output_validity
        if decision is not None:
            self.coordinator.routing_counts[(decision.disposition, decision.reason, acceptance)] += 1
            if decision.help_source or decision.route.intent == 'status_query':
                event['_help_checkpoint'] = checkpoint
                event['_help_authority'] = authority
        try:
            self._output_queue.put_nowait(event)
        except asyncio.QueueFull:
            self.suppressed_count += 1
            if kind != 'backend_reply':
                self._output_queue.get_nowait()
                self._output_queue.put_nowait(event)

    async def _output(self):
        while self._attached:
            event = await self._output_queue.get()
            if not self._attached:
                return
            help_checkpoint = event.pop('_help_checkpoint', None)
            help_authority = event.pop('_help_authority', None)
            input_validity = event.pop('_input_validity', None)
            def valid_help(checkpoint=help_checkpoint, authority=help_authority, input_validity=input_validity):
                try:
                    return (self._attached and (input_validity is None or input_validity())
                            and (authority is None or authority())
                            and (checkpoint is None or checkpoint == self.store.routing_checkpoint(self.scope.scope_id)))
                except Exception:
                    return False
            if not valid_help():
                self.suppressed_count += 1
                continue
            def valid_backend(task_id=event['task_id'], version=event['context_version']):
                try:
                    return (self._attached and self.coordinator._owner is self
                            and self.store.get_task(task_id, self.scope.scope_id)['context_version'] == version)
                except Exception:
                    return False
            try:
                deferred = getattr(self.emit, 'publish_deferred', None)
                guarded = getattr(self.emit, 'publish_guarded', None)
                if event['kind'] == 'backend_reply':
                    if not valid_backend():
                        self.suppressed_count += 1
                        continue
                    if callable(deferred):
                        await deferred(event, valid_backend)
                    else:
                        await self.emit(event)
                elif callable(guarded) and (help_checkpoint is not None or input_validity is not None):
                    await guarded(event, valid_help)
                else:
                    await self.emit(event)
            except Exception:
                # Output failure cannot retry/cancel a submitted business operation.
                self.suppressed_count += 1

    async def accept(self, utterance_id, text, *, voice_context=None):
        return (await self.accept_decision(utterance_id, text, voice_context=voice_context)).route

    async def accept_guarded(self, utterance_id, text, *, output_validity, voice_context=None):
        return await self.accept_decision(utterance_id, text, voice_context=voice_context,
                                          output_validity=output_validity)

    async def accept_decision(self, utterance_id, text, *, voice_context=None, output_validity=None):
        """Request-bound metadata; the legacy accept API projects its public Route."""
        bounded_identifier(utterance_id)
        if not isinstance(text, str) or not text or len(text) > 4000:
            raise StoreInvalid('invalid utterance')
        self.invalidate_grounded('input')
        async with self._accept_lock:
            if not self._attached:
                raise StoreDenied('scope detached')
            self._interrupt(preserve_deferred=True)
            question, tasks, operations, checkpoint = self.store.routing_snapshot(self.scope.scope_id)
            # Duplicate accepted input remains idempotent even after its question moved.
            prior_input = next((op for op in operations if op['utterance_id'] == utterance_id), None)
            if prior_input:
                if prior_input['text'] != text or prior_input['voice_context'] != (voice_context or {}):
                    raise StoreConflict('utterance identity conflict')
                owner = next(t for t in tasks if t['task_id'] == prior_input['task_id'])
                route = Route(prior_input['kind'], '' if prior_input['kind'] == 'new_task' else owner['task_id'],
                             owner['agent_alias'] if prior_input['kind'] == 'new_task' else '')
                return RoutingDecision(route, 'decision', 'duplicate_accepted')
            captured_agents = tuple(self.coordinator.agents)
            captured_focus = self._focus
            captured_workflow = self._context_task
            binding_valid = True
            def authority():
                return (binding_valid and self._attached and self.coordinator._owner is self
                        and tuple(self.coordinator.agents) == captured_agents
                        and self._focus == captured_focus and self._context_task == captured_workflow)

            pending_tasks = {op['task_id'] for op in self.store.pending(self.scope.scope_id)}
            for task in tasks:
                own_operations = [op for op in operations if op['task_id'] == task['task_id']]
                if own_operations:
                    latest = own_operations[-1]
                    task['retained_text'] = latest['text']
                    task.update(latest_operation_id=latest['operation_id'],
                                latest_operation_version=latest['context_version'],
                                latest_operation_state=latest['dispatch_state'])
                    # A correction may refer to the immediately answered question even
                    # after accept cleared its delivery binding. Journal evidence only;
                    # never restore open_question or infer that audio was heard.
                    if latest['kind'] == 'continue_task' and latest['context_version'] == task['context_version']:
                        events = self.store.events(task['task_id'], self.scope.scope_id)
                        accepted = next((event for event in events if event['type'] == 'utterance_accepted'
                            and event['operation_id'] == latest['operation_id']
                            and event['context_version'] == latest['context_version']), None)
                        # A previous-version settlement may arrive after this answer.
                        # Only journal evidence preceding acceptance can identify the
                        # question that was actually available when it was answered.
                        answered = accepted['payload'].get('answered_question') if accepted else None
                        if answered:
                            task.update(previous_question=answered['text'],
                                previous_question_version=answered['context_version'],
                                previous_question_id=answered['question_id'], previous_question_source=answered['source'],
                                previous_operation_id=latest['operation_id'], previous_operation_version=latest['context_version'],
                                previous_operation_state=latest['dispatch_state'])
                        prior = [event for event in events if accepted and event['sequence'] < accepted['sequence']]
                        if accepted and 'answered_question' in accepted['payload']:
                            prior = []
                        for event in reversed(prior):
                            if event['context_version'] != latest['context_version'] - 1:
                                continue
                            payload = event['payload']
                            previous = (payload['text'] if event['type'] == 'question_noted' else
                                payload['replies'][-1] if event['type'] == 'operation_settled'
                                and payload.get('outcome') == 'awaiting_input' and payload.get('replies') else '')
                            if previous:
                                task['previous_question'] = previous
                                task['previous_question_version'] = event['context_version']
                                task['previous_question_id'] = event['event_id']
                                task['previous_question_source'] = payload.get('source', event['source'])
                                task['previous_operation_id'] = latest['operation_id']
                                task['previous_operation_version'] = latest['context_version']
                                task['previous_operation_state'] = latest['dispatch_state']
                                break
                task['pending_delivery'] = task['task_id'] in pending_tasks
                if task['pending_delivery']:
                    task['open_question'] = None
            context = RoutingContext(self.scope.scope_id, tasks,
                focus_task_id=self._focus, agents=list(captured_agents),
                question_task_id=question['task_id'] if question else '',
                last_question=question['text'] if question else '',
                question_version=question['context_version'] if question else None,
                workflow_task_id=self._context_task,
                question_id=question['question_id'] if question else '',
                question_source=question['source'] if question else '',
                grounded_answers_enabled=self.coordinator.grounded_answers is not None)
            decide = getattr(self.coordinator.router, 'decide', None)
            if callable(decide):
                decision = await decide(text, context)
                if not isinstance(decision, RoutingDecision):
                    raise StoreInvalid('invalid routing decision')
                route = decision.route
            else:
                route = await self.coordinator.router.route(text, context)
                decision = RoutingDecision(route, 'clarification' if route.intent in ('uncertain', 'clarification') else 'decision', 'legacy_route')
            if decision.proposal is not None:
                p = decision.proposal
                self.coordinator.proposal_counts[(p.status, p.intent, p.meaning, p.domain)] += 1
            self.coordinator.routing_counts[(decision.disposition, decision.reason, 'policy')] += 1
            if route.intent in ('new_task', 'continue_task', 'amend_task', 'cancel_task'):
                bound_task = next((t for t in tasks if t['task_id'] == route.task_id), None)
                alias = route.agent_alias if route.intent == 'new_task' else bound_task['agent_alias'] if bound_task else ''
                agent = next((a for a in captured_agents if a.alias == alias), None)
                binding_valid = bool(agent and agent.capabilities.get(route.intent) and
                    (route.intent == 'new_task' or bound_task and
                     (bound_task['agent_id'], bound_task['registry_revision']) == (agent.agent_id, agent.revision)))
            if route.intent == 'grounded_answer':
                bound_task = next((t for t in tasks if t['task_id'] == route.task_id), None)
                agent = next((a for a in captured_agents if bound_task and a.alias == bound_task['agent_alias']), None)
                binding_valid = bool(agent and (bound_task['agent_id'], bound_task['registry_revision']) == (agent.agent_id, agent.revision))
            status_changed = (route.intent in ('status_query', 'grounded_answer') and
                checkpoint != self.store.routing_checkpoint(self.scope.scope_id))
            if not authority() or status_changed or (decision.help_source is not None and checkpoint != self.store.routing_checkpoint(self.scope.scope_id)):
                route = Route('clarification', reply='Der Gesprächskontext hat sich geändert. Bitte wiederhole deine Angabe.')
                decision = replace(decision, route=route, disposition='clarification', reason='authority_changed', help_source=None)
            try:
                if route.intent in ('uncertain', 'clarification'):
                    self._queue('local_reply', route.reply, utterance_id=utterance_id, output_validity=output_validity, decision=decision, checkpoint=checkpoint, authority=authority)
                elif route.intent == 'stop_speaking':
                    self._interrupt()
                elif route.intent == 'grounded_answer':
                    self._schedule_grounded(route, utterance_id, text, checkpoint, captured_agents, authority, output_validity)
                elif route.intent == 'status_query':
                    task = self.store.get_task(route.task_id, self.scope.scope_id)
                    observed = {}
                    for event in self.store.events(route.task_id, self.scope.scope_id):
                        if event['type'] == 'backend_observed':
                            observed[event['operation_id']] = event['payload']['text']
                    latest_reply = ''
                    # Operation order outranks late callbacks from an older operation.
                    # Within an operation, final returned replies outrank streamed progress.
                    for operation in reversed(self.store.operations(self.scope.scope_id)):
                        if operation['task_id'] != route.task_id:
                            continue
                        replies = operation['replies'] or []
                        latest_reply = replies[-1] if replies else observed.get(operation['operation_id'], '')
                        if latest_reply:
                            break
                    self._queue('local_reply', render_grounded_status(task.get('state'), latest_reply), task=task, utterance_id=utterance_id,
                                output_validity=output_validity, decision=decision, checkpoint=checkpoint, authority=authority)
                elif route.intent == 'cancel_task':
                    task = self.store.cancel_pending(route.task_id, self.scope.scope_id, utterance_id, text=text,
                                                     preconditions=checkpoint, authority=authority)
                    decision = replace(decision, durable_acceptance=True)
                    message = ('Die noch nicht übermittelte Aufgabe wurde lokal abgebrochen.' if task['state'] == 'cancelled' else
                               'Abbruch vorgemerkt. Eine bereits übermittelte Aktion kann ich nicht sicher stoppen; eine Stornierung ist nicht bestätigt.')
                    self._queue('local_reply', message, task=task, utterance_id=utterance_id, output_validity=output_validity, decision=decision, acceptance='durable_accepted')
                    self._wake.set()
                elif route.intent in ('new_task', 'amend_task', 'continue_task'):
                    if route.intent == 'new_task':
                        agent = next((a for a in self.coordinator.agents if a.alias == route.agent_alias), None)
                        if agent is None:
                            raise StoreDenied('agent unavailable')
                        operation = self.store.accept_new_task(self.scope, agent, utterance_id, text, voice_context=voice_context,
                                                               preconditions=checkpoint, authority=authority)
                        task = self.store.get_task(operation['task_id'], self.scope.scope_id)
                    else:
                        task = self.store.get_task(route.task_id, self.scope.scope_id)
                        operation = self.store.accept(task['task_id'], self.scope.scope_id, utterance_id, text,
                                                      kind=route.intent, voice_context=voice_context,
                                                      preconditions=checkpoint, authority=authority)
                    decision = replace(decision, durable_acceptance=True)
                    self._focus = task['task_id']
                    self._queue('local_reply', 'Angenommen und gespeichert. Neue Aufgaben bleiben im Legacy-Kontext in der Warteschlange, solange eine andere Aufgabe offen ist.' if route.intent == 'new_task' and self._context_task else
                                'Angenommen und zur Übermittlung vorgemerkt.', operation=operation, output_validity=output_validity, decision=decision, acceptance='durable_accepted')
                    self._wake.set()
                else:
                    raise StoreInvalid('unsupported route')
            except StoreConflict:
                # No stale route has been journaled: the transaction rolled back.
                if checkpoint == self.store.routing_checkpoint(self.scope.scope_id) and authority():
                    raise
                route = Route('clarification', reply='Die aktuelle Frage oder Aufgabe hat sich geändert. Bitte wiederhole deine Angabe.')
                decision = replace(decision, route=route, disposition='clarification', reason='authority_changed', help_source=None, durable_acceptance=False)
                self._queue('local_reply', route.reply, utterance_id=utterance_id, output_validity=output_validity, decision=decision, acceptance='durable_rejected')
            return decision

    async def detach(self):
        if not self._attached:
            return
        self.invalidate_grounded('detach')
        self._attached = False
        self.store.detach_scope(self.scope.scope_id)
        self._interrupt()
        self._detached.set()
        self._wake.set()
        if self._output_worker:
            self._output_worker.cancel()
            await asyncio.gather(self._output_worker, return_exceptions=True)

    async def wait_closed(self):
        """Wait for owned cleanup and reservation release, without owning the worker.

        Unknown business outcomes keep this pending. A timeout/cancel of this wait
        never propagates to submitted observation or owned cleanup.
        """
        await self._closed.wait()

    async def _ready(self):
        ready = asyncio.create_task(self.executor.wait_ready())
        detached = asyncio.create_task(self._detached.wait())
        try:
            await asyncio.wait([ready, detached], return_when=asyncio.FIRST_COMPLETED)
            if not self._attached:
                return False
            await ready
            return self._attached
        finally:
            for future in (ready, detached):
                if not future.done():
                    future.cancel()
            await asyncio.gather(ready, detached, return_exceptions=True)

    async def _run(self):
        try:
            while self._attached:
                await self._wake.wait()
                self._wake.clear()
                while self._attached:
                    pending = self.store.pending(self.scope.scope_id)
                    eligible = [op for op in pending if not self._context_task or op['task_id'] == self._context_task]
                    if not eligible or self.store.has_unresolved():
                        break
                    operation = eligible[0]
                    if not await self._ready():
                        break
                    # Readiness can yield to cancellation/amendment/detach; recheck durable claim.
                    try:
                        operation = self.store.dispatch(operation['operation_id'])
                    except (StoreConflict, StoreDenied):
                        continue
                    self._context_task = operation['task_id']
                    self.note_grounded_evidence_change()
                    seen = set()

                    async def on_reply(text, operation=operation, seen=seen):
                        if not isinstance(text, str) or len(text) > 4000:
                            raise StoreInvalid('invalid backend reply')
                        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                        event_id = operation['operation_id'] + ':' + digest
                        if self.store.observe(operation['operation_id'], event_id, 'backend_observed', {'text': text}):
                            self.note_grounded_evidence_change()
                            seen.add(text)
                            task = self.store.get_task(operation['task_id'], self.scope.scope_id)
                            if task['context_version'] == operation['context_version']:
                                if self._attached and '?' in text:
                                    self.store.note_question(operation['task_id'], self.scope.scope_id, text,
                                        source='backend', context_version=operation['context_version'])
                                self._queue('backend_reply', text, operation=operation)

                    try:
                        self._executing = True
                        replies = await self.executor.turn(operation, on_reply)
                        task = self.store.settle(operation['operation_id'], replies=replies)
                        self.note_grounded_evidence_change()
                        for reply in replies:
                            if reply not in seen and task['context_version'] == operation['context_version']:
                                seen.add(reply)
                                self._queue('backend_reply', reply, operation=operation)
                    except asyncio.CancelledError:
                        self.store.mark_unknown(operation['operation_id'], 'worker_interrupted')
                        self.note_grounded_evidence_change()
                        raise
                    except Exception:
                        self.store.mark_unknown(operation['operation_id'], 'executor_uncertain')
                        self.note_grounded_evidence_change()
                        self._queue('error', 'Das Ergebnis ist unklar. Die Anfrage wird nicht automatisch wiederholt.', operation=operation)
                        break
                    finally:
                        self._executing = False
        except Exception:
            self._queue('error', 'Die Verbindung ist nicht bereit. Vorgemerkte Anfragen werden nicht automatisch übermittelt.')
            # Keep the slot and queued journal intact until the caller detaches.
            # Retrying readiness here could turn a transport failure into a write retry.
            await self._detached.wait()
        finally:
            # This worker, never the native call task, owns cleanup after observation.
            try:
                await self.executor.close()
                self._cleanup_acknowledged = True
            except Exception:
                self._cleanup_acknowledged = False
            if self._cleanup_acknowledged and not self.store.has_unresolved():
                self.coordinator._owner = None
                self._closed.set()
