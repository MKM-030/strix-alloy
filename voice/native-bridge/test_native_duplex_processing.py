"""Model-free checks for short, source-bound automatic processing speech."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


PREFIX = 'ServiceNow meldet: '


class AutomaticProcessingTests(unittest.TestCase):
    def lane(self, label):
        call = FakeCall()
        lane = NativeDuplex(call, clock=lambda: 110)
        lane.updates.start(100)
        call.dialog.processing_observed_at = 109
        call.dialog.processing = {'revision': 3, 'messages': [label],
            'source': 'servicenow_processing', 'agentCompletionKnown': False}
        return lane

    def test_fresh_specific_label_without_punctuation_is_a_complete_spoken_sentence(self):
        label = 'Verfügbarkeit wird geprüft'
        lane = self.lane(label)
        self.assertEqual(lane._automatic_update(), (PREFIX + label + '.', 139))
        self.assertEqual(lane.call.dialog.processing['messages'], [label])
        self.assertEqual(lane.call.dialog.calls, [])
        lane.call.dialog.processing['messages'] = [label + '.']
        self.assertEqual(lane._automatic_update(), (None, None))

    def test_existing_terminal_punctuation_is_preserved(self):
        for punctuation in '.!?':
            with self.subTest(punctuation=punctuation):
                label = 'Verfügbarkeit wird geprüft' + punctuation
                self.assertEqual(self.lane(label)._automatic_update(), (PREFIX + label, 139))

    def test_generic_processing_stays_silent_with_or_without_punctuation(self):
        for label in ('Anfrage wird geprüft', 'Ich verarbeite Ihre Angaben',
                      'Einen Moment bitte', 'Ich warte noch auf die Rückmeldung'):
            for punctuation in ('', '.'):
                with self.subTest(label=label, punctuation=punctuation):
                    self.assertEqual(self.lane(label + punctuation)._automatic_update(),
                                     (None, None))

    def test_spoken_length_includes_added_punctuation_and_never_truncates(self):
        label = 'Verfügbarkeit ' + 'x' * (119 - len(PREFIX) - len('Verfügbarkeit '))
        expected = PREFIX + label + '.'
        self.assertEqual(len(expected), 120)
        self.assertEqual(self.lane(label)._automatic_update(), (expected, 139))
        self.assertEqual(self.lane(label + 'x')._automatic_update(), (None, None))

    def test_multiple_sentences_and_lines_are_not_truncated_to_an_update(self):
        for label in ('Lager geprüft. Lieferung wird geprüft',
                      'Lager geprüft. Lieferung wird geprüft.',
                      'Lager geprüft\nLieferung wird geprüft'):
            with self.subTest(label=label):
                self.assertEqual(self.lane(label)._automatic_update(), (None, None))

    def test_freshness_source_completion_and_pending_guards_still_hold(self):
        for observed_at in (80, 99, 111):
            with self.subTest(observed_at=observed_at):
                lane = self.lane('Verfügbarkeit wird geprüft')
                lane.call.dialog.processing_observed_at = observed_at
                self.assertEqual(lane._automatic_update(), (None, None))
        for field, value in (('source', 'internal_thoughts'), ('agentCompletionKnown', True)):
            with self.subTest(field=field):
                lane = self.lane('Verfügbarkeit wird geprüft')
                lane.call.dialog.processing[field] = value
                self.assertEqual(lane._automatic_update(), (None, None))
        lane = self.lane('Verfügbarkeit wird geprüft')
        lane._pending.append((0, 'Neue Angabe', 2, 'input-2', 110))
        self.assertEqual(lane._automatic_update(), (None, None))


class AutomaticProcessingSpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_speaks_once_with_current_bindings_without_another_business_post(self):
        call = FakeCall()
        now = 110
        lane = NativeDuplex(call, clock=lambda: now)
        turn = (0, 'Bitte die Verfügbarkeit prüfen.', 1, 'business-1', 110)
        business = asyncio.create_task(lane._business(turn))
        lane._backend = business
        tasks = [business]
        try:
            self.assertEqual(await asyncio.wait_for(call.dialog.started.get(), 1), turn[1])
            lane.updates.start(100)
            call.dialog.processing_observed_at = 109
            call.dialog.observation_revision = 3
            call.dialog.processing = {'revision': 3, 'messages': ['Verfügbarkeit wird geprüft'],
                'source': 'servicenow_processing', 'agentCompletionKnown': False}
            tasks.append(asyncio.create_task(lane._update_loop()))
            await asyncio.wait_for(lane._output_ready.wait(), 1)
            item = lane._outputs[0]
            self.assertEqual((item.kind, item.request, item.observation_revision, item.expires_at),
                             ('processing', 1, 3, 139))
            self.assertTrue(lane._valid(item))
            for attribute in ('_request', 'task_revision', 'epoch'):
                previous = getattr(lane, attribute)
                setattr(lane, attribute, previous + 1)
                self.assertFalse(lane._valid(item), attribute)
                setattr(lane, attribute, previous)
            call.dialog.observation_revision = 4
            self.assertFalse(lane._valid(item))
            call.dialog.observation_revision = 3
            now = 139
            self.assertFalse(lane._valid(item))
            now = 110
            tasks.append(asyncio.create_task(lane._speak_loop()))
            async with asyncio.timeout(1):
                while not call.spoken:
                    await asyncio.sleep(.005)
            self.assertEqual(call.spoken, [PREFIX + 'Verfügbarkeit wird geprüft.'])
            self.assertEqual(call.dialog.calls, [turn[1]])
            self.assertFalse(business.done())
            self.assertEqual(lane._automatic_update(), (None, None))
        finally:
            call.closed = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await lane.close()


if __name__ == '__main__':
    unittest.main()
