"""No-network tests of exact workload bytes and pre-send durable accounting."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gufo_control.finite_workload import Workload, load_workload, WORKLOAD_SHA256
from gufo_control import finite_ledger
from gufo_control.finite_ledger import Ledger


class WorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = load_workload()

    def test_pinned_identity_and_immutable_copies(self):
        workload = self.workload
        self.assertEqual(sha256(workload.raw).hexdigest().upper(), WORKLOAD_SHA256)
        value = workload.document()
        value['limits']['maximum_connections'] = 999
        self.assertEqual(workload.limits()['maximum_connections'], 3)
        with self.assertRaises(FrozenInstanceError):
            workload.raw = b'bad'
        with self.assertRaisesRegex(ValueError, 'finite_workload_identity'):
            Workload(workload.raw+b' ')

    def test_all_72_bodies_hash_and_only_congestion_probe_overrides(self):
        posts = [self.workload.post(index, attempt) for index, count in ((1, 66), (2, 6))
                 for attempt in range(1, count+1)]
        self.assertEqual(len(posts), 72)
        for post in posts:
            self.assertEqual(sha256(post.body).hexdigest().upper(), post.body_sha256)
        third = self.workload.post(1, 45)
        self.assertEqual((third.expected_status, third.expected_error), (429, 'queue_full'))
        ordinary = [p for p in posts if p.request_id == third.request_id and p.attempt != 45]
        self.assertTrue(ordinary)
        self.assertTrue(all(p.expected_status == 200 for p in ordinary))

    def test_raw_negative_bytes_are_not_reserialized(self):
        body = self.workload.post(1, 60).body
        self.assertEqual(len(body), 16385)
        self.assertEqual(json.loads(body)['model'], 'gufo-flash-next')
        invalid = self.workload.post(1, 64).body
        self.assertIn(b'\xc0', invalid)
        with self.assertRaises(UnicodeDecodeError):
            invalid.decode('utf-8')
        duplicate = self.workload.post(1, 65).body
        self.assertEqual(duplicate.count(b'"max_tokens"'), 2)
        self.assertEqual(self.workload.post(1, 66).body, b'{"model":')

    def test_indices_refuse_bool_and_unknown_slots(self):
        for index, attempt in ((True, 1), (0, 1), (3, 1), (1, True), (1, 67), (2, 7)):
            with self.subTest(index=index, attempt=attempt), self.assertRaises(ValueError):
                self.workload.post(index, attempt)


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = load_workload()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'ledger'
        self.now = 100.0
        self.ledger = Ledger(self.root, self.workload, 1, 'unit-run', 100.0,
                             create=True, clock=lambda: self.now)

    def reserve_post(self, attempt=1):
        return self.ledger.reserve('post', attempt,
                                  body=self.workload.post(1, attempt).body)

    def test_reservation_is_durable_before_return_and_never_refunded(self):
        row = self.reserve_post()
        path = self.root/'post-001.reserved.json'
        self.assertTrue(path.exists())
        disk = json.loads(path.read_text())
        self.assertEqual(disk['body_sha256'], row['body_sha256'])
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])
        self.ledger.complete(row['slot'], {'success': True, 'classification': 'expected_rejection'})
        with self.assertRaisesRegex(ValueError, 'consumed_or_out_of_order'):
            self.reserve_post()
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)

    def test_mutated_body_or_out_of_order_refuses_before_reservation(self):
        for attempt, body in ((1, b'{}'), (2, self.workload.post(1, 2).body)):
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                self.ledger.reserve('post', attempt, body=body)
        self.assertEqual(self.ledger.snapshot()['reserved'], 0)

    def test_unknown_and_bool_slots_refuse(self):
        for kind, ordinal in (('POST', 1), ('post', True), ('models', 2), ('ready', 0)):
            with self.subTest(kind=kind, ordinal=ordinal), self.assertRaises(ValueError):
                self.ledger.reserve(kind, ordinal)
        self.assertEqual(self.ledger.snapshot()['reserved'], 0)

    def test_failed_attempt_blocks_new_work(self):
        row = self.reserve_post()
        self.ledger.complete(row['slot'], {'success': False, 'classification': 'ambiguous_send'})
        with self.assertRaisesRegex(ValueError, 'finite_prior_failure'):
            self.reserve_post(2)
        with self.assertRaisesRegex(ValueError, 'finite_outcome_slot'):
            self.ledger.complete(row['slot'], {'success': True})

    def test_handoff_requires_terminal_records_and_exact_identity(self):
        self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_incomplete_handoff'):
            Ledger(self.root, self.workload, 1, 'unit-run', 100.0)
        self.ledger.complete('post-001', {'success': True})
        reopened = Ledger(self.root, self.workload, 1, 'unit-run', 100.0, clock=lambda: self.now)
        self.assertEqual(reopened.snapshot()['counts']['post'], 1)
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            Ledger(self.root, self.workload, 1, 'wrong-run', 100.0)
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            Ledger(self.root, self.workload, 2, 'unit-run', 100.0)

    def test_fsync_failure_consumes_record_and_handoff_fails_closed(self):
        with patch.object(finite_ledger.os, 'fsync', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.reserve_post()
        self.assertTrue((self.root/'post-001.reserved.json').exists())
        with self.assertRaisesRegex(ValueError, 'consumed_or_out_of_order'):
            self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_incomplete_handoff'):
            Ledger(self.root, self.workload, 1, 'unit-run', 100.0)

    def test_limits_and_absolute_deadlines(self):
        self.now = 579.5
        ready = self.ledger.reserve('ready', 1)
        self.assertEqual(ready['deadline'], 580.0)
        self.ledger.complete(ready['slot'], {'success': True, 'ready': False})
        self.now = 580.0
        with self.assertRaisesRegex(ValueError, 'finite_deadline'):
            self.ledger.reserve('ready', 2)
        self.now = 3690.0
        row = self.reserve_post()
        self.assertEqual(row['deadline'], 3700.0)
        self.now = 3700.0
        with self.assertRaisesRegex(ValueError, 'finite_deadline'):
            self.reserve_post(2)

    def test_nonfinite_clock_and_constructor_times(self):
        for value in (-1, True, float('nan'), float('inf'), 10**400):
            self.now = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                self.reserve_post()
        with self.assertRaises(ValueError):
            Ledger(Path(self.temp.name)/'bad', self.workload, 1, 'bad', 1e308, create=True)

    def test_ready_and_model_query_caps_and_no_get_after_post(self):
        for index in range(1, 241):
            self.ledger.reserve('ready', index)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            self.ledger.reserve('ready', 241)
        self.ledger.reserve('models', 1)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            self.ledger.reserve('models', 2)
        fresh = Ledger(Path(self.temp.name)/'after-ready', self.workload, 1, 'fresh',
                       100.0, create=True, clock=lambda: 100.0)
        fresh.reserve('post', 1, body=self.workload.post(1, 1).body)
        with self.assertRaisesRegex(ValueError, 'finite_readiness_finished'):
            fresh.reserve('ready', 1)

    def test_second_lifecycle_post_cap_and_budget_accounting(self):
        ledger = Ledger(Path(self.temp.name)/'second', self.workload, 2, 'second-run',
                        100.0, create=True, clock=lambda: 100.0)
        for attempt in range(1, 7):
            ledger.reserve('post', attempt, body=self.workload.post(2, attempt).body)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            ledger.reserve('post', 7)
        observed = ledger.snapshot()
        self.assertEqual(observed['reserved_wire_bytes'], 6*8*1024*1024)
        self.assertLess(observed['reserved_evidence_bytes'], 128*1024*1024)

    def test_budget_failure_does_not_create_a_reservation(self):
        with patch.object(finite_ledger, 'BASE_EVIDENCE_RESERVE',
                          self.ledger.life['maximum_client_evidence_bytes']):
            with self.assertRaisesRegex(ValueError, 'finite_budget_exceeded'):
                self.reserve_post()
        self.assertFalse((self.root/'post-001.reserved.json').exists())

    def test_partial_and_forged_records_refuse(self):
        self.reserve_post()
        path = self.root/'post-001.reserved.json'
        original = path.read_bytes()
        path.write_bytes(b'{"schema":')
        with self.assertRaises(ValueError):
            self.ledger.snapshot()
        path.write_bytes(original)
        self.ledger.complete('post-001', {'success': True})
        outcome = self.root/'post-001.outcome.json'
        row = json.loads(outcome.read_bytes())
        row['reservation_sha256'] = '0'*64
        outcome.write_text(json.dumps(row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'finite_outcome_binding'):
            self.ledger.snapshot()

    def test_oversized_outcome_refuses_and_stays_pending(self):
        self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_record_size'):
            self.ledger.complete('post-001', {'success': True, 'text': 'x'*65536})
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])

    def test_unknown_entry_and_boolean_header_are_not_trusted(self):
        identity = self.root/'identity.json'
        original = identity.read_bytes()
        value = json.loads(original)
        value['schema'] = True
        identity.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            self.ledger.snapshot()
        identity.write_bytes(original)
        (self.root/'unexpected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_entry'):
            self.ledger.snapshot()

    def test_directory_scan_stops_at_entry_cap_and_closes_iterator(self):
        maximum = 2 + 2*(self.ledger.life['maximum_post_attempts']
                         + self.ledger.life['maximum_ready_polls'] + 1)

        class SyntheticEntries:
            def __init__(self):
                self.pulled = 0
                self.closed = False

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.closed = True

            def __iter__(self):
                return self

            def __next__(self):
                self.pulled += 1
                if self.pulled > maximum + 1:
                    raise AssertionError('unbounded_directory_scan')
                return SimpleNamespace(name='runner.lock', path=str(self.root/'runner.lock'))

        entries = SyntheticEntries()
        entries.root = self.root
        with patch.object(finite_ledger.os, 'scandir', return_value=entries) as scan:
            with self.assertRaisesRegex(ValueError, 'finite_ledger_entries'):
                self.ledger.snapshot()
        scan.assert_called_once_with(self.root)
        self.assertEqual(entries.pulled, maximum + 1)
        self.assertTrue(entries.closed)

    def test_exponent_overflow_in_outcome_and_nested_result_refuses_readback(self):
        self.reserve_post()
        self.ledger.complete('post-001', {'success': True, 'seconds': 1.0,
                                          'nested': {'elapsed': -1.0}})
        outcome = self.root/'post-001.outcome.json'
        original = outcome.read_text(encoding='utf-8')
        for before, after in (('"seconds":1.0', '"seconds":1e400'),
                              ('"elapsed":-1.0', '"elapsed":-1e400')):
            with self.subTest(overflow=after):
                self.assertIn(before, original)
                outcome.write_text(original.replace(before, after), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'finite_nonfinite_json'):
                    self.ledger.snapshot()
        outcome.write_text(original, encoding='utf-8')
        self.assertEqual(self.ledger.snapshot()['completed'], 1)

    def test_nonfinite_outcome_stays_uncommitted(self):
        self.reserve_post()
        with self.assertRaises(ValueError):
            self.ledger.complete('post-001', {'success': True, 'seconds': float('nan')})
        self.assertFalse((self.root/'post-001.outcome.json').exists())
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])

    def test_same_slot_race_has_one_winner(self):
        barrier = threading.Barrier(2)
        def compete():
            barrier.wait(timeout=2)
            try:
                self.reserve_post()
                return 'reserved'
            except ValueError:
                return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: compete(), range(2)))
        self.assertEqual(sorted(results), ['refused', 'reserved'])
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)


if __name__ == '__main__':
    unittest.main()
