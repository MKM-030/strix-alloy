"""WSS managed-ICE regressions with synthetic external boundaries."""
import asyncio
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import native_bridge as bridge
from aiohttp import web, WSMsgType
import managed_turn
import sdk_sessions
from host_ice import HostIceConfiguration
from test_assistant_settings import authorized_settings, SERVICE, AGENT
from test_wss_authorization import Http, Response, OPAQUE
from test_managed_turn import HTTP, Response as MetadataResponse, config as managed_config, payload, URL, MAIN, REGION


class Peer:
    def __init__(self, configuration):
        self.ice = configuration.iceServers
        self.localDescription = None
        self.closed = False
        self.sctp = None

    def on(self, *_):
        pass

    def addTrack(self, _):
        pass

    async def setRemoteDescription(self, description):
        self.remote = description

    async def createAnswer(self):
        return SimpleNamespace(type='answer', sdp='synthetic-local-answer')

    async def setLocalDescription(self, description):
        self.localDescription = description

    async def addIceCandidate(self, candidate):
        raise AssertionError('no candidate fixture was sent')

    async def close(self):
        self.closed = True

    def getTransceivers(self):
        return []


class Dialog:
    must_reset = False

    def bind_caller_authorization(self, value):
        self.authorization = value

    async def close(self):
        self.closed = True


class WebSocket:
    def __init__(self, **_):
        self.prepared = False
        self.closed = False
        self.sent = []
        self.messages = [{'type': 'offer', 'sdp': {'type': 'offer', 'sdp': 'synthetic-offer'}}, {'type': 'disconnect'}]

    async def prepare(self, _):
        self.prepared = True

    async def send_json(self, value):
        self.sent.append(copy.deepcopy(value))

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return SimpleNamespace(type=WSMsgType.TEXT, data=json.dumps(self.messages.pop(0)))


class WssManaged(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patches = []
        self.tasks = []
        self.calls = []
        self.websockets = []
        self.metadata = HTTP()
        self.auth = Http(Response(payload=authorized_settings()))
        self.auth.close = AsyncMock()
        self.reference_http = Http(Response(payload=authorized_settings()))
        self.reference_http.close = AsyncMock()
        self.config = bridge.Config(instance_name='voice-auth', voice_service_id=SERVICE,
            required_agent_id=AGENT, auth_mode='servicenow', native_sdk_enabled=True,
            sdk_public_origin='https://voice-relay.example.test', private_managed_turn=managed_config(),
            private_host_ice=HostIceConfiguration('turn:operator.invalid:3478', 'OPERATOR_USER', 'OPERATOR_SECRET'))
        original_call = bridge.NativeCall
        calls = self.calls
        class RecordingCall(original_call):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.original_ice = list(self._session_ice_servers)
                calls.append(self)
            async def process_turns(self):
                await asyncio.Event().wait()
        original_register = sdk_sessions.register_sdk_routes
        def register(*args, **kwargs):
            self.manager = original_register(*args, **kwargs)
            return self.manager
        def websocket(**kwargs):
            ws = WebSocket(**kwargs)
            self.websockets.append(ws)
            return ws
        for item in [patch.object(bridge, 'RTCPeerConnection', Peer),
                     patch.object(bridge, 'NativeCall', RecordingCall),
                     patch.object(bridge.web, 'WebSocketResponse', websocket),
                     patch.object(bridge, 'ManagedTurnBootstrap', lambda config: managed_turn.ManagedTurnBootstrap(config, session_factory=self.metadata.factory), create=True),
                     patch.object(bridge, 'ClientSession',
                                  lambda **options: self.reference_http if 'cookie_jar' in options else self.auth),
                     patch.object(bridge, 'require_model_ready', AsyncMock()),
                     patch.object(bridge, 'require_asr_ready', AsyncMock()),
                     patch.object(sdk_sessions, 'register_sdk_routes', register)]:
            item.start()
            self.patches.append(item)
        self.make_app()

    def make_app(self):
        self.app = bridge.create_app(self.config, speech_factory=lambda _: object(), dialog_factory=Dialog)
        self.app[bridge.HTTP_KEY] = self.auth
        self.connect = next(route.handler for route in self.app.router.routes()
                            if route.method == 'GET' and route.resource.canonical == '/webrtc/connect/agent_operator')

    def request(self, **query_changes):
        return SimpleNamespace(query={'instance_name': self.config.instance_name,
            'voice_service_id': SERVICE, 'auth_token': OPAQUE, **query_changes},
            headers={'Origin': self.config.instance_url}, remote='127.0.0.1')

    async def asyncTearDown(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for call in self.calls:
            await call.close()
        for item in reversed(self.patches):
            item.stop()

    async def test_managed_wire_uses_original_authority_relay_and_owned_credentials(self):
        with self.assertLogs(level='INFO') as logs:
            ws = await self.connect(self.request())
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST', 'DELETE'])
        create = self.metadata.calls[0]
        self.assertEqual(create[2]['headers']['Authorization'], 'Bearer ' + OPAQUE)
        self.assertEqual(create[2]['params']['instance_name'], self.config.instance_name)
        self.assertEqual(create[2]['params']['voice_service_id'], SERVICE)
        self.assertEqual(create[2]['json'], {'agent_id': 'agent_operator'})
        self.assertEqual(self.metadata.calls[1][1], 'https://' + REGION + '/api/webrtc/sessions/fixture_metadata_123')
        self.assertEqual(ws.sent[0]['iceServers'], [{'urls': [URL],
            'username': self.config.instance_name + ':' + SERVICE + ':' + OPAQUE, 'credential': 'oauth'}])
        call = self.calls[0]
        self.assertEqual(call.call_settings.introduction, 'Guten Tag.')
        self.assertEqual(call.dialog.authorization, 'Bearer ' + OPAQUE)
        self.assertEqual([server.urls for server in call.original_ice], [[URL]])
        self.assertTrue(call.peer.closed)
        self.assertEqual(call._session_ice_servers, [])
        self.assertTrue(all(server.username is None and server.credential is None for server in call.original_ice))
        self.assertEqual(len(self.manager.active), 0)
        self.assertNotIn(OPAQUE, '\n'.join(logs.output))
        self.assertNotIn('OPERATOR_SECRET', json.dumps(ws.sent))
        self.assertNotIn('remote-private-', json.dumps(ws.sent))

    async def test_disabled_managed_turn_preserves_fixed_client_stun_and_host_private_boundary(self):
        self.config.private_managed_turn = managed_turn.ManagedTurnConfiguration()
        self.make_app()
        ws = await self.connect(self.request())
        self.assertEqual(self.metadata.calls, [])
        self.assertEqual(ws.sent[0]['iceServers'], [{'urls': [bridge.STUN_URL]}])
        self.assertNotIn('OPERATOR_SECRET', json.dumps(ws.sent))

    async def test_authorization_refusal_never_allocates_or_discovers(self):
        self.auth.response = Response(status=403)
        with self.assertRaises(web.HTTPUnauthorized):
            await self.connect(self.request())
        self.assertEqual(self.metadata.calls, [])
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.manager.active), 0)

    async def test_wrong_service_prevents_any_provider_dispatch(self):
        with self.assertRaises(web.HTTPUnauthorized):
            await self.connect(self.request(voice_service_id='9' * 32))
        self.assertEqual(self.auth.calls, [])
        self.assertEqual(self.metadata.calls, [])

    async def test_pending_metadata_reserves_shared_capacity_through_cleanup(self):
        release = asyncio.Event()
        self.metadata.delete_response = MetadataResponse(block=release)
        task = asyncio.create_task(self.connect(self.request()))
        self.tasks.append(task)
        await self.metadata.delete_response.entered.wait()
        self.assertEqual(len(self.manager.active), 1)
        owner = next(iter(self.manager.active))
        self.assertTrue(callable(owner.close))
        self.assertEqual(self.calls, [])
        self.auth.response = Response(payload=authorized_settings())
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())
        self.manager.admit = AsyncMock(return_value=SimpleNamespace(instance_url=self.config.instance_url,
            assistant_id=SERVICE, voice_agent_id=AGENT, sdk_agent_id='agent_operator', receive_data=True,
            call_settings=bridge.CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)))
        body = json.dumps({'agent_id': 'agent_operator'}).encode()
        sdk_request = SimpleNamespace(raw_headers=((b'Authorization', ('Bearer ' + OPAQUE).encode()),
            (b'Content-Type', b'application/json')), content_length=len(body),
            content=SimpleNamespace(read=AsyncMock(side_effect=[body, b''])),
            rel_url=SimpleNamespace(raw_query_string='instance_name=voice-auth&receive_data=true'))
        with self.assertRaises(sdk_sessions._Rejected) as rejected:
            await self.manager.create(sdk_request)
        self.assertEqual(rejected.exception.status, 503)
        self.assertEqual(len(self.metadata.calls), 2)
        release.set()
        await task
        self.assertEqual(len(self.manager.active), 0)

    async def test_metadata_delete_failure_is_closed_before_peer_allocation(self):
        self.metadata.delete_response = MetadataResponse(status=500)
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.manager.active), 0)
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST', 'DELETE'])

    async def test_malformed_ice_cleans_exact_metadata_and_never_creates_peer(self):
        self.metadata.post_response = MetadataResponse(payload(iceServers=[{'urls': ['turns:evil.invalid:443?transport=tcp']}]))
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())
        self.assertEqual(self.calls, [])
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST', 'DELETE'])
        self.assertEqual(len(self.manager.active), 0)

    async def test_cancel_during_known_metadata_cleanup_retains_owner_until_delete_finishes(self):
        release = asyncio.Event()
        self.metadata.delete_response = MetadataResponse(block=release)
        task = asyncio.create_task(self.connect(self.request()))
        self.tasks.append(task)
        await self.metadata.delete_response.entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertEqual(len(self.manager.active), 1)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(self.manager.active), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(sum(value[0] == 'DELETE' for value in self.metadata.calls), 1)

    async def test_normal_application_cleanup_closes_pending_owner_without_second_cancel(self):
        release = asyncio.Event()
        self.metadata.delete_response = MetadataResponse(block=release)
        lifecycle = self.app.cleanup_ctx[0](self.app)
        await anext(lifecycle)
        task = asyncio.create_task(self.connect(self.request()))
        self.tasks.append(task)
        await self.metadata.delete_response.entered.wait()
        for callback in self.app.on_shutdown:
            await callback(self.app)
        cleanup = asyncio.create_task(anext(lifecycle, None))
        self.tasks.append(cleanup)
        await asyncio.sleep(0)
        self.assertEqual(len(self.manager.active), 1)
        release.set()
        await cleanup
        self.assertEqual(task.cancelling(), 1)
        self.assertEqual(len(self.manager.active), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(sum(value[0] == 'DELETE' for value in self.metadata.calls), 1)
        self.assertTrue(self.metadata.closed)
        self.auth.close.assert_awaited_once()
        self.reference_http.close.assert_awaited_once()
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())

    async def test_shutdown_does_not_cancel_unrelated_live_call(self):
        class Other:
            async def close(self):
                raise AssertionError('shutdown admission callback must not close another owner')
        other = Other()
        self.manager.active.add(other)
        for callback in self.app.on_shutdown:
            await callback(self.app)
        self.assertIn(other, self.manager.active)
        self.manager.active.discard(other)

    async def test_failed_metadata_create_does_not_guess_cleanup_target(self):
        self.metadata.post_response = MetadataResponse(status=503)
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST'])
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.manager.active), 0)

    async def test_unapproved_provider_endpoint_only_uses_validated_cleanup_origin(self):
        self.metadata.post_response = MetadataResponse(payload(endpoint_url='https://attacker.invalid'))
        with self.assertRaises(web.HTTPServiceUnavailable):
            await self.connect(self.request())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.metadata.calls[1][1], 'https://' + MAIN + '/api/webrtc/sessions/fixture_metadata_123')
        self.assertTrue(all('attacker.invalid' not in value[1] for value in self.metadata.calls))

    async def test_cancel_while_create_is_pending_closes_http_and_releases_local_owner(self):
        release = asyncio.Event()
        self.metadata.post_response = MetadataResponse(payload(), block=release)
        task = asyncio.create_task(self.connect(self.request()))
        self.tasks.append(task)
        await self.metadata.post_response.entered.wait()
        self.assertEqual(len(self.manager.active), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.metadata.closed)
        self.assertEqual(len(self.manager.active), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST'])

    async def test_shutdown_blocks_late_discovery_result_even_if_provider_swallows_cancel(self):
        entered = asyncio.Event()
        async def late(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return [{'urls': [URL]}]
        with patch.object(managed_turn.ManagedTurnBootstrap, 'ice_servers', late):
            task = asyncio.create_task(self.connect(self.request()))
            self.tasks.append(task)
            await entered.wait()
            for callback in self.app.on_shutdown:
                await callback(self.app)
            with self.assertRaises(web.HTTPServiceUnavailable):
                await task
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.manager.active), 0)

    async def test_failed_upgrade_still_closes_peer_and_clears_session_credentials(self):
        async def fail_prepare(self, request):
            raise RuntimeError('private-' + OPAQUE)
        with patch.object(WebSocket, 'prepare', fail_prepare), self.assertLogs(level='WARNING') as logs:
            with self.assertRaises(web.HTTPServiceUnavailable):
                await self.connect(self.request())
        self.assertEqual([value[0] for value in self.metadata.calls], ['POST', 'DELETE'])
        self.assertTrue(self.calls[0].close_complete.is_set())
        self.assertTrue(self.calls[0].peer.closed)
        self.assertTrue(all(server.username is None and server.credential is None for server in self.calls[0].original_ice))
        self.assertEqual(len(self.manager.active), 0)
        self.assertNotIn(OPAQUE, '\n'.join(logs.output))

    async def test_failed_call_factory_clears_untransferred_managed_credentials(self):
        captured = []
        def fail(*args, **kwargs):
            captured.extend(kwargs['ice_servers'])
            raise RuntimeError('private-' + OPAQUE)
        with patch.object(bridge, 'NativeCall', fail), self.assertLogs(level='WARNING') as logs:
            with self.assertRaises(web.HTTPServiceUnavailable):
                await self.connect(self.request())
        self.assertTrue(captured)
        self.assertTrue(all(server.username is None and server.credential is None for server in captured))
        self.assertEqual(len(self.manager.active), 0)
        self.assertNotIn(OPAQUE, '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
