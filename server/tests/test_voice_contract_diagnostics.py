import asyncio
import io
import json
import logging
from pathlib import Path
import sys
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway

KEY = 'fixture-public-key-material-32-characters'


class VoiceContractDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.output = io.StringIO()
        self.handler = logging.StreamHandler(self.output)
        self.logger = logging.getLogger('alloy.gateway')
        self.level = self.logger.level
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)
        self.gateway = Gateway(Backend('fixture', 'http://127.0.0.1:18473', 'model'), KEY,
                               voice_contract_diagnostics=True)
        self.client = TestClient(TestServer(self.gateway.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.level)

    def events(self):
        return [json.loads(line.split('Gateway voice contract ', 1)[1])
                for line in self.output.getvalue().splitlines() if 'Gateway voice contract ' in line]

    async def test_unauthorized_webrtc_preserves_401_with_only_contract_shape(self):
        sensitive = 'private-sentinel-token-audio-transcript'
        body = {'token': sensitive, 'sdp': sensitive, 'offer': {'type': sensitive, 'sdp': sensitive},
                'audio': [sensitive], 'transcript': sensitive, 'metadata': {sensitive: sensitive}}
        r = await self.client.post('/webrtc/create_session/' + sensitive + '?auth_token=' + sensitive,
            headers={'Authorization': 'Bearer ' + sensitive, 'Origin': 'https://' + sensitive,
                     'X-Api-Key': sensitive, 'Content-Type': 'application/json; boundary=' + sensitive},
            data=json.dumps(body))
        self.assertEqual(r.status, 401)
        self.assertEqual(await r.json(), {'error': {'message': 'Unauthorized'}})
        self.assertNotIn(sensitive, self.output.getvalue())
        self.assertNotIn(KEY, self.output.getvalue())
        event = self.events()[0]
        self.assertEqual(event['path_shape'], '/webrtc/create_session/[redacted]')
        self.assertEqual(event['credential_syntax'], 'bearer')
        self.assertEqual(event['content_type'], 'application/json')
        self.assertEqual(event['body_shape']['token'], 'string')
        self.assertEqual(event['body_shape']['offer'], 'object')
        self.assertEqual(event['response_shape'], {'error': 'object'})
        self.assertTrue(event['header_presence']['authorization'])
        self.assertTrue(event['header_presence']['x_api_key'])
        self.assertTrue(event['header_presence']['origin'])
        self.assertTrue(event['query_credential_present'])

    async def test_authorized_unknown_route_preserves_404(self):
        r = await self.client.post('/webrtc/get_token', json={'client_id': 'private'},
                                   headers={'Authorization': 'Bearer ' + KEY})
        self.assertEqual(r.status, 404)
        event = self.events()[0]
        self.assertEqual(event['status'], 404)
        self.assertEqual(event['body_shape'], {'client_id': 'string'})
        self.assertEqual(event['response_shape'], 'not_json')

    async def test_opaque_and_oversized_bodies_are_not_read(self):
        for body, content_type in [('private audio', 'audio/wav'), ('x' * 32769, 'application/json')]:
            r = await self.client.post('/webrtc/token', data=body, headers={'Content-Type': content_type})
            self.assertEqual(r.status, 401)
        self.assertEqual([e['body_shape'] for e in self.events()], ['not_json', 'size_skipped'])

    async def test_invalid_json_does_not_change_response(self):
        r = await self.client.post('/webrtc/token', data='{', headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status, 401)
        self.assertEqual(self.events()[0]['body_shape'], 'invalid_json')

    async def test_body_without_known_length_is_not_read(self):
        async def chunks():
            yield b'{"token":"private"}'
        r = await self.client.post('/webrtc/token', data=chunks(), headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status, 401)
        self.assertEqual(self.events()[0]['body_shape'], 'size_skipped')

    async def test_diagnostics_default_off(self):
        gateway = Gateway(self.gateway.backend, KEY)
        client = TestClient(TestServer(gateway.app))
        try:
            await client.start_server()
            r = await client.post('/webrtc/token', json={'token': 'private'})
            self.assertEqual(r.status, 401)
            self.assertEqual(self.events(), [])
        finally:
            await client.close()

    async def test_known_gateway_routes_stay_quiet(self):
        for path in ('/health', '/v1/models', '/v1/chat/completions'):
            r = await self.client.post(path, json={'transcript': 'private'})
            self.assertEqual(r.status, 401)
        self.assertEqual(self.events(), [])

    async def test_other_authorization_syntax_and_unreviewed_keys_are_redacted(self):
        r = await self.client.post('/webrtc/aLongPrivateToken', json={'aLongPrivateToken': 'private'},
                                  headers={'Authorization': 'Basic private'})
        self.assertEqual(r.status, 401)
        event = self.events()[0]
        self.assertEqual(event['credential_syntax'], 'basic')
        self.assertEqual(event['body_shape'], {'[redacted_0]': 'string'})
        self.assertNotIn('aLongPrivateToken', self.output.getvalue())

    async def test_reviewed_native_configuration_keys_show_names_and_types_only(self):
        keys = ('instance_name', 'voice_service_id', 'oauth_client_id', 'mobileChannelType',
                'mobileChannelId', 'voiceServiceId', 'voiceWebhookURL', 'client_app', 'clientApp', 'ws_ticket')
        r = await self.client.post('/webrtc/get_token', json={key: 'private-sentinel' for key in keys})
        self.assertEqual(r.status, 401)
        self.assertEqual(self.events()[0]['body_shape'], {key: 'string' for key in keys})
        self.assertNotIn('private-sentinel', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
