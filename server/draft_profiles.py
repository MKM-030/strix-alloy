"""Create isolated Halogen/GUFO draft profiles without changing registered defaults."""
import argparse
import copy
import json
from pathlib import Path
from controller import memory_reserve_gib, validate_engine


def replace_option(args, flag, value):
    count = args.count(flag)
    if count > 1 or (count and args.index(flag) + 1 >= len(args)):
        raise ValueError('Ambiguous native option: ' + flag)
    if count:
        args[args.index(flag) + 1] = str(value)
    else:
        args.extend([flag, str(value)])


def tune(source, *, draft_tokens, draft_vocab='full', mtp_policy='length',
         prefill_chunk=None, prompt_lookup=None, cache_disk=None, lookup_workload=None):
    if type(draft_tokens) is not int or draft_tokens not in (1, 2, 3):
        raise ValueError('Draft depth must be an integer from 1 through 3')
    if draft_vocab not in ('full', 'latin') or mtp_policy not in ('length', 'survival'):
        raise ValueError('Unsupported draft policy or vocabulary')
    if prefill_chunk is not None:
        context = source.get("backend", {}).get("context")
        if type(prefill_chunk) is not int or prefill_chunk not in (2048,4096,8192):
            raise ValueError("Prefill chunk must be 2048, 4096 or 8192")
        if type(context) is not int or prefill_chunk > context:
            raise ValueError("Prefill chunk exceeds the declared context")
    if prompt_lookup is not None and type(prompt_lookup) is not bool:
        raise ValueError("Prompt lookup must be an explicit boolean")
    if lookup_workload not in (None, 'copy', 'prose'):
        raise ValueError('Lookup workload must be copy or prose')
    if lookup_workload is not None:
        if source.get('backend', {}).get('identifier') != 'gufo-flash-next':
            raise ValueError('Lookup workload is GUFO-specific')
        selected = lookup_workload == 'copy'
        if prompt_lookup is not None and prompt_lookup != selected:
            raise ValueError('Lookup switch conflicts with the explicit workload')
        prompt_lookup = selected
    if cache_disk is not None:
        local = (Path(__file__).resolve().parent / '.local').resolve()
        cache_disk = Path(cache_disk).resolve()
        if cache_disk == local or not cache_disk.is_relative_to(local):
            raise ValueError('GUFO cache must stay under server/.local')
    result = copy.deepcopy(source)
    engine = result.get('engine', {})
    backend = result.get('backend', {}).get('identifier')
    if backend in ('halogen-v2', 'halogen-w4b') and engine.get('kind') == 'halogen':
        if draft_vocab != 'full' or mtp_policy != 'length':
            raise ValueError('GUFO-specific options do not apply to Halogen')
        if prompt_lookup is not None:
            raise ValueError('GUFO prompt lookup does not apply to Halogen')
        engine['draft_tokens'] = draft_tokens
        if prefill_chunk is not None: engine['prefill_chunk'] = prefill_chunk
    elif backend == 'gufo-flash-next' and engine.get('kind') == 'native':
        if engine.get('qualified') is not True:
            raise ValueError('Retain a previously qualified GUFO runtime')
        args = engine['command']
        if '--mtp-model' not in args or '--speculative' not in args:
            raise ValueError('A registered MTP model is required')
        if args[args.index('--speculative') + 1] != 'mtp':
            raise ValueError('Source is not an MTP configuration')
        replace_option(args, '--draft-tokens', draft_tokens)
        replace_option(args, '--mtp-draft-vocab', draft_vocab)
        replace_option(args, '--mtp-policy', mtp_policy)
        if prefill_chunk is not None: replace_option(args, '--prefill-chunk', prefill_chunk)
        if args.count('--prompt-lookup')>1: raise ValueError('Duplicate prompt lookup option')
        if prompt_lookup is False and '--prompt-lookup' in args: args.remove('--prompt-lookup')
        if prompt_lookup is True and '--prompt-lookup' not in args: args.append('--prompt-lookup')
        if cache_disk is not None:
            replace_option(args, '--cache-disk', cache_disk)
            replace_option(args, '--cache-disk-staging-bytes', 4294967296)
            replace_option(args, '--cache-disk-bytes', 8589934592)
    else:
        raise ValueError('Only existing Halogen and GUFO profiles are supported')
    if cache_disk is not None and backend != 'gufo-flash-next':
        raise ValueError('Disk cache option only applies to GUFO')
    result['minimum_reserve_gib'] = max(18, memory_reserve_gib(source))
    result.setdefault('qualification', {}).update(
        experimental=True, draft_tokens=draft_tokens, draft_vocab=draft_vocab,
        mtp_policy=mtp_policy, weight_placement='unchanged-backend-native',
        tuning_evidence='docs/research/halogen-gufo-mtp-20261001.md')
    if prefill_chunk is not None: result['qualification']['prefill_chunk']=prefill_chunk
    if prompt_lookup is not None: result['qualification']['prompt_lookup']=prompt_lookup
    if lookup_workload is not None: result['qualification']['lookup_workload']=lookup_workload
    if cache_disk is not None: result['qualification']['cache_disk']=str(cache_disk)
    if prefill_chunk is not None or prompt_lookup is not None:
        result['qualification']['tuning_evidence']='docs/research/reddit-prefill-decode-20261001.md'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--draft-tokens', type=int, choices=(1, 2, 3), required=True)
    p.add_argument('--draft-vocab', choices=('full', 'latin'), default='full')
    p.add_argument('--mtp-policy', choices=('length', 'survival'), default='length')
    p.add_argument('--prefill-chunk',type=int,choices=(2048,4096,8192))
    p.add_argument('--prompt-lookup',action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--lookup-workload',choices=('copy','prose'))
    p.add_argument('--cache-disk',type=Path)
    a = p.parse_args()
    if a.output.exists() or a.output.resolve() == a.source.resolve():
        raise ValueError('Existing source and destination profiles are never overwritten')
    source = json.loads(a.source.read_text(encoding='utf-8-sig'))
    result = tune(source, draft_tokens=a.draft_tokens,
                  draft_vocab=a.draft_vocab, mtp_policy=a.mtp_policy,
                  prefill_chunk=a.prefill_chunk, prompt_lookup=a.prompt_lookup,
                  cache_disk=a.cache_disk, lookup_workload=a.lookup_workload)
    validate_engine(result['engine'], Path(__file__).resolve().parents[1])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print('Created isolated draft profile. No engine started; registered default unchanged.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
