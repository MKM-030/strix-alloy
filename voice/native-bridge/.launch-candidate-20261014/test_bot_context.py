import sys
from pathlib import Path
import unittest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings, callback_metadata


class BotContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        async def receive(request):
            self.requests.append(await request.json())
            return web.json_response({'status':'success'})
        app = web.Application()
        app.router.add_post('/bot', receive)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(user_id='demo', defer_start_until_message=True),
                             'unit-sn', 'unit-audio', 'unit-callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        state = await (await self.ui.get('/api/session')).json()
        self.headers = {'Origin':self.bridge.origin, 'X-CSRF-Token':state['csrf']}
        self.session = next(iter(self.bridge.sessions.values()))
        await self.post('/api/start', {})

    async def asyncTearDown(self):
        await self.ui.close()
        await self.bot.close()

    async def post(self, path, value):
        return await self.ui.post(path, json=value, headers=self.headers)

    async def test_explicit_session_language_reaches_bot_context_not_user_text(self):
        self.bridge.settings.session_language = 'de'
        self.assertEqual((await self.post('/api/message', {'text':'Hallo'})).status, 202)
        self.assertEqual(self.requests[0]['contextVariables'], {'requester_session_language':'de'})
        self.assertEqual(self.requests[0]['message']['text'], 'Hallo')
        self.assertIs(self.requests[0]['message']['typed'], True)

    async def test_empty_language_preserves_existing_api_default(self):
        await self.post('/api/message', {'text':'Hello'})
        self.assertNotIn('contextVariables', self.requests[0])
        self.assertNotIn('botToBot', self.requests[0])

    def test_known_progress_metadata_does_not_log_text(self):
        data = callback_metadata({'body':[{'uiType':'ActionMsg', 'actionType':'DynamicLoader',
            'header':'PRIVATE_HEADER', 'progressMessages':[{'message':'PRIVATE_TEXT','status':'COMPLETED'}],
            'shouldUpdateParentMessage':True, 'parentMessageId':'PRIVATE_ID'}]})
        item = data['controls'][0]
        self.assertEqual(item['actionType'], 'DynamicLoader')
        self.assertEqual(item['progressStatuses'], ['COMPLETED'])
        self.assertIs(item['shouldUpdateParentMessage'], True)
        self.assertNotIn('PRIVATE_', str(data))

    async def test_actual_bot_history_is_first_message_only(self):
        item = {'isBotMessage':True, 'value':'Hallo, ich helfe Ihnen bei der Laptopdemo.',
                'displayName':'Bot', 'type':'text', 'timestamp':'1791890700000'}
        self.assertEqual((await self.post('/api/message', {'text':'Hallo', 'history':[item]})).status, 202)
        self.assertEqual(self.requests[0]['history'], [item])
        self.bridge.consume(self.session, {'body':[{'uiType':'InputText'}]})
        self.assertEqual((await self.post('/api/message', {'text':'Laptop', 'history':[item]})).status, 400)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual((await self.post('/api/message', {'text':'Laptop'})).status, 202)
        self.assertNotIn('history', self.requests[1])

    async def test_initial_history_capability_is_false_after_request_or_nondeferred_start(self):
        state = await (await self.ui.get('/api/session')).json()
        self.assertIs(state['initialBotHistoryAllowed'], True)
        await self.post('/api/message', {'text':'Hallo'})
        state = await (await self.ui.get('/api/session')).json()
        self.assertIs(state['initialBotHistoryAllowed'], False)
        self.bridge.settings.defer_start_until_message = False
        self.session.requests.clear()
        state = await (await self.ui.get('/api/session')).json()
        self.assertIs(state['initialBotHistoryAllowed'], False)

    async def test_client_cannot_insert_user_intent_or_attachments_into_history(self):
        valid = {'isBotMessage':True, 'value':'Hallo.', 'displayName':'Bot',
                 'type':'text', 'timestamp':'1791890700000'}
        for item in [dict(valid, isBotMessage=False), dict(valid, type='attachment'),
                     dict(valid, value='x'*4001), dict(valid, timestamp='today'),
                     dict(valid, attachment={'url':'https://invalid.test'})]:
            with self.subTest(item_keys=list(item)):
                self.assertEqual((await self.post('/api/message', {'text':'Hallo','history':[item]})).status, 400)
        self.assertEqual(self.requests, [])

    def test_metadata_keeps_control_flags_and_omits_dialogue_and_secrets(self):
        actual = callback_metadata({'streamState':'END', 'streamActive':False,
            'takeControl':True, 'completed':False, 'userId':'PRIVATE_USER', 'PRIVATE_KEY':'x',
            'body':[{'uiType':'ActionMsg','actionType':'EndTypingIndicator',
                     'value':'PRIVATE_TRANSCRIPT', 'Authorization':'PRIVATE_TOKEN'},
                    {'uiType':'PRIVATE_ENUM','actionType':'PRIVATE_TOKEN','PRIVATE_KEY':'x'}]})
        self.assertEqual(actual['streamState'], 'END')
        self.assertIs(actual['takeControl'], True)
        self.assertEqual(actual['controls'][0]['actionType'], 'EndTypingIndicator')
        self.assertEqual(actual['controls'][1]['actionType'], 'other')
        self.assertEqual(actual['unknown_key_count'], 1)
        self.assertNotIn('PRIVATE_', str(actual))


if __name__ == '__main__':
    unittest.main()
