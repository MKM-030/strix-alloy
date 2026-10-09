"""Join optional raw-clock observations to complete actual stock-prefix rows.

These intervals include observer work between owned Begin/Outcome clock samples.
They are neither counterfactual width savings nor end-to-end token rates. The
unmodified ledger.py remains the authority for lifecycle/counter qualification.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import struct
import ledger

COST_EVENT = struct.Struct('<II8QIIiIQ')
assert COST_EVENT.size == 96
FIELDS = ('kind', 'flags', 'seq', 'birth', 'cookie', 'epoch', 'round', 'wire_id',
          'raw_ns', 'dropped', 'source', 'native_flags', 'error', 'reserved', 'tail_reserved')
COST_SCOPE = 'owned_begin_to_owned_outcome_including_observer_overhead'

def decode_cost_header(data):
    ledger.require(len(data) == 128, 'Incomplete cost header')
    ledger.require(data[:8] == b'H0173SC1', 'Wrong cost magic')
    ledger.require(struct.unpack_from('<II', data, 8) == (1, 96), 'Unsupported cost version/size')
    ledger.require(data[16:80] == ledger.RUNTIME_SHA.encode('ascii'), 'Wrong cost runtime SHA')
    ledger.require(any(data[80:96]), 'Missing cost session nonce')
    ledger.require(struct.unpack_from('<IIII', data, 96) == (1, 1, 0, 0), 'Unsupported cost clock/units/flags')
    ledger.require(data[112:] == bytes(16), 'Nonzero cost header reserved bytes')
    return dict(schema='halogen0173.shadow-cost.v1', runtime_sha256=ledger.RUNTIME_SHA,
                session_nonce=data[80:96].hex(), clock='CLOCK_MONOTONIC_RAW', units='ns', scope=COST_SCOPE)

def decode_cost_event(data):
    ledger.require(len(data) == 96, 'Torn cost event')
    e = dict(zip(FIELDS, COST_EVENT.unpack(data)))
    ledger.require(e['kind'] in (5, 6), 'Invalid cost event kind')
    ledger.require(e['reserved'] == e['tail_reserved'] == 0, 'Nonzero cost reserved field')
    ledger.require(e['flags'] in (1, 2, 4, 9), 'Invalid cost clock flags')
    ledger.require(e['error'] == 0 if e['flags'] & 1 else e['error'] > 0, 'Invalid cost clock error')
    ledger.require(bool(e['flags'] & 1) or e['raw_ns'] == 0, 'Failed clock carries timestamp')
    ledger.require(e['kind'] == 6 or e['flags'] != 9, 'Begin cannot carry reversed flag')
    return e

def read_timed_ledger(stream, cost_stream, *, max_events=65536, close_receipt=None, **metadata):
    ledger.require(type(max_events) is int and 0 < max_events <= 1000000, 'Invalid event budget')
    # One bounded cold copy supports both the unchanged reader and exact seq joins.
    blob = stream.read(128+512*max_events+1)
    ledger.require(len(blob) <= 128+512*max_events, 'Event budget exceeded')
    result = ledger.read_ledger(io.BytesIO(blob), max_events=max_events, **metadata)
    native = {}
    for offset in range(128, len(blob), 512):
        e = ledger.decode_event(blob[offset:offset+512])
        if e['kind'] in (5, 6): native[e['seq']] = e
    cost_header = decode_cost_header(cost_stream.read(128))
    ledger.require(cost_header['session_nonce'] == result['header']['session_nonce'], 'Cost session differs from native session')
    costs, previous = {}, 0
    summary = Counter(records=0, expected_records=len(native), missing_records=0,
                      clock_failure_stamps=0, reversed_stamps=0,
                      native_censored_pairs=result['summary']['censored_pairs'],
                      observed_training_rows=0, unavailable_training_rows=0)
    while True:
        data = cost_stream.read(96)
        if not data: break
        e = decode_cost_event(data)
        summary['records'] += 1
        ledger.require(summary['records'] <= max_events, 'Cost event budget exceeded')
        ledger.require(e['seq'] > previous, 'Duplicate/nonincreasing cost sequence')
        previous = e['seq']
        n = native.get(e['seq'])
        ledger.require(n is not None, 'Cost sequence has no native Begin/Outcome')
        for field in ('kind', 'birth', 'cookie', 'epoch', 'round', 'wire_id', 'source', 'dropped'):
            ledger.require(e[field] == n[field], 'Cost/native identity differs: '+field)
        ledger.require(e['native_flags'] == n['flags'], 'Cost/native flags differ')
        costs[e['seq']] = e
        summary['clock_failure_stamps'] += int(not e['flags'] & 1)
        summary['reversed_stamps'] += int(bool(e['flags'] & 8))
    summary['missing_records'] = len(native)-len(costs)
    closure_ok = None
    if close_receipt is not None:
        ledger.require(close_receipt.get('schema') == 'halogen0173.owned-shadow.close.v1', 'Wrong close schema')
        ledger.require(close_receipt.get('session_nonce') == cost_header['session_nonce'], 'Close session differs')
        ledger.require(close_receipt.get('written_events') == result['summary']['events'], 'Close native count differs')
        ledger.require(close_receipt.get('written_cost_events') == summary['records'], 'Close cost count differs')
        ledger.require(close_receipt.get('cost_timing_failures') == summary['clock_failure_stamps']+summary['reversed_stamps'], 'Close timing failure count differs')
        closure_ok = all(close_receipt.get(k) is True for k in
            ('closed', 'qualified_close', 'cost_capture_enabled', 'cost_closed', 'cost_qualified_close'))
    for row in result['rows']:
        native_begin = native[row['begin_seq']]
        before, after = costs.get(row['begin_seq']), costs.get(row['outcome_seq'])
        status, elapsed = 'observed', None
        if not result['dataset_complete']: status = 'journal_loss'
        elif closure_ok is False: status = 'closure_unqualified'
        elif before is None: status = 'missing_begin'
        elif after is None: status = 'missing_outcome'
        elif not (before['flags'] & after['flags'] & 1): status = 'clock_failure'
        elif after['flags'] & 8 or after['raw_ns'] < before['raw_ns']: status = 'clock_reversed'
        else: elapsed = after['raw_ns']-before['raw_ns']
        row.update(observed_begin_to_outcome_ns=elapsed, cost_status=status,
                   cost_clock='CLOCK_MONOTONIC_RAW', cost_scope=COST_SCOPE,
                   causal_depth_low=native_begin['depth_low'], causal_depth_high=native_begin['depth_high'])
        summary['observed_training_rows' if elapsed is not None else 'unavailable_training_rows'] += 1
    result.update(cost_header=cost_header, cost_summary=dict(summary),
        cost_close_verified=closure_ok is True,
        round_cost_labels_available=bool(summary['observed_training_rows']),
        round_costs_complete=bool(result['dataset_complete'] and not summary['missing_records'] and
            not summary['clock_failure_stamps'] and not summary['reversed_stamps'] and
            not summary['unavailable_training_rows'] and closure_ok is not False))
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('journal', type=Path)
    p.add_argument('cost_journal', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--close-receipt', type=Path)
    p.add_argument('--model-sha256')
    p.add_argument('--tokenizer-sha256')
    p.add_argument('--document-id')
    p.add_argument('--max-events', type=int, default=65536)
    p.add_argument('--require-complete', action='store_true', help='Require a nonce-bound qualified close and nonempty complete timed rows')
    args = p.parse_args()
    receipt = json.loads(args.close_receipt.read_text(encoding='utf-8')) if args.close_receipt else None
    with args.journal.open('rb') as native, args.cost_journal.open('rb') as costs:
        result = read_timed_ledger(native, costs, close_receipt=receipt, max_events=args.max_events,
            model_sha256=args.model_sha256, tokenizer_sha256=args.tokenizer_sha256, document_id=args.document_id)
    if args.require_complete:
        ledger.require(result['round_costs_complete'] and result['cost_close_verified'] and result['rows'], 'Closed complete nonempty timed journal required')
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}))

if __name__ == '__main__': main()
