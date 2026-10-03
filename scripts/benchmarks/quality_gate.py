"""Functional and optional top-N proxy gate for one managed backend configuration."""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error

from reddit_runtime import ManagedClient, ROOT, save_json
from reddit_suite import (compare_quality, compare_top_logprobs, digest, make_prompt,
                          modes_for_profile, validate_python_function)


def evaluate_code(text):
    if not validate_python_function(text):
        return False, 'syntax_or_unsafe_ast'
    program = ("exec(compile(" + repr(text) + ", '<candidate>', 'exec'), "
               "{'__builtins__': {'sum': sum, 'isinstance': isinstance, 'int': int}}, scope)\n"
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


def grade(name, text):
    """Separate usable payloads from the requested strict output format."""
    value = text.strip()
    if name in ('json_schema', 'tool_json'):
        expected = ({'alpha': 7, 'beta': 'ok', 'items': [2, 4]} if name == 'json_schema'
                    else {'tool': 'lookup', 'arguments': {'id': 42}})
        try:
            payload = json.loads(value)
            format_passed = isinstance(payload, dict)
        except (ValueError, TypeError):
            payload, format_passed = None, False
            fenced = re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n```', value, re.DOTALL)
            if fenced and '```' not in fenced.group(1):
                try:
                    payload = json.loads(fenced.group(1))
                except (ValueError, TypeError):
                    pass
        functional_passed = payload == expected
        return {'functional_passed': functional_passed, 'format_passed': format_passed,
                'passed': functional_passed and format_passed}
    if name == 'code':
        try:
            functional_passed, evaluation = evaluate_code(value)
        except (OSError, subprocess.TimeoutExpired) as error:
            functional_passed, evaluation = False, type(error).__name__
        format_passed = validate_python_function(value)
        return {'functional_passed': functional_passed, 'format_passed': format_passed,
                'passed': functional_passed and format_passed, 'code_evaluation': evaluation}
    passed = judge(name, text)
    return {'functional_passed': passed, 'format_passed': passed, 'passed': passed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=pathlib.Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    parser.add_argument('--mode', choices=('serial', 'speculative'), required=True)
    parser.add_argument('--control', type=pathlib.Path)
    parser.add_argument('--logprob-tolerance', type=float, default=0.05)
    parser.add_argument('--structured-json', action='store_true',
                        help='Require Halogen json_object output for JSON and tool-JSON cases')
    args = parser.parse_args()
    if not args.out.resolve().is_relative_to((ROOT / 'server/.local').resolve()):
        parser.error('Raw quality artifacts must be under server/.local')
    client = ManagedClient(args.profile, args.run_id)
    if args.mode not in modes_for_profile(client.profile):
        parser.error('Native decoding mode requires a separate matched profile and engine restart')
    if args.structured_json and client.profile['engine']['kind'] != 'halogen':
        parser.error('Structured JSON requires the supported Halogen backend')
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
    observations = []
    policy = {'grading_policy': 'functional_and_strict_format_v1',
              'structured_json': args.structured_json}

    def call(*positional, **options):
        response = client.call(*positional, **options)
        observations.append({key: response.get(key) for key in
            ('name', 'mode', 'text', 'sha256', 'minimum_memory', 'usage', 'timings')})
        return response

    summary = {'backend': client.model, 'run_id': args.run_id,
               'profile_sha256': client.profile_sha256,
               'profile': client.profile,
               **policy,
               'suite_sha256': digest(pathlib.Path(__file__).read_bytes() +
                                      pathlib.Path(__file__).with_name('reddit_suite.py').read_bytes() +
                                      json.dumps(policy, sort_keys=True).encode('utf-8')),
               'started_at': time.time(), 'rows': rows, 'observations': observations,
               'passed': False, 'functional_passed': False, 'parity_passed': None,
               'logprob_capability': {'supported': False, 'reason': 'not_probed'}}
    try:
        try:
            probe = call([{'role': 'user', 'content': 'Reply only OK.'}], 1,
                                args.mode, 'logprob_probe', top_logprobs=True)
            exposed = probe['top_logprobs']
            supported = compare_top_logprobs(exposed, exposed) is not None
            summary['logprob_capability'] = {'supported': supported,
                'kind': 'first_token_top_n_proxy_not_full_logits' if supported else None,
                'reason': 'valid first-token top candidates returned' if supported else 'no comparable first-token top-N probabilities returned'}
        except urllib.error.HTTPError as error:
            if error.code not in (400, 422, 501):
                raise
            summary['logprob_capability'] = {'supported': False, 'reason': 'HTTP ' + str(error.code)}
        for name, prompt, limit in cases:
            messages = [{'role': 'user', 'content': prompt}]
            options = ({'response_format': {'type': 'json_object'}}
                       if args.structured_json and name in ('json_schema', 'tool_json') else {})
            response = call(messages, limit, args.mode, name, **options)
            grammar_masked = bool(options)
            if summary['logprob_capability']['supported'] and not grammar_masked:
                # The greedy API exposes top-N only on a one-token request.
                # Keep that separate from the complete functional answer.
                first_token = call(messages, 1, args.mode, name + '_first_token',
                                   top_logprobs=True, **options)
                response['first_token_probe'] = first_token
                response['top_logprobs'] = first_token['top_logprobs']
            comparable = compare_top_logprobs(response['top_logprobs'], response['top_logprobs']) is not None
            response['logprob_evidence'] = ('unavailable_due_to_grammar_mask' if grammar_masked else
                                           'comparable_top_n_proxy' if comparable else
                                           'unavailable_or_malformed')
            response.update(grade(name, response['text']))
            response['passed'] = response['passed'] and (
                not summary['logprob_capability']['supported'] or grammar_masked or comparable)
            rows.append(response)
            print(name, 'PASS' if response['passed'] else 'FAIL', flush=True)
        messages = [{'role': 'user', 'content': 'Remember codeword COBALT-731. Reply only ACK.'}]
        first = call(messages, 32, args.mode, 'multi_turn_ack')
        messages += [{'role': 'assistant', 'content': first['text']},
                     {'role': 'user', 'content': 'Return only the codeword I asked you to remember.'}]
        second = call(messages, 32, args.mode, 'multi_turn')
        second['passed'] = first['text'].strip() == 'ACK' and second['text'].strip() == 'COBALT-731'
        second['functional_passed'] = second['format_passed'] = second['passed']
        second['turn1_sha256'] = first['sha256']
        rows.append(second)
        repeats = []
        for index in range(5):
            call([{'role': 'user', 'content': f'Reply only DISTRACTOR-{index}.'}],
                        24, args.mode, f'distractor{index}')
            repeats.append(call([{'role': 'user', 'content': 'Reply exactly STATE-OK'}],
                                       32, args.mode, 'repeat_state'))
        repeated = repeats[-1]
        repeated['sample_hashes'] = [row['sha256'] for row in repeats]
        repeated['passed'] = all(row['text'].strip() == 'STATE-OK' for row in repeats)
        repeated['functional_passed'] = repeated['format_passed'] = repeated['passed']
        rows.append(repeated)
        summary['passed'] = all(row['passed'] for row in rows)
        summary['functional_passed'] = all(row['functional_passed'] for row in rows)
        if args.control:
            control = json.loads(args.control.read_text(encoding='utf-8'))
            if control.get('suite_sha256') != summary['suite_sha256']:
                raise ValueError('Control suite revision differs; re-run baseline with this script')
            summary['control'] = str(args.control)
            summary['comparison'] = compare_quality(control, summary, args.logprob_tolerance)
            summary['parity_passed'] = summary['comparison']['parity_passed']
            summary['passed'] = summary['passed'] and summary['comparison']['passed']
    except Exception as error:
        summary['passed'] = False
        if args.control:
            summary['parity_passed'] = False
        summary['error'] = type(error).__name__ + ': ' + str(error)
        print('QUALITY_ERROR', summary['error'], flush=True)
    finally:
        summary['finished_at'] = time.time()
        summary['passed_count'] = sum(bool(row.get('passed')) for row in rows)
        summary['total'] = len(rows)
        summary['functional_passed_count'] = sum(bool(row.get('functional_passed')) for row in rows)
        summary['minimum_memory'] = {key: min(event['minimum_memory'][key] for event in observations)
                                     for key in ('available_bytes', 'commit_headroom_bytes')} if observations else None
        save_json(args.out / 'quality.json', summary)
    print('QUALITY_SUMMARY', summary['passed_count'], '/', summary['total'],
          'gate=', summary['passed'], flush=True)
    return 0 if summary['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
