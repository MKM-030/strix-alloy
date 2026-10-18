import asyncio
import unittest
from native_bridge import Config, NativeCall


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(.001)


class Speech:
    def __init__(self):
        self.recognized = []
        self.spoken = []
    async def transcribe(self, pcm):
        self.recognized.append(pcm)
        return 'Utterance ' + str(pcm[0])
    async def synthesize(self, text):
        self.spoken.append(text)
        yield bytes(960)


class HeldDialog:
    metadata = {}
    def __init__(self):
        self.received = []
        self.release = asyncio.Event()
        self.fail = False
        self.closed = False
    async def open(self):
        return []
    async def turn(self, text, on_reply=None):
        self.received.append(text)
        number = len(self.received)
        if number == 1:
            await self.release.wait()
        if self.fail:
            raise RuntimeError('backend did not become ready')
        if on_reply:
            await on_reply('Reply ' + str(number))
    async def close(self):
        self.closed = True


class IngestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.speech, self.dialog = Speech(), HeldDialog()
        self.call = NativeCall(Config(), self.speech, self.dialog)
        self.messages = []
        self.call.emit = lambda kind, data=None:self.messages.append({'type':kind,'data':data})
        self.worker = self.call.spawn(self.call.process_turns())

    async def asyncTearDown(self):
        self.dialog.release.set()
        await self.call.close()

    def users(self):
        return [m['data'] for m in self.messages if m['type']=='transcript' and m['data']['role']=='user']

    async def hold_first(self):
        await self.call.turns.put((0, b'\x01\x00'*1000))
        await until(lambda:len(self.dialog.received)==1)

    async def test_next_asr_and_user_transcript_do_not_wait_for_backend_ready(self):
        await self.hold_first()
        await self.call.turns.put((0, b'\x02\x00'*1000))
        await until(lambda:len(self.users())==2)
        self.assertEqual([x['content'] for x in self.users()], ['Utterance 1','Utterance 2'])
        self.assertEqual(self.dialog.received, ['Utterance 1'])
        self.assertFalse(self.worker.done())

    async def test_later_asr_does_not_relabel_previous_reply_or_restore_stale_audio(self):
        await self.hold_first()
        generation = self.call.playback.interrupt()
        await self.call.turns.put((generation, b'\x02\x00'*1000))
        await until(lambda:len(self.users())==2)
        users = self.users()
        self.dialog.release.set()
        await until(lambda:'Reply 2' in self.speech.spoken)
        replies = [m['data'] for m in self.messages if m['type']=='transcript' and m['data']['role']=='assistant']
        self.assertEqual([x['turn_num'] for x in replies], [1,2])
        self.assertEqual([x['caller_turn_id'] for x in replies], [x['caller_turn_id'] for x in users])
        self.assertNotIn('Reply 1', self.speech.spoken)
        self.assertEqual(self.dialog.received, ['Utterance 1','Utterance 2'])

    async def test_recognized_queue_is_bounded_and_rejected_turn_is_never_submitted(self):
        await self.hold_first()
        for number in (2,3,4):
            await self.call.turns.put((0, bytes([number,0])*1000))
            await until(lambda:len(self.users())==number)
        self.assertEqual(self.call.recognized_turns.qsize(),2)
        self.assertTrue(any(m['type']=='transcript' and m['data'].get('code')=='BUSY'
                            and 'nicht weitergeleitet' in m['data']['content'] for m in self.messages))
        self.assertFalse(any(m['type']=='error' for m in self.messages))
        self.dialog.release.set()
        await until(lambda:len(self.dialog.received)==3)
        self.assertEqual(self.dialog.received, ['Utterance 1','Utterance 2','Utterance 3'])

    async def test_backend_failure_reports_german_notice_and_discards_unsent_audio(self):
        await self.hold_first()
        await self.call.turns.put((0,b'\x02\x00'*1000))
        await until(lambda:len(self.users())==2)
        self.dialog.fail = True
        with self.assertLogs('native-voice',level='WARNING'):
            self.dialog.release.set()
            await asyncio.wait_for(self.worker,1)
        self.assertTrue(self.call.failed)
        self.assertEqual(self.dialog.received,['Utterance 1'])
        self.assertEqual(self.call.recognized_turns.qsize(),0)
        self.assertEqual(self.call.turns.qsize(),0)
        self.assertTrue(any('nicht fortgesetzt' in text for text in self.speech.spoken))
        self.assertTrue(any(m['type']=='transcript' and m['data'].get('code')=='TURN_FAILED' for m in self.messages))
        self.assertFalse(any(m['type']=='error' for m in self.messages))
        self.assertFalse(self.dialog.closed)

    async def test_asr_error_is_visible_without_native_disconnect_and_next_audio_is_recognized(self):
        async def fail_first(pcm):
            if pcm[0] == 1:
                raise RuntimeError('ASR unavailable')
            return 'Utterance 2'
        self.speech.transcribe = fail_first
        with self.assertLogs('native-voice',level='WARNING'):
            await self.call.turns.put((0,b'\x01\x00'*1000))
            await until(lambda:any(m['data'].get('code')=='ASR_FAILED' for m in self.messages))
        await self.call.turns.put((0,b'\x02\x00'*1000))
        await until(lambda:len(self.dialog.received)==1)
        self.assertFalse(self.call.failed)
        self.assertFalse(any(m['type']=='error' for m in self.messages))
        self.assertEqual([x['content'] for x in self.users()],['Utterance 2'])
        self.assertEqual(self.dialog.received,['Utterance 2'])

    async def test_close_cancels_pending_asr_and_emits_nothing_after_close(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def slow_asr(pcm):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        self.speech.transcribe = slow_asr
        await self.call.turns.put((0,b'\x01\x00'*1000))
        await asyncio.wait_for(started.wait(),1)
        before = list(self.messages)
        await self.call.close()
        self.assertTrue(cancelled.is_set())
        self.assertTrue(self.dialog.closed)
        self.assertEqual(self.messages,before)

    async def test_backend_failure_cancels_inflight_asr_without_late_transcript(self):
        await self.hold_first()
        started = asyncio.Event()
        cancelled = asyncio.Event()
        async def slow_asr(pcm):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        self.speech.transcribe = slow_asr
        await self.call.turns.put((0,b'\x02\x00'*1000))
        await asyncio.wait_for(started.wait(),1)
        self.dialog.fail = True
        with self.assertLogs('native-voice',level='WARNING'):
            self.dialog.release.set()
            await asyncio.wait_for(self.worker,1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual([x['content'] for x in self.users()],['Utterance 1'])
        self.assertEqual(self.dialog.received,['Utterance 1'])
        self.assertTrue(self.call.failed)
        self.assertEqual(self.call.turns.qsize(),0)
        self.assertEqual(self.call.recognized_turns.qsize(),0)


if __name__ == '__main__':
    unittest.main()
