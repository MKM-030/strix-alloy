"""Offline safety tests: stop-after-name must never load confirmation audio."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import wave

import demo_audio_smoke as demo


class StopAfterNameTests(unittest.IsolatedAsyncioTestCase):
    def test_native_assistant_failure_transcripts_stop_probe(self):
        fatal = getattr(demo, 'fatal_probe_event', None)
        self.assertIsNotNone(fatal, 'assistant transcript failure guard missing')
        self.assertTrue(fatal({'type':'error'}))
        for code in ('TURN_FAILED', 'BUSY', 'ASR_FAILED', 'ASR_EMPTY'):
            self.assertTrue(fatal({'type':'transcript', 'data':{'role':'assistant', 'code':code}}))
        for event in ({'type':'transcript', 'data':{'role':'assistant', 'content':'Wie heißt er?'}},
                      {'type':'transcript', 'data':{'role':'user', 'code':'BUSY'}},
                      {'type':'transcript', 'data':{'role':'assistant', 'code':'OTHER'}},
                      {'type':'transcript', 'data':{'role':'assistant', 'code':[]}},
                      {'type':'transcript', 'data':None}):
            self.assertFalse(fatal(event))

    async def test_ready_name_turn_never_loads_confirmation_or_requests_review(self):
        handler = getattr(demo, 'name_then_optional_confirmation', None)
        self.assertIsNotNone(handler, 'explicit stop-before-confirmation branch missing')
        for summary in (demo.EXPECTED_SUMMARY, 'Laptop für Philipp Borchert. Soll ich bestellen?'):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as tmp:
                fixture = Path(tmp) / 'synthetic-name.wav'
                with wave.open(str(fixture), 'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                    wav.writeframes(b'\0\0' * 160)
                microphone = demo.Microphone()
                loaded = []
                events = []
                dialog = SimpleNamespace(state={}, latest_replies=[])

                async def speak(path):
                    loaded.append(str(path))
                    microphone.load(path)
                    dialog.state = {'busy':False, 'ended':False, 'failed':False,
                                    'inputLabel':summary, 'choices':[{'label':'Bestellen'}]}
                    dialog.latest_replies = [summary]

                trace = SimpleNamespace(add=lambda kind, **data: events.append((kind, data)))
                with patch.object(demo, 'review_summary', new=AsyncMock(
                        side_effect=AssertionError('operator review is forbidden in stop mode'))) as review:
                    confirmed = await handler(speak, dialog, trace, asyncio.Event(),
                                              name_fixture=fixture, stop_after_name=True)
                    review.assert_not_awaited()
                self.assertFalse(confirmed)
                self.assertEqual(loaded, [str(fixture)])
                self.assertEqual(events[0][0], 'stopped_after_name_before_confirmation')
                self.assertIs(events[0][1]['confirmation_not_sent'], True)

    async def test_unready_or_ended_name_turn_fails_before_confirmation(self):
        handler = getattr(demo, 'name_then_optional_confirmation', None)
        self.assertIsNotNone(handler, 'explicit stop-before-confirmation branch missing')
        for state in ({'busy':True}, {'busy':False, 'ended':True},
                      {'busy':False, 'failed':True}, {}, {'busy':False, 'inputLabel':''}):
            with self.subTest(state=state):
                loaded = []
                dialog = SimpleNamespace(state=state, latest_replies=[])
                async def speak(path):
                    loaded.append(str(path))
                trace = SimpleNamespace(add=lambda *a, **kw: None)
                with patch.object(demo, 'review_summary', new=AsyncMock()) as review:
                    with self.assertRaises(RuntimeError):
                        await handler(speak, dialog, trace, asyncio.Event(),
                                      name_fixture=Path('name.wav'), stop_after_name=True)
                    review.assert_not_awaited()
                self.assertEqual(loaded, ['name.wav'])

    def test_cli_requires_explicit_name_fixture_and_exclusive_mode(self):
        parse = getattr(demo, 'parse_args', None)
        self.assertIsNotNone(parse, 'stop-after-name CLI validation missing')
        prefix = ['--run-approved-audio-demo']
        accepted = parse(prefix + ['--stop-after-name', '--name-fixture', 'name.wav'])
        self.assertTrue(accepted.stop_after_name)
        self.assertFalse(accepted.first_turn_only)
        for suffix in (['--stop-after-name'], ['--name-fixture','name.wav'],
                       ['--stop-after-name','--name-fixture','name.wav','--first-turn-only'],
                       ['--stop-after-name','--name-fixture','name.wav','--hello-first']):
            with self.subTest(suffix=suffix), patch('sys.stderr'):
                with self.assertRaises(SystemExit):
                    parse(prefix + suffix)

    async def test_missing_name_fixture_fails_before_configuration_or_http(self):
        self.assertIsNotNone(getattr(demo, 'parse_args', None), 'stop-after-name CLI validation missing')
        args = SimpleNamespace(stop_after_name=True, name_fixture='missing-name-fixture.wav',
                               first_turn_only=False, hello_first=False)
        with patch.object(demo, 'ClientSession', side_effect=AssertionError('no HTTP allowed')):
            with self.assertRaises(FileNotFoundError):
                await demo.run(args)


if __name__ == '__main__':
    unittest.main()
