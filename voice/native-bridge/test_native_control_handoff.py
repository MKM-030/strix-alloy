"""Native FIFO/onset/audio handoff; CPU only, no model or live services."""
import asyncio
from types import SimpleNamespace
import unittest

from native_backend import BackendEvent
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall

LABEL = 'Alle Angaben sind vorhanden. Soll ich das bestellen?'


class OnsetTurn(tuple):
    pass


class NativeControlHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.call.dialog.backend_owner = object()
        self.call.dialog.input_control = BackendEvent(7, 'a'*32, 'Boolean', LABEL,
            'genuine-control-7', self.call.dialog.backend_owner)
        self.call.dialog.input_boundary = dict(source='servicenow_input_control', controlType='Boolean',
            businessRequestId='a'*32, label=LABEL)
        self.lane = NativeDuplex(self.call)

    async def asyncTearDown(self):
        await self.lane.close()

    def sync(self):
        self.assertTrue(callable(getattr(self.lane, '_sync_native_control', None)),
                        'Native does not enforce the typed control handoff')
        self.lane._sync_native_control()

    def turn(self, text, number=1, onset=None):
        turn = OnsetTurn((self.call.playback.generation, text, number, str(number), 0))
        if onset is not None:
            turn.duplex_onset = (onset, False)
        return turn

    async def test_queued_prequestion_originals_are_held_and_exact_question_has_priority(self):
        originals = [self.turn(text, i) for i, text in enumerate((
            'Wie geht jetzt weiter', 'Ja und was ist jetzt damit? Sind wir jetzt fertig oder', 'Ja'), 1)]
        self.lane._pending.extend(originals)
        self.sync()
        self.assertEqual(list(self.lane._pending), [])
        self.assertEqual([held.turn for held in self.lane._control_gate.held], originals)
        self.assertEqual([item.text for item in self.lane._outputs], [LABEL])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_control_needs_full_emitted_pcm_and_preserves_original_onset(self):
        self.sync()
        item = self.lane._outputs.popleft()
        state = self.lane._begin_speech(item)
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.lane._finish_speech(state, complete=True)
        early = self.lane._input_question_snapshot()
        self.assertFalse(early[2])
        self.call.playback.read(480)
        fresh = self.lane._input_question_snapshot()
        self.assertTrue(fresh[2])
        await self.lane._accept(self.turn('Ja und was ist jetzt damit?', onset=early))
        self.assertEqual(list(self.lane._pending), [])
        self.assertEqual(self.lane._control_gate.held[-1].turn[1], 'Ja und was ist jetzt damit?')

    async def test_new_exact_control_retires_previously_heard_same_text_uid(self):
        self.sync()
        binding = self.lane._control_gate.binding
        self.lane._control_gate.mark_emitted(binding)
        self.call.dialog.input_control = BackendEvent(8, 'a'*32, 'Boolean', LABEL,
            'replacement-control', self.call.dialog.backend_owner)
        self.sync()
        self.assertFalse(self.lane._control_gate.heard)
        self.assertNotEqual(self.lane._control_gate.binding, binding)

    async def test_control_output_loses_authority_immediately_on_owner_reset(self):
        self.sync()
        item = self.lane._outputs.popleft()
        self.assertTrue(self.lane._valid(item))
        self.call.dialog.backend_owner = object()
        self.assertFalse(self.lane._valid(item))

    async def test_control_output_cannot_keep_authority_after_typed_receipt_disappears(self):
        self.sync()
        item = self.lane._outputs.popleft()
        self.call.dialog.input_control = SimpleNamespace(owner=None)
        self.assertFalse(self.lane._valid(item))

    async def test_held_prequestion_context_cannot_be_published_in_a_later_request(self):
        async def publisher(*args):
            return None
        self.lane._context_publisher = publisher
        self.lane._backend = asyncio.create_task(asyncio.Event().wait())
        early = self.turn('EARLY_UNBOUND_REMARK')
        self.lane._pending.append(early)
        self.lane._queue_context_update(early)
        self.sync()
        self.call.dialog.input_control = self.call.dialog.input_boundary = None
        self.lane._sync_native_control()
        self.lane._request = 2
        later = self.turn('LATER_NEW_INPUT', 2)
        self.lane._pending.append(later)
        self.lane._queue_context_update(later)
        self.assertEqual(self.lane._context_pending['snapshot'], 'LATER_NEW_INPUT')
        self.assertEqual(self.lane._control_gate.held[0].turn[1], 'EARLY_UNBOUND_REMARK')

    async def test_caller_interrupt_requeues_the_unheard_control_under_new_epoch(self):
        self.sync()
        item = self.lane._outputs.popleft()
        self.lane._active_output = item
        self.lane._active_kind = 'backend_control'
        self.lane._begin_speech(item)
        self.call.playback.put(bytes(480), self.call.playback.generation)
        early = self.lane._input_question_snapshot()
        await self.lane._accept(self.turn('Wie geht jetzt weiter', onset=early))
        self.assertEqual([output.text for output in self.lane._outputs], [LABEL])
        self.assertTrue(self.lane._valid(self.lane._outputs[0]))

    async def test_fresh_bound_answer_reaches_native_once_with_accepted_language(self):
        self.sync()
        state = self.lane._begin_speech(self.lane._outputs.popleft())
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.lane._finish_speech(state, complete=True)
        self.call.playback.read(480)
        onset = self.lane._input_question_snapshot()
        raw = 'Nein, zuerst möchte ich den Lieferort ändern.'
        context = dict(language='de', assistant_id='assistant', profile='profile')
        self.call.turn_contexts[1] = context
        await self.lane._accept(self.turn(raw, onset=onset))
        self.assertEqual([turn[1] for turn in self.lane._pending], [raw])
        seen = []
        original = self.call.dialog.turn
        async def audit(text, **kwargs):
            seen.append(kwargs)
            return await original(text, **kwargs)
        self.call.dialog.turn = audit
        self.call.dialog.release.put_nowait(dict(reply='Welcher Lieferort soll verwendet werden?',
            input_boundary=dict(source='servicenow_input_control', controlType='InputText',
                businessRequestId='b'*32, label='Welcher Lieferort soll verwendet werden?')))
        await self.lane._business(self.lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [raw])
        self.assertEqual(seen[0]['voice_context'], context)
        self.assertEqual(seen[0]['native_control_binding'], onset[4])
        self.assertEqual(self.lane._control_gate.held, [])

    async def test_fresh_nonboolean_full_labels_are_voiced_through_typed_path(self):
        self.call.dialog.input_control = self.call.dialog.input_boundary = None
        for number, kind in enumerate(('InputText', 'Date', 'Picker'), 1):
            with self.subTest(kind=kind):
                label = f'Bitte beachten Sie die aktuelle Rückfrage.\nWelche Angabe brauchen wir für {kind}?'
                self.call.dialog.release.put_nowait(dict(reply=label,
                    input_boundary=dict(source='servicenow_input_control', controlType=kind,
                        businessRequestId='b'*32, label=label)))
                await self.lane._business(self.turn('Neue konkrete Angabe.', number))
                self.assertIn(label, [item.text for item in self.lane._outputs])
                item = next(item for item in self.lane._outputs if item.text == label)
                self.assertTrue(self.lane._valid(item))
                await self.lane._synthesize(item, self.call.playback.generation)
                self.assertIn(label, self.call.spoken)
                self.lane._outputs.clear()
                self.call.playback.read(len(self.call.playback.data))

    async def test_fresh_short_boolean_yes_no_and_mixed_raw_are_not_legacy_gated_again(self):
        for raw in ('Ja', 'Nein', 'Ja, und bitte erkläre mir den nächsten Schritt.'):
            with self.subTest(raw=raw):
                await self.lane.close()
                await self.asyncSetUp()
                label = 'Soll ich das bestellen?'
                event = self.call.dialog.input_control
                self.call.dialog.input_control = BackendEvent(event.event_id, event.business_request_id,
                    'Boolean', label, event.control_uid, event.owner)
                self.call.dialog.input_boundary['label'] = label
                self.sync()
                state = self.lane._begin_speech(self.lane._outputs.popleft())
                self.call.playback.put(bytes(480), self.call.playback.generation)
                self.lane._finish_speech(state, complete=True)
                self.call.playback.read(480)
                onset = self.lane._input_question_snapshot()
                await self.lane._accept(self.turn(raw, onset=onset))
                self.call.dialog.release.put_nowait('Native Rückmeldung.')
                await self.lane._business(self.lane._pending.popleft())
                self.assertEqual(self.call.dialog.calls, [raw])


if __name__ == '__main__':
    unittest.main()
