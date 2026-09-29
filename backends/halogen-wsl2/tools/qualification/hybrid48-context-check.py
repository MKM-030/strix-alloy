"""One bounded diagnostic: calibration, small serial/MTP, then ~260k MTP."""
import argparse
import importlib.util
import json
import math
import pathlib
import time


API = 'http://127.0.0.1:8731'
MARKER = 'CONTEXT_CHECK'
MAX_FILLER_REPEATS = 100000
MAX_PROMPT_BYTES = 16 * 1024 * 1024


def request_body(prompt, mode, max_tokens):
    return dict(messages=[dict(role='user', content=prompt)], max_tokens=max_tokens,
                temperature=0, enable_thinking=False, reasoning_effort='low', drafter=mode)


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--mode', choices=('Unpinned256k', 'PreflightPinned256k'),
                        default='Unpinned256k')
    parser.add_argument('--deadline-seconds', type=int)
    args = parser.parse_args()
    output = args.output
    profile_deadline = 570 if args.mode == 'PreflightPinned256k' else 370
    if args.deadline_seconds is not None and (args.mode != 'PreflightPinned256k' or
            not 1 <= args.deadline_seconds <= profile_deadline):
        parser.error('deadline override must shrink the PreflightPinned256k profile')
    deadline_seconds = args.deadline_seconds or profile_deadline
    large_request_seconds = 500 if args.mode == 'PreflightPinned256k' else 300
    if output.exists():
        raise SystemExit('Refusing to overwrite existing context diagnostic')
    output.parent.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('halogen_benchmark', root / 'scripts/benchmark-halogen.py')
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    started = time.monotonic()
    result = dict(schema='hybrid48-immediate-context-v1', deadline_seconds=deadline_seconds,
                  created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  mode=args.mode, target_prompt_tokens=[512, 512, 260000],
                  samples=[], health=None, calibration=None, passed=False, error=None,
                  note='Actual prompt/output tokens and rates come only from server responses')

    def allowance(cap):
        remaining = deadline_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError(f'{deadline_seconds}-second context diagnostic deadline exhausted')
        return min(cap, remaining)

    def run(label, prompt, mode, max_tokens, target, cap, measured):
        body = request_body(prompt, mode, max_tokens)
        row = dict(label=label, target_prompt_tokens=target, target_output_tokens=max_tokens,
                   mode=mode, request=body, response=None, actual_prompt_tokens=None,
                   actual_output_tokens=None, prompt_ms=None, generation_ms=None,
                   prompt_tokens_per_second=None, generation_tokens_per_second=None,
                   wall_seconds=None, nonempty=False, marker_present=False,
                   passed=False, error=None)
        request_started = time.perf_counter()
        try:
            response, wall = bench.request_json(API + '/v1/chat/completions', body, timeout=allowance(cap))
            row['response'] = response
            row['wall_seconds'] = wall
            usage = response.get('usage')
            timings = response.get('timings')
            if not isinstance(usage, dict) or any(key not in usage for key in ('prompt_tokens', 'completion_tokens')):
                raise ValueError('response lacks server prompt/output counts')
            if not isinstance(timings, dict) or any(key not in timings for key in
                    ('prompt_ms', 'predicted_ms', 'prompt_per_second', 'predicted_per_second')):
                raise ValueError('response lacks engine prefill/decode timings or rates')
            row['actual_prompt_tokens'] = int(usage['prompt_tokens'])
            row['actual_output_tokens'] = int(usage['completion_tokens'])
            row.update(bench.extract_measurement(response, wall, MARKER if measured else 'calibration'))
            if timings.get('cache_n', 0) != 0:
                raise ValueError('prompt cache was active')
            if measured and (not row.get('nonempty') or not row.get('marker_present')):
                raise ValueError('answer is empty or missing CONTEXT_CHECK marker')
            row['passed'] = True
        except Exception as error:
            if row['wall_seconds'] is None:
                row['wall_seconds'] = time.perf_counter() - request_started
            row['error'] = repr(error)
        result['samples'].append(row)
        save_json(output.with_name(f'{output.stem}-sample-{len(result["samples"])}{output.suffix}'), row)
        print(json.dumps({key: row.get(key) for key in
                          ('label', 'target_prompt_tokens', 'actual_prompt_tokens',
                           'actual_output_tokens', 'wall_seconds', 'error')}), flush=True)
        return row

    try:
        health, wall = bench.request_json(API + '/health', timeout=allowance(5))
        result['health'] = dict(response=health, wall_seconds=wall)
        if health.get('prompt_cache', {}).get('enabled') is not False:
            raise ValueError('Prompt cache must be disabled')
        base = run('calibration_base', 'x', 'serial', 1, None, 30, False)
        if not base['passed']:
            raise ValueError('Base calibration failed')
        expanded = run('calibration_filler20', 'x' + bench.FILLER * 20, 'serial', 1, None, 30, False)
        if not expanded['passed']:
            raise ValueError('Filler calibration failed')
        overhead = base['actual_prompt_tokens']
        growth = expanded['actual_prompt_tokens'] - overhead
        if overhead < 0 or growth <= 0:
            raise ValueError('Invalid calibration: filler token growth must be positive')
        try:
            per_filler = growth / 20.0
        except OverflowError as error:
            raise ValueError('Invalid calibration: nonfinite filler growth') from error
        if not math.isfinite(per_filler) or per_filler <= 0:
            raise ValueError('Invalid calibration: nonfinite filler growth')
        calibration = dict(overhead_tokens=overhead, tokens_per_filler=per_filler)
        result['calibration'] = calibration
        instruction = f'Start your answer with {MARKER}. Summarize the supplied filler in one sentence.'
        filler_bytes = len(bench.FILLER.encode('utf-8'))
        for target in (512, 260000):
            repeats = max(1, round(max(0, target - overhead) / per_filler))
            if repeats > MAX_FILLER_REPEATS or repeats * filler_bytes > MAX_PROMPT_BYTES:
                raise ValueError(f'Filler bound exceeded for target {target}: {repeats} repeats')
        small = bench.build_prompt(512, calibration, instruction) + f'\nStart with {MARKER}.'
        large = bench.build_prompt(260000, calibration, instruction) + f'\nStart with {MARKER}.'
        if max(len(small.encode('utf-8')), len(large.encode('utf-8'))) > MAX_PROMPT_BYTES:
            raise ValueError('Filler bound exceeded by built prompt bytes')
        for label, prompt, mode, target, cap in (
                ('small_serial', small, 'serial', 512, 30),
                ('small_mtp', small, 'mtp', 512, 30),
                ('large_mtp', large, 'mtp', 260000, large_request_seconds)):
            row = run(label, prompt, mode, 32, target, cap, True)
            if not row['passed']:
                raise ValueError(f'{label} failed; later requests skipped')
        if time.monotonic() - started >= deadline_seconds:
            raise TimeoutError(f'{deadline_seconds}-second context diagnostic deadline exhausted')
        result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        save_json(output, result)
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
