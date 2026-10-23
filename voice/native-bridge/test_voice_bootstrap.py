"""Native Voice bootstrap lifecycle through real local Bridge HTTP endpoints.

Every server is loopback-only; no model, ServiceNow, or speech service is used.
"""
import asyncio
from pathlib import Path
import sys
import unittest

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

from assistant_settings import CallSettings
from native_bridge import Config, Dialog
from test_assistant_settings import authorized_settings, SERVICE, AGENT

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings


class VoiceBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        self.tasks = []
        self.create_ack_error = False
        self.end_ack_failures = 0

        async def receive(request):
            payload = await request.json()
            self.sent.append(payload)
            if payload.get('action') == 'CREATE_CONVERSATION' and self.create_ack_error:
                return web.json_response({'error': 'synthetic uncertain create ACK'}, status=502)
            if payload.get('action') == 'END_CONVERSATION' and self.end_ack_failures:
                self.end_ack_failures -= 1
                return web.json_response({'error': 'synthetic END ACK failure'}, status=502)
            return web.json_response({'status': 'success'})

        app = web.Application()
        app.router.add_post('/bot', receive)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(instance_url='https://instance.example.test',
            user_id='fixture-user', defer_start_until_message=True,
            wait_for_input_control=True), 'fixture-bot', 'fixture-audio', 'fixture-callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.callback_client = TestClient(TestServer(self.bridge.callback_app()))
        await self.callback_client.start_server()
        self.call_settings = CallSettings.from_authorized_response(
            authorized_settings(), SERVICE, AGENT)
        self.context = self.call_settings.native_context()
        self.dialog = Dialog(Config(backend_url=self.bridge.origin), self.call_settings)

    async def asyncTearDown(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.dialog.shutdown()
        await self.callback_client.close()
        await self.ui.close()
        await self.bot.close()

    def spawn(self, operation):
        task = asyncio.create_task(operation)
        self.tasks.append(task)
        return task

    async def wait_for_sent(self, count, operation=None):
        for _ in range(200):
            if len(self.sent) >= count or operation is not None and operation.done():
                break
            await asyncio.sleep(.005)
        self.assertGreaterEqual(len(self.sent), count,
            'Native profile startup must enqueue its empty CREATE before becoming ready')

    async def begin_bootstrap(self):
        opening = self.spawn(self.dialog.open())
        await self.wait_for_sent(1, opening)
        creation = self.sent[0]
        self.assertEqual(creation.get('action'), 'CREATE_CONVERSATION')
        self.assertEqual(creation['message']['text'], '')
        self.assertEqual(creation['contextVariables'], self.context)
        self.assertEqual(len(creation['contextVariables']), 6)
        await asyncio.sleep(.02)
        self.assertFalse(opening.done(), 'The enqueue ACK does not make Native Voice ready')
        return opening, creation

    async def callback(self, original, body, **changes):
        envelope = {'clientSessionId': original['clientSessionId'],
                    'requestId': original['requestId'], 'userId': original['userId'],
                    'body': body}
        envelope.update(changes)
        response = await self.callback_client.post('/callback', json=envelope,
            headers={'Authorization': 'Bearer fixture-callback'})
        self.assertEqual(response.status, 200)
        await response.read()
        return response

    async def ready(self, opening, creation):
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation',
              'conversationId': 'native-conversation-fixture',
              'interactionId': 'native-interaction-fixture',
              'messageId': 'native-create-message-fixture'}])
        await self.wait_for_sent(2, opening)
        starting = self.sent[1]
        self.assertEqual(starting['action'], 'START_CREATED_CONVERSATION')
        self.assertEqual(starting['message']['text'], '')
        self.assertEqual(starting['contextVariables'], self.context)
        await self.callback(starting, [{'uiType': 'InputText'}])
        return await asyncio.wait_for(opening, 2)

    async def assert_open_waiting(self, opening):
        await asyncio.sleep(.02)
        self.assertFalse(opening.done())
        self.assertTrue(next(iter(self.bridge.sessions.values())).busy)
        self.assertEqual(len(self.sent), 1)

    async def test_six_field_create_precedes_first_real_utterance_and_waits_for_ready(self):
        opening, creation = await self.begin_bootstrap()
        first_text = 'Describe the available laptop support.'
        async with self.dialog.http.post(self.bridge.origin + '/api/message',
                json={'text': first_text, 'voice_context': self.context},
                headers={'Origin': self.bridge.origin, 'X-CSRF-Token': self.dialog.csrf}) as response:
            self.assertEqual(response.status, 409)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(await self.ready(opening, creation), [])
        self.assertTrue(self.dialog.first_message_pending)
        self.assertFalse(self.dialog.greeting_history_allowed)
        self.dialog.record_greeting('Actually spoken local intro.')
        self.assertEqual(self.dialog.greeting_history, [])
        turning = self.spawn(self.dialog.turn(first_text))
        await self.wait_for_sent(3, turning)
        message = self.sent[2]
        self.assertNotIn('action', message)
        self.assertEqual(message['message']['text'], first_text)
        self.assertNotIn('nowSessionId', message)
        self.assertEqual(message['clientSessionId'], creation['clientSessionId'])
        self.assertEqual(message['userId'], creation['userId'])
        self.assertEqual(message['contextVariables'], self.context)
        self.assertNotIn('history', message)
        self.assertFalse(self.dialog.first_message_pending)
        await self.callback(message, [{'uiType': 'OutputText', 'value': 'A concise answer.'},
                                      {'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), ['A concise answer.'])

    async def test_bootstrap_partial_and_stream_end_do_not_release_even_without_input_wait(self):
        self.bridge.settings.wait_for_input_control = False
        opening, creation = await self.begin_bootstrap()
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}],
            streamState='START', streamActive=True)
        await self.assert_open_waiting(opening)
        await self.callback(creation,
            [{'uiType': 'OutputText', 'value': 'Bootstrap output.'}],
            streamState='END', streamActive=False)
        await self.assert_open_waiting(opening)
        self.assertEqual(await self.ready(opening, creation), [])

    async def test_unmatched_session_start_conversation_does_not_release_bootstrap(self):
        opening, creation = await self.begin_bootstrap()
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}],
            clientSessionId='unmatched-session')
        await self.assert_open_waiting(opening)
        self.assertEqual(await self.ready(opening, creation), [])

    async def test_wrong_request_start_conversation_does_not_release_bootstrap(self):
        opening, creation = await self.begin_bootstrap()
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}],
            requestId='0' * 32)
        await self.assert_open_waiting(opening)
        self.assertEqual(await self.ready(opening, creation), [])

    async def test_normal_message_start_conversation_and_interim_end_do_not_release(self):
        opening, creation = await self.begin_bootstrap()
        await self.ready(opening, creation)
        turning = self.spawn(self.dialog.turn('Describe laptop support without taking action.'))
        await self.wait_for_sent(3, turning)
        message = self.sent[2]
        self.assertNotIn('action', message)
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.callback(message,
            [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.callback(message,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}])
        await self.callback(message,
            [{'uiType': 'OutputText', 'value': 'Work is continuing.'}],
            streamState='END', streamActive=False)
        await asyncio.sleep(.02)
        self.assertFalse(turning.done())
        self.assertTrue(next(iter(self.bridge.sessions.values())).busy)
        await self.callback(message, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), ['Work is continuing.'])
        self.assertEqual(len(self.sent), 3)

    async def test_start_confirmation_does_not_confirm_pending_create(self):
        opening, creation = await self.begin_bootstrap()
        await self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.assert_open_waiting(opening)
        self.assertEqual(await self.ready(opening, creation), [])

    async def test_legacy_start_requires_its_own_confirmation(self):
        self.bridge.settings.defer_start_until_message = False
        legacy = {key: value for key, value in self.context.items()
                  if key != 'global_context_profile'}
        info = await (await self.ui.get('/api/session')).json()
        headers = {'Origin': self.bridge.origin, 'X-CSRF-Token': info['csrf']}
        response = await self.ui.post('/api/start', json={'voice_context': legacy}, headers=headers)
        self.assertEqual(response.status, 202)
        startup = self.sent[0]
        self.assertEqual(startup['action'], 'START_CONVERSATION')
        await self.callback(startup,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}])
        self.assertTrue(next(iter(self.bridge.sessions.values())).busy)
        await self.callback(startup,
            [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        self.assertFalse(next(iter(self.bridge.sessions.values())).busy)

    async def test_legacy_five_field_context_keeps_deferred_first_message(self):
        legacy = {key: value for key, value in self.context.items()
                  if key != 'global_context_profile'}
        info = await (await self.ui.get('/api/session')).json()
        headers = {'Origin': self.bridge.origin, 'X-CSRF-Token': info['csrf']}
        response = await self.ui.post('/api/start', json={'voice_context': legacy}, headers=headers)
        self.assertEqual(response.status, 202)
        self.assertEqual(self.sent, [])
        session = next(iter(self.bridge.sessions.values()))
        self.assertFalse(session.busy)
        response = await self.ui.post('/api/message',
            json={'text': 'A legacy first utterance.', 'voice_context': legacy}, headers=headers)
        self.assertEqual(response.status, 202)
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn('action', self.sent[0])
        self.assertEqual(self.sent[0]['message']['text'], 'A legacy first utterance.')
        self.assertEqual(self.sent[0]['contextVariables'], legacy)
        self.assertEqual(len(legacy), 5)

    async def test_uncertain_create_ack_retains_cookie_and_retries_only_owned_end(self):
        self.create_ack_error = True
        self.end_ack_failures = 1
        with self.assertLogs('voice-bridge', level='WARNING') as bot_logs:
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(self.dialog.open(), 2)
        self.assertEqual([record.getMessage() for record in bot_logs.records],
                         ['Bot request failed; no credentials or payload logged'])
        self.assertEqual([item.get('action') for item in self.sent], ['CREATE_CONVERSATION'])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertIsNotNone(self.dialog.http)
        self.assertTrue(any(cookie.key == 'scc_voice' and cookie.value == owned.sid
                            for cookie in self.dialog.http.cookie_jar))
        with self.assertLogs('voice-bridge', level='WARNING') as bot_logs:
            with self.assertLogs('native-voice', level='WARNING'):
                await self.dialog.close()
        self.assertEqual([record.getMessage() for record in bot_logs.records],
                         ['Bot request failed; no credentials or payload logged'])
        self.assertTrue(self.dialog.must_reset)
        self.assertIsNotNone(self.dialog.http)
        self.assertIn(owned.sid, self.bridge.sessions)
        self.assertTrue(any(cookie.key == 'scc_voice' and cookie.value == owned.sid
                            for cookie in self.dialog.http.cookie_jar))
        await self.dialog.close()
        self.assertEqual([item.get('action') for item in self.sent],
                         ['CREATE_CONVERSATION', 'END_CONVERSATION', 'END_CONVERSATION'])
        self.assertTrue(all(item['message']['text'] == '' for item in self.sent))
        self.assertFalse(self.bridge.sessions)
        self.assertFalse(self.dialog.must_reset)
        self.assertEqual(self.dialog.greeting_history, [])


if __name__ == '__main__':
    unittest.main()
