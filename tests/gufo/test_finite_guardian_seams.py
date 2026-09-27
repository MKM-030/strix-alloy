import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gufo_control import smoke_guard as guard, service_ipc as ipc
from test_smoke_guard import Harness


class GuardianSeamTests(unittest.TestCase):
    def test_default_hooks_leave_smoke_profile_unchanged(self):
        value = guard._Guardian()
        self.assertEqual(value._prepared_recheck_kwargs(), {})
        self.assertIsNone(value._before_begin(object()))
        self.assertFalse(value._immutable_terminal())
        life = object.__new__(ipc._IpcLifecycle)
        self.assertTrue(life._authorize_event({'command': 'stop'}))
        self.assertEqual(life._handoff_fields(), {})

    def test_admission_hook_runs_before_begin_and_create(self):
        base = guard._Guardian
        events = []
        class Hooked(base):
            def _before_begin(self, frame):
                events.append(('admitted', frame, self.current, self.child))
        with tempfile.TemporaryDirectory() as root:
            harness = Harness(root)
            original = harness.store.begin_run
            def begin(*args):
                events.append(('begin',))
                return original(*args)
            harness.store.begin_run = begin
            with patch.object(guard, '_Guardian', Hooked):
                result = harness.run()
            self.assertTrue(result['success'], result)
            self.assertEqual([event[0] for event in events], ['admitted', 'begin'])
            self.assertIsNotNone(events[0][1])
            self.assertIsNotNone(events[0][2])
            self.assertIsNone(events[0][3])
            self.assertEqual(harness.events.count('create'), 1)
            self.assertEqual(result['recovery_samples'], 5)

    def test_hook_refusal_cannot_create_or_consume_attempt(self):
        base = guard._Guardian
        class Refusing(base):
            def _before_begin(self, frame):
                raise ValueError('synthetic_admission_record_failure')
        with tempfile.TemporaryDirectory() as root:
            harness = Harness(root)
            with patch.object(guard, '_Guardian', Refusing):
                result = harness.run()
            self.assertFalse(result['success'])
            self.assertEqual(harness.children, [])
            self.assertNotIn('begin', harness.events)

    def test_immutable_failure_keeps_prior_terminal_bytes(self):
        class Immutable(guard._Guardian):
            def _immutable_terminal(self):
                return True
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / 'run-1'
            run.mkdir()
            terminal = run / 'result.json'
            terminal.write_bytes(b'{"original":true}\n')
            value = Immutable(store=SimpleNamespace(EVIDENCE=Path(root)))
            value.run_dir = run
            result = value._terminal_failure(ValueError('publication_failed'))
            self.assertFalse(result['success'])
            self.assertEqual(terminal.read_bytes(), b'{"original":true}\n')
            self.assertEqual(len(list(run.glob('result-failure-*.json'))), 1)
            self.assertTrue((Path(root) / 'incomplete.json').exists())
