"""Native readiness must not report a usable voice path without its model.

Real application routes, metadata-only readiness doubles; no model, media,
caller authorization, or ServiceNow execution is contacted.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer

from native_bridge import Config, QWEN_ASR_BACKEND, QWEN_ASR_URL, create_app


class NativeReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, model_ready=True, sdk=False):
        self.model = self.enterContext(patch('native_bridge.require_model_ready', AsyncMock()))
        self.asr = self.enterContext(patch('native_bridge.require_asr_ready', AsyncMock()))
        self.dialog = Mock(side_effect=AssertionError('Health must not allocate a Dialog'))
        self.speech = Mock(side_effect=AssertionError('Health must not allocate Speech'))
        config = Config(model_health_url='http://127.0.0.1:8840/health',
            private_model_health_token='unit-private-model-token',
            asr_backend=QWEN_ASR_BACKEND, asr_url=QWEN_ASR_URL,
            private_asr_token='unit-private-asr-token', asr_runtime='crispasr',
            instance_name='soprasteriaassvsdemo14', auth_mode='servicenow',
            voice_service_id='8aa131d793f787105c8132d47aba1095',
            required_agent_id='a6337ddf93f787105c8132d47aba1058',
            native_sdk_enabled=sdk,
            sdk_public_origin='https://strix-alloy.tail7f425a.ts.net' if sdk else '')
        context = SimpleNamespace(instance_url=config.instance_url,
            assistant_id=config.voice_service_id, voice_agent_id=config.required_agent_id,
            sdk_agent_id='agent_operator', receive_data=True, call_settings=None)
        self.enterContext(patch('sdk_admission.admit_sdk_session', AsyncMock(return_value=context)))
        client = TestClient(TestServer(create_app(config, dialog_factory=self.dialog,
            speech_factory=self.speech)))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        self.asr.reset_mock()
        if not model_ready:
            self.model.side_effect = RuntimeError('private dependency detail')
        return client

    async def health(self, client):
        response = await client.get('/health')
        value = await response.json()
        self.dialog.assert_not_called()
        self.speech.assert_not_called()
        self.assertEqual(value['nativeSessions'], 0)
        self.asr.assert_awaited_once()
        self.assertNotIn('private dependency detail', str(value))
        return response.status, value

    async def test_absent_model_is_unavailable_even_when_asr_is_ready(self):
        status, value = await self.health(await self.client(model_ready=False))
        self.assertEqual(status, 503)
        self.model.assert_awaited_once()
        self.assertTrue(value['bridgeAlive'])
        self.assertEqual(value['status'], 'unavailable')
        self.assertFalse(value['modelReady'])
        self.assertTrue(value['asrReady'])

    async def test_ready_model_and_asr_keep_successful_health(self):
        status, value = await self.health(await self.client())
        self.assertEqual(status, 200)
        self.model.assert_awaited_once()
        self.assertTrue(value['bridgeAlive'])
        self.assertEqual(value['status'], 'ok')
        self.assertTrue(value['modelReady'])
        self.assertTrue(value['asrReady'])

    async def test_asr_failure_keeps_independent_model_status(self):
        client = await self.client()
        self.asr.side_effect = RuntimeError('private dependency detail')
        status, value = await self.health(client)
        self.assertEqual(status, 503)
        self.model.assert_awaited_once()
        self.assertTrue(value['bridgeAlive'])
        self.assertEqual(value['status'], 'unavailable')
        self.assertTrue(value['modelReady'])
        self.assertFalse(value['asrReady'])

    async def assert_create_rejection(self, stage):
        client = await self.client(sdk=True)
        checker = self.model if stage == 'model_readiness' else self.asr
        checker.side_effect = RuntimeError('private dependency detail')
        with self.assertLogs('native-voice', level='WARNING') as logs:
            response = await client.post('/api/webrtc/sessions?'
                'instance_name=soprasteriaassvsdemo14&receive_data=true',
                headers={'Authorization':'Bearer original.opaque.token'},
                json={'agent_id':'agent_operator'})
        self.assertEqual(response.status, 503)
        self.assertEqual(await response.json(), {'error':'unavailable'})
        self.assertEqual(logs.output, ['WARNING:native-voice:Native create stage=' + stage +
                                     ' outcome=unavailable'])
        self.dialog.assert_not_called()
        self.speech.assert_not_called()
        self.model.assert_awaited_once()
        if stage == 'model_readiness':
            self.asr.assert_not_awaited()
        else:
            self.asr.assert_awaited_once()

    async def test_sdk_create_reports_model_failure_without_allocating_a_call(self):
        await self.assert_create_rejection('model_readiness')

    async def test_sdk_create_reports_asr_failure_without_allocating_a_call(self):
        await self.assert_create_rejection('asr_readiness')


if __name__ == '__main__':
    unittest.main()
