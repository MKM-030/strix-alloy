"""Model-free local sentence release, TTS and unchanged native FIFO behavior."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall

RAW = 'Der Laptop ist für Mara Testfeld und soll nach Hamburg geliefert werden.'
UNSAFE = 'Danke, ich habe mir den Namen Mara Testfeld und den Lieferort Hamburg notiert.'
QUESTION = 'Wann ist das Eintrittsdatum?'
FALLBACK = 'Ich kann Ihre Frage gerade nicht zuverlässig beantworten.'


class SentenceModel:
    sentence_streaming = True
    output_epoch = 1

    def __init__(self, sentences, before=None):
        self.sentences, self.before = sentences, before
        self.identity = SimpleNamespace(server_session_id='owned-offline-session', socket_instance='owned-offline-socket')
        self.current, self.closed = True, False
        self.inputs, self.offered = [], []
        self.done = asyncio.Event()

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    def is_current(self, identity):
        return self.current and identity is self.identity

    async def close(self):
        self.closed = True

    async def respond(self, raw, snapshot, key, *, on_sentence=None):
        self.inputs.append(raw)
        try:
            for index, text in enumerate(self.sentences):
                if self.before is not None:
                    self.before(index)
                self.offered.append(text)
                if on_sentence is not None:
                    await on_sentence(SimpleNamespace(text=text, identity=self.identity))
            return SimpleNamespace(text=' '.join(self.sentences), failure=None, identity=self.identity)
        except ValueError:
            return SimpleNamespace(text='', failure='output_callback_failed', identity=self.identity)
        finally:
            self.done.set()


class ClaimReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.tasks = []

    async def asyncTearDown(self):
        self.call.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(1):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    def start_speaker(self):
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))

    async def generate(self, model):
        self.lane.conversation = model
        turn = (0, RAW, 1, 'owned-input', 0)
        self.lane._observe_raw(RAW)
        await self.lane._general_help(turn, self.lane.epoch)

    async def test_unsafe_ack_is_never_synthesized_but_later_question_and_original_fifo_continue(self):
        model = SentenceModel([UNSAFE, QUESTION])
        async def factory(*args):
            return model
        self.lane._factory = factory
        self.tasks.append(asyncio.create_task(self.lane.run()))
        self.call.feed(RAW)
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), RAW)
        await self.until(lambda: QUESTION in self.call.spoken)
        self.assertEqual(self.call.spoken, [QUESTION])
        self.assertEqual(model.inputs, [RAW])
        self.assertFalse(model.closed)
        next_raw = 'Welche Angaben fehlen dir noch?'
        self.call.feed(next_raw, 2)
        await self.until(lambda: len(self.lane._pending) == 1)
        self.assertEqual(self.call.dialog.calls, [RAW])
        self.call.dialog.release.put_nowait('Weitere Angaben können wir gleich klären.')
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), next_raw)
        self.assertEqual(self.call.dialog.calls, [RAW, next_raw])
        self.assertEqual(self.call.dialog.calls.count(RAW), 1)
        self.assertEqual(self.call.dialog.calls.count(next_raw), 1)

    async def test_all_unsafe_stream_uses_existing_fallback_without_model_retry(self):
        model = SentenceModel([UNSAFE, 'Ihre Angaben wurden gespeichert.'])
        self.start_speaker()
        await self.generate(model)
        await self.until(lambda: bool(self.call.spoken))
        self.assertEqual(self.call.spoken, [FALLBACK])
        self.assertEqual(model.inputs, [RAW])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_nonstreaming_unsafe_candidate_keeps_existing_boolean_rejection_and_fallback(self):
        model = SentenceModel([UNSAFE])
        model.sentence_streaming = False
        self.start_speaker()
        await self.generate(model)
        await self.until(lambda: bool(self.call.spoken))
        self.assertEqual(self.call.spoken, [FALLBACK])
        self.assertEqual(model.inputs, [RAW])

    async def test_invalid_identity_cannot_be_hidden_by_skipping_a_claim(self):
        model = SentenceModel([UNSAFE, QUESTION])
        model.current = False
        self.start_speaker()
        with self.assertLogs('native-voice', level='INFO') as captured:
            await self.generate(model)
        await self.until(lambda: bool(self.call.spoken))
        self.assertEqual(model.offered, [UNSAFE])
        self.assertEqual(self.call.spoken, [FALLBACK])
        self.assertTrue(model.closed)
        self.assertIn('reason=identity_not_current at=sentence', '\n'.join(captured.output))

    async def test_source_number_markup_and_identifier_violations_abort_even_on_unsafe_claims(self):
        for text, reason in (
                ('Ich habe <intern> notiert.', 'markup'),
                ('Ich habe 749 Angaben notiert.', 'unbound_number'),
                ('Ich habe test-call notiert.', 'identifier_in_text'),
                ('Ich habe analysis notiert.', 'internal_control_word')):
            with self.subTest(reason=reason):
                self.call = FakeCall()
                self.lane = NativeDuplex(self.call)
                model = SentenceModel([text, QUESTION])
                with self.assertLogs('native-voice', level='INFO') as captured:
                    await self.generate(model)
                self.assertEqual(model.offered, [text])
                self.assertEqual([item.text for item in self.lane._outputs], [FALLBACK])
                self.assertIn('reason='+reason+' at=sentence', '\n'.join(captured.output))
                await self.lane.close()

    async def test_context_drift_after_skipped_claim_aborts_remaining_speech(self):
        self.call.vad_active = True
        model = SentenceModel(['Wir können die nächsten Angaben klären.', UNSAFE, QUESTION], before=lambda index:
            setattr(self.call.dialog, 'observation_revision', 1) if index == 2 else None)
        await self.generate(model)
        self.call.vad_active = False
        self.start_speaker()
        await asyncio.sleep(.02)
        self.assertEqual(self.call.spoken, [])
        self.assertEqual(list(self.lane._outputs), [])
        self.assertEqual(model.inputs, [RAW])

    async def test_new_caller_interrupt_after_skipped_claim_aborts_remaining_speech(self):
        self.call.vad_active = True
        model = SentenceModel(['Wir können die nächsten Angaben klären.', UNSAFE, QUESTION], before=lambda index:
            self.lane.interrupt() if index == 2 else None)
        await self.generate(model)
        self.call.vad_active = False
        self.start_speaker()
        await asyncio.sleep(.02)
        self.assertEqual(self.call.spoken, [])
        self.assertEqual(model.inputs, [RAW])

    async def test_context_drift_on_unsafe_sentence_cannot_hide_a_hard_rejection(self):
        model = SentenceModel([UNSAFE, QUESTION], before=lambda index:
            setattr(self.call.dialog, 'observation_revision', 1) if index == 0 else None)
        await self.generate(model)
        self.assertEqual(model.offered, [UNSAFE])
        self.assertEqual(list(self.lane._outputs), [])

    async def test_negative_question_quote_and_modal_sentences_still_reach_tts(self):
        allowed = [
            'Ich habe nichts gespeichert.',
            'Wurden die Angaben geprüft?',
            'Sie sagten: „Ich habe es gespeichert.“',
            'Der Lieferort ist Hamburg und muss noch geprüft werden.',
            'Wir haben noch Angaben zu erfassen bevor diese geprüft werden.',
            'Die Angaben werden später geprüft werden.',
        ]
        model = SentenceModel(allowed)
        self.start_speaker()
        await self.generate(model)
        await self.until(lambda: len(self.call.spoken) == len(allowed))
        self.assertEqual(self.call.spoken, allowed)
        self.assertEqual(model.inputs, [RAW])

    async def test_claim_rejection_keeps_boolean_admission_false_without_queued_output(self):
        model = SentenceModel([UNSAFE])
        self.lane.conversation = model
        turn = (0, RAW, 1, 'owned-input', 0)
        self.lane._observe_raw(RAW)
        _, snapshot, observation = self.lane._dialogue_snapshot(turn, self.lane.epoch)
        value = self.lane._admit_conversation(SimpleNamespace(text=UNSAFE, identity=model.identity),
                                               turn, self.lane.epoch, observation, snapshot)
        self.assertIs(value, False)
        self.assertEqual(list(self.lane._outputs), [])

    async def test_backend_speech_remains_authoritative_and_is_not_filtered(self):
        self.start_speaker()
        self.lane._enqueue('ServiceNow hat die Angaben gespeichert.', kind='backend')
        await self.until(lambda: bool(self.call.spoken))
        self.assertEqual(self.call.spoken, ['ServiceNow hat die Angaben gespeichert.'])


if __name__ == '__main__':
    unittest.main()
