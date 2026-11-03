"""Offline WSS admission tests; all credentials and responses are synthetic."""
import copy
import json
from types import SimpleNamespace
import unittest

from native_bridge import authorize
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings, SERVICE, AGENT


INSTANCE = 'https://voice-auth.example.test'
AUTH_URL = INSTANCE + '/api/sn_voice_aia/ai_voice_agent/agents_authorized'
OPAQUE = 'opaque_synthetic-voice+credential/with~padding=='
JWT = 'synthetic.header.signature'


class Response:
    def __init__(self, *, status=200, payload=None, raw=None, headers=None):
        self.status = status
        self.headers = headers or {}
        self.payload = {'result': [AGENT]} if payload is None else payload
        self.raw = json.dumps(self.payload).encode() if raw is None else raw
        self.offset = 0
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return json.loads(self.raw)

    async def read(self, size):
        part = self.raw[self.offset:self.offset + min(size, 17)]
        self.offset += len(part)
        return part


class Http:
    def __init__(self, response=None, error=None):
        self.response = response or Response()
        self.error = error
        self.calls = []

    def post(self, url, **options):
        self.calls.append((url, options))
        if self.error:
            raise self.error
        return self.response


class WssAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def config(self, **changes):
        values = dict(instance_name='voice-auth', instance_url=INSTANCE,
                      voice_service_id=SERVICE, required_agent_id=AGENT,
                      development_token='', auth_mode='servicenow')
        return SimpleNamespace(**{**values, **changes})

    def request(self, token=OPAQUE, **changes):
        values = dict(query={'instance_name': 'voice-auth',
                             'voice_service_id': SERVICE, 'auth_token': token},
                      headers={'Origin': INSTANCE}, remote='127.0.0.1')
        return SimpleNamespace(**{**values, **changes})

    async def test_opaque_is_admitted_only_after_native_service_agent_authorization(self):
        http = Http()
        self.assertIs(await authorize(self.request(), self.config(), http), True)
        self.assertEqual(len(http.calls), 1)
        url, options = http.calls[0]
        self.assertEqual(url, AUTH_URL)
        self.assertEqual(options['json'], {'serviceId': SERVICE, 'clientApp': 'admin_test'})
        self.assertEqual(options['headers']['Authorization'], 'Bearer ' + OPAQUE)
        self.assertFalse(options['allow_redirects'])

    async def test_opaque_receives_same_bounded_service_bound_call_settings(self):
        http = Http(Response(payload=authorized_settings()))
        result = await authorize(self.request(), self.config(), http, with_settings=True)
        self.assertIsInstance(result, CallSettings)
        self.assertEqual(result.service_id, SERVICE)
        self.assertEqual(result.introduction, 'Guten Tag.')
        self.assertNotIn(OPAQUE, repr(result))
        self.assertEqual(http.calls[0][1]['json'], {
            'serviceId': SERVICE, 'clientApp': 'admin_test', 'assistantSettingsVersion': 1})
        self.assertEqual(http.calls[0][1]['headers']['Accept-Encoding'], 'identity')
        self.assertFalse(http.calls[0][1]['auto_decompress'])

    async def test_jwt_is_forwarded_unchanged_and_native_authority_is_required(self):
        accepted = Http()
        self.assertIs(await authorize(self.request(JWT), self.config(), accepted), True)
        self.assertEqual(accepted.calls[0][1]['headers']['Authorization'], 'Bearer ' + JWT)
        denied = Http(Response(status=401))
        with self.assertLogs('native-voice', level='WARNING') as logs:
            self.assertIs(await authorize(self.request(JWT), self.config(), denied), False)
        self.assertEqual(len(denied.calls), 1)
        self.assertNotIn(JWT, '\n'.join(logs.output))

    async def test_opaque_native_denials_remain_closed_without_retry(self):
        for status in (401, 403, 500):
            with self.subTest(status=status):
                http = Http(Response(status=status))
                with self.assertLogs('native-voice', level='WARNING') as logs:
                    self.assertIs(await authorize(self.request(), self.config(), http), False)
                self.assertEqual(len(http.calls), 1)
                self.assertNotIn(OPAQUE, '\n'.join(logs.output))

    async def test_native_success_without_required_agent_is_not_admission(self):
        for payload in ({'result': []}, {'result': ['b' * 32]}, {'error': 'denied'}):
            with self.subTest(payload=payload):
                http = Http(Response(payload=payload))
                with self.assertLogs('native-voice', level='WARNING'):
                    self.assertIs(await authorize(self.request(), self.config(), http), False)
                self.assertEqual(len(http.calls), 1)

    async def test_bad_opaque_or_three_part_syntax_is_refused_before_forwarding(self):
        tokens = ('', 'Bearer token', 'with space', 'with:colon', 'with,comma',
                  'with;semicolon', 'nonascii-\u00ef', 'trail=ing', 'a=b',
                  'opaque\u0130', 'opaque\u0131', 'opaque\u017f', 'opaque\u212a',
                  'header.payload.signature ', 'header.pay load.signature',
                  'header.payload.sig:bad', 'header.\r\npayload.signature',
                  'header.payload.\x00signature')
        for token in tokens:
            with self.subTest(token=repr(token)):
                http = Http()
                admitted = await authorize(self.request(token), self.config(), http)
                self.assertEqual(http.calls, [])
                self.assertIs(admitted, False)

    async def test_authorization_limit_matches_original_caller_binder(self):
        # 8192 bytes includes the seven-byte 'Bearer ' prefix.
        boundary = 'x' * 8185
        http = Http()
        self.assertIs(await authorize(self.request(boundary), self.config(), http), True)
        self.assertEqual(http.calls[0][1]['headers']['Authorization'], 'Bearer ' + boundary)
        oversized = Http()
        self.assertIs(await authorize(self.request('x' * 8186), self.config(), oversized), False)
        self.assertEqual(oversized.calls, [])

    async def test_exact_origin_instance_and_service_guards_remain_required(self):
        good = self.request()
        requests = [self.request(headers={}),
                    self.request(headers={'Origin': 'https://other.example.test'}),
                    self.request(headers={'Origin': INSTANCE + '/'}),
                    self.request(headers={'Origin': INSTANCE + '\r\nX-Test: other'})]
        for field, value in (('instance_name', 'other'), ('voice_service_id', '9' * 32)):
            query = copy.deepcopy(good.query)
            query[field] = value
            requests.append(self.request(query=query))
        for request in requests:
            with self.subTest(request=request):
                http = Http()
                self.assertIs(await authorize(request, self.config(), http), False)
                self.assertEqual(http.calls, [])

    async def test_native_malformed_body_or_transport_failure_is_not_admission(self):
        for http in (Http(Response(raw=b'{not-json')),
                     Http(error=OSError('synthetic private credential: ' + OPAQUE))):
            with self.subTest(http=http):
                self.assertIs(await authorize(self.request(), self.config(), http), False)
                self.assertEqual(len(http.calls), 1)

    async def test_settings_still_refuse_wrong_service_or_compressed_native_envelope(self):
        wrong = authorized_settings()
        wrong['result']['assistant_settings']['service_id'] = '9' * 32
        for response in (Response(payload=wrong),
                         Response(payload=authorized_settings(), headers={'Content-Encoding': 'gzip'})):
            with self.subTest(response=response):
                http = Http(response)
                self.assertIs(await authorize(self.request(), self.config(), http, with_settings=True), False)
                self.assertEqual(len(http.calls), 1)

    async def test_development_loopback_guard_is_unchanged_and_uses_no_native_authority(self):
        token = 'synthetic-development-only-secret-123456'
        config = self.config(development_token=token)
        http = Http()
        self.assertIs(await authorize(self.request(token), config, http), True)
        self.assertIs(await authorize(self.request(token, remote='192.0.2.1'), config, http), False)
        self.assertEqual(http.calls, [])


if __name__ == '__main__':
    unittest.main()
