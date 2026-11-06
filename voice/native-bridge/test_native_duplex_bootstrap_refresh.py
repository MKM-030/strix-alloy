"""Model-free readiness race: stale speech stays rejected; one current refresh."""
import asyncio
from collections import deque
from types import SimpleNamespace
import unittest

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


OLD = 'Wir können das Anliegen gemeinsam besprechen.'
FRESH = 'Für den Laptop fehlen noch das Eintrittsdatum und die Führungskraft.'
RAW = 'Der Laptop ist für Mara Testfeld und soll nach Hamburg geliefert werden.'


class Conversation:
    sentence_streaming = True
    output_epoch = 2

    def __init__(self):
        self.inputs = []
        self.started = [asyncio.Event(), asyncio.Event()]
        self.release = [asyncio.Event(), asyncio.Event()]
        self.release[1].set()
        self.first_sentence = False
        self.first_failure = 'superseded'
        self.identity = SimpleNamespace(server_session_id='model-free-source')

    async def invalidate(self, epoch, reason):
        self.output_epoch = epoch

    async def observe(self, snapshot, key):
        return True

    async def respond(self, raw, snapshot, key, *, on_sentence):
        index = len(self.inputs)
        self.inputs.append((raw, snapshot, key))
        if index >= 2:
            raise AssertionError('A caller may not receive a third automatic model attempt')
        self.started[index].set()
        if index == 0 and self.first_sentence:
            await on_sentence(SimpleNamespace(text=OLD, identity=self.identity))
        await self.release[index].wait()
        if index == 1:
            try:
                await on_sentence(SimpleNamespace(text=FRESH, identity=self.identity))
            except ValueError:
                return SimpleNamespace(text='', failure='output_callback_failed', identity=self.identity)
        return SimpleNamespace(text='', failure=self.first_failure if index == 0 else None,
                               identity=self.identity)

    def is_current(self, identity):
        return identity is self.identity

    async def close(self):
        pass


class CancellableConversation(Conversation):
    """A blocked model with explicit owned cancellation and session retirement."""
    def __init__(self, reply, *, blocked=True):
        super().__init__()
        self.reply, self.blocked = reply, blocked
        self.active = self._closed = False
        self.cancelled, self.cleanup_release = asyncio.Event(), asyncio.Event()
        self.cleanup_release.set()

    async def respond(self, raw, snapshot, key, *, on_sentence):
        if self._closed or self.active:
            raise AssertionError('A retired or busy model session cannot be reused')
        self.inputs.append((raw, snapshot, key))
        self.active = True
        self.started[0].set()
        try:
            if self.first_sentence:
                await on_sentence(SimpleNamespace(text=self.reply, identity=self.identity))
            if self.blocked:
                await self.release[0].wait()
            if not self.first_sentence:
                await on_sentence(SimpleNamespace(text=self.reply, identity=self.identity))
            return SimpleNamespace(text=self.reply, failure=None, identity=self.identity)
        except asyncio.CancelledError:
            self.cancelled.set()
            await self.cleanup_release.wait()
            raise
        finally:
            self.active = False

    async def close(self):
        if self.active:
            raise AssertionError('The owned generation must settle before session close')
        self._closed = True


class BootstrapRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call, self.model = FakeCall(), Conversation()
        self.call.dialog.conversation_ended = False
        async def factory(*args):
            return self.model
        self.lane = NativeDuplex(self.call, conversation_factory=factory)
        self.lane._bootstrap_state = 'pending'
        self.lane.epoch = 2
        self.first = (0, 'Hörst du mich?', 1, 'a' * 32, 10)
        self.turn = (0, RAW, 2, 'b' * 32, 20)
        self.lane._pending = deque((self.first, self.turn))
        self.lane._raw.extend((self.first[1], RAW))
        self.lane.context_revision = 3
        self.lane._local_busy = True
        self.speaker = asyncio.create_task(self.lane._speak_loop())
        self.help = None

    async def asyncTearDown(self):
        self.call.closed = True
        if isinstance(self.model, CancellableConversation):
            self.model.cleanup_release.set()
        for task in (self.help, self.speaker):
            if task is not None:
                task.cancel()
        await asyncio.gather(*(task for task in (self.help, self.speaker) if task is not None),
                             return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(.5):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def start(self):
        self.help = asyncio.create_task(self.lane._general_help(self.turn, self.lane.epoch))
        await asyncio.wait_for(self.model.started[0].wait(), .5)

    def ready(self):
        opening = asyncio.get_running_loop().create_future()
        opening.set_result([])
        self.lane._settle_bootstrap(opening)

    async def finish(self):
        self.model.release[0].set()
        await asyncio.wait_for(self.help, .5)

    def cancellable_models(self):
        old = self.model = CancellableConversation(OLD)
        fresh = CancellableConversation(FRESH, blocked=False)
        async def factory(*args):
            if not old.inputs:
                return old
            if not old._closed:
                raise AssertionError('A new session must wait for retirement of its predecessor')
            return fresh
        self.lane._factory = factory
        return old, fresh

    async def test_readiness_cancels_blocked_generation_before_completion_and_reopens_once(self):
        old, fresh = self.cancellable_models()
        await self.start()
        self.ready()
        try:
            await self.until(lambda: FRESH in self.call.spoken)
        except TimeoutError:
            self.fail('Readiness left the local generation blocked on stale model completion')
        await asyncio.wait_for(self.help, .5)
        self.assertTrue(old.cancelled.is_set())
        self.assertTrue(old._closed)
        self.assertFalse(old.release[0].is_set(), 'Readiness must not wait for stale completion')
        self.assertNotIn(OLD, self.call.spoken)
        self.assertEqual(self.call.spoken.count(FRESH), 1)
        self.assertEqual([raw for model in (old, fresh) for raw, _, _ in model.inputs], [RAW, RAW])
        self.assertEqual(old.inputs[0][2]['request_id'], fresh.inputs[0][2]['request_id'])
        self.assertEqual(tuple(self.lane._pending), (self.first, self.turn))
        self.assertEqual(self.call.dialog.calls, [])

    async def test_readiness_during_started_pcm_finishes_sentence_without_cancelling_model(self):
        old, fresh = self.cancellable_models()
        old.first_sentence = True
        next_pcm = asyncio.Event()
        async def speech(text):
            self.call.spoken.append(text)
            yield bytes(480)
            await next_pcm.wait()
            yield bytes(480)
        self.call.speech.synthesize = speech
        await self.start()
        await self.until(lambda: self.call.playback.accepted_samples == 240)
        self.ready()
        next_pcm.set()
        await self.until(lambda: not self.call.synthesis_active)
        self.assertEqual(self.call.playback.accepted_samples, 480)
        self.assertTrue(self.lane._speech['complete'])
        self.assertFalse(old.cancelled.is_set())
        self.assertEqual(fresh.inputs, [])
        await self.finish()
        self.assertEqual(self.call.spoken, [OLD])

    async def test_caller_change_during_cancel_cleanup_prevents_stale_refresh(self):
        old, fresh = self.cancellable_models()
        old.cleanup_release.clear()
        await self.start()
        self.ready()
        try:
            await asyncio.wait_for(old.cancelled.wait(), .5)
        except TimeoutError:
            self.fail('Readiness never cancelled the blocked local generation')
        self.assertEqual(fresh.inputs, [])
        self.lane.epoch += 1
        old.cleanup_release.set()
        await asyncio.wait_for(self.help, .5)
        self.assertFalse(old.active)
        self.assertTrue(old._closed)
        self.assertEqual(fresh.inputs, [])
        self.assertEqual(self.call.spoken, [])

    async def test_cancelling_local_owner_drains_blocked_model_and_readiness_wait(self):
        old, fresh = self.cancellable_models()
        existing_tasks = asyncio.all_tasks()
        await self.start()
        self.help.cancel()
        await asyncio.gather(self.help, return_exceptions=True)
        self.assertTrue(old.cancelled.is_set())
        self.assertFalse(old.active)
        self.assertFalse([task for task in asyncio.all_tasks()
                          if task not in existing_tasks and not task.done()])
        self.ready()
        await asyncio.sleep(0)
        self.assertEqual(fresh.inputs, [])
        self.assertEqual(self.call.spoken, [])

    async def test_refresh_connection_shares_the_original_attempt_deadline(self):
        old, fresh = self.cancellable_models()
        async def factory(*args):
            if not old.inputs:
                return old
            await asyncio.Event().wait()
            return fresh
        self.lane._factory = factory
        deadline = asyncio.get_running_loop().time() + .1
        self.help = asyncio.create_task(self.lane._general_help_attempt(
            self.turn, self.lane.epoch, 'help', refresh_bootstrap=True, deadline=deadline))
        await asyncio.wait_for(old.started[0].wait(), .5)
        self.ready()
        self.assertTrue(await asyncio.wait_for(self.help, .5))
        self.help = asyncio.create_task(self.lane._general_help_attempt(
            self.turn, self.lane.epoch, 'help', refresh_bootstrap=False, deadline=deadline))
        try:
            await asyncio.wait_for(asyncio.shield(self.help), .5)
        except TimeoutError:
            self.fail('The replacement connection escaped the original response deadline')
        self.assertEqual(fresh.inputs, [])
        self.assertTrue(self.lane._model_failed)

    async def test_ready_recomputes_once_from_fresh_snapshot_without_replaying_business_or_retiming_input(self):
        await self.start()
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 2, 'Readiness must not silently consume the only local reply')
        await self.until(lambda: FRESH in self.call.spoken)
        self.assertNotIn(OLD, self.call.spoken)
        self.assertEqual([raw for raw, _, _ in self.model.inputs], [RAW, RAW])
        old, fresh = self.model.inputs
        self.assertNotEqual(old[1]['capability_limits'], fresh[1]['capability_limits'])
        self.assertEqual(old[2]['request_id'], fresh[2]['request_id'])
        self.assertEqual(old[2]['output_epoch'], fresh[2]['output_epoch'])
        self.assertEqual(tuple(self.lane._pending), (self.first, self.turn))
        self.assertEqual(self.turn[-1], 20, 'The original ASR/onset clock is retained')
        self.assertEqual(self.call.dialog.calls, [])

    async def test_real_initial_inputtext_change_rejects_old_context_and_refreshes_only_current_snapshot(self):
        await self.start()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='c' * 32, label='Für welchen Mitarbeiter?')
        self.call.dialog.observation_revision += 1
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 2)
        self.assertEqual(self.model.inputs[1][2]['observation_revision'], 1)
        await self.until(lambda: FRESH in self.call.spoken)
        self.assertNotIn(OLD, self.call.spoken)

    async def test_already_started_sentence_is_not_duplicated_by_readiness_refresh(self):
        self.model.first_sentence = True
        await self.start()
        await self.until(lambda: self.turn[3] in self.lane._turn_speech_started)
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)
        self.assertEqual(self.call.spoken.count(OLD), 1)
        self.assertNotIn(FRESH, self.call.spoken)

    async def test_queued_but_unstarted_old_local_sentence_is_revoked_before_one_fresh_reply(self):
        self.call.vad_active = True
        self.model.first_sentence = True
        await self.start()
        await self.until(lambda: bool(self.lane._outputs))
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 2)
        self.call.vad_active = False
        await self.until(lambda: FRESH in self.call.spoken)
        self.assertNotIn(OLD, self.call.spoken)

    async def test_admitted_backend_replacement_prevents_local_refresh(self):
        self.call.vad_active = True
        await self.start()
        self.ready()
        self.lane._enqueue('Die fachliche Rückfrage liegt vor.', self.turn, kind='backend')
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)
        self.assertNotIn(FRESH, self.call.spoken)

    async def test_boolean_boundary_prevents_local_refresh_without_waiting_for_control_poll(self):
        await self.start()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='Boolean', businessRequestId='c' * 32, label='Sind die Angaben richtig?')
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)
        self.assertNotIn(FRESH, self.call.spoken)

    async def test_ended_backend_cannot_trigger_bootstrap_refresh(self):
        await self.start()
        self.ready()
        self.call.dialog.conversation_ended = True
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)

    async def test_unavailable_backend_cannot_trigger_bootstrap_refresh(self):
        await self.start()
        self.ready()
        self.lane._backend_unavailable = True
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)

    async def test_closed_backend_input_cannot_trigger_bootstrap_refresh(self):
        await self.start()
        self.ready()
        self.lane._backend_input_closed = True
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)

    async def test_active_backend_replacement_prevents_local_refresh_even_before_first_pcm(self):
        await self.start()
        self.ready()
        self.lane._enqueue('Die fachliche Rückfrage liegt vor.', self.turn, kind='backend')
        self.lane._active_output = self.lane._outputs.popleft()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)

    async def test_closed_model_source_cannot_receive_a_refresh(self):
        await self.start()
        self.ready()
        self.model._closed = True
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)

    async def test_new_caller_epoch_cannot_receive_automatic_old_caller_refresh(self):
        await self.start()
        self.ready()
        self.lane.epoch += 1
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)
        self.assertNotIn(FRESH, self.call.spoken)

    async def test_replaced_model_source_cannot_be_reopened_for_old_caller(self):
        await self.start()
        self.ready()
        self.lane.conversation = Conversation()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)
        self.assertEqual(self.lane.conversation.inputs, [])

    async def test_fresh_attempt_invalidated_again_is_discarded_without_a_third_attempt(self):
        self.model.release[1].clear()
        await self.start()
        self.ready()
        self.model.release[0].set()
        try:
            await self.until(lambda: self.model.started[1].is_set())
        except TimeoutError:
            self.fail('The single fresh attempt was never scheduled')
        self.lane.context_revision += 1
        self.lane._raw.append('Eine neue Angabe.')
        self.model.release[1].set()
        await asyncio.wait_for(self.help, .5)
        self.assertEqual(len(self.model.inputs), 2)
        self.assertNotIn(FRESH, self.call.spoken)

    async def test_terminal_model_failure_is_not_retried_as_readiness_refresh(self):
        self.model.first_failure = 'unavailable'
        await self.start()
        self.ready()
        await self.finish()
        self.assertEqual(len(self.model.inputs), 1)


if __name__ == '__main__':
    unittest.main()
