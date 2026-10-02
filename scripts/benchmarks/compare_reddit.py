"""Compare already-recorded benchmark continuations without starting an engine."""
import argparse
import json
import pathlib

from reddit_runtime import ROOT
from reddit_suite import digest


def compare_runs(control_identity, control_rows, control_mode,
                 candidate_identity, candidate_rows, candidate_mode):
    fields = ('backend', 'suite_sha256', 'harness_sha256', 'tokenizer_sha256',
              'context_capacity', 'ladder_max', 'reps')
    if any(control_identity.get(field) != candidate_identity.get(field)
           for field in fields):
        raise ValueError('Different backend, workload, tokenizer or harness revision')

    def selected(rows, mode):
        result = {}
        for row in rows:
            if row.get('mode') != mode:
                continue
            key = (row['name'], row['rep'])
            if key in result:
                raise ValueError('Duplicate benchmark case/rep in selected mode')
            usage = row['usage']
            if (not row.get('prompt_sha256') or not row.get('sha256') or
                    type(usage.get('prompt_tokens')) is not int or
                    type(usage.get('completion_tokens')) is not int):
                raise ValueError('Incomplete benchmark sample')
            result[key] = row
        if not result:
            raise ValueError('Requested decoding mode has no samples')
        return result

    previous = selected(control_rows, control_mode)
    current = selected(candidate_rows, candidate_mode)
    if previous.keys() != current.keys():
        raise ValueError('Benchmark cases/repetitions differ')
    input_drift, output_drift, count_drift = [], [], []
    for key in sorted(previous):
        name = str(key[0]) + '/' + str(key[1])
        left, right = previous[key], current[key]
        if left['prompt_sha256'] != right['prompt_sha256']:
            input_drift.append(name)
        if left['sha256'] != right['sha256']:
            output_drift.append(name)
        if any(left['usage'][field] != right['usage'][field]
               for field in ('prompt_tokens', 'completion_tokens')):
            count_drift.append(name)
    return {'passed': not (input_drift or output_drift or count_drift),
            'comparison_kind': 'matched_deterministic_outputs_not_full_logits',
            'control_mode': control_mode, 'candidate_mode': candidate_mode,
            'samples': len(previous), 'input_drift': input_drift,
            'output_drift': output_drift, 'token_count_drift': count_drift}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=pathlib.Path, required=True)
    parser.add_argument('--candidate', type=pathlib.Path, required=True)
    parser.add_argument('--control-mode', choices=('serial', 'speculative'), required=True)
    parser.add_argument('--candidate-mode', choices=('serial', 'speculative'), required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    local = (ROOT / 'server/.local').resolve()
    if any(not path.resolve().is_relative_to(local)
           for path in (args.control, args.candidate, args.out)):
        parser.error('Raw artifacts must stay under server/.local')
    if args.out.exists():
        parser.error('Do not overwrite comparison evidence')

    def load(directory):
        identity = json.loads((directory / 'identity.json').read_text(encoding='utf-8'))
        summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
        if not summary.get('passed_execution'):
            raise ValueError('Control or candidate benchmark did not pass execution')
        raw = (directory / 'samples.jsonl').read_bytes()
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
        return identity, rows, digest(raw)

    control_identity, control_rows, control_digest = load(args.control)
    candidate_identity, candidate_rows, candidate_digest = load(args.candidate)
    result = compare_runs(control_identity, control_rows, args.control_mode,
                          candidate_identity, candidate_rows, args.candidate_mode)
    result['control_samples_sha256'] = control_digest
    result['candidate_samples_sha256'] = candidate_digest
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print('BENCHMARK_COMPARISON', json.dumps(result))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
