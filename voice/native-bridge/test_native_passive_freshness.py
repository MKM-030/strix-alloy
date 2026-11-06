"""Passive caller context must not silently retire the only pending answer."""
import asyncio
from types import SimpleNamespace
import unittest

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


REPLY = 'Wir können das Anliegen gemeinsam besprechen.'


class PassiveFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_passive_accept_keeps_reply_but_correction_and_native_control_retire_it(self):
        for phase in ('bootstrap', 'pending', 'active'):
            with self.subTest(phase=phase):
                call = FakeCall()
                lane = NativeDuplex(call)
                lane._bootstrap_state = 'pending' if phase == 'bootstrap' else 'ready'
                turn = (0, 'Ich brauche einen Laptop für Mara.', 1, 'a' * 32, 0)
                await lane._accept(turn)
                if phase == 'active':
                    lane._pending.clear()
                    lane._backend = asyncio.create_task(asyncio.Event().wait())
                identity = object()
                lane.conversation = SimpleNamespace(
                    is_current=lambda value: value is identity,
                    output_epoch=lane.epoch,
                    invalidate=self.noop,
                    close=self.noop)
                epoch = lane.epoch
                _, snapshot, observation = lane._dialogue_snapshot(turn, epoch)
                pending = tuple(lane._pending)
                queued_questions = lane._local_questions.qsize()
                speaker = None
                try:
                    for number, text in ((2, 'Hallo'), (3, 'Ähm')):
                        await lane._accept((call.playback.generation, text, number,
                                            str(number) * 32, 0))
                    self.assertEqual(tuple(lane._raw), (turn[1], 'Hallo', 'Ähm'))
                    self.assertEqual(tuple(lane._pending), pending)
                    self.assertEqual(lane._local_questions.qsize(), queued_questions)
                    candidate = SimpleNamespace(text=REPLY, identity=identity)
                    self.assertEqual(lane._release_conversation_sentence(
                        candidate, turn, epoch, observation, snapshot), 'enqueued')
                    speaker = asyncio.create_task(lane._speak_loop())
                    async with asyncio.timeout(.5):
                        while not call.spoken:
                            await asyncio.sleep(.001)
                    self.assertEqual(call.spoken, [REPLY])

                    correction = (call.playback.generation, 'Nein, Lieferort ist Berlin.',
                                  4, 'd' * 32, 0)
                    await lane._accept(correction)
                    self.assertFalse(lane._observation_current(observation))
                    _, _, latest = lane._dialogue_snapshot(correction, lane.epoch)
                    call.dialog.input_boundary = dict(source='servicenow_input_control',
                        businessRequestId='e' * 32, controlType='Boolean',
                        label='Soll die Bestellung ausgelöst werden?')
                    self.assertFalse(lane._observation_current(latest))
                    self.assertEqual(call.dialog.calls, [])
                finally:
                    call.closed = True
                    if speaker is not None:
                        speaker.cancel()
                        await asyncio.gather(speaker, return_exceptions=True)
                    await lane.close()

    async def noop(self, *args):
        pass


if __name__ == '__main__':
    unittest.main()
