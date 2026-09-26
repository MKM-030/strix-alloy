"""Private fixed-profile research CLI; only run can invoke the owned Guardian."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

from . import benchmark_recipes as recipes, operator_store, smoke_store
from .benchmark_runtime import BoundPolicy, BoundStore
from .benchmark_suite import start_suite
from .smoke_guard import _Guardian, check_port

MARGIN_SHA256='75BDFDFFFB46D6BB88529FA12D76EE29910064AE03334906ABB46B8A38861620'


def profile_pins(profile_id):
    definition=recipes.recipe_definition(profile_id)
    four=profile_id==recipes.PROFILE_4K
    reports=smoke_store.ROOT/'reports'
    acceptance_sha=None
    if four:
        predecessor=smoke_store.PredecessorPin(smoke_store.PROFILE_ID,
            reports/smoke_store.PROFILE_ROOTS[smoke_store.PROFILE_ID]/smoke_store.FIRST_PREDECESSOR_RUN,
            smoke_store.FIRST_PREDECESSOR_SHA256)
    else:
        path=reports/'gufo-ar4k-benchmark-acceptance.json'
        if path.is_symlink() or path.resolve(strict=True).parent!=reports.resolve(strict=True):
            raise ValueError('acceptance_path_invalid')
        before=operator_store.artifact_record(path)
        value=operator_store.read_json(path)
        if (not isinstance(value,dict) or set(value)!={'profile_id','run','result_sha256','semantic_status','review_id'}
                or value['profile_id']!=recipes.PROFILE_4K or value['semantic_status']!='passed'
                or not isinstance(value['review_id'],str) or not value['review_id'].strip()
                or not smoke_store._digest_valid(value['result_sha256']) or not isinstance(value['run'],str)):
            raise ValueError('acceptance_invalid')
        run=Path(value['run'])
        root=reports/smoke_store.PROFILE_ROOTS[recipes.PROFILE_4K]
        if (not run.is_absolute() or not run.is_dir() or run.is_symlink() or run.resolve(strict=True)!=run
                or run.parent!=root or run.resolve(strict=True).parent!=root.resolve(strict=True)):
            raise ValueError('predecessor_run_invalid')
        result_path=run/'result.json'
        if result_path.is_symlink() or result_path.resolve(strict=True).parent!=run:
            raise ValueError('predecessor_artifact_path')
        if operator_store.artifact_record(result_path)['sha256']!=value['result_sha256']:
            raise ValueError('predecessor_result_hash_mismatch')
        if operator_store.artifact_record(path)!=before: raise ValueError('acceptance_changed')
        acceptance_sha=before['sha256']
        predecessor=smoke_store.PredecessorPin(recipes.PROFILE_4K,run,value['result_sha256'])
    experiment=dict(profile_id=profile_id,recipe_sha256=sha256(recipes.recipe_json(profile_id).encode()).hexdigest().upper(),
        context_tokens=definition['context_tokens'],max_prompt_tokens=definition['max_prompt_tokens'],
        max_output_tokens=256,max_requests=definition['max_requests'],sessions=1,max_connections=16,
        max_request_bytes=262144,max_response_bytes=1048576,request_seconds=60,startup_seconds=480,lifetime_seconds=600,
        speculative=False,disk_cache=False)
    evidence_name='gufo-ar4k-benchmark-v2-runs' if four else 'gufo-ar16k-benchmark-v2-runs'
    qualification_name='gufo-ar4k-benchmark-v2-qualification.json' if four else 'gufo-ar16k-benchmark-v2-qualification.json'
    return replace(smoke_store.PINS,profile_id=profile_id,evidence=reports/evidence_name,
        qualification=reports/qualification_name,
        margin_report=reports/'gufo-ar-benchmark-fit-20260926.md',margin_sha256=MARGIN_SHA256,
        experiment_json=recipes.canonical(experiment),predecessors=(predecessor,),acceptance_sha256=acceptance_sha)


def make_guardian(profile_id):
    pins=profile_pins(profile_id)
    guardian=_Guardian(store=BoundStore(pins),policy_module=BoundPolicy(pins),
        profile_id=profile_id,argv_builder=lambda secret: recipes.build_argv(profile_id,secret))

    def http_start(**kwargs):
        if guardian.run_dir is None: raise ValueError('guardian_run_dir_missing')
        return start_suite(profile_id=profile_id,evidence_dir=guardian.run_dir,**kwargs)

    guardian.http_start=http_start
    return guardian


def status(profile_id, *, print_only=False):
    result=dict(profile=profile_id,admitted=False,admission='requires_fresh_run_baseline',
        argv=recipes.build_argv(profile_id,'[REDACTED]'),bounds=dict(smoke_store.BOUNDS))
    try:
        pins=profile_pins(profile_id)
        result['experiment']=json.loads(pins.experiment_json)
        for name in ('attempt.json','incomplete.json'):
            path=pins.evidence/name
            result[name]=dict(present=path.exists())
            if path.exists():
                try:
                    value=operator_store.read_json(path)
                    valid=Path(value['run']).resolve().parent==pins.evidence.resolve()
                except (OSError,ValueError,KeyError,TypeError): valid=False
                result[name]['state_valid']=valid
        if print_only:
            BoundStore(pins).verify_static()
            operator_store.child_environment(dict(os.environ))
            check_port()
            result['static_qualified']=True
    except Exception as exc:
        result.update(static_qualified=False,refused=type(exc).__name__+':'+str(exc))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description='Fixed finite native GUFO research suite')
    parser.add_argument('command',choices=('status','print-only','run'))
    parser.add_argument('--profile',choices=(recipes.PROFILE_4K,recipes.PROFILE_16K),required=True)
    args=parser.parse_args(argv)
    if args.command!='run':
        result=status(args.profile,print_only=args.command=='print-only')
        code=2 if result.get('static_qualified') is False else 0
    else:
        if os.name!='nt': parser.error('Windows required')
        try:
            result=make_guardian(args.profile).run()
            code=0 if result['success'] else 2 if result['resumed_monotonic'] is None else 1
        except Exception as exc:
            result=dict(profile=args.profile,success=False,refused=type(exc).__name__+':'+str(exc)); code=2
    print(json.dumps(result,allow_nan=False))
    return code


if __name__=='__main__':
    raise SystemExit(main())
