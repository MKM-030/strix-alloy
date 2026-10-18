import unittest
import asyncio
from aiohttp import ClientSession, WSMsgType, web
import demo_audio_smoke
from demo_audio_smoke import EXPECTED_SUMMARY, expected_summary, name_question


class DemoConfirmationTests(unittest.TestCase):
    def test_review_approval_requires_exact_summary_and_current_request(self):
        check = getattr(demo_audio_smoke, 'review_approved', None)
        self.assertIsNotNone(check, 'bounded exact-summary operator review gate missing')
        self.assertTrue(check({'approve':True,'summary_sha256':'abc','review_id':'current'}, 'abc','current'))
        self.assertFalse(check({'approve':True,'summary_sha256':'changed','review_id':'current'}, 'abc','current'))
        self.assertFalse(check({'approve':True,'summary_sha256':'abc','review_id':'old'}, 'abc','current'))
        self.assertFalse(check({'approve':'true','summary_sha256':'abc','review_id':'current'}, 'abc','current'))
    def test_only_the_accepted_order_summary_can_trigger_confirmation_fixture(self):
        self.assertTrue(expected_summary(EXPECTED_SUMMARY))
        for old, new in [('Alex Sommer','Max Mustermann'), ('Hamburg','Berlin'),
                         ('1. November','2. November'), ('2026','2027'),
                         ('Marcel KAEFKE','Alex Sommer')]:
            self.assertFalse(expected_summary(EXPECTED_SUMMARY.replace(old,new)))
        self.assertFalse(expected_summary('Bestellung bestätigt.'))
        self.assertFalse(expected_summary('Nicht bestellen. '+EXPECTED_SUMMARY))

    def test_a_name_question_allows_name_audio_but_a_summary_does_not(self):
        self.assertTrue(name_question('Wie heißt dein neuer Mitarbeiter? Als Vorgesetzten trage ich dich ein.'))
        self.assertFalse(name_question(EXPECTED_SUMMARY))


class SignalingHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_keeps_reading_websocket_during_slow_backend_turn(self):
        drain = getattr(demo_audio_smoke, 'drain_signaling', None)
        self.assertIsNotNone(drain, 'probe must drain WS so aiohttp answers native heartbeat pings')
        backend_started = asyncio.Event()
        backend_release = asyncio.Event()
        heartbeats_received = asyncio.Event()
        received = []
        payloads = [b'heartbeat-1', b'heartbeat-2', b'heartbeat-3']
        async def slow_backend_turn():
            backend_started.set()
            await backend_release.wait()
        async def endpoint(request):
            # Observe real heartbeat frames without a 25ms scheduler deadline.
            ws = web.WebSocketResponse(autoping=False)
            await ws.prepare(request)
            await backend_started.wait()
            for payload in payloads:
                await ws.ping(payload)
                message = await ws.receive()
                received.append((message.type, message.data))
                if message.type != WSMsgType.PONG:
                    break
            heartbeats_received.set()
            async for _ in ws:
                pass
            return ws
        app = web.Application()
        app.router.add_get('/', endpoint)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner,'127.0.0.1',0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as http:
                async with http.ws_connect(f'http://127.0.0.1:{port}/') as ws:
                    closed = asyncio.Event()
                    reader = asyncio.create_task(drain(ws, None, closed))
                    backend = asyncio.create_task(slow_backend_turn())
                    try:
                        await asyncio.wait_for(heartbeats_received.wait(), 2)
                        self.assertEqual(received, [(WSMsgType.PONG, payload) for payload in payloads])
                        self.assertFalse(backend.done(), 'backend turn must still be pending during heartbeats')
                        self.assertFalse(closed.is_set(), 'heartbeat timeout incorrectly ended test call')
                        self.assertFalse(ws.closed)
                    finally:
                        backend_release.set()
                        await backend
                        await ws.close()
                        await reader
        finally:
            await runner.cleanup()


if __name__ == '__main__':
    unittest.main()
