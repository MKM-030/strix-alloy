import array
import asyncio
import logging
import re
import unittest
from unittest.mock import patch

from native_bridge import Config, NativeCall, SpeakerTrack
from core import PlaybackBuffer


PRIVATE = 'PRIVATE_GREETING_TRANSCRIPT_TOKEN_DO_NOT_LOG'


class _Dialog:
    metadata = {}
    def __init__(self, greetings=None):
        self.greetings = greetings or []
        self.recorded = []
    async def open(self):
        return self.greetings
    def record_greeting(self, text):
        self.recorded.append(text)
    async def close(self):
        pass


class _Speech:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
    async def synthesize(self, text):
        self.started.set()
        await self.release.wait()
        yield array.array('h', [1200] * 480).tobytes()
        self.finished.set()


class GreetingDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_greeting_logs_order_bytes_and_no_content(self):
        speech = _Speech()
        dialog = _Dialog()
        call = NativeCall(Config(greeting=PRIVATE), speech, dialog)
        with self.assertLogs('native-voice', level='INFO') as captured:
            worker = call.spawn(call.process_turns())
            try:
                await asyncio.wait_for(speech.started.wait(), .5)
                self.assertFalse(speech.finished.is_set())
                self.assertEqual(len(call.playback.data), 0)
                speech.release.set()
                await asyncio.wait_for(speech.finished.wait(), .5)
                self.assertEqual(len(call.playback.data), 960)
                self.assertEqual(dialog.recorded, [PRIVATE])
                self.assertFalse(worker.done())
            finally:
                await call.close()
        logs = '\n'.join(captured.output)
        stages = re.findall(r'stage=(dialog_open_begin|dialog_open_end|greeting_fallback|greeting_tts_begin|greeting_tts_first_chunk|greeting_tts_end)', logs)
        self.assertEqual(stages, ['dialog_open_begin', 'dialog_open_end', 'greeting_fallback', 'greeting_tts_begin', 'greeting_tts_first_chunk', 'greeting_tts_end'])
        self.assertIn('greeting_count=0', logs)
        self.assertRegex(logs, r'stage=greeting_tts_end .*bytes=960 accepted_bytes=960 .*outcome=complete')
        self.assertRegex(logs, r'stage=greeting_tts_first_chunk .*elapsed_ms=\d+')
        self.assertNotIn(PRIVATE, logs)
        self.assertIn('call=' + call.call_id, logs)

    async def test_interrupt_before_first_chunk_is_distinguished_from_empty_tts(self):
        speech = _Speech()
        call = NativeCall(Config(greeting=PRIVATE), speech, _Dialog())
        with self.assertLogs('native-voice', level='INFO') as captured:
            call.spawn(call.process_turns())
            try:
                await asyncio.wait_for(speech.started.wait(), .5)
                call.input_started = True
                call.playback.interrupt()
                speech.release.set()
                await asyncio.sleep(.02)
                self.assertEqual(len(call.playback.data), 0)
                self.assertFalse(call.synthesis_active)
            finally:
                await call.close()
        logs = '\n'.join(captured.output)
        self.assertRegex(logs, r'stage=greeting_tts_end .*bytes=960 accepted_bytes=0 .*outcome=interrupted')
        self.assertNotIn(PRIVATE, logs)

    async def test_fallback_skip_reason_preserves_existing_no_tts_behavior(self):
        speech = _Speech()
        call = NativeCall(Config(greeting=PRIVATE), speech, _Dialog())
        call.input_started = True
        with self.assertLogs('native-voice', level='INFO') as captured:
            call.spawn(call.process_turns())
            try:
                await asyncio.sleep(.01)
                self.assertFalse(speech.started.is_set())
                self.assertEqual(call.dialog.recorded, [])
            finally:
                await call.close()
        logs = '\n'.join(captured.output)
        self.assertIn('stage=greeting_skip reason=prior_input', logs)
        self.assertNotIn(PRIVATE, logs)

    async def test_synthesis_error_records_end_without_exception_content(self):
        class FailedSpeech:
            async def synthesize(self, text):
                raise RuntimeError(PRIVATE)
                yield b''
        call = NativeCall(Config(greeting=PRIVATE), FailedSpeech(), _Dialog())
        async def no_failure_speech():
            call.failed = True
        call.report_backend_failure = no_failure_speech
        with self.assertLogs('native-voice', level='INFO') as captured:
            try:
                await asyncio.wait_for(call.spawn(call.process_turns()), .5)
            finally:
                await call.close()
        logs = '\n'.join(captured.output)
        self.assertRegex(logs, r'stage=greeting_tts_end .*bytes=0 accepted_bytes=0 .*outcome=error')
        self.assertNotIn(PRIVATE, logs)

    async def test_speaker_reports_first_non_silent_drain_once(self):
        playback = PlaybackBuffer()
        track = SpeakerTrack(playback)
        with self.assertLogs('native-voice', level='INFO') as captured:
            silent = await track.recv()
            self.assertEqual(silent.to_ndarray().max(), 0)
            playback.put(array.array('h', [1200] * 960).tobytes(), 0)
            first = await track.recv()
            second = await track.recv()
        self.assertEqual(first.to_ndarray().min(), 1200)
        self.assertEqual(second.to_ndarray().min(), 1200)
        logs = '\n'.join(captured.output)
        self.assertEqual(logs.count('stage=first_non_silent_pcm'), 1)
        self.assertIn('pcm_bytes=960', logs)
        self.assertNotIn(PRIVATE, logs)

    async def test_datachannel_open_logs_once_without_changing_flush(self):
        class Channel:
            label = 'transcripts'
            readyState = 'open'
            def __init__(self):
                self.sent = []
                self.callbacks = {}
            def on(self, name, callback):
                self.callbacks[name] = callback
            def send(self, message):
                self.sent.append(message)
        call = NativeCall(Config(), _Speech(), _Dialog())
        channel = Channel()
        call.pending_events.append({'type':'transcript', 'data':{'content':PRIVATE}})
        with self.assertLogs('native-voice', level='INFO') as captured:
            try:
                call.datachannel(channel)
                channel.callbacks['open']()
                self.assertEqual(len(channel.sent), 1)
                self.assertIn(PRIVATE, channel.sent[0])
            finally:
                await call.close()
        logs = '\n'.join(captured.output)
        self.assertEqual(logs.count('stage=datachannel_open'), 1)
        self.assertIn('pending_events=1', logs)
        self.assertNotIn(PRIVATE, logs)


if __name__ == '__main__':
    unittest.main()
