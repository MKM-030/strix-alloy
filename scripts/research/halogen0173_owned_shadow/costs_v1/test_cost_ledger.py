"""CPU-only sidecar join tests; execution belongs to the task owner."""
import io
import struct
import unittest
import cost_ledger as cost
from test_ledger import header, event, initial, round_pair
# Frozen fixture helpers load their own reader module. Expect exceptions from
# the actual reader under test, whose class identity belongs to cost.ledger.
ledger = cost.ledger

def cost_header():
    b = bytearray(128)
    b[:8] = b'H0173SC1'
    struct.pack_into('<II', b, 8, 1, 96)
    b[16:80] = ledger.RUNTIME_SHA.encode('ascii')
    b[80:96] = bytes(range(16))
    struct.pack_into('<IIII', b, 96, 1, 1, 0, 0)
    return bytes(b)

def stamp(kind, seq, ns, flags=1, error=0, **kw):
    return cost.COST_EVENT.pack(kind, flags, seq, kw.get('birth', 1),
        kw.get('cookie', 10), kw.get('epoch', 1), kw.get('round', 1),
        123, ns, kw.get('dropped', 0), 1, kw.get('native_flags', 32|1 if kind == 5 else 32|16|64), error, 0, 0)

def join(costs, events=None):
    if events is None:
        events = initial()+round_pair()+[event(4, 5)]
    return cost.read_timed_ledger(io.BytesIO(header()+b''.join(events)),
                                 io.BytesIO(cost_header()+b''.join(costs)))

class CostTests(unittest.TestCase):
    def test_exact_owned_sequences_join_only_observed_elapsed(self):
        r = join([stamp(5, 3, 100), stamp(6, 4, 325)])
        row, = r['rows']
        self.assertEqual(row['observed_begin_to_outcome_ns'], 225)
        self.assertEqual(row['cost_status'], 'observed')
        self.assertTrue(r['round_costs_complete'])
        self.assertEqual(row['survival_labels'], [1, 0])
        self.assertEqual((row['causal_depth_low'], row['causal_depth_high']), (2, 3))
        self.assertNotIn('decode_tps', row)

    def test_missing_stamp_and_clock_failure_do_not_invent_elapsed(self):
        for records, expected in (([stamp(5,3,100)], 'missing_outcome'),
            ([stamp(5,3,0,flags=2,error=5),stamp(6,4,200)], 'clock_failure')):
            row, = join(records)['rows']
            self.assertIsNone(row['observed_begin_to_outcome_ns'])
            self.assertEqual(row['cost_status'], expected)

    def test_reversed_clock_is_unavailable_even_without_producer_flag(self):
        row, = join([stamp(5,3,200),stamp(6,4,100)])['rows']
        self.assertEqual(row['cost_status'], 'clock_reversed')
        self.assertIsNone(row['observed_begin_to_outcome_ns'])

    def test_nonce_or_identity_mismatch_is_rejected(self):
        b = bytearray(cost_header()); b[80] ^= 1
        with self.assertRaises(ledger.LedgerError):
            cost.read_timed_ledger(io.BytesIO(header()), io.BytesIO(b))
        with self.assertRaises(ledger.LedgerError):
            join([stamp(5,3,100,birth=2),stamp(6,4,200)])

    def test_terminal_native_censor_never_becomes_cost_training_row(self):
        r = join([stamp(5,3,100),stamp(6,4,200,native_flags=32|16|128|256|512)],
                 initial()+round_pair(terminal=True)+[event(4,5)])
        self.assertEqual(r['rows'], [])
        self.assertEqual(r['cost_summary']['native_censored_pairs'], 1)

    def test_native_loss_disqualifies_costs(self):
        events = initial()+round_pair()+[event(7,5,dropped=1)]
        r = join([stamp(5,3,100),stamp(6,4,200)],events)
        self.assertFalse(r['round_costs_complete'])
        self.assertEqual(r['rows'][0]['cost_status'], 'journal_loss')

    def test_torn_duplicate_or_nonzero_reserved_cost_is_rejected(self):
        records = [stamp(5,3,100),stamp(6,4,200)]
        with self.assertRaises(ledger.LedgerError): join(records+[records[-1]])
        with self.assertRaises(ledger.LedgerError): join(records+[b'x'])
        invalid = bytearray(records[0]); invalid[-1] = 1
        with self.assertRaises(ledger.LedgerError): join([bytes(invalid),records[1]])

if __name__ == '__main__':
    unittest.main()
