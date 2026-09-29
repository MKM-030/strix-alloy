#!/usr/bin/env python3
"""Bounded identical-input serial/MTP comparison; requires prompt cache OFF.

Two repetitions alternate order. OS file cache is not flushed between requests.
This tests text identity/markers, not general model quality. Non-streaming HTTP
does not measure TTFT; engine prefill and complete request duration are retained.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import time

SPEC = importlib.util.spec_from_file_location(
    'halogen_benchmark', pathlib.Path(__file__).with_name('benchmark-halogen.py'))
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


def cases(suite):
    if suite == 'draft':
        copied = '\n'.join(f'item_{i:02d}: state=ready; owner=local; retries=3; timeout=30;'
                           for i in range(1, 21))
        return [
            dict(name='prose', marker='PROSE_CHECK', prompt=
                 'Start with PROSE_CHECK. Explain in detail the different memory and '
                 'compute costs of prefill and decoding in a mixture-of-experts model. '
                 'Discuss Windows and WSL sharing physical RAM. Write at least 700 words.'),
            dict(name='code', marker='CODE_CHECK', prompt=
                 'Start with CODE_CHECK. Write a Python implementation of a bounded LRU '
                 'cache with get and put, then comprehensive unittest cases for eviction, '
                 'updates, missing keys and invalid capacity. Explain the implementation.'),
            dict(name='lookup', marker='LOOKUP_CHECK', prompt=
                 'Output LOOKUP_CHECK followed by an exact verbatim copy of the text '
                 'between the delimiters. No explanation or code fence.\n<text>\n' +
                 copied + '\n</text>', expected='LOOKUP_CHECK\n' + copied),
        ]
    synthetic = [dict(name=f'prefill_{units}', marker=f'CONTEXT_{units}', prompt=
                 f'Start with CONTEXT_{units}. Explain the supplied text in detail. '
                 'Continue for at least 500 words.\n' + BENCH.FILLER * units)
            for units in (390, 780)]
    root = pathlib.Path(__file__).parents[1]
    code = '\n\n'.join((root / 'patches' / name).read_text() for name in (
        'hip-register-private-rw.c', 'hip-register-hybrid.c', 'halogen-preflight-bridge.c'))[:32000]
    return synthetic + [dict(name='real_code', marker='REAL_CODE_CHECK', prompt=
        'Start with REAL_CODE_CHECK. Review this C code, explaining allocation '
        'ownership, error handling, thread safety and invariants. Do not execute it. '
        'Write a detailed analysis of at least 500 words.\n\n' + code)]


def freeze_from_reference(fixtures, reference):
    prompts = {}
    try:
        for row in reference['samples']:
            messages = row['request']['messages']
            if len(messages) != 1 or messages[0]['role'] != 'user':
                raise ValueError('reference must contain one user message per request')
            prompt = messages[0]['content']
            if not isinstance(prompt, str) or not prompt:
                raise ValueError('reference prompt must be nonempty text')
            if hashlib.sha256(prompt.encode()).hexdigest() != row['prompt_sha256']:
                raise ValueError('reference prompt hash mismatch')
            name = row['case']
            if name in prompts and prompts[name] != prompt:
                raise ValueError('reference mixes prompts within a case')
            prompts[name] = prompt
        if set(prompts) != {case['name'] for case in fixtures}:
            raise ValueError('reference cases do not match the requested suite')
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError('invalid reference request structure') from error
    return [dict(case, prompt=prompts[case['name']]) for case in fixtures]


def payload(case, mode, max_tokens):
    return dict(messages=[dict(role='user', content=case['prompt'])],
                max_tokens=max_tokens, temperature=0, enable_thinking=False,
                reasoning_effort='low', drafter=mode)


def gates(rows, expected_schedule=None):
    names = {row['case'] for row in rows}
    paired = bool(rows) and all(
        {r['drafter'] for r in rows if r['case'] == name} == {'serial', 'mtp'}
        for name in names)
    identical = bool(rows) and all(
        len({r.get('content') for r in rows if r['case'] == name}) == 1
        for name in names)
    correct = bool(rows) and all(
        r.get('nonempty') and r.get('marker_present') and
        r.get('lookup_exact', True) and not r.get('error') for r in rows)
    fresh = bool(rows) and all(r.get('cache_tokens') == 0 for r in rows)
    observed = [(r['case'], r['drafter'], r.get('repetition')) for r in rows]
    complete = (expected_schedule is not None and len(observed) == len(expected_schedule)
                and len(set(observed)) == len(observed)
                and set(observed) == set(expected_schedule))
    # Without a schedule this is only a row-level check, never suite completion.
    return dict(paired=paired, identical=identical, correct=correct, fresh=fresh,
                complete=complete, passed=complete and paired and identical and correct and fresh)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8731')
    parser.add_argument('--suite', choices=('draft', 'prefill'), default='draft')
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--reps', type=int, default=2)
    parser.add_argument('--output', required=True)
    parser.add_argument('--reference', help='reuse identical prompts from a prior result JSON')
    args = parser.parse_args()
    if args.reps < 1 or not 1 <= args.max_tokens <= 2048:
        parser.error('reps must be positive and max-tokens must be 1..2048')
    path = pathlib.Path(args.output)
    if path.exists():
        parser.error('refusing to overwrite an existing result')
    health, _ = BENCH.request_json(args.api + '/health', timeout=30)
    if health.get('prompt_cache', {}).get('enabled') is not False:
        parser.error('requires a server with prompt_cache.enabled=false')
    fixtures = cases(args.suite)
    reference_sha256 = None
    if args.reference:
        try:
            reference_bytes = pathlib.Path(args.reference).read_bytes()
            fixtures = freeze_from_reference(fixtures, json.loads(reference_bytes))
            reference_sha256 = hashlib.sha256(reference_bytes).hexdigest()
        except (OSError, ValueError) as error:
            parser.error(str(error))
    schedule = [(case['name'], mode, rep + 1) for rep in range(args.reps)
                for case in fixtures for mode in ('serial', 'mtp')]
    result = dict(schema='halogen-mode-comparison-v1',
                  created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  health=health, configuration=vars(args), samples=[], ttft=None,
                  expected_schedule=schedule,
                  reference_sha256=reference_sha256,
                  method='cache0; fixed inputs; alternating serial/MTP order; OS cache not flushed')
    path.parent.mkdir(parents=True, exist_ok=True)
    for rep in range(args.reps):
        for case in fixtures:
            for mode in (('serial', 'mtp') if rep % 2 == 0 else ('mtp', 'serial')):
                body = payload(case, mode, args.max_tokens)
                row = dict(case=case['name'], drafter=mode, repetition=rep + 1,
                           prompt_sha256=hashlib.sha256(case['prompt'].encode()).hexdigest())
                try:
                    response, wall = BENCH.request_json(
                        args.api + '/v1/chat/completions', body, timeout=180)
                    row.update(BENCH.extract_measurement(response, wall, case['marker']))
                    row['response'] = response
                    row['request'] = body
                    if 'expected' in case:
                        row['lookup_exact'] = row['content'].strip() == case['expected']
                except Exception as error:
                    row.update(error=repr(error), nonempty=False)
                result['samples'].append(row)
                result['gates'] = gates(result['samples'], schedule)
                path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
                print(json.dumps({k: row.get(k) for k in (
                    'case', 'drafter', 'repetition', 'prompt_tokens', 'completion_tokens',
                    'prompt_tokens_per_second', 'generation_tokens_per_second',
                    'draft_acceptance', 'wall_seconds', 'cache_tokens', 'error')}), flush=True)
                if row.get('error') or not row.get('nonempty') or not row.get('marker_present'):
                    return 2
    print(json.dumps(result['gates']), flush=True)
    return 0 if result['gates']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
