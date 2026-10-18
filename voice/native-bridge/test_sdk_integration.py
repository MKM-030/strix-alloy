import unittest
from aiohttp.test_utils import TestClient, TestServer
from native_bridge import Config, create_app


class SDKIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, enabled):
        config = Config(instance_name='soprasteriaassvsdemo14', auth_mode='servicenow',
            sdk_public_origin='https://strix-alloy.tail7f425a.ts.net',
            voice_service_id='8aa131d793f787105c8132d47aba1095',
            required_agent_id='a6337ddf93f787105c8132d47aba1058')
        config.native_sdk_enabled = enabled
        # No call or dialog is allocated by the rejected admission fixtures.
        client = TestClient(TestServer(create_app(config, dialog_factory=lambda: None)))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_opted_in_sdk_route_rejects_missing_oauth_before_allocation(self):
        client = await self.client(True)
        response = await client.post('/api/webrtc/sessions?instance_name=soprasteriaassvsdemo14&receive_data=true',
            json={'agent_id':'agent_operator'})
        self.assertEqual(response.status, 401)
        health = await (await client.get('/health')).json()
        self.assertEqual(health['nativeSessions'], 0)
        self.assertTrue(health['nativeSdkEnabled'])

    async def test_default_disabled_preserves_existing_route_surface(self):
        client = await self.client(False)
        response = await client.post('/api/webrtc/sessions', json={})
        self.assertEqual(response.status, 404)

    async def test_browser_admission_stays_protected_when_sdk_enabled(self):
        client = await self.client(True)
        response = await client.get('/webrtc/connect/agent_operator')
        self.assertEqual(response.status, 401)


if __name__=='__main__':
    unittest.main()
