"""Bounded two/three-client qualification of one shared 32k KV pool."""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import math
import pathlib
import subprocess
import sys
import threading
import time


API = 'http://127.0.0.1:8731'
POOL_POSITIONS = 32768
TARGET_INPUT_TOKENS = 8192
OUTPUT_CAP = 128
MAX_FILLER_REPEATS = 100000
MAX_PROMPT_BYTES = 16 * 1024 * 1024
REQUEST_TAIL_MARGIN_SECONDS = 10


class BoundedBenchmarkTransport:
    """Run each benchmark HTTP call in a child with an absolute parent timeout."""

    def __init__(self, bench, child_script: pathlib.Path | None = None):
        self.FILLER = bench.FILLER
        self.build_prompt = bench.build_prompt
        self.extract_measurement = bench.extract_measurement
        self.child_script = child_script or pathlib.Path(__file__).resolve()

    def request_json(self, url: str, body: dict | None = None, timeout: float = 30):
        if not math.isfinite(timeout) or timeout <= 0:
            raise TimeoutError('request allowance exhausted before child launch')
        payload = json.dumps(dict(url=url, body=body, timeout=timeout)).encode('utf-8')
        started = time.perf_counter()
        process = None
        try:
            process = subprocess.Popen([sys.executable, str(self.child_script), '--request-child'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            left = timeout - (time.perf_counter() - started)
            if left <= 0:
                raise TimeoutError('request child launch exceeded absolute timeout')
            try:
                raw, stderr = process.communicate(payload, timeout=left)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError('request child exceeded absolute timeout') from error
            if time.perf_counter() - started > timeout:
                raise TimeoutError('request child response arrived after absolute timeout')
            if process.returncode != 0:
                raise RuntimeError(f'request child failed ({process.returncode}): '
                                   + stderr.decode('utf-8', errors='replace')[-500:])
            packet = json.loads(raw)
            return packet['response'], packet['wall_seconds']
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError('killed request child did not terminate within 5 seconds') from error
                if process.poll() is None:
                    raise RuntimeError('killed request child is still running')


def request_child() -> int:
    request = json.load(sys.stdin)
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('halogen_benchmark', root / 'scripts/benchmark-halogen.py')
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    response, wall = bench.request_json(request['url'], request['body'], timeout=request['timeout'])
    json.dump(dict(response=response, wall_seconds=wall), sys.stdout, ensure_ascii=True)
    return 0


def request_body(prompt: str, output_tokens: int, drafter: str) -> dict:
    return dict(messages=[dict(role='user', content=prompt)], max_tokens=output_tokens,
                temperature=0, enable_thinking=False, reasoning_effort='low',
                drafter=drafter)


def save_json(path: pathlib.Path, value: dict) -> None:
    def safe(item):
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, dict):
            return {key: safe(part) for key, part in item.items()}
        if isinstance(item, (list, tuple)):
            return [safe(part) for part in item]
        return item

    with path.open('x', encoding='utf-8') as stream:
        json.dump(safe(value), stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def exact_count(value, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'invalid {label}: expected integer >= {minimum}')
    return value


def positive_finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'invalid {label}: expected positive finite number')
    return float(value)


def check_health(health: dict) -> None:
    if not isinstance(health, dict):
        raise ValueError('invalid health response')
    if health.get('prompt_cache', {}).get('enabled') is not False:
        raise ValueError('health prompt_cache.enabled must be false')
    if health.get('version', {}).get('match') is not True:
        raise ValueError('health version.match must be true')
    for key, expected in (('context', POOL_POSITIONS), ('slot_ctx', POOL_POSITIONS),
                          ('kv_pool_positions', POOL_POSITIONS), ('slots', 3)):
        if type(health.get(key)) is not int or health[key] != expected:
            raise ValueError(f'health {key} must be {expected}')


def check_counts(response: dict, *, measured: bool, group_size: int = 0) -> tuple[int, int]:
    if not isinstance(response, dict) or not isinstance(response.get('usage'), dict):
        raise ValueError('response lacks usage counts')
    usage = response['usage']
    prompt = exact_count(usage.get('prompt_tokens'), 'prompt_tokens', 1)
    output = exact_count(usage.get('completion_tokens'), 'completion_tokens', 1)
    if measured:
        if output > OUTPUT_CAP:
            raise ValueError('actual output exceeds request cap')
        if prompt + OUTPUT_CAP > POOL_POSITIONS // group_size:
            raise ValueError('actual input plus output cap exceeds fair share of KV pool')
    return prompt, output


def check_measurement(response: dict, row: dict, bench, group_size: int) -> None:
    prompt, output = check_counts(response, measured=True, group_size=group_size)
    timings = response.get('timings')
    if not isinstance(timings, dict):
        raise ValueError('response lacks engine timings')
    for key in ('prompt_ms', 'predicted_ms', 'prompt_per_second', 'predicted_per_second'):
        positive_finite(timings.get(key), key)
    if type(timings.get('cache_n')) is not int or timings['cache_n'] != 0:
        raise ValueError('prompt cache was active or unreported')
    identifier = response.get('id')
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError('missing request id')
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError('response lacks a valid choice')
    message = choices[0].get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip() or row['marker'] not in content:
        raise ValueError('answer must be a nonempty string with the correct marker')
    measurement = bench.extract_measurement(response, row['wall_seconds'], row['marker'])
    row.update(measurement)
    row['request_id'] = identifier
    row['actual_prompt_tokens'] = prompt
    row['actual_output_tokens'] = output
    row['cache_tokens'] = 0
    row['content'] = content
    row['marker_present'] = True
    row['nonempty'] = True
    row['passed'] = True


def run_qualification(bench, output: pathlib.Path, deadline_seconds: int = 300) -> int:
    if not 1 <= deadline_seconds <= 300:
        raise ValueError('deadline must be within 1..300 seconds')
    if output.exists():
        raise FileExistsError(f'refusing to overwrite {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = dict(schema='hybrid48-sessions-v1', mode='PreflightSessions32k',
                  created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  deadline_seconds=deadline_seconds, pool_positions=POOL_POSITIONS,
                  slot_count=3, shared_pool_note='All clients share one 32768-position KV pool; '
                  'this does not establish three full-context sessions or three models.',
                  requested_drafter='mtp',
                  drafter_note='The engine may schedule a group serially or in batches; '
                  'MTP activation and GPU overlap are not inferred from client overlap.',
                  throughput_label='End-to-end output tokens per second, including prefill; '
                  'not pure aggregate decode rate.',
                  health=None, calibration=None, groups=[], successful_sessions=0,
                  passed=False, error=None)

    def allowance(cap: float, reserve: float = 0) -> float:
        left = deadline_seconds - (time.monotonic() - started) - reserve
        if left <= 0:
            raise TimeoutError('sessions probe deadline exhausted')
        return min(cap, left)

    def request(url: str, body: dict | None, cap: float):
        timeout = allowance(cap, REQUEST_TAIL_MARGIN_SECONDS)
        call_started = time.monotonic()
        response, wall = bench.request_json(url, body, timeout=timeout)
        if time.monotonic() - call_started > timeout or time.monotonic() - started >= deadline_seconds:
            raise TimeoutError('request exceeded its absolute or global deadline')
        return response, wall

    try:
        health, health_wall = request(API + '/health', None, 5)
        result['health'] = dict(response=health, wall_seconds=health_wall)
        check_health(health)
        calibration = []
        result['calibration'] = dict(samples=calibration, fit=None)
        for label, prompt in (('base', 'x'), ('filler20', 'x' + bench.FILLER * 20)):
            body = request_body(prompt, 1, 'serial')
            response, wall = request(API + '/v1/chat/completions', body, 30)
            prompt_count, output_count = check_counts(response, measured=False)
            calibration.append(dict(label=label, request=body, response=response,
                                    wall_seconds=positive_finite(wall, 'calibration wall time'),
                                    actual_prompt_tokens=prompt_count,
                                    actual_output_tokens=output_count))
        growth = calibration[1]['actual_prompt_tokens'] - calibration[0]['actual_prompt_tokens']
        per_filler = growth / 20.0
        if growth <= 0 or not math.isfinite(per_filler) or per_filler <= 0:
            raise ValueError('invalid calibration: filler token growth must be positive finite')
        fit = dict(overhead_tokens=calibration[0]['actual_prompt_tokens'],
                   tokens_per_filler=per_filler)
        result['calibration']['fit'] = fit
        repeats = max(1, round(max(0, TARGET_INPUT_TOKENS - fit['overhead_tokens']) / per_filler))
        if repeats > MAX_FILLER_REPEATS or repeats * len(bench.FILLER.encode('utf-8')) > MAX_PROMPT_BYTES:
            raise ValueError('calibration filler bound exceeded')

        seen_request_ids = set()
        for group_size in (2, 3):
            prompts = []
            for index in range(1, group_size + 1):
                marker = f'GROUP-{group_size}-SESSION-{index:02d}'
                instruction = (f'Begin with the exact marker {marker}. '
                               'Explain why independent inference sessions matter; continue to the output cap.')
                prompt = bench.build_prompt(TARGET_INPUT_TOKENS, fit, instruction)
                if len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES:
                    raise ValueError('built prompt exceeds byte bound')
                prompts.append((marker, prompt))
            barrier = threading.Barrier(group_size)
            group_started = time.perf_counter()

            def one(item):
                marker, prompt = item
                body = request_body(prompt, OUTPUT_CAP, 'mtp')
                row = dict(group_size=group_size, marker=marker, requested_drafter='mtp',
                           request=body, response=None, actual_prompt_tokens=None,
                           actual_output_tokens=None, prompt_ms=None, generation_ms=None,
                           prompt_tokens_per_second=None, generation_tokens_per_second=None,
                           cache_tokens=None, content=None, request_id=None,
                           client_start_seconds=None, client_end_seconds=None,
                           wall_seconds=None, nonempty=False, marker_present=False,
                           passed=False, error=None)
                try:
                    barrier.wait(timeout=allowance(10, REQUEST_TAIL_MARGIN_SECONDS))
                    row['client_start_seconds'] = time.perf_counter()
                    response, wall = request(API + '/v1/chat/completions', body, 90)
                    row['client_end_seconds'] = time.perf_counter()
                    row['wall_seconds'] = positive_finite(wall, 'client wall time')
                    row['response'] = response
                    check_measurement(response, row, bench, group_size)
                except Exception as error:
                    if row['client_start_seconds'] is not None and row['client_end_seconds'] is None:
                        row['client_end_seconds'] = time.perf_counter()
                    if row['wall_seconds'] is None and row['client_start_seconds'] is not None:
                        row['wall_seconds'] = row['client_end_seconds'] - row['client_start_seconds']
                    row['error'] = repr(error)
                session_number = marker.rsplit('-', 1)[-1]
                save_json(output.with_name(
                    f'{output.stem}-group-{group_size}-session-{session_number}{output.suffix}'), row)
                return row

            with concurrent.futures.ThreadPoolExecutor(max_workers=group_size) as executor:
                rows = list(executor.map(one, prompts))
            group_wall = time.perf_counter() - group_started
            ids = [row['request_id'] for row in rows if row['passed']]
            contents = [row['content'] for row in rows if row['passed']]
            unique_ids = len(ids) == len(set(ids)) and not (set(ids) & seen_request_ids)
            unique_outputs = len(contents) == len(set(contents))
            seen_request_ids.update(ids)
            successful = [row for row in rows if row['passed']]
            starts = [row['client_start_seconds'] for row in successful]
            ends = [row['client_end_seconds'] for row in successful]
            overlap = min(ends) - max(starts) if len(successful) == group_size else 0.0
            group = dict(requested_sessions=group_size, successful_sessions=len(successful),
                         group_wall_seconds=group_wall,
                         end_to_end_output_tokens_per_second=(
                             sum(row['actual_output_tokens'] for row in successful) / group_wall),
                         throughput_label=result['throughput_label'],
                         latency_min_seconds=min((row['wall_seconds'] for row in successful), default=None),
                         latency_max_seconds=max((row['wall_seconds'] for row in successful), default=None),
                         client_overlap_seconds=overlap,
                         unique_response_ids=unique_ids, unique_outputs=unique_outputs,
                         error=('duplicate response id or content' if not unique_ids or not unique_outputs else None),
                         all_sessions_succeeded=(len(successful) == group_size and overlap > 0 and
                                                 unique_ids and unique_outputs),
                         sessions=rows)
            result['groups'].append(group)
            result['successful_sessions'] += len(successful)
            if not group['all_sessions_succeeded']:
                raise ValueError(f'group {group_size} failed; later groups skipped')
        allowance(0.001)
        result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        save_json(output, result)
    return 0 if result['passed'] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--deadline-seconds', type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.deadline_seconds <= 300:
        parser.error('deadline-seconds may only shrink the 300-second probe limit')
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('halogen_benchmark', root / 'scripts/benchmark-halogen.py')
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    return run_qualification(BoundedBenchmarkTransport(bench), args.output, args.deadline_seconds)


if __name__ == '__main__':
    raise SystemExit(request_child() if sys.argv[1:] == ['--request-child'] else main())
