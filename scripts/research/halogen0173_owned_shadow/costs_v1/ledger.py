"""Strict offline reader for the copied, shadow-only Halogen 0.17.3 journal.

No runtime import or accelerator access. Counter labels describe the actually
attempted stock prefix, not unchosen widths, independent token probabilities,
or throughput. Model/tokenizer/document pins are supplied by the owned collector.
The v1 wire has no clocks and therefore supplies no round-cost labels. External
metadata is caller supplied, not proof of loaded native assets. A collector's
owned receipt must bind session/request IDs to documents and loaded asset pins
before these rows can train a selector; one global document ID requires a
collection containing only that document.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct

RUNTIME_SHA = 'af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7'
EVENT = struct.Struct('<II6QIiQ4I6iIiII8Q64i16i')
assert EVENT.size == 512
COUNTERS = ('decode_rounds', 'output_attempted', 'pld_rounds', 'pld_accepted',
            'pld_drafted', 'neural_rounds', 'neural_drafted', 'neural_accepted')
FIELDS = ('kind', 'flags', 'seq', 'birth', 'cookie', 'epoch', 'round', 'wire_id',
          'source', 'status', 'dropped', 'context_total', 'context_count',
          'offer_total', 'offer_count', 'current_id', 'opening_id', 'depth_low',
          'depth_high', 'stock_width', 'native_allowance', 'transported_count',
          'model_position', 'adaptive', 'reserved')

class LedgerError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise LedgerError(message)

def decode_header(data):
    require(len(data) == 128, 'Incomplete header')
    require(data[:8] == b'H0173SL1', 'Wrong magic')
    require(struct.unpack_from('<II', data, 8) == (1, 512), 'Unsupported wire version/size')
    require(data[16:80] == RUNTIME_SHA.encode('ascii'), 'Wrong runtime SHA')
    require(any(data[80:96]), 'Missing session nonce')
    require(struct.unpack_from('<IIII', data, 96) == (64, 16, 8, 0), 'Unsupported capacities/flags')
    require(data[112:] == bytes(16), 'Nonzero header reserved bytes')
    return {'schema': 'halogen0173.shadow-ledger.v1', 'runtime_sha256': RUNTIME_SHA,
            'session_nonce': data[80:96].hex(), 'contains_round_costs': False}

def decode_event(data):
    require(len(data) == EVENT.size, 'Torn event')
    values = EVENT.unpack(data)
    e = dict(zip(FIELDS, values[:25]))
    e['counters'] = values[25:33]
    context, offer = values[33:97], values[97:113]
    require(1 <= e['kind'] <= 7, 'Unknown event kind')
    require(e['flags'] & ~1023 == 0 and e['reserved'] == 0, 'Unknown flags/reserved field')
    require(e['source'] in (0, 1, 2), 'Unknown source')
    require(e['adaptive'] in (0, 1), 'Invalid adaptive byte')
    for name, total, count, cap, available, truncated, ids in (
        ('context', e['context_total'], e['context_count'], 64, 1, 2, context),
        ('offer', e['offer_total'], e['offer_count'], 16, 4, 8, offer),
    ):
        require(count <= min(total, cap), name+' count exceeds total/cap')
        require(not any(ids[count:]), name+' unused IDs must be zero')
        if e['flags'] & available:
            require(count == min(total, cap), name+' incomplete copy')
            require(bool(e['flags'] & truncated) == (total > cap), name+' truncation mismatch')
            require(all(i >= 0 for i in ids[:count]), name+' negative token ID')
        else:
            require(count == total == 0 and not e['flags'] & truncated, name+' unavailable copy carries data')
    require(not (e['flags'] & 64 and e['flags'] & 128), 'Both continuing and terminal')
    e['context_suffix'] = list(context[:e['context_count']])
    e['offer_ids'] = list(offer[:e['offer_count']])
    return e

def read_ledger(stream, *, model_sha256=None, tokenizer_sha256=None,
                document_id=None, max_events=65536):
    """Join only currently owned begin/outcome pairs; never invent missing rows."""
    require(type(max_events) is int and 0 < max_events <= 1000000, 'Invalid event budget')
    for label, value in (('model', model_sha256), ('tokenizer', tokenizer_sha256)):
        require(value is None or re.fullmatch('[0-9a-f]{64}', value), 'Invalid '+label+' pin')
    require(document_id is None or isinstance(document_id, str) and 0 < len(document_id) <= 256,
            'Invalid document ID')
    header = decode_header(stream.read(128))
    summary = Counter(events=0, matched_pairs=0, censored_pairs=0, zero_attempt_pairs=0,
                      unmatched_outcomes=0, invalidated_pairs=0, gaps=0,
                      native_neural_drafted=0, native_neural_accepted=0,
                      native_pld_drafted=0, native_pld_accepted=0)
    owners, slots, epochs, pending, next_round, counter_watermarks = {}, {}, {}, {}, {}, {}
    last_birth = 0
    rows = []
    previous_seq = 0
    dropped = 0
    complete = True

    def invalidate(predicate):
        doomed = [key for key in pending if predicate(key)]
        for key in doomed:
            del pending[key]
        summary['invalidated_pairs'] += len(doomed)

    while True:
        data = stream.read(512)
        if not data:
            break
        e = decode_event(data)
        summary['events'] += 1
        require(summary['events'] <= max_events, 'Event budget exceeded')
        require(e['seq'] > previous_seq, 'Nonincreasing sequence')
        require(e['dropped'] >= dropped, 'Dropped count regressed')
        discontinuity = e['seq'] != previous_seq+1 or e['dropped'] != dropped or e['kind'] == 7
        previous_seq, dropped = e['seq'], e['dropped']
        if discontinuity:
            complete = False
            summary['gaps'] += 1
            invalidate(lambda key: True)
            owners.clear(); slots.clear(); next_round.clear(); counter_watermarks.clear()
        if e['kind'] == 7:
            continue
        birth, cookie, epoch = e['birth'], e['cookie'], e['epoch']
        kind = e['kind']
        if kind == 1:
            require(birth > last_birth, 'Duplicate/nonincreasing birth')
            require(len(owners) < 1024, 'Owner budget exceeded')
            last_birth = birth
            owners[birth] = e['wire_id']
        elif kind == 2:
            require(birth in owners and owners[birth] == e['wire_id'] and cookie > 0 and epoch > epochs.get(cookie, 0),
                    'Slot attach without fresh owned epoch')
            invalidate(lambda key: key[1] == cookie or key[0] == birth)
            slots = {c: b for c, b in slots.items() if b[0] != birth}
            epochs[cookie] = epoch
            slots[cookie] = (birth, epoch)
        elif kind == 3:
            require(birth in owners and owners[birth] == e['wire_id'], 'Invalidation without owner')
            invalidate(lambda key: key[:3] == (birth, cookie, epoch))
            if slots.get(cookie) == (birth, epoch):
                del slots[cookie]
        elif kind == 4:
            require(birth in owners and owners[birth] == e['wire_id'], 'Retirement without owner')
            invalidate(lambda key: key[0] == birth)
            owners.pop(birth, None)
            counter_watermarks.pop(birth, None)
            slots = {c: b for c, b in slots.items() if b[0] != birth}
        elif kind in (5, 6):
            key = (birth, cookie, epoch, e['round'])
            owned = birth in owners and owners[birth] == e['wire_id'] and slots.get(cookie) == (birth, epoch)
            if owned and e['flags'] & 32:
                previous = counter_watermarks.get(birth, (0,) * 8)
                require(all(b >= a for a, b in zip(previous, e['counters'])), 'Cumulative counters regressed')
                counter_watermarks[birth] = e['counters']
            if kind == 5:
                require(owned and e['round'] > 0, 'Begin without active owner/slot')
                owner_key = key[:3]
                require(e['round'] > next_round.get(owner_key, 0), 'Reused/nonincreasing round')
                require(not any(k[:3] == owner_key for k in pending), 'Overlapping owned round')
                next_round[owner_key] = e['round']
                pending[key] = e
                continue
            before = pending.pop(key, None) if owned else None
            if before is None:
                summary['unmatched_outcomes'] += 1
                continue
            require(before['source'] == e['source'], 'Outcome source changed')
            summary['matched_pairs'] += 1
            if not before['flags'] & 32 or not e['flags'] & 32:
                summary['censored_pairs'] += 1
                continue
            delta = tuple(b-a for a, b in zip(before['counters'], e['counters']))
            require(all(d >= 0 for d in delta), 'Native counters regressed')
            require(delta[3] <= delta[4] and delta[7] <= delta[6], 'Accepted exceeds attempted')
            summary['native_neural_drafted'] += delta[6]
            summary['native_neural_accepted'] += delta[7]
            summary['native_pld_drafted'] += delta[4]
            summary['native_pld_accepted'] += delta[3]
            censored = (e['status'] != 0 or not e['flags'] & 64 or
                        bool((before['flags'] | e['flags']) & (128|256|512)))
            if censored or e['source'] == 0:
                summary['censored_pairs'] += 1
                continue
            source = 'neural' if e['source'] == 1 else 'pld'
            attempted, accepted = (delta[6], delta[7]) if source == 'neural' else (delta[4], delta[3])
            if attempted == 0:
                summary['zero_attempt_pairs'] += 1
                continue
            require(delta[5 if source == 'neural' else 2] == 1, 'Aggregate native rounds are not one prefix')
            other_indices = (2, 3, 4) if source == 'neural' else (5, 6, 7)
            require(all(delta[i] == 0 for i in other_indices), 'Cross-source aggregate is not one prefix')
            require(attempted <= 16, 'Attempted prefix exceeds bounded label budget')
            if before['stock_width'] >= 0:
                require(attempted <= before['stock_width'], 'Attempts exceed recorded stock width')
            if before['native_allowance'] >= 0:
                require(attempted <= before['native_allowance'], 'Attempts exceed recorded allowance')
            if source == 'pld':
                require(before['flags'] & 4 and attempted <= before['offer_total'], 'PLD labels without offer')
                if attempted > before['offer_count']:
                    summary['censored_pairs'] += 1
                    continue
            transported_delta = None
            if before['flags'] & 16 and e['flags'] & 16:
                transported_delta = e['transported_count'] - before['transported_count']
                require(transported_delta >= 0, 'Transport count regressed')
            rows.append(dict(session_nonce=header['session_nonce'], owner_birth=birth,
                             slot_cookie=cookie, slot_epoch=epoch, round=e['round'],
                             begin_seq=before['seq'], outcome_seq=e['seq'], source=source,
                             wire_request_id=before['wire_id'],
                             current_id=before['current_id'], opening_id=before['opening_id'],
                             context_available=bool(before['flags'] & 1),
                             context_total=before['context_total'], context_suffix=before['context_suffix'],
                             offer_total=before['offer_total'], offer_ids=before['offer_ids'],
                             stock_width=before['stock_width'], native_allowance=before['native_allowance'],
                             model_position=before['model_position'], adaptive=before['adaptive'],
                             attempted=attempted, accepted_prefix=accepted,
                             survival_labels=[int(accepted >= j) for j in range(1, attempted+1)],
                             output_attempted_delta=delta[1], transported_delta=transported_delta,
                             native_counter_deltas=dict(zip(COUNTERS, delta)),
                             runtime_sha256=RUNTIME_SHA, model_sha256=model_sha256,
                             tokenizer_sha256=tokenizer_sha256, document_id=document_id))
    summary['unmatched_begins'] = len(pending)
    summary['unretired_owners'] = len(owners)
    summary['dropped_cumulative'] = dropped
    summary['training_rows'] = len(rows)
    complete = complete and not pending and not owners and not summary['unmatched_outcomes'] and not summary['invalidated_pairs']
    return dict(header=header, summary=dict(summary), dataset_complete=bool(complete),
                external_metadata_supplied=all(v is not None for v in (model_sha256, tokenizer_sha256, document_id)),
                native_assets_verified_by_reader=False, round_cost_labels_available=False,
                rows=rows)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('journal', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--model-sha256')
    p.add_argument('--tokenizer-sha256')
    p.add_argument('--document-id')
    p.add_argument('--max-events', type=int, default=65536)
    p.add_argument('--require-complete', action='store_true', help='Reject gaps or incomplete owners; does not certify training provenance')
    args = p.parse_args()
    with args.journal.open('rb') as stream:
        result = read_ledger(stream, model_sha256=args.model_sha256,
                             tokenizer_sha256=args.tokenizer_sha256,
                             document_id=args.document_id, max_events=args.max_events)
    if args.require_complete:
        require(result['dataset_complete'] and result['rows'], 'Complete nonempty journal required')
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))

if __name__ == '__main__':
    main()
