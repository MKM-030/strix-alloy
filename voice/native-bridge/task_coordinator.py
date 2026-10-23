"""Process-owned legacy business observation, independent of native/audio tasks.

One attachment reserves one legacy context until submitted observation and owned
cleanup finish. The passed emitter must enqueue promptly (OutputArbiter.publish
does); callbacks are journaled before a separate output worker invokes it.
"""

import asyncio
import hashlib
import inspect

from business_tasks import Scope, StoreConflict, StoreDenied, StoreInvalid, bounded_identifier
from conversation_router import RoutingContext
from servicenow_executor import LegacyVAExecutor


class TaskCoordinator:
    def __init__(self, store, router, agents, executor_factory, *, mode='legacy'):
        if mode not in ('legacy', 'full'):
            raise ValueError('invalid coordinator mode')
        self.store, self.router = store, router
        self.agents = list(agents)
        self.executor_factory, self.mode = executor_factory, mode
        self._owner = None
        self._shutdown = False

    @property
    def available(self):
        """Synchronous admission hint; attach still performs the authoritative check."""
        return (self.mode == 'legacy' and not self._shutdown and self._owner is None
                and not self.store.has_unresolved())

    async def attach(self, scope: Scope, emit, *, executor=None):
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
        owner = self._owner
        if owner is None:
            return {'pending': 0, 'unresolved': self.store.has_unresolved()}
        await owner.detach()
        done, pending = await asyncio.wait([owner._worker], timeout=max(0, timeout_seconds))
        return {'pending': len(pending), 'unresolved': self.store.has_unresolved(),
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

    def _interrupt(self):
        owner = getattr(self.emit, '__self__', None)
        if owner is not None and callable(getattr(owner, 'interrupt', None)):
            owner.interrupt()
        while not self._output_queue.empty():
            self._output_queue.get_nowait()
            self.suppressed_count += 1

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
            return task_id

    def _queue(self, kind, text, *, operation=None, task=None, utterance_id=''):
        if not self._attached:
            return
        operation, task = operation or {}, task or {}
        event = dict(kind=kind, task_id=task.get('task_id', operation.get('task_id', '')),
            operation_id=operation.get('operation_id', ''),
            utterance_id=utterance_id or operation.get('utterance_id', ''),
            context_version=task.get('context_version', operation.get('context_version', 0)),
            text=text, priority=10 if kind == 'backend_reply' else 0)
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
            if event['kind'] == 'backend_reply':
                task = self.store.get_task(event['task_id'], self.scope.scope_id)
                if task['context_version'] != event['context_version']:
                    self.suppressed_count += 1
                    continue
            try:
                await self.emit(event)
            except Exception:
                # Output failure cannot retry/cancel a submitted business operation.
                self.suppressed_count += 1

    async def accept(self, utterance_id, text, *, voice_context=None):
        bounded_identifier(utterance_id)
        if not isinstance(text, str) or not text or len(text) > 4000:
            raise StoreInvalid('invalid utterance')
        async with self._accept_lock:
            if not self._attached:
                raise StoreDenied('scope detached')
            self._interrupt()
            question = self.store.question(self.scope.scope_id)
            tasks = self.store.list_tasks(self.scope.scope_id)
            operations = self.store.operations(self.scope.scope_id)
            pending_tasks = {op['task_id'] for op in self.store.pending(self.scope.scope_id)}
            for task in tasks:
                own_operations = [op for op in operations if op['task_id'] == task['task_id']]
                if own_operations:
                    latest = own_operations[-1]
                    task['retained_text'] = latest['text']
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
                        prior = [event for event in events if accepted and event['sequence'] < accepted['sequence']]
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
                                break
                task['pending_delivery'] = task['task_id'] in pending_tasks
                if task['pending_delivery']:
                    task['open_question'] = None
            context = RoutingContext(self.scope.scope_id, tasks,
                focus_task_id=self._focus, agents=self.coordinator.agents,
                question_task_id=question['task_id'] if question else '',
                last_question=question['text'] if question else '',
                question_version=question['context_version'] if question else None,
                workflow_task_id=self._context_task)
            route = await self.coordinator.router.route(text, context)
            if not self._attached:
                raise StoreDenied('scope detached')
            if route.intent in ('uncertain', 'clarification'):
                self._queue('local_reply', route.reply, utterance_id=utterance_id)
            elif route.intent == 'stop_speaking':
                pass
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
                suffix = (' Letzte Antwort: ' + latest_reply) if latest_reply else ''
                self._queue('local_reply', ('Status: ' + task['state'] + '.' + suffix)[:4000], task=task, utterance_id=utterance_id)
            elif route.intent == 'cancel_task':
                task = self.store.cancel_pending(route.task_id, self.scope.scope_id, utterance_id, text=text)
                message = ('Die noch nicht übermittelte Aufgabe wurde lokal abgebrochen.' if task['state'] == 'cancelled' else
                           'Abbruch vorgemerkt. Eine bereits übermittelte Aktion kann ich nicht sicher stoppen; eine Stornierung ist nicht bestätigt.')
                self._queue('local_reply', message, task=task, utterance_id=utterance_id)
                self._wake.set()
            elif route.intent in ('new_task', 'amend_task', 'continue_task'):
                if route.intent == 'new_task':
                    agent = next((a for a in self.coordinator.agents if a.alias == route.agent_alias), None)
                    if agent is None:
                        raise StoreDenied('agent unavailable')
                    operation = self.store.accept_new_task(self.scope, agent, utterance_id, text, voice_context=voice_context)
                    task = self.store.get_task(operation['task_id'], self.scope.scope_id)
                else:
                    task = self.store.get_task(route.task_id, self.scope.scope_id)
                    if route.intent == 'amend_task':
                        self._queue('local_reply', 'Eine bereits laufende Aktion kann ich nicht sicher ändern. Die Änderung wird zur späteren Übermittlung vorgemerkt.', task=task, utterance_id=utterance_id)
                    operation = self.store.accept(task['task_id'], self.scope.scope_id, utterance_id, text,
                                                  kind=route.intent, voice_context=voice_context)
                self._focus = task['task_id']
                self._queue('local_reply', 'Angenommen und gespeichert. Neue Aufgaben bleiben im Legacy-Kontext in der Warteschlange, solange eine andere Aufgabe offen ist.' if route.intent == 'new_task' and self._context_task else
                            'Angenommen und zur Übermittlung vorgemerkt.', operation=operation)
                self._wake.set()
            else:
                raise StoreInvalid('unsupported route')
            return route

    async def detach(self):
        if not self._attached:
            return
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
                    seen = set()

                    async def on_reply(text, operation=operation, seen=seen):
                        if not isinstance(text, str) or len(text) > 4000:
                            raise StoreInvalid('invalid backend reply')
                        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                        event_id = operation['operation_id'] + ':' + digest
                        if self.store.observe(operation['operation_id'], event_id, 'backend_observed', {'text': text}):
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
                        for reply in replies:
                            if reply not in seen and task['context_version'] == operation['context_version']:
                                seen.add(reply)
                                self._queue('backend_reply', reply, operation=operation)
                    except asyncio.CancelledError:
                        self.store.mark_unknown(operation['operation_id'], 'worker_interrupted')
                        raise
                    except Exception:
                        self.store.mark_unknown(operation['operation_id'], 'executor_uncertain')
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
