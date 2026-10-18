import sys
from pathlib import Path
import unittest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestServer, TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings
from native_bridge import Config, Dialog


class EndSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_end_requires_csrf_and_frees_slot_without_creating_another_session(self):
        sent = []
        async def bot(request):
            sent.append(await request.json())
            return web.json_response({'status':'success'})
        bot_app = web.Application()
        bot_app.router.add_post('/bot', bot)
        backend = TestServer(bot_app)
        await backend.start_server()
        bridge = Bridge(Settings(user_id='test'), 'test-sn', 'test-audio', 'test-callback')
        bridge.bot_url = str(backend.make_url('/bot'))
        client = TestClient(TestServer(bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await client.start_server()
        bridge.origin = str(client.make_url('/')).rstrip('/')
        try:
            first = await (await client.get('/api/session')).json()
            headers = {'Origin':bridge.origin,'X-CSRF-Token':first['csrf']}
            await client.post('/api/start', json={}, headers=headers)
            old_sid = sent[0]['clientSessionId']
            denied = await client.post('/api/end', json={}, headers={'Origin':bridge.origin})
            self.assertEqual(denied.status, 403)
            self.assertIn(old_sid, bridge.sessions)
            ended = await client.post('/api/end', json={}, headers=headers)
            self.assertEqual(ended.status, 200)
            self.assertEqual(await ended.json(), {'ended':True})
            self.assertEqual(sent[-1]['action'], 'END_CONVERSATION')
            self.assertEqual(bridge.sessions, {})
            again = await (await client.get('/api/session')).json()
            self.assertNotEqual(first['csrf'], again['csrf'])
            self.assertEqual(len(bridge.sessions), 1)
            self.assertNotIn(old_sid, bridge.sessions)
            await client.post('/api/end', json={}, headers={
                'Origin':bridge.origin,'X-CSRF-Token':again['csrf']})
            bridge.settings.defer_start_until_message = True
            for _ in range(2):
                # A wholly new adapter has no old cookie and must still acquire
                # the sole available slot after the previous clean disconnect.
                adapter = Dialog(Config(backend_url=bridge.origin))
                try:
                    await adapter.open()
                    await adapter.close()
                    self.assertEqual(bridge.sessions, {})
                    self.assertFalse(adapter.must_reset)
                finally:
                    await adapter.shutdown()
        finally:
            await client.close()
            await backend.close()


if __name__ == '__main__':
    unittest.main()
