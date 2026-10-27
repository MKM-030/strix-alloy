"""Focused model-free independent Native conversation checks."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import PlaybackBuffer
from native_duplex import NativeDuplex, DurationUpdates, validate_conversation_url, _question_kind


class FakeDialog:
    def __init__(self):
        self.calls = []
        self.started = asyncio.Queue()
        self.release = asyncio.Queue()
        self.public_replies = []
        self.current_question = ''
        self.input_boundary = None
        self.processing = None
        self.observation_revision = 0

    def record_public_reply(self, reply):
        if reply:
            self.public_replies.append(reply)

    async def turn(self, text, on_reply=None, voice_context=None):
        self.calls.append(text)
        await self.started.put(text)
        response = await self.release.get()
        reply = response['reply'] if isinstance(response, dict) else response
        self.input_boundary = response.get('input_boundary') if isinstance(response, dict) else None
        self.record_public_reply(reply)
        self.current_question = self.input_boundary['label'] if self.input_boundary else ''
        self.observation_revision += 1
        await on_reply(reply)
        return [reply]


class FakeCall:
    def __init__(self):
        self.config = SimpleNamespace(conversation_ws_url='ws://127.0.0.1:8795/')
        self.call_id = 'test-call'
        self.dialog = FakeDialog()
        self.playback = PlaybackBuffer()
        self.closed = self.closing = self.input_lost = self.failed = False
        self.recognition_active = self.vad_active = self.synthesis_active = False
        self.turns = asyncio.Queue()
        self.recognized_turns = asyncio.Queue()
        self.turn_contexts = {}
        self.turn_controls = {}
        self.call_settings = None
        self.events = []
        self.spoken = []
        self.speech = SimpleNamespace(synthesize=self.synthesize)

    async def synthesize(self, text):
        self.spoken.append(text)
        yield bytes(480)

    async def wait_for_user_turn(self):
        return await self.recognized_turns.get()

    def transcript(self, turn, role, text):
        self.events.append((role, text))

    def notice(self, code, text):
        self.events.append((code, text))

    async def speak_language_control(self, *args):
        pass

    def feed(self, text, number=1):
        self.recognized_turns.put_nowait((self.playback.generation, text, number,
                                        str(number), time.monotonic()))


class DuplexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        async def unavailable(*args):
            raise RuntimeError('synthetic optional outage')
        self.lane = NativeDuplex(self.call, conversation_factory=unavailable)
        self.running = asyncio.create_task(self.lane.run())

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(2):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.005)

    async def next_business(self):
        return await asyncio.wait_for(self.call.dialog.started.get(), 1)

    async def test_question_answered_while_backend_pending_without_parallel_business_post(self):
        self.call.feed('Bitte einen neuen Mitarbeiter vorbereiten.')
        self.assertEqual(await self.next_business(), 'Bitte einen neuen Mitarbeiter vorbereiten.')
        self.call.dialog.processing = {'revision': 1, 'messages': ['Verfügbarkeit wird geprüft'],
            'ageSeconds': 0, 'source': 'servicenow_processing', 'agentCompletionKnown': False}
        self.call.feed('Gibt es schon etwas Konkretes?', 2)
        await self.until(lambda: bool(self.call.spoken))
        self.assertIn('Verfügbarkeit wird geprüft', self.call.spoken[-1])
        self.assertIn('Ergebnis', self.call.spoken[-1])
        self.assertEqual(self.call.dialog.calls, ['Bitte einen neuen Mitarbeiter vorbereiten.'])
        self.assertFalse(self.running.done())

    async def test_busy_correction_is_retained_until_fresh_input_at_current_boundary(self):
        self.call.feed('Mara Lueders')
        await self.next_business()
        raw = 'Nein: L, ü, h, d, e, r, s!'
        self.call.feed(raw, 2)
        await self.until(lambda: len(self.lane._supplements) == 1)
        self.assertEqual(self.call.dialog.calls, ['Mara Lueders'])
        self.call.dialog.release.put_nowait({'reply': 'Bitte buchstabieren Sie den Vornamen.',
            'input_boundary': {'source': 'servicenow_input_control', 'controlType': 'InputText',
                'businessRequestId': 'business-1', 'label': 'Bitte buchstabieren Sie den Vornamen.'}})
        await self.until(lambda: not self.lane.busy)
        self.assertEqual(self.call.dialog.calls, ['Mara Lueders'])
        self.assertEqual([turn[0][1] for turn in self.lane._supplements], [raw])
        fresh = 'L, ü, h, d, e, r, s!'
        self.call.feed(fresh, 3)
        self.assertEqual(await self.next_business(), fresh)
        self.call.dialog.release.put_nowait('Meinen Sie Mara Lühders?')
        await self.until(lambda: not self.lane.busy)
        self.assertEqual(self.call.dialog.calls.count(fresh), 1)
        self.assertNotIn(raw, self.call.dialog.calls)
        self.assertFalse(any('Meinen Sie Mara Lueders?' == s for s in self.call.spoken))

    async def test_unbound_yes_is_not_submitted_but_mixed_business_question_remains_verbatim(self):
        self.call.feed('Ja, genau so.')
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        self.assertEqual(self.call.dialog.calls, [])
        self.call.feed('Wie lange dauert das und bitte verwende Lühders?', 2)
        self.assertEqual(await self.next_business(),
                         'Wie lange dauert das und bitte verwende Lühders?')
        self.assertEqual(len(self.call.dialog.calls), 1)

    async def test_optional_model_outage_does_not_fail_call_or_block_later_business_turn(self):
        self.call.feed('Was kannst du?', 1)
        await self.until(lambda: bool(self.call.spoken))
        self.assertIn('ServiceNow', self.call.spoken[-1])
        self.assertEqual(self.call.dialog.calls, [])
        self.call.feed('Mara Lühders', 2)
        self.assertEqual(await self.next_business(), 'Mara Lühders')
        self.assertFalse(self.call.failed)

    async def test_new_input_invalidates_queued_local_speech(self):
        self.call.vad_active = True
        self.call.feed('Was kannst du?')
        await self.until(lambda: self.lane.output_pending)
        self.lane.interrupt()
        self.call.vad_active = False
        await asyncio.sleep(.05)
        self.assertEqual(self.call.spoken, [])

    async def test_barge_in_releases_stalled_old_tts_for_new_reply(self):
        entered = asyncio.Event()
        async def synthesis(text):
            self.call.spoken.append(text)
            if len(self.call.spoken) == 1:
                entered.set()
                await asyncio.Event().wait()
            yield bytes(480)
        self.call.speech.synthesize = synthesis
        self.call.feed('Was kannst du?')
        await asyncio.wait_for(entered.wait(), 1)
        self.lane.interrupt()
        self.call.feed('Was weißt du sicher?', 2)
        await self.until(lambda: len(self.call.spoken) == 2)
        self.assertIn('bestätigtes Ergebnis', self.call.spoken[-1])

    async def test_complete_backend_reply_is_quoted_and_never_inferred_as_completion(self):
        self.call.feed('Auftrag')
        await self.next_business()
        self.call.dialog.release.put_nowait('Das angefragte Modell ist nicht verfügbar.')
        await self.until(lambda: not self.lane.busy)
        self.call.feed('Was weißt du sicher?', 2)
        await self.until(lambda: any('Rückmeldung' in s for s in self.call.spoken))
        self.assertIn('Das angefragte Modell ist nicht verfügbar.', self.call.spoken[-1])
        self.assertEqual(self.call.dialog.calls, ['Auftrag'])
        self.call.feed('Bitte die Angaben prüfen.', 3)
        await self.next_business()
        self.call.dialog.release.put_nowait('Ein öffentlicher Satz. ' * 400)
        await self.until(lambda: not self.lane.busy)
        excerpt = self.lane._status()
        self.assertLess(len(excerpt), 500)
        self.assertIn('Auszug', excerpt)
        self.assertIn('länger', excerpt)

    async def test_natural_help_uses_persistent_candidate_and_current_snapshot(self):
        class Conversation:
            output_epoch = 1
            def __init__(inner):
                inner.inputs = []
                inner.closed = False
                inner.identity = SimpleNamespace(server_session_id='private-session')
            def invalidate(inner, epoch, reason):
                inner.output_epoch = epoch
                async def done():
                    return None
                return done()
            async def respond(inner, raw, snapshot, key):
                inner.inputs.append((raw, snapshot, key))
                return SimpleNamespace(text='Wir können die Angaben gemeinsam klären. Welche Frage möchten Sie zuerst besprechen?',
                                       failure=None, identity=inner.identity)
            def is_current(inner, identity):
                return identity is inner.identity
            async def close(inner):
                inner.closed = True
        conversation = Conversation()
        async def factory(url, call_id, epoch):
            conversation.output_epoch = epoch
            return conversation
        self.lane._factory = factory
        self.call.feed('Was kannst du?')
        await self.until(lambda: bool(self.call.spoken))
        self.call.dialog.public_replies = ['Das angefragte Modell ist nicht verfügbar.']
        self.call.feed('Wie kannst du mir helfen?', 2)
        await self.until(lambda: len(conversation.inputs) == 2)
        self.assertEqual(conversation.inputs[0][0], 'Was kannst du?')
        self.assertEqual(conversation.inputs[1][1]['raw_inputs'],
                         ('Was kannst du?', 'Wie kannst du mir helfen?'))
        self.assertEqual(conversation.inputs[1][1]['public_findings'][0]['text'],
                         'Das angefragte Modell ist nicht verfügbar.')
        self.assertEqual(conversation.inputs[1][2]['call_id'], 'test-call')
        self.assertEqual(self.call.dialog.calls, [])
        await self.lane.close()
        self.assertTrue(conversation.closed)


class NativeSeamTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_and_public_processing_are_bounded_without_new_request(self):
        from native_bridge import Config, Dialog
        config = Config(conversation_ws_url='ws://127.0.0.1:8795/')
        dialog = Dialog(config)
        dialog.observe_state({'processing': {'revision': 2, 'messages': ['Verfügbarkeit prüfen'],
            'ageSeconds': 1, 'source': 'servicenow_processing', 'agentCompletionKnown': False}})
        self.assertEqual(dialog.processing['messages'], ['Verfügbarkeit prüfen'])
        self.assertEqual(dialog.observation_revision, 1)
        dialog.observe_state({'processing': {'revision': 2, 'messages': ['hidden'],
            'ageSeconds': 1, 'source': 'internal_thoughts', 'agentCompletionKnown': True}})
        self.assertIsNone(dialog.processing)
        self.assertIsNone(dialog.http)

    async def test_empty_successful_tts_response_is_failure(self):
        from native_bridge import Config, Speech
        class Content:
            async def iter_chunked(self, size):
                if False:
                    yield b''
        class Response:
            status = 200
            content = Content()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        http = SimpleNamespace(post=lambda *args, **kwargs: Response())
        with self.assertRaisesRegex(RuntimeError, 'empty PCM'):
            async for _ in Speech(http, Config()).synthesize('Test'):
                pass


class DurationTests(unittest.TestCase):
    def test_natural_status_paraphrases_take_readonly_lane(self):
        self.assertEqual(_question_kind('Sag mir bitte kurz, was du bisher weißt.'), 'status')
        self.assertEqual(_question_kind('Wie weit seid ihr denn inzwischen?'), 'status')

    def test_mixed_action_correction_and_confirmation_stay_business(self):
        self.assertIsNone(_question_kind('Wie weit seid ihr und bitte verwende Lühders?'))
        self.assertIsNone(_question_kind('Ja, genau so.'))
        self.assertIsNone(_question_kind('Wie lange dauert das und bestelle bitte den Laptop?'))

    def test_real_audio_duration_no_overlap_spacing_and_two_update_cap(self):
        self.assertEqual(DurationUpdates(240).delay, 240)
        updates = DurationUpdates(8)
        updates.start(0)
        self.assertEqual(updates.remaining_audio_seconds(480000), 10)
        self.assertFalse(updates.due(8, queued_bytes=480000))
        self.assertFalse(updates.due(18))
        self.assertTrue(updates.due(26))
        updates.sent(26)
        self.assertFalse(updates.due(40))
        self.assertTrue(updates.due(41))
        updates.sent(41)
        self.assertFalse(updates.due(1000))
        updates.start(1001)
        self.assertFalse(updates.due(1010, user_busy=True))
        self.assertFalse(updates.due(1018, output_pending=True))
        self.assertFalse(updates.due(1026, local_busy=True))
        self.assertFalse(updates.due(1034, synthesizing=True))

    def test_url_rejects_remote_credentials_query_and_wrong_scheme(self):
        self.assertEqual(validate_conversation_url(''), '')
        self.assertEqual(validate_conversation_url('ws://127.0.0.1:8795/'), 'ws://127.0.0.1:8795/')
        for value in ('wss://127.0.0.1:8795', 'ws://example.com:8795',
                      'ws://a:b@127.0.0.1:8795', 'ws://127.0.0.1:8795/?token=x', 8795):
            with self.assertRaises(ValueError):
                validate_conversation_url(value)


if __name__ == '__main__':
    unittest.main()
