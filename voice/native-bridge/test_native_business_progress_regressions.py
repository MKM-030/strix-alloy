"""CPU regressions for retained originals and cross-control context snapshots.

Only fake dialogue/model/audio/HTTP dependencies run. Two desired delivery
invariants deliberately fail against the audited baseline pending design review.
"""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from native_backend import BackendEvent
from native_bridge import Config, Dialog
from native_duplex import NativeDuplex
from test_native_control_handoff import OnsetTurn
from test_native_duplex import FakeCall
from voice.bridge import Bridge, Conversation, ConversationBinding, Settings
from aiohttp import web


CONTROL = 'Soll ich die Bestellung mit diesen Angaben ausführen?'
FACT = 'Der Lieferort ist Dresden, nicht Berlin.'
FOLLOWUP = 'Bitte berücksichtige meine Korrektur.'


class HeldOriginalProgressTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.context_publications = []

        async def publish(revision, snapshot):
            self.context_publications.append(snapshot)
            return dict(state='context_action_acknowledged', revision=revision,
                        contextStored=True, promptIncluded=False, ingested=False)

        async def unavailable_model(*args, **kwargs):
            raise RuntimeError('CPU fixture has no model')

        self.lane = NativeDuplex(self.call, context_publisher=publish,
                                 conversation_factory=unavailable_model)
        self.running = asyncio.create_task(self.lane.run())

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                await asyncio.sleep(.001)

    async def next_business(self):
        return await asyncio.wait_for(self.call.dialog.started.get(), 1)

    def feed_at_onset(self, text, number, onset):
        turn = OnsetTurn((self.call.playback.generation, text, number, str(number), 0))
        turn.duplex_onset = (onset, False)
        self.call.recognized_turns.put_nowait(turn)
        return turn

    async def reach_unheard_boolean(self):
        self.call.feed('Bitte bereite den Vorgang vor.')
        self.assertEqual(await self.next_business(), 'Bitte bereite den Vorgang vor.')
        self.call.dialog.release.put_nowait(dict(reply=CONTROL, input_boundary=dict(
            source='servicenow_input_control', controlType='Boolean', label=CONTROL)))
        await self.until(lambda: self.lane._control_gate.binding is not None
                         and self.lane._backend is None)
        self.assertFalse(self.lane._control_gate.heard)
        return self.lane._input_question_snapshot()

    async def hear_current_boolean(self):
        await self.until(lambda: CONTROL in self.call.spoken and bool(self.call.playback.data))
        self.call.playback.read(len(self.call.playback.data))
        await self.until(lambda: self.lane._input_question_snapshot()[2])
        self.assertTrue(self.lane._control_gate.heard)
        return self.lane._input_question_snapshot()

    async def test_held_factual_original_reaches_non_authoritative_context_after_fresh_rejection(self):
        early_onset = await self.reach_unheard_boolean()
        original = self.feed_at_onset(FACT, 2, early_onset)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        self.assertEqual([item.turn for item in self.lane._control_gate.held], [original])
        self.assertEqual(self.context_publications, [])
        current_onset = await self.hear_current_boolean()
        self.feed_at_onset('Nein', 3, current_onset)
        self.assertEqual(await self.next_business(), 'Nein')
        self.call.dialog.release.put_nowait(dict(reply='Welche Angabe möchten Sie korrigieren?',
            input_boundary=dict(source='servicenow_input_control', controlType='InputText',
                                label='Welche Angabe möchten Sie korrigieren?')))
        await self.until(lambda: self.lane._backend is None
                         and self.lane._control_gate.binding is None)
        self.call.feed(FOLLOWUP, 4)
        self.assertEqual(await self.next_business(), FOLLOWUP)
        # Let an optional owned context publication complete without another turn.
        await asyncio.sleep(.02)
        self.assertEqual(self.call.dialog.calls,
                         ['Bitte bereite den Vorgang vor.', 'Nein', FOLLOWUP])
        self.assertTrue(any(FACT in note for note in self.context_publications),
                        'The original factual correction remains held with no delivery path')

    async def test_old_yes_keeps_its_unheard_onset_after_control_audio_completes(self):
        early_onset = await self.reach_unheard_boolean()
        original = self.feed_at_onset('Ja', 2, early_onset)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        await self.hear_current_boolean()
        self.assertEqual(self.call.dialog.calls, ['Bitte bereite den Vorgang vor.'])
        self.assertEqual([item.turn for item in self.lane._control_gate.held], [original])
        self.assertFalse(self.lane._control_gate.dispatched)
        self.assertEqual(self.context_publications, [])


class ContextSnapshotBoundaryTests(unittest.IsolatedAsyncioTestCase):
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
        owner = self

        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            async def __aenter__(self):
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


if __name__ == '__main__':
    unittest.main()
