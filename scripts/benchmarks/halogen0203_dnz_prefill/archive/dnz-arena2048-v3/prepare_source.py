"""Private DNZ v3 source preparation:8K capacity and paired2048 working arena.

Default CLI and import perform no hardware, model, process or network action.
Preparation only creates fresh files in this experiment, after input validation.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PRIMARY=HERE.parent
V2=PRIMARY/'dnz-prefill-capacity8192-v2'
V2_EXECUTED=V2/'Root-execution-bindings-v2.json'
BASE=V2/'prepared-v2'
spec=importlib.util.spec_from_file_location('dnz_arena2048_frozen_prepare_v2',V2/'prepare_source.py')
v2=importlib.util.module_from_spec(spec);sys.modules[spec.name]=v2;spec.loader.exec_module(v2)
need,sha,safe,read,pin,verify_pins,encode=(v2.need,v2.sha,v2.safe,v2.read,v2.pin,v2.verify_pins,v2.encode)
need(pin(V2/'prepare_source.py')['sha256']=='b109e5d624f0b048a61386603db0a819b4927cba4003ba5d8c38ce8517a488bd',
     'Frozen reviewed v2 preparation changed')
ROOT,OLD,FROZEN,PACKAGE,NORMAL=v2.ROOT,v2.OLD,v2.FROZEN,v2.PACKAGE,v2.NORMAL
NORMAL_SHA,SOURCE_SHA,RAW_SHA,ARMS=v2.NORMAL_SHA,v2.SOURCE_SHA,v2.RAW_SHA,v2.ARMS
COLLECTOR_ROOT=HERE
SCHEMA='halogen0203.DNZ-arena2048-capacity8192-actual2048-bindings.v3'


def profiles(normal):
    result=v2.profiles(normal)
    for profile in result.values():
        profile['engine']['prefill_chunk']=profile['engine']['max_prefill_tokens']=2048
    return result


def request_case(size):
    need(size==2048,'This finite working-arena experiment accepts actual2048 input only')
    case=v2.request_case(size)
    case.update(name='natural2048_context8192_arena2048',paired_prefill_arena=2048)
    return case


def collector_sources():
    names=('raw/binding.json','raw/collector/collect_epoch.py','raw/collector/qpc_audit.py',
           'raw/observer/validate_capture.py','raw/observer/validate_cohort.py')
    result={name:safe(V2/name).read_bytes() for name in names}
    result['measure_helpers.py']=safe(HERE/'measure_helpers.py').read_bytes()
    return result


def dependencies():
    inherited=read(V2_EXECUTED)
    need(inherited['root_sealed'] is True and inherited['dependency_closure_reviewed'] is True,
         'Actual Root-reviewed v2 execution closure required')
    paths=[Path(row['path']) for row in inherited['pins']
           if not Path(row['path']).resolve().is_relative_to(BASE.resolve())]
    paths += [V2_EXECUTED,BASE/'transition.json']
    paths += [HERE/name for name in ('prepare_source.py','campaign.py','counter_reader.py',
                                     'measure_helpers.py','restore_margin.py','DESIGN-PLAN.md')]
    paths += [HERE/name for name in collector_sources()]
    paths += [ROOT/'docs/benchmarks'/('halogen0203-dnz-prefill-plan-20261111-v3.'+ext)
              for ext in ('md','json')]
    paths += [PRIMARY/'dnz-arena2048-feasibility-v1'/('assessment-v1.'+ext) for ext in ('md','json')]
    return sorted(set(path.resolve() for path in paths))


def stage_collector():
    for name,data in collector_sources().items():
        path=safe(HERE/name)
        if path.exists():need(path.read_bytes()==data,'Do not overwrite a changed private collector member')
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(data)


def prepare(output):
    output=safe(output).resolve()
    need(output.is_relative_to(HERE) and not output.exists(),'Fresh v3-only preparation path required')
    inherited=read(V2_EXECUTED);verify_pins(inherited['pins'])
    need(inherited['root_sealed'] is True and inherited['dependency_closure_reviewed'] is True,
         'Unreviewed v2 execution seal')
    need(pin(NORMAL)['sha256']==NORMAL_SHA and pin(PACKAGE/'profiles/sources.json')['sha256']==SOURCE_SHA,
         'Original normal32K profile/source manifest changed')
    old=read(BASE/'transition.json')
    baseline={name:safe(PACKAGE/name).read_bytes() for name in old['baseline']['files']}
    candidate={name:safe(BASE/'candidate'/name).read_bytes() for name in old['candidate']}
    need(all(sha(data)==old['baseline']['files'][name] for name,data in baseline.items()),
         'Exact normal baseline differs')
    need(all(sha(data)==old['candidate'][name] for name,data in candidate.items()),'Reviewed v2 candidate changed')
    # Validate every available input before any preparation write. Missing raw
    # copies below are generated only from the preceding sealed v2 inputs.
    for path in dependencies():
        if path.is_relative_to(HERE/'raw') and not path.exists():continue
        pin(path)
    for name,data in collector_sources().items():
        path=HERE/name
        if path.exists():need(path.read_bytes()==data,'Existing private collector source differs')
    transition=v2.materialize(output,baseline,candidate)
    transition.update(schema='halogen0203.DNZ-arena2048-capacity8192-private-overlay.v3',
                      capacity_context=8192,paired_prefill_arena=2048,private_v2_minimum_commit_GiB=131)
    (output/'transition.json').write_bytes(encode(transition))
    stage_collector()
    for arm,profile in profiles(read(NORMAL)).items():
        (output/(arm+'.profile.json')).write_bytes(encode(profile))
    case=request_case(2048);raw=pin(FROZEN/'raw/observer/libhgn0203_raw_side.so')
    need(raw['sha256']==RAW_SHA and raw['bytes']==21432,'Exact existing RAW observer differs')
    paths=dependencies()+[NORMAL,PACKAGE/'profiles/sources.json',output/'transition.json',Path(raw['path'])]
    paths += [Path(row['path']) for row in case['pins']]
    paths += [output/(arm+'.profile.json') for arm in ARMS]
    for section,members in (('candidate',transition['candidate']),('rollback',transition['rollback_restore'])):
        paths += [output/section/name for name in members]
    binding=dict(schema=SCHEMA,root_sealed=False,dependency_closure_reviewed=False,source_freeze_complete=True,
        transition=str(output/'transition.json'),pins=[pin(path) for path in sorted(set(paths))],
        normal_profile=pin(NORMAL),normal_source_manifest=pin(PACKAGE/'profiles/sources.json'),
        capacity_context=8192,paired_prefill_arena=2048,case=case,
        profiles={arm:pin(output/(arm+'.profile.json')) for arm in ARMS},
        artifact=dict(target='.local/libhgn0203_raw_side.so',source=raw),
        guards=dict(startup_physical=30,startup_commit=131,entry=22,runtime=18),
        normal_restore_margin=dict(physical=30.25,commit=131,stable_seconds=10,maximum_seconds=300,runtime=18),
        NPU_helper=False,external_stream=False,independent_all_neural_acceptance=False,
        normal_restoration_context=32768,no_8192_input_campaign=True,prior_v2_execution_provenance=pin(V2_EXECUTED))
    (output/'bindings-prepared.json').write_bytes(encode(binding))
    need(all(sha(safe(PACKAGE/name).read_bytes())==digest for name,digest in old['baseline']['files'].items()),
         'Normal baseline changed during source preparation')
    return binding


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--output',type=Path,default=HERE/'prepared-v3')
    args=parser.parse_args()
    if not args.prepare:
        print(json.dumps(dict(source_only=True,executed=False)));return 0
    binding=prepare(args.output)
    print(json.dumps(dict(prepared=True,root_sealed=False,pins=len(binding['pins']),
                         capacity_context=8192,paired_prefill_arena=2048,actual_input_tokens=2048)))
    return 0


if __name__=='__main__':raise SystemExit(main())
