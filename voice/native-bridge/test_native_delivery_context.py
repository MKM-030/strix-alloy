"""Actual input handoff evidence must not become invented business progress."""
import asyncio
import unittest
from types import SimpleNamespace

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall
from test_native_duplex_claim_release import SentenceModel


class DeliveryContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.running = None

    async def asyncTearDown(self):
        self.call.closed = True
        if self.running is not None and not self.running.done():
            self.running.cancel()
            await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def accept(self, text, number=1):
        turn = (self.call.playback.generation, text, number, f'{number:032x}', float(number))
        await self.lane._accept(turn)
        return turn

    def rules(self, turn):
        return '\n'.join(self.lane._dialogue_snapshot(turn, self.lane.epoch)[1]['capability_limits'])

    async def test_queued_input_is_not_a_transmitted_request_even_when_lane_is_busy(self):
        turn = await self.accept('Für Lea Oltmer.')
        rules = self.rules(turn)
        self.assertIn('Noch lokal:', rules)
        self.assertNotIn('Eine übermittelte Eingabe wartet auf Antwort', rules)
        self.assertNotIn('Die Anfrage wartet noch auf vollständige Rückmeldung.', rules)
        self.assertIn('Erwähne Übermittlung, Verarbeitung oder fehlende Bestätigung nur', rules)

    async def test_handoff_ack_does_not_claim_processing_or_invalidate_fast_reply(self):
        before_ack, allow_ack = asyncio.Event(), asyncio.Event()
        original = self.call.dialog.turn
        async def delayed_ack(text, **kwargs):
            before_ack.set()
            await allow_ack.wait()
            return await original(text, **kwargs)
        self.call.dialog.turn = delayed_ack
        turn = await self.accept('Für Lea Oltmer.')
        self.running = self.lane._backend = asyncio.create_task(
            self.lane._business(self.lane._pending.popleft()))
        await before_ack.wait()
        _, snapshot, observation = self.lane._dialogue_snapshot(turn, self.lane.epoch)
        rules = '\n'.join(snapshot['capability_limits'])
        self.assertIn('Übergabe angestoßen:', rules)
        self.assertNotIn('Während ServiceNow die Eingabe bearbeitet', rules)
        allow_ack.set()
        await self.call.dialog.started.get()
        self.assertEqual(rules, self.rules(turn))
        self.assertTrue(self.lane._observation_current(observation))
        correction = await self.accept('Korrektur: Eintritt ist 01.01.2027.', 2)
        self.assertIn('Noch lokal:', self.rules(correction))
        self.assertNotIn('Übergabe angestoßen:', self.rules(correction))
        self.call.dialog.release.put_nowait('Welches Datum gilt?')
        await self.running
        self.assertIn('Noch lokal:', self.rules(correction), 'Older reply is not a reply to this correction')

    async def test_owned_reply_and_failed_attempt_have_distinct_truthful_states(self):
        turn = await self.accept('Für Lea Oltmer.')
        self.call.dialog.release.put_nowait('Wie lautet das Eintrittsdatum?')
        await self.lane._business(self.lane._pending.popleft())
        self.assertIn('Native Rückmeldung:', self.rules(turn))
        self.call.dialog.backend_owner = object()
        self.assertNotIn('Native Rückmeldung:', self.rules(turn))
        correction = await self.accept('Das Datum ist 01.01.2027.', 2)
        async def uncertain(text, **kwargs):
            raise RuntimeError('uncertain transport result')
        self.call.dialog.turn = uncertain
        with self.assertRaisesRegex(RuntimeError, 'uncertain transport result'):
            await self.lane._business(self.lane._pending.popleft())
        self.assertIn('Übergabe ungewiss:', self.rules(correction))
        self.assertFalse(self.lane._pending)

    async def test_bootstrap_causal_prerequisite_is_skipped_but_real_conversation_survives(self):
        self.lane._bootstrap_state = 'pending'
        turn = await self.accept('Was dauert da so lange?')
        model = SentenceModel([])
        self.lane.conversation = model
        _, snapshot, observation = self.lane._dialogue_snapshot(turn, self.lane.epoch)
        actual = ('Ich habe Ihre Angaben für Lea Oldma und Mariaz noch nicht an das System übergeben, '
                  'da ich noch das Eintrittsdatum, die zuständige Führungskraft und den Lieferort benötige.')
        def release(text):
            return self.lane._release_conversation_sentence(
                SimpleNamespace(text=text, identity=model.identity), turn, self.lane.epoch,
                observation, snapshot, skip_unsupported_claim=True)
        self.assertEqual(release(actual), 'skipped_claim')
        self.assertEqual(release('Ich habe Ihre Angaben noch nicht übermittelt, weil ich noch eine Kennung brauche.'),
                         'skipped_claim')
        self.assertEqual(release('Die Verbindung wird noch vorbereitet. Wir können Ihr Anliegen schon besprechen.'),
                         'enqueued')
        self.assertEqual(release('Sie sagten: «' + actual + '»'), 'enqueued')
        self.assertEqual(release('Wenn noch eine Angabe benötigt wird, fragt ServiceNow danach.'), 'enqueued')


if __name__ == '__main__':
    unittest.main()
