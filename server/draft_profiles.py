"""Create isolated Halogen/GUFO draft profiles without changing registered defaults."""
import argparse
import copy
import json
from pathlib import Path
from controller import (halogen_draft_arguments, halogen_kernel_arguments, halogen_kernel_module,
                        halogen_speculation_arguments, halogen_speculation_module,
                        halogen_lookup_arguments,
                        memory_reserve_gib, validate_engine,
                        validate_halogen_launcher_controls)


def replace_option(args, flag, value):
    count = args.count(flag)
    if count > 1 or (count and args.index(flag) + 1 >= len(args)):
        raise ValueError('Ambiguous native option: ' + flag)
    if count:
        args[args.index(flag) + 1] = str(value)
    else:
        args.extend([flag, str(value)])


def tune(source, *, draft_tokens, draft_vocab='full', mtp_policy='length',
         prefill_chunk=None, prompt_lookup=None, cache_disk=None, lookup_workload=None,
         prefill_keep_trunk=False, admit_ticks=None, kernel_controls=None, lookup_tuning=None,
         speculation_policy=None):
    if type(draft_tokens) is not int or draft_tokens not in (1, 2, 3):
        raise ValueError('Draft depth must be an integer from 1 through 3')
    if draft_vocab not in ('full', 'latin') or mtp_policy not in ('length', 'survival'):
        raise ValueError('Unsupported draft policy or vocabulary')
    if prefill_chunk is not None:
        context = source.get("backend", {}).get("context")
        if type(prefill_chunk) is not int or prefill_chunk not in (2048,4096,8192,16384,32768):
            raise ValueError("Prefill chunk must be 2048, 4096, 8192, 16384 or 32768")
        if type(context) is not int or prefill_chunk > context:
            raise ValueError("Prefill chunk exceeds the declared context")
    if prompt_lookup is not None and type(prompt_lookup) is not bool:
        raise ValueError("Prompt lookup must be an explicit boolean")
    if type(prefill_keep_trunk) is not bool: raise ValueError("Prefill keep trunk must be boolean")
    if admit_ticks is not None and (type(admit_ticks) is not int or not 1 <= admit_ticks <= 1024):
        raise ValueError("Admit ticks must be 1..1024")
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
        if prefill_keep_trunk: engine['prefill_keep_trunk'] = True
        if admit_ticks is not None: engine['admit_ticks'] = admit_ticks
        halogen_draft_arguments(engine)
        repo=Path(__file__).resolve().parents[1]
        validate_halogen_launcher_controls(engine,repo)
        if speculation_policy is not None or 'speculation_policy' in engine:
            if not isinstance(engine.get('directory'), str):
                raise ValueError('Speculation policy requires a declared Halogen backend')
            directory = (repo / engine['directory']).resolve()
            module = halogen_speculation_module(directory)
            if speculation_policy is not None:
                engine['speculation_policy'] = (module.parse(speculation_policy)
                    if isinstance(speculation_policy, str) else module.validate(speculation_policy))
            halogen_speculation_arguments(engine, directory)
        if lookup_tuning is not None:
            engine['lookup_tuning'] = copy.deepcopy(lookup_tuning)
        if 'lookup_tuning' in engine:
            directory=(repo/engine['directory']).resolve()
            halogen_lookup_arguments(engine,directory)
        if kernel_controls is not None or 'kernel_controls' in engine:
            if not isinstance(engine.get('directory'),str):
                raise ValueError('Kernel controls require a declared Halogen backend')
            directory=(repo/engine['directory']).resolve()
            if not directory.is_relative_to((repo/'backends').resolve()):
                raise ValueError('Halogen backend directory is outside this repository')
            if kernel_controls is not None:
                module=halogen_kernel_module(directory)
                engine['kernel_controls']=(module.parse(kernel_controls) if isinstance(kernel_controls,str)
                                           else module.validate(kernel_controls))
            halogen_kernel_arguments(engine,directory)
    elif backend == 'gufo-flash-next' and engine.get('kind') == 'native':
        if (prefill_keep_trunk or admit_ticks is not None or kernel_controls is not None
                or lookup_tuning is not None or 'lookup_tuning' in engine
                or speculation_policy is not None or 'speculation_policy' in engine):
            raise ValueError('Halogen-only prefill controls do not apply to GUFO')
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
    if prefill_keep_trunk: result['qualification']['prefill_keep_trunk']=True
    if admit_ticks is not None: result['qualification']['admit_ticks']=admit_ticks
    if 'kernel_controls' in engine:
        result['qualification']['kernel_controls']=copy.deepcopy(engine['kernel_controls'])
    if 'lookup_tuning' in engine:
        result['qualification']['lookup_tuning']=copy.deepcopy(engine['lookup_tuning'])
    if 'speculation_policy' in engine:
        result['qualification']['speculation_policy']=copy.deepcopy(engine['speculation_policy'])
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
    p.add_argument('--prefill-chunk',type=int,choices=(2048,4096,8192,16384,32768))
    p.add_argument('--prefill-keep-trunk',action='store_true')
    p.add_argument('--admit-ticks',type=int)
    p.add_argument('--kernel-controls-json',help='Explicit experimental HALOGEN_* numeric controls as a JSON object')
    p.add_argument('--speculation-policy-json',help='Opt-in HALOGEN_PLD / HALOGEN_SPEC_ADAPT off or stock strings')
    p.add_argument('--lookup-receipt',type=Path)
    p.add_argument('--lookup-receipt-sha256')
    p.add_argument('--prompt-lookup',action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--lookup-workload',choices=('copy','prose'))
    p.add_argument('--cache-disk',type=Path)
    a = p.parse_args()
    if bool(a.lookup_receipt) != bool(a.lookup_receipt_sha256):
        p.error('Lookup experiment requires both receipt path and its reviewed SHA256')
    if a.output.exists() or a.output.resolve() == a.source.resolve():
        raise ValueError('Existing source and destination profiles are never overwritten')
    source = json.loads(a.source.read_text(encoding='utf-8-sig'))
    result = tune(source, draft_tokens=a.draft_tokens,
                  draft_vocab=a.draft_vocab, mtp_policy=a.mtp_policy,
                  prefill_chunk=a.prefill_chunk, prompt_lookup=a.prompt_lookup,
                  cache_disk=a.cache_disk, lookup_workload=a.lookup_workload,
                  prefill_keep_trunk=a.prefill_keep_trunk, admit_ticks=a.admit_ticks,
                  kernel_controls=a.kernel_controls_json,
                  speculation_policy=a.speculation_policy_json,
                  lookup_tuning=({'receipt':str(a.lookup_receipt.absolute()),
                                  'receipt_sha256':a.lookup_receipt_sha256}
                                 if a.lookup_receipt else None))
    validate_engine(result['engine'], Path(__file__).resolve().parents[1])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print('Created isolated draft profile. No engine started; registered default unchanged.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
