"""Create an isolated GUFO autoregressive control; never register or start it."""
import argparse
import copy
import json
from pathlib import Path

from controller import memory_reserve_gib, validate_engine


def serial_profile(source):
    if (source.get('backend', {}).get('identifier') != 'gufo-flash-next' or
            source.get('engine', {}).get('kind') != 'native' or
            source['engine'].get('qualified') is not True):
        raise ValueError('An existing qualified GUFO profile is required')
    result = copy.deepcopy(source)
    original = result['engine']['command']
    pairs = ('--mtp-model', '--draft-tokens', '--mtp-policy', '--mtp-draft-vocab')
    for flag in pairs + ('--speculative',):
        if original.count(flag) > 1:
            raise ValueError('Ambiguous GUFO option: ' + flag)
    if (original.count('--mtp-model') != 1 or original.count('--speculative') != 1 or
            original[original.index('--speculative') + 1] != 'mtp' or
            original.count('--prompt-lookup') > 1):
        raise ValueError('Source must be an unambiguous MTP profile')
    command = []
    position = 0
    while position < len(original):
        flag = original[position]
        if flag in pairs:
            if position + 1 >= len(original):
                raise ValueError('Incomplete GUFO option: ' + flag)
            position += 2
        elif flag == '--prompt-lookup':
            position += 1
        else:
            command.append('off' if position > 0 and original[position - 1] == '--speculative' else flag)
            position += 1
    result['engine']['command'] = command
    result['minimum_reserve_gib'] = max(18, memory_reserve_gib(source))
    result.setdefault('qualification', {}).update(
        experimental=True, decoding_mode='serial', prompt_lookup=False,
        tuning_evidence='docs/research/reddit-prefill-decode-20261001.md')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.source.resolve():
        raise ValueError('Source and existing profiles cannot be overwritten')
    source = json.loads(args.source.read_text(encoding='utf-8-sig'))
    result = serial_profile(source)
    validate_engine(result['engine'], Path(__file__).resolve().parents[1])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print('Wrote isolated GUFO serial profile; no engine or registered default changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
