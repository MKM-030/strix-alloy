"""Offline-sealed Halogen 0.14.2 cold HTTP PP2k/PP8k release adapter.

Default prints a seal and bounded command. --run requires an independent review
and a qualified success from the frozen release smoke controller.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

INTEGRATION=Path(__file__).resolve().parents[2]
if str(INTEGRATION) not in sys.path: sys.path.insert(0,str(INTEGRATION))
from experimental.halogen0142_release import runner as base
from experimental.halogen0142_pp import pure_recipe as recipes
from experimental.halogen0142_pp import http_transport as client

HERE=Path(__file__).resolve().parent
MODEL='qwen38-flash-next-w4b'
LIMIT_SECONDS=600
REQUEST_SECONDS=60
ADMISSION_SAMPLES=60
PP_ENV={'HALOGEN_CTX':'16384','HALOGEN_KV_POOL_POSITIONS':'16384',
        'HALOGEN_KV_SLOTS':'1','HALOGEN_PREFILL_CHUNK':'2048',
        'HALOGEN_MAX_TOK':'2048','HALOGEN_PROMPT_CACHE':'0',
        'HALOGEN_TOPK_REPLAY':'0','HALOGEN_FLASH_ROUTE_GEMM':'0'}


def schedule():
    rows=[dict(kind='warmup',target=None),dict(kind='calibration',target=None,calibration='first'),
          dict(kind='calibration',target=None,calibration='second')]
    for target in (2048,8192,8192,2048,2048,8192):
        rows.append(dict(kind='measurement',target=target))
    return rows


def environment(m):
    if m.get('stage')!='smoke' or m.get('timeout_seconds')!=LIMIT_SECONDS:
        raise ValueError('PP requires exact finite smoke base')
    return {**base.environment(m),**PP_ENV}


def command(m,name):
    original=base.command(m,name)
    result=[]; index=0
    while index<len(original):
        if original[index]=='-e': index+=2
        else: result.append(original[index]); index+=1
    at=result.index('--entrypoint')
    for key,value in sorted(environment(m).items()):
        result[at:at]=['-e',key+'='+value]; at+=2
    return result


def request(model,prompt):
    return dict(model=model,messages=[{'role':'user','content':prompt}],
                max_tokens=1,temperature=0,stream=False,drafter='serial',
                reasoning_effort='none',enable_thinking=False)


def assess(parsed,target,wall_seconds):
    usage=parsed.get('usage'); timing=parsed.get('timings')
    if not isinstance(usage,dict) or not isinstance(timing,dict):
        raise ValueError('missing Halogen usage/timings')
    details=usage.get('prompt_tokens_details',{})
    fresh=timing.get('prompt_n'); cached=timing.get('cache_n')
    total=usage.get('prompt_tokens'); generated=timing.get('predicted_n')
    completion=usage.get('completion_tokens'); prompt_ms=timing.get('prompt_ms')
    decode_ms=timing.get('predicted_ms')
    if (not isinstance(details,dict) or
        ('cached_tokens' in details and
         (type(details['cached_tokens']) is not int or details['cached_tokens']!=0)) or
        any(type(x) is not int for x in (fresh,cached,total,generated,completion)) or
        fresh<0 or cached!=0 or total!=fresh or
        generated!=1 or completion!=1 or
        type(prompt_ms) not in (int,float) or type(decode_ms) not in (int,float) or
        not math.isfinite(prompt_ms) or not math.isfinite(decode_ms) or
        type(wall_seconds) not in (int,float) or not math.isfinite(wall_seconds) or
        prompt_ms<=0 or decode_ms<0 or not 0<wall_seconds<=REQUEST_SECONDS):
        raise ValueError('invalid cold PP counters or timing')
    if target is not None and abs(fresh-target)>32:
        raise ValueError('actual fresh token count outside target tolerance')
    over=prompt_ms+decode_ms-wall_seconds*1000
    return dict(actual_prompt_tokens=total,fresh_prompt_tokens=fresh,cached_prompt_tokens=cached,
                output_tokens=completion,engine_prefill_ms=prompt_ms,engine_decode_ms=decode_ms,
                http_wall_ms=wall_seconds*1000,http_pp_tps=fresh/wall_seconds,
                engine_pp_tps=fresh*1000/prompt_ms,engine_over_http_ms=over,
                engine_time_exceeds_http=over>0)


def check_pp_frame(frame,age=0):
    if not 0<=age<=2 or any(type(frame.get(key)) is not int or frame[key]<floor*base.GIB
        for key,floor in (('available_bytes',45),('commit_headroom_bytes',117))):
        raise ValueError('PP admission below reviewed 45/117 GiB floor')


def immediate_admission(host):
    base.exclusive_host()
    began=time.monotonic(); frame=host.frame()
    check_pp_frame(frame,time.monotonic()-began)
    return frame


def admission(host):
    base.exclusive_host()
    for index in range(ADMISSION_SAMPLES):
        began=time.monotonic(); frame=host.frame()
        check_pp_frame(frame,time.monotonic()-began)
        if index<ADMISSION_SAMPLES-1: time.sleep(1)
    return immediate_admission(host)


def validate_manifest(m):
    base.validate_manifest(m)
    if m['stage']!='smoke' or m['timeout_seconds']!=LIMIT_SECONDS:
        raise ValueError('PP base must use the exact 600s smoke manifest')
    return m


def offline(m):
    validate_manifest(m)
    base_seal=base.make_seal(m)
    sources=[Path(__file__),Path(base.__file__),Path(recipes.__file__),Path(client.__file__)]
    body=dict(schema=1,profile='halogen0142-cold-pp16k-v1',manifest=m,
              base_controller_sources=base_seal['controller_sources'],
              adapter_sources={str(path.resolve()):base.file_sha(path) for path in sources},
              schedule=schedule(),launch_environment=environment(m),
              admission={'physical_gib':45,'commit_gib':117,'runtime_physical_gib':12,
                         'runtime_commit_gib':12,'stable_samples':ADMISSION_SAMPLES},
              transport_contract={'timeout_semantics':'per-io-socket-timeout',
                                  'request_timeout_seconds':REQUEST_SECONDS,
                                  'completed_wall_max_seconds':REQUEST_SECONDS,
                                  'response_max_bytes':client.RESPONSE_LIMIT,
                                  'container_timeout_seconds':LIMIT_SECONDS,
                                  'container_kill_after_seconds':5},
              docker_argv=command(m,'halogen-flash-hybrid-0142-pp-DRYRUN'))
    return {**body,'seal_sha256':base.digest(body)}


def require_base_smoke(review,m):
    value=review.get('base_smoke_success_path'); expected=review.get('base_smoke_success_sha256')
    if not value or not expected: raise ValueError('reviewed release smoke success required')
    try: path=Path(value).resolve(strict=True)
    except (OSError,ValueError) as error:
        raise ValueError('base smoke success path unavailable') from error
    if (path.name!='success.json' or not path.is_relative_to(base.ARTIFACT_ROOT/'attempts') or
        base.file_sha(path)!=expected):
        raise ValueError('base smoke success identity invalid')
    success=base.read_json(path); seal=base.read_json(path.parent/'seal.json')
    outcome=base.read_json(path.parent/'outcome.json')
    release=base.read_json(path.parent/'release.json')
    if (success.get('stage')!='smoke' or success.get('cleanup') is not True or
        success.get('recovery') is not True or outcome.get('passed') is not True or
        release.get('guard_exit') is not True or seal.get('manifest',{}).get('stage')!='smoke' or
        seal['manifest'].get('artifacts')!=m['artifacts'] or
        success.get('seal_sha256')!=seal.get('seal_sha256') or
        base.make_seal(seal['manifest'])!=seal):
        raise ValueError('base release smoke no longer qualified for PP candidate')


def check_health(health,cid,name,m):
    versions=health.get('version') or {}
    if (health.get('status')!='ok' or versions.get('api')!='0.14.2' or
        versions.get('engine')!='0.14.2' or versions.get('match') is not True or
        health.get('context')!=16384 or health.get('kv_pool_positions')!=16384 or
        health.get('slots')!=1 or (health.get('prompt_cache') or {}).get('mode')!=0):
        raise ValueError('PP health/effective capacity mismatch')
    info=base.inspect(cid); base.owned(info,cid,name,m,running=True)
    check_effective_environment(info,m)


def check_effective_environment(info,m):
    actual=info['Config']['Env']
    for key,value in environment(m).items():
        if [entry for entry in actual if entry.startswith(key+'=')]!=[key+'='+value]:
            raise ValueError('effective PP container environment mismatch: '+key)
    if any(entry.startswith(('HALOGEN_CACHE_BRANCHES=','HALOGEN_CACHE_ENTRIES=',
                             'HALOGEN_CACHE_INPLACE=','HALOGEN_CACHE_SNAP3=',
                             'HALOGEN_CACHE_FULL=')) for entry in actual):
        raise ValueError('PP cache tuning variables must be absent')


def execute_rows(attempt,cid,watcher,health,deadline):
    counts=[]; results=[]
    for index,row in enumerate(schedule()):
        base.guard_alive(watcher,attempt)
        if time.monotonic()>=deadline: raise TimeoutError('PP container deadline')
        if row['kind']=='warmup': prompt='What is 2 + 2? Reply with only 4.'
        elif row['kind']=='calibration':
            prompt='x' if row['calibration']=='first' else 'x'+recipes.FILLER*20
        else:
            if len(counts)!=2: raise ValueError('calibration incomplete')
            prompt=recipes.calibrated_prompt(row['target'],*counts)
        body=request(health.get('model',MODEL),prompt)
        wire=client.packed(body)
        if len(wire)>262144: raise ValueError('PP request body exceeds bound')
        record=dict(ordinal=index,kind=row['kind'],target=row.get('target'),request=body,
                    request_base64=base64.b64encode(wire).decode(),
                    request_sha256=hashlib.sha256(wire).hexdigest())
        try:
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('PP container deadline')
            status,headers,raw,began,ended=client.exchange('POST','/v1/chat/completions',
                wire,timeout=min(REQUEST_SECONDS,remaining))
            record.update(http_status=status,response_headers=headers,
                response_base64=base64.b64encode(raw).decode(),
                response_sha256=hashlib.sha256(raw).hexdigest(),
                http_started_monotonic=began,http_ended_monotonic=ended,
                http_wall_seconds=ended-began)
            base.save(attempt/f'http-{index:02d}.json',record)
            if status!=200: raise ValueError('PP HTTP status not 200')
            parsed=client.strict_json(raw)
            if row['kind']=='warmup':
                try:
                    choice=parsed['choices'][0]
                    correct=(choice['message']['content'].strip()=='4' and
                             choice['finish_reason'] in ('stop','length'))
                except (KeyError,IndexError,TypeError,AttributeError): correct=False
                if not correct: raise ValueError('PP warmup answer incorrect')
            metrics=assess(parsed,row.get('target'),ended-began)
            if row['kind']=='calibration': counts.append(metrics['fresh_prompt_tokens'])
            if row['kind']=='measurement': results.append(dict(ordinal=index,target=row['target'],
                                                            metrics=metrics))
            base.save(attempt/f'parsed-{index:02d}.json',dict(response=parsed,metrics=metrics))
        except BaseException as error:
            if not (attempt/f'http-{index:02d}.json').exists():
                base.save(attempt/f'http-{index:02d}.json',{**record,'error':repr(error)})
            raise
        base.guard_alive(watcher,attempt)
    if len(results)!=6 or [x['target'] for x in results]!=[2048,8192,8192,2048,2048,8192]:
        raise ValueError('PP schedule incomplete')
    return results


def run(m,review):
    if os.name!='nt': raise ValueError('Windows controller required')
    validate_manifest(m); seal=offline(m)
    base.check_review(review,seal['seal_sha256'],'pp')
    require_base_smoke(review,m)
    attempts=base.ARTIFACT_ROOT/'attempts'; attempts.mkdir(exist_ok=True)
    name='halogen-flash-hybrid-0142-pp-'+uuid.uuid4().hex
    attempt=attempts/name; attempt.mkdir()
    base.save(attempt/'seal.json',seal); base.save(attempt/'review.json',review)
    base.save(attempt/'manifest.json',m)
    lock=base.ARTIFACT_ROOT/'runner.lock'; lock_handle=lock.open('x')
    cid=None; watcher=None; baseline=None; cleanup=False; recovery=False; creation_attempted=False
    outcome={'stage':'pp','passed':False}; cleanup_errors=[]
    try:
        _,host=base.guards(m)
        baseline=admission(host); base.save(attempt/'admission-create.json',baseline)
        if offline(m)!=seal: raise ValueError('PP seal changed before create')
        base.save(attempt/'admission-create-immediate.json',immediate_admission(host))
        creation_attempted=True
        cid=base.docker(*command(m,name),timeout=20)
        created=base.inspect(cid); base.owned(created,cid,name,m)
        check_effective_environment(created,m)
        base.save(attempt/'container.json',{'id':cid,'name':name})
        watcher=subprocess.Popen([sys.executable,str(Path(base.__file__)),'--manifest',
            str(attempt/'manifest.json'),'--guard',cid,'--name',name,'--attempt',str(attempt)],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        armed_deadline=time.monotonic()+15
        while not (attempt/'armed.json').exists():
            if watcher.poll() is not None or time.monotonic()>armed_deadline:
                raise RuntimeError('PP host guard not armed')
            time.sleep(.1)
        baseline=admission(host); base.save(attempt/'admission-start.json',baseline)
        if offline(m)!=seal: raise ValueError('PP seal changed before start')
        base.guard_alive(watcher,attempt)
        baseline=immediate_admission(host); base.save(attempt/'admission-start-immediate.json',baseline)
        base.docker('start',cid)
        deadline=time.monotonic()+LIMIT_SECONDS-5
        while time.monotonic()<deadline:
            base.guard_alive(watcher,attempt)
            current=base.inspect(cid); base.owned(current,cid,name,m)
            if not current['State']['Running']: raise RuntimeError('PP engine exited before readiness')
            try: health=base.http('/health')
            except (OSError,ValueError): health={}
            if health.get('status')=='ok': break
            startup,_=base.guards(m); startup.validate_target(current,cid)
            base.docker('exec',cid,'python3','-c',startup.CACHE_CODE,timeout=20)
            time.sleep(3)
        else: raise TimeoutError('PP readiness deadline')
        check_health(health,cid,name,m); base.save(attempt/'health.json',health)
        outcome['cells']=execute_rows(attempt,cid,watcher,health,deadline)
        raw=base.raw_samples(attempt)
        if not raw: raise ValueError('PP raw guest/GPU telemetry absent')
        for path in raw: base.validate_sample(base.read_json(path),cid)
        outcome['qualification_passed']=True
    except BaseException as error:
        outcome['error']=repr(error)
    finally:
        try:
            if not cid and creation_attempted:
                candidate=base.inspect(name); recovered_id=candidate['Id']
                base.owned(candidate,recovered_id,name,m); cid=recovered_id
            if cid:
                if watcher:
                    try: base.request_quiescence(attempt,cid,watcher)
                    except BaseException as error: cleanup_errors.append('quiescence: '+repr(error))
                else: cleanup_errors.append('quiescence: guard not started')
                terminal=base.stop_owned(cid,name,m); cleanup=True
                base.save(attempt/'terminal.json',terminal)
                try: base.validate_terminal(terminal['State'])
                except Exception as error: cleanup_errors.append('terminal: '+repr(error))
                try:
                    logs=subprocess.run(base.WSL+['docker','logs',cid],capture_output=True,text=True,
                        timeout=15,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    base.save(attempt/'container-logs.json',{'stdout':logs.stdout,'stderr':logs.stderr})
                except Exception as error: cleanup_errors.append('logs: '+repr(error))
            elif not creation_attempted: cleanup=True
            if baseline:
                _,host=base.guards(m); frames=[]; end=time.monotonic()+180
                while time.monotonic()<end:
                    began=time.monotonic(); frame=host.frame()
                    base.check_frame(frame,age=time.monotonic()-began); frames.append(frame)
                    if base.recovered(frames,baseline['available_bytes']): recovery=True; break
                    time.sleep(1)
                base.save(attempt/'recovery.json',{'frames':frames,'passed':recovery})
            if not cleanup or not recovery:
                raise RuntimeError('PP cleanup/recovery not established')
            if cleanup_errors: raise RuntimeError('; '.join(cleanup_errors))
            guard_code=base.finish_guard(attempt,cid,watcher) if watcher else None
            if watcher is None and cid: raise RuntimeError('PP host guard missing')
            if outcome.get('qualification_passed') and not outcome.get('error'):
                base.commit_release(attempt,cleanup=cleanup,recovery=recovery,
                    guard_returncode=guard_code,cleanup_errors=cleanup_errors,
                    qualification_passed=True,primary_error=None)
        except BaseException as error:
            outcome['cleanup_error']=repr(error)
        finally:
            if watcher and cleanup and watcher.poll() is None:
                watcher.terminate()
                try: watcher.wait(timeout=10)
                except subprocess.TimeoutExpired: watcher.kill(); watcher.wait(timeout=5)
            outcome.update(cleanup=cleanup,recovery=recovery,
                passed=bool(outcome.get('qualification_passed') and cleanup and recovery and
                            not outcome.get('error') and not outcome.get('cleanup_error') and
                            (attempt/'release.json').exists()))
            base.save(attempt/'outcome.json',outcome)
            lock_handle.close()
            if (attempt/'release.json').exists(): lock.unlink()
    if outcome['passed']:
        base.save(attempt/'success.json',{'stage':'pp','seal_sha256':seal['seal_sha256'],
                                         'cleanup':True,'recovery':True})
    return attempt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args(argv)
    m=base.read_json(args.manifest)
    if not args.run:
        print(json.dumps(offline(m),indent=2)); return 0
    if not args.review: parser.error('--run requires --review')
    attempt=run(m,base.read_json(args.review))
    print(attempt)
    return 0 if base.read_json(attempt/'outcome.json')['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
