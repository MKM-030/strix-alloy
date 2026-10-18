import asyncio
import unittest
from array import array
from fractions import Fraction

from av import AudioFrame
from native_bridge import Config, NativeCall


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(.001)


class Microphone:
    def __init__(self):
        self.frames = asyncio.Queue()
        self.samples = 0

    def feed(self, frames, voiced):
        for _ in range(frames):
            frame = AudioFrame(format='s16', layout='mono', samples=320)
            frame.planes[0].update(array('h', [3000 if voiced else 0]*320).tobytes())
            frame.sample_rate = 16000
            frame.pts = self.samples
            frame.time_base = Fraction(1, 16000)
            self.samples += 320
            self.frames.put_nowait(frame)

    async def recv(self):
        return await self.frames.get()


class Speech:
    def __init__(self):
        self.spoken = []
        self.transcriptions = 0
        self.empty_second = False
        self.hold_first = False
        self.first_pcm = asyncio.Event()
        self.release_audio = asyncio.Event()

    async def transcribe(self, pcm):
        self.transcriptions += 1
        if self.empty_second and self.transcriptions == 2:
            return ''
        return 'Utterance ' + str(self.transcriptions)

    async def synthesize(self, text):
        self.spoken.append(text)
        yield b'\x01\x00'*480
        if self.hold_first and text == 'Reply 1':
            self.first_pcm.set()
            await self.release_audio.wait()
            yield b'\x09\x00'*480


class Dialog:
    metadata = {}
    def __init__(self):
        self.received = []
        self.release = asyncio.Event()

    async def open(self):
        return []

    async def turn(self, text, on_reply=None):
        self.received.append(text)
        number = len(self.received)
        if number == 1:
            await self.release.wait()
        await on_reply('Reply ' + str(number))

    async def close(self):
        pass


class AudioPauseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.speech, self.dialog, self.microphone = Speech(), Dialog(), Microphone()
        self.call = NativeCall(Config(), self.speech, self.dialog)
        self.call.spawn(self.call.microphone(self.microphone))
        self.call.spawn(self.call.process_turns())

    async def asyncTearDown(self):
        self.dialog.release.set()
        self.speech.release_audio.set()
        await self.call.close()

    def utterance(self):
        self.microphone.feed(20, True)
        self.microphone.feed(70, False)

    async def test_continuation_during_backend_wait_does_not_mute_replies(self):
        self.utterance()
        await until(lambda:len(self.dialog.received) == 1)
        self.utterance()
        await until(lambda:self.speech.transcriptions == 2)
        self.dialog.release.set()
        await until(lambda:len(self.dialog.received) == 2)
        await until(lambda:len(self.speech.spoken) >= 1)
        self.assertEqual(self.speech.spoken, ['Reply 1', 'Reply 2'])

    async def test_empty_followup_asr_does_not_mute_pending_backend_reply(self):
        self.speech.empty_second = True
        self.utterance()
        await until(lambda:len(self.dialog.received) == 1)
        self.utterance()
        await until(lambda:self.speech.transcriptions == 2)
        self.dialog.release.set()
        await until(lambda:self.call.recognized_turns._unfinished_tasks == 0)
        self.assertEqual(self.speech.spoken, ['Reply 1'])
        self.assertEqual(self.dialog.received, ['Utterance 1'])

    async def test_actual_barge_in_fences_queued_and_late_speech(self):
        self.speech.hold_first = True
        self.utterance()
        await until(lambda:len(self.dialog.received) == 1)
        self.dialog.release.set()
        await asyncio.wait_for(self.speech.first_pcm.wait(), 1)
        old_generation = self.call.playback.generation
        self.call.playback.read(960)
        self.assertTrue(self.call.synthesis_active)
        self.utterance()
        await until(lambda:self.speech.transcriptions == 2)
        self.assertGreater(self.call.playback.generation, old_generation)
        self.assertEqual(self.call.playback.data, bytearray())
        self.speech.release_audio.set()
        await until(lambda:len(self.speech.spoken) == 2)
        self.assertNotIn(b'\x09\x00', bytes(self.call.playback.data))
        self.assertIn(b'\x01\x00', bytes(self.call.playback.data))
        self.assertFalse(self.call.synthesis_active)

    async def test_queued_speech_is_interrupted_after_synthesis_has_finished(self):
        self.utterance()
        await until(lambda:len(self.dialog.received) == 1)
        self.dialog.release.set()
        await until(lambda:len(self.speech.spoken) == 1)
        self.assertFalse(self.call.synthesis_active)
        self.assertGreater(len(self.call.playback.data), 0)
        old_generation = self.call.playback.generation
        self.utterance()
        await until(lambda:self.speech.transcriptions == 2)
        self.assertGreater(self.call.playback.generation, old_generation)

    async def test_short_pause_remains_one_microphone_utterance(self):
        self.microphone.feed(20, True)
        self.microphone.feed(35, False)
        self.microphone.feed(20, True)
        self.microphone.feed(70, False)
        await until(lambda:self.microphone.frames.empty())
        await until(lambda:self.speech.transcriptions > 0)
        self.assertEqual(self.speech.transcriptions, 1)
        self.dialog.release.set()
        await until(lambda:len(self.speech.spoken) > 0)
        self.assertEqual(self.dialog.received, ['Utterance 1'])

    async def test_input_before_backend_open_suppresses_fallback_greeting(self):
        opened = asyncio.Event()
        async def delayed_open():
            await opened.wait()
            return []
        self.call.config.greeting = 'Fallback greeting'
        self.dialog.open = delayed_open
        self.dialog.record_greeting = lambda text:None
        self.utterance()
        await until(lambda:self.speech.transcriptions == 1)
        opened.set()
        await until(lambda:len(self.dialog.received) == 1)
        self.dialog.release.set()
        await until(lambda:len(self.speech.spoken) > 0)
        self.assertEqual(self.speech.spoken, ['Reply 1'])


class EndpointConfigurationTests(unittest.TestCase):
    def test_endpoint_silence_rejects_unbounded_or_noninteger_configuration(self):
        for invalid in (True, 1.2, '1200', 299, 2001):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                Config(vad_silence_ms=invalid)


if __name__ == '__main__':
    unittest.main()
