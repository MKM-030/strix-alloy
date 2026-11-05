"""CPU reproduction with real Dialog dispatch and a synthetic delayed model."""
import asyncio
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
from native_bridge import Config, Dialog
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall
from test_native_duplex_pending_context import Model, REPLY


class DispatchBoundaryRepro(unittest.IsolatedAsyncioTestCase):
    async def test_answered_inputtext_retirement_preserves_current_optional_reply(self):
        call, model = FakeCall(), Model()
        dialog = call.dialog = Dialog(Config())
        dialog.business_request_id = 'a' * 32
        dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId=dialog.business_request_id, controlType='InputText',
            label='Wie lautet der Name des neuen Mitarbeiters?')
        lane = NativeDuplex(call)
        lane._bootstrap_state = 'ready'
        lane._request = 1
        ready_entered, ready_release, posted, public_release = (asyncio.Event() for _ in range(4))
        requests, captures = [], []
        original_signature = lane._dialogue_signature

        def signature(snapshot, key):
            captures.append(dict(snapshot=copy.deepcopy(snapshot), key=copy.deepcopy(key),
                                 input_boundary=copy.deepcopy(dialog.input_boundary)))
            return original_signature(snapshot, key)
        lane._dialogue_signature = signature

        async def ready(*args):
            ready_entered.set()
            await ready_release.wait()

        async def request(method, path, **kwargs):
            requests.append((method, path))
            if method == 'POST':
                posted.set()
                return {'accepted': True, 'businessRequestId': 'c' * 32}
            await public_release.wait()
            raise AssertionError('No backend reply is allowed in this reproduction')
        dialog.request = request
        turn = (0, 'Ich brauche einen Laptop für Marcel Käfke, Lieferung nach Hamburg.', 2, 'b' * 32, 0)
        tasks = []
        with patch('native_bridge.require_model_ready', side_effect=ready):
            try:
                await lane._accept(turn)
                dispatched = lane._pending.popleft()
                model.output_epoch = lane.epoch
                lane.conversation = model
                # Match run(): the local Queue waiter is already runnable when
                # the newly created business task receives its first timeslice.
                help_task = asyncio.create_task(lane._general_help(turn, lane.epoch))
                business = asyncio.create_task(lane._business(dispatched))
                lane._backend = business
                speaker = asyncio.create_task(lane._speak_loop())
                tasks.extend((help_task, business, speaker))
                await asyncio.wait_for(model.started.wait(), .5)
                await asyncio.wait_for(ready_entered.wait(), .5)
                self.assertIsNotNone(captures[0]['input_boundary'])
                self.assertIsNone(dialog.input_boundary)
                ready_release.set()
                await asyncio.wait_for(posted.wait(), .5)
                model.release.set()
                await asyncio.wait_for(help_task, .5)
                await asyncio.sleep(.01)
                def without_revision(value):
                    if isinstance(value, dict):
                        return {k: without_revision(v) for k, v in value.items() if k != 'observation_revision'}
                    if isinstance(value, (tuple, list)):
                        return [without_revision(v) for v in value]
                    return value
                before, after = map(without_revision, (captures[0], captures[-1]))
                changed = [key for key in before if before[key] != after[key]]
                self.assertEqual(changed, ['input_boundary'])
                self.assertEqual(dialog.public_replies, [])
                self.assertEqual(sum(method == 'POST' for method, _ in requests), 1)
                self.assertIn(REPLY, call.spoken,
                    'Only the answered prior InputText was retired; no new public reply or control arrived')
            finally:
                call.closed = True
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await lane.close()




class RetirementOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.dialog = self.call.dialog = Dialog(Config())
        self.dialog.business_request_id = 'a' * 32
        self.original = dict(source='servicenow_input_control',
            businessRequestId='a' * 32, controlType='InputText',
            label='Wie lautet der Name des neuen Mitarbeiters?')
        self.dialog.input_boundary = self.original
        self.lane = NativeDuplex(self.call)
        self.lane._request = 1
        self.turn = (0, 'Der Laptop ist für Mara Testfeld.', 2, 'b' * 32, 0)
        await self.lane._accept(self.turn)
        self.lane._pending.popleft()
        self.lane._backend = asyncio.get_running_loop().create_future()
        self.binding = self.capture()

    async def asyncTearDown(self):
        self.call.closed = True
        self.lane._backend.cancel()
        self.lane._backend = None
        await self.lane.close()

    def capture(self):
        return self.lane._dialogue_snapshot(self.turn, self.lane.epoch)[2]

    def publish(self, **changes):
        boundary = dict(self.original, **changes)
        label = boundary.pop('label')
        self.dialog.observe_state(dict(busy=False, inputBoundary=boundary, inputLabel=label))
        self.assertIsNot(self.dialog.input_boundary, self.original)

    async def test_dispatch_retirement_alone_preserves_observation(self):
        self.assertIs(self.dialog.input_boundary, self.original)
        _, prompt, _ = self.lane._dialogue_snapshot(self.turn, self.lane.epoch)
        self.assertNotIn('accepted_inputtext_retirement', repr(prompt))
        self.dialog.input_boundary = None
        self.assertTrue(self.lane._observation_current(self.binding))

    async def test_same_shaped_same_word_new_publication_invalidates(self):
        self.dialog.input_boundary = None
        self.publish()
        self.assertEqual(self.dialog.input_boundary, self.original)
        self.assertFalse(self.lane._observation_current(self.binding),
            'A fresh publication remains authoritative even with identical text and fields')

    async def test_same_word_new_request_invalidates(self):
        self.dialog.input_boundary = None
        self.publish(businessRequestId='c' * 32)
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_new_backend_owner_invalidates(self):
        self.dialog.input_boundary = None
        self.dialog.backend_owner = object()
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_boolean_and_choice_controls_invalidate(self):
        for control_type in ('Boolean', 'Picker', 'TopicPickerControl'):
            with self.subTest(control_type=control_type):
                self.publish(controlType=control_type)
                self.assertFalse(self.lane._observation_current(self.binding))

    async def test_changed_label_invalidates(self):
        self.publish(label='An welche Adresse soll geliefert werden?')
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_mutated_original_boundary_invalidates(self):
        self.original['label'] = 'Ein neues Datum?'
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_raw_correction_invalidates(self):
        self.lane._observe_raw('Korrektur, nach Berlin.')
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_epoch_change_invalidates(self):
        self.lane.epoch += 1
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_terminal_change_invalidates(self):
        self.dialog.conversation_ended = True
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_second_accepted_raw_turn_invalidates(self):
        await self.lane._accept((0, 'Korrektur, nach Berlin.', 3, 'd' * 32, 0))
        self.assertFalse(self.lane._observation_current(self.binding))

    async def test_mismatched_initial_request_does_not_gain_retirement_equivalence(self):
        self.dialog.business_request_id = 'c' * 32
        self.lane._queue_business_input(self.turn)
        self.lane._pending.popleft()
        binding = self.capture()
        self.dialog.input_boundary = None
        self.assertFalse(self.lane._observation_current(binding))

    async def test_missing_initial_backend_owner_does_not_gain_retirement_equivalence(self):
        self.dialog.backend_owner = None
        self.lane._queue_business_input(self.turn)
        self.lane._pending.popleft()
        binding = self.capture()
        self.dialog.input_boundary = None
        self.assertFalse(self.lane._observation_current(binding))

    async def test_stale_polar_inputtext_is_held_without_post_or_retirement_equivalence(self):
        self.original['label'] = 'Soll ich den Laptop bestellen?'
        polar_turn = (0, 'Ja.', 3, 'd' * 32, 0)
        self.lane._queue_business_input(polar_turn)
        self.lane._pending.popleft()
        binding = self.lane._dialogue_snapshot(polar_turn, self.lane.epoch)[2]
        self.dialog.turn = AsyncMock()
        await self.lane._business(polar_turn)
        self.dialog.turn.assert_not_awaited()
        self.assertIs(self.dialog.input_boundary, self.original)
        self.assertIsNone(self.lane._answered_inputtext)
        self.dialog.input_boundary = None
        self.assertFalse(self.lane._observation_current(binding))


    async def test_fresh_same_shaped_publication_then_clear_never_resurrects(self):
        self.publish()
        self.assertFalse(self.lane._observation_current(self.binding))
        self.dialog.input_boundary = None
        self.assertFalse(self.lane._observation_current(self.binding))




if __name__ == '__main__':
    unittest.main()
