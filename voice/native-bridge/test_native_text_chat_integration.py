"""Offline real-router regression for native Test Assistant typed Chat."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from assistant_settings import CallSettings
from native_bridge import Config, create_app
from test_assistant_settings import authorized_settings, SERVICE, AGENT


class TextChatIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, authorized=True):
        self.dialogs = []
        owner = self
        class Dialog:
            def __init__(self):
                self.metadata = {'conversation_id': 'c' * 32, 'interaction_id': 'd' * 32}
                self.conversation_ended = False
                self.must_reset = False
                self.inputs = []
                self.closed = asyncio.Event()
                self.authorization = None
                owner.dialogs.append(self)
            def bind_caller_authorization(self, authorization):
                self.authorization = authorization
            async def open(self):
                return ['Für welchen Mitarbeiter ist der Laptop?']
            async def turn(self, raw, on_reply=None):
                self.inputs.append(raw)
                await on_reply('Bitte buchstabieren Sie den Nachnamen.')
                return ['Bitte buchstabieren Sie den Nachnamen.']
            async def close(self):
                pass
            async def shutdown(self):
                self.authorization = None
                self.closed.set()
        raw = authorized_settings()
        raw['result']['assistant_settings']['language_selection']['enabled'] = False
        settings = CallSettings.from_authorized_response(raw, SERVICE, AGENT)
        self.enterContext(patch('native_bridge.authorize', AsyncMock(return_value=settings if authorized else False)))
        self.enterContext(patch('native_bridge.require_model_ready', AsyncMock()))
        self.enterContext(patch('native_bridge.require_asr_ready', AsyncMock()))
        def no_media(_):
            self.fail('Typed Chat must never allocate Speech or WebRTC')
        config = Config(instance_name='soprasteriaassvsdemo14', voice_service_id=SERVICE,
            required_agent_id=AGENT, auth_mode='servicenow')
        client = TestClient(TestServer(create_app(config, speech_factory=no_media, dialog_factory=Dialog)))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_native_route_establishes_session_and_passes_raw_input_once_without_media(self):
        client = await self.client()
        ws = await client.ws_connect('/text/chat/agent_operator?auth_token=fixture')
        packets = []
        async def until_content(expected):
            for _ in range(8):
                packet = await ws.receive_json(timeout=2)
                packets.append(packet)
                if packet.get('content') == expected:
                    return
            self.fail('Native Chat reply was not delivered')
        await until_content('Für welchen Mitarbeiter ist der Laptop?')
        self.assertEqual(packets[0]['type'], 'connected')
        self.assertTrue(packets[0]['call_sid'])
        self.assertTrue(any(p.get('metadata', {}).get('conversation_id') == 'c' * 32 for p in packets))
        self.assertEqual(self.dialogs[0].authorization, 'Bearer fixture')
        raw = 'Nein, den Nachnamen buchstabiere ich: M, e, i, e, r.'
        await ws.send_json({'type': 'user_query', 'content': raw})
        await until_content('Bitte buchstabieren Sie den Nachnamen.')
        self.assertEqual(self.dialogs[0].inputs, [raw])
        await ws.close()
        await asyncio.wait_for(self.dialogs[0].closed.wait(), 2)
        self.assertIsNone(self.dialogs[0].authorization)

    async def test_invalid_upgrade_releases_capacity_for_next_valid_connection(self):
        client = await self.client()
        response = await client.get('/text/chat/agent_operator?auth_token=fixture')
        self.assertEqual(response.status, 400)
        self.assertEqual(self.dialogs, [])
        ws = await client.ws_connect('/text/chat/agent_operator?auth_token=fixture')
        self.assertEqual((await ws.receive_json(timeout=2))['type'], 'connected')
        await ws.close()

    async def test_denied_auth_allocates_no_dialog(self):
        client = await self.client(authorized=False)
        response = await client.get('/text/chat/agent_operator?auth_token=fixture')
        self.assertEqual(response.status, 401)
        self.assertEqual(self.dialogs, [])


if __name__ == '__main__':
    unittest.main()
