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

    async def test_real_playback_generation_drops_stale_chunks(self):
        await self.arbiter.publish(event())
        await self.speech.entered.wait()
        self.playback.interrupt()
        self.speech.release.set()
        await asyncio.sleep(.02)
        self.assertEqual(self.playback.data, b'')

    async def test_status_interrupt_does_not_suppress_future_backend(self):
        await self.arbiter.publish(event('Old'))
        await self.speech.entered.wait()
        self.arbiter.interrupt()
        await self.arbiter.publish(event('Status', 'local_reply'))
        await self.arbiter.publish(event('Future'))
        self.speech.release.set()
        await asyncio.sleep(.03)
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
        await asyncio.sleep(.03)
        self.assertTrue(any(e['kind'] == 'error' for e in self.transcripts))

    async def test_audio_failure_reported_once_and_publish_is_bounded(self):
        self.speech.fail = True
        self.speech.release.set()
        await self.arbiter.publish(event())
        await self.arbiter.publish(event('Again'))
        await asyncio.sleep(.03)
        self.assertEqual(len([e for e in self.transcripts if e['kind'] == 'error']), 1)
        with self.assertRaises(ValueError):
            await self.arbiter.publish(event('x' * 4001))

    async def test_interrupt_cancels_held_audio_for_prompt_local_control(self):
        await self.arbiter.publish(event('Held'))
        await self.speech.entered.wait()
        self.arbiter.interrupt()
        self.speech.release.set()
        await self.arbiter.publish(event('Control', 'local_reply'))
        await asyncio.sleep(.03)
        self.assertEqual(self.playback.data, b'Control')
        self.assertEqual(self.speech.maximum, 1)


if __name__ == '__main__':
    unittest.main()
