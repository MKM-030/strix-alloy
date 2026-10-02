"""Matched PP/TG and three-turn coding benchmark for one already-managed engine."""
import argparse
import json
import pathlib
import statistics
import sys
import time

from reddit_runtime import ManagedClient, ROOT, save_json
from reddit_suite import LADDER_SIZES, PROMPT_SIZES, digest, make_prompt, modes_for_profile


def coding_turns():
    return [
        'You are editing a Python project. We need to fix parse_port to reject booleans and out-of-range ports. First return only JSON: {"tool":"read_file","arguments":{"path":"config.py"}}.',
        'Tool read_file result: config.py contains `def parse_port(value): return int(value)` and tests require an integer from 1 through 65535, with ValueError for bool, zero and 65536. Write a minimal replacement function as Python code.',
        'The test runner reports that parse_port(True) must raise ValueError. Review your change, then give the exact two pytest assertions for True and 65536. No filesystem actions.',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=pathlib.Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--tokenizer', type=pathlib.Path, required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    parser.add_argument('--mode', choices=('serial', 'speculative', 'both'), required=True)
    parser.add_argument('--reps', type=int, default=2)
    parser.add_argument('--ladder-max', type=int, choices=LADDER_SIZES, default=65536)
    args = parser.parse_args()
    if not 1 <= args.reps <= 5:
        parser.error('Use 1..5 repetitions')
    if not args.out.resolve().is_relative_to((ROOT / 'server/.local').resolve()):
        parser.error('Raw benchmark output must be under server/.local')
    client = ManagedClient(args.profile, args.run_id)
    available = modes_for_profile(client.profile)
    requested = available if args.mode == 'both' else (args.mode,)
    if not set(requested).issubset(available):
        parser.error('This native profile cannot switch decoding mode per request')
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    context = client.profile['backend']['context']
    cases = {size: make_prompt(size, tokenizer) for size in
             PROMPT_SIZES + tuple(size for size in LADDER_SIZES if size <= args.ladder_max)}
    occupied_cases = {size: make_prompt(size, tokenizer, task='generation')
                      for size in LADDER_SIZES if size <= args.ladder_max}
    args.out.mkdir(parents=True, exist_ok=False)
    identity = {'backend': client.model, 'run_id': args.run_id, 'profile': client.profile,
                'profile_sha256': client.profile_sha256, 'tokenizer_sha256': digest(args.tokenizer.read_bytes()),
                'harness_sha256': digest(pathlib.Path(__file__).read_bytes()),
                'suite_sha256': digest((pathlib.Path(__file__).with_name('reddit_suite.py')).read_bytes()),
                'modes': requested, 'reps': args.reps, 'ladder_max': args.ladder_max,
                'context_capacity': context, 'prompt_text_tokens': {
                    str(size): len(tokenizer.encode(text, add_special_tokens=False).ids)
                    for size, text in cases.items()},
                'prompt_sha256': {str(size): digest(text.encode('utf-8')) for size, text in cases.items()},
                'occupied_prompt_sha256': {str(size): digest(text.encode('utf-8'))
                                           for size, text in occupied_cases.items()},
                'occupied_prompt_text_tokens': {str(size): len(tokenizer.encode(
                    text, add_special_tokens=False).ids) for size, text in occupied_cases.items()},
                'note': 'PP labels target text tokens; actual server prompt_tokens include backend chat framing.'}
    save_json(args.out / 'identity.json', identity)
    rows = []

    def sample(messages, limit, mode, label, rep, cold=False):
        row = client.call(messages, limit, mode, label, cold=cold)
        row['rep'] = rep
        rows.append(row)
        with (args.out / 'samples.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(label, mode, rep, row['usage'].get('prompt_tokens'),
              row['usage'].get('completion_tokens'), round(row['wall_seconds'], 3), flush=True)
        return row

    summary = {'identity_sha256': digest((args.out / 'identity.json').read_bytes()),
               'passed_execution': False, 'rows': 0, 'started_at': time.time()}
    try:
        with (args.out / 'warmups.jsonl').open('x', encoding='utf-8') as stream:
            for mode in requested:
                warmup = client.call([{'role': 'user', 'content':
                    'Write two sentences about a river town.'}], 16, mode, 'warmup', cold=True)
                stream.write(json.dumps(warmup, ensure_ascii=False) + '\n')
        for rep in range(args.reps):
            for size in PROMPT_SIZES:
                if size + 256 > context:
                    continue
                mode = 'serial' if 'serial' in requested else requested[0]
                prefill = sample([{'role': 'user', 'content': cases[size]}], 1, mode,
                                 f'PP{size}', rep, cold=True)
                if prefill['usage'].get('completion_tokens', prefill['timings'].get('predicted_n')) != 1:
                    raise ValueError('PP probe did not produce one token; sample retained')
            for mode in requested:
                tg = sample([{'role': 'user', 'content':
                    'Write a detailed original story about a river town. Continue until the token limit.'}],
                    128, mode, 'TG128', rep, cold=True)
                if tg['usage'].get('completion_tokens', tg['timings'].get('predicted_n')) != 128:
                    raise ValueError('TG128 ended early; sample retained, benchmark not qualified')
            mode = requested[-1]
            messages = []
            for turn, instruction in enumerate(coding_turns(), 1):
                messages.append({'role': 'user', 'content': instruction})
                response = sample(messages, 128, mode, f'coding_tool_turn{turn}', rep)
                messages.append({'role': 'assistant', 'content': response['text']})
            for size in LADDER_SIZES:
                if size > args.ladder_max or size + 512 > context:
                    continue
                occupied = sample([{'role': 'user', 'content': occupied_cases[size]}],
                                  128, mode, f'occupied{size}_TG128', rep, cold=True)
                if occupied['usage'].get('completion_tokens', occupied['timings'].get('predicted_n')) != 128:
                    raise ValueError('Occupied TG128 ended early; sample retained, benchmark not qualified')
        summary['passed_execution'] = True
    except Exception as exc:
        summary['error'] = type(exc).__name__ + ': ' + str(exc)
        print('BENCHMARK_ERROR', summary['error'], flush=True)
    finally:
        summary['rows'] = len(rows)
        summary['finished_at'] = time.time()
        summary['minimum_memory'] = {key: min(row['minimum_memory'][key] for row in rows)
                                     for key in ('available_bytes', 'commit_headroom_bytes')} if rows else None
        summary['wall_seconds'] = sum(row['wall_seconds'] for row in rows)
        summary['cases'] = []
        for label, mode in sorted({(row['name'], row['mode']) for row in rows}):
            group = [row for row in rows if row['name'] == label and row['mode'] == mode]
            drafted = [row for row in group if isinstance(row['drafted'], int) and
                       isinstance(row['accepted'], int)]
            total_drafted = sum(row['drafted'] for row in drafted)
            summary['cases'].append({'name': label, 'mode': mode, 'samples': len(group),
                'mean_wall_seconds': statistics.fmean(row['wall_seconds'] for row in group),
                'prompt_tokens': sorted({row['usage'].get('prompt_tokens', row['timings'].get('prompt_n'))
                                         for row in group}),
                'output_tokens': sorted({row['usage'].get('completion_tokens', row['timings'].get('predicted_n'))
                                         for row in group}),
                'draft_acceptance': sum(row['accepted'] for row in drafted) / total_drafted
                                    if total_drafted else None,
                'deterministic_hashes_match': len({row['sha256'] for row in group}) == 1})
        if summary['passed_execution'] and any(not row['deterministic_hashes_match']
                                               for row in summary['cases']):
            summary['passed_execution'] = False
            summary['error'] = 'Repeated deterministic output hashes changed'
        save_json(args.out / 'summary.json', summary)
    return 0 if summary['passed_execution'] else 2


if __name__ == '__main__':
    sys.exit(main())
