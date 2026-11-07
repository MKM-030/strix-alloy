"""CPU-only active-context checks with the real Dialog.turn dispatch ordering."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_bridge import Config, Dialog
from native_duplex import NativeDuplex, _PublicFinding
from test_native_duplex import FakeCall
from test_native_duplex_pending_context import Model, REPLY


class ActiveContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call, self.model = FakeCall(), Model()
        self.dialog = self.call.dialog = Dialog(Config())
        self.now = 100.0
        self.lane = NativeDuplex(self.call, clock=lambda: self.now)
        self.lane._bootstrap_state = 'ready'
        self.lane._request = 1
        self.ready_entered, self.ready_release = asyncio.Event(), asyncio.Event()
        self.posted, self.public_release = asyncio.Event(), asyncio.Event()
        self.requests, self.public_responses = [], 0

        async def ready(*args):
            self.ready_entered.set()
            await self.ready_release.wait()

        async def request(method, path, **kwargs):
            self.requests.append((method, path))
            if method == 'POST':
                self.posted.set()
                return {'accepted': True, 'businessRequestId': 'a' * 32}
            await self.public_release.wait()
            self.public_responses += 1
            raise AssertionError('This regression must finish before public callbacks')

        self.dialog.request = request
        patcher = patch('native_bridge.require_model_ready', side_effect=ready)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.turn = (0, 'Der Laptop ist für Mara Testfeld und soll nach Hamburg geliefert werden.',
                     2, 'b' * 32, 0)
        await self.lane._accept(self.turn)
        self.business = asyncio.create_task(self.lane._business(self.lane._pending.popleft()))
        self.lane._backend = self.business
        await asyncio.wait_for(self.ready_entered.wait(), .5)
        self.model.output_epoch = self.lane.epoch
        self.lane.conversation = self.model
        self.help = asyncio.create_task(self.lane._general_help(self.turn, self.lane.epoch))
        self.speaker = asyncio.create_task(self.lane._speak_loop())
        await asyncio.wait_for(self.model.started.wait(), .5)

    async def asyncTearDown(self):
        self.call.closed = True
        for task in (self.help, self.business, self.speaker):
            task.cancel()
        await asyncio.gather(self.help, self.business, self.speaker, return_exceptions=True)
        await self.lane.close()

    def snapshot(self):
        return self.lane._dialogue_snapshot(self.turn, self.lane.epoch)

    def signature(self):
        key, snapshot, _ = self.snapshot()
        return self.lane._dialogue_signature(snapshot, key)

    def progress(self, revision, label):
        self.dialog.observe_state({'processing': {
            'source': 'servicenow_processing', 'agentCompletionKnown': False,
            'revision': revision, 'messages': [label], 'ageSeconds': 0}}, sampled_at=self.now)

    async def test_dispatch_only_revision_preserves_active_sentence_before_any_callback(self):
        _, before, _ = self.snapshot()
        fingerprint = self.signature()
        self.assertFalse(self.lane._pending)
        self.assertIsNone(self.dialog.input_boundary)
        self.ready_release.set()
        await asyncio.wait_for(self.posted.wait(), .5)
        _, after, _ = self.snapshot()
        self.assertEqual([key for key in before if before[key] != after[key]], ['observation_revision'])
        self.assertEqual(self.signature(), fingerprint)
        self.assertEqual(self.public_responses, 0)
        self.assertEqual(self.dialog.public_replies, [])
        self.model.release.set()
        await asyncio.wait_for(self.help, .5)
        await asyncio.sleep(.01)
        self.assertIn(REPLY, self.call.spoken,
                      'Dispatch bookkeeping must not cancel an unchanged current local response')

    async def test_progress_clock_and_label_are_advisory_but_remain_in_prompt(self):
        self.progress(1, 'Verfügbarkeit wird geprüft')
        _, before, binding = self.snapshot()
        fingerprint = self.signature()
        self.assertTrue(any(item['source_event'] == 'servicenow_processing_presentation'
                            for item in before['public_findings']))
        self.now += 1
        self.assertEqual(self.signature(), fingerprint, 'Recomputed processing observed_at is advisory')
        self.progress(2, 'Angaben werden zugeordnet')
        _, after, _ = self.snapshot()
        self.assertTrue(any(item['text'] == 'Angaben werden zugeordnet' for item in after['public_findings']))
        self.assertEqual(self.signature(), fingerprint)
        self.assertTrue(self.lane._observation_current(binding))

    async def test_genuine_public_finding_invalidates_active_observation(self):
        _, _, binding = self.snapshot()
        self.lane._reply_revision = self.lane.task_revision
        self.lane._public_findings.append(_PublicFinding(self.lane._request, self.lane.task_revision,
            1, self.now, 'Die Lieferung ist nur nach Berlin möglich.'))
        # Deliberately leave the generic revision counter unchanged.
        self.assertFalse(self.lane._observation_current(binding))

    async def test_control_boundary_installation_and_clearing_both_invalidate(self):
        _, _, binding = self.snapshot()
        self.dialog.input_boundary = {'source': 'servicenow_input_control',
            'businessRequestId': 'c' * 32, 'controlType': 'Boolean', 'label': 'Freigeben?'}
        self.assertFalse(self.lane._observation_current(binding))
        _, _, with_boundary = self.snapshot()
        self.dialog.input_boundary = None
        self.assertFalse(self.lane._observation_current(with_boundary))

    async def test_owner_raw_question_scope_and_terminal_changes_remain_invalidating(self):
        changes = [
            (self.dialog, 'backend_owner', object()),
            (self.dialog, 'conversation_ended', True),
            (self.lane, '_backend_unavailable', True),
            (self.lane, 'epoch', self.lane.epoch + 1),
            (self.lane, 'task_revision', self.lane.task_revision + 1),
            (self.lane, 'context_revision', self.lane.context_revision + 1),
            (self.lane, 'question_context', lambda: ('Welches Datum?', 'servicenow_input_control', True)),
        ]
        for owner, field, changed in changes:
            _, _, binding = self.snapshot()
            original = getattr(owner, field)
            with self.subTest(field=field):
                setattr(owner, field, changed)
                self.assertFalse(self.lane._observation_current(binding))
            setattr(owner, field, original)
        _, _, binding = self.snapshot()
        await self.lane._accept((self.call.playback.generation, 'Korrektur, nach Berlin.',
                                 99, 'f' * 32, 0))
        self.assertFalse(self.lane._observation_current(binding))

    async def test_pending_transfer_keeps_its_separate_guard(self):
        self.lane._pending.append(self.turn)
        _, _, pending = self.snapshot()
        self.assertTrue(self.lane._observation_current(pending))
        self.lane._pending.popleft()
        self.assertFalse(self.lane._observation_current(pending))

    async def test_progress_output_expiry_remains_thirty_seconds(self):
        self.progress(1, 'Verfügbarkeit wird geprüft')
        text, expiry = self.lane._automatic_update()
        self.assertIn('Verfügbarkeit wird geprüft', text)
        self.assertEqual(expiry, self.now + 30)
        self.now += 31
        self.assertEqual(self.lane._automatic_update(), (None, None))


if __name__ == '__main__':
    unittest.main()
