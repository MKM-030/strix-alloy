"""Offline CREATE -> START_CREATED -> input readiness through real local HTTP."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

from assistant_settings import CallSettings
from aiortc import RTCConfiguration
from native_bridge import Config, Dialog, NativeCall
from test_assistant_settings import authorized_settings, SERVICE, AGENT

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings


class CreatedLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        self.tasks = []
        self.create_ack_gate = asyncio.Event()
        self.create_ack_gate.set()
        self.start_ack_gate = asyncio.Event()
        self.start_ack_gate.set()
        self.start_ack_error = False
        async def receive(request):
            payload = await request.json()
            self.sent.append(payload)
            if payload.get('action') == 'CREATE_CONVERSATION':
                await self.create_ack_gate.wait()
            if payload.get('action') == 'START_CREATED_CONVERSATION':
                await self.start_ack_gate.wait()
                if self.start_ack_error:
                    return web.json_response({'error': 'synthetic uncertain START enqueue'}, status=502)
            return web.json_response({'status': 'success'})
        bot_app = web.Application()
        bot_app.router.add_post('/bot', receive)
        self.bot = TestServer(bot_app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(instance_url='https://fixture.example.test',
            user_id='owned-fixture-user', defer_start_until_message=True,
            wait_for_input_control=True), 'fixture-bot', 'fixture-audio', 'fixture-callback')
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.callbacks = TestClient(TestServer(self.bridge.callback_app()))
        await self.callbacks.start_server()
        self.call_settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        self.context = self.call_settings.native_context()
        self.dialog = Dialog(Config(backend_url=self.bridge.origin), self.call_settings)

    async def asyncTearDown(self):
        self.create_ack_gate.set()
        self.start_ack_gate.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.dialog.shutdown()
        await self.callbacks.close()
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
            'A matched native CREATE callback must enqueue one empty START_CREATED_CONVERSATION')

    async def callback(self, original, body, expected_status=200, **changes):
        envelope = {'clientSessionId': original['clientSessionId'],
                    'requestId': original['requestId'], 'userId': original['userId'], 'body': body}
        envelope.update(changes)
        response = await self.callbacks.post('/callback', json=envelope,
            headers={'Authorization': 'Bearer fixture-callback'})
        self.assertEqual(response.status, expected_status)
        await response.read()

    async def begin_create(self):
        opening = self.spawn(self.dialog.open())
        await self.wait_for_sent(1, opening)
        creation = self.sent[0]
        self.assertEqual(creation.get('action'), 'CREATE_CONVERSATION')
        self.assertEqual(creation['message']['text'], '')
        self.assertEqual(creation['contextVariables'], self.context)
        await asyncio.sleep(.01)
        self.assertFalse(opening.done())
        return opening, creation

    async def create_confirmed(self, opening, creation):
        await self.callback(creation, [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation',
            'conversationId': 'native-conversation-fixture', 'interactionId': 'native-interaction-fixture'}])
        await self.wait_for_sent(2, opening)
        startup = self.sent[1]
        self.assertEqual(startup.get('action'), 'START_CREATED_CONVERSATION')
        return startup

    async def assert_waiting(self, opening):
        await asyncio.sleep(.02)
        self.assertFalse(opening.done(), 'Creation/start markers do not prove input readiness')
        self.assertTrue(next(iter(self.bridge.sessions.values())).busy)

    async def test_matched_create_enqueues_one_empty_start_created_and_keeps_dialog_waiting(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        self.assertEqual(startup['message']['text'], '')
        self.assertIs(startup['message']['typed'], True)
        for key in ('clientSessionId', 'userId', 'contextVariables'):
            self.assertEqual(startup[key], creation[key])
        self.assertNotEqual(startup['requestId'], creation['requestId'])
        self.assertNotIn('nowSessionId', startup)
        await self.assert_waiting(opening)
        self.assertEqual([payload.get('action') for payload in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION'])

    async def test_start_markers_and_stream_end_do_not_release_before_inputtext(self):
        self.bridge.settings.wait_for_input_control = False
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.assert_waiting(opening)
        await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Startup output.'}],
                            streamState='END', streamActive=False)
        await self.assert_waiting(opening)
        await self.callback(startup, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        self.assertEqual(len(self.sent), 2)

    async def test_topic_picker_releases_start_created_then_first_business_once(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'TopicPickerControl', 'label': 'Choose support.', 'options': [
            {'label': 'Support', 'value': 'support'}]}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertEqual(owned.input_label, 'Choose support.')
        self.assertEqual(owned.choices, [{'label': 'Support', 'value': 'support'}])
        turning = self.spawn(self.dialog.turn('Describe support without taking action.'))
        await self.wait_for_sent(3, turning)
        message = self.sent[2]
        self.assertNotIn('action', message)
        self.assertEqual(message['message']['text'], 'Describe support without taking action.')
        self.assertNotIn('nowSessionId', message)
        self.assertNotIn('history', message)
        await self.callback(message, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), [])
        self.assertEqual(len(self.sent), 3)

    async def test_stale_wrong_and_duplicate_callbacks_cannot_enqueue_another_start(self):
        opening, creation = await self.begin_create()
        create_control = [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}]
        await self.callback(creation, create_control, clientSessionId='wrong-owned-session')
        await self.callback(creation, create_control, requestId='stale-create-request')
        await self.callback(creation, create_control, userId='wrong-user', expected_status=400)
        await self.callback(creation, [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.callback(creation, create_control, streamState='START', streamActive=True)
        await self.assert_waiting(opening)
        self.assertEqual(len(self.sent), 1)
        startup = await self.create_confirmed(opening, creation)
        await self.callback(creation, create_control)
        await self.callback(creation, [{'uiType': 'InputText'}])
        await self.callback(creation, create_control)
        await self.callback(startup, create_control)
        await self.callback(startup, [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        await self.assert_waiting(opening)
        self.assertEqual(len(self.sent), 2)
        await self.callback(startup, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        await self.callback(startup, create_control)
        await asyncio.sleep(.02)
        self.assertEqual(len(self.sent), 2)

    async def test_callback_returns_promptly_while_create_ack_holds_the_send_lock(self):
        self.create_ack_gate.clear()
        opening, creation = await self.begin_create()
        await asyncio.wait_for(self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}]), .5)
        await asyncio.wait_for(self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation', 'messageId': 'another-create-marker'}]), .5)
        await asyncio.sleep(.02)
        self.assertEqual(len(self.sent), 1)
        self.create_ack_gate.set()
        await self.wait_for_sent(2, opening)
        self.assertEqual(self.sent[1]['action'], 'START_CREATED_CONVERSATION')
        await self.assert_waiting(opening)
        self.assertEqual(len(self.sent), 2)

    async def test_end_preempts_start_queued_behind_create_ack(self):
        self.create_ack_gate.clear()
        opening, creation = await self.begin_create()
        owned = next(iter(self.bridge.sessions.values()))
        await asyncio.wait_for(self.callback(creation,
            [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}]), .5)
        ending = self.spawn(self.dialog.close())
        for _ in range(100):
            if getattr(owned, 'ending', False):
                break
            await asyncio.sleep(.005)
        self.assertTrue(getattr(owned, 'ending', False), 'END must fence queued START before waiting for the send lock')
        self.assertEqual(len(self.sent), 1)
        self.create_ack_gate.set()
        await asyncio.wait_for(ending, 2)
        self.assertEqual([payload.get('action') for payload in self.sent],
                         ['CREATE_CONVERSATION', 'END_CONVERSATION'])
        await self.callback(creation, [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}])
        await asyncio.sleep(.02)
        self.assertEqual(len(self.sent), 2)
        self.assertFalse(self.bridge.sessions)
        self.assertFalse(self.dialog.must_reset)

    async def test_uncertain_start_ack_keeps_owned_end_and_never_replays_intent(self):
        self.start_ack_error = True
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        with self.assertLogs('voice-bridge', level='WARNING') as logs:
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(opening, 2)
        self.assertEqual([record.getMessage() for record in logs.records],
                         ['Bot request failed; no credentials or payload logged'])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertTrue(any(cookie.key == 'scc_voice' and cookie.value == owned.sid
                            for cookie in self.dialog.http.cookie_jar))
        await self.callback(startup, [{'uiType': 'ActionMsg', 'actionType': 'CreateConversation'}])
        await asyncio.sleep(.02)
        self.assertEqual(len(self.sent), 2)
        await self.dialog.close()
        self.assertEqual([payload.get('action') for payload in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', 'END_CONVERSATION'])
        self.assertTrue(all(payload['message']['text'] == '' for payload in self.sent))
        self.assertFalse(self.bridge.sessions)
        self.assertFalse(self.dialog.must_reset)

    async def test_input_before_start_ack_does_not_release_dialog_until_ack_success(self):
        self.start_ack_gate.clear()
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'InputText'}])
        await self.assert_waiting(opening)
        self.assertEqual(len(self.sent), 2)
        self.start_ack_gate.set()
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        self.assertFalse(next(iter(self.bridge.sessions.values())).busy)
        self.assertEqual(len(self.sent), 2)

    async def test_input_before_uncertain_start_ack_never_releases_or_forwards_intent(self):
        self.start_ack_gate.clear()
        self.start_ack_error = True
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Unconfirmed startup greeting.'},
                                      {'uiType': 'InputText'}])
        await self.assert_waiting(opening)
        self.assertEqual(len(self.sent), 2)
        self.start_ack_gate.set()
        with self.assertLogs('voice-bridge', level='WARNING') as logs:
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(opening, 2)
        self.assertEqual([record.getMessage() for record in logs.records],
                         ['Bot request failed; no credentials or payload logged'])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertTrue(owned.failed)
        self.assertTrue(any(cookie.key == 'scc_voice' and cookie.value == owned.sid
                            for cookie in self.dialog.http.cookie_jar))
        await self.dialog.close()
        self.assertEqual([payload.get('action') for payload in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', 'END_CONVERSATION'])
        self.assertTrue(all(payload['message']['text'] == '' for payload in self.sent))
        self.assertFalse(self.bridge.sessions)

    async def test_backend_welcome_is_suppressed_but_input_metadata_and_business_reply_survive(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        greeting = 'Hello, how can I help you today?'
        input_label = 'What can I help you with?'
        await self.callback(startup, [{'uiType': 'OutputText', 'value': greeting},
                                      {'uiType': 'InputText', 'label': input_label}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertEqual(owned.input_label, input_label)
        self.assertEqual(owned.choices, [])
        self.assertFalse(owned.busy)
        self.assertFalse(self.dialog.greeting_history_allowed)
        self.dialog.record_greeting('Local fallback introduction.')
        self.assertEqual(self.dialog.greeting_history, [])
        turning = self.spawn(self.dialog.turn('One read-only business question.'))
        await self.wait_for_sent(3, turning)
        message = self.sent[2]
        self.assertEqual(message['message']['text'], 'One read-only business question.')
        self.assertNotIn('history', message)
        self.assertNotIn('nowSessionId', message)
        for key in ('clientSessionId', 'userId', 'contextVariables'):
            self.assertEqual(message[key], creation[key])
        await self.callback(message, [{'uiType': 'OutputText', 'value': 'Business answer.'}, {'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), ['Business answer.'])
        self.assertEqual(len(self.sent), 3)

    async def test_inputtext_before_outputtext_in_same_callback_suppresses_both_welcomes(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'InputText', 'label': 'How can I help?'},
                                      {'uiType': 'OutputText', 'value': 'Hello, welcome to support.'}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        owned = next(iter(self.bridge.sessions.values()))
        self.assertEqual(owned.input_label, 'How can I help?')
        self.assertFalse(owned.busy)

    async def test_late_bootstrap_welcome_before_business_is_not_a_business_response(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Late English welcome.'}])
        state = await self.dialog.request('GET', '/api/events',
            params={'after': str(self.dialog.cursor), 'wait': '0'})
        self.assertEqual(state['events'], [])
        turning = self.spawn(self.dialog.turn('One business question after startup.'))
        await self.wait_for_sent(3, turning)
        await self.callback(self.sent[2], [{'uiType': 'OutputText', 'value': 'Actual business reply.'},
                                         {'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), ['Actual business reply.'])
        self.assertEqual(len(self.sent), 3)

    async def test_secure_bootstrap_input_remains_a_failure_notice(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Ordinary welcome.'},
                                      {'uiType': 'InputText', 'maskType': 'SECURE'}])
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        owned = next(iter(self.bridge.sessions.values()))
        self.assertTrue(owned.failed)
        self.assertTrue(any(event['kind'] == 'notice' for event in owned.events))
        self.assertEqual(len(self.sent), 2)

    async def test_unsupported_bootstrap_control_remains_a_notice(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'FileUpload'}])
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        owned = next(iter(self.bridge.sessions.values()))
        self.assertTrue(any(event['kind'] == 'notice' for event in owned.events))
        self.assertEqual(len(self.sent), 2)

    async def test_terminal_bootstrap_state_still_ends_dialog(self):
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Ordinary welcome.'}], completed=True)
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        self.assertTrue(next(iter(self.bridge.sessions.values())).ended)
        self.assertEqual(len(self.sent), 2)

    async def test_real_native_call_emits_configured_introduction_and_selection_once(self):
        class CapturingSpeech:
            def __init__(self):
                self.spoken = []
                self.emitted = asyncio.Event()
            async def synthesize(self, text):
                self.spoken.append(text)
                self.emitted.set()
                yield bytes(480)
            async def transcribe(self, pcm):
                raise AssertionError('This test submits no microphone audio')
        speech = CapturingSpeech()
        with patch('native_bridge.RTCConfiguration', side_effect=lambda **kw: RTCConfiguration(iceServers=[])):
            call = NativeCall(Config(backend_url=self.bridge.origin, greeting='Unselected host intro.'),
                              speech, self.dialog, self.call_settings)
        processing = call.spawn(call.process_turns())
        self.tasks.append(processing)
        try:
            await self.wait_for_sent(1, processing)
            creation = self.sent[0]
            startup = await self.create_confirmed(processing, creation)
            await self.callback(startup, [{'uiType': 'OutputText', 'value': 'Hello, welcome to support.'},
                                          {'uiType': 'InputText', 'label': 'How can I help?'}])
            await asyncio.wait_for(speech.emitted.wait(), 2)
            await asyncio.sleep(.02)
            expected = self.call_settings.introduction + ' ' + self.call_settings.selection_prompt
            self.assertEqual(speech.spoken, [expected])
            self.assertEqual(expected.count(self.call_settings.introduction), 1)
            self.assertEqual(expected.count(self.call_settings.selection_prompt), 1)
            transcripts = [event['data']['content'] for event in call.pending_events
                           if event['type'] == 'transcript']
            self.assertEqual(transcripts, [expected])
            self.assertEqual(self.dialog.greeting_history, [])
            self.assertEqual(len(self.sent), 2)
        finally:
            await asyncio.wait_for(call.close(), 2)


if __name__ == '__main__':
    unittest.main()
