import unittest
from unittest.mock import Mock

from aiohttp import ClientSession, web
from native_bridge import Config, create_app

INSTANCE = 'voice-fixture'
ASSISTANT = 'a' * 32
TARGET = 'https://voice-fixture.service-now.com/now/now-assist-with-va/voice-test/' + ASSISTANT


class MobileLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def open_server(self, **changes):
        values = dict(instance_name=INSTANCE, voice_service_id=ASSISTANT, auth_mode='servicenow')
        values.update(changes)
        self.speech_factory = Mock(side_effect=AssertionError('launch must not create speech'))
        self.dialog_factory = Mock(side_effect=AssertionError('launch must not create dialog'))
        app = create_app(Config(**values), speech_factory=self.speech_factory, dialog_factory=self.dialog_factory)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        self.addAsyncCleanup(runner.cleanup)
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        self.base = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        self.http = ClientSession()
        self.addAsyncCleanup(self.http.close)

    def assert_privacy_headers(self, response):
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'no-referrer')
        self.assertFalse(response.cookies)

    async def test_configured_redirect_without_query_token_or_session(self):
        await self.open_server()
        async with self.http.get(self.base + '/launch', allow_redirects=False) as response:
            self.assertEqual(response.status, 302)
            self.assertEqual(response.headers.get('Location'), TARGET)
            self.assert_privacy_headers(response)
        async with self.http.get(self.base + '/health') as response:
            self.assertEqual((await response.json())['nativeSessions'], 0)
        self.speech_factory.assert_not_called()
        self.dialog_factory.assert_not_called()

    async def test_other_valid_startup_binding_is_portable(self):
        await self.open_server(instance_name='different-instance', voice_service_id='b' * 32)
        async with self.http.get(self.base + '/launch', allow_redirects=False) as response:
            self.assertEqual(response.status, 302)
            self.assertEqual(response.headers.get('Location'),
                'https://different-instance.service-now.com/now/now-assist-with-va/voice-test/' + 'b' * 32)
            self.assert_privacy_headers(response)
        self.speech_factory.assert_not_called()
        self.dialog_factory.assert_not_called()

    async def test_request_headers_cannot_rebind_configured_target(self):
        await self.open_server()
        headers = {'Host':'untrusted.invalid', 'Forwarded':'host=untrusted.invalid;proto=http',
            'X-Forwarded-Host':'untrusted.invalid', 'X-Forwarded-Proto':'http',
            'Origin':'https://untrusted.invalid'}
        async with self.http.get(self.base + '/launch', headers=headers, allow_redirects=False) as response:
            self.assertEqual(response.status, 302)
            self.assertEqual(response.headers.get('Location'), TARGET)
            self.assert_privacy_headers(response)

    async def test_query_is_rejected_without_reflecting_values(self):
        await self.open_server()
        for query in ('?next=https://untrusted.invalid/', '?auth_token=do-not-reflect', '?a=', '?a=1&a=2'):
            async with self.http.get(self.base + '/launch' + query, allow_redirects=False) as response:
                self.assertEqual(response.status, 400)
                self.assertIsNone(response.headers.get('Location'))
                self.assert_privacy_headers(response)
                self.assertNotIn('do-not-reflect', await response.text())
        self.speech_factory.assert_not_called()
        self.dialog_factory.assert_not_called()

    async def test_invalid_startup_instance_is_rejected_before_app_construction(self):
        for instance in ('', 'other.service-now.com', 'voice/escape', 'https://untrusted.invalid',
                         '-bad', 'bad-', 'UPPERCASE', 'x' * 64, None, 17):
            with self.subTest(instance=instance):
                with self.assertRaises(ValueError):
                    await self.open_server(instance_name=instance)
                self.speech_factory.assert_not_called()
                self.dialog_factory.assert_not_called()

    async def test_invalid_startup_assistant_is_not_exposed(self):
        for assistant in ('other', 'a' * 31, 'a' * 33, 'A' * 32, 'a' * 32 + '?next=escape', None, 17):
            with self.subTest(assistant=assistant):
                await self.open_server(voice_service_id=assistant)
                async with self.http.get(self.base + '/launch', allow_redirects=False) as response:
                    self.assertEqual(response.status, 404)
                    self.assertIsNone(response.headers.get('Location'))
                    self.assert_privacy_headers(response)

    async def test_post_is_not_a_launch_or_voice_session(self):
        await self.open_server()
        async with self.http.post(self.base + '/launch', allow_redirects=False) as response:
            self.assertEqual(response.status, 405)
            self.assertIsNone(response.headers.get('Location'))
        self.speech_factory.assert_not_called()
        self.dialog_factory.assert_not_called()

    async def test_health_remains_idle(self):
        await self.open_server()
        async with self.http.get(self.base + '/health') as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {'status':'ok', 'nativeSessions':0,
                'authMode':'servicenow', 'conversationLayer':'legacy',
                'conversationPipeline':'legacy', 'conversationSentenceStreaming':False})
        self.speech_factory.assert_not_called()
        self.dialog_factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
