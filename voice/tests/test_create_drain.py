"""Owned CREATE drain regressions. Local synthetic servers only."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
from voice import bridge as implementation
from voice.tests import test_local_caller_create as original
created, CONTROL = original.created, original.CONTROL
from voice.tests import test_caller_binding as fixtures


class CreateDrainTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = original.OwnedCreateBridgeTests.asyncSetUp
    start = original.OwnedCreateBridgeTests.start
    settle = original.OwnedCreateBridgeTests.settle
    async def pending_create(self):
        self.entered, self.release, self.cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def own(*args, **kwargs):
            self.entered.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
            return created(args[4])
        self.creator.side_effect = own
        self.starting = asyncio.create_task(self.start())
        await asyncio.wait_for(self.entered.wait(), 1)
        self.session = next(iter(self.bridge.sessions.values()))
        self.addAsyncCleanup(self.release_start)
        return self.session

    async def release_start(self):
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)

    async def close_request(self, path='/api/end'):
        response = await asyncio.wait_for(self.ui.post(path, json={}, headers=self.headers), 1)
        return response, await response.json()

    async def terminal(self, **overrides):
        end = self.sent[-1]
        data = dict(requestId=end['requestId'], clientSessionId=self.session.sid,
                    userId=self.session.user_id, completed=True, body=[])
        data.update(overrides)
        return await self.callbacks.post('/callback', json=data,
            headers={'Authorization':'Bearer callback-secret'})

    async def test_drain_close_preserves_create_and_orders_single_end_without_start(self):
        session = await self.pending_create()
        response, info = await self.close_request()
        self.assertEqual(response.status, 202)
        self.assertIs(info.get('ended'), False)
        self.assertFalse(self.cancelled.is_set())
        self.assertEqual(self.sent, [])
        self.assertIs(self.bridge.sessions[session.sid], session)
        self.assertIsNone(session.caller_bootstrap)
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertEqual(session.conversation_binding.conversation_id, CONTROL['conversationId'])
        self.assertEqual([item.get('action') for item in self.sent], ['END_CONVERSATION'])
        self.refresher.assert_not_awaited()
        self.creator.assert_awaited_once()
        _, info = await self.close_request()
        self.assertIs(info['ended'], False)
        self.assertEqual(info['cleanup'], 'end_enqueued')
        self.assertEqual(len(self.sent), 1)
        message = await self.ui.post('/api/message', json={'text':'forbidden'}, headers=self.headers)
        self.assertEqual(message.status, 409)

    async def test_drain_reset_and_expiry_retain_cookie_and_identity_until_terminal(self):
        session = await self.pending_create()
        response, info = await self.close_request('/api/reset')
        self.assertEqual(response.status, 202)
        self.assertIs(info['ended'], False)
        session.created -= self.bridge.settings.session_seconds + 1
        self.bridge.expire()
        self.assertIs(self.bridge.sessions[session.sid], session)
        self.assertEqual(session.caller_user_id, '1'*32)
        self.assertFalse(self.cancelled.is_set())
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual((await self.terminal()).status, 200)
        response, info = await self.close_request()
        self.assertEqual(response.status, 200)
        self.assertTrue(info['ended'])
        self.assertEqual((await self.ui.get('/api/session')).status, 200)
        self.assertNotIn(session.sid, self.bridge.sessions)
        self.assertEqual(len(self.bridge.sessions), 1)

    async def test_drain_ack_does_not_settle_and_only_exact_end_completed_callback_does(self):
        await self.pending_create()
        response, _ = await self.close_request()
        self.assertEqual(response.status, 202)
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        for overrides in ({'completed':False}, {'completed':None}, {'requestId':'f'*32},
                          {'requestId':self.session.caller_create_request_id}, {'userId':'foreign'},
                          {'userId':None}, {'streamActive':True}):
            await self.terminal(**overrides)
            _, info = await self.close_request()
            self.assertIs(info['ended'], False)
        self.assertEqual((await self.terminal()).status, 200)
        response, info = await self.close_request()
        self.assertEqual(response.status, 200)
        self.assertIs(info['ended'], True)
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        self.assertEqual(len(self.sent), 1)

    async def test_drain_concurrent_observers_join_one_end_and_tombstone_is_end_only(self):
        await self.pending_create()
        responses = await asyncio.gather(*(self.close_request() for _ in range(5)))
        self.assertTrue(all(response.status == 202 for response, _ in responses))
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertEqual(len(self.sent), 1)
        await self.terminal()
        await self.close_request()
        self.ui.session.cookie_jar.update_cookies({'scc_voice': self.session.sid})
        # Retained receipts can answer END only and require the original CSRF.
        denied = await self.ui.post('/api/end', json={}, headers={**self.headers,'X-CSRF-Token':'wrong'})
        self.assertEqual(denied.status, 403)
        for path in ('/api/start', '/api/message', '/api/reset'):
            denied = await self.ui.post(path, json={}, headers=self.headers)
            self.assertEqual(denied.status, 401)
        response, info = await self.close_request()
        self.assertEqual(response.status, 200)
        self.assertIs(info['ended'], True)
        fresh = await self.ui.get('/api/session')
        self.assertEqual(fresh.status, 200)
        self.assertEqual(len(self.sent), 1)

    async def test_drain_cancelled_start_handler_keeps_owned_mutation_and_cleanup(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def own(*args, **kwargs):
            entered.set()
            await release.wait()
            return created(args[4])
        self.creator.side_effect = own
        session = next(iter(self.bridge.sessions.values()))
        class Headers(dict):
            def getall(self, key, default):
                return [self[key]] if key in self else default
        request = SimpleNamespace(_voice_session=session, headers=Headers({fixtures.HEADER:fixtures.TOKEN}))
        with patch.object(self.bridge, 'json', return_value={'voice_context':fixtures.CONTEXT}):
            starting = asyncio.create_task(self.bridge.start(request))
            await entered.wait()
            starting.cancel()
            await asyncio.gather(starting, return_exceptions=True)
        self.assertIsNotNone(getattr(session, 'caller_create_task', None))
        self.assertFalse(session.caller_create_task.cancelled())
        release.set()
        await asyncio.wait_for(session.cleanup_task, 1)
        self.assertEqual(session.conversation_binding.conversation_id, CONTROL['conversationId'])
        self.assertEqual([item.get('action') for item in self.sent], ['END_CONVERSATION'])
        self.refresher.assert_not_awaited()

    async def unknown_create(self, result):
        session = next(iter(self.bridge.sessions.values()))
        async def own(*args, **kwargs):
            if result == 'timeout': raise asyncio.TimeoutError()
            value = created(args[4])
            value['userId'] = 'foreign'
            return {} if result == 'malformed' else value
        self.creator.side_effect = own
        self.assertGreaterEqual((await self.start()).status, 400)
        for _ in range(2):
            response, info = await self.close_request()
            self.assertEqual(response.status, 202)
            self.assertIs(info['ended'], False)
        self.assertIs(self.bridge.sessions[session.sid], session)
        self.assertEqual(self.sent, [])
        self.creator.assert_awaited_once()

    async def test_drain_malformed_create_never_speculates_or_replays_end(self):
        await self.unknown_create('malformed')

    async def test_drain_timeout_create_never_speculates_or_replays_end(self):
        await self.unknown_create('timeout')

    async def test_drain_foreign_create_never_speculates_or_replays_end(self):
        await self.unknown_create('foreign')

    async def test_drain_source_change_after_create_prevents_end_at_changed_destination(self):
        await self.start()
        await self.settle()
        session = next(iter(self.bridge.sessions.values()))
        before = len(self.sent)
        self.bridge.settings.instance_url = 'https://changed.example.test'
        response, info = await self.close_request()
        self.assertEqual(response.status, 202)
        await session.cleanup_task
        self.assertEqual(len(self.sent), before)
        self.assertEqual(session.cleanup_state, 'unresolved')

    async def test_drain_caller_change_after_create_prevents_end_for_changed_caller(self):
        await self.start()
        await self.settle()
        session = next(iter(self.bridge.sessions.values()))
        before = len(self.sent)
        session.caller_user_id = 'f'*32
        await self.close_request()
        await session.cleanup_task
        self.assertEqual(len(self.sent), before)
        self.assertEqual(session.cleanup_state, 'unresolved')

    async def test_drain_admitted_language_update_keeps_original_cleanup_ownership(self):
        await self.start()
        await self.settle()
        self.session = next(iter(self.bridge.sessions.values()))
        await self.terminal(completed=False, body=[{'uiType':'InputText','label':'Name?'}])
        context = dict(fixtures.CONTEXT, interaction_requester_session_language='en',
                       interaction_user_language='en', requester_session_language='en')
        response = await self.ui.post('/api/message', json={'text':'Synthetic name',
                                      'voice_context':context}, headers=self.headers)
        self.assertEqual(response.status, 202)
        await self.close_request()
        await self.session.cleanup_task
        self.assertEqual([item.get('action') for item in self.sent],
                         ['START_CREATED_CONVERSATION', None, 'END_CONVERSATION'])
        self.assertEqual(self.session.cleanup_state, 'end_enqueued')

    async def test_drain_profile_change_after_create_still_prevents_end(self):
        await self.start()
        await self.settle()
        session = next(iter(self.bridge.sessions.values()))
        before = len(self.sent)
        session.voice_context['global_context_profile'] = 'f'*32
        await self.close_request()
        await session.cleanup_task
        self.assertEqual(len(self.sent), before)
        self.assertEqual(session.cleanup_state, 'unresolved')

    async def test_drain_failed_end_is_latched_and_not_replayed(self):
        await self.start()
        await self.settle()
        session = next(iter(self.bridge.sessions.values()))
        with patch.object(self.bridge.http, 'post', side_effect=RuntimeError('synthetic failure')) as post:
            await self.close_request()
            await session.cleanup_task
            await self.close_request()
            await self.close_request('/api/reset')
            self.assertEqual(post.call_count, 1)
        self.assertEqual(session.cleanup_state, 'unresolved')
        self.assertIs(self.bridge.sessions[session.sid], session)

    async def test_drain_tombstones_are_bounded_and_expire_without_session_credit(self):
        for _ in range(implementation.MAX_END_RECEIPTS + 2):
            session = implementation.Conversation()
            self.bridge.finish_owned_cleanup(session)
        self.assertEqual(len(self.bridge.end_receipts), implementation.MAX_END_RECEIPTS)
        self.assertNotIn(session.sid, self.bridge.sessions)
        with patch('voice.bridge.time.monotonic', return_value=10**12):
            self.bridge.expire()
        self.assertEqual(self.bridge.end_receipts, {})

    async def test_drain_expiry_of_already_terminal_conversation_releases_active_capacity(self):
        await self.start()
        await self.settle()
        self.session = next(iter(self.bridge.sessions.values()))
        await self.terminal()
        self.assertTrue(self.session.ended)
        self.session.created -= self.bridge.settings.session_seconds + 1
        self.bridge.expire()
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        self.assertIn(self.session.sid, self.bridge.end_receipts)
        self.assertEqual(len(self.sent), 1)

    async def test_drain_ticket_expiry_preserves_dispatched_task_but_never_refreshes(self):
        session = await self.pending_create()
        session.caller_bootstrap._expire()
        self.assertFalse(self.cancelled.is_set())
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertEqual([item.get('action') for item in self.sent], ['END_CONVERSATION'])
        self.refresher.assert_not_awaited()

    async def test_drain_shutdown_waits_for_known_create_before_closing_http(self):
        await self.bridge.http.close()
        lifecycle = self.bridge.lifecycle(None)
        await anext(lifecycle)
        session = await self.pending_create()
        shutting = asyncio.create_task(anext(lifecycle))
        self.addAsyncCleanup(asyncio.gather, shutting, return_exceptions=True)
        await asyncio.sleep(.03)
        self.assertFalse(self.cancelled.is_set())
        self.release.set()
        await asyncio.gather(self.starting, return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(shutting, return_exceptions=True), 2)
        self.assertEqual([item.get('action') for item in self.sent], ['END_CONVERSATION'])
        self.assertIs(self.bridge.sessions[session.sid], session)
        self.assertFalse(session.ended)


class ServeCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_callback_listener_remains_open_during_ui_owned_drain(self):
        order = []
        ready = asyncio.Event()
        class Runner:
            def __init__(self, name): self.name = name
            async def setup(self): pass
            async def cleanup(self): order.append(self.name)
        ui, callbacks = Runner('ui_drain'), Runner('callbacks_close')
        class Site:
            def __init__(self, runner, *args): self.runner = runner
            async def start(self):
                if self.runner is callbacks: ready.set()
        bridge = SimpleNamespace(settings=implementation.Settings(), ui_app=lambda:None,
                                 callback_app=lambda:None)
        with patch.object(implementation.web, 'AppRunner', side_effect=[ui, callbacks]), \
                patch.object(implementation.web, 'TCPSite', Site):
            serving = asyncio.create_task(implementation.serve(bridge))
            await ready.wait()
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
        self.assertEqual(order, ['ui_drain', 'callbacks_close'])
