"""One bounded, four-response hybrid48 qualification using the comparison contract."""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    output = parser.parse_args().output
    if output.exists():
        raise SystemExit('Refusing to overwrite existing qualification')
    output.parent.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('comparison', root / 'scripts/compare-halogen-modes.py')
    comparison = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparison)
    health, _ = comparison.BENCH.request_json('http://127.0.0.1:8731/health', timeout=5)
    if health.get('prompt_cache', {}).get('enabled') is not False:
        raise RuntimeError('Prompt cache must be disabled')
    case = comparison.cases('draft')[0]
    schedule = [('prose', mode, rep) for mode, rep in
                (('serial', 1), ('mtp', 1), ('mtp', 2), ('serial', 2))]
    result = dict(schema='hybrid48-prose-qualification-v1', health=health, samples=[],
                  created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  method='128-token cap, temperature0, cache0, serial/MTP/MTP/serial; no OS cache flush',
                  expected_schedule=schedule, max_tokens=128, timeout_seconds=90)
    for name, mode, rep in schedule:
        body = comparison.payload(case, mode, 128)
        row = dict(case=name, drafter=mode, repetition=rep, request=body,
                   prompt_sha256=hashlib.sha256(case['prompt'].encode()).hexdigest())
        try:
            response, wall = comparison.BENCH.request_json(
                'http://127.0.0.1:8731/v1/chat/completions', body, timeout=90)
            row['response'] = response
            row.update(comparison.BENCH.extract_measurement(response, wall, case['marker']))
        except Exception as error:
            row.update(error=repr(error), nonempty=False)
        result['samples'].append(row)
        result['gates'] = comparison.gates(result['samples'], schedule)
        # One immutable record per completed request; the summary is written only at the end.
        sample_path = output.with_name(f'{output.stem}-sample-{len(result["samples"])}{output.suffix}')
        with sample_path.open('x', encoding='utf-8') as stream:
            json.dump(row, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        print(json.dumps({key: row.get(key) for key in ('drafter', 'repetition',
            'prompt_tokens', 'completion_tokens', 'wall_seconds', 'cache_tokens', 'error')}), flush=True)
        if row.get('error') or not row.get('nonempty') or not row.get('marker_present'):
            break
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return 0 if len(result['samples']) == 4 and result['gates']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
