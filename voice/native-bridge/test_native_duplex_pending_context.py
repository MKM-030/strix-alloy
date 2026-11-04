"""Old business callbacks must not invalidate a semantically unchanged new input."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall

REPLY = 'Wir können die nächsten Angaben gemeinsam klären.'


class Model:
    sentence_streaming = True
    output_epoch = 1
    def __init__(self):
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.observations, self.reject = [], False
        self.scope = self.bound = None
        self.identity = SimpleNamespace(server_session_id='offline-session')
    async def invalidate(self, epoch, reason): self.output_epoch = epoch
    async def observe(self, snapshot, key):
        self.observations.append((snapshot, key))
        self.scope = key['observation_revision']
        return not self.reject
    async def respond(self, raw, snapshot, key, *, on_sentence):
        self.scope = self.bound = key['observation_revision']
        self.started.set()
        await self.release.wait()
        try: await on_sentence(SimpleNamespace(text=REPLY, identity=self.identity))
        except ValueError: return SimpleNamespace(failure='output_callback_failed', text='', identity=self.identity)
        return SimpleNamespace(failure=None, text=REPLY, identity=self.identity)
    def is_current(self, identity): return identity is self.identity and self.scope == self.bound
    async def close(self): pass


class PendingContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call, self.model = FakeCall(), Model()
        self.lane = NativeDuplex(self.call)
        q1 = (0, 'Erste Frage.', 1, 'q1', 0)
        self.lane._observe_raw(q1[1])
        self.business = asyncio.create_task(self.lane._business(q1))
        self.lane._backend = self.business
        await self.call.dialog.started.get()
        self.q2 = (0, 'Welche Angaben fehlen noch?', 2, 'q2', 1)
        await self.lane._accept(self.q2)
        self.model.output_epoch = self.lane.epoch
        self.lane.conversation = self.model
        self.help = asyncio.create_task(self.lane._general_help(self.q2, self.lane.epoch))
        self.speaker = asyncio.create_task(self.lane._speak_loop())
        await self.model.started.wait()
    async def asyncTearDown(self):
        self.call.closed = True
        for task in (self.help, self.business, self.speaker): task.cancel()
        await asyncio.gather(self.help, self.business, self.speaker, return_exceptions=True)
        await self.lane.close()
    async def until(self, predicate):
        async with asyncio.timeout(.5):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)
    async def drain_observations(self):
        if self.lane._observations: await asyncio.gather(*tuple(self.lane._observations))
    async def test_hidden_old_reply_preserves_new_answer_and_never_observes_equal_context(self):
        _, before, _ = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.call.dialog.release.put_nowait('Diese Rückmeldung gehört zur ersten Frage.')
        await self.business
        await self.drain_observations()
        _, after, _ = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.assertEqual([key for key in before if before[key] != after[key]], ['observation_revision'])
        self.assertEqual(self.model.observations, [])
        self.model.release.set()
        await self.help
        await self.until(lambda: REPLY in self.call.spoken)
        self.assertEqual(self.call.dialog.calls, ['Erste Frage.'])
        self.assertEqual([turn[3] for turn in self.lane._pending], ['q2'])
    async def test_hidden_native_control_change_still_invalidates_pending_binding(self):
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='new-control', controlType='InputText', label='Neue Frage?')
        self.assertFalse(self.lane._observation_current(binding))
    async def test_caller_and_pending_dispatch_changes_invalidate_binding(self):
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        await self.lane._accept((0, 'Zusätzliche Angabe.', 3, 'q3', 2))
        self.assertFalse(self.lane._observation_current(binding))
        _, _, current = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.lane._pending.clear()
        self.assertFalse(self.lane._observation_current(current))
    async def test_closed_and_unavailable_business_state_invalidates_binding(self):
        for field in ('conversation_ended',):
            _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
            setattr(self.call.dialog, field, True)
            self.assertFalse(self.lane._observation_current(binding))
            setattr(self.call.dialog, field, False)
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.lane._backend_unavailable = True
        self.assertFalse(self.lane._observation_current(binding))
    async def test_own_emitted_history_does_not_invalidate_or_schedule_observe(self):
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.lane._spoken_history.append(dict(text='Vorige hörbare Antwort.', sequence=1, observed_at=1))
        self.assertTrue(self.lane._observation_current(binding))
        self.lane._queue_dialogue_observation()
        await self.drain_observations()
        self.assertEqual(self.model.observations, [])
    async def test_identical_scheduled_updates_coalesce_and_failed_update_can_be_retried(self):
        self.model.reject = True
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='new-control', controlType='InputText', label='Neue Frage?')
        self.lane._queue_dialogue_observation()
        self.lane._queue_dialogue_observation()
        await self.drain_observations()
        self.assertEqual(len(self.model.observations), 1)
        self.model.reject = False
        self.lane._queue_dialogue_observation()
        await self.drain_observations()
        self.assertEqual(len(self.model.observations), 2)
    async def test_unmasked_context_keeps_strict_raw_revision_guard(self):
        self.lane._pending.clear()
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.call.dialog.observation_revision += 1
        self.assertFalse(self.lane._observation_current(binding))

    async def test_same_pending_count_with_different_input_identity_invalidates_binding(self):
        _, _, binding = self.lane._dialogue_snapshot(self.q2, self.lane.epoch)
        self.lane._pending[0] = (0, self.q2[1], 2, 'different-input', 1)
        self.assertFalse(self.lane._observation_current(binding))

    async def test_old_failed_observation_cannot_clear_new_matching_signature(self):
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def observe(snapshot, key):
            calls.append(self.call.dialog.input_boundary['label'])
            if len(calls) == 1:
                started.set()
                await release.wait()
                return False
            return True
        self.model.observe = observe
        def control(label):
            self.call.dialog.input_boundary = dict(source='servicenow_input_control',
                businessRequestId='control', controlType='InputText', label=label)
        control('A'); self.lane._queue_dialogue_observation(); await started.wait()
        control('B'); self.lane._queue_dialogue_observation(); await asyncio.sleep(.01)
        control('A'); self.lane._queue_dialogue_observation(); await asyncio.sleep(.01)
        current = self.lane._dialogue_observation_state
        release.set(); await self.drain_observations()
        self.assertIs(self.lane._dialogue_observation_state, current)
        self.lane._queue_dialogue_observation(); await self.drain_observations()
        self.assertEqual(calls, ['A', 'B', 'A'])

    async def test_cancelled_observation_does_not_permanently_suppress_its_context(self):
        started = asyncio.Event()
        async def observe(snapshot, key):
            started.set()
            await asyncio.Event().wait()
        self.model.observe = observe
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='control', controlType='InputText', label='A')
        self.lane._queue_dialogue_observation(); await started.wait()
        tasks = tuple(self.lane._observations)
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertIsNone(self.lane._dialogue_observation_state)

    async def test_observation_cancelled_before_start_releases_its_scheduled_signature(self):
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='control', controlType='InputText', label='A')
        self.lane._queue_dialogue_observation()
        tasks = tuple(self.lane._observations)
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertIsNone(self.lane._dialogue_observation_state)


if __name__ == '__main__': unittest.main()
