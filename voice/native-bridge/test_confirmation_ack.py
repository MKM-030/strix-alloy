"""Native confirmation ownership and retained playback precedence contracts."""
import asyncio
import time
import unittest

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall
from test_native_duplex_name_readback import ObservedTurn


ACK = 'Danke für die Bestätigung.'


class BoundCall(FakeCall):
    def __init__(self):
        super().__init__()
        self.bound_events = []

    def transcript(self, turn, role, text):
        super().transcript(turn, role, text)
        self.bound_events.append((turn[3], turn[2], role, text))


class ConfirmationAckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = BoundCall()
        self.model_calls = []
        async def no_model(*args):
            self.model_calls.append(args)
            raise RuntimeError('offline optional model')
        self.lane = NativeDuplex(self.call, conversation_factory=no_model)
        self.number = 0
        self.running = asyncio.create_task(self.lane.run())

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate, *, reason='expected owned event did not occur'):
        try:
            async with asyncio.timeout(1):
                while not predicate():
                    self.call.playback.read(len(self.call.playback.data))
                    await asyncio.sleep(.002)
        except TimeoutError:
            self.fail(reason)

    async def say(self, text, *, onset=None):
        self.number += 1
        turn = ObservedTurn(self.call.playback.generation, text, self.number,
                            self.lane.speech_onset() if onset is None else onset)
        self.call.recognized_turns.put_nowait(turn)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        return turn

    async def native_confirmation(self):
        label = 'Ist der Name Testperson Sprachprüfung korrekt?'
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='name-boundary', label=label)
        self.call.dialog.current_question = label
        self.lane._enqueue(label, kind='backend')
        await self.until(lambda: self.lane.question_context() ==
                         (label, 'servicenow_input_control', True))
        self.assertEqual(self.call.dialog.calls, [])
        return label

    async def test_native_yes_posts_original_once_without_manufacturing_confirmation_receipt(self):
        await self.native_confirmation()
        yes = await self.say('Ja')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Ja')
        await self.until(lambda: bool(self.model_calls))
        self.assertEqual(self.call.dialog.calls, [yes[1]])
        self.assertTrue(self.lane._backend is not None and not self.lane._backend.done())
        self.assertEqual([event for event in self.call.bound_events if event[3] == ACK], [])
        self.assertEqual(list(self.lane._public_findings), [])
        self.assertNotIn(ACK, self.call.dialog.public_replies)
        self.assertEqual(self.lane.question_context(), ('', '', False))
        await self.say('Ja')
        self.assertNotIn(ACK, self.call.spoken)
        self.assertEqual(self.call.dialog.calls, ['Ja'])

    async def test_native_rejection_is_forwarded_without_local_success_receipt(self):
        await self.native_confirmation()
        await self.say('Nein')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Nein')
        self.assertNotIn(ACK, self.call.spoken)
        self.assertEqual(self.call.dialog.calls, ['Nein'])

    async def test_incomplete_native_confirmation_has_no_success_receipt_or_post(self):
        question = await self.native_confirmation()
        early = ((question, 'servicenow_input_control', False, 'name-boundary', self.lane.task_revision), False)
        await self.say('Ja', onset=early)
        await self.until(lambda: self.lane.question_context() == (question, 'servicenow_input_control', True))
        self.assertNotIn(ACK, self.call.spoken)
        self.assertEqual(self.call.dialog.calls, [])

    async def test_stale_native_confirmation_has_no_receipt_or_post(self):
        question = await self.native_confirmation()
        onset = self.lane.speech_onset()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control', controlType='InputText',
            businessRequestId='other-boundary', label=question)
        await self.say('Ja', onset=onset)
        await self.until(lambda: self.lane.question_context() == (question, 'servicenow_input_control', True))
        self.assertNotIn(ACK, self.call.spoken)
        self.assertEqual(self.call.dialog.calls, [])


class AckOutputOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def until(self, call, predicate, *, reason='source replacement did not get playback ownership'):
        try:
            async with asyncio.timeout(1):
                while not predicate():
                    call.playback.read(len(call.playback.data))
                    await asyncio.sleep(.002)
        except TimeoutError:
            self.fail(reason)

    async def test_valid_queued_backend_precedes_optional_receipt(self):
        call, lane = BoundCall(), None
        lane = NativeDuplex(call)
        label = 'Welche Abteilung?'
        call.dialog.input_boundary = dict(source='servicenow_input_control', controlType='InputText',
            businessRequestId='next-boundary', label=label)
        yes = (0, 'Ja', 2, 'yes-2', time.monotonic())
        lane._enqueue(ACK, yes, kind='confirmation_ack')
        lane._enqueue(label, kind='backend')
        speaker = asyncio.create_task(lane._speak_loop())
        try:
            await self.until(call, lambda: lane.question_context() ==
                             (label, 'servicenow_input_control', True))
            self.assertEqual(call.spoken, [label], 'optional receipt delayed an already queued genuine source reply')
            self.assertEqual(lane.question_context()[0:2], (label, 'servicenow_input_control'))
        finally:
            call.closed = True
            speaker.cancel()
            await asyncio.gather(speaker, return_exceptions=True)
            await lane.close()

    async def test_stale_queued_backend_does_not_discard_current_receipt(self):
        call = BoundCall()
        lane = NativeDuplex(call)
        lane._enqueue('Stale source reply.', kind='backend')
        lane.epoch += 1
        lane._enqueue(ACK, (0, 'Ja', 2, 'yes-2', time.monotonic()), kind='confirmation_ack')
        speaker = asyncio.create_task(lane._speak_loop())
        try:
            await self.until(call, lambda: ACK in call.spoken)
            self.assertEqual(call.spoken, [ACK])
        finally:
            call.closed = True
            speaker.cancel()
            await asyncio.gather(speaker, return_exceptions=True)
            await lane.close()

    async def callback(self, reply, *, stale=False, replaces=False):
        call = BoundCall()
        lane = NativeDuplex(call)
        started, release = asyncio.Event(), asyncio.Event()
        prefix = b'\x01\x00' * 240
        async def synthesize(text):
            call.spoken.append(text)
            if text == ACK:
                started.set()
                yield prefix
                await release.wait()
            else:
                yield bytes(480)
        call.speech.synthesize = synthesize
        original = (0, 'Testperson Sprachprüfung', 1, 'name-1', time.monotonic())
        business = asyncio.create_task(lane._business(original))
        lane._backend = business
        speaker = None
        try:
            await asyncio.wait_for(call.dialog.started.get(), 1)
            if stale:
                lane.task_revision += 1
            lane._enqueue(ACK, (0, 'Ja', 2, 'yes-2', time.monotonic()), kind='confirmation_ack')
            speaker = asyncio.create_task(lane._speak_loop())
            await asyncio.wait_for(started.wait(), 1)
            synthesis = lane._synthesis_task
            call.dialog.release.put_nowait(reply)
            await asyncio.wait_for(business, 1)
            if replaces:
                await self.until(call, lambda: reply in call.spoken)
                self.assertTrue(synthesis.cancelled())
                self.assertEqual(call.spoken, [ACK, reply])
            else:
                await asyncio.sleep(0)
                self.assertFalse(synthesis.done(), 'callback without admitted replacement cancelled acknowledgement')
                self.assertEqual(call.spoken, [ACK])
                self.assertEqual(bytes(call.playback.data), prefix)
            self.assertEqual(call.dialog.calls, [original[1]])
        finally:
            call.closed = True
            release.set()
            for task in (business, speaker):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(task for task in (business, speaker) if task is not None), return_exceptions=True)
            await lane.close()

    async def test_admitted_real_backend_reply_preempts_current_receipt(self):
        await self.callback('Der nächste Schritt kann besprochen werden.', replaces=True)

    async def test_suppressed_generic_callback_keeps_current_receipt(self):
        await self.callback('Bitte warten Sie einen Moment.')

    async def test_empty_callback_keeps_current_receipt(self):
        await self.callback('')

    async def test_stale_callback_keeps_current_receipt(self):
        await self.callback('Veraltete Rückmeldung.', stale=True)

    async def test_caller_interrupt_revokes_receipt_without_cancelling_submitted_name(self):
        call = BoundCall()
        lane = NativeDuplex(call)
        original = (0, 'Testperson Sprachprüfung', 1, 'name-1', time.monotonic())
        business = asyncio.create_task(lane._business(original))
        lane._backend = business
        try:
            await asyncio.wait_for(call.dialog.started.get(), 1)
            lane._enqueue(ACK, (0, 'Ja', 2, 'yes-2', time.monotonic()), kind='confirmation_ack')
            lane.interrupt()
            self.assertEqual(list(lane._outputs), [])
            self.assertFalse(business.done())
            self.assertFalse(business.cancelled())
            self.assertEqual(call.dialog.calls, [original[1]])
        finally:
            call.closed = True
            business.cancel()
            await asyncio.gather(business, return_exceptions=True)
            await lane.close()

    async def buffered_callback(self, reply, *, stale=False, newer=None, partial=False, replaces=False):
        call = BoundCall()
        lane = NativeDuplex(call)
        ack_pcm, backend_pcm, unrelated = (b'\x01\x00' * 240, b'\x02\x00' * 240,
                                          b'\x03\x00' * 240)
        async def synthesize(text):
            call.spoken.append(text)
            yield ack_pcm if text == ACK else backend_pcm
        call.speech.synthesize = synthesize
        original = (0, 'Testperson Sprachprüfung', 1, 'name-1', time.monotonic())
        business = asyncio.create_task(lane._business(original))
        lane._backend = business
        speaker = None
        try:
            await asyncio.wait_for(call.dialog.started.get(), 1)
            if stale:
                lane.task_revision += 1
            lane._enqueue(ACK, (0, 'Ja', 2, 'yes-2', time.monotonic()), kind='confirmation_ack')
            speaker = asyncio.create_task(lane._speak_loop())
            # Deliberately do not drain PCM: synthesis is complete, playback is not.
            async with asyncio.timeout(1):
                while not (call.spoken and not call.synthesis_active and lane._active_kind is None):
                    await asyncio.sleep(.002)
            self.assertEqual(bytes(call.playback.data), ack_pcm)
            self.assertTrue(lane._speech['complete'])
            if partial:
                call.playback.read(len(ack_pcm) // 2)
            if newer == 'generation':
                call.playback.interrupt()
                call.playback.put(unrelated, call.playback.generation)
            elif newer == 'epoch':
                lane.interrupt()
                call.playback.put(unrelated, call.playback.generation)
            elif newer == 'mixed_same_generation':
                call.playback.put(unrelated, call.playback.generation)
            elif newer == 'epoch_only':
                lane.epoch += 1
            before = bytes(call.playback.data)
            generation = call.playback.generation
            call.dialog.release.put_nowait(reply)
            await asyncio.wait_for(business, 1)
            if replaces:
                try:
                    async with asyncio.timeout(1):
                        while reply not in call.spoken:
                            await asyncio.sleep(.002)
                except TimeoutError:
                    self.fail('admitted backend stayed blocked on completed acknowledgement PCM')
                self.assertGreater(call.playback.generation, generation)
                self.assertEqual(bytes(call.playback.data), backend_pcm)
                self.assertEqual(call.spoken, [ACK, reply])
            else:
                await asyncio.sleep(0)
                self.assertEqual(bytes(call.playback.data), before,
                                 'callback erased stale or unrelated buffered audio')
                self.assertEqual(call.playback.generation, generation)
                self.assertEqual(call.spoken, [ACK])
            self.assertEqual(call.dialog.calls, [original[1]])
        finally:
            call.closed = True
            for task in (business, speaker):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(task for task in (business, speaker) if task is not None),
                                 return_exceptions=True)
            await lane.close()

    async def test_admitted_backend_retires_owned_ack_pcm_after_synthesis_finished(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', replaces=True)

    async def test_admitted_backend_retires_only_remaining_owned_ack_pcm_after_partial_drain(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', partial=True, replaces=True)

    async def test_empty_callback_preserves_completed_ack_pcm(self):
        await self.buffered_callback('')

    async def test_suppressed_generic_callback_preserves_completed_ack_pcm(self):
        await self.buffered_callback('Bitte warten Sie einen Moment.')

    async def test_stale_callback_preserves_current_completed_ack_pcm(self):
        await self.buffered_callback('Veraltete Rückmeldung.', stale=True)

    async def test_backend_cannot_erase_newer_generation_audio_using_old_ack_state(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', newer='generation')

    async def test_backend_cannot_erase_newer_epoch_audio_using_old_ack_state(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', newer='epoch')

    async def test_backend_cannot_use_stale_ack_output_epoch_to_interrupt_playback(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', newer='epoch_only')

    async def test_backend_cannot_erase_mixed_unrelated_audio_in_ack_generation(self):
        await self.buffered_callback('Eine echte neue Rückmeldung.', newer='mixed_same_generation')


if __name__ == '__main__':
    unittest.main()
