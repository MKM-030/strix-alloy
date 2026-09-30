"""Clock-domain independent lease regression tests; no model or network."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
import lease_supervisor as lease

RUN = "c"*32

def record(sequence, stamp=1000, run=RUN):
    return {"schema": 2, "run_id": run, "sequence": sequence, "time": stamp}

class ProgressLeaseTests(unittest.TestCase):
    def test_bootstrap_requires_an_observed_renewal(self):
        tracker = lease.ProgressLease(RUN)
        self.assertFalse(tracker.observe(record(7), now=10))
        self.assertFalse(tracker.is_fresh(now=11))
        self.assertFalse(tracker.observe(record(7), now=11))
        self.assertTrue(tracker.observe(record(8), now=12))
        self.assertTrue(tracker.is_fresh(now=12))

    def test_cross_os_offsets_and_wall_clock_jumps_do_not_stop_live_progress(self):
        for stamp in [-1000000, 0, 1790700297.8, 9000000000]:
            with self.subTest(stamp=stamp):
                tracker=lease.ProgressLease(RUN)
                self.assertFalse(tracker.observe(record(1,stamp),now=10))
                self.assertTrue(tracker.observe(record(2,stamp+90000),now=11))
                self.assertTrue(tracker.observe(record(3,stamp-90000),now=12))

    def test_duplicate_sequence_and_changed_timestamp_cannot_renew(self):
        tracker=lease.ProgressLease(RUN)
        tracker.observe(record(1),now=10)
        tracker.observe(record(2),now=11)
        self.assertTrue(tracker.observe(record(2,9000000000),now=55.9))
        self.assertFalse(tracker.is_fresh(now=56))
        with self.assertRaisesRegex(ValueError,"expired"):
            tracker.observe(record(2,9000000001),now=56)

    def test_late_renewal_cannot_revive_expired_lease(self):
        tracker=lease.ProgressLease(RUN)
        tracker.observe(record(1),now=0)
        tracker.observe(record(2),now=1)
        with self.assertRaisesRegex(ValueError,"expired"):
            tracker.observe(record(99),now=47)

    def test_static_file_never_authorizes_engine_start(self):
        tracker=lease.ProgressLease(RUN)
        self.assertFalse(tracker.observe(record(50),now=0))
        self.assertFalse(tracker.observe(record(50),now=44.9))
        with self.assertRaisesRegex(ValueError,"expired"):
            tracker.observe(record(50),now=45)

    def test_wrong_identity_schema_or_sequence_fails_closed(self):
        bad=[None,[],{},record(1,run="wrong"),{**record(1),"schema":1},
             {**record(1),"schema":True},record(True),record(0),record(-1),record(1.5)]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                lease.ProgressLease(RUN).observe(item,now=1)

    def test_backwards_sequence_is_refused(self):
        tracker=lease.ProgressLease(RUN)
        tracker.observe(record(5),now=0); tracker.observe(record(8),now=1)
        with self.assertRaisesRegex(ValueError,"backwards"):
            tracker.observe(record(7),now=2)

    def test_advancing_sequence_renews_without_relaxing_45_second_limit(self):
        tracker=lease.ProgressLease(RUN)
        tracker.observe(record(1),now=0); tracker.observe(record(2),now=1)
        tracker.observe(record(40),now=44)
        self.assertTrue(tracker.is_fresh(now=88.9))
        self.assertFalse(tracker.is_fresh(now=89))
        self.assertEqual(lease.LEASE_AGE,45)

    def test_record_factory_generates_versioned_progress(self):
        value=lease.lease_record(RUN,3)
        self.assertEqual(value["schema"],2)
        self.assertEqual(value["sequence"],3)
        self.assertEqual(value["run_id"],RUN)
        self.assertIsInstance(value["time"],float)

    def test_wall_clock_is_not_consulted_for_consumer_deadline(self):
        tracker=lease.ProgressLease(RUN)
        with patch.object(lease.time,"time",side_effect=AssertionError("wrong clock")):
            self.assertFalse(tracker.observe(record(1),now=100))
            self.assertTrue(tracker.observe(record(2),now=101))
            self.assertTrue(tracker.is_fresh(now=102))

if __name__=="__main__": unittest.main()
