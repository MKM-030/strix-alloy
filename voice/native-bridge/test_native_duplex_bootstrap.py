"""Local dialogue remains usable while one call-owned VA bootstrap settles."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


QUESTION = 'Wie lautet der Name des Mitarbeiters?'
BOUNDARY = dict(source='servicenow_input_control', controlType='InputText',
                businessRequestId='startup-request', label=QUESTION)
LOCAL_REPLY = 'Wir können Ihr Anliegen gemeinsam besprechen. Wobei möchten Sie Hilfe?'


class Conversation:
    output_epoch = 1
    def __init__(self):
        self.inputs = []
        self.closed = False
        self.identity = SimpleNamespace(server_session_id='private-local-session')

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    async def respond(self, raw, snapshot, key):
        self.inputs.append((raw, snapshot, key))
        return SimpleNamespace(text=LOCAL_REPLY, failure=None, identity=self.identity)

    def is_current(self, identity):
        return identity is self.identity

    async def close(self):
        self.closed = True


class BootstrapDialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.conversation = Conversation()
        async def factory(url, call_id, epoch):
            self.conversation.output_epoch = epoch
            return self.conversation
        self.lane = NativeDuplex(self.call, conversation_factory=factory)
        self.gate = asyncio.Event()
        self.open_count = 0
        self.boot_result = []
        self.boot_error = None
        async def open_once():
            self.open_count += 1
            await self.gate.wait()
            if self.boot_error is not None:
                raise self.boot_error
            return self.boot_result
        self.opening = asyncio.create_task(open_once())
        try:
            self.running = asyncio.create_task(self.lane.run(bootstrap_task=self.opening))
        except TypeError:
            self.opening.cancel()
            await asyncio.gather(self.opening, return_exceptions=True)
            self.fail('NativeDuplex must accept the one call-owned bootstrap task')

    async def asyncTearDown(self):
        self.call.closed = True
        self.running.cancel()
        self.opening.cancel()
        await asyncio.gather(self.running, self.opening, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(2):
            while not predicate():
                if self.running.done():
                    self.fail('Bootstrap-aware dialogue stopped: ' + repr(self.running.exception()))
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.005)

    async def consumed(self):
        await self.until(lambda: self.call.recognized_turns._unfinished_tasks == 0)

    async def settle(self, messages=None):
        self.boot_result = messages or []
        self.gate.set()
        await self.until(lambda: not self.lane.bootstrap_pending)

    async def test_local_model_answers_while_bootstrap_pending_without_business_dispatch(self):
        self.call.feed('Was kannst du?')
        await self.until(lambda: LOCAL_REPLY in self.call.spoken)
        self.assertFalse(self.opening.done())
        self.assertEqual(self.open_count, 1)
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual([item[0] for item in self.conversation.inputs], ['Was kannst du?'])
        self.assertTrue(self.lane.bootstrap_pending)
        self.assertTrue(self.lane.busy, 'Native inactivity must not expire during owned startup')

    async def test_structural_auth_rejection_gets_fixed_feedback_without_business_dispatch(self):
        from startup_reason import NativeStartupError
        self.boot_error = NativeStartupError('servicenow_caller_create_unauthorized')
        self.gate.set()
        await self.until(lambda: not self.lane.bootstrap_pending)
        self.assertIn('Anmeldung', self.lane._status())
        self.assertNotIn('abgelaufen', self.lane._status())
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual(self.open_count, 1)

    async def test_early_intent_is_dispatched_once_only_after_success(self):
        self.call.feed('Bitte einen Mitarbeiter vorbereiten.')
        await self.consumed()
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual(self.lane.pending_count, 1)
        topic_question = 'Was möchten Sie vorbereiten?'
        self.call.dialog.input_boundary = dict(BOUNDARY, label=topic_question)
        await self.settle([topic_question])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1),
                         'Bitte einen Mitarbeiter vorbereiten.')
        self.assertEqual(self.call.dialog.calls, ['Bitte einen Mitarbeiter vorbereiten.'])
        self.assertNotIn(topic_question, self.call.spoken,
                         'A startup question superseded by the queued intent must not be replayed')
        self.assertEqual(self.open_count, 1)

    async def test_second_early_utterance_is_delivered_in_original_fifo_order(self):
        first, extra = 'Bitte einen Mitarbeiter vorbereiten.', 'Nachname: L, ü, h, d, e, r, s!'
        self.call.feed(first)
        await self.consumed()
        self.call.feed(extra, 2)
        await self.consumed()
        self.assertEqual([item[1] for item in self.lane._pending], [first, extra])
        self.assertEqual(list(self.lane._supplements), [])
        await self.settle()
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), first)
        self.call.dialog.release.put_nowait({'reply':QUESTION, 'input_boundary':dict(BOUNDARY)})
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), extra)
        self.assertEqual(self.call.dialog.calls, [first, extra])

    async def test_partial_startup_question_and_progress_are_not_business_evidence(self):
        await self.until(lambda: self.open_count == 1)
        self.call.dialog.public_replies = [QUESTION]
        self.call.dialog.current_question = QUESTION
        self.call.dialog.input_boundary = dict(BOUNDARY)
        self.call.dialog.processing = dict(source='servicenow_processing',
            agentCompletionKnown=False, revision=1, messages=['Datensatz wird geprüft.'], ageSeconds=0)
        self.call.dialog.processing_observed_at = self.lane.clock()
        self.call.feed('Was kannst du?')
        await self.until(lambda: bool(self.conversation.inputs))
        snapshot = self.conversation.inputs[-1][1]
        self.assertEqual(snapshot['question'], '')
        self.assertEqual(snapshot['public_findings'], ())
        self.assertEqual(self.lane._current_question(), '')
        self.assertEqual(self.lane._automatic_update(), (None, None))
        limits = ' '.join(snapshot['capability_limits'])
        self.assertIn('vorbereitet', limits)
        self.assertNotIn('Eine übermittelte Eingabe läuft noch', limits)
        self.assertIn('vorbereitet', self.lane._status())

    async def test_settled_startup_question_is_spoken_once_with_real_control_binding(self):
        self.call.dialog.input_boundary = dict(BOUNDARY)
        self.call.dialog.current_question = QUESTION
        await self.settle([QUESTION, QUESTION])
        await self.until(lambda: QUESTION in self.call.spoken)
        await self.until(lambda: not self.lane.output_pending and not self.call.synthesis_active)
        self.call.playback.read(len(self.call.playback.data))
        self.assertEqual(self.call.spoken.count(QUESTION), 1)
        self.assertEqual(self.lane.question_context(), (QUESTION, 'servicenow_input_control', True))
        self.assertEqual(self.lane._spoken_question['binding'], BOUNDARY['businessRequestId'])
        self.assertEqual(self.call.dialog.calls, [])

    async def test_bootstrap_failure_keeps_local_dialogue_and_never_retries_business(self):
        self.boot_error = RuntimeError('fixture startup failure')
        self.call.feed('Bitte die Angaben prüfen.')
        await self.consumed()
        self.gate.set()
        await self.until(lambda: self.lane._backend_unavailable)
        self.assertFalse(self.running.done())
        self.assertFalse(self.call.failed)
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual(self.open_count, 1)
        self.call.feed('Was kannst du?', 2)
        await self.until(lambda: LOCAL_REPLY in self.call.spoken)
        self.assertIn('nicht vorbereitet', self.lane._status())
        self.assertEqual(self.call.dialog.calls, [])

    async def test_failed_bootstrap_keeps_held_intent_without_claiming_active_work_forever(self):
        self.boot_error = RuntimeError('fixture startup failure')
        original = 'Bitte die Angaben prüfen.'
        self.call.feed(original)
        await self.consumed()
        self.gate.set()
        await self.until(lambda: self.lane._backend_unavailable)
        self.assertEqual([item[1] for item in self.lane._pending], [original])
        self.assertFalse(self.lane.busy,
                         'Unsubmitted held data cannot disable normal idle expiry after failed startup')
        self.assertEqual(self.call.dialog.calls, [])

    async def test_early_name_reaches_native_once_without_local_readback(self):
        raw = 'Muthighefke'
        self.call.feed(raw)
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), raw)
        self.assertEqual(self.call.dialog.calls, [raw])
        self.assertFalse(any('Ich habe „' in text for text in self.call.spoken))
        self.assertEqual(self.open_count, 1)

    async def test_early_topic_intent_is_delivered_as_original_text_not_a_local_name(self):
        raw = 'Ich möchte einen Laptop bestellen.'
        self.call.feed(raw)
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), raw)
        self.assertEqual(self.call.dialog.calls, [raw])
        self.assertEqual(list(self.lane._supplements), [])
        self.assertFalse(any('Ich habe „' in text for text in self.call.spoken))

    async def test_unprompted_early_name_remains_raw_for_native_validation(self):
        raw = 'Muthighefke'
        self.call.feed(raw)
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), raw)
        self.assertEqual(list(self.lane._supplements), [])

    async def test_unprompted_early_intent_and_extra_are_not_stranded_at_name_control(self):
        first, extra = 'Ich möchte einen Laptop bestellen.', 'Zusätzlich einen Monitor.'
        self.call.feed(first)
        await self.consumed()
        self.call.feed(extra, 2)
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), first)
        self.call.dialog.release.put_nowait({'reply':QUESTION, 'input_boundary':dict(BOUNDARY)})
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), extra)
        self.assertEqual(self.call.dialog.calls, [first, extra])
        self.assertEqual(list(self.lane._supplements), [])

    async def test_early_positive_is_raw_text_not_a_locally_invented_name(self):
        raw = 'Ja, das stimmt'
        self.call.feed(raw)
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), raw)
        self.assertFalse(any('Buchstaben' in text or 'Ich habe „' in text for text in self.call.spoken))

    async def test_hearing_question_during_bootstrap_is_delivered_without_replaying_startup_question(self):
        self.call.feed('Hörst du mich?')
        await self.consumed()
        self.call.dialog.input_boundary = dict(BOUNDARY)
        await self.settle([QUESTION])
        self.assertEqual(await asyncio.wait_for(self.call.dialog.started.get(), 1), 'Hörst du mich?')
        self.call.dialog.release.put_nowait({'reply':QUESTION, 'input_boundary':dict(BOUNDARY)})
        await self.until(lambda: QUESTION in self.call.spoken)
        self.assertEqual(self.call.spoken.count(QUESTION), 1)

    async def test_cancelled_bootstrap_is_observed_without_cancelling_local_dialogue(self):
        self.opening.cancel()
        await self.until(lambda: self.lane._backend_unavailable)
        self.call.feed('Was kannst du?')
        await self.until(lambda: LOCAL_REPLY in self.call.spoken)
        self.assertFalse(self.running.done())
        self.assertEqual(self.call.dialog.calls, [])

    async def test_duplex_close_does_not_steal_call_owned_startup_or_next_call_state(self):
        await self.until(lambda: self.open_count == 1)
        self.running.cancel()
        await asyncio.gather(self.running, return_exceptions=True)
        self.assertFalse(self.opening.done(), 'Only NativeCall owns startup cancellation/drain')
        fresh = NativeDuplex(FakeCall())
        self.assertFalse(fresh.bootstrap_pending)
        self.assertFalse(fresh._backend_unavailable)
        await fresh.close()


if __name__ == '__main__':
    unittest.main()
