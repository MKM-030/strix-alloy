"""CPU-only held original-note recovery and the real MESSAGE ACK callback."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_backend import BackendEvent
from native_bridge import Config, Dialog
from native_duplex import BackendTurnUnavailable, NativeDuplex
from test_native_control_handoff import OnsetTurn
from test_native_duplex import FakeCall, FakeDialog

CONTROL = 'Soll ich die Bestellung mit diesen Angaben ausführen?'
FACT = 'Der Lieferort ist Dresden, nicht Berlin.'
FOLLOWUP = 'Bitte berücksichtige meine Korrektur.'


class HeldContextFixture:
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.call.dialog.metadata = {"conversation_id": "c" * 32}
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


class HeldNoteRecoveryTests(HeldContextFixture, unittest.IsolatedAsyncioTestCase):
    async def stage_notes(self, originals):
        onset = await self.reach_unheard_boolean()
        for number, text in enumerate(originals, 2):
            self.feed_at_onset(text, number, onset)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        fresh = await self.hear_current_boolean()
        self.feed_at_onset('Nein', len(originals) + 2, fresh)
        self.assertEqual(await self.next_business(), 'Nein')
        self.call.dialog.release.put_nowait(dict(reply='Welche Angabe möchten Sie korrigieren?',
            input_boundary=dict(source='servicenow_input_control', controlType='InputText',
                                label='Welche Angabe möchten Sie korrigieren?')))
        await self.until(lambda: self.lane._backend is None
                         and self.lane._control_gate.binding is None)
        self.assertEqual(self.context_publications, [], 'Idle InputText cannot publish context')

    async def next_real_turn(self):
        self.call.feed(FOLLOWUP, 20)
        self.assertEqual(await self.next_business(), FOLLOWUP)
        await asyncio.sleep(.02)

    def recovered(self):
        self.assertTrue(self.context_publications, 'No held-note context publication')
        raw = self.context_publications[-1].split('\n', 1)[1]
        return json.JSONDecoder().raw_decode(raw)[0]

    async def test_mixed_fact_and_yes_remains_whole_quoted_note_without_message_replay(self):
        raw = 'Ja, und der Lieferort ist Dresden, nicht Berlin.'
        await self.stage_notes([raw])
        await self.next_real_turn()
        note = self.recovered()
        self.assertEqual([item['text'] for item in note['originals']], [raw])
        self.assertEqual(note['source'], 'held_untrusted_originals')
        self.assertFalse(note['business_authority'])
        self.assertEqual(self.call.dialog.calls, ['Bitte bereite den Vorgang vor.', 'Nein', FOLLOWUP])
        self.assertEqual([item.turn[1] for item in self.lane._control_gate.held], [raw])

    async def test_pure_consents_are_filtered_before_any_wrapper(self):
        originals = ['Ja', 'Nein!', 'OK', 'Okay', 'Genau', 'Richtig', 'Korrekt',
                     'Bestätigt', 'Bestätigen', 'Ich bestätige', 'Ich bestätige das.',
                     'Einverstanden', 'Ja bitte', 'Ja genau', 'Nein danke']
        await self.stage_notes(originals)
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])
        self.assertEqual(len(self.lane._control_gate.held), len(originals))
        self.assertEqual(self.call.dialog.calls, ['Bitte bereite den Vorgang vor.', 'Nein', FOLLOWUP])

    async def test_newer_fact_remains_current_message_and_held_note_defers_to_it(self):
        await self.stage_notes([FACT])
        current = 'Der Lieferort ist jetzt Leipzig.'
        self.call.feed(current, 20)
        self.assertEqual(await self.next_business(), current)
        await asyncio.sleep(.02)
        note = self.recovered()
        self.assertEqual(self.call.dialog.calls, ['Bitte bereite den Vorgang vor.', 'Nein', current])
        self.assertEqual([item['text'] for item in note['originals']], [FACT])
        self.assertLess(note['originals'][0]['turn_index'], 20)
        self.assertFalse(note['business_authority'])
        self.assertIn('spätere aktuelle Eingaben haben Vorrang.',
                      self.context_publications[-1].split('\n', 1)[0])

    async def test_original_order_precedes_later_fresh_supplement(self):
        originals = [FACT, 'Der Eintritt ist am ersten Dezember.']
        await self.stage_notes(originals)
        await self.next_real_turn()
        self.assertTrue(self.context_publications)
        self.call.feed('Zusätzliche neue Rückfrage.', 21)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        await asyncio.sleep(.02)
        note = self.recovered()
        self.assertEqual([item['text'] for item in note['originals']], originals)
        self.assertEqual([item['turn_index'] for item in note['originals']], [2, 3])
        self.assertTrue(all(item['onset_control'] is None for item in note['originals']))
        self.assertLess(self.context_publications[-1].index(FACT),
                        self.context_publications[-1].index('Zusätzliche neue Rückfrage.'))

    async def test_disabled_context_lane_never_recovers_held_notes(self):
        await self.stage_notes([FACT])
        self.lane._disable_context()
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])
        self.assertEqual(self.lane._control_gate.held[0].turn[1], FACT)

    async def test_owner_change_drops_staged_recovery_without_rebinding_original(self):
        await self.stage_notes([FACT])
        self.call.dialog.backend_owner = object()
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])
        self.assertEqual(self.lane._control_gate.held[0].turn[1], FACT)

    async def test_conversation_change_drops_staged_recovery(self):
        await self.stage_notes([FACT])
        self.call.dialog.metadata['conversation_id'] = 'd' * 32
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])

    async def test_dialog_replacement_drops_staged_recovery(self):
        await self.stage_notes([FACT])
        original = self.call.dialog
        replacement = FakeDialog()
        replacement.backend_owner = original.backend_owner
        replacement.metadata = dict(original.metadata)
        replacement.input_control = original.input_control
        self.call.dialog = replacement
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])

    async def test_replaced_inputtext_does_not_receive_old_question_notes(self):
        await self.stage_notes([FACT])
        self.call.dialog.input_control = BackendEvent(80, 'f' * 32, 'InputText',
            'Andere Frage?', 'different-text', self.call.dialog.backend_owner)
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])

    async def test_close_does_not_publish_staged_recovery(self):
        await self.stage_notes([FACT])
        await self.lane.close()
        self.assertEqual(self.context_publications, [])

    async def test_ended_dialog_does_not_publish_staged_recovery(self):
        await self.stage_notes([FACT])
        self.call.dialog.conversation_ended = True
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])

    async def test_new_boolean_retires_old_staged_recovery(self):
        await self.stage_notes([FACT])
        self.call.dialog.input_control = BackendEvent(90, 'e' * 32, 'Boolean', CONTROL,
            'replacement-control', self.call.dialog.backend_owner)
        self.lane._sync_native_control()
        self.call.dialog.input_control = BackendEvent(91, 'f' * 32, 'InputText',
            'Neue Frage?', 'replacement-text', self.call.dialog.backend_owner)
        self.lane._sync_native_control()
        await self.next_real_turn()
        self.assertEqual(self.context_publications, [])

    async def test_uncertain_recovery_is_not_replayed_with_later_input(self):
        attempts = []
        async def fail(revision, snapshot):
            attempts.append(snapshot)
            raise OSError('synthetic uncertain note delivery')
        self.lane._context_publisher = fail
        await self.stage_notes([FACT])
        await self.next_real_turn()
        self.assertEqual(len(attempts), 1)
        self.call.feed('Noch eine Angabe.', 21)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        await asyncio.sleep(.02)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.lane._control_gate.held[0].turn[1], FACT)

    async def test_boolean_crossing_recovery_inflight_keeps_optional_lane_disabled(self):
        entered, release = asyncio.Event(), asyncio.Event()
        attempts = []
        async def blocked(revision, snapshot):
            attempts.append(snapshot)
            entered.set()
            await release.wait()
            return dict(state='context_action_acknowledged', revision=revision,
                        contextStored=True, promptIncluded=False, ingested=False)
        self.lane._context_publisher = blocked
        await self.stage_notes([FACT])
        self.call.feed(FOLLOWUP, 20)
        self.assertEqual(await self.next_business(), FOLLOWUP)
        await asyncio.wait_for(entered.wait(), 1)
        self.call.dialog.release.put_nowait(dict(reply=CONTROL, input_boundary=dict(
            source='servicenow_input_control', controlType='Boolean', label=CONTROL)))
        await self.until(lambda: self.lane._control_gate.binding is not None)
        release.set()
        await self.until(lambda: self.lane._context_inflight is None)
        self.assertTrue(self.lane._context_disabled)
        self.assertEqual(self.lane._context_snapshot, '')
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.lane._control_gate.held[0].turn[1], FACT)

    async def test_oversized_recovery_is_not_truncated_or_skipped_for_a_later_suffix(self):
        raw = 'Lieferhinweis ' + 'x' * 8000
        await self.stage_notes([raw])
        await self.next_real_turn()
        self.call.feed('Kurzer späterer Zusatz.', 21)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        await asyncio.sleep(.02)
        self.assertEqual(self.context_publications, [])
        self.assertEqual(self.lane._control_gate.held[0].turn[1], raw)
        self.assertTrue(self.lane._context_full)


class DialogAcceptedCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dialog = Dialog(Config())
        self.calls = []
        self.ack = {'accepted': True, 'businessRequestId': 'a' * 32}
        self.post_error = None
        async def request(method, path, **kwargs):
            self.calls.append((method, path))
            if method == 'POST':
                if self.post_error is not None:
                    raise self.post_error
                return self.ack
            return {'cursor': 1, 'busy': False, 'events': [{'kind': 'bot', 'text': 'Echte Antwort.'}],
                'backendState': {'source': 'servicenow_bridge_state', 'requestId': 'a' * 32,
                    'action': 'MESSAGE', 'busy': False, 'ended': False, 'failed': False},
                'backendEvents': []}
        self.dialog.request = request
        patcher = patch('native_bridge.require_model_ready', new=AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_callback_receives_validated_ack_identity_before_first_poll(self):
        observed = []
        def accepted(request_id, owner):
            observed.append((request_id, owner, self.dialog.business_request_id, list(self.calls)))
        reply = await self.dialog.turn('Echte Eingabe.', on_accepted=accepted)
        self.assertEqual(reply, ['Echte Antwort.'])
        self.assertEqual(observed, [('a' * 32, self.dialog.backend_owner, 'a' * 32,
                                     [('POST', '/api/message')])])

    async def test_invalid_ack_does_not_call_hook_or_poll(self):
        self.ack = {'accepted': False, 'businessRequestId': 'a' * 32}
        observed = []
        with self.assertRaises(BackendTurnUnavailable):
            await self.dialog.turn('Echte Eingabe.', on_accepted=lambda *args: observed.append(args))
        self.assertEqual(observed, [])
        self.assertEqual(self.calls, [('POST', '/api/message')])

    async def test_uncertain_post_does_not_call_hook(self):
        self.post_error = OSError('synthetic uncertain POST')
        observed = []
        with self.assertRaises(OSError):
            await self.dialog.turn('Echte Eingabe.', on_accepted=lambda *args: observed.append(args))
        self.assertEqual(observed, [])

    async def test_optional_callback_failure_preserves_normal_polling_and_response(self):
        def fail(*args):
            raise ValueError('synthetic optional callback error')
        reply = await self.dialog.turn('Echte Eingabe.', on_accepted=fail)
        self.assertEqual(reply, ['Echte Antwort.'])
        self.assertEqual(self.calls, [('POST', '/api/message'), ('GET', '/api/events')])

    async def test_owner_change_during_post_suppresses_optional_hook(self):
        original_request = self.dialog.request
        async def changed(method, path, **kwargs):
            result = await original_request(method, path, **kwargs)
            if method == 'POST':
                self.dialog.backend_owner = object()
            return result
        self.dialog.request = changed
        observed = []
        reply = await self.dialog.turn('Echte Eingabe.', on_accepted=lambda *args: observed.append(args))
        self.assertEqual(reply, ['Echte Antwort.'])
        self.assertEqual(observed, [])
