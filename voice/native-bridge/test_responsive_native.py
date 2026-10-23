import asyncio
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from native_bridge import Config, NativeCall, Dialog as NativeDialog, create_app, load_config
from responsive_config import ResponsiveConfig
from business_tasks import Agent, Scope, StoreDenied
from conversation_router import ConversationRouter, Route
from servicenow_executor import LegacyVAExecutor
from task_coordinator import TaskCoordinator
from task_store import TaskStore
from test_input_lifecycle import Peer


class Router:
    async def route(self, text, context):
        if text == 'status':
            return Route('status_query', context.tasks[0]['task_id'])
        if context.tasks:
            return Route('continue_task', context.tasks[0]['task_id'])
        return Route('new_task', agent_alias='desk')


class Speech:
    def __init__(self):
        self.spoken = []
        self.active = self.maximum = 0
        self.hold = None
        self.release = asyncio.Event()

    async def transcribe(self, pcm):
        return pcm.decode()

    async def synthesize(self, text):
        self.spoken.append(text)
        self.active += 1
        self.maximum = max(self.active, self.maximum)
        try:
            if text == self.hold:
                await self.release.wait()
            yield bytes(960)
        finally:
            self.active -= 1


class Dialog:
    metadata = {}
    _call_owned = True
    must_reset = False

    def __init__(self):
        self.open_release = asyncio.Event()
        self.open_release.set()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.received = []
        self.greetings = []
        self.history = []
        self.closed = self.shutdown_called = self.cancelled = False
        self.fail = False

    async def open(self):
        await self.open_release.wait()
        return self.greetings

    def record_greeting(self, text):
        self.history.append(text)

    async def turn(self, text, on_reply=None, voice_context=None):
        self.received.append((text, voice_context))
        self.started.set()
        try:
            await self.release.wait()
            if self.fail:
                raise RuntimeError('synthetic business uncertainty')
            await on_reply('Real backend reply?')
            return ['Real backend reply?']
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def close(self):
        self.closed = True

    async def shutdown(self):
        self.shutdown_called = True


async def until(predicate, timeout=2):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.005)


class NativeResponsiveTests(unittest.IsolatedAsyncioTestCase):
    def idle_settings(self, *, selection=False):
        return SimpleNamespace(service_id='assistant', introduction='', vad_stop_ms=None,
            max_call_seconds=None, inactivity_seconds=.05, configured_goodbye='Local goodbye.',
            selection_prompt='Choose a language.' if selection else '',
            language_selection={'enabled':selection, 'mode':'voice', 'languages':[{},{}]},
            select_language=lambda text:False,
            native_context=lambda:{'requester_session_language':'de-DE', 'voice_assistant':'assistant',
                                   'global_context_profile':'profile'})

    def drain_audio(self, call):
        async def drain():
            while not call.closed:
                call.playback.read(960)
                await asyncio.sleep(.005)
        return call.spawn(drain())

    async def test_idle_waits_for_open_and_held_business_then_closes_at_awaiting_input(self):
        self.dialog.open_release.clear()
        call = await self.start(settings=self.idle_settings())
        self.drain_audio(call)
        await asyncio.sleep(.15)
        self.assertFalse(call.closing)
        await self.say(call, 'first request')
        self.dialog.open_release.set()
        await asyncio.wait_for(self.dialog.started.wait(), 1)
        await asyncio.sleep(.15)
        self.assertFalse(call.closing)
        self.dialog.release.set()
        await asyncio.wait_for(call.input_ended.wait(), 1)
        await asyncio.wait_for(call.turns_settled.wait(), 1)
        self.assertIn('Local goodbye.', self.speech.spoken)
        self.assertFalse(self.dialog.cancelled)

    async def test_language_prompt_waiting_for_user_can_idle_close(self):
        call = await self.start(settings=self.idle_settings(selection=True))
        self.drain_audio(call)
        await asyncio.wait_for(call.input_ended.wait(), .5)
        await asyncio.wait_for(call.turns_settled.wait(), .5)
        self.assertEqual(self.speech.spoken, ['Choose a language.', 'Local goodbye.'])
        self.assertEqual(self.dialog.received, [])

    async def test_unrelated_queued_task_does_not_disable_idle_timeout(self):
        class SeparateRouter(Router):
            async def route(self, text, context):
                if text == 'unrelated task':
                    return Route('new_task', agent_alias='desk')
                return await super().route(text, context)
        self.coordinator.router = SeparateRouter()
        call = await self.start(settings=self.idle_settings())
        self.drain_audio(call)
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 1)
        await self.say(call, 'unrelated task')
        self.dialog.release.set()
        await asyncio.wait_for(call.input_ended.wait(), 1)
        await asyncio.wait_for(call.turns_settled.wait(), 1)
        self.assertEqual(len(self.dialog.received), 1)
        self.assertEqual(self.store.operations(call.call_id)[1]['dispatch_state'], 'suspended')

    async def test_barge_in_during_goodbye_resumes_intake(self):
        self.speech.hold = 'Local goodbye.'
        call = await self.start(settings=self.idle_settings())
        self.drain_audio(call)
        await until(lambda: 'Local goodbye.' in self.speech.spoken)
        # Exercise the same arbiter generation interruption used by native VAD.
        call.responsive_output.interrupt()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 1)
        self.assertFalse(call.input_ended.is_set())
        self.assertFalse(call.closing)
        self.assertEqual(self.speech.maximum, 1)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp.name) / 'tasks.db')
        self.agent = Agent('desk', 'agent', 'rev', {'new_task': True, 'continue_task': True})
        self.profile = ResponsiveConfig(enabled=True, mode='assist', store_file=str(self.store.path), agents=(self.agent,))
        self.coordinator = TaskCoordinator(self.store, Router(), [self.agent], lambda scope: None)
        self.dialog = Dialog()
        self.speech = Speech()
        self.calls = []
        self.peer_patch = patch('native_bridge.RTCPeerConnection', Peer)
        self.peer_patch.start()

    async def attach(self, call, emit, ready):
        scope = Scope(call.call_id, call.call_id, 1, call.config.instance_name, call.config.voice_service_id)
        return await self.coordinator.attach(scope, emit, executor=LegacyVAExecutor(call.dialog, ready=ready))

    def call(self, settings=None, dialog=None, enabled=True):
        config = Config(instance_name='fixture', voice_service_id=settings.service_id if settings else 'assistant', private_responsive=self.profile)
        call = NativeCall(config, self.speech, dialog or self.dialog, settings,
                          responsive_attachment_factory=self.attach if enabled else None)
        self.calls.append(call)
        return call

    async def start(self, **kwargs):
        call = self.call(**kwargs)
        call.spawn(call.process_turns())
        await until(lambda: call.responsive_attachment is not None)
        return call

    async def say(self, call, text):
        call.turns.put_nowait((call.playback.generation, text.encode()))
        await call.turns.join()
        await call.recognized_turns.join()

    def transcripts(self, call):
        return [e['data'] for e in call.pending_events if e['type'] == 'transcript']

    async def asyncTearDown(self):
        self.dialog.open_release.set()
        self.dialog.release.set()
        self.speech.release.set()
        for call in self.calls:
            call.dialog.release.set()
            await asyncio.wait_for(call.close(), 2)
        await self.coordinator.shutdown(.2)
        self.peer_patch.stop()
        self.store.close()
        self.tmp.cleanup()

    async def test_delayed_open_accepts_input_without_dispatch(self):
        self.dialog.open_release.clear()
        call = await self.start()
        await self.say(call, 'first request')
        self.assertEqual([op['text'] for op in self.store.pending(call.call_id)], ['first request'])
        self.assertFalse(self.dialog.started.is_set())
        self.assertTrue(any(t['content'] == 'first request' for t in self.transcripts(call)))
        self.dialog.open_release.set()
        await asyncio.wait_for(self.dialog.started.wait(), 2)

    async def test_readiness_notice_once_after_1000ms(self):
        self.dialog.open_release.clear()
        call = await self.start()
        await asyncio.sleep(.8)
        self.assertFalse(any(t.get('code') == 'CONNECTION_PENDING' for t in self.transcripts(call)))
        await until(lambda: any(t.get('code') == 'CONNECTION_PENDING' for t in self.transcripts(call)))
        await asyncio.sleep(.15)
        self.assertEqual(len([t for t in self.transcripts(call) if t.get('code') == 'CONNECTION_PENDING']), 1)
        self.assertEqual(self.dialog.history, [])
        self.assertTrue(self.speech.spoken)

    async def test_ready_before_1000ms_has_no_notice(self):
        call = await self.start()
        await asyncio.sleep(1.05)
        self.assertFalse(any(t.get('code') == 'CONNECTION_PENDING' for t in self.transcripts(call)))

    async def test_actual_configured_name_prompt_binds_short_answer_without_fabrication(self):
        self.coordinator.router = ConversationRouter()
        self.dialog.greetings = ['Bitte nennen Sie Ihren Namen.']
        call = await self.start()
        await until(lambda: bool(self.speech.spoken))
        await self.say(call, 'Max Mustermann')
        await asyncio.wait_for(self.dialog.started.wait(), .5)
        self.assertEqual(self.dialog.received[0][0], 'Max Mustermann')
        self.assertEqual(self.dialog.history, [])

    async def test_real_router_explains_bound_question_while_native_business_is_held(self):
        self.coordinator.router = ConversationRouter()
        self.dialog.greetings = ['Bitte nennen Sie Ihren Namen.']
        call = await self.start()
        await until(lambda: bool(self.speech.spoken))
        await self.say(call, 'Nora Berg')
        await asyncio.wait_for(self.dialog.started.wait(), .5)
        task_id = self.store.operations(call.call_id)[0]['task_id']
        await call.responsive_attachment.note_question('An welchem Datum?', task_id=task_id)
        await self.say(call, 'Was bedeutet die aktuelle Frage?')
        await until(lambda: any('Kalendertag' in text for text in self.speech.spoken))
        self.assertFalse(self.dialog.release.is_set())
        self.assertEqual(len(self.dialog.received), 1)
        self.assertEqual(len(self.store.operations(call.call_id)), 1)
        self.assertTrue(any('An welchem Datum?' in t['content'] for t in self.transcripts(call)))

    async def test_suppressed_fallback_does_not_fabricate_greeting_history(self):
        from conversation_output import OutputArbiter
        publish = OutputArbiter.publish
        async def interrupted(arbiter, event):
            result = await publish(arbiter, event)
            if event['text'] == 'Configured fallback':
                arbiter.interrupt()
            return result
        call = self.call()
        call.config.greeting = 'Configured fallback'
        with patch.object(OutputArbiter, 'publish', interrupted):
            call.spawn(call.process_turns())
            await until(lambda: call.responsive_attachment is not None)
            await asyncio.sleep(.02)
            await self.say(call, 'first request')
            await asyncio.wait_for(self.dialog.started.wait(), 1)
        self.assertEqual(self.dialog.history, [])
        self.assertFalse(any(t['content'] == 'Configured fallback' for t in self.transcripts(call)))

    async def test_status_spoken_before_release_and_second_followup_retained(self):
        call = await self.start()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        await self.say(call, 'status')
        await until(lambda: any('Status: running' in text for text in self.speech.spoken))
        self.assertFalse(self.dialog.release.is_set())
        await self.say(call, 'second exact followup')
        self.assertEqual([o['text'] for o in self.store.pending(call.call_id)], ['second exact followup'])
        self.dialog.release.set()
        await until(lambda: len(self.dialog.received) == 2)
        self.assertEqual(self.dialog.received[1][0], 'second exact followup')

    async def test_real_transcript_order_shape_and_greeting_before_dispatch(self):
        self.dialog.greetings = ['Actual greeting: your name?']
        self.speech.hold = self.dialog.greetings[0]
        call = await self.start()
        await until(lambda: self.speech.active == 1)
        self.assertTrue(call.synthesis_active)
        # User acceptance interrupts the greeting, but cannot dispatch before its synthesis exits.
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        self.dialog.release.set()
        await until(lambda: any(t['content'] == 'Real backend reply?' for t in self.transcripts(call)))
        ts = self.transcripts(call)
        self.assertLess(next(i for i,t in enumerate(ts) if t['content'].startswith('Actual greeting')),
                        next(i for i,t in enumerate(ts) if t['content'] == 'Real backend reply?'))
        user = next(t for t in ts if t['role'] == 'user')
        reply = next(t for t in ts if t['content'] == 'Real backend reply?')
        self.assertEqual(reply['caller_turn_id'], user['caller_turn_id'])
        self.assertEqual(reply['turn_num'], user['turn_num'])
        self.assertEqual(set(reply), {'role','content','message_id','caller_turn_id','turn_num','latency_ms'})
        self.assertEqual(self.speech.maximum, 1)

    async def test_language_selection_is_local_and_serialized(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        call = await self.start(settings=settings)
        await self.say(call, 'English please.')
        await until(lambda: any(t.get('code') == 'LANGUAGE_SELECTED' for t in self.transcripts(call)))
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(self.store.operations(call.call_id), [])
        self.assertEqual(self.speech.maximum, 1)
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        self.assertEqual(self.dialog.received[0][1]['language'], 'en-US')

    async def test_queued_language_snapshot_survives_later_selection(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        call = await self.start(settings=settings)
        await self.say(call, 'English please.')
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        await self.say(call, 'queued request')
        saved = self.store.pending(call.call_id)[0]['voice_context']
        self.assertEqual(saved, {'language':'en-US', 'assistant_id':SERVICE, 'profile':settings.context_profile})
        # A later trusted selection cannot rewrite the accepted operation snapshot.
        settings.selected_language = 'de-DE'
        self.dialog.release.set()
        await until(lambda: len(self.dialog.received) == 2)
        self.assertEqual(self.dialog.received[1][1], saved)

    async def test_terminal_input_loss_detaches_but_observes_submitted_turn(self):
        call = await self.start()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        await call.finish_input_loss()
        await asyncio.wait_for(call.turns_settled.wait(), 1)
        self.assertFalse(self.dialog.cancelled)
        self.assertTrue(self.store.has_unresolved())
        self.dialog.release.set()
        await call.close()
        await call.recognized_turns.join()
        self.assertFalse(any(t['content'] == 'Real backend reply?' for t in self.transcripts(call)))

    async def test_startup_failure_never_dispatches_accepted_input(self):
        self.dialog.open_release.clear()
        async def fail_open():
            await self.dialog.open_release.wait()
            raise RuntimeError('synthetic startup failure')
        self.dialog.open = fail_open
        call = await self.start()
        await self.say(call, 'first request')
        with self.assertLogs('native-voice', level='WARNING') as logs:
            self.dialog.open_release.set()
            await asyncio.wait_for(call.turns_settled.wait(), 1)
        self.assertTrue(any('stage=startup_failed type=RuntimeError' in line for line in logs.output))
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(self.store.operations(call.call_id)[0]['dispatch_state'], 'suspended')
        await call.close()
        await call.recognized_turns.join()

    async def test_hangup_does_not_cancel_worker_or_close_dialog_early(self):
        call = await self.start()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        closing = asyncio.create_task(call.close())
        await until(lambda: call.closed)
        self.assertFalse(closing.done())
        self.assertFalse(self.dialog.closed)
        self.assertFalse(self.dialog.cancelled)
        self.assertFalse(self.dialog.shutdown_called)
        self.assertFalse(self.coordinator.available)
        self.dialog.release.set()
        await closing
        self.assertTrue(self.dialog.shutdown_called)
        self.assertTrue(self.coordinator.available)

    async def test_late_reply_cannot_reach_next_call_and_repeat_greeting(self):
        self.dialog.greetings = ['Real greeting']
        call = await self.start()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        closing = asyncio.create_task(call.close())
        await until(lambda: call.closed)
        count = len(self.transcripts(call))
        with self.assertRaises(StoreDenied):
            await self.coordinator.attach(Scope('other','other',1,'fixture','assistant'), lambda e: None)
        self.dialog.release.set()
        await closing
        self.assertEqual(len(self.transcripts(call)), count)
        next_dialog = Dialog()
        next_dialog.greetings = ['Real greeting']
        other = await self.start(dialog=next_dialog)
        await until(lambda: any(t['content'] == 'Real greeting' for t in self.transcripts(other)))
        self.assertFalse(any(t['content'] == 'Real backend reply?' for t in self.transcripts(other)))
        self.assertEqual([t['content'] for t in self.transcripts(other)], ['Real greeting'])

    async def test_failed_store_has_no_accepted_or_user_ack(self):
        call = await self.start()
        with self.assertLogs('native-voice', level='WARNING') as logs:
            with patch.object(self.store, 'accept_new_task', side_effect=OSError('private synthetic failure')):
                await self.say(call, 'first request')
        self.assertTrue(any('stage=not_accepted type=OSError' in line for line in logs.output))
        self.assertFalse(any('private synthetic failure' in line for line in logs.output))
        await until(lambda: any(t.get('code') == 'NOT_ACCEPTED' for t in self.transcripts(call)))
        self.assertFalse(any(t['role'] == 'user' or 'Angenommen' in t['content'] for t in self.transcripts(call)))
        self.assertFalse(self.dialog.started.is_set())

    async def test_enabled_queue_is_32_and_legacy_queue_is_2(self):
        call = self.call()
        legacy = self.call(enabled=False, dialog=Dialog())
        self.assertEqual(call.recognized_turns.maxsize, 32)
        self.assertEqual(legacy.recognized_turns.maxsize, 2)
        for i in range(32):
            call.recognized_turns.put_nowait((0,'queued',i,str(i),time.monotonic()))
        call.asr_task = call.spawn(call.recognize_turns())
        call.turns.put_nowait((0, b'overflow'))
        await call.turns.join()
        self.assertTrue(any(t.get('code') == 'BUSY' for t in self.transcripts(call)))
        self.assertFalse(any(t['role'] == 'user' for t in self.transcripts(call)))


class ConfigResponsiveTests(unittest.TestCase):
    def test_profile_resolved_once_and_inline_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'responsive.json').write_text(json.dumps({'enabled':False,'mode':'assist'}))
            (root/'config.json').write_text(json.dumps({'responsive_config_file':'responsive.json'}))
            config = load_config(root/'config.json')
            self.assertFalse(config.private_responsive.enabled)
            self.assertEqual(config.private_responsive.mode, 'assist')
            (root/'config.json').write_text(json.dumps({'private_responsive':{}}))
            with self.assertRaises(ValueError): load_config(root/'config.json')


class DialogContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonical_context_reconstructs_exact_native_fields_and_retains_language(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        dialog = NativeDialog(Config(voice_service_id=SERVICE), settings)
        expected = settings.native_context()
        canonical = {'language':settings.language, 'assistant_id':SERVICE, 'profile':settings.context_profile}
        settings.select_language('English please.')
        sent = []
        async def request(method, path, **kwargs):
            if method == 'POST':
                sent.append(kwargs['json'])
            return {'cursor':1, 'events':[], 'busy':False}
        dialog.request = request
        await dialog.turn('verbatim', voice_context=canonical)
        self.assertEqual(sent, [{'text':'verbatim', 'voice_context':expected}])
        for changed in ({'assistant_id':'wrong'}, {'profile':'wrong'}, {'language':'unconfigured'}):
            with self.assertRaises(ValueError):
                await dialog.turn('must not send', voice_context={**canonical, **changed})
        self.assertEqual(len(sent), 1)
        # Public legacy None/six-key callers keep their existing meaning.
        await dialog.turn('legacy', voice_context=expected)
        await dialog.turn('current')
        self.assertEqual(sent[-2]['voice_context'], expected)
        self.assertEqual(sent[-1]['voice_context'], settings.native_context())


class AppResponsiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresolved_reservation_blocks_browser_and_sdk_without_private_details(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'private.db'
            store = TaskStore(path)
            agent = Agent('desk', 'agent', 'rev', {'new_task':True})
            scope = Scope('oldscope','oldcall',1,'fixture',SERVICE)
            operation = store.accept_new_task(scope, agent, 'oldutterance', 'private business content')
            store.dispatch(operation['operation_id'])
            store.close()
            profile = ResponsiveConfig(enabled=True, mode='assist', store_file=str(path), agents=(agent,))
            config = Config(instance_name='fixture', voice_service_id=SERVICE, required_agent_id=AGENT,
                auth_mode='servicenow', native_sdk_enabled=True, sdk_public_origin='https://voice.example.com',
                private_responsive=profile)
            context = SimpleNamespace(instance_url=config.instance_url, assistant_id=SERVICE,
                voice_agent_id=AGENT, sdk_agent_id='agent_operator', receive_data=True, call_settings=settings)
            async def admit(*args, **kwargs): return context
            async def authorize(*args, **kwargs): return settings
            with patch('sdk_admission.admit_sdk_session', admit), patch('native_bridge.authorize', authorize):
                app = create_app(config, dialog_factory=lambda: self.fail('must not allocate a dialog'))
                client = TestClient(TestServer(app))
                await client.start_server()
                try:
                    browser = await client.get('/webrtc/connect/agent_operator')
                    self.assertEqual(browser.status, 503)
                    self.assertIn('Support', await browser.text())
                    with self.assertLogs('sdk_sessions', level='WARNING'):
                        sdk = await client.post('/api/webrtc/sessions?instance_name=fixture&receive_data=true',
                            headers={'Authorization':'Bearer fixture-token'}, json={'agent_id':'agent_operator'})
                    self.assertEqual(sdk.status, 503)
                    payload = await sdk.json()
                    self.assertEqual(payload['error'], 'unavailable')
                    self.assertIn('Support', payload['message'])
                    self.assertNotIn('private business content', json.dumps(payload))
                    self.assertEqual(sdk.headers['Cache-Control'], 'no-store')
                    health = await (await client.get('/health')).json()
                    self.assertEqual(health['nativeSessions'], 0)
                    self.assertEqual(health['responsive']['unresolvedContexts'], 1)
                finally:
                    await client.close()
            reopened = TaskStore(path)
            try:
                self.assertEqual(reopened.operations('oldscope')[0]['dispatch_state'], 'unknown')
            finally:
                reopened.close()

    async def test_default_factory_loads_configured_model_without_network_or_secret_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = ResponsiveConfig(enabled=True, mode='assist', store_file=str(Path(tmp)/'private.db'),
                model_url='http://127.0.0.1:9999/v1/chat/completions', model_name='test-dialogue',
                model_token_file=str(Path(tmp)/'secret-token'))
            app = create_app(Config(instance_name='fixture', voice_service_id='assistant', private_responsive=profile),
                             dialog_factory=lambda:None)
            client = TestClient(TestServer(app))
            await client.start_server()
            try:
                response = await client.get('/health')
                text = await response.text()
                health = json.loads(text)['responsive']
                self.assertEqual(health['model'], 'test-dialogue')
                self.assertFalse(any(health['capabilities'].values()))
                self.assertNotIn('private.db', text)
                self.assertNotIn('secret-token', text)
                self.assertNotIn('127.0.0.1', text)
            finally:
                await client.close()

    async def test_app_cleanup_retains_observer_and_restart_unknown_blocks_admission(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(Path(tmp)/'private.db')
            agent = Agent('desk','agent','rev',{'new_task':True, 'continue_task':True})
            profile = ResponsiveConfig(enabled=True, mode='assist', store_file=str(store.path), agents=(agent,))
            coordinator = TaskCoordinator(store, Router(), [agent], lambda scope: None)
            dialog, speech, captured = Dialog(), Speech(), {}
            config = Config(instance_name='fixture', voice_service_id=SERVICE, required_agent_id=AGENT,
                auth_mode='servicenow', native_sdk_enabled=True, sdk_public_origin='https://voice.example.com',
                private_responsive=profile)
            def register(app, config, active, factory, admit, **kwargs):
                captured.update(active=active, factory=kwargs['context_call_factory'])
            with patch('sdk_sessions.register_sdk_routes', register), patch('native_bridge.RTCPeerConnection', Peer):
                with patch.object(store, 'recover', wraps=store.recover) as recover:
                    app = create_app(config, lambda http:speech, lambda:dialog,
                                     responsive_factory=lambda profile,http:coordinator)
                    lifecycle = app.cleanup_ctx[0](app)
                    await anext(lifecycle)
                    self.assertEqual(recover.call_count, 1)
                call = captured['factory'](SimpleNamespace(call_settings=settings))
                captured['active'].add(call)
                call.spawn(call.process_turns())
                await until(lambda: call.responsive_attachment is not None)
                call.turns.put_nowait((0,b'English please.'))
                await call.turns.join()
                await call.recognized_turns.join()
                call.turns.put_nowait((0,b'first request'))
                await asyncio.wait_for(dialog.started.wait(), 2)
                self.assertEqual(call.responsive_attachment.scope.assistant_id, SERVICE)
                self.assertEqual(call.responsive_attachment.scope.principal_id, '')
                with self.assertRaises(Exception) as rejected:
                    captured['factory'](SimpleNamespace(call_settings=settings))
                self.assertEqual(rejected.exception.status, 503)
                self.assertIn('Support', rejected.exception.text)
                handler = next(route.handler for route in app.router.routes() if route.resource.canonical == '/health')
                health = json.loads((await handler(SimpleNamespace(query={}))).text)['responsive']
                self.assertEqual(set(health), {'mode','model','capabilities','reservedContexts','unresolvedContexts'})
                self.assertEqual(health['unresolvedContexts'], 1)
                start = time.monotonic()
                with self.assertLogs('native-voice', level='WARNING') as logs:
                    with self.assertRaises(StopAsyncIteration):
                        await anext(lifecycle)
                self.assertTrue(any('stage=unresolved_owned_cleanup' in line for line in logs.output))
                self.assertLess(time.monotonic()-start, 6)
                self.assertFalse(dialog.closed or dialog.shutdown_called or dialog.cancelled)
                self.assertEqual(store.operations(call.call_id)[0]['dispatch_state'], 'submitted')
                # Snapshot the fake journal as at process exit. Recover only the new process store.
                import sqlite3
                restart_path = Path(tmp)/'restart.db'
                with sqlite3.connect(restart_path) as snapshot:
                    store._db.backup(snapshot)
                snapshot.close()
                restart = TaskStore(restart_path)
                try:
                    self.assertEqual(restart.recover(), {'unknown':1})
                    self.assertEqual(restart.operations(call.call_id)[0]['dispatch_state'], 'unknown')
                    blocked = TaskCoordinator(restart, Router(), [agent], lambda scope: None)
                    self.assertFalse(blocked.available)
                    with self.assertRaises(StoreDenied):
                        await blocked.attach(Scope('new','new',1,'fixture',SERVICE), lambda event:None)
                finally:
                    restart.close()
                dialog.release.set()
                await asyncio.wait_for(call.close(), 2)
                await until(lambda: store._db is None)
                self.assertTrue(dialog.shutdown_called)


if __name__ == '__main__':
    unittest.main()
