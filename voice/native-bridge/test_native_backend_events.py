"""Authenticated loopback event lineage; no ServiceNow/model/speech services."""
import asyncio
from pathlib import Path
import sys
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings
from native_bridge import Config, Dialog


class BackendEventTests(unittest.IsolatedAsyncioTestCase):
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
        self.bridge = Bridge(Settings(instance_url='https://fixture.example.test', user_id='fixture',
            defer_start_until_message=True, wait_for_input_control=True), 'token', 'audio', 'callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestServer(self.bridge.ui_app())
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.cb = TestClient(TestServer(self.bridge.callback_app()))
        await self.cb.start_server()
        self.dialog = Dialog(Config(backend_url=self.bridge.origin))
        await self.dialog.open()

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.dialog.shutdown()
        await self.cb.close()
        await self.ui.close()
        await self.bot.close()

    async def begin(self):
        ack = await self.dialog.request('POST', '/api/message', json={'text': 'Offline question.'})
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        return ack

    async def callback(self, body=(), **changes):
        value = {name: self.original[name] for name in ('requestId', 'clientSessionId', 'userId')}
        value.update(body=list(body), **changes)
        response = await self.cb.post('/callback', json=value,
            headers={'Authorization': 'Bearer callback'})
        await response.read()
        self.assertEqual(response.status, 200)

    async def state(self, after=0):
        return await self.dialog.request('GET', '/api/events', params={'after': str(after), 'wait': '0'})

    async def test_message_ack_names_the_exact_outbound_request(self):
        ack = await self.begin()
        self.assertEqual(ack.get('businessRequestId'), self.original['requestId'])

    async def test_distinct_types_keep_receipts_without_duplicating_legacy_text(self):
        await self.begin()
        text = 'Soll ich das tun?'
        await self.callback([{'uiType': 'OutputText', 'value': text},
                             {'uiType': 'Boolean', 'label': text, 'uniqueIdentifier': 'native-control-7'}])
        state = await self.state()
        self.assertEqual([event['text'] for event in state['events']], [text])
        events = state.get('backendEvents', [])
        self.assertEqual([event['uiType'] for event in events], ['OutputText', 'Boolean'])
        self.assertEqual([event['businessRequestId'] for event in events], [self.original['requestId']] * 2)
        self.assertTrue(all(event['source'] == 'servicenow_bridge_event' and
                            event['streamComplete'] is True for event in events))
        self.assertEqual(events[1]['controlUid'], 'native-control-7')
        await self.callback([{'uiType': 'OutputText', 'value': text},
                             {'uiType': 'Boolean', 'label': text, 'uniqueIdentifier': 'native-control-7'}])
        self.assertEqual((await self.state())['backendEvents'], events)
        self.assertEqual((await self.state(after=events[-1]['id']))['backendEvents'], [])

    async def test_output_without_completed_is_owned_information_while_still_busy(self):
        await self.begin()
        await self.callback([{'uiType': 'OutputText', 'value': 'The actual recorded result.'}])
        state = await self.state()
        self.assertTrue(state['busy'])
        self.assertFalse(state['ended'])
        self.assertEqual(state.get('backendState'), dict(source='servicenow_bridge_state',
            requestId=self.original['requestId'], action='MESSAGE', busy=True, ended=False, failed=False))
        self.assertEqual([event['text'] for event in state.get('backendEvents', [])],
                         ['The actual recorded result.'])

    async def test_wrong_request_and_partial_text_cannot_receive_a_receipt(self):
        await self.begin()
        await self.callback([{'uiType': 'OutputText', 'value': 'Old.'}], requestId='f' * 32)
        await self.callback([{'uiType': 'OutputText', 'value': 'Partial.', 'streaming': 'INPROGRESS'}])
        self.assertEqual((await self.state()).get('backendEvents', []), [])
        await self.callback([{'uiType': 'OutputText', 'value': 'Complete.'}])
        self.assertEqual([event['text'] for event in (await self.state()).get('backendEvents', [])], ['Complete.'])

    async def test_explicit_context_alias_keeps_original_business_lineage(self):
        await self.begin()
        session = next(iter(self.bridge.sessions.values()))
        alias = 'c' * 32
        session.context_requests.bind(alias, self.original['requestId'])
        await self.callback([{'uiType': 'OutputText', 'value': 'Aliased output.'}], requestId=alias)
        event = (await self.state())['backendEvents'][0]
        self.assertEqual(event['businessRequestId'], self.original['requestId'])
        self.assertNotEqual(event['businessRequestId'], alias)

    async def test_terminal_state_does_not_erase_reordered_final_receipts(self):
        await self.begin()
        await self.callback(completed=True)
        first = await self.state()
        self.assertTrue(first['backendState']['ended'])
        self.assertTrue(first['backendState']['busy'])
        await self.callback([{'uiType': 'OutputText', 'value': 'Recorded final information.'}])
        final = await self.state(after=first['cursor'])
        self.assertEqual([item['text'] for item in final['backendEvents']], ['Recorded final information.'])
        self.assertTrue(final['backendState']['ended'])

    async def test_reset_retires_the_exact_dialogue_owner(self):
        await self.begin()
        owner = self.dialog.backend_owner
        await self.dialog.close()
        self.assertIsNot(self.dialog.backend_owner, owner)
        self.assertEqual(self.dialog.business_request_id, '')
        self.assertIsNone(self.dialog.backend_state)
        self.assertIsNone(self.dialog.input_control)

    async def test_typed_dialog_callback_retains_exact_event_and_request(self):
        received = []

        async def deliver(event):
            received.append(event)

        try:
            turning = asyncio.create_task(self.dialog.turn('Offline typed question.', on_event=deliver))
            self.tasks.append(turning)
            await asyncio.sleep(0)
            if turning.done() and isinstance(turning.exception(), TypeError):
                self.fail('Dialog does not implement the typed event callback')
            self.original = await asyncio.wait_for(self.sent.get(), 1)
            await self.callback([{'uiType': 'OutputText', 'value': 'Actual output.'},
                                 {'uiType': 'Boolean', 'label': 'Genuine question?', 'uniqueIdentifier': 'control-8'}])
            self.assertEqual(await asyncio.wait_for(turning, 1), ['Actual output.', 'Genuine question?'])
        except TypeError as error:
            self.fail(f'Dialog does not implement the typed event callback: {error}')
        self.assertEqual([(event.ui_type, event.text, event.business_request_id) for event in received],
            [('OutputText', 'Actual output.', self.original['requestId']),
             ('Boolean', 'Genuine question?', self.original['requestId'])])
        self.assertEqual(received[-1].control_uid, 'control-8')


if __name__ == '__main__':
    unittest.main()
