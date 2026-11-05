"""CPU-only acknowledged context-prefix and asynchronous ownership regressions."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiohttp import web
from native_backend import BackendEvent
from native_bridge import Config, Dialog
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall, FakeDialog
from voice.bridge import Bridge, Conversation, ConversationBinding, Settings

CONTROL = 'Soll ich die Bestellung mit diesen Angaben ausführen?'
FACT = 'Der Lieferort ist Dresden, nicht Berlin.'


class ContextSnapshotFixture:
    async def asyncSetUp(self):
        self.bridge = Bridge(Settings(instance_url='https://fixture.invalid',
            user_id='fixture', email='fixture@example.invalid'), 'test-token', 'audio', 'callback')
        self.session = Conversation()
        self.bridge.sessions[self.session.sid] = self.session
        self.session.started = self.session.busy = True
        self.session.requests.append('a' * 32)
        self.session.conversation_binding = ConversationBinding('c' * 32, 'd' * 32, 'e' * 32)
        self.session.voice_context = {'voice_assistant': 'f' * 32}
        self.upstream = []
        self.statuses = []
        self.upstream_error = None
        self.upstream_arrived = asyncio.Event()
        self.upstream_release = asyncio.Event()
        self.upstream_release.set()
        owner = self

        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            async def __aenter__(self):
                owner.upstream_arrived.set()
                await owner.upstream_release.wait()
                if owner.upstream_error is not None:
                    raise owner.upstream_error
                return self

            async def __aexit__(self, *args):
                pass

            @property
            def content(self):
                return self

            async def iter_chunked(self, size):
                payload = self.payload
                yield json.dumps(dict(status='success', result=dict(
                    state='caller_context_stored', contextStored=True,
                    requestId=payload['requestId'], contextRequestId=payload['requestId'],
                    revision=payload['revision'], conversationId='c' * 32,
                    executionPlanId='f' * 32, promptIncluded=False, ingested=False))).encode()

        def post(url, **kwargs):
            owner.upstream.append(kwargs['json'])
            return Response(kwargs['json'])

        async def body(request):
            return request.data

        self.bridge.http = SimpleNamespace(post=post)
        self.bridge.json = body
        self.publisher = Dialog(Config())
        self.publisher.http = object()
        self.publisher.csrf = 'fixture'
        self.publisher.metadata['conversation_id'] = 'c' * 32

        async def request(method, path, **kwargs):
            self.assertEqual((method, path), ('POST', '/api/context-update'))
            incoming = SimpleNamespace(_voice_session=self.session, data=kwargs['json'])
            try:
                response = await self.bridge.context_update(incoming)
            except web.HTTPException as error:
                self.statuses.append(error.status)
                raise RuntimeError('Context transport rejected') from None
            self.statuses.append(response.status)
            return json.loads(response.body)

        self.publisher.request = request
        self.call = FakeCall()
        self.call.dialog.metadata = {'conversation_id': 'c' * 32}
        self.lane = NativeDuplex(self.call, context_publisher=self.publisher.publish_context_update)
        self.lane._backend = asyncio.create_task(asyncio.Event().wait())
        self.context_worker = asyncio.create_task(self.lane._context_loop())

    async def asyncTearDown(self):
        self.context_worker.cancel()
        await asyncio.gather(self.context_worker, return_exceptions=True)
        await self.lane.close()

    async def publish_original(self, text, number):
        turn = (self.call.playback.generation, text, number, str(number), 0)
        await self.lane._accept(turn)
        item = self.lane._context_candidate
        self.assertIsNotNone(item)
        await asyncio.wait_for(item['done'].wait(), 1)
        return item

    def cross_boolean_boundary(self):
        owner = self.call.dialog.backend_owner
        self.call.dialog.input_control = BackendEvent(1, 'a' * 32, 'Boolean', CONTROL,
                                                       'boolean-fixture', owner)
        self.lane._sync_native_control()
        self.call.dialog.input_control = BackendEvent(2, 'b' * 32, 'InputText',
            'Welche Angabe möchten Sie ergänzen?', 'text-fixture', owner)
        self.lane._sync_native_control()
        self.session.requests.append('b' * 32)

    async def test_fresh_post_control_update_retains_acknowledged_wire_prefix(self):
        first = await self.publish_original('Lieferort Berlin.', 1)
        self.assertTrue(first['ack']['contextStored'])
        self.cross_boolean_boundary()
        second = await self.publish_original('Eintritt am ersten Dezember.', 2)
        self.assertEqual(self.statuses, [200, 200],
                         'A fresh local snapshot is rejected against the old Bridge prefix')
        self.assertTrue(second['ack']['contextStored'])
        self.assertEqual(self.upstream[-1]['caller_updates'],
                         'Lieferort Berlin.\nEintritt am ersten Dezember.')
        self.assertEqual(self.call.dialog.calls, [])

    async def test_unsent_prequestion_original_is_held_without_entering_later_snapshot(self):
        self.context_worker.cancel()
        await asyncio.gather(self.context_worker, return_exceptions=True)
        turn = (0, FACT, 1, '1', 0)
        await self.lane._accept(turn)
        self.assertEqual(self.lane._context_candidate['snapshot'], FACT)
        self.cross_boolean_boundary()
        self.assertEqual([item.turn for item in self.lane._control_gate.held], [turn])
        self.context_worker = asyncio.create_task(self.lane._context_loop())
        later = await self.publish_original('Eintritt am ersten Dezember.', 2)
        self.assertTrue(later['ack']['contextStored'])
        self.assertEqual(self.upstream[-1]['caller_updates'], 'Eintritt am ersten Dezember.')
        self.assertNotIn(FACT, self.upstream[-1]['caller_updates'])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_same_scope_cumulative_originals_reach_bridge_unchanged(self):
        await self.publish_original('Lieferort Berlin.', 1)
        second = await self.publish_original('Eintritt am ersten Dezember.', 2)
        self.assertEqual(self.statuses, [200, 200])
        self.assertTrue(second['ack']['contextStored'])
        self.assertEqual(self.upstream[-1]['caller_updates'],
                         'Lieferort Berlin.\nEintritt am ersten Dezember.')
        self.assertEqual([turn[1] for turn in self.lane._pending],
                         ['Lieferort Berlin.', 'Eintritt am ersten Dezember.'])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_first_snapshot_after_control_has_no_previous_prefix_conflict(self):
        self.cross_boolean_boundary()
        first = await self.publish_original('Eintritt am ersten Dezember.', 1)
        self.assertEqual(self.statuses, [200])
        self.assertTrue(first['ack']['contextStored'])
        self.assertEqual(self.upstream[-1]['caller_updates'], 'Eintritt am ersten Dezember.')



class AcknowledgedContextPrefixTests(ContextSnapshotFixture, unittest.IsolatedAsyncioTestCase):
    async def begin_publication(self, text, number=1):
        turn = (self.call.playback.generation, text, number, str(number), 0)
        await self.lane._accept(turn)
        item = self.lane._context_candidate
        await asyncio.wait_for(self.upstream_arrived.wait(), 1)
        return item

    async def assert_no_later_publication(self):
        count = len(self.upstream)
        turn = (self.call.playback.generation, 'Neue unveränderte Originalangabe.', 9, '9', 0)
        await self.lane._accept(turn)
        await asyncio.sleep(.01)
        self.assertEqual(len(self.upstream), count)
        self.assertIsNone(self.lane._context_candidate)
        self.assertIn(turn, self.lane._pending)
        self.assertEqual(self.call.dialog.calls, [])

    async def test_queued_only_ack_retains_wire_prefix_without_sending_consent_to_native_memory(self):
        # Exercise the valid publisher contract even though normal busy-input
        # admission filters this short backchannel before the context queue.
        turn = (0, 'Ja', 1, '1', 0)
        self.lane._pending.append(turn)
        self.lane._queue_context_update(turn)
        first = self.lane._context_candidate
        await asyncio.wait_for(first['done'].wait(), 1)
        self.assertTrue(first['ack']['queuedOnly'])
        self.assertFalse(first['ack']['contextStored'])
        self.assertEqual(self.upstream, [])
        self.cross_boolean_boundary()
        second = await self.publish_original('Lieferort Dresden.', 2)
        self.assertEqual(self.statuses, [200, 200])
        self.assertTrue(second['ack']['contextStored'])
        self.assertEqual(self.session.context_text, 'Ja\nLieferort Dresden.')
        self.assertEqual(self.upstream[-1]['caller_updates'], '\nLieferort Dresden.')
        self.assertEqual(self.call.dialog.calls, [])

    async def test_boolean_crossing_inflight_ack_drops_fresh_suffix_and_never_reopens_context(self):
        self.upstream_release.clear()
        first = await self.begin_publication('Erste Originalangabe.')
        self.cross_boolean_boundary()
        await self.assert_no_later_publication()
        self.upstream_release.set()
        await asyncio.wait_for(first['done'].wait(), 1)
        self.assertEqual(self.statuses, [200])
        self.assertIsNone(first['ack'])
        self.assertEqual(self.lane._context_snapshot, '')
        self.cross_boolean_boundary()
        await self.assert_no_later_publication()

    async def test_uncertain_transport_disables_only_context_without_retrying_claimed_prefix(self):
        self.upstream_error = OSError('synthetic storage uncertainty')
        item = await self.publish_original('Erste Originalangabe.', 1)
        self.assertIsNone(item['ack'])
        self.assertEqual(self.statuses, [502])
        self.assertEqual(self.session.context_text, 'Erste Originalangabe.')
        self.assertTrue(self.session.busy)
        self.assertFalse(self.session.failed)
        self.upstream_error = None
        await self.assert_no_later_publication()

    async def test_invalid_ack_never_becomes_a_transport_prefix(self):
        async def malformed(revision, snapshot):
            return dict(state='context_action_acknowledged', revision=True,
                        contextStored=True, promptIncluded=False, ingested=False)

        self.lane._context_publisher = malformed
        item = await self.publish_original('Erste Originalangabe.', 1)
        self.assertIsNone(item['ack'])
        await self.assert_no_later_publication()

    async def test_owner_replacement_rejects_late_ack(self):
        self.upstream_release.clear()
        item = await self.begin_publication('Erste Originalangabe.')
        self.call.dialog.backend_owner = object()
        self.upstream_release.set()
        await asyncio.wait_for(item['done'].wait(), 1)
        self.assertIsNone(item['ack'])
        self.assertEqual(self.lane._context_snapshot, '')
        await self.assert_no_later_publication()

    async def test_owner_replacement_cannot_reuse_an_acknowledged_prefix(self):
        await self.publish_original('Erste Originalangabe.', 1)
        self.call.dialog.backend_owner = object()
        await self.assert_no_later_publication()
        self.assertEqual(self.lane._context_snapshot, '')

    async def test_dialog_replacement_cannot_reuse_an_acknowledged_prefix(self):
        await self.publish_original('Erste Originalangabe.', 1)
        replacement = FakeDialog()
        replacement.backend_owner = self.call.dialog.backend_owner
        replacement.metadata = dict(self.call.dialog.metadata)
        self.call.dialog = replacement
        await self.assert_no_later_publication()
        self.assertEqual(self.lane._context_snapshot, '')

    async def test_conversation_replacement_cannot_reuse_an_acknowledged_prefix(self):
        await self.publish_original('Erste Originalangabe.', 1)
        self.call.dialog.metadata['conversation_id'] = 'd' * 32
        await self.assert_no_later_publication()
        self.assertEqual(self.lane._context_snapshot, '')
