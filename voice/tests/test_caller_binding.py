"""Authenticated Native caller bootstrap; all traffic is loopback/test doubles."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from voice.bridge import Bridge, Settings

SERVICE = '8aa131d793f787105c8132d47aba1095'
AGENT = 'a6337ddf93f787105c8132d47aba1058'
PROFILE = 'c623e20f93374354e7f2b9fa6aba1081'
TOKEN = 'Bearer original.voice.credential'
HEADER = 'X-SCC-Voice-Authorization'
CONTEXT = dict(interaction_requester_session_language='de', interaction_user_language='de',
    requester_session_language='de', voice_assistant=SERVICE, interaction_ai_voice='true',
    global_context_profile=PROFILE)


class CallerBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        async def bot(request):
            self.assertEqual(request.headers.get('token'), 'bot-secret')
            self.assertNotIn(HEADER, request.headers)
            self.sent.append(await request.json())
            return web.json_response({'status': 'success'})
        app = web.Application(); app.router.add_post('/bot', bot)
        self.bot = TestServer(app); await self.bot.start_server()
        self.bridge = Bridge(Settings(user_id='legacy', email='static@example.test',
            instance_url='https://instance.example.test', session_scoped_user_id=True),
            'bot-secret', 'audio-secret', 'callback-secret')
        self.bridge.settings.caller_binding_service_id = SERVICE
        self.bridge.settings.caller_binding_agent_id = AGENT
        self.bridge.bot_url = str(self.bot.make_url('/bot'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server(); self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.addAsyncCleanup(self.bot.close); self.addAsyncCleanup(self.ui.close)
        self.csrf = (await (await self.ui.get('/api/session')).json())['csrf']
        self.headers = {'Origin': self.bridge.origin, 'X-CSRF-Token': self.csrf}
        self.binding = SimpleNamespace(user_id='1'*32, email='real@example.test')
        self.resolve = AsyncMock(return_value=self.binding)
        self.patch = patch('voice.bridge.resolve_native_caller', self.resolve, create=True)
        self.patch.start(); self.addCleanup(self.patch.stop)

    async def start(self, *, token=TOKEN, **extra):
        headers = dict(self.headers)
        if token is not None: headers[HEADER] = token
        return await self.ui.post('/api/start', json={'voice_context': CONTEXT, **extra}, headers=headers)

    async def test_voice_without_original_bearer_refuses_before_create(self):
        self.assertEqual((await self.start(token=None)).status, 401)
        self.assertEqual(self.sent, [])
        self.resolve.assert_not_awaited()

    async def test_missing_fixed_binding_configuration_cannot_fall_back_to_static_email(self):
        self.bridge.settings.caller_binding_service_id = ''
        self.bridge.settings.caller_binding_agent_id = ''
        self.assertEqual((await self.start(token=None)).status, 503)
        self.assertEqual(self.sent, [])
        self.resolve.assert_not_awaited()

    async def test_native_authority_supplies_email_without_changing_random_alias(self):
        response = await self.start(emailId='attacker@example.test', caller_binding={'email':'attacker@example.test'})
        self.assertEqual(response.status, 202)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['emailId'], 'real@example.test')
        self.assertTrue(self.sent[0]['userId'].startswith('voice-'))
        self.assertEqual(self.sent[0]['contextVariables'], CONTEXT)
        args = self.resolve.await_args
        self.assertEqual(args.args, ('https://instance.example.test', SERVICE, AGENT, PROFILE, TOKEN))
        public = await (await self.ui.get('/api/events?wait=0')).json()
        rendered = json.dumps(public) + repr(next(iter(self.bridge.sessions.values())))
        self.assertNotIn('real@example.test', rendered)
        self.assertNotIn('1'*32, rendered)
        self.assertNotIn(TOKEN, rendered)

    async def test_native_denial_or_malformed_identity_does_not_start(self):
        self.resolve.side_effect = ValueError('private text and original token must not escape')
        response = await self.start()
        self.assertEqual(response.status, 403)
        self.assertNotIn('private', await response.text())
        self.assertEqual(self.sent, [])
        self.assertFalse(next(iter(self.bridge.sessions.values())).started)

    async def test_wrong_service_does_not_query_authority(self):
        data = dict(CONTEXT, voice_assistant='f'*32)
        response = await self.ui.post('/api/start', json={'voice_context':data},
            headers={**self.headers, HEADER:TOKEN})
        self.assertEqual(response.status, 403)
        self.resolve.assert_not_awaited()
        self.assertEqual(self.sent, [])

    async def test_two_calls_retire_identity_and_do_not_reuse_static_email(self):
        await self.start()
        first = self.sent[0]
        old = next(iter(self.bridge.sessions.values()))
        response = await self.ui.post('/api/end', json={}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertNotIn('real@example.test', repr(old))
        self.assertEqual(getattr(old, 'caller_email', ''), '')
        self.csrf = (await (await self.ui.get('/api/session')).json())['csrf']
        self.headers['X-CSRF-Token'] = self.csrf
        self.resolve.return_value = SimpleNamespace(user_id='2'*32, email='second@example.test')
        await self.start(token='Bearer second.voice.credential')
        self.assertEqual(self.sent[-1]['emailId'], 'second@example.test')
        self.assertNotEqual(self.sent[-1]['userId'], first['userId'])


if __name__ == '__main__': unittest.main()
