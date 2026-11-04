"""Native name validation and confirmation own the caller's unchanged text."""
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


class NativeNameOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        async def unavailable(*args):
            raise RuntimeError('offline optional model')
        self.lane = NativeDuplex(self.call, conversation_factory=unavailable)
        self.number = 0
        self.running = asyncio.create_task(self.lane.run())

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def ask(self, label='Wie heißt dein neuer Mitarbeiter?', *, request='name-boundary'):
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId=request, label=label)
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

    async def next_business(self):
        return await asyncio.wait_for(self.call.dialog.started.get(), 1)

    async def test_native_employee_prompt_receives_first_raw_name_without_local_readback(self):
        await self.ask()
        await self.say('Muthighefke')
        self.assertEqual(await self.next_business(), 'Muthighefke')
        self.assertEqual(self.call.dialog.calls, ['Muthighefke'])
        self.assertFalse(any('Ich habe „' in text for text in self.call.spoken))

    async def test_well_spelled_name_is_delivered_directly(self):
        await self.ask('Bitte nennen Sie den Vor- und Nachnamen.')
        await self.say('Mara Lühders')
        self.assertEqual(await self.next_business(), 'Mara Lühders')

    async def test_correction_waits_fifo_then_reaches_native_verbatim_once(self):
        await self.ask()
        first, correction = 'Muthighefke', 'Nein, der richtige Name ist Mara Lühders.'
        await self.say(first)
        self.assertEqual(await self.next_business(), first)
        await self.say(correction)
        self.assertEqual(self.call.dialog.calls, [first])
        self.assertEqual([turn[1] for turn in self.lane._pending], [correction])
        self.call.dialog.release.put_nowait('Bitte nennen Sie den Namen erneut.')
        self.assertEqual(await self.next_business(), correction)
        self.assertEqual(self.call.dialog.calls, [first, correction])
        self.assertFalse(any('buchstabieren' in text for text in self.call.spoken))

    async def test_spelling_remains_exact_native_input(self):
        await self.ask()
        raw = 'M, a, r, a!'
        await self.say(raw)
        self.assertEqual(await self.next_business(), raw)

    async def test_device_name_is_ordinary_raw_input(self):
        await self.ask('Wie lautet der Name des Geräts?')
        await self.say('Laptop Blau')
        self.assertEqual(await self.next_business(), 'Laptop Blau')

    async def test_complete_native_name_confirmation_receives_yes_once(self):
        await self.ask('Ist der Name Mara Lühders korrekt?')
        await self.say('Ja')
        self.assertEqual(await self.next_business(), 'Ja')
        self.assertEqual(self.call.dialog.calls, ['Ja'])

    async def test_name_confirmation_does_not_approve_later_native_order(self):
        await self.ask('Ist der Name Mara Lühders korrekt?')
        await self.say('Ja')
        self.assertEqual(await self.next_business(), 'Ja')
        label = 'Soll ich diese Bestellung ausführen?'
        self.call.dialog.release.put_nowait(dict(reply=label, input_boundary=dict(
            source='servicenow_input_control', controlType='InputText',
            businessRequestId='order-boundary', label=label)))
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))
        self.assertEqual(self.call.dialog.calls, ['Ja'])
        self.assertEqual(list(self.lane._pending), [])

    async def test_incomplete_native_confirmation_onset_reasks_without_submission(self):
        label = 'Ist der Name Mara Lühders korrekt?'
        await self.ask(label)
        early = ((label, 'servicenow_input_control', False,
                  'name-boundary', self.lane.task_revision), False)
        await self.say('Ja', onset=early)
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))
        self.assertEqual(self.call.dialog.calls, [])
        await self.say('Ja')
        self.assertEqual(await self.next_business(), 'Ja')

    async def test_changed_native_request_rejects_stale_confirmation(self):
        label = 'Soll ich diese Bestellung ausführen?'
        await self.ask(label, request='old-order')
        old_onset = self.lane.speech_onset()
        self.call.dialog.input_boundary['businessRequestId'] = 'new-order'
        await self.say('Ja', onset=old_onset)
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))
        self.assertEqual(self.call.dialog.calls, [])

    async def test_changed_revision_rejects_stale_native_confirmation(self):
        label = 'Soll ich diese Bestellung ausführen?'
        await self.ask(label)
        old_onset = self.lane.speech_onset()
        self.lane.task_revision += 1
        await self.say('Ja', onset=old_onset)
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))
        self.assertEqual(self.call.dialog.calls, [])

    async def test_unverified_planner_text_cannot_create_local_name_workflow(self):
        self.call.dialog.input_boundary = dict(source='planner_text', controlType='InputText',
            businessRequestId='not-an-input', label='Wie heißt dein neuer Mitarbeiter?')
        await self.say('Mara Lühders')
        self.assertEqual(await self.next_business(), 'Mara Lühders')
        self.assertFalse(any('Ich habe „' in text for text in self.call.spoken))

    async def test_name_beginning_with_nein_remains_raw_text(self):
        await self.ask()
        await self.say('Neinhold')
        self.assertEqual(await self.next_business(), 'Neinhold')

    async def test_serial_spelling_does_not_create_person_name_gate(self):
        await self.ask('Bitte buchstabieren Sie die Seriennummer.')
        await self.say('A, B, C!')
        self.assertEqual(await self.next_business(), 'A, B, C!')

    async def test_positive_at_open_name_question_is_for_native_validation(self):
        await self.ask()
        await self.say('Ja')
        self.assertEqual(await self.next_business(), 'Ja')
        self.assertFalse(any('Bestätigung' in text for text in self.call.spoken))

    async def test_negative_at_open_name_question_is_for_native_validation(self):
        await self.ask()
        await self.say('Nein')
        self.assertEqual(await self.next_business(), 'Nein')
        self.assertFalse(any('buchstabieren' in text for text in self.call.spoken))


if __name__ == '__main__':
    unittest.main()
