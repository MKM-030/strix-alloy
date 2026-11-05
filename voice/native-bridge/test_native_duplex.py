"""Focused model-free independent Native conversation checks."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import PlaybackBuffer
from native_backend import BackendEvent, BackendState, UNSET
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
        self.backend_owner = object()
        self.metadata = {'conversation_id': 'c' * 32}
        self.backend_state = self.input_control = None
        self.business_request_id = ''
        self._event_id = 0

    def record_public_reply(self, reply):
        if reply:
            self.public_replies.append(reply)

    async def turn(self, text, on_reply=None, voice_context=None, *, on_event=None,
                   native_control_binding=UNSET, on_accepted=None):
        self.calls.append(text)
        self.business_request_id = f'{len(self.calls):032x}'
        if on_accepted is not None:
            on_accepted(self.business_request_id, self.backend_owner)
        await self.started.put(text)
        response = await self.release.get()
        reply = response['reply'] if isinstance(response, dict) else response
        self.input_boundary = response.get('input_boundary') if isinstance(response, dict) else None
        if self.input_boundary is not None:
            self.input_boundary = dict(self.input_boundary, businessRequestId=self.business_request_id)
            self._event_id += 1
            self.input_control = BackendEvent(self._event_id, self.business_request_id,
                self.input_boundary['controlType'], self.input_boundary['label'],
                'offline-control-' + str(self._event_id), self.backend_owner)
        else:
            self.input_control = None
        self.backend_state = BackendState(self.business_request_id, 'MESSAGE', False, False, False, self.backend_owner)
        self.record_public_reply(reply)
        self.current_question = self.input_boundary['label'] if self.input_boundary else ''
        self.observation_revision += 1
        if on_event is not None:
            if self.input_control is not None and reply == self.input_control.text:
                await on_event(self.input_control)
            elif reply:
                self._event_id += 1
                await on_event(BackendEvent(self._event_id, self.business_request_id, 'OutputText',
                    reply, '', self.backend_owner))
            if self.input_control is not None and reply != self.input_control.text:
                await on_event(self.input_control)
        elif on_reply is not None:
            await on_reply(reply)
        return [reply]


class FakeCall:
    def __init__(self):
        self.config = SimpleNamespace(conversation_ws_url='offline-conversation-fixture')
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

    def transcript(self, turn, role, text, *, started_at=None, control_type=None):
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

    async def test_free_question_waits_in_raw_fifo_without_parallel_business_post(self):
        first, question = 'Bitte einen neuen Mitarbeiter vorbereiten.', 'Gibt es schon etwas Konkretes?'
        self.call.feed(first)
        self.assertEqual(await self.next_business(), first)
        self.call.feed(question, 2)
        await asyncio.wait_for(self.call.recognized_turns.join(), 1)
        await self.until(lambda: bool(self.call.spoken))
        self.assertLessEqual(len(self.call.spoken[-1]), 120)
        self.assertEqual(self.call.dialog.calls, [first])
        self.assertEqual([turn[1] for turn in self.lane._pending], [question])
        self.call.dialog.release.put_nowait('Native erste Antwort.')
        self.assertEqual(await self.next_business(), question)
        self.assertEqual(self.call.dialog.calls, [first, question])

    async def test_busy_correction_reaches_native_once_without_local_spelling_workflow(self):
        first, correction = 'Mara Lueders', 'Nein: L, ü, h, d, e, r, s!'
        self.call.feed(first)
        await self.next_business()
        self.call.feed(correction, 2)
        await self.until(lambda: bool(self.lane._pending))
        self.assertEqual(self.call.dialog.calls, [first])
        self.call.dialog.release.put_nowait({'reply':'Bitte erläutern Sie Ihre Angabe.',
            'input_boundary':dict(source='servicenow_input_control', controlType='InputText',
                businessRequestId='business-1', label='Bitte erläutern Sie Ihre Angabe.')})
        self.assertEqual(await self.next_business(), correction)
        self.assertEqual(self.call.dialog.calls, [first, correction])
        self.assertEqual(self.call.dialog.calls.count(correction), 1)
        self.assertFalse(any('buchstabieren Sie zuerst' in text for text in self.call.spoken))

    async def test_raw_yes_creates_no_local_approval_and_mixed_question_remains_verbatim(self):
        self.call.feed('Ja, genau so.')
        self.assertEqual(await self.next_business(), 'Ja, genau so.')
        self.assertFalse(any('Bestätigung' in text for text in self.call.spoken))
        self.call.dialog.release.put_nowait('Welche Angabe möchten Sie erläutern?')
        await self.until(lambda: not self.lane.busy)
        raw = 'Wie lange dauert das und bitte verwende Lühders?'
        self.call.feed(raw, 2)
        self.assertEqual(await self.next_business(), raw)
        self.assertEqual(self.call.dialog.calls, ['Ja, genau so.', raw])

    async def test_optional_model_outage_preserves_first_and_later_native_input(self):
        first, second = 'Was kannst du?', 'Mara Lühders'
        self.call.feed(first)
        self.assertEqual(await self.next_business(), first)
        await self.until(lambda: bool(self.call.spoken))
        self.assertLessEqual(len(self.call.spoken[-1]), 120)
        self.call.feed(second, 2)
        self.call.dialog.release.put_nowait('Native Rückfrage.')
        self.assertEqual(await self.next_business(), second)
        self.assertEqual(self.call.dialog.calls, [first, second])
        self.assertFalse(self.call.failed)

    async def test_new_input_invalidates_queued_local_speech(self):
        self.call.vad_active = True
        self.call.feed('Was kannst du?')
        await self.until(lambda: self.lane.output_pending)
        self.lane.interrupt()
        self.call.vad_active = False
        await asyncio.sleep(.05)
        self.assertEqual(self.call.spoken, [])

    async def test_barge_in_releases_stalled_old_tts_for_brief_new_feedback(self):
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
        self.assertLessEqual(len(self.call.spoken[-1]), 120)
        self.assertNotIn('Welche Angabe', self.call.spoken[-1])

    async def test_actual_backend_evidence_stays_current_without_inventing_completion(self):
        self.call.feed('Auftrag')
        await self.next_business()
        self.call.dialog.release.put_nowait('Das angefragte Modell ist nicht verfügbar.')
        await self.until(lambda: not self.lane.busy)
        self.assertIn('Das angefragte Modell ist nicht verfügbar.', self.lane._status())
        self.call.feed('Was weißt du sicher?', 2)
        self.assertEqual(await self.next_business(), 'Was weißt du sicher?')
        self.call.dialog.release.put_nowait('Ein öffentlicher Satz. ' * 400)
        await self.until(lambda: not self.lane.busy)
        excerpt = self.lane._status()
        self.assertLess(len(excerpt), 500)
        self.assertIn('Auszug', excerpt)
        self.assertIn('länger', excerpt)

    async def test_natural_dialogue_persists_while_raw_questions_reach_native(self):
        class Conversation:
            output_epoch = 1
            def __init__(inner):
                inner.inputs, inner.closed = [], False
                inner.identity = SimpleNamespace(server_session_id='private-session')
            def invalidate(inner, epoch, reason):
                inner.output_epoch = epoch
                async def done():
                    return None
                return done()
            async def respond(inner, raw, snapshot, key):
                inner.inputs.append((raw, snapshot, key))
                return SimpleNamespace(text='Gern, welche Frage möchten Sie besprechen?', failure=None, identity=inner.identity)
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
        self.assertEqual(await self.next_business(), 'Was kannst du?')
        await self.until(lambda: len(conversation.inputs) == 1)
        self.call.dialog.release.put_nowait('Das angefragte Modell ist nicht verfügbar.')
        await self.until(lambda: not self.lane.busy)
        self.call.feed('Wie kannst du mir helfen?', 2)
        self.assertEqual(await self.next_business(), 'Wie kannst du mir helfen?')
        await self.until(lambda: len(conversation.inputs) == 2)
        self.assertEqual(conversation.inputs[1][1]['raw_inputs'], ('Was kannst du?', 'Wie kannst du mir helfen?'))
        self.assertEqual(conversation.inputs[1][2]['call_id'], 'test-call')
        self.assertEqual(self.call.dialog.calls, ['Was kannst du?', 'Wie kannst du mir helfen?'])
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
    def test_status_and_other_questions_share_optional_conversation_without_consuming_raw_input(self):
        self.assertEqual(_question_kind('Sag mir bitte kurz, was du bisher weißt.'), 'help')
        self.assertEqual(_question_kind('Wie weit seid ihr denn inzwischen?'), 'help')

    def test_optional_dialogue_kind_never_decides_business_submission(self):
        for text in ('Wie weit seid ihr und bitte verwende Lühders?', 'Ja, genau so.',
                     'Wie lange dauert das und bestelle bitte den Laptop?'):
            self.assertEqual(_question_kind(text), 'help')

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
