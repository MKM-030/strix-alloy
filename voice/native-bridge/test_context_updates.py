"""Two focused fake-HTTP checks for the independent context control lane."""
import asyncio
import sys
from pathlib import Path
import unittest

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, ConversationBinding, Settings


class ContextLaneTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = []
        self.first_arrived, self.second_arrived = asyncio.Event(), asyncio.Event()
        self.release = asyncio.Event()
        self.fail_first = False
        async def receive(request):
            payload = await request.json()
            self.received.append(payload)
            if len(self.received) == 1:
                self.first_arrived.set()
                await self.release.wait()
                if self.fail_first:
                    return web.json_response({'status': 'failure'})
            else:
                self.second_arrived.set()
            if 'caller_updates' in payload:
                return web.json_response({'status': 'success', 'result': {
                    'state': 'caller_context_stored', 'contextStored': True,
                    'requestId': payload['requestId'], 'contextRequestId': payload['requestId'],
                    'revision': payload['revision'],
                    'conversationId': payload['conversationBinding']['conversationId'],
                    'executionPlanId': 'f' * 32, 'promptIncluded': False, 'ingested': False}})
            return web.json_response({'status': 'success'})
        fake = web.Application()
        fake.router.add_post('/api/bot', receive)
        fake.router.add_post('/api/global/scc_voice_context/updates', receive)
        self.bot = TestServer(fake)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(instance_url='https://instance.example.test',
            user_id='owned-user', email='owned@example.invalid'), 'unit-sn', 'audio', 'callback')
        self.bridge.bot_url = str(self.bot.make_url('/api/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        state = await (await self.ui.get('/api/session')).json()
        self.headers = {'Origin': self.bridge.origin, 'X-CSRF-Token': state['csrf']}
        self.session = next(iter(self.bridge.sessions.values()))
        self.session.started = self.session.busy = True
        self.session.pending_since = __import__('time').monotonic()
        self.session.requests.append('active-business-request')
        self.session.now_session = 'owned-now-session'
        self.session.conversation_binding = ConversationBinding('c' * 32, 'd' * 32, 'e' * 32)
        self.session.voice_context = {
            'interaction_requester_session_language': 'de', 'interaction_user_language': 'de',
            'requester_session_language': 'de', 'voice_assistant': 'a' * 32,
            'interaction_ai_voice': 'true', 'global_context_profile': 'b' * 32}
        self.callbacks = TestClient(TestServer(self.bridge.callback_app()))
        await self.callbacks.start_server()

    async def asyncTearDown(self):
        self.release.set()
        await self.callbacks.close()
        await self.ui.close()
        await self.bot.close()

    async def post(self, value, headers=None):
        return await self.ui.post('/api/context-update', json=value,
                                  headers=self.headers if headers is None else headers)

    async def test_busy_control_alias_callback_race_preserves_original_request(self):
        fields = ('requests', 'pending_since', 'pending_action', 'bootstrap_stage',
                  'completion_deadline', 'now_session', 'turn_texts', 'choices', 'input_label')
        before = {name: list(getattr(self.session, name)) if name in ('requests', 'turn_texts', 'choices')
                  else getattr(self.session, name) for name in fields}
        self.session.progress.begin_request('active-business-request')
        raw = '  Müller, nicht Möller.\nBitte genau so übernehmen.  '
        pending = asyncio.create_task(self.post({'revision': 1, 'caller_updates': raw,
                                                'voice_context': dict(self.session.voice_context)}))
        await asyncio.wait_for(self.first_arrived.wait(), 1)
        self.assertTrue(self.session.busy)
        for name, value in before.items():
            actual = list(getattr(self.session, name)) if name in ('requests', 'turn_texts', 'choices') else getattr(self.session, name)
            self.assertEqual(actual, value, name)
        sent = self.received[0]
        self.assertNotEqual(sent['requestId'], self.session.requests[-1])
        self.assertNotIn('action', sent)
        self.assertNotIn('message', sent)
        self.assertEqual(sent['conversationBinding'], self.session.conversation_binding.snapshot())
        self.assertEqual(sent['userId'], self.session.user_id)
        self.assertEqual(sent['clientSessionId'], self.session.sid)
        self.assertEqual(sent['caller_updates'], raw)
        self.assertEqual(sent['revision'], 1)
        self.assertNotIn('silentMessage', sent)
        alias_data = {'clientSessionId': self.session.sid, 'requestId': sent['requestId'],
            'userId': self.session.user_id,
            'body': [{'uiType': 'ActionMsg', 'actionType': 'DynamicLoader',
                      'progressMessages': [{'message': 'Öffentlicher Hinweis', 'status': 'COMPLETED'}]}]}
        for changes in ({'userId': 'other-user'}, {'userId': ''}):
            denied = await self.callbacks.post('/callback', json=dict(alias_data, **changes),
                headers={'Authorization': self.bridge.callback_auth})
            self.assertEqual(denied.status, 400)
        for changes in ({'requestId': 'unknown-request'}, {'clientSessionId': 'other-session'}):
            await self.callbacks.post('/callback', json=dict(alias_data, **changes),
                headers={'Authorization': self.bridge.callback_auth})
        self.assertIsNone(self.session.progress.update)
        await self.callbacks.post('/callback', json=alias_data,
            headers={'Authorization': self.bridge.callback_auth})
        self.assertTrue(self.session.busy)  # A completed presentation label is not input-ready.
        self.assertEqual(self.session.progress.update.messages, ('Öffentlicher Hinweis',))
        fingerprints = len(self.session.fingerprints)
        await self.callbacks.post('/callback', json=alias_data,
            headers={'Authorization': self.bridge.callback_auth})
        self.assertEqual(len(self.session.fingerprints), fingerprints)
        callback = await self.callbacks.post('/callback', json={
            'clientSessionId': self.session.sid, 'requestId': sent['requestId'],
            'userId': self.session.user_id,
            'body': [{'uiType': 'OutputText', 'value': 'Öffentliche Antwort.'}]},
            headers={'Authorization': self.bridge.callback_auth})
        self.assertEqual(callback.status, 200)
        self.assertTrue(self.session.busy)  # Complete text alone is not an input boundary.
        await self.callbacks.post('/callback', json=dict(alias_data,
            requestId='active-business-request', body=[{'uiType': 'OutputText', 'value': 'Original request still works.'}]),
            headers={'Authorization': self.bridge.callback_auth})
        await self.callbacks.post('/callback', json=dict(alias_data,
            body=[{'uiType': 'InputText', 'label': 'Nächste Frage?'}]),
            headers={'Authorization': self.bridge.callback_auth})
        self.assertFalse(self.session.busy)
        self.assertIn('Öffentliche Antwort.', [item['text'] for item in self.session.events])
        self.assertEqual(list(self.session.requests), ['active-business-request'])
        self.assertEqual(self.session.progress.request_id, 'active-business-request')
        normal = asyncio.create_task(self.ui.post('/api/message', json={'text': 'Next business input'},
                                                  headers=self.headers))
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.second_arrived.wait(), .05)
        self.release.set()
        result = await pending
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'state': 'context_action_acknowledged',
            'revision': 1, 'contextStored': True, 'promptIncluded': False, 'ingested': False,
            'contextRequestId': sent['requestId'], 'businessRequestId': 'active-business-request',
            'conversationId': 'c' * 32, 'executionPlanId': 'f' * 32})
        self.assertEqual((await normal).status, 202)
        current = self.session.requests[-1]
        self.assertNotEqual(current, 'active-business-request')
        count = len(self.session.events)
        await self.callbacks.post('/callback', json=dict(alias_data, completed=True,
            body=[{'uiType': 'InputText', 'label': 'Stale input'},
                  {'uiType': 'OutputText', 'value': 'Stale output'}]),
            headers={'Authorization': self.bridge.callback_auth})
        self.assertTrue(self.session.busy)
        self.assertFalse(self.session.ended)
        self.assertEqual(len(self.session.events), count)
        self.assertIsNone(self.session.context_requests.resolve(sent['requestId'], current))

    async def test_serial_uncertain_controls_are_fenced_and_identity_changes_rejected(self):
        self.fail_first = True
        denied = await self.post({'revision': 1, 'caller_updates': 'A'}, headers={'Origin': self.bridge.origin})
        self.assertEqual(denied.status, 403)
        for value in ({'revision': 1, 'caller_updates': 'A', 'contextVariables': {'agent': 'other'}},
                      {'revision': 1, 'caller_updates': 'A', 'voice_context': dict(self.session.voice_context, voice_assistant='c' * 32)},
                      {'revision': 1, 'caller_updates': 'x' * 8001}):
            self.assertEqual((await self.post(value)).status, 400)
        self.assertEqual(self.received, [])
        first = asyncio.create_task(self.post({'revision': 1, 'caller_updates': 'A'}))
        await asyncio.wait_for(self.first_arrived.wait(), 1)
        second = asyncio.create_task(self.post({'revision': 2, 'caller_updates': 'A\nB'}))
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.second_arrived.wait(), .05)
        self.release.set()
        first_result, second_result = await asyncio.gather(first, second)
        self.assertEqual(first_result.status, 502)
        self.assertEqual((await first_result.json())['state'], 'context_action_uncertain')
        self.assertEqual(second_result.status, 200)
        self.assertEqual(self.session.context_ack_revision, 2)
        self.assertEqual((await self.post({'revision': 2, 'caller_updates': 'A\nB'})).status, 409)
        self.assertEqual((await self.post({'revision': 3, 'caller_updates': 'replaced'})).status, 400)
        self.assertEqual(len(self.received), 2)
        self.assertTrue(self.session.busy)
        self.assertFalse(self.session.failed)
        self.assertEqual(list(self.session.requests), ['active-business-request'])
        # Refuse excess aliases without evicting uncertain earlier requests.
        for index in range(30):
            self.session.context_requests.bind('bounded-unit-' + str(index), 'active-business-request')
        self.assertEqual((await self.post({'revision': 3, 'caller_updates': 'A\nB\nC'})).status, 409)
        self.assertEqual(len(self.received), 2)
        self.assertEqual(self.session.context_requests.resolve(self.received[0]['requestId'],
                         'active-business-request'), 'active-business-request')


if __name__ == '__main__':
    unittest.main()
