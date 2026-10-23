import asyncio
import unittest

from core import PlaybackBuffer
from conversation_output import OutputArbiter


def event(text='Answer', kind='backend_reply', version=1):
    return dict(kind=kind, task_id='task', operation_id='operation', utterance_id='u',
                context_version=version, text=text, priority=0 if kind == 'local_reply' else 10)


class Speech:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.active = 0
        self.maximum = 0
        self.fail = False

    async def synthesize(self, text):
        self.active += 1
        self.maximum = max(self.active, self.maximum)
        self.entered.set()
        try:
            await self.release.wait()
            if self.fail:
                raise RuntimeError('synthetic audio failure')
            yield text.encode()
        finally:
            self.active -= 1


class OutputTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.speech = Speech()
        self.playback = PlaybackBuffer()
        self.transcripts = []
        async def transcript(payload):
            self.transcripts.append(payload)
        self.arbiter = OutputArbiter(self.speech, self.playback, transcript, lambda: True)

    async def asyncTearDown(self):
        await self.arbiter.close()

    async def test_guard_is_rechecked_after_async_transcript_before_synthesis(self):
        entered, release = asyncio.Event(), asyncio.Event()
        valid = True
        async def held_transcript(payload):
            entered.set()
            await release.wait()
        self.arbiter.emit_transcript = held_transcript
        await self.arbiter.publish_guarded(event(), lambda: valid)
        await entered.wait()
        valid = False
        release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertFalse(self.speech.entered.is_set())
        self.assertEqual(self.playback.data, b'')

    async def test_guard_changes_during_synthesis_suppress_chunks(self):
        valid = True
        await self.arbiter.publish_guarded(event(), lambda: valid)
        await self.speech.entered.wait()
        valid = False
        self.speech.release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'')
        self.assertEqual(self.arbiter.sent_bytes, 0)

    async def test_queued_guard_exception_fails_closed_without_error_prose(self):
        fail = False
        def valid():
            if fail: raise RuntimeError('private validity detail')
            return True
        await self.arbiter.publish_guarded(event(), valid)
        fail = True
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertFalse(self.speech.entered.is_set())
        self.assertEqual(self.transcripts, [])

    async def test_real_playback_generation_drops_stale_chunks(self):
        await self.arbiter.publish(event())
        await self.speech.entered.wait()
        self.playback.interrupt()
        self.speech.release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'')

    async def test_status_interrupt_does_not_suppress_future_backend(self):
        await self.arbiter.publish(event('Old'))
        await self.speech.entered.wait()
        self.arbiter.interrupt()
        await self.arbiter.publish(event('Status', 'local_reply'))
        await self.arbiter.publish(event('Future'))
        self.speech.release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'StatusFuture')
        self.assertEqual(self.speech.maximum, 1)
        self.assertFalse(any('heard' in e for e in self.transcripts))

    async def test_output_queue_bounded_and_overflow_reported(self):
        await self.arbiter.publish(event('Held'))
        await self.speech.entered.wait()
        for i in range(20):
            await self.arbiter.publish(event(str(i)))
        self.assertLessEqual(self.arbiter.pending_count, 8)
        self.assertGreater(self.arbiter.suppressed_count, 0)
        self.speech.release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertTrue(any(e['kind'] == 'error' for e in self.transcripts))

    async def test_audio_failure_reported_once_and_publish_is_bounded(self):
        self.speech.fail = True
        self.speech.release.set()
        await self.arbiter.publish(event())
        await self.arbiter.publish(event('Again'))
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(len([e for e in self.transcripts if e['kind'] == 'error']), 1)
        with self.assertRaises(ValueError):
            await self.arbiter.publish(event('x' * 4001))

    async def test_interrupt_cancels_held_audio_for_prompt_local_control(self):
        await self.arbiter.publish(event('Held'))
        await self.speech.entered.wait()
        self.arbiter.interrupt()
        self.speech.release.set()
        await self.arbiter.publish(event('Control', 'local_reply'))
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'Control')
        self.assertEqual(self.speech.maximum, 1)

    async def test_wait_idle_covers_queued_active_interrupted_and_closed(self):
        await self.arbiter.wait_idle()
        await self.arbiter.publish(event('Held'))
        waiter = asyncio.create_task(self.arbiter.wait_idle())
        await self.speech.entered.wait()
        self.assertFalse(waiter.done())
        self.arbiter.interrupt()
        await asyncio.wait_for(waiter, 1)
        self.assertEqual(self.speech.active, 0)
        await self.arbiter.publish(event('Held again'))
        waiter = asyncio.create_task(self.arbiter.wait_idle())
        await self.arbiter.close()
        await asyncio.wait_for(waiter, 1)
        self.assertEqual(self.speech.active, 0)

    async def test_wait_idle_completes_after_audio_error_and_suppressed_queue(self):
        self.speech.fail = True
        self.speech.release.set()
        await self.arbiter.publish(event())
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.speech.active, 0)
        await self.arbiter.publish(event('Suppressed'))
        self.arbiter.interrupt()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)

    async def test_deferred_pauses_then_survives_input_interrupt_and_speaks_once(self):
        ready = False
        self.arbiter.input_ready = lambda: ready
        await self.arbiter.publish_deferred(event(), lambda: True)
        self.arbiter.interrupt_for_input()
        await asyncio.sleep(0)
        self.assertEqual(self.arbiter.pending_count, 1)
        self.assertEqual(self.transcripts, [])
        self.assertFalse(self.arbiter._idle.is_set())
        ready = True
        self.speech.release.set()
        self.arbiter.notify_input_changed()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual([e['text'] for e in self.transcripts], ['Answer'])
        self.assertEqual(self.playback.data, b'Answer')

    async def test_reserved_unstarted_deferred_survives_input_interrupt(self):
        reserved, release = asyncio.Event(), asyncio.Event()
        speak = self.arbiter._speak
        async def delayed(entry):
            reserved.set()
            await release.wait()
            await speak(entry)
        self.arbiter._speak = delayed
        await self.arbiter.publish_deferred(event(), lambda: True)
        await reserved.wait()
        self.arbiter.interrupt_for_input()
        self.assertEqual(self.arbiter.pending_count, 1)
        release.set()
        self.speech.release.set()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual([e['text'] for e in self.transcripts], ['Answer'])

    async def test_readiness_changed_in_reservation_pauses_without_discard(self):
        reserved, release = asyncio.Event(), asyncio.Event()
        ready = True
        self.arbiter.input_ready = lambda: ready
        speak = self.arbiter._speak
        async def delayed(entry):
            reserved.set()
            await release.wait()
            await speak(entry)
        self.arbiter._speak = delayed
        await self.arbiter.publish(event())
        await reserved.wait()
        ready = False
        release.set()
        for _ in range(4): await asyncio.sleep(0)
        self.assertEqual(self.arbiter.pending_count, 1)
        self.assertEqual(self.transcripts, [])
        ready = True
        self.speech.release.set()
        self.arbiter.notify_input_changed()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'Answer')

    async def test_started_deferred_interrupted_in_async_transcript_never_replays(self):
        entered = asyncio.Event()
        async def transcript(payload):
            self.transcripts.append(payload)
            entered.set()
            await asyncio.Event().wait()
        self.arbiter.emit_transcript = transcript
        await self.arbiter.publish_deferred(event(), lambda: True)
        await entered.wait()
        self.arbiter.interrupt_for_input()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.arbiter.notify_input_changed()
        await asyncio.sleep(0)
        self.assertEqual(len(self.transcripts), 1)
        self.assertFalse(self.speech.entered.is_set())
        self.assertEqual(self.playback.data, b'')

    async def test_control_bypasses_paused_backend_and_completes_own_waiter(self):
        self.arbiter.input_ready = lambda: False
        self.arbiter.control_ready = lambda: True
        self.speech.release.set()
        await self.arbiter.publish_deferred(event('Backend'), lambda: True)
        await asyncio.wait_for(self.arbiter.publish_control(event('Control'), wait=True), 1)
        self.assertEqual(self.playback.data, b'Control')
        self.assertEqual(self.arbiter.pending_count, 1)
        self.assertFalse(self.arbiter._idle.is_set())

    async def test_control_waiter_cancel_does_not_cancel_delivery(self):
        ready = False
        self.arbiter.control_ready = lambda: ready
        waiter = asyncio.create_task(self.arbiter.publish_control(event('Control'), wait=True))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        self.assertEqual(self.arbiter.pending_count, 1)
        ready = True
        self.speech.release.set()
        self.arbiter.notify_input_changed()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.playback.data, b'Control')

    async def test_control_waiters_finish_on_rejection_eviction_stop_and_close(self):
        self.arbiter.control_ready = lambda: False
        await self.arbiter.publish_control(event(), lambda: False, wait=True)
        waiters = [asyncio.create_task(self.arbiter.publish_control(event(str(i)), wait=True)) for i in range(9)]
        await asyncio.sleep(0)
        self.assertEqual(self.arbiter.pending_count, 8)
        # A higher priority entry evicts the earliest low priority control.
        await self.arbiter.publish(event('Priority', 'local_reply'))
        await asyncio.sleep(0)
        await asyncio.wait_for(waiters[0], 1)
        self.assertTrue(waiters[-1].done())
        self.arbiter.interrupt()
        await asyncio.wait_for(asyncio.gather(*waiters), 1)
        waiter = asyncio.create_task(self.arbiter.publish_control(event(), wait=True))
        await asyncio.sleep(0)
        await self.arbiter.close()
        await asyncio.wait_for(waiter, 1)

    async def test_invalid_deferred_pruned_even_while_input_paused(self):
        ready, valid = False, True
        self.arbiter.input_ready = lambda: ready
        await self.arbiter.publish_deferred(event(), lambda: valid)
        valid = False
        self.arbiter.notify_input_changed()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.transcripts, [])

    async def test_kind_does_not_make_transient_backend_durable(self):
        self.arbiter.input_ready = lambda: False
        await self.arbiter.publish(event())
        self.arbiter.interrupt_for_input()
        await asyncio.wait_for(self.arbiter.wait_idle(), 1)
        self.assertEqual(self.arbiter.pending_count, 0)
        self.assertEqual(self.transcripts, [])


if __name__ == '__main__':
    unittest.main()
