"""Pinned Halogen 0.16.2 bounded WSL2 controller.

Trace4k must pass before Single4k; both exact-source qualifications must pass
before Serve4k. --print-only performs no model launch. Failed attempts and
owned-container cleanup evidence are retained; no unattended restart is provided.
"""
import argparse
import bridge_adapter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import portable
import shutil
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

GIB = 1 << 30
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARTIFACT_ROOT = ROOT / '.local'
CONTROL = HERE
IMAGE = portable.IMAGE
ENGINE_SHA = portable.RELEASE['engine_sha256']
SEQUENCE_SHA = '2578343f8d732785e630b385fd67bf71a17ba20cdf95b6b7cc90259bdccc886b'
WSL = None
PWSH = None
FIXED_MOUNTS = {}
MACHINE = None
TRACE_STATUS='/tmp/halogen0162-trace-status.json'
TRACE_RELEASE='/tmp/halogen0162-trace-release.json'
# Keep the SAME cgroup alive after the fast diagnostic child exits. Its peak is
# retained; Windows GPU counters collected here are explicitly post-engine-exit,
# not an observation of transient engine GPU allocations. timeout owns the group.
TRACE_WRAPPER = '''import json, os, pathlib, subprocess, sys, time
status, release = map(pathlib.Path, sys.argv[1:3])
hold = float(sys.argv[3])
child = subprocess.Popen(sys.argv[4:])
code = child.wait()
record = dict(schema=1, child_exit=code, child_pid=child.pid, child_finished_ns=time.time_ns())
temporary = status.with_suffix('.tmp')
with temporary.open('x') as stream:
    json.dump(record, stream)
os.rename(temporary, status)
if code != 1:
    raise SystemExit(code if code >= 0 else 128-code)
deadline = time.monotonic()+hold
while time.monotonic() < deadline:
    if release.exists():
        if json.loads(release.read_text()) != record:
            raise SystemExit(125)
        raise SystemExit(code)
    time.sleep(.05)
raise SystemExit(124)
'''
SEALED_SOURCES = sorted(HERE.glob('*.py'))+sorted(HERE.glob('*.ps1'))+sorted(HERE.glob('*.c'))+sorted((ROOT/'patches').iterdir())+[ROOT/'profiles/release.json',ROOT/'profiles/preflight-sequences.json']


def configure():
    global WSL,PWSH,FIXED_MOUNTS,MACHINE
    MACHINE=portable.installed()
    WSL=portable.wsl_command(MACHINE['distro'],MACHINE['user'],[])
    # installed() returns the validated session host in memory when explicitly
    # overridden; the sealed machine receipt keeps its original launcher path.
    PWSH=MACHINE['pwsh']
    FIXED_MOUNTS={'/models':MACHINE['models'],
                  '/usr/lib/libdxcore.so':'/usr/lib/wsl/lib/libdxcore.so',
                  '/usr/lib/librocdxg.so':MACHINE['dxg'],
                  # 0.16.2's bundled rocRoller has a WSL dynamic-version lookup failure.
                  # 0.16.0/0.15.1 ship this identical library; flash_serve 0.16.2
                  # resolves cleanly against it (validated with ldd -r and --help).
                  '/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1':
                      linux_path(ARTIFACT_ROOT/'librocroller-compat.so.1')}
    if MACHINE.get('ngram_source'):
        FIXED_MOUNTS['/ngram-w4b.hgn']=MACHINE['ngram_source']


def manifest_for(stage,serve_seconds=300):
    if stage not in ('trace','smoke','serve') or type(serve_seconds) is not int or not 30<=serve_seconds<=300:
        raise ValueError('Only Trace4k, Single4k and Serve4k (30..300 seconds) are supported')
    def item(path,sha,destination=None):
        data={'path':str(path),'sha256':sha}
        if destination: data['container_path']=destination
        return data
    pins=portable.RELEASE
    runtime={'entrypoint':('entrypoint-wsl.sh','adapted_entrypoint_sha256','/candidate/entrypoint-wsl-candidate.sh'),
             'bridge':('libhalogen0162-preflight.so','bridge_sha256','/candidate/libhalogen0162-preflight.so'),
             'private':('hip-register-private-rw.so','private_sha256','/candidate/hip-register-private-rw.so'),
             'probe':('halogen0162_hip_probe','probe_sha256','/candidate/halogen0162_hip_probe'),
             'engine':('flash_serve','engine_sha256',None)}
    a={key:item(ARTIFACT_ROOT/name,pins[pin],dest) for key,(name,pin,dest) in runtime.items()}
    a['sequences']=item(ROOT/'profiles/preflight-sequences.json',SEQUENCE_SHA)
    a['sources']=item(ROOT/'profiles/sources.json',file_sha(ROOT/'profiles/sources.json'))
    a['startup_cache']=item(HERE/'startup_cache.py',file_sha(HERE/'startup_cache.py'),
                            '/candidate/startup_cache.py')
    return {'schema':1,'stage':stage,'image':IMAGE,'engine_sha256':ENGINE_SHA,
            'timeout_seconds':600,'serve_seconds':serve_seconds,'artifacts':a,'machine':MACHINE}


def successful_stage(m,stage):
    expected=make_seal(manifest_for(stage))['seal_sha256']
    for path in sorted((ARTIFACT_ROOT/'attempts').glob('halogen-flash-hybrid-0151-'+stage+'-*/success.json'),reverse=True):
        record=read_json(path)
        if (record.get('seal_sha256')==expected and record.get('cleanup') is True and record.get('recovery') is True
                and read_json(path.parent/'outcome.json').get('passed') is True
                and (path.parent/'release.json').is_file()):
            return path
    raise ValueError('Run '+{'trace':'Trace4k','smoke':'Single4k'}[stage]+' successfully first; exact source/configuration qualification is missing')


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def read_json(path):
    from state_io import read_json as bounded_read
    return bounded_read(path)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def publish_record(path,value):
    """Publish a complete handshake JSON atomically, refusing existing finals."""
    path=Path(path)
    temporary=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temporary,path)  # atomic, no-overwrite publication on NTFS
    finally:
        temporary.unlink(missing_ok=True)


def make_seal(manifest):
    for artifact in manifest['artifacts'].values():
        if file_sha(artifact['path']) != artifact['sha256']:
            raise ValueError('artifact hash mismatch: '+artifact['path'])
    sources=set(SEALED_SOURCES)|set(HERE.glob('*.py'))|set(HERE.glob('*.c'))
    body = {'manifest':manifest, 'controller_sources':
            {str(path.resolve()):file_sha(path) for path in sorted(sources)},
            'launch_environment':environment(manifest) if 'stage' in manifest else None}
    return {**body, 'seal_sha256':digest(body)}


def check_review(review, seal_sha, stage):
    if (review.get('approved') is not True or review.get('stage') != stage or
        review.get('seal_sha256') != seal_sha or
        not str(review.get('reviewer','')).strip() or
        not str(review.get('allocation_reason','')).strip()):
        raise ValueError('stage-specific allocation/source review required')


def require_trace(m,review=None):
    if m['stage'] in ('smoke','serve'): successful_stage(m,'trace')
    if m['stage']=='serve': successful_stage(m,'smoke')


def check_frame(frame, *, admission=False, age=0):
    physical, commit = (45,117) if admission else (12,12)
    if not 0 <= age <= 2 or any(type(frame.get(k)) is not int or frame[k] < floor*GIB
        for k,floor in [('available_bytes',physical),('commit_headroom_bytes',commit)]):
        raise ValueError('missing/stale/unsafe direct Windows memory frame')


def recovered(frames, before):
    return len(frames) >= 5 and all(f.get('available_bytes',0) >= max(24*GIB,before-2*GIB)
           and f.get('commit_headroom_bytes',0) >= 12*GIB for f in frames[-5:])


def validate_trace(log, exit_code, vector):
    active = f'[preflight-bridge] active sha256={ENGINE_SHA} rva={hex(bridge_adapter.SITE_RVA)} trace=1'
    rows = re.findall(r'\[preflight-bridge\] range\[(\d+)\]=(\d+):(\d+)',log)
    demand = re.findall(r'\[preflight-bridge\] demand aggregate=(\d+) host=(\d+) mapping=(\d+) count=(\d+) floor=(\d+)',log)
    plan = re.findall(r'\[preflight\] plan phase=1 ranges=(\d+) aggregate=(\d+) copy=(\d+) host=(\d+)',log)
    # start_engine converts a pre-readiness child exit to wrapper status 1.
    # The sealed bridge exits 77 at this site; that child status is not exposed.
    if (exit_code != 1 or log.count(active) != 1 or len(demand) != 1 or len(plan) != 1 or
        [int(i) for i,_,_ in rows] != list(range(len(vector))) or
        [int(end)-int(begin) for _,begin,end in rows] != vector or
        re.search(r'\[hybrid\] (?:device-copy bytes|copy-cache|host reserve|failed-copy)|'
                  r'\[private-rw\] (?:register|refuse)|\[preflight\] (?:execute|complete|reject)',log)):
        raise ValueError('trace did not prove exact vector and pre-registration exit')
    aggregate,host,mapping,count,floor = map(int,demand[0])
    n,total,copy,h = map(int,plan[0])
    if (aggregate != sum(vector) or count != len(vector) or floor != 16*GIB or
        n != count or total != aggregate or h != host or copy+host != aggregate or
        copy > 48*GIB or mapping < aggregate):
        raise ValueError('trace allocation arithmetic mismatch')
    if len(vector)==252 and (aggregate,copy,host,mapping)!=(70434994368,50433337536,20001656832,124068083904):
        raise ValueError('trace differs from reviewed exact allocation')


def trace_vector(path):
    if file_sha(path)!=SEQUENCE_SHA:
        raise ValueError('frozen registration sequences changed')
    vectors=read_json(path)
    if len(vectors)!=2 or vectors[0]!=vectors[1] or len(vectors[0])!=253:
        raise ValueError('unreviewed planner vector shape')
    return vectors[0][:-1]  # trace exits before the later overlay registration


def validate_terminal(state,trace=False):
    if (state.get('Running') is not False or state.get('Pid')!=0 or
        state.get('OOMKilled') is not False or state.get('Error')!='' or
        (trace and state.get('ExitCode')!=1)):
        raise ValueError('container terminal status unsafe or unexpected')


def linux_path(path):
    value = Path(path).resolve().as_posix()
    if not re.match(r'^[A-Za-z]:/',value):
        raise ValueError('candidate requires an absolute Windows path')
    return '/mnt/'+value[0].lower()+value[2:]


def validate_manifest(m):
    if (m.get('schema') != 1 or m.get('stage') not in ('trace','smoke','serve') or
        m.get('image') != IMAGE or m.get('engine_sha256') != ENGINE_SHA or
        type(m.get('timeout_seconds')) is not int or not 30 <= m['timeout_seconds'] <= 600):
        raise ValueError('candidate identity/stage/deadline invalid')
    if m != manifest_for(m['stage'],m.get('serve_seconds',300)):
        raise ValueError('Only the installed fixed 4K profile is permitted')
    artifacts=m['artifacts']
    if not {'entrypoint','bridge','private','probe','engine','sequences','sources','startup_cache'} <= artifacts.keys():
        raise ValueError('missing candidate artifact role')
    destinations=[]
    for key,item in artifacts.items():
        path=Path(item['path']).resolve(strict=True)
        if not path.is_file() or not re.fullmatch('[0-9a-f]{64}',item['sha256']):
            raise ValueError('invalid artifact: '+key)
        destination=item.get('container_path')
        if destination is not None:
            if not re.fullmatch(r'/candidate/[A-Za-z0-9_.-]+',destination):
                raise ValueError('candidate mount outside fixed namespace')
            if key == 'startup_cache':
                if path != (HERE/'startup_cache.py').resolve() or Path(item['path']).is_symlink():
                    raise ValueError('memory sampler must use the exact package startup-cache source')
            elif not path.is_relative_to(ARTIFACT_ROOT.resolve()):
                raise ValueError('mounted artifact outside candidate root')
            destinations.append(destination)
    if len(set(destinations)) != len(destinations): raise ValueError('duplicate mount')
    for key in ('entrypoint','bridge','private','probe','startup_cache'):
        if not artifacts[key].get('container_path'): raise ValueError('missing runtime artifact mount')
    if artifacts['probe']['container_path'] != '/candidate/halogen0162_hip_probe':
        raise ValueError('probe must be at fixed entrypoint path')
    if artifacts['startup_cache']['container_path'] != '/candidate/startup_cache.py':
        raise ValueError('memory sampler must be at fixed startup-cache path')
    if artifacts['engine']['sha256'] != ENGINE_SHA: raise ValueError('wrong engine artifact')
    return trace_vector(artifacts['sequences']['path'])


def mounts(m):
    return {**FIXED_MOUNTS, **{v['container_path']:linux_path(v['path'])
           for v in m['artifacts'].values() if v.get('container_path')}}


def environment(m):
    a=m['artifacts']
    return dict(HALOGEN_WSL_PROFILE='halogen0162-dxg', HALOGEN_CTX='4096', HALOGEN_CHECKPOINT='/models/qwen38-flash-next-w4b.hgn', HALOGEN_CK_OVERLAY='/models/qwen38-flash-next-w4b.overlay.hgn',
        HALOGEN_PREFLIGHT_PROFILE='flash0162-copy48-v1', HALOGEN_HYBRID_PROFILE='vgm64-copy48-v1',
        HALOGEN_KV_POOL_POSITIONS='4096', HALOGEN_KV_SLOTS='1', HALOGEN_PREFILL_CHUNK='2048',
        HALOGEN_MAX_TOK='2048', HALOGEN_HOST_RESERVE_GIB='12', HALOGEN_HYBRID_COPY_BYTES=str(48*GIB),
        HALOGEN_HYBRID_RECLAIM_COPY='1', HALOGEN_FLASH_PIN_TRUNK='1', HALOGEN_FLASH_ROUTE_GEMM='0',
        HALOGEN_PROMPT_CACHE='0', HALOGEN_TOPK_REPLAY='0', HALOGEN_DMALLOC_LOG='1',
        HALOGEN_VERBOSE='1', HALOGEN_ENGINE_WATCHDOG_S='120', HALOGEN_TOKENIZER='/models/tokenizer',
        HALOGEN_PREFLIGHT_TRACE_ONLY='1' if m['stage']=='trace' else '0',
        HSA_ENABLE_SDMA='1', HSA_ENABLE_DXG_DETECTION='1', AMD_SERIALIZE_KERNEL='0',
        AMD_SERIALIZE_COPY='0', LD_PRELOAD=a['bridge']['container_path']+':'+a['private']['container_path'])


def command(m, name):
    cmd=['create','--name',name,'--memory',str(44*GIB),'--memory-swap',str(44*GIB),
         '--restart=no','--device=/dev/dxg','--ipc=host','--shm-size=8g',
         '--cap-add=SYS_PTRACE','--security-opt=seccomp=unconfined','--security-opt=label=disable',
         '--ulimit=memlock=-1:-1','-p','127.0.0.1:8731:8731',
         '--label=halogen.performance=hybrid','--label=strix-alloy.owner=strix-alloy-wsl2',
         '--label=strix-alloy.run='+name]
    for destination,source in sorted(mounts(m).items()):
        cmd += ['--mount',f'type=bind,src={source},dst={destination},readonly']
    for key,value in sorted(environment(m).items()): cmd += ['-e',key+'='+value]
    # A process-tree deadline survives host controller death. No shell expansion.
    child=['/bin/bash',m['artifacts']['entrypoint']['container_path'],
           'engine' if m['stage']=='trace' else 'all']
    if m['stage']=='trace':
        child=['python3','-c',TRACE_WRAPPER,TRACE_STATUS,TRACE_RELEASE,'45',*child]
    return cmd+['--entrypoint','/usr/bin/timeout',IMAGE,'--signal=TERM','--kill-after=5',
               str(m['timeout_seconds']),*child]


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def guards(m):
    startup=load_module('candidate_startup_guard',CONTROL/'startup_guard.py')
    startup.IMAGE=IMAGE; startup.REVIEWED_IMAGES=frozenset([IMAGE])
    startup.WSL=WSL+['docker']; startup.EXPECTED_MOUNTS=mounts(m)
    host=load_module('candidate_host_frames',CONTROL/'host_frames.py')
    return startup,host


def invoke(argv,timeout=10):
    return subprocess.run(argv,capture_output=True,text=True,check=True,timeout=timeout,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout.strip()


def docker(*args,timeout=10): return invoke(WSL+['docker',*args],timeout)


def inspect(cid): return json.loads(docker('inspect',cid))[0]


def owned(info,cid,name,m,running=False):
    config=info.get('Config',{}); labels=config.get('Labels') or {}
    if (not re.fullmatch('[0-9a-f]{64}',cid) or info.get('Id') != cid or
        info.get('Name') != '/'+name or labels.get('strix-alloy.run') != name or
        labels.get('strix-alloy.owner') != 'strix-alloy-wsl2' or config.get('Image') != IMAGE):
        raise ValueError('owned candidate identity changed')
    if running:
        startup,_=guards(m); startup.validate_target(info,cid)


def stop_owned(cid,name,m):
    current=inspect(cid); owned(current,cid,name,m)
    if current['State']['Running']: docker('stop','-t','0',cid,timeout=45)
    current=inspect(cid); owned(current,cid,name,m)
    if current['State']['Running'] or current['State']['Pid'] != 0:
        raise ValueError('owned container not terminal')
    return current


def exclusive_host():
    if docker('ps','-q'): raise ValueError('another container is running')
    native=invoke(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        "@(Get-Process -Name 'llama-server','flash_serve','gufo','gufo-server','nativeengine' -ErrorAction SilentlyContinue).Count"])
    if native != '0': raise ValueError('native model engine running')


def immediate_admission(host):
    exclusive_host()
    began=time.monotonic(); frame=host.frame()
    check_frame(frame,admission=True,age=time.monotonic()-began)
    return frame


def admission(host):
    exclusive_host()
    for index in range(60):
        began=time.monotonic(); frame=host.frame()
        check_frame(frame,admission=True,age=time.monotonic()-began)
        if index<59: time.sleep(1)
    return immediate_admission(host)


def guard_process(m,cid,name,attempt):
    startup,host=guards(m); started=time.monotonic()
    sampler=ThreadPoolExecutor(max_workers=1); pending=None; last_sample=0; sample_started=0; index=0
    try:
        owned(inspect(cid),cid,name,m)
        while time.monotonic()-started <= m['timeout_seconds']+240:
            began=time.monotonic(); frame=host.frame()
            check_frame(frame,age=time.monotonic()-began)
            with (attempt/'host-guard.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'monotonic':time.monotonic(),**frame})+'\n'); stream.flush()
            if not (attempt/'armed.json').exists(): save(attempt/'armed.json',frame)
            if pending is not None:
                if pending.done():
                    validate_sample(pending.result(),cid)
                    last_sample=time.monotonic(); pending=None
                elif time.monotonic()-sample_started>35:
                    raise TimeoutError('raw guest/GPU telemetry stale')
            quiesce=attempt/'quiesce-request.json'
            if quiesce.exists():
                request=read_json(quiesce)
                if request != {'schema':1,'container_id':cid}:
                    raise ValueError('invalid quiesce request')
                if pending is None and not (attempt/'quiesce-ack.json').exists():
                    publish_record(attempt/'quiesce-ack.json',request)
            current=inspect(cid); owned(current,cid,name,m)
            if current['State']['Running']:
                startup.validate_target(current,cid)
                # Trace telemetry is synchronously collected after its child
                # exits, while its original cgroup is held alive. Direct host
                # frames above remain continuous throughout both trace phases.
                if m['stage'] in ('smoke','serve') and not quiesce.exists() and pending is None and time.monotonic()-last_sample>=10:
                    sample_started=time.monotonic()
                    pending=sampler.submit(sample,cid,attempt,'inference',index)
                    index+=1
            exit_request=attempt/'guard-exit-request.json'
            if exit_request.exists():
                if read_json(exit_request) != {'schema':1,'container_id':cid} or pending is not None:
                    raise ValueError('invalid guard exit request or active sampler')
                if not (attempt/'quiesce-ack.json').exists():
                    raise ValueError('guard exit before sampler quiescence')
                publish_record(attempt/'guard-exit-ack.json',{'schema':1,'container_id':cid})
                return 0
            time.sleep(1)
        raise TimeoutError('independent host guard deadline')
    except BaseException as error:
        try: save(attempt/'guard-failure.json',{'error':repr(error)})
        finally: stop_owned(cid,name,m)
        return 2
    finally:
        sampler.shutdown(wait=False,cancel_futures=True)


def guard_alive(process,attempt):
    path=attempt/'host-guard.jsonl'
    if process.poll() is not None or not path.exists() or time.time()-path.stat().st_mtime > 12:
        raise RuntimeError('independent guard missing/stale/dead')


def request_quiescence(attempt,cid,watcher,timeout=40):
    publish_record(attempt/'quiesce-request.json',{'schema':1,'container_id':cid})
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        guard_alive(watcher,attempt)
        ack=attempt/'quiesce-ack.json'
        if ack.exists():
            if read_json(ack)!={'schema':1,'container_id':cid}:
                raise ValueError('invalid sampler quiescence ACK')
            return
        time.sleep(.1)
    raise TimeoutError('sampler quiescence not confirmed')


def finish_guard(attempt,cid,watcher,timeout=15):
    guard_alive(watcher,attempt)
    publish_record(attempt/'guard-exit-request.json',{'schema':1,'container_id':cid})
    try: code=watcher.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error: raise TimeoutError('host guard exit not confirmed') from error
    ack=attempt/'guard-exit-ack.json'
    if code!=0 or not ack.exists() or read_json(ack)!={'schema':1,'container_id':cid}:
        raise RuntimeError('host guard failed or exit ACK invalid')
    if (attempt/'guard-failure.json').exists():
        raise RuntimeError('host guard recorded failure')
    return code


def commit_release(attempt,*,cleanup,recovery,guard_returncode,cleanup_errors,
                   qualification_passed,primary_error):
    if (not cleanup or not recovery or guard_returncode!=0 or cleanup_errors or
        qualification_passed is not True or primary_error is not None):
        raise RuntimeError('release prerequisites incomplete')
    save(attempt/'release.json',{'cleanup':True,'recovery':True,'guard_exit':True})


def raw_samples(attempt):
    return sorted(path for path in attempt.glob('telemetry-*.json')
                  if re.fullmatch(r'telemetry-\d{4}\.json',path.name))


def sample(cid,attempt,phase,index):
    path=attempt/f'telemetry-{index:04d}.json'
    argv=[PWSH,'-NoProfile','-NonInteractive','-File',str(CONTROL/'sample.ps1'),
          '-ContainerId',cid,'-Output',str(path),'-Phase',phase,
          '-Distribution',MACHINE['distro'],'-LinuxUser',MACHINE['user']]
    started=datetime.now(timezone.utc).isoformat()
    code=None; stdout=''; stderr=''; failure=None
    try:
        result=subprocess.run(argv,capture_output=True,text=True,check=False,timeout=35,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        code=result.returncode; stdout=result.stdout; stderr=result.stderr
    except subprocess.TimeoutExpired as error:
        failure='timeout'
        stdout=error.stdout or ''; stderr=error.stderr or ''
        if isinstance(stdout,bytes): stdout=stdout.decode(errors='replace')
        if isinstance(stderr,bytes): stderr=stderr.decode(errors='replace')
    except OSError as error:
        failure=repr(error)
        raise
    finally:
        save(attempt/f'telemetry-{index:04d}-process.json',{
            'phase':phase,'container_id':cid,'started_utc':started,
            'ended_utc':datetime.now(timezone.utc).isoformat(),
            'returncode':code,'stdout':stdout,'stderr':stderr,'failure':failure})
    if failure or code!=0: raise RuntimeError(f'sampler {index} failed: {failure or code}')
    return read_json(path)


def validate_sample(record,cid):
    guest=record.get('guest') or {}; gpu=record.get('gpuInstances') or []
    if (record.get('containerId') != cid or not gpu or
        any(type(guest.get(key)) is not int or guest[key]<0
            for key in ('memory.current','memory.peak','memory.swap.current')) or
        any(not item.get('name') or any(type(item.get(k)) is not int or item[k]<0
            for k in ('dedicatedBytes','sharedBytes','totalCommittedBytes')) for item in gpu)):
        raise ValueError('missing raw guest/GPU telemetry')


def trace_status(cid):
    raw=docker('exec',cid,'python3','-c',
        'import pathlib,sys; p=pathlib.Path(sys.argv[1]); print(p.read_text() if p.exists() else "null")',
        TRACE_STATUS)
    return json.loads(raw)


def complete_trace_telemetry(cid,attempt,status,check_guard=lambda: None):
    if (status.get('schema')!=1 or status.get('child_exit')!=1 or
        type(status.get('child_pid')) is not int or status['child_pid']<=0 or
        type(status.get('child_finished_ns')) is not int or status['child_finished_ns']<=0):
        raise ValueError('unexpected trace child status')
    check_guard()
    record=sample(cid,attempt,'final',9998)
    validate_sample(record,cid)
    save(attempt/'trace-telemetry.json',dict(
        scope='same-container-cgroup-peak-and-post-engine-exit-gpu-snapshot',
        cgroup_peak_scope='whole container lifetime including entrypoint, engine, wrapper and telemetry processes',
        child_status=status, telemetry=record,
        transient_engine_gpu_peak_observed=False))
    check_guard()
    # Acknowledge only after the required genuine measurement is saved. Exact
    # child identity/status is echoed; empty or stale release files fail closed.
    docker('exec',cid,'python3','-c',
        'import pathlib,sys; p=pathlib.Path(sys.argv[1]); t=p.with_suffix(".tmp"); '
        't.write_text(sys.argv[2]); t.rename(p)',TRACE_RELEASE,json.dumps(status,sort_keys=True))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def http(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:8731'+path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=45 if body else 3) as response:
        raw=response.read(1<<20)
        if response.read(1): raise ValueError('oversized API response')
        return json.loads(raw)


def run(m,review,manifest_path):
    if os.name != 'nt': raise ValueError('Windows controller required')
    vector=validate_manifest(m); seal=make_seal(m)
    require_trace(m,review)
    attempts=ARTIFACT_ROOT/'attempts'; attempts.mkdir(exist_ok=True)
    name='halogen-flash-hybrid-0151-'+m['stage']+'-'+uuid.uuid4().hex
    attempt=attempts/name; attempt.mkdir()
    save(attempt/'seal.json',seal); save(attempt/'manifest.json',m)
    lock=ARTIFACT_ROOT/'runner.lock'; lock_handle=lock.open('x')
    cid=None; watcher=None; baseline=None; cleanup=False; recovery=False; creation_attempted=False
    outcome={'passed':False,'stage':m['stage']}; cleanup_errors=[]
    try:
        _,host=guards(m)
        baseline=admission(host); save(attempt/'admission-create.json',baseline)
        if make_seal(m) != seal: raise ValueError('seal changed before create')
        save(attempt/'admission-create-immediate.json',immediate_admission(host))
        creation_attempted=True
        cid=docker(*command(m,name),timeout=20)
        owned(inspect(cid),cid,name,m); save(attempt/'container.json',{'id':cid,'name':name})
        watcher=subprocess.Popen([sys.executable,str(Path(__file__)),'--manifest',str(attempt/'manifest.json'),
            '--guard',cid,'--name',name,'--attempt',str(attempt)],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        armed_deadline=time.monotonic()+15
        while not (attempt/'armed.json').exists():
            if watcher.poll() is not None or time.monotonic()>armed_deadline: raise RuntimeError('guard not armed')
            time.sleep(.1)
        fresh=admission(host); save(attempt/'admission-start.json',fresh)
        baseline=fresh
        if make_seal(m) != seal: raise ValueError('seal changed before start')
        guard_alive(watcher,attempt)
        baseline=immediate_admission(host); save(attempt/'admission-start-immediate.json',baseline)
        docker('start',cid)
        deadline=time.monotonic()+m['timeout_seconds']; ready=False; trace_sampled=False
        last_advice=0
        while time.monotonic()<deadline:
            guard_alive(watcher,attempt)
            current=inspect(cid); owned(current,cid,name,m)
            if not current['State']['Running']:
                # Docker puts engine diagnostics on stderr; collect both streams below.
                result=subprocess.run(WSL+['docker','logs',cid],capture_output=True,text=True,timeout=15,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
                logs=result.stdout+result.stderr
                save(attempt/'trace-log.json',{'log':logs,'state':current['State']})
                if m['stage'] != 'trace': raise RuntimeError('engine exited before smoke')
                if not trace_sampled: raise RuntimeError('trace exited without telemetry handshake')
                validate_terminal(current['State'],trace=True)
                validate_trace(logs,current['State']['ExitCode'],vector)
                break
            if m['stage']=='trace' and not trace_sampled:
                status=trace_status(cid)
                if status is not None:
                    complete_trace_telemetry(cid,attempt,status,lambda: guard_alive(watcher,attempt))
                    trace_sampled=True
            if m['stage'] in ('smoke','serve'):
                try: health=http('/health')
                except (OSError,ValueError): health={}
                if health.get('status')=='ok':
                    ready=True; save(attempt/'health.json',health)
                    versions=health.get('version',{})
                    if versions.get('api')!='0.16.2' or versions.get('engine')!='0.16.2' or versions.get('match') is not True:
                        raise ValueError('engine/API version mismatch')
                    for label,prompt,answer in [('arithmetic','Antworte nur mit der Zahl: Was ist 17 + 25?','42'),
                        ('german','Antworte auf Deutsch mit genau einem Wort: Welche Farbe hat Gras?','grün')]:
                        guard_alive(watcher,attempt)
                        body={'model':health.get('model','qwen38-flash-next-w4b'),'messages':[{'role':'user','content':prompt}],
                              'max_tokens':32,'temperature':0,'stream':False,'drafter':'serial',
                              'reasoning_effort':'none','enable_thinking':False}
                        response=http('/v1/chat/completions',body)
                        save(attempt/(label+'.json'),{'request':body,'response':response})
                        content=response['choices'][0]['message']['content'].strip().strip('.!').casefold()
                        if content != answer: raise ValueError('incorrect smoke answer: '+label)
                    if m['stage']=='serve':
                        serve_until=time.monotonic()+m['serve_seconds']
                        if serve_until+40>deadline: raise RuntimeError('Insufficient remaining container lifetime for bounded serving')
                        print('READY: Halogen 0.16.2 http://127.0.0.1:8731/v1; bounded serving '+str(m['serve_seconds'])+' seconds',flush=True)
                        while time.monotonic()<serve_until:
                            guard_alive(watcher,attempt)
                            current=inspect(cid); owned(current,cid,name,m,running=True)
                            time.sleep(1)
                    validate_sample(sample(cid,attempt,'final',9999),cid)
                    break
                if not ready and time.monotonic()-last_advice>=3:
                    startup,_=guards(m)
                    startup.validate_target(inspect(cid),cid)
                    docker('exec',cid,'python3','-c',startup.CACHE_CODE,timeout=20)
                    last_advice=time.monotonic()
            time.sleep(1)
        else: raise TimeoutError('candidate qualification deadline')
        observed=raw_samples(attempt)
        if not observed: raise RuntimeError('no complete raw guest/GPU telemetry frame')
        for path in observed: validate_sample(read_json(path),cid)
        save(attempt/'qualification.json',{'stage':m['stage'],'passed':True})
        outcome['qualification_passed']=True
    except BaseException as error:
        outcome['error']=repr(error)
        raise
    finally:
        try:
            if not cid and creation_attempted:
                # Recover only this randomly named owned candidate after a lost
                # create response, never enumerate/terminate unrelated engines.
                candidate=inspect(name)
                recovered_id=candidate['Id']; owned(candidate,recovered_id,name,m)
                cid=recovered_id
            if cid:
                if watcher:
                    try: request_quiescence(attempt,cid,watcher)
                    except BaseException as error:
                        cleanup_errors.append('sampler quiescence: '+repr(error))
                else:
                    cleanup_errors.append('sampler quiescence: guard not started')
                terminal=stop_owned(cid,name,m); cleanup=True
                save(attempt/'terminal.json',terminal)
                try: validate_terminal(terminal['State'],trace=m['stage']=='trace' and bool(outcome.get('qualification_passed')))
                except Exception as error: cleanup_errors.append(repr(error))
                try:
                    logs=subprocess.run(WSL+['docker','logs',cid],capture_output=True,text=True,timeout=15,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
                    save(attempt/'container-logs.json',{'stdout':logs.stdout,'stderr':logs.stderr})
                except Exception as error: cleanup_errors.append('logs: '+repr(error))
            elif not creation_attempted:
                cleanup=True
            if baseline:
                _,host=guards(m); frames=[]; deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    began=time.monotonic(); frame=host.frame(); check_frame(frame,age=time.monotonic()-began)
                    frames.append(frame)
                    if recovered(frames,baseline['available_bytes']): recovery=True; break
                    time.sleep(1)
                save(attempt/'recovery.json',{'frames':frames,'passed':recovery})
            if not cleanup or not recovery:
                raise RuntimeError('cleanup/recovery not established; retain lock and evidence')
            if cleanup_errors:
                raise RuntimeError('; '.join(cleanup_errors))
            guard_code=finish_guard(attempt,cid,watcher) if watcher else None
            if watcher is None and cid:
                raise RuntimeError('host guard missing')
            if outcome.get('qualification_passed') and not outcome.get('error'):
                commit_release(attempt,cleanup=cleanup,recovery=recovery,
                               guard_returncode=guard_code,cleanup_errors=cleanup_errors,
                               qualification_passed=True,primary_error=None)
        except BaseException as error:
            outcome['cleanup_error']=repr(error)
            raise
        finally:
            # Once the owned container is terminal, reap our guard process even
            # when host recovery failed. Its helper subprocesses have deadlines.
            if watcher and cleanup and watcher.poll() is None:
                watcher.terminate()
                try: watcher.wait(timeout=10)
                except subprocess.TimeoutExpired: watcher.kill(); watcher.wait(timeout=5)
            outcome.update(cleanup=cleanup,recovery=recovery,
                           passed=bool(outcome.get('qualification_passed') and cleanup and recovery
                                       and not outcome.get('error') and not outcome.get('cleanup_error')))
            save(attempt/'outcome.json',outcome)
            lock_handle.close()
            if (attempt/'release.json').exists(): lock.unlink()
    save(attempt/'success.json',{'stage':m['stage'],'seal_sha256':seal['seal_sha256'],'cleanup':True,'recovery':True})
    return attempt


def main(argv=None):
    parser=argparse.ArgumentParser(description='Pinned Halogen 0.16.2 bounded WSL2 controller')
    parser.add_argument('--profile',choices=['Trace4k','Single4k','Serve4k'],default='Single4k')
    parser.add_argument('--serve-seconds',type=int,default=300)
    parser.add_argument('--print-only',action='store_true')
    parser.add_argument('--manifest',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--guard',help=argparse.SUPPRESS)
    parser.add_argument('--name',help=argparse.SUPPRESS)
    parser.add_argument('--attempt',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    configure()
    m=read_json(args.manifest) if args.manifest else manifest_for(
        {'Trace4k':'trace','Single4k':'smoke','Serve4k':'serve'}[args.profile],args.serve_seconds)
    validate_manifest(m)
    if args.guard:
        if not args.attempt or args.attempt.resolve().parent!=(ARTIFACT_ROOT/'attempts').resolve():
            raise ValueError('Guard attempt path outside local attempts')
        return guard_process(m,args.guard,args.name,args.attempt)
    if args.print_only:
        print(json.dumps({**make_seal(m),'docker_argv':command(m,'halogen-flash-hybrid-0151-DRYRUN')},indent=2))
        return 0
    actual=portable.preflight(MACHINE['distro'],MACHINE['user'],MACHINE['models'],MACHINE['dxg'])
    if actual!=MACHINE: raise ValueError('Installed machine configuration drift')
    print(run(m,None,args.manifest),flush=True)
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr); raise SystemExit(2)
