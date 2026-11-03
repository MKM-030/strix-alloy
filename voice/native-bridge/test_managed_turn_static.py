"""Offline explicit static ICE option; no endpoint or device qualification."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

import managed_turn as mt
from test_managed_turn import MAIN, REGION, TURN, URL, HTTP, Response
import test_managed_turn as managed_fixture
import test_wss_managed_turn as wss_fixture
from test_sdk_sessions import TOKEN, INSTANCE, ASSISTANT, BASE
from test_wss_authorization import OPAQUE

OTHER = 'aivoiceservice-prod-turn-ytz.sncapps.service-now.com'
OTHER_URL = 'turns:' + OTHER + ':443?transport=tcp'


def configured(urls=(URL, OTHER_URL)):
    return mt.ManagedTurnConfiguration('https://' + MAIN, (MAIN, REGION), (TURN, OTHER), urls)


class StaticConfigurationTests(unittest.TestCase):
    def test_explicit_ordered_tuple_is_immutable_and_private(self):
        config = configured((OTHER_URL, URL))
        self.assertEqual(config.static_ice_urls, (OTHER_URL, URL))
        self.assertNotIn(TURN, repr(config))
        with self.assertRaises(AttributeError): config.static_ice_urls = (URL,)

    def test_absent_field_is_legacy_and_disabled_configuration_rejects_any_selection(self):
        self.assertIsNone(mt.ManagedTurnConfiguration().static_ice_urls)
        self.assertIsNone(mt.ManagedTurnConfiguration('https://' + MAIN, (MAIN,), (TURN,)).static_ice_urls)
        for urls in ((URL,), ()):
            with self.subTest(urls=urls), self.assertRaises(ValueError):
                mt.ManagedTurnConfiguration(static_ice_urls=urls)

    def test_constructor_rejects_wrong_shape_duplicates_or_more_than_four_urls(self):
        for urls in ([], [URL], (), (URL, URL), (URL,) * 5, 'urls', 0, (None,), ({'urls': [URL]},)):
            with self.subTest(urls=urls), self.assertRaises(ValueError): configured(urls)

    def test_constructor_rejects_unsafe_or_unapproved_urls_without_echo(self):
        for url in (
            'turns:evil.invalid:443?transport=tcp', 'turn:' + TURN + ':443?transport=tcp',
            'turns:' + TURN + ':444?transport=tcp', 'turns:' + TURN + ':443?transport=udp',
            'turns:user:private@' + TURN + ':443?transport=tcp', URL + '&credential=private',
            URL + '#private', URL + '\n', URL.upper(), 'turns:' + TURN + ':443', 'x' * 513):
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                configured((url,))
            self.assertNotIn(url, str(caught.exception))

    def test_private_file_optional_list_and_legacy_omission(self):
        raw = dict(base_origin='https://' + MAIN, signaling_hosts=[MAIN, REGION], turn_hosts=[TURN, OTHER])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'managed.json'
            path.write_text(json.dumps(raw))
            self.assertIsNone(mt.load_managed_turn_file(path).static_ice_urls)
            path.write_text(json.dumps(dict(raw, static_ice_urls=[OTHER_URL, URL])))
            self.assertEqual(mt.load_managed_turn_file(path), configured((OTHER_URL, URL)))
            for value in (None, [], [URL, URL], [URL] * 5, URL, {'urls': [URL]}, [None]):
                path.write_text(json.dumps(dict(raw, static_ice_urls=value)))
                with self.subTest(value=value), self.assertRaises(ValueError): mt.load_managed_turn_file(path)
            for value in (dict(raw, static_ice_urls=[URL], credential='private'),
                          dict(raw, static_ice_urls=[URL], static_ice_urls_extra=[])):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): mt.load_managed_turn_file(path)
            for suffix in (',"static_ice_urls":[]', ',"static_ice_urls":NaN'):
                path.write_text(json.dumps(dict(raw, static_ice_urls=[URL]))[:-1] + suffix + '}')
                with self.assertRaises(ValueError): mt.load_managed_turn_file(path)

    def test_four_distinct_explicit_urls_are_supported_in_operator_order(self):
        hosts = tuple('aivoiceservice-prod-turn-region' + str(i) + '.sncapps.service-now.com' for i in range(4))
        urls = tuple('turns:' + host + ':443?transport=tcp' for host in reversed(hosts))
        self.assertEqual(mt.ManagedTurnConfiguration('https://' + MAIN, (MAIN,), hosts, urls).static_ice_urls, urls)


class StaticBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_returns_fresh_ordered_url_rows_with_zero_http(self):
        def no_http(**kwargs): self.fail('Static URL mode must not construct an HTTP client')
        bootstrap = mt.ManagedTurnBootstrap(configured((OTHER_URL, URL)), session_factory=no_http)
        first = await bootstrap.ice_servers(TOKEN, INSTANCE, ASSISTANT)
        self.assertEqual(first, [{'urls': [OTHER_URL]}, {'urls': [URL]}])
        first[0]['urls'].append('mutated')
        first[1]['urls'][0] = 'changed'
        first.append({'urls': ['injected']})
        second = await bootstrap.ice_servers('second-private-token', INSTANCE, ASSISTANT)
        self.assertEqual(second, [{'urls': [OTHER_URL]}, {'urls': [URL]}])
        self.assertNotIn(TOKEN, json.dumps(second) + repr(bootstrap.config))
        self.assertEqual(set(vars(bootstrap)), {'config', '_session_factory'})

    async def test_invalid_call_authentication_shape_fails_before_static_or_http(self):
        def no_http(**kwargs): self.fail('Invalid call must not construct an HTTP client')
        bootstrap = mt.ManagedTurnBootstrap(configured(), session_factory=no_http)
        for token, instance, service in (
            ('', INSTANCE, ASSISTANT), ('bad\nheader', INSTANCE, ASSISTANT),
            (TOKEN, 'other.example', ASSISTANT), (TOKEN, INSTANCE, '../bad'),
            (None, INSTANCE, ASSISTANT), (TOKEN, None, ASSISTANT), (TOKEN, INSTANCE, None)):
            with self.subTest(token=token, instance=instance, service=service), self.assertRaises(mt.ManagedTurnUnavailable):
                await bootstrap.ice_servers(token, instance, service)

    async def test_legacy_omission_still_waits_for_exact_metadata_deletion(self):
        release = asyncio.Event()
        delete = Response(block=release)
        http = HTTP(delete=delete)
        bootstrap = http.bootstrap()
        self.assertIsNone(bootstrap.config.static_ice_urls)
        task = asyncio.create_task(bootstrap.ice_servers(TOKEN, INSTANCE, ASSISTANT))
        try:
            await asyncio.wait_for(delete.entered.wait(), 1)
            self.assertFalse(task.done())
            self.assertEqual([row[0] for row in http.calls], ['POST', 'DELETE'])
        finally:
            release.set()
        self.assertEqual(await asyncio.wait_for(task, 1), [{'urls': [URL]}])
        self.assertTrue(http.closed)

    async def test_each_call_keeps_fresh_oauth_identity_and_clearable_servers(self):
        bootstrap = mt.ManagedTurnBootstrap(configured(), session_factory=lambda **kwargs: self.fail('HTTP'))
        one = mt.session_host_ice(await bootstrap.ice_servers(TOKEN, INSTANCE, ASSISTANT), TOKEN, INSTANCE, ASSISTANT)
        two = mt.session_host_ice(await bootstrap.ice_servers('fresh-second-token', INSTANCE, ASSISTANT), 'fresh-second-token', INSTANCE, ASSISTANT)
        self.assertEqual(one[0].username, INSTANCE + ':' + ASSISTANT + ':' + TOKEN)
        self.assertEqual(two[0].username, INSTANCE + ':' + ASSISTANT + ':fresh-second-token')
        self.assertEqual(one[0].credential, 'oauth')
        mt.clear_session_ice(one)
        self.assertEqual(one, [])
        self.assertIsNotNone(two[0].username)
        mt.clear_session_ice(two)


class StaticSDKContractTests(unittest.IsolatedAsyncioTestCase):
    headers = managed_fixture.ManagedSDKTests.headers
    create = managed_fixture.ManagedSDKTests.create
    asyncTearDown = managed_fixture.ManagedSDKTests.asyncTearDown

    async def asyncSetUp(self):
        await managed_fixture.ManagedSDKTests.asyncSetUp(self)
        self.manager.managed_turn = mt.ManagedTurnBootstrap(configured(), session_factory=self.http.factory)

    test_static_sdk_refusal_and_shared_capacity_preserve_admission = managed_fixture.ManagedSDKTests.test_rejected_auth_admission_context_and_capacity_never_reach_cloud

    async def test_static_sdk_uses_original_oauth_and_local_signaling_without_discovery(self):
        response = await self.create()
        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertEqual(result['iceServers'], [{'urls': ['stun:stun.l.google.com:19302']},
                                                {'urls': [URL]}, {'urls': [OTHER_URL]}])
        self.assertEqual(result['endpoint_url'], 'https://strix-alloy.tail7f425a.ts.net')
        self.assertEqual(self.http.calls, [])
        self.assertIsNone(self.http.factory_args)
        self.assertEqual(self.host_servers[0][0].username, INSTANCE + ':' + ASSISTANT + ':' + TOKEN)
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertEqual((await self.create()).status, 503)
        self.assertEqual(len(self.calls), 1)
        response = await self.client.delete(BASE + '/' + result['session_id'], headers=self.headers())
        self.assertEqual(response.status, 204)
        await asyncio.wait_for(self.calls[0].close_complete.wait(), 1)
        self.assertFalse(self.active)


class StaticWssContractTests(unittest.IsolatedAsyncioTestCase):
    make_app = wss_fixture.WssManaged.make_app
    request = wss_fixture.WssManaged.request
    asyncTearDown = wss_fixture.WssManaged.asyncTearDown

    async def asyncSetUp(self):
        await wss_fixture.WssManaged.asyncSetUp(self)
        self.config.private_managed_turn = configured((URL,))
        self.make_app()

    test_static_wss_authorization_refusal_precedes_allocation = wss_fixture.WssManaged.test_authorization_refusal_never_allocates_or_discovers

    async def test_static_wss_original_authority_and_own_credentials_are_preserved_then_cleared(self):
        ws = await self.connect(self.request())
        self.assertEqual(self.metadata.calls, [])
        self.assertIsNone(self.metadata.factory_args)
        self.assertEqual(ws.sent[0]['iceServers'], [{'urls': [URL],
            'username': self.config.instance_name + ':' + wss_fixture.SERVICE + ':' + OPAQUE, 'credential': 'oauth'}])
        call = self.calls[0]
        self.assertEqual(call.dialog.authorization, 'Bearer ' + OPAQUE)
        self.assertTrue(call.peer.closed)
        self.assertEqual(call._session_ice_servers, [])
        self.assertTrue(all(server.username is None and server.credential is None for server in call.original_ice))
        self.assertEqual(len(self.manager.active), 0)


if __name__ == '__main__': unittest.main()
