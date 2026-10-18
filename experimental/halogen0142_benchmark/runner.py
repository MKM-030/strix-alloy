"""Bounded, single-container replay of the frozen Reddit tables on Halogen 0.14.2.

The default command only validates inputs and prints the sealed Docker argv.
Live execution requires --run and an independent review of that exact seal.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

INTEGRATION = Path(__file__).resolve().parents[2]
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))
from experimental.halogen0142 import runner as base
from scripts.gufo_control import reddit_halogen_client as client

HERE = Path(__file__).resolve().parent
ROOT = base.ROOT
INPUTS = {
    'mixed': (ROOT/'reports/reddit-native-mixed-20260928-v1-runs/20260928T175042Z-77a3e79ffb3e4feb8f414707d9503a74/result.json',
              'fc6a573675541d13df5fed7bd931577547b8071c81032d65113920bdf4ac626f'),
    'repetitive': (ROOT/'reports/reddit-native-repetitive-20260928-v1-runs/20260928T180048Z-d254e48eb64f4d5ca41b834984ce5198/result.json',
                   'dbcaf81027180ac1aa5c684569b7d9b470f1e126d06c8a5d508c38e3a3fa6b48')}
BENCH_ENV = dict(HALOGEN_CTX='133888', HALOGEN_KV_POOL_POSITIONS='133888',
                 HALOGEN_KV_SLOTS='1', HALOGEN_PREFILL_CHUNK='2048', HALOGEN_MAX_TOK='2048',
                 HALOGEN_PROMPT_CACHE='2', HALOGEN_CACHE_BRANCHES='2',
                 HALOGEN_CACHE_INPLACE='1', HALOGEN_CACHE_SNAP3='0',
                 HALOGEN_CACHE_FULL='0', HALOGEN_CACHE_ENTRIES='3',
                 HALOGEN_TOPK_REPLAY='0', HALOGEN_FLASH_ROUTE_GEMM='0',
                 HALOGEN_PREFLIGHT_TRACE_ONLY='0')


def check_file(item):
    path = Path(item['path']).resolve(strict=True)
    if not path.is_file() or base.file_sha(path) != item['sha256']:
        raise ValueError('file hash mismatch: '+str(path))
    return path


def evidence_digest(attempt):
    files = {str(path.relative_to(attempt)).replace('\\','/'):base.file_sha(path)
             for path in attempt.rglob('*') if path.is_file()}
    return base.digest(files)


def environment(m):
    return {**base.environment(m), **BENCH_ENV}


def command(m, name):
    """Keep base ownership, mounts and timeout; replace its entire env vector."""
    original = base.command(m, name)
    result = []
    i = 0
    while i < len(original):
        if original[i] == '-e':
            i += 2
        else:
            result.append(original[i]); i += 1
    at = result.index('--entrypoint')
    for key, value in sorted(environment(m).items()):
        result[at:at] = ['-e', key+'='+value]
        at += 2
    return result


def selected_table(config):
    table = config.get('table')
    if table not in INPUTS:
        raise ValueError('exactly one frozen table required per attempt')
    return table


def validate_config(config):
    if config.get('schema') != 1 or set(config) != {'schema','table','base_manifest','prerequisites'}:
        raise ValueError('benchmark config shape invalid')
    selected_table(config)
    manifest_path = check_file(config['base_manifest'])
    m = base.read_json(manifest_path)
    if m.get('stage') != 'smoke':
        raise ValueError('benchmark requires smoke candidate manifest')
    base.validate_manifest(m)
    m = {**m, 'timeout_seconds':1800}
    table = selected_table(config)
    path, sha = INPUTS[table]
    check_file({'path': str(path), 'sha256': sha})
    _, rows, _, _ = client.load_source(path, table)
    if len(rows) != 8:
        raise ValueError('frozen table is not eight rows: '+table)
    return m


def offline(config):
    m = validate_config(config)
    base_seal = base.make_seal(m)
    sources = [Path(__file__), Path(client.__file__), Path(client.native.__file__),
               Path(client.native.smoke_http.__file__), Path(base.__file__)]
    body = dict(schema=1, config=config, candidate_image=m['image'],
                candidate_engine_sha256=m['engine_sha256'],
                candidate_artifacts=m['artifacts'],
                base_controller_sources=base_seal['controller_sources'],
                companion_sources={str(p.resolve()):base.file_sha(p) for p in sources},
                input={'table':selected_table(config),'path':str(INPUTS[selected_table(config)][0]),
                       'sha256':INPUTS[selected_table(config)][1]},
                launch_environment=environment(m),
                docker_argv=command(m,'halogen-flash-hybrid-0142-benchmark-DRYRUN'))
    return {**body, 'seal_sha256':base.digest(body)}


def check_success(item, stage, artifacts):
    path = check_file(item)
    if path.name != 'success.json' or not path.is_relative_to(base.ARTIFACT_ROOT/'attempts'):
        raise ValueError('qualified success path invalid')
    if item.get('evidence_sha256') != evidence_digest(path.parent):
        raise ValueError(stage+' evidence inventory changed')
    success = base.read_json(path)
    seal_path = path.parent/'seal.json'
    seal = base.read_json(seal_path)
    if (success.get('stage') != stage or success.get('cleanup') is not True or
        success.get('recovery') is not True or success.get('seal_sha256') != seal.get('seal_sha256') or
        seal.get('manifest',{}).get('stage') != stage or
        seal['manifest'].get('artifacts') != artifacts or base.make_seal(seal['manifest']) != seal):
        raise ValueError(stage+' success/seal identity invalid')
    if item.get('seal_sha256') != base.file_sha(seal_path):
        raise ValueError(stage+' seal evidence hash mismatch')
    outcome = base.read_json(path.parent/'outcome.json')
    if outcome.get('passed') is not True:
        raise ValueError(stage+' outcome not successful')
    return path, seal


def prerequisites(config, m):
    items = config['prerequisites']
    if set(items) != {'trace','smoke'}:
        raise ValueError('trace and smoke successes required')
    trace_path, trace = check_success(items['trace'], 'trace', m['artifacts'])
    smoke_path, smoke = check_success(items['smoke'], 'smoke', m['artifacts'])
    smoke_review = base.read_json(smoke_path.parent/'review.json')
    check_smoke_trace_link(smoke_review,trace_path,items['trace']['sha256'])
    return trace, smoke


def check_smoke_trace_link(smoke_review, trace_path, trace_sha):
    supplied = smoke_review.get('trace_success_path')
    if (not supplied or Path(supplied).resolve() != Path(trace_path).resolve() or
        smoke_review.get('trace_success_sha256') != trace_sha):
        raise ValueError('smoke did not depend on this trace success')


def summarize_replay(record, exit_code):
    return dict(replay_exit_code=exit_code,
                http_workload_completed=len(record.get('requests',[])) == 8 and
                all(row.get('success') is True for row in record['requests']),
                strictly_comparable=exit_code == 0 and record.get('candidate_success') is True,
                raw_candidate_success=record.get('candidate_success'),
                cells=record.get('cells'), error=record.get('error'))


def check_cleanup(attempt, *, had_container=True):
    if had_container:
        terminal = base.read_json(attempt/'terminal.json')
        base.validate_terminal(terminal['State'])
    elif (attempt/'container.json').exists() or (attempt/'terminal.json').exists():
        raise ValueError('no-container cleanup has container evidence')
    if not (attempt/'recovery.json').exists() or not (attempt/'release.json').exists():
        raise ValueError('recovery/cleanup evidence incomplete')
    recovery = base.read_json(attempt/'recovery.json')
    release = base.read_json(attempt/'release.json')
    if (recovery.get('passed') is not True or len(recovery.get('frames',[])) < 5 or
        release != {'cleanup':True,'recovery':True}):
        raise ValueError('recovery/cleanup evidence incomplete')


def check_health(health, m, cid):
    versions = health.get('version') or {}
    if (health.get('status') != 'ok' or versions.get('api') != '0.14.2' or
        versions.get('engine') != '0.14.2' or versions.get('match') is not True or
        health.get('context') != 133888 or health.get('kv_pool_positions') != 133888 or
        health.get('slots') != 1 or health.get('prompt_cache',{}).get('mode') != 2 or
        health.get('drafter_default') != 'mtp' or
        (health.get('prompt_lookup') or {}).get('ngram') != 3 or
        (health.get('prompt_lookup') or {}).get('chain') != 3):
        raise ValueError('0.14.2 health/effective capacity mismatch')
    info = base.inspect(cid); base.owned(info,cid,info['Name'][1:],m,running=True)
    actual = info['Config']['Env']
    for key,value in environment(m).items():
        if [item for item in actual if item.startswith(key+'=')] != [key+'='+value]:
            raise ValueError('effective container environment mismatch: '+key)


def sample_after_table(cid, attempt, index):
    record = base.sample(cid,attempt,'inference',9000+index)
    base.validate_sample(record,cid)


def exit_status(outcome):
    return 0 if outcome.get('passed') is True else 1


def check_benchmark_admission(frame, table):
    if table not in ('mixed','repetitive'):
        raise ValueError('benchmark admission table invalid')
    physical_floor = 47 if table == 'mixed' else 45
    if (type(frame.get('available_bytes')) is not int or
        frame['available_bytes'] < physical_floor*base.GIB or
        type(frame.get('commit_headroom_bytes')) is not int or
        frame['commit_headroom_bytes'] < 116*base.GIB):
        raise ValueError(f'benchmark admission below reviewed {physical_floor}/116 GiB floor')


def run(config, review, config_path):
    if os.name != 'nt': raise ValueError('Windows controller required')
    m = validate_config(config); seal = offline(config)
    base.check_review(review,seal['seal_sha256'],'benchmark')
    prerequisites(config,m)
    attempts = base.ARTIFACT_ROOT/'attempts'; attempts.mkdir(exist_ok=True)
    table = selected_table(config)
    name = 'halogen-flash-hybrid-0142-benchmark-'+table+'-'+uuid.uuid4().hex
    attempt = attempts/name; attempt.mkdir()
    base.save(attempt/'seal.json',seal); base.save(attempt/'review.json',review)
    base.save(attempt/'config.json',config); base.save(attempt/'manifest.json',m)
    lock = base.ARTIFACT_ROOT/'runner.lock'; lock_handle = lock.open('x')
    cid = None; watcher = None; baseline = None; creation_attempted = False
    cleanup = recovery = False; errors = []
    outcome = {'stage':'benchmark','table':table,'passed':False}
    try:
        _,host = base.guards(m)
        baseline = base.admission(host); base.save(attempt/'admission-create.json',baseline)
        check_benchmark_admission(baseline,table)
        if offline(config) != seal: raise ValueError('benchmark seal drift before create')
        creation_attempted = True
        cid = base.docker(*command(m,name),timeout=20)
        base.owned(base.inspect(cid),cid,name,m)
        base.save(attempt/'container.json',{'id':cid,'name':name})
        watcher = subprocess.Popen([sys.executable,str(Path(__file__)),'--manifest',str(config_path),
                                    '--guard',cid,'--name',name,'--attempt',str(attempt)],
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        armed_deadline = time.monotonic()+15
        while not (attempt/'armed.json').exists():
            if watcher.poll() is not None or time.monotonic()>armed_deadline:
                raise RuntimeError('independent guard not armed')
            time.sleep(.1)
        baseline = base.admission(host); base.save(attempt/'admission-start.json',baseline)
        check_benchmark_admission(baseline,table)
        if offline(config) != seal: raise ValueError('benchmark seal drift before start')
        base.guard_alive(watcher,attempt); base.docker('start',cid)
        deadline = time.monotonic()+1800
        while time.monotonic()<deadline:
            base.guard_alive(watcher,attempt)
            current=base.inspect(cid); base.owned(current,cid,name,m)
            if not current['State']['Running']: raise RuntimeError('engine exited before benchmark')
            try: health=base.http('/health')
            except (OSError,ValueError): health={}
            if health.get('status')=='ok': break
            startup,_=base.guards(m); startup.validate_target(current,cid)
            base.docker('exec',cid,'python3','-c',startup.CACHE_CODE,timeout=20)
            time.sleep(3)
        else: raise TimeoutError('benchmark readiness deadline')
        check_health(health,m,cid); base.save(attempt/'health.json',health)
        path,_=INPUTS[table]
        base.guard_alive(watcher,attempt)
        if time.monotonic()>=deadline: raise TimeoutError('container benchmark deadline')
        out=io.StringIO(); err=io.StringIO(); replay_path=attempt/(table+'-replay.json')
        try:
            with redirect_stdout(out),redirect_stderr(err):
                code=client.replay(path,table,cid,replay_path)
        finally:
            base.save(attempt/(table+'-stdio.json'),{'stdout':out.getvalue(),'stderr':err.getvalue()})
        record=base.read_json(replay_path)
        outcome['replay']=summarize_replay(record,code)
        base.save(attempt/(table+'-summary.json'),outcome['replay'])
        base.guard_alive(watcher,attempt)
        sample_after_table(cid,attempt,1)
        outcome['http_workload_completed']=outcome['replay']['http_workload_completed']
        outcome['strictly_comparable']=outcome['replay']['strictly_comparable']
    except BaseException as error:
        outcome['error']=repr(error)
    finally:
        try:
            if not cid and creation_attempted:
                candidate=base.inspect(name); cid=candidate['Id']; base.owned(candidate,cid,name,m)
            if cid:
                terminal=base.stop_owned(cid,name,m); cleanup=True
                base.save(attempt/'terminal.json',terminal)
                base.validate_terminal(terminal['State'])
                logs=subprocess.run(base.WSL+['docker','logs',cid],capture_output=True,text=True,
                                    timeout=15,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                base.save(attempt/'container-logs.json',{'stdout':logs.stdout,'stderr':logs.stderr})
            elif not creation_attempted: cleanup=True
            if baseline:
                _,host=base.guards(m); frames=[]; end=time.monotonic()+180
                while time.monotonic()<end:
                    began=time.monotonic(); frame=host.frame()
                    base.check_frame(frame,age=time.monotonic()-began); frames.append(frame)
                    if base.recovered(frames,baseline['available_bytes']): recovery=True; break
                    time.sleep(1)
                base.save(attempt/'recovery.json',{'frames':frames,'passed':recovery})
            if cleanup and recovery:
                base.save(attempt/'release.json',{'cleanup':True,'recovery':True})
                if watcher and watcher.wait(timeout=15)!=0: raise RuntimeError('host guard failed')
                check_cleanup(attempt,had_container=cid is not None)
            else: raise RuntimeError('cleanup/recovery not established; lock retained')
        except BaseException as error:
            errors.append(repr(error))
        finally:
            if watcher and cleanup and watcher.poll() is None:
                watcher.terminate()
                try: watcher.wait(timeout=10)
                except subprocess.TimeoutExpired: watcher.kill(); watcher.wait(timeout=5)
            outcome.update(cleanup=cleanup,recovery=recovery,cleanup_errors=errors,
                           passed=bool(outcome.get('strictly_comparable') and cleanup and recovery
                                       and not outcome.get('error') and not errors))
            base.save(attempt/'outcome.json',outcome)
            lock_handle.close()
            if cleanup and recovery and not errors: lock.unlink()
    return attempt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--guard',help=argparse.SUPPRESS)
    parser.add_argument('--name',help=argparse.SUPPRESS)
    parser.add_argument('--attempt',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.guard:
        m=base.read_json(args.attempt/'manifest.json')
        return base.guard_process(m,args.guard,args.name,args.attempt)
    config=base.read_json(args.manifest)
    if not args.run:
        print(json.dumps(offline(config),indent=2)); return 0
    if not args.review: parser.error('--run requires --review')
    attempt=run(config,base.read_json(args.review),args.manifest.resolve())
    print(attempt)
    return exit_status(base.read_json(attempt/'outcome.json'))


if __name__=='__main__': raise SystemExit(main())
