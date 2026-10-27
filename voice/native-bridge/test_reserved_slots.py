"""Controlled ephemeral HTTP/OS boundaries, never a configured runtime port."""
import asyncio
import copy
import json
import tempfile
import threading
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer
import conversation_admission as admission
from conversation_router import LoopbackConversationModel, RoutingContext
from test_token_admission import count_body, choice_body, TEXT


def slots():
    return [{'id': i, 'n_ctx': 4096, 'id_task': -1, 'is_processing': False} for i in (0, 1)]


class Host:
    def __init__(self):
        self.facts = {'pid': 17, 'created': 123.125, 'exe': 'synthetic-server.exe', 'argv': ['synthetic-server.exe', '--slots']}
        self.bound = [{'pid': 17, 'ip': '127.0.0.1'}]

    def process(self, pid): return copy.deepcopy(self.facts)
    def listeners(self, port): return copy.deepcopy(self.bound)


class Server:
    def __init__(self):
        self.state = slots()
        self.calls = []
        self.on_get = None
        self.on_count = None
        self.on_infer = None
        self.inferred = asyncio.Event()

    async def handle(self, request):
        raw = await request.read()
        self.calls.append((request.method, request.path, raw, request.headers.get('Authorization')))
        if request.headers.get('Authorization') != 'Bearer synthetic-token':
            return web.Response(status=401)
        if request.method == 'GET':
            if self.on_get: return await self.on_get(request)
            return web.json_response(self.state)
        if request.path.endswith('input_tokens'):
            if self.on_count: return await self.on_count(request)
            return web.Response(body=count_body(100), content_type='application/json')
        self.inferred.set()
        if self.on_infer: return await self.on_infer(request)
        return web.Response(body=choice_body(100), content_type='application/json')


@asynccontextmanager
async def reserved(timeout=1, *, configure=None, initialize=True):
    fixture = Server()
    if configure: configure(fixture)
    app = web.Application()
    app.router.add_route('*', '/{tail:.*}', fixture.handle)
    async with TestServer(app) as server:
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / 'token'
            token.write_text('synthetic-token')
            model = LoopbackConversationModel(None, str(server.make_url('/v1/chat/completions')), 'synthetic', token, timeout)
            host = Host()
            owner = None
            if initialize:
                owner = admission.SharedSlotOwner(host, 17, 123.125, model.url, model.model, token)
                await owner.initialize(time.monotonic() + 1)
                model.slot_owner = owner
            try:
                yield fixture, model, owner, host
            finally:
                # Cleanup is ordinary cancellation of the gate's bounded tasks.
                if owner:
                    for task in tuple(owner.cleanup_tasks): task.cancel()
                    await asyncio.gather(*tuple(owner.cleanup_tasks), return_exceptions=True)


async def admitted(model, role='planner', request=None, **changes):
    budget = admission.PLANNER_BUDGET if role == 'planner' else admission.ROUTE_BUDGET
    request = request or admission.AdmissionRequest(model.timeout_seconds, budget=budget)
    payload = {'model': 'synthetic', 'max_tokens': budget.completion_tokens, 'id_slot': 1 if role == 'planner' else 0}
    payload.update(changes)
    return await admission.run_admitted_chat(request, host=model.host, port=model.port, token_file=model.token_file,
        prepare=lambda: admission.PreparedChat(json.dumps(payload).encode(), b'{}', None),
        decode_content=lambda value, _: value, observe=lambda _: None, slot_owner=model.slot_owner, role=role)


@asynccontextmanager
async def grounded_transaction(replies):
    """Migrate existing planner fixtures to the real persistent owner boundary."""
    async with reserved() as (server, model, owner, _):
        async def response(request):
            index = 0 if request.path.endswith('input_tokens') else 1
            return web.Response(body=replies[index].split(b'\r\n\r\n', 1)[1])
        server.on_count = server.on_infer = response
        class Capture:
            @property
            def requests(self):
                return [(path, body, b'') for method, path, body, _ in server.calls if method == 'POST']
        yield Capture(), model


class ReservedSlots(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Python 3.12/Windows monotonic has a ~15ms tick. Use its monotonic
        # high-resolution clock for deterministic 20ms fake observer windows;
        # this is no assertion about a real server's cancellation latency.
        clock = patch.object(time, 'monotonic', time.perf_counter)
        clock.start()
        self.addCleanup(clock.stop)
        asyncio.get_running_loop()._clock_resolution = time.get_clock_info('perf_counter').resolution

    async def test_shared_owner_exists_and_startup_is_once(self):
        self.assertTrue(hasattr(admission, 'SharedSlotOwner'), 'persistent role ownership is absent')
        async with reserved() as (server, model, owner, host):
            await owner.initialize(time.monotonic() + 1)
            self.assertEqual(len(server.calls), 1)
            await model.classify(TEXT, RoutingContext('scope', []))
            self.assertEqual([c[:2] for c in server.calls], [('GET', '/slots'), ('POST', admission.COUNT_PATH),
                ('POST', admission.INFERENCE_PATH), ('GET', '/slots')])
            self.assertEqual(server.calls[1][2], server.calls[2][2])
            self.assertEqual(json.loads(server.calls[1][2])['id_slot'], 0)
            await admitted(model)
            self.assertEqual(json.loads(server.calls[4][2])['id_slot'], 1)
            self.assertEqual(server.calls[4][2], server.calls[5][2])

    async def test_grounded_rejects_missing_owner(self):
        from grounded_conversation import GroundedAnswers
        model = LoopbackConversationModel(None, 'http://127.0.0.1:8899/v1/chat/completions', 'synthetic', '')
        with self.assertRaisesRegex(ValueError, 'owner'):
            GroundedAnswers(model)

    async def test_invalid_wire_role_rejected_without_count(self):
        async with reserved() as (server, model, owner, _):
            for value in (None, True, -1, 0, 2, '1'):
                with self.subTest(value=value), self.assertRaises(admission.AdmissionUnavailable):
                    await admitted(model, id_slot=value)
            self.assertEqual(len(server.calls), 1)

    async def test_full_response_needs_fresh_idle_and_busy_does_not_poll(self):
        async with reserved() as (server, model, owner, _):
            server.state[1].update(is_processing=True, id_task=8)
            await admitted(model)
            self.assertEqual(owner.snapshot()['roles']['planner']['release_basis'], '')
            with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
            self.assertEqual(len(server.calls), 4)

    async def test_cancelled_idle_first_latches_only_planner(self):
        async with reserved() as (server, model, owner, _):
            hold = asyncio.Event()
            async def infer(request):
                if json.loads(await request.read())['id_slot'] == 1:
                    await hold.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            task = asyncio.create_task(admitted(model, request=req))
            await server.inferred.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            # First 20ms probe may time out on Windows scheduler granularity;
            # the permitted second observation is still idle with no witness.
            await asyncio.sleep(1.4)
            self.assertEqual(owner.snapshot()['roles']['planner']['unresolved_reason'], 'no_terminal_or_active_witness', owner.snapshot()['probes'])
            await model.classify(TEXT, RoutingContext('scope', []))
            with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
            hold.set()
            self.assertTrue(req.snapshot().connection_closed)
            self.assertEqual(req.snapshot().inference_attempts, 1)

    async def test_cancelled_count_is_sealed_before_late_parse_can_infer(self):
        async with reserved() as (server, model, owner, _):
            entered, release = threading.Event(), threading.Event()
            strict = admission._strict_json
            def held(raw, cap):
                value = strict(raw, cap)
                if value.get('object') == 'response.input_tokens':
                    entered.set()
                    release.wait(1)
                return value
            with patch.object(admission, '_strict_json', held):
                req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
                task = asyncio.create_task(admitted(model, request=req))
                self.assertTrue(await asyncio.to_thread(entered.wait, .5))
                req.retire('cancelled')
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
                release.set()
                await asyncio.sleep(.03)
            self.assertEqual(req.snapshot().inference_attempts, 0)
            self.assertEqual(owner.snapshot()['roles']['planner']['release_basis'], 'sealed_zero_inference')
            await admitted(model)
            self.assertEqual(sum(c[1] == admission.INFERENCE_PATH for c in server.calls), 1)

    async def test_current_identity_drift_blocks_both_roles(self):
        for drift in ('created', 'exe', 'argv', 'listener', 'token'):
            async with reserved() as (server, model, owner, host):
                if drift == 'listener': host.bound = [{'pid': 17, 'ip': '0.0.0.0'}]
                elif drift == 'token': model.token_file.write_text('other-token')
                elif drift == 'created': host.facts['created'] += .000001
                elif drift == 'argv': host.facts['argv'].append('--changed')
                else: host.facts['exe'] = 'other.exe'
                with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
                with self.assertRaises(admission.AdmissionUnavailable): await model.classify(TEXT, RoutingContext('scope', []))
                self.assertEqual(len(server.calls), 1)

    async def test_original_deadline_includes_slow_guard(self):
        async with reserved(.06) as (server, model, owner, host):
            original = host.process
            def slow(pid):
                time.sleep(.1)
                return original(pid)
            host.process = slow
            started = time.monotonic()
            with self.assertRaises(TimeoutError): await admitted(model)
            self.assertLess(time.monotonic() - started, .1)
            await asyncio.sleep(.15)
            self.assertEqual(len(server.calls), 1)

    async def test_model_owner_cannot_be_cleared_or_replaced_between_fixtures(self):
        async with reserved() as (_, model, owner, _):
            with self.assertRaises(ValueError): model.slot_owner = None
            with self.assertRaises(ValueError): model.slot_owner = object()
            self.assertIs(model.slot_owner, owner)

    async def test_startup_rejects_wrong_geometry_types_busy_auth_and_duplicate_json(self):
        bad = [[], slots()[:1], [slots()[0], slots()[0]],
               [dict(slots()[0], id=True), slots()[1]], [dict(slots()[0], n_ctx=8192), slots()[1]],
               [dict(slots()[0], is_processing=True, id_task=7), slots()[1]],
               [dict(slots()[0], id_task=None), slots()[1]], [dict(slots()[0], is_processing=0), slots()[1]]]
        for state in bad:
            with self.subTest(state=state), self.assertRaises(admission.AdmissionUnavailable):
                async with reserved(configure=lambda server: setattr(server, 'state', state)): pass
        for body, status in ((b'[{"id":0,"id":0}]', 200), (b'x'*8193, 200), (b'[]', 401)):
            async def bad_get(request): return web.Response(body=body, status=status)
            with self.subTest(status=status, size=len(body)), self.assertRaises((ValueError, admission.AdmissionUnavailable)):
                async with reserved(configure=lambda server: setattr(server, 'on_get', bad_get)): pass

    async def test_nonstream_single_completion_shape_and_absent_slot_reject(self):
        async with reserved() as (server, model, owner, _):
            for data in ({'n': 2}, {'n': True}, {'stream': True}, {'stream': 0}, {'resume_id': 3}):
                with self.subTest(data=data), self.assertRaises(admission.AdmissionUnavailable):
                    await admitted(model, **data)
            req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            with self.assertRaises(admission.AdmissionUnavailable):
                await admission.run_admitted_chat(req, host=model.host, port=model.port, token_file=model.token_file,
                    prepare=lambda: admission.PreparedChat(b'{"model":"synthetic","max_tokens":128}', b'{}', None),
                    decode_content=lambda *args: None, observe=lambda _: None, slot_owner=owner, role='planner')
            self.assertEqual(len(server.calls), 1)

    async def test_virgin_idle_slots_can_omit_task_id_but_active_cannot(self):
        virgin = [{'id': i, 'n_ctx': 4096, 'is_processing': False} for i in (0, 1)]
        async with reserved(configure=lambda server: setattr(server, 'state', virgin)) as (_, model, owner, _):
            await admitted(model)
            self.assertEqual(owner.snapshot()['roles']['planner']['release_basis'], 'full_terminal_then_idle')
            self.assertIsNone(owner.snapshot()['roles']['planner']['active_task'])
        virgin[0]['is_processing'] = True
        with self.assertRaises(admission.AdmissionUnavailable):
            async with reserved(configure=lambda server: setattr(server, 'state', virgin)): pass

    async def test_normal_terminal_get_keeps_original_deadline_and_does_not_poll(self):
        async with reserved(.12) as (server, model, owner, _):
            async def slow_get(request):
                await asyncio.sleep(.2)
                return web.json_response(slots())
            server.on_get = slow_get
            started = time.monotonic()
            with self.assertRaises(TimeoutError): await admitted(model)
            self.assertLess(time.monotonic() - started, .2)
            self.assertIsNone(owner.snapshot()['roles']['planner']['released_at'])
            self.assertEqual(owner.snapshot()['roles']['planner']['slot_get_attempts'], 1)

    async def test_full_response_while_get_held_has_no_release_authority(self):
        async with reserved() as (server, model, owner, _):
            entered, release = asyncio.Event(), asyncio.Event()
            async def held_get(request):
                entered.set()
                await release.wait()
                return web.json_response(slots())
            server.on_get = held_get
            request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            task = asyncio.create_task(admitted(model, request=request))
            await entered.wait()
            self.assertIsNotNone(request.snapshot().full_terminal_at)
            self.assertIsNone(request.snapshot().released_at)
            release.set()
            await task
            self.assertEqual(request.snapshot().release_basis, 'full_terminal_then_idle')

    async def test_busy_idle_retained_id_releases_only_associated_target(self):
        async with reserved() as (_, model, owner, _):
            request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            await owner.acquire(request, 'planner')
            request.update(count_valid=True, input_tokens=100)
            request.dispatch('inference', 10)
            owner._apply_slots(request, {0: (True, 50), 1: (True, 9)}, time.monotonic())
            self.assertEqual(request.snapshot().active_task, 9)
            owner._apply_slots(request, {0: (True, 50), 1: (False, 9)}, time.monotonic())
            self.assertEqual(request.snapshot().release_basis, 'active_then_idle')
            self.assertIsNone(owner.snapshot()['roles']['classifier'])

    async def test_unknown_changed_target_task_cannot_be_released_by_idle(self):
        async with reserved() as (_, model, owner, _):
            request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            await owner.acquire(request, 'planner')
            request.update(count_valid=True, input_tokens=100)
            request.dispatch('inference', 10)
            owner._apply_slots(request, {0: (False, -1), 1: (True, 9)}, time.monotonic())
            owner._apply_slots(request, {0: (False, -1), 1: (True, 10)}, time.monotonic())
            owner._apply_slots(request, {0: (False, -1), 1: (False, 10)}, time.monotonic())
            self.assertEqual(request.snapshot().unresolved_reason, 'unexpected_task')
            self.assertIsNone(request.snapshot().released_at)

    async def test_retire_dispatch_race_is_atomic_and_cannot_reuse_attempted_role(self):
        async with reserved() as (_, model, owner, _):
            for index in range(30):
                # Reuse one owner; end on the first race won by dispatch because
                # that uncertainty must intentionally latch the role.
                request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
                await owner.acquire(request, 'planner')
                request.update(count_valid=True, input_tokens=100)
                barrier = threading.Barrier(2)
                def dispatch():
                    barrier.wait()
                    try: request.dispatch('inference', 10)
                    except (TimeoutError, admission.AdmissionUnavailable): pass
                def retire():
                    barrier.wait()
                    request.retire('cancelled')
                await asyncio.gather(asyncio.to_thread(dispatch), asyncio.to_thread(retire))
                owner.finish(request)
                snap = request.snapshot()
                if snap.inference_attempts:
                    self.assertEqual(snap.release_basis, '')
                    with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
                    break
                self.assertEqual(snap.release_basis, 'sealed_zero_inference')
                with self.assertRaises(TimeoutError): request.dispatch('inference', 10)

    async def test_current_guard_detects_drift_after_get_and_before_inference(self):
        async with reserved() as (server, model, owner, host):
            async def changed_get(request):
                host.facts['argv'].append('--foreign')
                return web.json_response(slots())
            server.on_get = changed_get
            with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
            self.assertTrue(owner.snapshot()['invalid'])
            self.assertIsNone(owner.snapshot()['roles']['planner']['released_at'])
            with self.assertRaises(admission.AdmissionUnavailable): await model.classify(TEXT, RoutingContext('scope', []))
        async with reserved() as (server, model, owner, host):
            async def changed_count(request):
                host.facts['created'] += .000001
                return web.Response(body=count_body(100))
            server.on_count = changed_count
            with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
            self.assertFalse(any(c[1] == admission.INFERENCE_PATH for c in server.calls))

    async def test_one_waiter_per_role_and_planner_local_wait_is_bounded(self):
        async with reserved() as (server, model, owner, _):
            hold = asyncio.Event()
            async def infer(request):
                await hold.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            first = asyncio.create_task(admitted(model))
            await server.inferred.wait()
            second = asyncio.create_task(admitted(model))
            while not owner.waiters['planner']: await asyncio.sleep(.001)
            started = time.monotonic()
            with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
            self.assertLess(time.monotonic()-started, .08)
            with self.assertRaises(admission.AdmissionUnavailable): await second
            self.assertEqual(sum(c[1] == admission.INFERENCE_PATH for c in server.calls), 1)
            hold.set()
            await first

    async def test_route_own_ambiguous_timeout_latches_classifier_only(self):
        async with reserved(.1) as (server, model, owner, _):
            hold = asyncio.Event()
            async def infer(request):
                if json.loads(await request.read())['id_slot'] == 0: await hold.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            with self.assertRaises(TimeoutError): await model.classify(TEXT, RoutingContext('scope', []))
            await admitted(model)
            with self.assertRaises(admission.AdmissionUnavailable): await model.classify(TEXT, RoutingContext('scope', []))
            self.assertIsNone(owner.snapshot()['roles']['classifier']['released_at'])
            hold.set()

    async def test_native_startup_retains_proof_and_wires_same_owner_into_both_callers(self):
        import sys
        from types import SimpleNamespace
        from aiohttp.test_utils import TestClient
        import native_bridge
        from responsive_config import ResponsiveConfig
        from task_coordinator import TaskCoordinator
        from business_tasks import Scope
        from grounded_conversation import GroundedJob, make_request
        from test_unified_routing_policy import AGENT
        async with reserved(initialize=False) as (server, model, unused, host):
            # Native alone constructs/initializes the shared session owner.
            module = native_bridge._grounded_readiness_module()
            expected_pair = []
            async def provider(expected):
                expected_pair.append(expected.context_parallel)
                return module.GroundedReadinessProof(expected, 'a'*64, 17, 123.125,
                    tuple((label, 'b'*64) for label in ('admission', 'grounding', 'cancellation', 'coexistence')))
            made = []
            def coordinator(*args, **kwargs):
                instance = TaskCoordinator(*args, **kwargs)
                made.append(instance)
                return instance
            profile = ResponsiveConfig(enabled=True, mode='assist', store_file=str(model.token_file.parent/'tasks.db'),
                model_url=model.url, model_name='synthetic', model_token_file=str(model.token_file),
                grounded_answers_enabled=True, agents=(AGENT,))
            with patch.dict(sys.modules, {'conversation_runtime': SimpleNamespace(WindowsHost=lambda: host)}), \
                    patch('task_coordinator.TaskCoordinator', coordinator):
                app = native_bridge.create_app(native_bridge.Config(instance_name='fiction', voice_service_id='assistant',
                    private_responsive=profile), grounded_readiness_provider=provider)
                async with TestClient(TestServer(app)):
                    real = made[0]
                    self.assertIs(real.router.model, real.grounded_answers.model)
                    native_owner = real.router.model.slot_owner
                    self.assertTrue(native_owner.initialized)
                    self.assertEqual(expected_pair, [(8192, 2)])
                    await real.router.model.classify(TEXT, RoutingContext('scope', []))
                    scope = Scope('scope', 'call', 1, 'instance', 'assistant')
                    task = real.store.create_task(scope, AGENT, 'Synthetic')
                    request = make_request(real.store.grounded_snapshot('scope', task['task_id']),
                        utterance_id='synthetic', text='Was wurde gespeichert?', checkpoint=real.store.routing_checkpoint('scope'),
                        registry=(AGENT,), focus='', workflow='', origin_validity=lambda: True, generation=0)
                    job = GroundedJob(request)
                    real.grounded_answers.bind_job(job)
                    async def planner(request):
                        return web.Response(body=choice_body(100, choices=[{'finish_reason': 'stop', 'message': {
                            'content': '{"outcome":"answer","form":"state","evidence":["e1"],"gap":"none"}'}}]))
                    server.on_infer = planner
                    await real.grounded_answers.plan(request)
                    real.grounded_answers.release_job(job)
                    self.assertIs(real.router.model.slot_owner, native_owner)
                    posts = [c for c in server.calls if c[0] == 'POST']
                    self.assertEqual([json.loads(c[2])['id_slot'] for c in posts], [0, 0, 1, 1])
                    self.assertEqual(native_owner.snapshot()['all_http_attempts'], 7)

    async def test_delayed_server_submission_idle_first_then_busy_never_borrows_role(self):
        async with reserved() as (server, model, owner, _):
            hold = asyncio.Event()
            async def infer(request):
                if json.loads(await request.read())['id_slot'] == 1: await hold.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            real_exchange = admission.exchange
            real_connect = admission.AdmissionRequest.connect
            real_start_worker = owner._start_worker
            class ProbeSocket:
                def shutdown(self, *_): pass
                def close(self): pass
            def deterministic_connect(request, host, port):
                if not request.snapshot().role:
                    request.check()
                    with request.lock:
                        request.socket = ProbeSocket()
                    return request.socket
                return real_connect(request, host, port)
            def deterministic_probe(request, owned, frame, **kwargs):
                # Controlled transport response eliminates scheduler dependence
                # from the cancellation state proof. Route/count/inference use
                # real ephemeral HTTP; separate tests cover GET framing/auth.
                if kwargs.get('method') == 'GET':
                    request.check()
                    return json.dumps(server.state).encode(), False
                return real_exchange(request, owned, frame, **kwargs)
            def deterministic_worker(role, action):
                if action.__name__ != 'observe':
                    return real_start_worker(role, action)
                # This observer uses only the in-memory response above. Keep
                # ownership and all real probe checks, without OS executor
                # scheduling consuming its intentionally narrow 20ms window.
                marker = (role, object())
                with owner.lock:
                    owner._worker_owners.add(marker)
                async def run():
                    try:
                        return action()
                    finally:
                        with owner.lock:
                            owner._worker_owners.discard(marker)
                return asyncio.create_task(run())
            with patch.object(admission, 'exchange', deterministic_probe), \
                    patch.object(admission.AdmissionRequest, 'connect', deterministic_connect), \
                    patch.object(owner, '_start_worker', deterministic_worker):
                req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
                pending = asyncio.create_task(admitted(model, request=req))
                await server.inferred.wait()
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                await asyncio.sleep(.15)
                first = req.snapshot()
                self.assertEqual(first.unresolved_reason, 'no_terminal_or_active_witness')
                self.assertIsNone(first.active_task)
                # Server inserts the already-received request only after idle.
                server.state[1].update(is_processing=True, id_task=71)
                await model.classify(TEXT, RoutingContext('scope', []))
                await asyncio.sleep(1.2)
                self.assertEqual(req.snapshot().slot_get_attempts, 2)
                self.assertEqual(req.snapshot().active_task, 71)
                server.state[1].update(is_processing=False)
                for _ in range(3):
                    with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
                await asyncio.sleep(.15)
                self.assertEqual(req.snapshot().slot_get_attempts, 2)
                self.assertIsNone(req.snapshot().released_at)
                probes = [p for p in owner.snapshot()['probes'] if p['lease_id'] == first.lease_id]
                self.assertGreaterEqual(probes[0]['sent_at'], first.cancelled_at + .08)
                self.assertLessEqual(probes[0]['deadline'], first.cancelled_at + .100001)
                self.assertGreaterEqual(probes[1]['sent_at'], probes[0]['terminal_at'] + 1.1)
                self.assertEqual(owner.snapshot()['total_attempts'], 4)
                self.assertEqual(owner.snapshot()['all_http_attempts'], 8)
                hold.set()

    async def test_outstanding_planner_observer_never_blocks_classifier_or_overlaps_followup(self):
        async with reserved() as (server, model, owner, _):
            hold = asyncio.Event()
            async def infer(request):
                if json.loads(await request.read())['id_slot'] == 1: await hold.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            started, release = threading.Event(), threading.Event()
            real_exchange = admission.exchange
            def held_probe(request, owned, frame, **kwargs):
                if kwargs.get('method') == 'GET' and not started.is_set():
                    started.set()
                    release.wait(2)
                return real_exchange(request, owned, frame, **kwargs)
            with patch.object(admission, 'exchange', held_probe):
                req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
                pending = asyncio.create_task(admitted(model, request=req))
                await server.inferred.wait()
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError): await pending
                self.assertTrue(await asyncio.to_thread(started.wait, .5))
                await model.classify(TEXT, RoutingContext('scope', []))
                await asyncio.sleep(1.2)
                probes = [p for p in owner.snapshot()['probes'] if p['role'] == 'planner']
                self.assertEqual(len(probes), 1)
                self.assertIsNone(probes[0]['terminal_at'])
                self.assertTrue(probes[0]['connection_closed'], 'timeout must close observer while worker remains outstanding')
                release.set()
                hold.set()
                await asyncio.sleep(.04)
            self.assertEqual(req.snapshot().slot_get_attempts, 1)

    async def test_get_framing_authentication_and_startup_attempt_cannot_retry(self):
        from test_token_admission import Peer, framed
        bodies = [b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n[]',
                  b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n[]',
                  b'HTTP/1.1 200 OK\r\n\r\n[]']
        for body in bodies:
            peer = Peer([body])
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    token = Path(tmp)/'token'
                    token.write_text('synthetic-token')
                    owner = admission.SharedSlotOwner(Host(), 17, 123.125,
                        f'http://127.0.0.1:{peer.port}/v1/chat/completions', 'synthetic', token)
                    with self.assertRaises((TimeoutError, admission.AdmissionUnavailable)):
                        await owner.initialize(time.monotonic()+.08)
                    with self.assertRaises(admission.AdmissionUnavailable):
                        await owner.initialize(time.monotonic()+1)
                    self.assertEqual(owner.snapshot()['slot_get_attempts'], 1)
                    self.assertTrue(peer.requests[0][2].startswith(b'GET /slots '))
                    self.assertIn(b'Authorization: Bearer synthetic-token', peer.requests[0][2])
            finally: await peer.finish()

    async def test_cumulative_timestamps_and_history_survive_next_successful_call(self):
        async with reserved() as (_, model, owner, _):
            req = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            await admitted(model, request=req)
            await admitted(model)
            receipt = owner.snapshot()['history'][0]
            self.assertFalse(receipt['worker_outstanding'])
            self.assertLessEqual(receipt['count_dispatched_at'], receipt['count_terminal_at'])
            self.assertLessEqual(receipt['count_terminal_at'], receipt['inference_dispatched_at'])
            self.assertLessEqual(receipt['inference_dispatched_at'], receipt['full_terminal_at'])
            self.assertLessEqual(receipt['full_terminal_at'], receipt['released_at'])
            self.assertEqual(owner.snapshot()['total_attempts'], 4)
            self.assertEqual(owner.snapshot()['all_http_attempts'], 7)

    async def test_waiting_successor_refreshes_identity_before_acquisition(self):
        async with reserved() as (_, model, owner, host):
            first = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            await owner.acquire(first, 'planner')
            second = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            pending = asyncio.create_task(owner.acquire(second, 'planner'))
            while not owner.waiters['planner']: await asyncio.sleep(.001)
            first.retire('cancelled')
            owner.finish(first)
            host.facts['argv'].append('--changed')
            with self.assertRaises(admission.AdmissionUnavailable): await pending
            self.assertIsNone(second.snapshot().acquired_at)

    async def test_role_cannot_change_budget_or_rebind_existing_request(self):
        async with reserved() as (_, model, owner, _):
            request = admission.AdmissionRequest(1)
            with self.assertRaises(admission.AdmissionUnavailable): await owner.acquire(request, 'planner')
            await owner.acquire(request, 'classifier')
            owner.finish(request)
            with self.assertRaises(admission.AdmissionUnavailable): await owner.acquire(request, 'classifier')

    async def test_unoffered_route_choice_is_not_full_terminal_release_evidence(self):
        from route_proposal import ProposalError
        async with reserved() as (server, model, owner, _):
            async def unoffered(request):
                return web.Response(body=choice_body(100, choices=[{'finish_reason': 'stop',
                    'message': {'content': '{"choice":"foreign-option"}'}}]))
            server.on_infer = unoffered
            with self.assertRaises(ProposalError): await model.classify(TEXT, RoutingContext('scope', []))
            receipt = owner.snapshot()['roles']['classifier']
            self.assertIsNone(receipt['full_terminal_at'])
            self.assertIsNone(receipt['released_at'])
            self.assertEqual(receipt['slot_get_attempts'], 0)

    async def test_publication_revoke_drains_only_attempted_live_planner_until_original_deadline(self):
        self.assertTrue(hasattr(admission.AdmissionRequest, 'revoke_for_drain'), 'publication revoke is coupled to hard abort')
        async with reserved(.12) as (server, model, owner, _):
            held = asyncio.Event()
            async def infer(request):
                await held.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = infer
            request = admission.AdmissionRequest(.12, budget=admission.PLANNER_BUDGET)
            original = request.deadline
            pending = asyncio.create_task(admitted(model, request=request))
            await server.inferred.wait()
            self.assertIs(request.revoke_for_drain(), True)
            self.assertIs(request.revoke_for_drain(), True)
            self.assertEqual(request.deadline, original)
            self.assertFalse(request.cancelled.is_set())
            self.assertTrue(request.sealed)
            with self.assertRaises(TimeoutError): await pending
            self.assertTrue(request.cancelled.is_set())
            self.assertTrue(request.snapshot().connection_closed)
            self.assertIsNone(request.snapshot().released_at)
            self.assertIs(request.revoke_for_drain(), False)
            held.set()
        request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
        self.assertIs(request.revoke_for_drain(), False)
        request.update(count_valid=True, input_tokens=100)
        with self.assertRaises(TimeoutError): request.dispatch('inference', 10)

    async def test_preflight_active_witness_is_once_separate_and_cleanup_waits_for_it(self):
        self.assertTrue(hasattr(admission.SharedSlotOwner, 'observe_active'), 'owned active witness API is absent')
        async with reserved() as (server, model, owner, _):
            inference_release, get_entered, get_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
            async def infer(request):
                await inference_release.wait()
                return web.Response(body=choice_body(100))
            async def witness(request):
                get_entered.set()
                await get_release.wait()
                state = slots()
                state[1].update(is_processing=True, id_task=75)
                return web.json_response(state)
            server.on_infer = infer
            request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            pending = asyncio.create_task(admitted(model, request=request))
            await server.inferred.wait()
            server.on_get = witness
            observation = asyncio.create_task(owner.observe_active(request, request.deadline))
            await get_entered.wait()
            inference_release.set()
            await asyncio.sleep(.03)
            self.assertFalse(pending.done())
            self.assertEqual(sum(c[0] == 'GET' for c in server.calls), 2)
            server.on_get = None
            get_release.set()
            receipt = await observation
            self.assertEqual(receipt.active_task, 75)
            await pending
            self.assertEqual(request.snapshot().release_basis, 'full_terminal_then_idle')
            self.assertEqual(request.snapshot().witness_get_attempts, 1)
            self.assertEqual(request.snapshot().cleanup_get_attempts, 1)
            self.assertEqual(request.snapshot().slot_get_attempts, 2)
            self.assertEqual(owner.snapshot()['all_http_attempts'], 5)
            with self.assertRaises(admission.AdmissionUnavailable): await owner.observe_active(request, request.deadline)

    async def test_shutdown_reports_worker_still_running_after_outer_job_is_done(self):
        from types import SimpleNamespace
        from grounded_conversation import GroundedAnswers, GroundedJob
        async with reserved() as (server, model, owner, _):
            answers = GroundedAnswers(model)
            job = GroundedJob(SimpleNamespace(job_id='held-worker'))
            entered, release = threading.Event(), threading.Event()
            strict = admission._strict_json
            def held(raw, maximum):
                value = strict(raw, maximum)
                if value.get('object') == 'response.input_tokens':
                    entered.set()
                    release.wait(1)
                return value
            answers.bind_job(job)
            async def run():
                try: await admitted(model, request=job.admission)
                finally: answers.release_job(job)
            with patch.object(admission, '_strict_json', held):
                job.task = asyncio.create_task(run())
                self.assertTrue(await asyncio.to_thread(entered.wait, .5))
                try:
                    self.assertGreater(await answers.shutdown(.02), 0)
                    self.assertTrue(job.task.done())
                    self.assertTrue(job.admission.snapshot().worker_outstanding)
                finally: release.set()
                await asyncio.sleep(.04)
            self.assertEqual(await answers.shutdown(.1), 0)

    async def test_explicit_abort_cannot_be_reopened_by_repeated_publication_revoke(self):
        from grounded_conversation import GroundedJob
        from types import SimpleNamespace
        async with reserved() as (server, model, owner, _):
            release = asyncio.Event()
            async def held(request):
                await release.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = held
            job = GroundedJob(SimpleNamespace(job_id='explicit-abort'))
            job.task = asyncio.create_task(admitted(model, request=job.admission))
            await server.inferred.wait()
            job.retire('input')
            self.assertFalse(job.active)
            self.assertEqual(job.admission.snapshot().reason, 'input')
            self.assertFalse(job.admission.cancelled.is_set())
            job.retire('shutdown', abort=True)
            self.assertFalse(job.admission.revoke_for_drain('input'))
            with self.assertRaises(asyncio.CancelledError): await job.task
            self.assertTrue(job.admission.cancelled.is_set())
            self.assertTrue(job.admission.snapshot().connection_closed)
            self.assertIsNone(job.admission.snapshot().released_at)
            release.set()

    async def test_active_witness_rejects_unowned_preinfer_and_classifier_without_get(self):
        async with reserved() as (server, model, owner, _):
            unowned = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            with self.assertRaises(admission.AdmissionUnavailable):
                await owner.observe_active(unowned, unowned.deadline)
            await owner.acquire(unowned, 'planner')
            with self.assertRaises(admission.AdmissionUnavailable):
                await owner.observe_active(unowned, unowned.deadline)
            classifier = admission.AdmissionRequest(1)
            await owner.acquire(classifier, 'classifier')
            classifier.update(inference_attempts=1)
            with self.assertRaises(admission.AdmissionUnavailable):
                await owner.observe_active(classifier, classifier.deadline)
            self.assertEqual(len(server.calls), 1)

    async def test_unexpected_task_survives_normal_timeout_and_capped_hard_cleanup_idle(self):
        def retained_task(server): server.state[1]['id_task'] = 9
        async with reserved(configure=retained_task) as (server, model, owner, _):
            release = asyncio.Event()
            async def held(request):
                await release.wait()
                return web.Response(body=choice_body(100))
            server.on_infer = held
            real_connect, real_exchange = admission.AdmissionRequest.connect, admission.exchange
            class ProbeSocket:
                def shutdown(self, *_): pass
                def close(self): pass
            def connect(request, host, port):
                if request.snapshot().role: return real_connect(request, host, port)
                request.check()
                with request.lock: request.socket = ProbeSocket()
                return request.socket
            get_count = 0
            def exchange(request, owned, frame, **kwargs):
                nonlocal get_count
                if kwargs.get('method') != 'GET': return real_exchange(request, owned, frame, **kwargs)
                get_count += 1
                state = slots()
                state[1]['id_task'] = 9
                if get_count == 1: state[1]['is_processing'] = True
                if get_count == 2: raise TimeoutError('synthetic normal cleanup timeout')
                return json.dumps(state).encode(), False
            with patch.object(admission.AdmissionRequest, 'connect', connect), patch.object(admission, 'exchange', exchange):
                request = admission.AdmissionRequest(2, budget=admission.PLANNER_BUDGET)
                pending = asyncio.create_task(admitted(model, request=request))
                await server.inferred.wait()
                witness = await owner.observe_active(request, request.deadline)
                self.assertEqual(witness.unresolved_reason, 'unexpected_task')
                release.set()
                with self.assertRaises(TimeoutError): await pending
                await asyncio.gather(*tuple(owner.cleanup_tasks))
                receipt = request.snapshot()
                self.assertEqual((receipt.witness_get_attempts, receipt.cleanup_get_attempts), (1, 2))
                self.assertEqual(owner.snapshot()['slot_get_attempts'], 4)  # startup included
                self.assertIsNone(receipt.released_at, 'contradictory task association must remain latched')
                self.assertEqual(receipt.unresolved_reason, 'unexpected_task')
                before = owner.snapshot()['all_http_attempts']
                with self.assertRaises(admission.AdmissionUnavailable): await admitted(model)
                self.assertEqual(owner.snapshot()['all_http_attempts'], before)
                await model.classify(TEXT, RoutingContext('scope', []))
                self.assertFalse(owner.invalid)

    async def test_shutdown_retains_preparation_worker_after_129_released_history_evictions(self):
        from grounded_conversation import GroundedAnswers, GroundedJob
        from types import SimpleNamespace
        async with reserved() as (server, model, owner, _):
            answers = GroundedAnswers(model)
            job = GroundedJob(SimpleNamespace(job_id='old-prepare'), timeout=5)
            entered, release, finished = threading.Event(), threading.Event(), threading.Event()
            def held_prepare():
                entered.set()
                try:
                    release.wait(5)
                    raise ValueError('synthetic preparation rejection')
                finally: finished.set()
            def reject(): raise ValueError('synthetic preparation rejection')
            async def run(request, prepare):
                return await admission.run_admitted_chat(request, host=model.host, port=model.port,
                    token_file=model.token_file, prepare=prepare, decode_content=lambda value, _: value,
                    observe=lambda _: None, slot_owner=owner, role='planner')
            async def owned():
                try: await run(job.admission, held_prepare)
                finally: answers.release_job(job)
            answers.bind_job(job)
            job.task = asyncio.create_task(owned())
            self.assertTrue(await asyncio.to_thread(entered.wait, .5))
            try:
                job.retire()
                with self.assertRaises(asyncio.CancelledError): await job.task
                self.assertEqual(job.admission.snapshot().release_basis, 'sealed_zero_inference')
                for _ in range(129):
                    request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
                    with self.assertRaises(admission.AdmissionUnavailable): await run(request, reject)
                state = owner.snapshot()
                self.assertEqual(len(state['history']), 128)
                self.assertNotIn(job.admission.snapshot().request_id, {r['request_id'] for r in state['history']})
                self.assertEqual(state['total_attempts'], 0)
                self.assertEqual(len(server.calls), 1)
                self.assertFalse(finished.is_set())
                self.assertTrue(job.admission.snapshot().worker_outstanding)
                self.assertGreater(await answers.shutdown(.03), 0)
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait, .5))
            self.assertEqual(await answers.shutdown(.2), 0)

    async def test_transport_failure_during_drain_is_a_hard_abort(self):
        async with reserved() as (server, model, owner, _):
            release = asyncio.Event()
            async def broken(request):
                await release.wait()
                request.transport.close()
                return web.Response()
            server.on_infer = broken
            request = admission.AdmissionRequest(1, budget=admission.PLANNER_BUDGET)
            pending = asyncio.create_task(admitted(model, request=request))
            await server.inferred.wait()
            self.assertTrue(request.revoke_for_drain())
            release.set()
            with self.assertRaises(admission.AdmissionUnavailable): await pending
            self.assertTrue(request.cancelled.is_set())
            self.assertFalse(request.revoke_for_drain())
            self.assertIsNone(request.snapshot().released_at)


if __name__ == '__main__': unittest.main()
