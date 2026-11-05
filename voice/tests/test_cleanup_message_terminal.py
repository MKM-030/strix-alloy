"""Saved-call regression: keep the exact pending MESSAGE terminal owned across END.
Local synthetic HTTP only. No model, ServiceNow, SDK or process operations.
"""
import asyncio
from dataclasses import replace
import unittest
from aiohttp import web
from aiohttp.test_utils import TestServer
from voice.bridge import Conversation
from voice.tests import test_create_drain as drain_fixture


class PendingTerminalOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await drain_fixture.CreateDrainTests.asyncSetUp(self)
        self.end_entered, self.end_gate = asyncio.Event(), asyncio.Event()
        self.end_gate.set()
        self.addCleanup(self.end_gate.set)
        self.end_status = 200
        async def bot(request):
            payload = await request.json()
            self.sent.append(payload)
            if payload.get('action') == 'END_CONVERSATION':
                self.end_entered.set()
                await self.end_gate.wait()
                if self.end_status != 200:
                    return web.Response(status=self.end_status)
            return web.json_response({'status':'success'})
        app = web.Application()
        app.router.add_post('/bot', bot)
        bot_server = TestServer(app)
        await bot_server.start_server()
        self.addAsyncCleanup(bot_server.close)
        self.bridge.bot_url = str(bot_server.make_url('/bot'))
    start = drain_fixture.CreateDrainTests.start
    settle = drain_fixture.CreateDrainTests.settle
    close_request = drain_fixture.CreateDrainTests.close_request
    terminal = drain_fixture.CreateDrainTests.terminal

    async def pending_message_then_end(self, *, drain=True):
        await self.start()
        await self.settle()
        self.session = next(iter(self.bridge.sessions.values()))
        await self.terminal(completed=False, body=[{'uiType':'InputText', 'label':'Name?'}])
        response = await self.ui.post('/api/message', json={'text':'Synthetic caller facts'},
                                      headers=self.headers)
        self.assertEqual(response.status, 202)
        await response.read()
        self.pending = self.sent[-1]
        response, info = await self.close_request()
        self.assertEqual(response.status, 202)
        self.assertIs(info['ended'], False)
        await asyncio.wait_for(self.end_entered.wait(), 1)
        if drain:
            await asyncio.wait_for(self.session.cleanup_task, 1)
        self.end = self.sent[-1]
        self.assertEqual([p.get('action') for p in self.sent],
                         ['START_CREATED_CONVERSATION', None, 'END_CONVERSATION'])
        self.assertEqual(self.session.cleanup_state, 'end_enqueued' if drain else 'ending')

    async def late_terminal(self, **changes):
        data = dict(requestId=self.pending['requestId'], clientSessionId=self.session.sid,
                    userId=self.session.user_id, completed=True, body=[])
        data.update(changes)
        response = await self.callbacks.post('/callback', json=data,
            headers={'Authorization':'Bearer callback-secret'})
        self.assertEqual(response.status, 200)
        await response.read()

    async def test_pending_owned_message_terminal_settles_conversation_after_end(self):
        # Break caught: replacing the current request with END loses the pending
        # MESSAGE's authoritative conversation-terminal callback.
        await self.pending_message_then_end()
        events = list(self.session.events)
        await self.late_terminal(body=[{'uiType':'OutputText','value':'Never publish this closing output'}])
        self.assertTrue(self.session.ended,
            'Exact previously outstanding MESSAGE completed=True must settle owned conversation cleanup')
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        response, info = await self.close_request()
        self.assertEqual(response.status, 200)
        self.assertIs(info['ended'], True)
        self.assertEqual(len(self.sent), 3, 'Observers must never replay MESSAGE or END')
        self.assertEqual(list(self.session.events), events)

    async def test_other_old_or_nonterminal_callbacks_never_release_cleanup(self):
        await self.pending_message_then_end()
        for changes in ({'completed':False}, {'completed':None}, {'requestId':'f'*32},
                        {'requestId':self.session.caller_create_request_id},
                        {'requestId':self.sent[0]['requestId']}, {'userId':'foreign'},
                        {'userId':None}, {'streamActive':True}, {'streamState':'INPROGRESS'},
                        {'clientSessionId':'foreign'}, {'completed':1}, {'streamState':'START'}):
            with self.subTest(changes=changes):
                await self.late_terminal(**changes)
                self.assertFalse(self.session.ended)
                self.assertIn(self.session.sid, self.bridge.sessions)
        self.assertEqual(len(self.sent), 3)

    async def test_terminal_during_end_http_wait_retains_capacity_until_ack(self):
        self.end_gate.clear()
        await self.pending_message_then_end(drain=False)
        await self.late_terminal()
        self.assertFalse(self.session.ended, 'Terminal must not orphan an undrained owned END')
        self.assertIn(self.session.sid, self.bridge.sessions)
        self.end_gate.set()
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertTrue(self.session.ended, 'Drained END must consume the exact saved terminal')
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        self.assertEqual(len(self.sent), 3)

    async def test_terminal_before_end_dispatch_is_saved_without_replaying_end(self):
        await self.start()
        await self.settle()
        self.session = next(iter(self.bridge.sessions.values()))
        await self.terminal(completed=False, body=[{'uiType':'InputText','label':'Name?'}])
        response = await self.ui.post('/api/message', json={'text':'Synthetic caller facts'},
                                      headers=self.headers)
        self.assertEqual(response.status, 202)
        await response.read()
        self.pending = self.sent[-1]
        async with self.session.lock:
            response, _ = await self.close_request()
            self.assertEqual(response.status, 202)
            await self.late_terminal()
            self.assertFalse(self.session.ended)
            self.assertEqual(len(self.sent), 2)
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertTrue(self.session.ended)
        self.assertEqual(len(self.sent), 3)

    async def assert_ownership_change_retires_terminal(self, target, field, value):
        before = getattr(target, field)
        setattr(target, field, value)
        await self.late_terminal()
        self.assertFalse(self.session.ended)
        self.assertIn(self.session.sid, self.bridge.sessions)
        setattr(target, field, before)
        await self.late_terminal()
        self.assertFalse(self.session.ended, 'Restoring fields must not rearm observed changed ownership')
        self.assertEqual(len(self.sent), 3)

    async def test_changed_caller_permanently_retires_terminal(self):
        await self.pending_message_then_end()
        await self.assert_ownership_change_retires_terminal(self.session, 'caller_user_id', 'f'*32)

    async def test_changed_destination_permanently_retires_terminal(self):
        await self.pending_message_then_end()
        await self.assert_ownership_change_retires_terminal(self.bridge, 'bot_url', self.bridge.bot_url + '/other')

    async def test_changed_conversation_permanently_retires_terminal(self):
        await self.pending_message_then_end()
        await self.assert_ownership_change_retires_terminal(self.session, 'conversation_binding',
            replace(self.session.conversation_binding, conversation_id='f'*32))

    async def test_changed_create_request_permanently_retires_terminal(self):
        await self.pending_message_then_end()
        await self.assert_ownership_change_retires_terminal(self.session, 'caller_create_request_id', 'f'*32)

    async def test_new_current_request_permanently_retires_terminal(self):
        await self.pending_message_then_end()
        self.session.requests.append('f'*32)
        await self.late_terminal()
        self.assertFalse(self.session.ended)
        self.session.requests.pop()
        await self.late_terminal()
        self.assertFalse(self.session.ended)
        self.assertEqual(len(self.sent), 3)

    async def test_replaced_session_cannot_consume_saved_terminal_during_end(self):
        self.end_gate.clear()
        await self.pending_message_then_end(drain=False)
        original = self.session
        self.bridge.sessions[original.sid] = Conversation(sid=original.sid)
        await self.late_terminal()
        self.assertFalse(original.ended)
        self.end_gate.set()
        await asyncio.wait_for(original.cleanup_task, 1)
        self.assertFalse(original.ended)
        self.bridge.sessions[original.sid] = original
        await self.late_terminal()
        self.assertFalse(original.ended, 'END drain observed new ownership and must retire its latch')

    async def test_failed_end_ack_does_not_release_or_replay_from_saved_terminal(self):
        self.end_gate.clear()
        self.end_status = 502
        await self.pending_message_then_end(drain=False)
        await self.late_terminal()
        self.end_gate.set()
        await asyncio.wait_for(self.session.cleanup_task, 1)
        self.assertFalse(self.session.ended)
        self.assertEqual(self.session.cleanup_state, 'unresolved')
        for _ in range(2):
            _, info = await self.close_request()
            self.assertIs(info['ended'], False)
        self.assertEqual(len(self.sent), 3)

    async def test_exact_end_terminal_still_releases_cleanup_without_model_health(self):
        await self.pending_message_then_end()
        await self.terminal()
        self.assertTrue(self.session.ended)
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        response, info = await self.close_request()
        self.assertEqual(response.status, 200)
        self.assertIs(info['ended'], True)
        self.assertEqual(len(self.sent), 3)




if __name__ == '__main__':
    unittest.main(verbosity=2)
