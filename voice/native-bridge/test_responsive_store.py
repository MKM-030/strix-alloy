"""Durability and ownership contract for responsive voice work."""

import tempfile
import sqlite3
import unittest
from pathlib import Path

from business_tasks import Agent, Scope, StoreCapacity, StoreConflict, StoreDenied, StoreInvalid
from task_store import TaskStore


class ResponsiveStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "tasks.sqlite3"
        self.store = TaskStore(self.path)
        self.scope = Scope("scope-1", "call-1", 1, "instance-1", "assistant-1")
        self.agent = Agent("helpdesk", "agent-1", "revision-1", {"continue_task": True})

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def task(self, *, scope=None):
        return self.store.create_task(scope or self.scope, self.agent, "Help with a request")

    def accepted(self, *, task=None, utterance="utterance-1", text="Please help"):
        task = task or self.task()
        return self.store.accept(task["task_id"], self.scope.scope_id, utterance, text)

    def test_accepted_text_and_version_survive_reopen(self):
        task = self.task()
        operation = self.accepted(task=task, text="  exact words!  ")
        self.assertEqual(operation["text"], "  exact words!  ")
        self.assertEqual(operation["context_version"], 1)
        self.store.close()
        self.store = TaskStore(self.path)
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 1)
        self.assertEqual(self.store.pending(self.scope.scope_id)[0]["text"], "  exact words!  ")
        self.assertEqual(len(self.store.events(task["task_id"], self.scope.scope_id)), 2)

    def test_same_utterance_different_text_conflicts_without_version_bump(self):
        task = self.task()
        first = self.accepted(task=task)
        duplicate = self.accepted(task=task)
        self.assertEqual(first["operation_id"], duplicate["operation_id"])
        with self.assertRaises(StoreConflict):
            self.accepted(task=task, text="different")
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 1)
        self.assertEqual(len(self.store.pending(self.scope.scope_id)), 1)

    def test_cross_scope_access_is_denied(self):
        task = self.task()
        with self.assertRaises(StoreDenied):
            self.store.get_task(task["task_id"], "scope-other")
        with self.assertRaises(StoreDenied):
            self.store.accept(task["task_id"], "scope-other", "u", "secret")
        with self.assertRaises(StoreDenied):
            self.store.events(task["task_id"], "scope-other")
        self.assertEqual(self.store.list_tasks("scope-other"), [])

    def test_duplicate_callback_is_recorded_once_and_conflicting_replay_fails(self):
        operation = self.accepted()
        self.assertTrue(self.store.observe(operation["operation_id"], "callback-1", "callback", {"answer": "A"}))
        self.assertFalse(self.store.observe(operation["operation_id"], "callback-1", "callback", {"answer": "A"}))
        with self.assertRaises(StoreConflict):
            self.store.observe(operation["operation_id"], "callback-1", "callback", {"answer": "B"})
        task_id = operation["task_id"]
        self.assertEqual([e["type"] for e in self.store.events(task_id, self.scope.scope_id)].count("callback"), 1)

    def test_callback_rejects_nested_case_separator_and_prefixed_credential_fields(self):
        operation = self.accepted()
        task_id = operation["task_id"]
        before = self.store.events(task_id, self.scope.scope_id)
        forbidden = (
            {"x-api-key": "placeholder"},
            {"meta": [{"AUTHORIZATION_Header": "placeholder"}]},
            {"callback": {"session-token-v2": "placeholder"}},
            {"headers": {"Set.Cookie": "placeholder"}},
            {"meta": {"clientSecretValue": "placeholder"}},
        )
        for index, payload in enumerate(forbidden):
            with self.subTest(index=index), self.assertRaises(StoreInvalid):
                self.store.observe(operation["operation_id"], f"blocked-{index}", "callback", payload)
        self.assertEqual(self.store.events(task_id, self.scope.scope_id), before)
        self.assertTrue(self.store.observe(operation["operation_id"], "safe-event", "callback", {"response": [{"status": "accepted"}]}))

    def test_settlement_rejects_credential_fields_without_persisting_result(self):
        operation = self.accepted()
        self.store.dispatch(operation["operation_id"])
        task_id = operation["task_id"]
        before = self.store.events(task_id, self.scope.scope_id)
        with self.assertRaises(StoreInvalid):
            self.store.settle(operation["operation_id"], replies=["Still working"], evidence={"details": [{"X_API.Key_Id": "placeholder"}]})
        self.assertEqual(self.store.events(task_id, self.scope.scope_id), before)
        self.assertEqual(self.store.get_task(task_id, self.scope.scope_id)["state"], "running")
        self.assertEqual(self.store.settle(operation["operation_id"], replies=["Still working"], evidence={"source": "legacy"})["state"], "awaiting_input")

    def test_callback_json_depth_and_node_limits_have_fixed_error(self):
        operation = self.accepted()
        nested = []
        for _ in range(1100):
            nested = [nested]
        for payload in (nested, [None] * 2100):
            with self.assertRaises(StoreInvalid):
                self.store.observe(operation["operation_id"], "oversized", "callback", payload)
        self.assertEqual([event["type"] for event in self.store.events(operation["task_id"], self.scope.scope_id)].count("callback"), 0)

    def test_event_sequence_is_monotonic_after_reopen(self):
        task = self.task()
        operation = self.accepted(task=task)
        self.store.dispatch(operation["operation_id"])
        before = self.store.events(task["task_id"], self.scope.scope_id)
        self.store.close()
        self.store = TaskStore(self.path)
        self.store.observe(operation["operation_id"], "callback-1", "callback", {"answer": "A"})
        after = self.store.events(task["task_id"], self.scope.scope_id)
        self.assertEqual([e["sequence"] for e in after], list(range(1, len(after) + 1)))
        self.assertEqual(after[:len(before)], before)
        self.assertEqual([e["sequence"] for e in self.store.events(task["task_id"], self.scope.scope_id, after=2)], [3, 4])

    def test_two_connections_enforce_pending_limit(self):
        task = self.task()
        other = TaskStore(self.path)
        try:
            for index in range(32):
                store = self.store if index % 2 else other
                store.accept(task["task_id"], self.scope.scope_id, f"u-{index}", "next")
            with self.assertRaises(StoreCapacity):
                other.accept(task["task_id"], self.scope.scope_id, "overflow", "too many")
            self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 32)
            self.assertEqual(len(self.store.pending(self.scope.scope_id)), 32)
        finally:
            other.close()

    def test_submitted_unsettled_utterance_counts_toward_scope_limit(self):
        task = self.task()
        first = self.store.accept(task["task_id"], self.scope.scope_id, "u-0", "first")
        self.store.dispatch(first["operation_id"])
        for index in range(1, 32):
            self.store.accept(task["task_id"], self.scope.scope_id, f"u-{index}", "next")
        with self.assertRaises(StoreCapacity):
            self.store.accept(task["task_id"], self.scope.scope_id, "u-32", "overflow")
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 32)

    def test_two_connections_allow_only_one_dispatch_claim(self):
        operation = self.accepted()
        other = TaskStore(self.path)
        try:
            claimed = other.dispatch(operation["operation_id"])
            self.assertEqual(claimed["dispatch_state"], "submitted")
            with self.assertRaises(StoreConflict):
                self.store.dispatch(operation["operation_id"])
            self.assertEqual(self.store.pending(self.scope.scope_id), [])
        finally:
            other.close()

    def test_recover_marks_dispatched_unknown_and_never_pending(self):
        operation = self.accepted()
        self.store.dispatch(operation["operation_id"])
        self.store.close()
        self.store = TaskStore(self.path)
        self.assertEqual(self.store.recover()["unknown"], 1)
        self.assertEqual(self.store.recover()["unknown"], 0)
        self.assertEqual(self.store.pending(self.scope.scope_id), [])
        self.assertTrue(self.store.has_unresolved())
        with self.assertRaises(StoreConflict):
            self.store.dispatch(operation["operation_id"])

    def test_detached_scope_blocks_unsubmitted_reservation(self):
        operation = self.accepted()
        self.store.detach_scope(self.scope.scope_id)
        with self.assertRaises(StoreDenied):
            self.store.dispatch(operation["operation_id"])
        self.assertEqual(self.store.pending(self.scope.scope_id), [])

    def test_invalid_accept_rolls_back_state_and_event(self):
        task = self.task()
        before = self.store.events(task["task_id"], self.scope.scope_id)
        with self.assertRaises(StoreInvalid):
            self.store.accept(task["task_id"], self.scope.scope_id, "u", "not local", kind="status_query")
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 0)
        self.assertEqual(self.store.events(task["task_id"], self.scope.scope_id), before)

    def test_invalid_settlement_has_no_event_and_identical_one_is_idempotent(self):
        operation = self.accepted()
        task_id = operation["task_id"]
        before = self.store.events(task_id, self.scope.scope_id)
        with self.assertRaises(StoreConflict):
            self.store.settle(operation["operation_id"], replies=["reply"])
        self.assertEqual(self.store.events(task_id, self.scope.scope_id), before)
        self.store.dispatch(operation["operation_id"])
        result = self.store.settle(operation["operation_id"], replies=["reply"], evidence={"source": "legacy"})
        self.assertEqual(result["state"], "awaiting_input")
        count = len(self.store.events(task_id, self.scope.scope_id))
        self.assertEqual(self.store.settle(operation["operation_id"], replies=["reply"], evidence={"source": "legacy"}), result)
        self.assertEqual(len(self.store.events(task_id, self.scope.scope_id)), count)
        with self.assertRaises(StoreConflict):
            self.store.settle(operation["operation_id"], replies=["different"])

    def test_task_and_text_bounds(self):
        tasks = [self.task() for _ in range(8)]
        with self.assertRaises(StoreCapacity):
            self.task()
        with self.assertRaises(StoreInvalid):
            self.store.accept(tasks[0]["task_id"], self.scope.scope_id, "too-long", "x" * 4001)
        operation = self.store.accept(tasks[0]["task_id"], self.scope.scope_id, "max", "x" * 4000)
        self.assertEqual(len(operation["text"]), 4000)
        self.assertEqual(self.store.get_task(tasks[0]["task_id"], self.scope.scope_id)["context_version"], 1)

    def test_voice_context_allowlist_and_capabilities_validation(self):
        task = self.task()
        with self.assertRaises(StoreInvalid):
            self.store.accept(task["task_id"], self.scope.scope_id, "u", "hello", voice_context={"bearer": "secret"})
        operation = self.store.accept(task["task_id"], self.scope.scope_id, "u", "hello", voice_context={"language": "de-DE", "assistant_id": "assistant-1", "profile": "default"})
        self.assertEqual(operation["voice_context"]["language"], "de-DE")
        with self.assertRaises(StoreInvalid):
            Agent("bad", "agent", "rev", {"continue_task": "yes"})

    def test_voice_context_cannot_switch_assistant_binding(self):
        task = self.task()
        with self.assertRaises(StoreInvalid):
            self.store.accept(task["task_id"], self.scope.scope_id, "u", "hello", voice_context={"assistant_id": "different-assistant"})
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 0)

    def test_operation_snapshot_has_execution_reference_slots(self):
        operation = self.accepted()
        self.assertIsNone(operation["request_ref"])
        self.assertIsNone(operation["execution_ref"])
        self.assertIsNone(operation["receipt"])

    def test_disabled_agent_capability_cannot_accept(self):
        agent = Agent("restricted", "agent-2", "revision-1", {"continue_task": False})
        task = self.store.create_task(self.scope, agent, "Restricted work")
        with self.assertRaises(StoreDenied):
            self.store.accept(task["task_id"], self.scope.scope_id, "u", "Do it")
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 0)

    def test_event_write_failure_rolls_back_acceptance(self):
        task = self.task()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("""CREATE TRIGGER abort_accept BEFORE INSERT ON events
                WHEN NEW.type='utterance_accepted' BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END""")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.accept(task["task_id"], self.scope.scope_id, "u", "Keep exact text")
        self.assertEqual(self.store.get_task(task["task_id"], self.scope.scope_id)["context_version"], 0)
        self.assertEqual(self.store.pending(self.scope.scope_id), [])
        self.assertEqual([event["type"] for event in self.store.events(task["task_id"], self.scope.scope_id)], ["task_created"])

    def test_cancel_pending_is_atomic_idempotent_and_binding_checked(self):
        operation = self.accepted()
        task_id = operation['task_id']
        result = self.store.cancel_pending(task_id, self.scope.scope_id, 'cancel-1', text='Cancel')
        self.assertEqual(result['state'], 'cancelled')
        events = self.store.events(task_id, self.scope.scope_id)
        self.store.cancel_pending(task_id, self.scope.scope_id, 'cancel-1', text='Cancel')
        self.assertEqual(self.store.events(task_id, self.scope.scope_id), events)
        with self.assertRaises(StoreConflict):
            self.store.cancel_pending(task_id, self.scope.scope_id, 'cancel-1', text='Changed')
        self.assertEqual(self.store.pending(self.scope.scope_id), [])
        with self.assertRaises(StoreConflict):
            self.store.dispatch(operation['operation_id'])

    def test_cancel_submitted_preserved_across_legacy_settlement(self):
        operation = self.accepted()
        self.store.dispatch(operation['operation_id'])
        pending = self.accepted(task=self.store.get_task(operation['task_id'], self.scope.scope_id), utterance='second')
        self.store.cancel_pending(operation['task_id'], self.scope.scope_id, 'cancel', text='Stop')
        result = self.store.settle(operation['operation_id'], replies=['Your name?'])
        self.assertEqual(result['state'], 'cancel_requested')
        self.assertEqual(result['open_question'], 'Your name?')
        self.assertEqual(self.store.pending(self.scope.scope_id), [])
        with self.assertRaises(StoreConflict):
            self.store.dispatch(pending['operation_id'])

    def test_settlement_persists_latest_question_and_clears_on_final(self):
        operation = self.accepted()
        self.store.dispatch(operation['operation_id'])
        result = self.store.settle(operation['operation_id'], replies=['Hello', 'Your name?'])
        self.assertEqual(result['open_question'], 'Your name?')
        operation = self.accepted(task=result, utterance='answer')
        self.store.dispatch(operation['operation_id'])
        result = self.store.settle(operation['operation_id'], replies=['Done'], outcome='succeeded')
        self.assertIsNone(result['open_question'])

    def test_legacy_cannot_claim_authoritative_cancellation(self):
        operation = self.accepted()
        self.store.dispatch(operation['operation_id'])
        with self.assertRaises(StoreDenied):
            self.store.settle(operation['operation_id'], replies=['Cancelled'], outcome='cancelled',
                              evidence={'authoritative': True})
        self.assertTrue(self.store.has_unresolved())

    def test_cancel_event_failure_rolls_back_all_changes(self):
        operation = self.accepted()
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TRIGGER abort_cancel BEFORE INSERT ON events WHEN NEW.type='cancel_pending' BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END")
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.cancel_pending(operation['task_id'], 'scope-1', 'cancel', text='Stop')
        self.assertEqual(self.store.get_task(operation['task_id'], 'scope-1')['state'], 'queued')
        self.assertEqual(len(self.store.pending('scope-1')), 1)

    def test_question_binding_survives_reopen_and_clears_on_answer(self):
        task = self.task()
        self.store.note_question(task['task_id'], 'scope-1', 'Your name?', source='greeting')
        self.store.close()
        self.store = TaskStore(self.path)
        self.assertEqual(self.store.question('scope-1')['source'], 'greeting')
        self.assertEqual(self.store.question('scope-1')['task_id'], task['task_id'])
        self.accepted(task=task)
        self.assertIsNone(self.store.question('scope-1'))


if __name__ == "__main__":
    unittest.main()
