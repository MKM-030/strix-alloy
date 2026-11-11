"""Offline four-capture cohort with causal API/native identities and actual counts."""
import argparse
import hashlib
import json
from pathlib import Path

from validate_capture import BINDING, need, parse_epoch, read_capture, response_counts, validate


def absent(path):
    return not path.exists() and not path.is_symlink()


def validate_cohort(prefix, response_files, request_file, epoch_nonce, arm_file, require_cold=False):
    need(len(response_files) == 4, 'four API response files required')
    need(type(epoch_nonce) is int and 0 < epoch_nonce <= 0xffffffffffffffff,
         'valid nonzero epoch nonce required')
    epoch_prefix = Path(str(prefix) + f'-{epoch_nonce:016x}')
    fault = Path(str(epoch_prefix) + '-fault.bin')
    need(absent(fault), 'epoch fault marker exists')
    need(isinstance(arm_file, Path), 'arm file path required')
    need(absent(arm_file), 'collector must disarm epoch before validation')
    request_data = request_file.read_bytes()
    request = json.loads(request_data)
    rows = []
    last_after = 0
    ids = set()
    for ordinal, response_file in enumerate(response_files):
        response_data = response_file.read_bytes()
        response = json.loads(response_data)
        response_counts(response, request, require_cold)
        journal = Path(str(epoch_prefix) + f'-{ordinal}.bin')
        data = journal.read_bytes()
        events = read_capture(data, ordinal, epoch_nonce)
        report = validate(events, response, request=request, require_cold=require_cold)
        need(events[0]['raw_before'] >= last_after, 'cross-request RAW order violated')
        last_after = events[-1]['raw_after']
        need(report['request_id'] not in ids, 'reused request ID across cohort')
        ids.add(report['request_id'])
        report.update(ordinal=ordinal, phase='warmup_excluded' if ordinal == 0 else 'measured',
                      journal_sha256=hashlib.sha256(data).hexdigest(),
                      response_sha256=hashlib.sha256(response_data).hexdigest(),
                      API_response_id=response.get('id'))
        rows.append(report)
    measured = rows[1:]
    rate_fields = [key for key in measured[0]
                   if key.endswith(('_tps', '_tps_lower', '_tps_upper', '_tps_mid'))]
    means = {key: sum(row[key] for row in measured) / 3 for key in rate_fields}
    binding_data = BINDING.read_bytes()
    need(absent(fault), 'epoch fault marker appeared during validation')
    need(absent(arm_file), 'collector epoch rearmed during validation')
    return dict(schema='halogen0202.raw-side.cohort.v3', valid=True,
                warmup_excluded=True, measured_repetitions=3,
                epoch_nonce=f'{epoch_nonce:016x}', epoch_fault_marker_absent=True,
                epoch_disarm_verified=True,
                request_sha256=hashlib.sha256(request_data).hexdigest(),
                binding_sha256=hashlib.sha256(binding_data).hexdigest(),
                engine_sha256=json.loads(binding_data)['engine_sha256'],
                causal_pairing='Each exact API D-record native ID equals every RAW phase native ID.',
                phase_convention='Actual API/native output total is the decode numerator. '
                                 'Begin count 1 and end-minus-begin delta are retained separately. '
                                 'RAW brackets include observer overhead.',
                cold_required=require_cold, samples=rows, arithmetic_means=means)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', type=Path)
    parser.add_argument('--response-files', type=Path, nargs=4, required=True,
                        help='Four exact OAI response files in ordinal order, warmup then measured')
    parser.add_argument('--request-file', type=Path, required=True)
    parser.add_argument('--epoch', type=parse_epoch, required=True)
    parser.add_argument('--arm-file', type=Path, required=True)
    parser.add_argument('--require-cold', action='store_true')
    args = parser.parse_args()
    report = validate_cohort(args.prefix, args.response_files, args.request_file, args.epoch,
                             args.arm_file, args.require_cold)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
