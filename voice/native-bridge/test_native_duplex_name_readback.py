"""Offline contract for exact person-name readback at a genuine VA input."""
import asyncio
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class ObservedTurn(tuple):
    def __new__(cls, generation, text, number, onset):
        turn = super().__new__(cls, (generation, text, number, str(number), time.monotonic()))
        turn.duplex_onset = onset
        return turn


class PersonNameReadbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.number = 0
        self.running = asyncio.create_task(self.lane.run())

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate, *, drain=True):
        async with asyncio.timeout(1):
            while not predicate():
                if drain:
                    self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def ask(self, label='Wie heißt dein neuer Mitarbeiter?', **changes):
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='name-boundary', label=label, **changes)
        self.call.dialog.current_question = label
        self.lane._enqueue(label, kind='backend')
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))

    async def say(self, text, *, onset=None):
        self.number += 1
        turn = ObservedTurn(self.call.playback.generation, text, self.number,
                            self.lane.speech_onset() if onset is None else onset)
        self.call.recognized_turns.put_nowait(turn)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        return turn

    async def readback(self, raw):
        await self.say(raw)
        # The exact raw input must be read back, without guessing a spelling.
        await self.until(lambda: bool(self.call.dialog.calls) or self.lane.question_context()[1:] ==
                         ('local_clarification', True))
        self.assertEqual(self.call.dialog.calls, [], 'Unconfirmed name was submitted to ServiceNow')
        self.assertIn('„' + raw + '“', self.lane.question_context()[0])
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual(list(self.lane._pending), [])
        return self.lane.question_context()[0]

    async def test_actual_employee_prompt_holds_first_raw_name_until_exact_readback_confirmation(self):
        await self.ask()
        raw = 'Muthighefke'
        await self.readback(raw)
        self.assertEqual(tuple(self.lane._raw), (raw,))
        self.assertEqual(list(self.lane._supplements), [])
        await self.say('Ja, genau so.')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), raw)
        self.assertEqual(self.call.dialog.calls, [raw])
        await self.say('Ja, genau so.')
        self.assertEqual(self.call.dialog.calls, [raw], 'A repeated yes must not resubmit the name')

    async def test_ordinary_well_spelled_name_has_the_same_confirmation_gate(self):
        await self.ask('Bitte nennen Sie den Vor- und Nachnamen.')
        await self.readback('Mara Lühders')

    async def test_rejection_asks_spelling_without_sending_name_or_no(self):
        await self.ask()
        await self.readback('Muthighefke')
        await self.say('Nein')
        await self.until(lambda: self.lane.question_context()[0] == self.lane._correction_question()
                         and self.lane.question_context()[2])
        self.assertEqual(self.call.dialog.calls, [])
        spelling = 'M, a, r, a!'
        await self.readback(spelling)
        await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), spelling)
        self.assertEqual(self.call.dialog.calls, [spelling])

    async def test_confirmation_with_incomplete_readback_onset_cannot_submit_name(self):
        await self.ask()
        question = await self.readback('Mara Lühders')
        early = ((question, 'local_clarification', False, 'name-boundary', self.lane.task_revision), False)
        await self.say('Ja', onset=early)
        self.assertEqual(self.call.dialog.calls, [])
        await self.until(lambda: self.lane.question_context() ==
                         (question, 'local_clarification', True))
        await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Mara Lühders')

    async def test_changed_boundary_rejects_stale_confirmation_and_keeps_raw_local(self):
        await self.ask()
        await self.readback('Mara Lühders')
        old_onset = self.lane.speech_onset()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='new-boundary', label='Welche Abteilung?')
        await self.say('Ja', onset=old_onset)
        await self.until(lambda: 'Welche Abteilung?' in self.call.spoken)
        self.assertEqual(self.call.dialog.calls, [])
        self.assertIn('Mara Lühders', self.lane._raw)
        self.assertEqual(list(self.lane._supplements), [])

    async def test_changed_task_revision_rejects_stale_confirmation(self):
        await self.ask()
        await self.readback('Mara Lühders')
        old_onset = self.lane.speech_onset()
        self.lane.task_revision += 1
        await self.say('Ja', onset=old_onset)
        self.assertEqual(self.call.dialog.calls, [])
        await self.until(lambda: self.lane.question_context()[1:] ==
                         ('servicenow_input_control', True))

    async def test_replacement_is_read_back_exactly_instead_of_confirming_prior_candidate(self):
        await self.ask()
        await self.readback('Muthighefke')
        replacement = 'Mara Lühders'
        await self.readback(replacement)
        await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), replacement)
        self.assertEqual(self.call.dialog.calls, [replacement])

    async def test_device_name_control_remains_an_ordinary_business_input(self):
        await self.ask('Wie lautet der Name des Geräts?')
        await self.say('Laptop Blau')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Laptop Blau')

    async def test_genuine_polar_name_confirmation_remains_a_service_now_input(self):
        await self.ask('Ist der Name Mara Lühders korrekt?')
        self.lane._request = 1
        await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Ja')

    async def test_unverified_source_cannot_create_a_person_name_gate(self):
        self.call.dialog.input_boundary = dict(source='planner_text', controlType='InputText',
            businessRequestId='not-an-input', label='Wie heißt dein neuer Mitarbeiter?')
        await self.say('Mara Lühders')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Mara Lühders')

    async def test_mixed_rejection_keeps_replacement_raw_and_asks_spelling_without_submitting_it(self):
        await self.ask()
        await self.readback('Muthighefke')
        rejection = 'Nein, der richtige Name ist Mara Lühders.'
        await self.say(rejection)
        await self.until(lambda: self.lane.question_context()[0] == self.lane._correction_question())
        self.assertEqual(self.call.dialog.calls, [])
        self.assertIn(rejection, self.lane._raw)
        self.assertEqual(list(self.lane._supplements), [])

    async def test_subsequent_unrelated_local_question_cannot_approve_an_older_readback(self):
        from types import SimpleNamespace
        await self.ask()
        question = await self.readback('Mara Lühders')
        spoken_count = self.call.spoken.count(question)
        state = self.lane._begin_speech(SimpleNamespace(
            text='Möchten Sie den Ablauf erklärt haben?', kind='conversation', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(len(self.call.playback.data))
        self.lane._finish_speech(state, complete=True)
        await self.say('Ja')
        await self.until(lambda: bool(self.call.dialog.calls) or
                         self.call.spoken.count(question) > spoken_count)
        self.assertEqual(self.call.dialog.calls, [])
        await self.until(lambda: self.lane.question_context()[1:] == ('local_clarification', True))
        await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Mara Lühders')

    async def test_name_beginning_with_nein_is_a_replacement_name_not_a_rejection(self):
        await self.ask()
        await self.readback('Mara Lühders')
        await self.readback('Neinhold')

    async def test_spelling_a_serial_number_does_not_create_a_person_name_gate(self):
        await self.ask('Bitte buchstabieren Sie die Seriennummer.')
        await self.say('A, B, C!')
        await self.until(lambda: bool(self.call.dialog.calls) or
                         self.lane.question_context()[1] == 'local_clarification')
        self.assertEqual(self.lane.question_context()[1], '')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'A, B, C!')

    async def test_positive_answers_without_a_candidate_reask_name_without_submitting(self):
        label = 'Wie heißt dein neuer Mitarbeiter?'
        await self.ask(label)
        for positive in ('Ja', 'genau', 'richtig', 'Ja, das stimmt', 'Ich bestätige das', 'einverstanden'):
            with self.subTest(positive=positive):
                await self.say(positive)
                await self.until(lambda: bool(self.call.dialog.calls) or
                                 self.lane.question_context() == (label, 'servicenow_input_control', True))
                self.assertEqual(self.call.dialog.calls, [], 'A positive answer is not a supplied person name')
                self.assertIsNone(self.lane._name_candidate)

    async def test_negative_without_a_candidate_asks_spelling_without_submitting_no(self):
        await self.ask()
        await self.say('Nein')
        await self.until(lambda: bool(self.call.dialog.calls) or self.lane.question_context()[0] ==
                         self.lane._correction_question())
        self.assertEqual(self.call.dialog.calls, [], 'A rejection is not a supplied person name')
        self.assertIsNone(self.lane._name_candidate)


if __name__ == '__main__':
    unittest.main()
