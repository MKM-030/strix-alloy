"""Passive regression for the native request mover; never launches an ELF."""
from pathlib import Path
import copy, json, tempfile
from test_clock_tools import fixture
from verify_phase_journal import validate


def moved_fixture():
    rows, records = fixture()
    rows[0]['decode_pairing_version'] = 2
    for row in rows[1:]:
        row.setdefault('begin_object', row['object'])
        row['observed_native_start_ns'] = row['native_start_ns']
        row['object_native_start_ns'] = row['native_start_ns'] if row['phase'] == 2 and not row['begin'] else 0
    rows[-1]['object'] = 0x5000
    return rows, records


def main():
    rows, records = moved_fixture()
    with tempfile.TemporaryDirectory(prefix='phase-clock-moved-request-') as td:
        target = Path(td)
        journal, dfile = target/'journal.jsonl', target/'d.json'
        journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        dfile.write_text(json.dumps({'records': records}))
        result = validate(journal, dfile, True)
        assert result['paired_raw_phase_verified']
        assert result['consumed_pairs'] == 3
        assert rows[-2]['object'] != rows[-1]['object']
        print(json.dumps({'moved_decode_object_accepted': True, 'signed_request_id': -17,
                          'complete_pairs': result['consumed_pairs'], 'hardware_used': False}))


if __name__ == '__main__':
    main()
