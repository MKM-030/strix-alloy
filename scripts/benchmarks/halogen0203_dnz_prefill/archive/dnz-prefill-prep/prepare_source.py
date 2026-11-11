"""Prepare a private DNZ source set; no install, process, DLL or API action.

Default CLI is inert. --prepare only reads verified local evidence/sources and
writes a fresh private directory. Root separately reviews and seals execution.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(r'C:\Projects\strix-alloy-clean')
HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
FROZEN = PRIMARY / 'real-npu-v4-prep'
OLD = ROOT / 'server/.local/halogen-update-20261110/primary0201'
PACKAGE = ROOT / 'backends/halogen-wsl2-0.20.3'
NORMAL = PRIMARY / 'serving0203-text32k-8192.json'
NORMAL_SHA = 'dfa4b82b5de41cadbb3d3a5ed89b243d53112cbf9729e2de45c5f0e3958cb430'
SOURCE_SHA = 'c32138235c3847dfe29576d9ed634e4686f2ddc203ac718395444b7784804492'
TRANSITION_SHA = '84ff46e90613363ca3df9d6d6447e8d0865ac25c819d2295be3978b10a34f8f1'
RAW_SHA = 'cc898ddb875402902e52b401416f61b9b8c662a54f540ca871047fd970cdca8f'
ARMS = ('before', 'candidate', 'after')
SCHEMA = 'halogen0203.DNZ-cohort-bindings.v1'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(path):
    path = Path(path)
    need(not any(item.is_symlink() or getattr(item, 'is_junction', lambda: False)()
                 for item in (path, *path.parents)), 'Linked source/evidence path')
    return path


def read(path):
    return json.loads(safe(path).read_bytes())


def pin(path):
    path = safe(path).resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=sha(data))


def verify_pins(pins):
    for expected in pins:
        need(pin(expected['path']) == expected, 'Frozen dependency changed: ' + expected['path'])


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def profiles(normal):
    engine = normal['engine']
    need(engine['directory'] == 'backends/halogen-wsl2-0.20.3'
         and engine['context'] == engine['kv_pool_positions'] == 32768
         and engine['slots'] == normal['concurrency'] == 1
         and engine['prefill_chunk'] == engine['max_prefill_tokens'] == 8192
         and engine['prompt_cache'] == 'Off' and engine['disable_vision'] is True
         and engine['speculation_policy'] == {'HALOGEN_PLD': '3,3', 'HALOGEN_MTP_GATE_P': '0.90'}
         and engine['api_defaults']['enable_thinking'] is False
         and normal['minimum_reserve_gib'] == 18, 'Frozen32K/8192 text policy differs')
    need(engine['kernel_controls'] == {'HALOGEN_DECODE_PREFETCH': 0},
         'Normal kernel controls have unreviewed changes')
    result = {}
    for arm in ARMS:
        value = copy.deepcopy(normal)
        value['engine']['kernel_controls'].update(
            HALOGEN_PHASE_RAW=1, HALOGEN_SERVE_TRACE=1,
            HALOGEN_DN_Z_STREAM=int(arm == 'candidate'))
        result[arm] = value
    return result


def extend_controls(source):
    anchor = b"'DECODE_PREFETCH','EXTERNAL_STREAM'"
    need(source.count(anchor) == 1 and b"'DN_Z_STREAM'" not in source,
         'Exact private switch anchor differs')
    result = source.replace(anchor, b"'DECODE_PREFETCH','DN_Z_STREAM','EXTERNAL_STREAM'")
    ast.parse(result)
    return result


def materialize(output, baseline, candidate):
    output = safe(output)
    for name in set(baseline) | set(candidate):
        relative = Path(name)
        need(not relative.is_absolute() and '..' not in relative.parts
             and ':' not in name and '\\' not in name, 'Nonfinite overlay member')
    need(set(baseline) <= set(candidate), 'Baseline member removed from private source')
    output.mkdir()
    for section, members in [('candidate', candidate), ('rollback', baseline)]:
        for name, data in members.items():
            target = output / section / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    base_pins = {name: sha(data) for name, data in baseline.items()}
    candidate_pins = {name: sha(data) for name, data in candidate.items()}
    added = set(candidate) - set(baseline)
    delta = {name: digest for name, digest in candidate_pins.items()
             if base_pins.get(name) != digest}
    transition = dict(schema='halogen0203.DNZ-private-source-overlay.v1',
        baseline=dict(files=base_pins), candidate=candidate_pins,
        rollback_restore=base_pins,
        rollback_remove={name: candidate_pins[name] for name in sorted(added)},
        candidate_delta=delta, common_source_all_arms=True, native_DNZ_patch=False)
    (output / 'transition.json').write_bytes(encode(transition))
    return transition


def dependencies():
    """Explicit retained import/lifecycle closure for Root review, never import it."""
    paths = [HERE / name for name in ('prepare_source.py', 'campaign.py', 'counter_reader.py')]
    paths += [FROZEN / name for name in (
        'measure_helpers.py', 'raw/binding.json', 'raw/collector/collect_epoch.py',
        'raw/collector/qpc_audit.py', 'raw/observer/validate_capture.py',
        'raw/observer/validate_cohort.py')]
    paths += [OLD / name for name in (
        'prefill4096-cohort-prep/root_campaign.py',
        'prefill4096-cohort-prep/coordinator_skeleton.py',
        'prefill8192-cohort-prep-v2/mtp_trace.py',
        'prefill8192-cohort-prep-v2/gpu_admission.py',
        'cost-cohort-prep-v5/await_owned.py',
        'oracle-cohort-prep/oracle_campaign.py', 'oracle-cohort-prep/oracle_evidence.py')]
    # These modules are imported by the retained support chain. A source list
    # is not a claim that every helper will execute; Root must review closure.
    for relative in (
        'server/.local/halogen-update-20261101/primary01822',
        'server/.local/halogen-update-20261025/primary01815',
        'server/.local/halogen-update-20261017',
        'server/.local/halogen-update-20261017/goal-next-20261017/primary0188',
        'voice/native-start'):
        paths += list((ROOT / relative).glob('*.py'))
    paths += list((ROOT / 'server').glob('*.py'))
    paths += [PACKAGE / name for name in ('.local/machine.json', '.local/install-manifest.json',
                                         '.local/entrypoint-wsl.sh', 'profiles/release.json')]
    paths += [PRIMARY / 'gpu-opportunity-next' / name for name in (
        'dn-z-stream-followup-v1.json', 'dn-z-counter-contract-v1.json')]
    paths += [ROOT / 'docs/benchmarks' / name for name in (
        'halogen0203-dnz-prefill-plan-20261111.json',
        'halogen0203-dnz-prefill-plan-20261111.md')]
    return sorted(set(path.resolve() for path in paths))


def request_case(size):
    fields = dict(cache_prompt=False, drafter='mtp', max_tokens=128, model='halogen-v2',
                  prompt_cache_policy='no_store', seed=1, stream=False, temperature=0)
    if size == 2048:
        manifest_path = HERE / 'natural2048-v1/manifest.json'
        manifest = read(manifest_path)
        need(manifest['schema'] == 'halogen0203.exact-natural2048-serving-tokenizer.v1'
             and manifest['actual_input_tokens'] == 2048
             and manifest['instruction_and_closed_thinking_frame_unchanged'] is True
             and manifest['padding_added'] is manifest['corpus_repetition_added'] is False,
             'Genuine current-tokenizer2K preparation required')
        verify_pins([manifest['request'], manifest['input_ids']])
        ids = read(manifest['input_ids']['path'])
        need(len(ids) == 2048 and all(type(token) is int and 0 <= token < 248320 for token in ids)
             and sha(b''.join(struct.pack('<i', token) for token in ids)) == manifest['input_id_sequence_sha256'],
             'Exact2048 actual input IDs differ')
        request_pin = manifest['request']
        case_pins = [pin(manifest_path), manifest['request'], manifest['input_ids']]
    elif size == 8192:
        path = ROOT / 'server/.local/halogen-update-20261107/primary0191/natural8192-prep/request-natural8192.json'
        request_pin = pin(path)
        need(request_pin['sha256'] == '2e26413988ce75fcf745a1a143aa3647297349c1516f9d18968e9d1b4da0632d',
             'Frozen8K request changed')
        case_pins = [request_pin]
    else:
        raise ValueError('Only separate2048 or8192 cohorts are allowed')
    request = read(request_pin['path'])
    need({key: value for key, value in request.items() if key != 'prompt'} == fields,
         'Frozen completion request fields differ')
    return dict(name='natural' + str(size), actual_input_tokens=size,
                actual_output_tokens=128, request=request_pin, pins=case_pins)


def prepare(output, size=2048):
    output = safe(output).resolve()
    need(output.is_relative_to(HERE.resolve()) and not output.exists(), 'Fresh private preparation path required')
    need(pin(NORMAL)['sha256'] == NORMAL_SHA and pin(PACKAGE / 'profiles/sources.json')['sha256'] == SOURCE_SHA,
         'Normal profile or47-source manifest changed')
    prior_path = FROZEN / 'overlay-v2/transition.json'
    need(pin(prior_path)['sha256'] == TRANSITION_SHA, 'Executed common RAW overlay changed')
    prior = read(prior_path)
    normal_manifest = read(PACKAGE / 'profiles/sources.json')
    need(len(normal_manifest['files']) == 47 and normal_manifest['version'] == '0.20.3',
         'Exact normal source47 required')
    baseline = {name: safe(PACKAGE / name).read_bytes() for name in prior['baseline']}
    need(all(sha(data) == prior['baseline'][name] for name, data in baseline.items()),
         'Active baseline differs from executed RAW overlay')
    candidate = {name: safe(FROZEN / 'overlay-v2/candidate' / name).read_bytes()
                 for name in prior['candidate']}
    need(all(sha(data) == prior['candidate'][name] for name, data in candidate.items()),
         'Executed common RAW source changed')
    raw = pin(FROZEN / 'raw/observer/libhgn0203_raw_side.so')
    need(raw['sha256'] == RAW_SHA and raw['bytes'] == 21432, 'Existing RAW artifact differs')
    candidate['scripts/kernel_controls.py'] = extend_controls(candidate['scripts/kernel_controls.py'])
    manifest = json.loads(candidate['profiles/sources.json'])
    manifest['files'] = {name: sha(data) for name, data in candidate.items() if name != 'profiles/sources.json'}
    manifest['integration_status'] = 'Private common RAW source with default-off native DNZ0/1; no external stream'
    candidate['profiles/sources.json'] = encode(manifest)
    for name, data in candidate.items():
        if name.endswith('.py'):
            ast.parse(data, filename=name)
    case = request_case(size)
    profile_set = profiles(read(NORMAL))
    transition = materialize(output, baseline, candidate)
    for arm, profile in profile_set.items():
        (output / (arm + '.profile.json')).write_bytes(encode(profile))
    paths = dependencies() + [NORMAL, PACKAGE / 'profiles/sources.json', prior_path]
    paths += [Path(item['path']) for item in case['pins']]
    paths += [output / 'transition.json'] + [output / (arm + '.profile.json') for arm in ARMS]
    for section, members in [('candidate', transition['candidate']), ('rollback', transition['rollback_restore'])]:
        paths += [output / section / name for name in members]
    paths += [Path(raw['path'])]
    pins = [pin(path) for path in sorted(set(paths))]
    binding = dict(schema=SCHEMA, root_sealed=False, dependency_closure_reviewed=False,
        source_freeze_complete=True, transition=str(output / 'transition.json'), pins=pins,
        normal_profile=pin(NORMAL), normal_source_manifest=pin(PACKAGE / 'profiles/sources.json'),
        case=case, profiles={arm: pin(output / (arm + '.profile.json')) for arm in ARMS},
        artifact=dict(target='.local/libhgn0203_raw_side.so', source=raw),
        guards=dict(startup_physical=30, startup_commit=131, entry=22, runtime=18),
        NPU_helper=False, external_stream=False, independent_all_neural_acceptance=False,
        dependency_seal_policy='Root must review this explicit retained source/import closure, add any missing executed dependency, then set both execution gates true. No permission or provider discovery is run by preparation.')
    (output / 'bindings-prepared.json').write_bytes(encode(binding))
    need(all(sha(safe(PACKAGE / name).read_bytes()) == digest
             for name, digest in transition['baseline']['files'].items()), 'Normal source changed during preparation')
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--size', type=int, choices=(2048, 8192), default=2048)
    parser.add_argument('--output', type=Path, default=HERE / 'prepared-natural2048-v1')
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps(dict(source_only=True, executed=False)))
        return 0
    binding = prepare(args.output, args.size)
    print(json.dumps(dict(prepared=True, root_sealed=False, pins=len(binding['pins']), output=str(args.output))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
