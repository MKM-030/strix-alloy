"""Offline tests of causal joins and censoring; no engine/device imports."""
import importlib.util
import io
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("round_ledger", HERE / "ledger.py")
ledger = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ledger
spec.loader.exec_module(ledger)

def header():
    b = bytearray(128)
    b[:8] = b"H0173SL1"
    struct.pack_into("<II", b, 8, 1, 512)
    b[16:80] = ledger.RUNTIME_SHA.encode("ascii")
    b[80:96] = bytes(range(16))
    struct.pack_into("<IIII", b, 96, 64, 16, 8, 0)
    return bytes(b)

def event(kind, seq, **kw):
    b = bytearray(512)
    values = dict(flags=32, birth=1, cookie=10, epoch=1, round=0,
                  source=0, status=0, dropped=0, context_total=0,
                  context=(), offer=(), stock=2, allowance=2,
                  counters=(0,) * 8, transported=0)
    values.update(kw)
    struct.pack_into("<II6QIiQ4I6iIiII", b, 0,
                     kind, values['flags'], seq, values['birth'], values['cookie'],
                     values['epoch'], values['round'], 123, values['source'],
                     values['status'], values['dropped'], values['context_total'],
                     len(values['context']), len(values['offer']), len(values['offer']),
                     42, 43, 2, 3, values['stock'], values['allowance'],
                     values['transported'], 8192, 0, 0)
    struct.pack_into("<8Q", b, 128, *values['counters'])
    struct.pack_into("<64i", b, 192, *(tuple(values['context']) + (0,) * (64-len(values['context']))))
    struct.pack_into("<16i", b, 448, *(tuple(values['offer']) + (0,) * (16-len(values['offer']))))
    return bytes(b)

def initial():
    return [event(1, 1, cookie=0, epoch=0), event(2, 2)]

def round_pair(seq=3, round=1, terminal=False, accepted=1, source=1):
    flags = 32 | 1
    kw = dict(source=source, round=round, flags=flags, context_total=2, context=(41,42))
    if source == 2:
        kw.update(flags=flags|4, offer=(43,44))
    before = event(5, seq, **kw)
    counters = (1, 2, 0, 0, 0, 1, 2, accepted) if source == 1 else (1, 2, 1, accepted, 2, 0, 0, 0)
    after = event(6, seq+1, round=round, source=source,
                  flags=32|16|(128|256|512 if terminal else 64),
                  status=1 if terminal else 0, counters=counters, transported=1 if terminal else 2)
    return [before, after]

def read(events, tail=b''):
    return ledger.read_ledger(io.BytesIO(header()+b''.join(events)+tail),
                              model_sha256='a'*64, tokenizer_sha256='b'*64,
                              document_id='offline-fixture')

class LedgerTests(unittest.TestCase):
    def test_neural_survival_is_prefix_and_unattempted_horizons_are_absent(self):
        r = read(initial()+round_pair())
        row, = r['rows']
        self.assertEqual(row['source'], 'neural')
        self.assertEqual(row['attempted'], 2)
        self.assertEqual(row['accepted_prefix'], 1)
        self.assertEqual(row['survival_labels'], [1, 0])
        self.assertEqual(row['context_suffix'], [41,42])
        self.assertNotIn('decode_tps', row)

    def test_pld_is_separate_from_neural_and_keeps_copied_offer(self):
        row, = read(initial()+round_pair(source=2))['rows']
        self.assertEqual(row['source'], 'pld')
        self.assertEqual(row['offer_ids'], [43,44])

    def test_terminal_partial_round_keeps_counters_but_no_training_row(self):
        r = read(initial()+round_pair(terminal=True, accepted=2))
        self.assertEqual(r['rows'], [])
        self.assertEqual(r['summary']['censored_pairs'], 1)
        self.assertEqual(r['summary']['native_neural_accepted'], 2)

    def test_slot_replacement_prevents_late_pair_even_with_reused_cookie(self):
        begin, outcome = round_pair()
        events = initial()+[begin, event(3,4), event(2,5,epoch=2),
                            event(6,6,round=1,source=1,flags=32|64,counters=(1,2,0,0,0,1,2,1))]
        r = read(events)
        self.assertEqual(r['rows'], [])
        self.assertEqual(r['summary']['unmatched_outcomes'], 1)

    def test_drop_invalidates_pair_and_disqualifies_dataset(self):
        begin, outcome = round_pair()
        events = initial()+[begin, event(7,4,dropped=1), event(6,5,round=1,source=1,dropped=1)]
        r = read(events)
        self.assertFalse(r['dataset_complete'])
        self.assertEqual(r['rows'], [])

    def test_wrong_runtime_reserved_bytes_or_torn_tail_are_rejected(self):
        for offset in (16, 112):
            b = bytearray(header()); b[offset] ^= 1
            with self.assertRaises(ledger.LedgerError):
                ledger.read_ledger(io.BytesIO(b))
        with self.assertRaises(ledger.LedgerError):
            read(initial(), b'x')

    def test_counter_regression_and_accepted_exceeding_attempts_are_rejected(self):
        for counters in ((1,2,0,0,0,1,2,3), (0,0,0,0,0,0,0,0)):
            begin = event(5,3,round=1,source=1,counters=(1,1,0,0,0,1,1,1))
            outcome = event(6,4,round=1,source=1,flags=32|64,counters=counters)
            with self.assertRaises(ledger.LedgerError):
                read(initial()+[begin,outcome])

    def test_zero_attempt_pld_fallback_does_not_invent_labels(self):
        begin, unused = round_pair(source=2)
        after = event(6,4,round=1,source=2,flags=32|64,counters=(1,2,0,0,0,1,2,1))
        r = read(initial()+[begin,after])
        self.assertEqual(r['rows'], [])
        self.assertEqual(r['summary']['zero_attempt_pairs'], 1)

    def test_aggregate_or_cross_source_counts_cannot_become_one_prefix(self):
        begin, unused = round_pair()
        for counts in ((2,4,0,0,0,2,4,3), (1,2,1,1,2,1,2,1)):
            with self.assertRaises(ledger.LedgerError):
                read(initial()+[begin,event(6,4,round=1,source=1,flags=32|64,counters=counts)])

    def test_birth_is_single_use_and_retirement_must_own_its_wire_identity(self):
        with self.assertRaises(ledger.LedgerError):
            read(initial()+[event(4,3),event(1,4,cookie=0,epoch=0)])
        retired = bytearray(event(4,3))
        struct.pack_into('<Q',retired,48,124)
        with self.assertRaises(ledger.LedgerError):
            read(initial()+[bytes(retired)])

    def test_complete_owned_request_has_matching_rows_and_external_pins(self):
        r = read(initial()+round_pair()+[event(3,5),event(4,6)])
        self.assertTrue(r['dataset_complete'])
        self.assertTrue(r['external_metadata_supplied'])
        self.assertFalse(r['native_assets_verified_by_reader'])
        self.assertEqual(r['summary']['unretired_owners'],0)

if __name__ == '__main__':
    unittest.main()
