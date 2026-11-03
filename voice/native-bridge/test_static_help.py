"""Static help survives public progress; mutable facts keep their guards."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_bridge import Dialog
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall
from test_native_duplex_bootstrap import Conversation


QUESTION = 'Wie lautet der Name des Mitarbeiters?'
CHUNKS = (b'\x01\x00' * 240, b'\x02\x00' * 240, b'\x03\x00' * 240)


def progress(dialog):
    # Use the production boundary that changed the S6 output validity.
    dialog.observe_state(dict(busy=True, processing=dict(
        source='servicenow_processing', agentCompletionKnown=False,
        revision=1, messages=['Vorgang wird vorbereitet'], ageSeconds=0)), sampled_at=1)


class StaticHelpTests(unittest.IsolatedAsyncioTestCase):
    def call(self):
        call = FakeCall()
        call.dialog = Dialog(call.config)
        return call

    async def fallback(self, call, *, pending=True):
        lane = NativeDuplex(call)
        lane._bootstrap_state = 'pending' if pending else 'ready'
        lane._model_failed = True
        turn = (0, 'Was kannst du für mich tun?', 1, 'help-turn', 0)
        await lane._general_help(turn, lane.epoch)
        return lane

    async def test_queued_generic_help_remains_valid_after_real_progress_update(self):
        call = self.call()
        lane = await self.fallback(call)
        self.assertEqual(len(lane._outputs), 1)
        item = lane._outputs[0]
        self.assertTrue(lane._valid(item))
        progress(call.dialog)
        self.assertEqual(call.dialog.observation_revision, 1)
        self.assertTrue(lane._valid(item), 'Unrelated progress dropped invariant help before playback')

    async def test_active_generic_help_finishes_all_pcm_after_real_progress_update(self):
        call = self.call()
        lane = await self.fallback(call)
        item = lane._outputs.popleft()

        async def synthesize(text):
            yield CHUNKS[0]
            progress(call.dialog)
            yield CHUNKS[1]
            yield CHUNKS[2]

        call.speech = SimpleNamespace(synthesize=synthesize)
        with self.assertLogs('native-voice', level='INFO') as captured:
            await lane._synthesize(item, call.playback.generation)
        self.assertEqual(bytes(call.playback.data), b''.join(CHUNKS),
                         'Progress truncated the stable help answer after its first chunk')
        self.assertTrue(any('tts_finished kind=local queued_bytes=1440' in line
                            and 'current=True' in line for line in captured.output))
        self.assertEqual(call.events, [('assistant', item.text)])

    async def test_question_suffix_remains_bound_while_invariant_explanation_survives(self):
        call = self.call()
        call.dialog.record_public_reply(QUESTION)
        lane = await self.fallback(call, pending=False)
        self.assertEqual(len(lane._outputs), 2,
                         'A mutable question still shares the invariant explanation output')
        explanation, suffix = lane._outputs
        self.assertNotIn(QUESTION, explanation.text)
        self.assertIn(QUESTION, suffix.text)
        progress(call.dialog)
        self.assertTrue(lane._valid(explanation))
        self.assertFalse(lane._valid(suffix), 'A stale current-question suffix lost its observation guard')

    async def test_generated_and_status_outputs_keep_observation_guards(self):
        for kind in ('help', 'status'):
            with self.subTest(kind=kind):
                call = self.call()
                conversation = Conversation()
                async def factory(*args):
                    conversation.output_epoch = lane.epoch
                    return conversation
                lane = NativeDuplex(call, conversation_factory=factory)
                turn = (0, 'Was kannst du für mich tun?', 1, 'help-turn', 0)
                await lane._general_help(turn, lane.epoch, kind=kind)
                self.assertEqual(len(lane._outputs), 1)
                item = lane._outputs[0]
                self.assertEqual(item.kind, 'conversation' if kind == 'help' else 'status')
                self.assertTrue(lane._valid(item))
                progress(call.dialog)
                self.assertFalse(lane._valid(item))

    async def test_active_static_help_still_stops_for_input_task_and_call_changes(self):
        for change in ('input', 'task', 'closed', 'failed', 'generation'):
            with self.subTest(change=change):
                call = self.call()
                lane = await self.fallback(call)
                item = lane._outputs.popleft()
                generation = call.playback.generation

                async def synthesize(text):
                    yield CHUNKS[0]
                    if change == 'input':
                        lane.interrupt()
                    elif change == 'task':
                        lane.task_revision += 1
                    elif change == 'closed':
                        call.closed = True
                    elif change == 'failed':
                        call.failed = True
                    else:
                        call.playback.interrupt()
                    yield CHUNKS[1]
                    yield CHUNKS[2]

                call.speech = SimpleNamespace(synthesize=synthesize)
                with self.assertLogs('native-voice', level='INFO') as captured:
                    await lane._synthesize(item, generation)
                self.assertNotEqual(bytes(call.playback.data), b''.join(CHUNKS))
                self.assertTrue(any('tts_finished kind=local' in line and 'current=False' in line
                                    for line in captured.output))

    async def test_pending_bootstrap_help_keeps_all_pcm_without_a_business_turn(self):
        call = self.call()
        business_calls = []
        async def turn(*args, **kwargs):
            business_calls.append(args)
            raise AssertionError('Help must not dispatch a business turn')
        call.dialog.turn = turn
        async def unavailable(*args):
            raise RuntimeError('Optional local model unavailable')
        lane = NativeDuplex(call, conversation_factory=unavailable)
        gate = asyncio.Event()
        opening = asyncio.create_task(gate.wait())
        running = asyncio.create_task(lane.run(bootstrap_task=opening))
        completed = asyncio.Event()
        async def synthesize(text):
            yield CHUNKS[0]
            progress(call.dialog)
            yield CHUNKS[1]
            yield CHUNKS[2]
            completed.set()
        call.speech = SimpleNamespace(synthesize=synthesize)
        try:
            call.feed('Was kannst du für mich tun?')
            async with asyncio.timeout(1):
                while not completed.is_set() and len(call.playback.data) < len(CHUNKS[0]):
                    await asyncio.sleep(.001)
                while call.synthesis_active:
                    await asyncio.sleep(.001)
            self.assertTrue(completed.is_set(), 'Progress stopped the real fallback speaker early')
            self.assertEqual(bytes(call.playback.data), b''.join(CHUNKS))
            self.assertEqual(business_calls, [])
            self.assertFalse(opening.done())
            self.assertTrue(lane.bootstrap_pending)
        finally:
            call.closed = True
            running.cancel()
            opening.cancel()
            await asyncio.gather(running, opening, return_exceptions=True)
            await lane.close()

    async def test_fallback_diagnostic_uses_owned_call_and_only_safe_reason_enum(self):
        for branch, reason in (('prior_failure', 'model_failed'), ('busy_result', 'controller_busy'),
                               ('busy_exception', 'controller_busy'), ('unavailable', 'unavailable')):
            with self.subTest(branch=branch):
                call = self.call()
                call.call_id = 'owned-static-help-call'
                class FailedConversation(Conversation):
                    controller_transport = SimpleNamespace(transient_busy=branch.startswith('busy'))
                    async def respond(self, raw, snapshot, key):
                        if branch in ('busy_exception', 'unavailable'):
                            raise RuntimeError('private-exception-content')
                        return SimpleNamespace(failure='private-provider-detail')
                conversation = FailedConversation()
                async def factory(*args):
                    conversation.output_epoch = lane.epoch
                    return conversation
                lane = NativeDuplex(call, conversation_factory=factory)
                lane._bootstrap_state = 'pending'
                lane._model_failed = branch == 'prior_failure'
                turn = (0, 'private-user-prompt', 1, 'private-turn-id', 0)
                with self.assertLogs('native-voice', level='INFO') as captured:
                    await lane._general_help(turn, lane.epoch)
                diagnostics = [line.split(':', 2)[-1] for line in captured.output
                               if ' stage=fallback ' in line]
                self.assertEqual(diagnostics, [
                    'Voice independent help call=owned-static-help-call stage=fallback reason=' + reason])
                self.assertNotIn('private-', '\n'.join(captured.output))
                self.assertEqual(len(lane._outputs), 1)

    async def test_local_worker_error_boundary_retains_help_and_status_guard_policy(self):
        class OnceFailingDialog(Dialog):
            def __getattribute__(self, name):
                if name == 'current_question' and self.fail_once:
                    self.fail_once = False
                    raise RuntimeError('private-observation-error')
                return super().__getattribute__(name)
        for kind in ('help', 'status'):
            with self.subTest(kind=kind):
                call = self.call()
                call.dialog = OnceFailingDialog(call.config)
                call.dialog.fail_once = True
                lane = NativeDuplex(call)
                lane._model_failed = True
                turn = (0, 'Was kannst du für mich tun?', 1, 'help-turn', 0)
                lane._local_questions.put_nowait((turn, kind, lane.epoch))
                worker = asyncio.create_task(lane._local_loop())
                try:
                    with self.assertLogs('native-voice', level='WARNING'):
                        await asyncio.wait_for(lane._local_questions.join(), 1)
                    self.assertFalse(worker.done(), 'The local fallback error boundary killed its worker')
                    self.assertEqual(len(lane._outputs), 1)
                    item = lane._outputs[0]
                    self.assertEqual(item.kind, 'local' if kind == 'help' else 'status')
                    progress(call.dialog)
                    self.assertEqual(lane._valid(item), kind == 'help')
                finally:
                    call.closed = True
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
