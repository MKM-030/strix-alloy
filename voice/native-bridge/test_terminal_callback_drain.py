"""Offline regression: final callbacks may follow a terminal-only callback."""
import asyncio
from pathlib import Path
import sys
import unittest

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings
from native_bridge import Config, Dialog


class TerminalCallbackDrainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = asyncio.Queue()
        self.tasks = []

        async def bot(request):
            await self.sent.put(await request.json())
            return web.json_response({'status': 'success'})

        app = web.Application()
        app.router.add_post('/bot', bot)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(instance_url='https://fixture.example.test',
            user_id='fixture-user', defer_start_until_message=True,
            wait_for_input_control=True), 'fixture-bot', 'fixture-audio', 'fixture-callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.cb = TestClient(TestServer(self.bridge.callback_app()))
        await self.cb.start_server()
        self.dialog = Dialog(Config(backend_url=self.bridge.origin))
        await self.dialog.open()
        self.session = next(iter(self.bridge.sessions.values()))

    async def asyncTearDown(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.dialog.shutdown()
        await self.cb.close()
        await self.ui.close()
        await self.bot.close()

    async def begin_turn(self):
        self.spoken = []

        async def deliver(text):
            self.spoken.append(text)

        task = asyncio.create_task(self.dialog.turn('Fixture question.', on_reply=deliver))
        self.tasks.append(task)
        self.original = await asyncio.wait_for(self.sent.get(), 2)
        self.assertNotIn('action', self.original)
        return task

    async def callback(self, body=None, expected_status=200, **changes):
        data = {key: self.original[key] for key in ('clientSessionId', 'requestId', 'userId')}
        data['body'] = [] if body is None else body
        data.update(changes)
        response = await self.cb.post('/callback', json=data,
            headers={'Authorization': 'Bearer fixture-callback'})
        self.assertEqual(response.status, expected_status)
        await response.read()

    async def state(self, after=0):
        return await self.dialog.request('GET', '/api/events',
            params={'after': str(after), 'wait': '0'})

    async def assert_draining(self):
        state = await self.state()
        self.assertTrue(state['ended'], 'Terminal state must block another user turn immediately')
        self.assertTrue(state['busy'], 'Terminal-only callbacks must keep the current reply drain open')
        return state

    async def test_terminal_before_final_output_reaches_native_reply_delivery_once(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        for text in ('First final sentence.', 'Second final sentence.', 'Third final sentence.'):
            body = [{'uiType': 'OutputText', 'value': text}]
            await self.callback(body)
            await self.callback(body)
            await self.callback(body, streamState='END', streamActive=False)
        self.assertEqual(await asyncio.wait_for(turning, 3),
            ['First final sentence.', 'Second final sentence.', 'Third final sentence.'])
        self.assertEqual(self.spoken,
            ['First final sentence.', 'Second final sentence.', 'Third final sentence.'])
        state = await self.state()
        self.assertTrue(state['ended'])
        self.assertFalse(state['busy'])

    async def test_terminal_only_finishes_at_deadline_even_after_cursor_was_consumed(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        state = await self.assert_draining()
        self.assertEqual(await asyncio.wait_for(turning, 3), [])
        final = await self.state(after=state['cursor'])
        self.assertGreater(final['cursor'], state['cursor'])
        self.assertFalse(final['busy'])
        self.assertFalse(final['failed'])
        self.assertTrue(final['ended'])

    async def test_duplicate_terminal_does_not_extend_the_original_deadline(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        await asyncio.sleep(1.5)
        await self.callback(completed=True, streamActive=False)
        self.assertEqual(await asyncio.wait_for(turning, 1.3), [])

    async def test_normal_output_before_terminal_and_same_envelope_output_survive(self):
        turning = await self.begin_turn()
        await self.callback([{'uiType': 'OutputText', 'value': 'Before terminal.'}])
        await self.callback([{'uiType': 'OutputText', 'value': 'With terminal.'}], completed=True)
        self.assertEqual(await asyncio.wait_for(turning, 3), ['Before terminal.', 'With terminal.'])
        self.assertEqual(self.spoken, ['Before terminal.', 'With terminal.'])

    async def test_drain_accepts_only_final_text_and_never_reopens_input(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        await self.callback([{'uiType': 'InputText', 'label': 'Must not become another question.'}])
        await self.callback([{'uiType': 'Picker', 'label': 'Do not reopen.',
                              'options': [{'label': 'Item', 'value': 'item'}]}])
        await self.callback([{'uiType': 'OutputText', 'value': 'Partial.', 'streaming': 'INPROGRESS'}])
        await self.callback([{'uiType': 'OutputText', 'value': 'Envelope partial.'}],
                            streamState='INPROGRESS', streamActive=True)
        response = await self.dialog.http.post(self.bridge.origin + '/api/message',
            json={'text': 'Another turn.'},
            headers={'Origin': self.bridge.origin, 'X-CSRF-Token': self.dialog.csrf})
        self.assertEqual(response.status, 409)
        await response.read()
        state = await self.state()
        self.assertEqual(state['choices'], [])
        self.assertEqual(state['inputLabel'], '')
        self.assertEqual(await asyncio.wait_for(turning, 3), [])

    async def test_stale_request_other_session_and_wrong_identity_cannot_enter_drain(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        body = [{'uiType': 'OutputText', 'value': 'Must not be delivered.'}]
        await self.callback(body, requestId='stale-request')
        await self.callback(body, clientSessionId='another-session')
        await self.callback(body, userId='another-user', expected_status=400)
        self.assertEqual(await asyncio.wait_for(turning, 3), [])
        self.assertEqual(self.spoken, [])

    async def test_expired_drain_rejects_late_output(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        self.assertEqual(await asyncio.wait_for(turning, 3), [])
        await self.callback([{'uiType': 'OutputText', 'value': 'Too late.'}])
        self.assertEqual((await self.state())['events'], [])

    async def test_explicit_end_discards_pending_output_and_cannot_revive_session(self):
        await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        await self.dialog.close()
        await self.callback([{'uiType': 'OutputText', 'value': 'After explicit end.'}])
        self.assertNotIn(self.session.sid, self.bridge.sessions)
        self.assertEqual(list(self.session.events), [])
        self.assertTrue(self.session.ended)

    async def test_ending_flag_fences_callback_before_end_lock_is_acquired(self):
        await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        self.session.ending = True
        await self.callback([{'uiType': 'OutputText', 'value': 'During explicit end.'}])
        self.assertEqual(list(self.session.events), [])

    async def test_failed_session_cannot_accept_final_output(self):
        await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        self.session.failed = True
        await self.callback([{'uiType': 'OutputText', 'value': 'After failure.'}])
        self.assertEqual(list(self.session.events), [])

    async def test_secure_final_text_never_reaches_native_reply_delivery(self):
        turning = await self.begin_turn()
        await self.callback(completed=True)
        await self.assert_draining()
        await self.callback([{'uiType': 'OutputText', 'value': 'Protected.', 'maskType': 'SECURE'}])
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(turning, 3)
        self.assertEqual(self.spoken, [])


if __name__ == '__main__':
    unittest.main()
