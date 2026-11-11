"""Actual local metadata HTTP; fake admission/calls, no model or audio."""
from contextlib import AsyncExitStack
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer

from assistant_settings import CallSettings
from native_bridge import Config, create_app
from test_assistant_settings import authorized_settings, SERVICE, AGENT
from test_sdk_sessions import FakeCall


class TTSReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_absent_wrong_and_ready_tts_gate_health_and_call_allocation(self):
        for state in ('absent', 'wrong', 'ready'):
            with self.subTest(state=state):
                async with AsyncExitStack() as stack:
                    requests = []
                    health_entered, health_release = asyncio.Event(), asyncio.Event()
                    hold_health = False
                    async def models(request):
                        requests.append((request.method, request.path))
                        if hold_health:
                            health_entered.set()
                            await health_release.wait()
                        return web.json_response({'object': 'list', 'data': [
                            {'id': 'scc-native-qwen3' if state == 'ready' else 'other-model',
                             'object': 'model'}]})
                    metadata = web.Application()
                    metadata.router.add_get('/v1/models', models)
                    server = await stack.enter_async_context(TestServer(metadata))
                    speech_url = str(server.make_url('/v1/audio/speech'))
                    if state == 'absent':
                        await server.close()
                    config = Config(instance_name='soprasteriaassvsdemo14',
                        voice_service_id=SERVICE, required_agent_id=AGENT, auth_mode='servicenow',
                        native_sdk_enabled=True, sdk_public_origin='https://strix-alloy.tail7f425a.ts.net',
                        tts_url=speech_url)
                    raw = authorized_settings()
                    raw['result']['assistant_settings']['language_selection']['enabled'] = False
                    settings = CallSettings.from_authorized_response(raw, SERVICE, AGENT)
                    context = SimpleNamespace(instance_url=config.instance_url,
                        assistant_id=SERVICE, voice_agent_id=AGENT, sdk_agent_id='agent_operator',
                        receive_data=True, call_settings=settings)
                    for target in ('native_bridge.require_model_ready', 'native_bridge.require_asr_ready'):
                        stack.enter_context(patch(target, AsyncMock()))
                    stack.enter_context(patch('sdk_admission.admit_sdk_session', AsyncMock(return_value=context)))
                    stack.enter_context(patch('native_bridge.authorize', AsyncMock(return_value=settings)))
                    stack.enter_context(patch('voice_reference_runtime.reference_cache', return_value=None))
                    references = stack.enter_context(patch('voice_reference_runtime.prepare_references', AsyncMock()))
                    speech, dialog = Mock(), Mock()
                    def make_call(cfg, speech, dialog, **kwargs):
                        call = FakeCall()
                        call.config, call.dialog = cfg, dialog
                        return call
                    calls = stack.enter_context(patch('native_bridge.NativeCall', side_effect=make_call))
                    client = await stack.enter_async_context(TestClient(TestServer(create_app(config,
                        speech_factory=speech, dialog_factory=dialog))))
                    response = await client.get('/health')
                    value = await response.json()
                    self.assertEqual(response.status, 200 if state == 'ready' else 503)
                    self.assertEqual(value['ttsReady'], state == 'ready')
                    self.assertTrue(value['bridgeAlive'])
                    self.assertEqual(value['nativeSessions'], 0)
                    self.assertNotIn(speech_url, str(value))
                    self.assertNotIn('other-model', str(value))
                    response = await client.post('/api/webrtc/sessions?'
                        'instance_name=soprasteriaassvsdemo14&receive_data=true',
                        headers={'Authorization': 'Bearer synthetic.token'}, json={'agent_id': 'agent_operator'})
                    if state != 'ready':
                        self.assertEqual(response.status, 503)
                        self.assertEqual(await response.json(), {'error': 'unavailable'})
                        # Browser and SDK preflight must both precede reference preparation.
                        response = await client.get('/webrtc/connect/agent_operator?auth_token=synthetic.token')
                        self.assertEqual(response.status, 503)
                        calls.assert_not_called()
                        speech.assert_not_called()
                        dialog.assert_not_called()
                        references.assert_not_awaited()
                    else:
                        self.assertEqual(response.status, 200)
                        session = await response.json()
                        calls.assert_called_once()
                        references.assert_awaited_once()
                        # The call closes while the metadata probe is outstanding.
                        hold_health = True
                        pending_health = asyncio.create_task(client.get('/health'))
                        await asyncio.wait_for(health_entered.wait(), 1)
                        response = await client.delete('/api/webrtc/sessions/' + session['session_id'],
                            headers={'Authorization': 'Bearer synthetic.token'})
                        self.assertEqual(response.status, 204)
                        health_release.set()
                        snapshot = await (await pending_health).json()
                        self.assertEqual(snapshot['nativeSessions'], 0)
                    self.assertTrue(all(item == ('GET', '/v1/models') for item in requests))
                    self.assertEqual(len(requests), {'absent': 0, 'wrong': 3, 'ready': 3}[state])

    async def test_metadata_limits_redirect_timeout_and_cancellation(self):
        import tts_health
        entered, release = asyncio.Event(), asyncio.Event()
        requests = []
        mode = 'redirect'
        async def models(request):
            requests.append(request.path)
            if mode == 'redirect':
                raise web.HTTPFound('/private-target')
            if mode == 'large':
                return web.Response(body=b' ' * (tts_health.MAX_MODELS_BYTES + 1))
            if mode == 'invalid':
                return web.Response(body=b'not metadata')
            entered.set()
            await release.wait()
            return web.json_response({'object': 'list', 'data': [{'id': tts_health.TTS_MODEL, 'object': 'model'}]})
        async def forbidden(request):
            self.fail('Readiness followed a redirect')
        app = web.Application()
        app.router.add_get('/v1/models', models)
        app.router.add_get('/private-target', forbidden)
        async with TestServer(app) as server, ClientSession(trust_env=False) as http:
            url = str(server.make_url('/v1/audio/speech'))
            for mode in ('redirect', 'large', 'invalid'):
                with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, '^Selected TTS service is unavailable$'):
                    await tts_health.require_tts_ready(http, url)
            count = len(requests)
            for invalid in ('https://external.invalid/v1/audio/speech',
                            url + '?token=private', url.replace('127.0.0.1', 'user:secret@127.0.0.1'),
                            url.replace('/v1/audio/speech', '/other')):
                with self.assertRaises(RuntimeError):
                    await tts_health.require_tts_ready(http, invalid)
            self.assertEqual(len(requests), count)
            mode = 'slow'
            try:
                with patch.object(tts_health, 'TTS_READINESS_TIMEOUT', 0.03), self.assertRaises(RuntimeError):
                    await asyncio.wait_for(tts_health.require_tts_ready(http, url), 0.5)
                entered.clear()
                task = asyncio.create_task(tts_health.require_tts_ready(http, url))
                await asyncio.wait_for(entered.wait(), 0.5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()


if __name__ == '__main__':
    unittest.main()
