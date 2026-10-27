"""Callback state revisions through real loopback Bridge event polling."""
import asyncio
from pathlib import Path
import sys
import unittest

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings


class ObservedChange(asyncio.Event):
    """Expose entry into the real long-poll wait without timing benchmarks."""
    def __init__(self):
        super().__init__()
        self.wait_entered = asyncio.Event()

    async def wait(self):
        self.wait_entered.set()
        return await super().wait()


class CallbackStateCursorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        self.tasks = []

        async def bot(request):
            self.sent.append(await request.json())
            return web.json_response({'status': 'success'})

        app = web.Application()
        app.router.add_post('/bot', bot)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(instance_url='https://instance.example.test',
            user_id='fixture-user', defer_start_until_message=False,
            wait_for_input_control=True), 'fixture-bot', 'fixture-audio', 'fixture-callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.cb = TestClient(TestServer(self.bridge.callback_app()))
        await self.cb.start_server()
        info = await (await self.ui.get('/api/session')).json()
        self.headers = {'Origin': self.bridge.origin, 'X-CSRF-Token': info['csrf']}
        response = await self.ui.post('/api/start', json={}, headers=self.headers)
        self.assertEqual(response.status, 202)
        await response.read()
        self.session = next(iter(self.bridge.sessions.values()))
        was_set = self.session.change.is_set()
        self.change = ObservedChange()
        if was_set:
            self.change.set()
        self.session.change = self.change
        self.before = await self.state()
        self.assertTrue(self.before['busy'])

    async def asyncTearDown(self):
        self.change.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.cb.close()
        await self.ui.close()
        await self.bot.close()

    def spawn(self, operation):
        task = asyncio.create_task(operation)
        self.tasks.append(task)
        return task

    async def state(self, after=0):
        response = await self.ui.get('/api/events',
            params={'after': str(after), 'wait': '0'}, headers=self.headers)
        self.assertEqual(response.status, 200)
        return await response.json()

    async def callback(self, body=None, **changes):
        original = self.sent[-1]
        envelope = {'clientSessionId': original['clientSessionId'],
                    'requestId': original['requestId'], 'userId': original['userId'],
                    'body': [] if body is None else body}
        envelope.update(changes)
        response = await self.cb.post('/callback', json=envelope,
            headers={'Authorization': 'Bearer fixture-callback'})
        self.assertEqual(response.status, 200)
        await response.read()

    async def state_without_waiting(self, after):
        self.change.wait_entered.clear()
        poll = self.spawn(self.ui.get('/api/events',
            params={'after': str(after), 'wait': '20'}, headers=self.headers))
        waiting = self.spawn(self.change.wait_entered.wait())
        try:
            done, _ = await asyncio.wait((poll, waiting), timeout=2,
                                         return_when=asyncio.FIRST_COMPLETED)
            self.assertIn(poll, done,
                'A callback state revision before GET must return without entering long-poll wait')
            response = await poll
            self.assertEqual(response.status, 200)
            return await response.json()
        finally:
            if not poll.done():
                self.change.set()
                await asyncio.wait_for(poll, 2)
            if poll.done() and not poll.cancelled() and poll.exception() is None:
                await poll.result().read()
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async def test_ready_callback_before_get_advances_cursor_without_text(self):
        await self.callback([{'uiType': 'InputText'}])
        self.assertFalse(self.session.busy)
        self.assertEqual(list(self.session.events), [])
        state = await self.state_without_waiting(self.before['cursor'])
        self.assertGreater(state['cursor'], self.before['cursor'])
        self.assertFalse(state['busy'])
        self.assertEqual(state['events'], [])

    async def test_terminal_callback_before_get_advances_cursor_without_text(self):
        await self.callback(completed=True)
        self.assertTrue(self.session.ended)
        self.assertEqual(list(self.session.events), [])
        state = await self.state_without_waiting(self.before['cursor'])
        self.assertGreater(state['cursor'], self.before['cursor'])
        self.assertTrue(state['ended'])
        self.assertFalse(state['busy'])
        self.assertEqual(state['events'], [])



    async def waiting_poll(self, after):
        self.change.wait_entered.clear()
        poll = self.spawn(self.ui.get('/api/events',
            params={'after': str(after), 'wait': '20'}, headers=self.headers))
        waiting = self.spawn(self.change.wait_entered.wait())
        try:
            done, _ = await asyncio.wait((poll, waiting), timeout=2,
                                         return_when=asyncio.FIRST_COMPLETED)
            self.assertIn(waiting, done,
                'Reading the same cursor without a state change must enter long-poll wait')
            self.assertFalse(poll.done())
            return poll
        finally:
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)

    async def test_reading_same_state_cursor_waits_until_the_next_change(self):
        await self.callback([{'uiType': 'InputText'}])
        ready = await self.state()
        self.assertGreater(ready['cursor'], self.before['cursor'])
        poll = await self.waiting_poll(ready['cursor'])
        await self.callback(completed=True)
        response = await asyncio.wait_for(poll, 2)
        state = await response.json()
        self.assertGreater(state['cursor'], ready['cursor'])
        self.assertTrue(state['ended'])
        self.assertEqual(state['events'], [])

    async def test_pending_poll_wakes_with_new_ready_cursor_without_text(self):
        poll = await self.waiting_poll(self.before['cursor'])
        await self.callback([{'uiType': 'InputText'}])
        response = await asyncio.wait_for(poll, 2)
        state = await response.json()
        self.assertGreater(state['cursor'], self.before['cursor'])
        self.assertFalse(state['busy'])
        self.assertEqual(state['events'], [])

    async def test_deduplicated_input_label_and_choices_change_cursor_without_new_text(self):
        prompt = 'Choose an available option.'
        await self.callback([{'uiType': 'OutputText', 'value': prompt}])
        spoken = await self.state()
        self.assertEqual([item['text'] for item in spoken['events']], [prompt])
        self.assertTrue(spoken['busy'])
        self.assertEqual(spoken['inputLabel'], '')
        await self.callback([{'uiType': 'Picker', 'label': prompt, 'options': [
            {'label': 'First option', 'value': 'first'},
            {'label': 'Second option', 'value': 'second'}]}])
        self.assertEqual(len(self.session.events), 1)
        state = await self.state_without_waiting(spoken['cursor'])
        self.assertGreater(state['cursor'], spoken['cursor'])
        self.assertFalse(state['busy'])
        self.assertEqual(state['inputLabel'], prompt)
        self.assertEqual(state['choices'], [
            {'label': 'First option', 'value': 'first'},
            {'label': 'Second option', 'value': 'second'}])
        self.assertEqual(state['events'], [])

    async def test_failed_callback_reports_current_state_and_monotonic_cursor(self):
        await self.callback([{'uiType': 'InputText', 'maskType': 'SECURE'}])
        state = await self.state_without_waiting(self.before['cursor'])
        self.assertGreater(state['cursor'], self.before['cursor'])
        self.assertTrue(state['failed'])
        self.assertFalse(state['busy'])
        self.assertEqual(state['choices'], [])
        self.assertEqual(state['inputLabel'], '')
        self.assertEqual(len(state['events']), 1)
        self.assertEqual(state['events'][0]['kind'], 'notice')

    async def test_text_ids_remain_monotonic_and_duplicate_callbacks_do_not_duplicate_text(self):
        first_text = 'First complete answer.'
        await self.callback([{'uiType': 'OutputText', 'value': first_text}])
        await self.callback([{'uiType': 'OutputText', 'value': first_text}])
        await self.callback([{'uiType': 'OutputText', 'value': first_text}],
                            streamState='END', streamActive=False)
        first = await self.state()
        self.assertEqual([item['text'] for item in first['events']], [first_text])
        self.assertEqual(len(self.session.events), 1)
        await self.callback([{'uiType': 'InputText'}])
        ready = await self.state(after=first['cursor'])
        self.assertGreater(ready['cursor'], first['cursor'])
        self.assertEqual(ready['events'], [])
        second_text = 'Second complete answer.'
        await self.callback([{'uiType': 'OutputText', 'value': second_text}])
        await self.callback([{'uiType': 'OutputText', 'value': second_text}])
        second = await self.state(after=ready['cursor'])
        self.assertEqual([item['text'] for item in second['events']], [second_text])
        self.assertGreater(second['events'][0]['id'], ready['cursor'])
        combined = first['events'] + second['events']
        identifiers = [item['id'] for item in combined]
        self.assertEqual(identifiers, sorted(set(identifiers)))
        self.assertEqual(len(self.session.events), 2)

if __name__ == '__main__':
    unittest.main()
