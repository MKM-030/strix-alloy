"""Private8K-capacity/actual2K-input DNZ preparation; no runtime action.

Reuse the independently reviewed v1 sources and its complete execution closure.
Only the private v2 commit floor, implicit-capacity profiles and two ordinary
collector slot reads change. Default CLI remains inert; preparation is local.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent
V1 = PRIMARY / 'dnz-prefill-prep'
spec = importlib.util.spec_from_file_location('dnz_capacity8192_frozen_prepare_v1', V1 / 'prepare_source.py')
v1 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v1
spec.loader.exec_module(v1)
need, sha, safe, read, pin, verify_pins, encode = (
    v1.need, v1.sha, v1.safe, v1.read, v1.pin, v1.verify_pins, v1.encode)
need(pin(V1 / 'prepare_source.py')['sha256'] ==
     'e34ab8b6c6ee333d25da2d266685e381856e5d185a845e3afe3eee25fec93ce4',
     'Frozen reviewed v1 preparation changed')
ROOT, OLD, FROZEN, PACKAGE, NORMAL = v1.ROOT, v1.OLD, v1.FROZEN, v1.PACKAGE, v1.NORMAL
NORMAL_SHA, SOURCE_SHA, RAW_SHA, ARMS = v1.NORMAL_SHA, v1.SOURCE_SHA, v1.RAW_SHA, v1.ARMS
COLLECTOR_ROOT = HERE
SCHEMA = 'halogen0203.DNZ-capacity8192-actual2048-bindings.v2'
V1_EXECUTED = V1 / 'Root-dnz-natural2048-v1/executed-bindings.json'
BASE = V1 / 'prepared-natural2048-v1'
materialize = v1.materialize
extend_controls = v1.extend_controls


def profiles(normal):
    result = v1.profiles(normal)
    for profile in result.values():
        engine, backend = profile['engine'], profile['backend']
        engine['context'] = backend['context'] = 8192
        del engine['slots']
        del engine['kv_pool_positions']
        backend['expected'].update(context=8192, slot_ctx=8192, kv_pool_positions=8192, slots=1)
    return result


def clamp_v2_budget(source):
    anchor = b'    if vision:\n        # Charge the complete pinned tower'
    need(source.count(anchor) == 1 and b'Private capacity8192' not in source,
         'Exact unchanged admission source anchor required')
    addition = (b"    # Private capacity8192 experiment preserves the existing v2 startup commitment.\n"
                b"    if checkpoint == 'v2':\n        commit = max(commit, 131)\n")
    return source.replace(anchor, addition + anchor)


def ordinary_collector(source):
    anchor = b"slots = config['engine']['slots']"
    need(source.count(anchor) == 2, 'Exactly two reviewed collector slot reads required')
    return source.replace(anchor, b"slots = config['engine'].get('slots', 1)")


def collector_sources():
    names = ('measure_helpers.py', 'raw/binding.json', 'raw/collector/collect_epoch.py',
             'raw/collector/qpc_audit.py', 'raw/observer/validate_capture.py', 'raw/observer/validate_cohort.py')
    result = {name: safe(FROZEN / name).read_bytes() for name in names}
    result['raw/collector/collect_epoch.py'] = ordinary_collector(result['raw/collector/collect_epoch.py'])
    return result


def stage_collector(output):
    output = safe(output)
    for name, data in collector_sources().items():
        path = output / name
        need(not path.exists(), 'Do not overwrite a prepared collector member')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def capacity_candidate(template):
    result = dict(template)
    result['scripts/memory_budget.py'] = clamp_v2_budget(result['scripts/memory_budget.py'])
    manifest = json.loads(result['profiles/sources.json'])
    manifest['files'] = {name: sha(data) for name, data in result.items() if name != 'profiles/sources.json'}
    manifest['integration_status'] = 'Private DNZ0/1, implicit8K capacity, actual2K input; v2 startup30/131 retained'
    result['profiles/sources.json'] = encode(manifest)
    return result


def request_case(size):
    need(size == 2048, 'This8K-capacity experiment fits actual2048+128, not8192+128')
    case = v1.request_case(size)
    case.update(name='natural2048_context8192', capacity_context=8192)
    return case


def dependencies():
    # Carry the actual reviewed five extra transitive roles as well as the
    # original closure. Old prepared package copies are provenance, not runtime.
    inherited = read(V1_EXECUTED)
    need(inherited['root_sealed'] is True and inherited['dependency_closure_reviewed'] is True,
         'Reviewed executed v1 dependency closure required')
    old_prepared = BASE.resolve()
    paths = [Path(row['path']) for row in inherited['pins']
             if not Path(row['path']).resolve().is_relative_to(old_prepared)]
    paths += [V1_EXECUTED, BASE / 'transition.json']
    paths += [HERE / name for name in ('prepare_source.py', 'campaign.py', 'counter_reader.py')]
    paths += [HERE / name for name in collector_sources()]
    # Root adds the separately preregistered prospective v2 plan when sealing;
    # include it here too if it already exists at preparation time.
    paths += [ROOT / 'docs/benchmarks' / name for name in (
        'halogen0203-dnz-prefill-plan-20261111-v2.md',
        'halogen0203-dnz-prefill-plan-20261111-v2.json')]
    return sorted(set(path.resolve() for path in paths))


def prepare(output):
    output = safe(output).resolve()
    need(output.is_relative_to(HERE.resolve()) and not output.exists(), 'Fresh v2-only preparation directory required')
    need(pin(NORMAL)['sha256'] == NORMAL_SHA and pin(PACKAGE / 'profiles/sources.json')['sha256'] == SOURCE_SHA,
         'Normal32K source/profile changed')
    inherited = read(V1_EXECUTED)
    verify_pins(inherited['pins'])
    old = read(BASE / 'transition.json')
    baseline = {name: safe(PACKAGE / name).read_bytes() for name in old['baseline']['files']}
    need(all(sha(data) == old['baseline']['files'][name] for name, data in baseline.items()),
         'Normal47-source baseline differs from v1')
    template = {name: safe(BASE / 'candidate' / name).read_bytes() for name in old['candidate']}
    need(all(sha(data) == old['candidate'][name] for name, data in template.items()), 'Reviewed common v1 source changed')
    candidate = capacity_candidate(template)
    transition = materialize(output, baseline, candidate)
    transition['schema'] = 'halogen0203.DNZ-implicit8192-capacity-private-overlay.v2'
    transition['capacity_context'] = 8192
    transition['private_v2_minimum_commit_GiB'] = 131
    (output / 'transition.json').write_bytes(encode(transition))
    # Collector lives beside this v2 coordinator. Its layout and bound inputs
    # are separate from the immutable v1 copies and the active package.
    if not (HERE / 'raw/collector/collect_epoch.py').exists():
        stage_collector(HERE)
    expected_collector = collector_sources()
    need(all(safe(HERE / name).read_bytes() == data for name, data in expected_collector.items()),
         'Private ordinary-capacity collector changed')
    for arm, profile in profiles(read(NORMAL)).items():
        (output / (arm + '.profile.json')).write_bytes(encode(profile))
    case = request_case(2048)
    raw = pin(FROZEN / 'raw/observer/libhgn0203_raw_side.so')
    need(raw['sha256'] == RAW_SHA and raw['bytes'] == 21432, 'Existing RAW observer product differs')
    paths = dependencies() + [NORMAL, PACKAGE / 'profiles/sources.json', output / 'transition.json', Path(raw['path'])]
    paths += [Path(row['path']) for row in case['pins']]
    paths += [output / (arm + '.profile.json') for arm in ARMS]
    for section, members in [('candidate', transition['candidate']), ('rollback', transition['rollback_restore'])]:
        paths += [output / section / name for name in members]
    binding = dict(schema=SCHEMA, root_sealed=False, dependency_closure_reviewed=False,
        source_freeze_complete=True, transition=str(output / 'transition.json'),
        pins=[pin(path) for path in sorted(set(paths))], normal_profile=pin(NORMAL),
        normal_source_manifest=pin(PACKAGE / 'profiles/sources.json'), capacity_context=8192,
        case=case, profiles={arm: pin(output / (arm + '.profile.json')) for arm in ARMS},
        artifact=dict(target='.local/libhgn0203_raw_side.so', source=raw),
        guards=dict(startup_physical=30, startup_commit=131, entry=22, runtime=18),
        NPU_helper=False, external_stream=False, independent_all_neural_acceptance=False,
        normal_restoration_context=32768, no_8192_input_campaign=True,
        prior_failed32K_attempt_provenance=pin(V1_EXECUTED))
    (output / 'bindings-prepared.json').write_bytes(encode(binding))
    need(all(sha(safe(PACKAGE / name).read_bytes()) == digest
             for name, digest in old['baseline']['files'].items()), 'Normal source changed during private preparation')
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--output', type=Path, default=HERE / 'prepared-v2')
    args = parser.parse_args()
    if not args.prepare:
        print(json.dumps(dict(source_only=True, executed=False)))
        return 0
    binding = prepare(args.output)
    print(json.dumps(dict(prepared=True, root_sealed=False, pins=len(binding['pins']),
                          capacity_context=8192, actual_input_tokens=2048)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
