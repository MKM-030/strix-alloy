"""Functional and optional top-N proxy gate for one managed backend configuration."""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error

from reddit_runtime import ManagedClient, ROOT, save_json
from reddit_suite import compare_quality, digest, make_prompt, modes_for_profile, validate_python_function


def evaluate_code(text):
    if not validate_python_function(text):
        return False, 'syntax_or_unsafe_ast'
    program = ("exec(compile(" + repr(text) + ", '<candidate>', 'exec'), {'__builtins__': {'sum': sum}}, scope)\n"
               "assert scope['add_even']([1, 2, 4, 7]) == 6\n"
               "assert scope['add_even']([]) == 0\n"
               "assert scope['add_even']([-4, 3, 8]) == 4\n")
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run([sys.executable, '-I', '-S', '-c', 'scope = {}\n' + program],
                                cwd=directory, capture_output=True, timeout=3, check=False)
    return result.returncode == 0, 'unit_tests_exit_' + str(result.returncode)


def judge(name, text):
    value = text.strip()
    if name == 'arithmetic':
        return value == '5017'
    if name == 'german':
        return value == 'Berlin ist die Hauptstadt Deutschlands.'
    if name == 'cyrillic':
        return value == 'Москва'
    if name == 'long_needle_8192' or name == 'long_needle_16384':
        return value == 'NEEDLE-7319'
    if name == 'json_schema':
        try:
            obj = json.loads(value)
            return obj == {'alpha': 7, 'beta': 'ok', 'items': [2, 4]}
        except (ValueError, TypeError):
            return False
    if name == 'tool_json':
        try:
            return json.loads(value) == {'tool': 'lookup', 'arguments': {'id': 42}}
        except (ValueError, TypeError):
            return False
    if name == 'code':
        try:
            return evaluate_code(value)[0]
        except (OSError, subprocess.TimeoutExpired):
            return False
    raise ValueError('Unknown quality case: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=pathlib.Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    parser.add_argument('--mode', choices=('serial', 'speculative'), required=True)
    parser.add_argument('--control', type=pathlib.Path)
    parser.add_argument('--logprob-tolerance', type=float, default=0.05)
    args = parser.parse_args()
    if not args.out.resolve().is_relative_to((ROOT / 'server/.local').resolve()):
        parser.error('Raw quality artifacts must be under server/.local')
    client = ManagedClient(args.profile, args.run_id)
    if args.mode not in modes_for_profile(client.profile):
        parser.error('Native decoding mode requires a separate matched profile and engine restart')
    args.out.mkdir(parents=True, exist_ok=False)
    cases = [
        ('arithmetic', 'Reply only with the value of 173 * 29.', 16),
        ('german', 'Antworte exakt: Berlin ist die Hauptstadt Deutschlands.', 40),
        ('cyrillic', 'Ответь точно одним словом: Москва', 32),
        ('json_schema', 'Return only a JSON object with alpha=7, beta="ok", items=[2,4]. No markdown.', 72),
        ('tool_json', 'Return only JSON for calling tool lookup with arguments id=42. Keys: tool, arguments.', 72),
        ('code', 'Return only Python code defining add_even(values), returning the sum of even integers. No markdown.', 192),
        ('long_needle_8192', make_prompt(8192), 32),
    ]
    if client.profile['backend']['context'] >= 32768:
        cases.append(('long_needle_16384', make_prompt(16384), 32))
    rows = []
    summary = {'backend': client.model, 'run_id': args.run_id,
               'profile_sha256': client.profile_sha256,
               'profile': client.profile,
               'suite_sha256': digest(pathlib.Path(__file__).read_bytes() +
                                      pathlib.Path(__file__).with_name('reddit_suite.py').read_bytes()),
               'started_at': time.time(), 'rows': rows, 'passed': False,
               'logprob_capability': {'supported': False, 'reason': 'not_probed'}}
    try:
        try:
            probe = client.call([{'role': 'user', 'content': 'Reply only OK.'}], 8,
                                args.mode, 'logprob_probe', top_logprobs=True)
            exposed = probe['top_logprobs']
            supported = compare_top_logprobs(exposed, exposed) is not None
            summary['logprob_capability'] = {'supported': supported,
                'kind': 'top_n_logprob_proxy_not_full_logits' if supported else None,
                'reason': 'valid per-token top candidates returned' if supported else 'no comparable per-token top-N probabilities returned'}
        except urllib.error.HTTPError as error:
            if error.code not in (400, 422, 501):
                raise
            summary['logprob_capability'] = {'supported': False, 'reason': 'HTTP ' + str(error.code)}
        for name, prompt, limit in cases:
            response = client.call([{'role': 'user', 'content': prompt}], limit, args.mode,
                                   name, top_logprobs=summary['logprob_capability']['supported'])
            comparable = compare_top_logprobs(response['top_logprobs'], response['top_logprobs']) is not None
            response['logprob_evidence'] = ('comparable_top_n_proxy' if comparable else
                                            'unavailable_or_malformed')
            response['passed'] = judge(name, response['text']) and (
                not summary['logprob_capability']['supported'] or comparable)
            rows.append(response)
            print(name, 'PASS' if response['passed'] else 'FAIL', flush=True)
        messages = [{'role': 'user', 'content': 'Remember codeword COBALT-731. Reply only ACK.'}]
        first = client.call(messages, 32, args.mode, 'multi_turn_ack')
        messages += [{'role': 'assistant', 'content': first['text']},
                     {'role': 'user', 'content': 'Return only the codeword I asked you to remember.'}]
        second = client.call(messages, 32, args.mode, 'multi_turn')
        second['passed'] = first['text'].strip() == 'ACK' and second['text'].strip() == 'COBALT-731'
        second['turn1_sha256'] = first['sha256']
        rows.append(second)
        repeats = []
        for index in range(5):
            client.call([{'role': 'user', 'content': f'Reply only DISTRACTOR-{index}.'}],
                        24, args.mode, f'distractor{index}')
            repeats.append(client.call([{'role': 'user', 'content': 'Reply exactly STATE-OK'}],
                                       32, args.mode, 'repeat_state'))
        repeated = repeats[-1]
        repeated['sample_hashes'] = [row['sha256'] for row in repeats]
        repeated['passed'] = all(row['text'].strip() == 'STATE-OK' for row in repeats)
        rows.append(repeated)
        summary['passed'] = all(row['passed'] for row in rows)
        if args.control:
            control = json.loads(args.control.read_text(encoding='utf-8'))
            if control.get('suite_sha256') != summary['suite_sha256']:
                raise ValueError('Control suite revision differs; re-run baseline with this script')
            summary['control'] = str(args.control)
            summary['comparison'] = compare_quality(control, summary, args.logprob_tolerance)
            summary['passed'] = summary['passed'] and summary['comparison']['passed']
    except Exception as error:
        summary['error'] = type(error).__name__ + ': ' + str(error)
        print('QUALITY_ERROR', summary['error'], flush=True)
    finally:
        summary['finished_at'] = time.time()
        summary['passed_count'] = sum(bool(row.get('passed')) for row in rows)
        summary['total'] = len(rows)
        summary['minimum_memory'] = {key: min(row['minimum_memory'][key] for row in rows)
                                     for key in ('available_bytes', 'commit_headroom_bytes')} if rows else None
        save_json(args.out / 'quality.json', summary)
    print('QUALITY_SUMMARY', summary['passed_count'], '/', summary['total'],
          'gate=', summary['passed'], flush=True)
    return 0 if summary['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
