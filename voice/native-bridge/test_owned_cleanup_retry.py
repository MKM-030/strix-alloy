"""Real loopback regression: failed owned END must not orphan its cookie.

No model, ServiceNow, speech service, or external network is contacted.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from native_bridge import Config, Dialog, NativeCall
from sdk_sessions import SDKSessionManager

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from voice.bridge import Bridge, Settings


class OwnedCleanupRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_end_retains_owner_and_capacity_until_ack_without_message_replay(self):
        bridge = Bridge(Settings(instance_url='https://instance.example.test',
            user_id='fixture-user', defer_start_until_message=True),
            'fixture-bot', 'fixture-speech', 'fixture-callback')
        server = TestServer(bridge.ui_app())
        await server.start_server()
        bridge.origin = str(server.make_url('/')).rstrip('/')
        config = Config(backend_url=bridge.origin)
        dialog = Dialog(config)
        dialog._call_owned = True
        call = NativeCall(config, object(), dialog)
        active = {call}
        manager = SDKSessionManager(config, active, lambda: call, None)
        session = SimpleNamespace(operation=None, watchers=set(), call=call,
            pending=[], closed_at=None)
        first_rejected = asyncio.Event()
        retry_started = asyncio.Event()
        permit_ack = asyncio.Event()
        attempted_actions = []
        cleanup = None
        fresh = None

        async def end_only(owned_session, text, typed, action='', history=None):
            attempted_actions.append(action)
            self.assertEqual(action, 'END_CONVERSATION')
            self.assertEqual(text, '')
            self.assertIsNone(history)
            if len(attempted_actions) == 1:
                first_rejected.set()
                raise web.HTTPBadGateway(text='Synthetic transient END failure')
            retry_started.set()
            await permit_ack.wait()
            # Successful enqueue ACK; Bridge.end itself removes only its owned session.

        try:
            await dialog.open()
            owned = next(iter(bridge.sessions.values()))
            owned.requests.append('fixture-already-submitted-request')
            bridge.send = end_only
            cleanup = asyncio.create_task(manager._finish_close(session))
            await asyncio.wait_for(first_rejected.wait(), 2)
            await asyncio.sleep(.02)
            self.assertFalse(call.close_complete.is_set(),
                'A failed END must retain cleanup ownership, not destroy its cookie')
            self.assertIn(call, active)
            self.assertIsNotNone(dialog.http)
            cookies = list(dialog.http.cookie_jar)
            self.assertTrue(any(item.key == 'scc_voice' and item.value == owned.sid
                                for item in cookies))
            self.assertEqual(len(bridge.sessions), 1)
            self.assertTrue(attempted_actions)
            self.assertEqual(set(attempted_actions), {'END_CONVERSATION'})
            await asyncio.wait_for(retry_started.wait(), 5)
            self.assertFalse(cleanup.done())
            self.assertFalse(call.close_complete.is_set())
            self.assertIn(call, active)
            permit_ack.set()
            await asyncio.wait_for(cleanup, 5)
            self.assertTrue(call.close_complete.is_set())
            self.assertNotIn(call, active)
            self.assertIsNone(dialog.http)
            self.assertFalse(bridge.sessions)
            self.assertEqual(set(attempted_actions), {'END_CONVERSATION'})
            self.assertGreaterEqual(len(attempted_actions), 2)
            fresh = Dialog(config)
            self.assertEqual(await fresh.open(), [])
            self.assertEqual(len(bridge.sessions), 1)
            self.assertNotEqual(next(iter(bridge.sessions)), owned.sid)
            self.assertEqual(fresh.greeting_history, [])
        finally:
            permit_ack.set()
            if cleanup is not None:
                await asyncio.wait_for(asyncio.gather(cleanup, return_exceptions=True), 6)
            if fresh is not None:
                await fresh.close()
                await fresh.shutdown()
            await dialog.shutdown()
            await server.close()


if __name__ == '__main__':
    unittest.main()
