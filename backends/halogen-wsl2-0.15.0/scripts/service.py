# Interactive Halogen serving. Legacy finite qualification lives in runner.py.
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import portable
from startup_monitor import StartupMonitor
import runner as r
import startup_guard as sg
from lease_supervisor import fresh, lease_record

DEFAULT_CONTEXT = 126 * 1024
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
API = 'http://127.0.0.1:8731'
MODEL = 'halogen-qwen3.8-flash-next'
TOKEN_PATH = LOCAL / 'api-token.txt'
STATE_PATH = LOCAL / 'current-service.json'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def options(argv=None):
    p = argparse.ArgumentParser(description='Halogen service: authenticated, logged, continuous by default')
    p.add_argument('--context-size',type=int,default=DEFAULT_CONTEXT)
    p.add_argument('--serve-seconds',type=int,default=0,help='0 means until explicitly stopped')
    p.add_argument('--startup-timeout',type=int,default=900)
    p.add_argument('--print-only',action='store_true')
    group=p.add_mutually_exclusive_group()
    group.add_argument('--stop',action='store_true')
    group.add_argument('--status',action='store_true')
    p.add_argument('--guard',type=Path,help=argparse.SUPPRESS)
    o=p.parse_args([] if argv is None else argv)
    validate_options(o)
    return o


def validate_options(o):
    if type(o.context_size) is not int or not 4096 <= o.context_size <= 262144:
        raise ValueError('ContextSize must be 4096..262144 positions (prompt + output), one slot')
    if type(o.serve_seconds) is not int or not 0 <= o.serve_seconds <= 604800:
        raise ValueError('ServeSeconds must be 0 (continuous) or 1..604800')
    if type(o.startup_timeout) is not int or not 120 <= o.startup_timeout <= 3600:
        raise ValueError('StartupTimeoutSeconds must be 120..3600; it is not a serving timeout')


def floors(context):
    # Observed 4K worst case: 26.257 GiB physical decline / 100.247 GiB commit.
    # Add 4 GiB uncertainty, 12 GiB residual and 32 KiB/extra KV position.
    # This is admission planning, NOT a proof of worst-case driver residency.
    delta=max(0,context-4096)*32768/r.GIB
    return max(45,math.ceil(26.257+4+12+delta)), max(117,math.ceil(100.247+4+12+delta))


def atomic(path, value):
    path=Path(path)
    tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with tmp.open('x',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=True); f.flush(); os.fsync(f.fileno())
        # Windows readers (including WSL/DrvFS) may briefly deny rename/delete.
        # Retry this SAME complete snapshot, never truncate the live file or
        # renew its timestamp. The 2 s retry budget is below the 12 s guard
        # freshness and 45 s container lease deadlines; persistent errors fail.
        deadline=time.monotonic()+2.0
        retries=0
        while True:
            try:
                os.replace(tmp,path)
                break
            except OSError as exc:
                if getattr(exc,'winerror',None) not in (5,32,33):
                    raise
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    exc.add_note('Atomic state replacement retry budget exhausted (2 seconds)')
                    raise
                time.sleep(min(0.025*(2**min(retries,3)),remaining))
                retries+=1
    finally:
        tmp.unlink(missing_ok=True)


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def logger(path, console=False, raw=False):
    log=logging.getLogger(str(path)); log.setLevel(logging.INFO); log.propagate=False
    for handler in log.handlers[:]: handler.close(); log.removeHandler(handler)
    file=RotatingFileHandler(path,maxBytes=10*1024*1024,backupCount=5,encoding='utf-8')
    fmt=logging.Formatter('%(message)s' if raw else '%(asctime)s %(message)s')
    file.setFormatter(fmt); log.addHandler(file)
    if console:
        handler=logging.StreamHandler(sys.stdout); handler.setFormatter(fmt); log.addHandler(handler)
    return log


def token():
    portable.reject_links(TOKEN_PATH)
    if not TOKEN_PATH.exists():
        value=secrets.token_urlsafe(32)
        fd=os.open(str(TOKEN_PATH),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='ascii') as f: f.write(value+'\n')
    value=TOKEN_PATH.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}',value):
        raise ValueError('API token file is invalid; do not silently replace a configured token')
    if os.name=='nt':
        user=subprocess.run(['whoami','/user','/fo','csv','/nh'],check=True,capture_output=True,text=True)
        sid=next(csv.reader(user.stdout.strip().splitlines()))[-1]
        if not re.fullmatch(r'S-1-[0-9-]+',sid): raise ValueError('Cannot resolve token owner SID')
        subprocess.run(['icacls',str(TOKEN_PATH),'/inheritance:r','/grant:r',
                        '*'+sid+':(F)','*S-1-5-18:(F)'],check=True,capture_output=True)
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*_): raise ValueError('API redirect refused')


def http(path, secret, body=None, timeout=5):
    request=urllib.request.Request(API+path,
        data=None if body is None else json.dumps(body).encode('utf-8'),
        headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(request,timeout=timeout) as response:
        raw=response.read(1048577)
        if len(raw)>1048576: raise ValueError('API response exceeds smoke-check budget')
        return json.loads(raw)


def environment(context):
    env=r.environment(r.manifest_for('serve'))
    env.update(HALOGEN_CTX=str(context),HALOGEN_KV_POOL_POSITIONS=str(context),
               HALOGEN_KV_SLOTS='1',HALOGEN_API_PORT='8731',HALOGEN_VERBOSE='1')
    return env


def service_entrypoint(source):
    if hashlib.sha256(source).hexdigest()!=portable.RELEASE['adapted_entrypoint_sha256']:
        raise ValueError('Pinned WSL entrypoint identity changed')
    needle=b'python3 /halogen/tools/serve_api.py'
    if source.count(needle)!=4: raise ValueError('Unexpected upstream API launch sites')
    return source.replace(needle,b'python3 /candidate/auth_api.py')


def source_hashes():
    paths=sorted((ROOT/'scripts').glob('*'))+sorted((ROOT/'patches').glob('*'))
    paths += [ROOT/'profiles/release.json',ROOT/'profiles/sources.json']
    return {str(p.relative_to(ROOT)):portable.digest(p) for p in paths if p.is_file() and p.suffix in ('.py','.ps1','.c','.S','.h','.json')}


def build_manifest(o, attempt, run_id):
    base=r.manifest_for('serve')
    mounts=dict(r.FIXED_MOUNTS)
    for role,item in base['artifacts'].items():
        if item.get('container_path'):
            mounts[item['container_path']]=r.linux_path(item['path'])
    mounts['/candidate/entrypoint-wsl-candidate.sh']=r.linux_path(attempt/'entrypoint-service.sh')
    mounts.update({'/candidate/auth_api.py':r.linux_path(ROOT/'scripts/auth_api.py'),
                   '/candidate/lease_supervisor.py':r.linux_path(ROOT/'scripts/lease_supervisor.py'),
                   '/candidate/startup_cache.py':r.linux_path(ROOT/'scripts/startup_cache.py'),
                   '/candidate/api-token.txt':r.linux_path(TOKEN_PATH),
                   '/service-state':r.linux_path(attempt)})
    return dict(schema=1,version='0.15.0',image=r.IMAGE,run_id=run_id,
        context=o.context_size,slots=1,serve_seconds=o.serve_seconds,startup_timeout=o.startup_timeout,
        mounts=mounts,environment=environment(o.context_size),sources=source_hashes(),
        entrypoint_sha256=portable.digest(attempt/'entrypoint-service.sh'))


def command(m):
    name='halogen-flash-hybrid-service-'+m['run_id']
    args=['create','--name',name,'--restart=no','--device=/dev/dxg','--ipc=host','--shm-size=8g',
        '--cap-add=SYS_PTRACE','--security-opt=seccomp=unconfined','--security-opt=label=disable',
        '--ulimit=memlock=-1:-1','--memory',str(44*r.GIB),'--memory-swap',str(44*r.GIB),
        '-p','127.0.0.1:8731:8731','--log-driver=json-file','--log-opt=max-size=10m','--log-opt=max-file=5',
        '--label=halogen.performance=hybrid','--label=strix-alloy.owner=strix-alloy-wsl2',
        '--label=strix-alloy.run='+name]
    for dest,src in sorted(m['mounts'].items()):
        args+=['--mount',f'type=bind,src={src},dst={dest},readonly']
    for key,value in sorted(m['environment'].items()): args+=['--env',key+'='+value]
    return args+['--entrypoint','python3',r.IMAGE,'/candidate/lease_supervisor.py',
        '--lease','/service-state/lease.json','--run-id',m['run_id'],
        '/bin/bash','/candidate/entrypoint-wsl-candidate.sh','all']


def owned(info,cid,m,running=False):
    name='halogen-flash-hybrid-service-'+m['run_id']
    r.owned(info,cid,name,{},running=False)
    if running:
        sg.IMAGE=r.IMAGE; sg.REVIEWED_IMAGES=frozenset([r.IMAGE]); sg.EXPECTED_MOUNTS=m['mounts']
        sg.validate_target(info,cid)
        actual=info.get('Config',{}).get('Env',[])
        for key,value in m['environment'].items():
            if [s for s in actual if s.startswith(key+'=')]!=[key+'='+value]:
                raise ValueError('Container environment changed: '+key)
        if info['HostConfig'].get('RestartPolicy',{}).get('Name') not in ('no',''):
            raise ValueError('Unexpected restart policy')


def stop_owned(cid,m):
    info=r.inspect(cid); owned(info,cid,m)
    if info['State']['Running']: r.docker('stop','-t','10',cid,timeout=45)
    info=r.inspect(cid); owned(info,cid,m); r.validate_terminal(info['State'])
    return info


def request_stop(o):
    state=read(STATE_PATH); attempt=Path(state['attempt'])
    if attempt.resolve().parent!=(LOCAL/'services').resolve(): raise ValueError('Invalid service state')
    if o.status:
        result=dict(state)
        try: result['controller_live']=fresh(read(attempt/'controller.json'),state['run_id'])
        except (ValueError,OSError): result['controller_live']=False
        result['ready']=state['phase']=='ready' and result['controller_live']
        print(json.dumps(result,indent=2)); return 0
    if state['phase'] in ('stopped','failed'):
        print('Service is already terminal; no process was touched.'); return 0
    atomic(attempt/'stop.json',{'run_id':state['run_id']})
    print('Stop requested. Follow the serving console for cleanup and memory recovery.')
    return 0


def check_admission(frame, context):
    phys,commit=floors(context)
    if frame.get('available_bytes',0)<phys*r.GIB or frame.get('commit_headroom_bytes',0)<commit*r.GIB:
        raise ValueError(f'Context {context} needs {phys} GiB free physical / {commit} GiB commit headroom; '
            f'observed {frame.get("available_bytes",0)/r.GIB:.2f} / {frame.get("commit_headroom_bytes",0)/r.GIB:.2f}')


def admission(host,context,stop,log):
    r.exclusive_host()
    log.info('Checking memory admission: context=%s, required physical/commit GiB=%s',context,floors(context))
    deadline=time.monotonic()+240; safe_since=None; last_note=-20; last_error=None
    while time.monotonic()<deadline:
        if stop.is_set(): raise InterruptedError('Startup cancelled')
        started=time.monotonic(); frame=host.frame()
        r.check_frame(frame,age=time.monotonic()-started)
        try:
            check_admission(frame,context)
            if safe_since is None: safe_since=time.monotonic()
            if time.monotonic()-safe_since>=60: return frame
        except ValueError as exc:
            safe_since=None; last_error=exc
            if time.monotonic()-last_note>=20:
                log.info('Waiting for stable free memory: %s',exc); last_note=time.monotonic()
        time.sleep(1)
    raise ValueError('Memory admission did not stabilize within 240 seconds: '+str(last_error))


def check_runtime_frame(frame, age):
    fields = ('available_bytes', 'commit_headroom_bytes')
    if not 0 <= age <= 2:
        raise ValueError(f'Memory sample too slow/stale: {age:.3f}s (maximum 2s)')
    if any(type(frame.get(key)) is not int or frame[key] < 0 for key in fields):
        raise ValueError('Invalid physical/commit memory telemetry: ' + repr(frame))
    if any(frame[key] < 12*r.GIB for key in fields):
        raise ValueError('Physical/commit memory reserve crossed: '
            f'{frame[fields[0]]/r.GIB:.3f}/{frame[fields[1]]/r.GIB:.3f} GiB; minimum 12/12 GiB')


def startup_exit_error(attempt):
    try: reason = read(attempt/'guard-failure.json').get('error')
    except (OSError, ValueError): reason = None
    return RuntimeError('Engine exited during startup; ' + (
        'guard cause: '+str(reason) if reason else 'inspect engine.log and startup-cache.jsonl'))


def guard(attempt):
    r.configure()
    m=read(attempt/'manifest.json'); cid=read(attempt/'container.json')['id']
    if m['sources']!=source_hashes(): raise ValueError('Service source changed before guard start')
    log=logger(attempt/'host-guard.jsonl',raw=True)
    host=r.load_module('service_host_frames',ROOT/'scripts/host_frames.py')
    checked=0
    sequence=0
    frame=None; sample_age=None
    try:
        owned(r.inspect(cid),cid,m)
        while True:
            if not fresh(read(attempt/'controller.json'),m['run_id']):
                raise RuntimeError('Controller heartbeat is stale')
            began=time.monotonic(); frame=host.frame()
            sample_age=time.monotonic()-began
            log.info(json.dumps({'time':time.time(),'sample_age':sample_age,**frame}))
            check_runtime_frame(frame,sample_age)
            if time.monotonic()-checked>=5:
                info=r.inspect(cid); owned(info,cid,m,running=info['State']['Running']); checked=time.monotonic()
            sequence += 1
            atomic(attempt/'lease.json',lease_record(m['run_id'],sequence))
            if not (attempt/'armed.json').exists(): atomic(attempt/'armed.json',{'id':cid})
            if (attempt/'quiesce-request.json').exists():
                if read(attempt/'quiesce-request.json')!={'schema':1,'container_id':cid}:
                    raise ValueError('Wrong quiescence target')
                if not (attempt/'quiesce-ack.json').exists():
                    atomic(attempt/'quiesce-ack.json',{'schema':1,'container_id':cid})
            if (attempt/'guard-exit-request.json').exists():
                if read(attempt/'guard-exit-request.json')!={'schema':1,'container_id':cid}:
                    raise ValueError('Wrong guard exit target')
                if not (attempt/'quiesce-ack.json').exists(): raise ValueError('Exit before quiescence')
                terminal=r.inspect(cid); owned(terminal,cid,m); r.validate_terminal(terminal['State'])
                atomic(attempt/'guard-exit-ack.json',{'schema':1,'container_id':cid})
                return 0
            time.sleep(1)
    except BaseException as error:
        try:
            atomic(attempt/'guard-failure.json',{'error':str(error),'last_frame':frame,'sample_age':sample_age})
        except OSError as report_error:
            print(f'Guard failure: {error}; could not save diagnostics: {report_error}',
                  file=sys.stderr,flush=True)
        finally:
            # A failed diagnostic write must not skip verified owned shutdown.
            stop_owned(cid,m)
        return 2


def guard_alive(process, attempt):
    try:
        r.guard_alive(process,attempt)
    except RuntimeError as exc:
        try:
            detail=read(Path(attempt)/'guard-failure.json').get('error')
        except (OSError,ValueError,AttributeError):
            detail=None
        if isinstance(detail,str) and detail:
            raise RuntimeError(f'{exc}; guard cause: {detail}') from exc
        raise


def validate_health(h,context):
    if h.get('status')!='ok' or h.get('version')!={'api':'0.15.0','engine':'0.15.0','match':True}:
        raise ValueError('Expected ready, matching Halogen 0.15.0 engine and API')
    for key,expected in [('context',context),('slot_ctx',context),('kv_pool_positions',context),('slots',1)]:
        if h.get(key)!=expected: raise ValueError(f'Server silently changed {key}: {h.get(key)} != {expected}')


def main(argv=None):
    o=options(sys.argv[1:] if argv is None else argv)
    if o.guard: return guard(o.guard)
    if o.stop or o.status: return request_stop(o)
    if o.print_only:
        print(json.dumps(dict(context=o.context_size,slots=1,serve_seconds=o.serve_seconds,
            continuous=o.serve_seconds==0,startup_timeout=o.startup_timeout,
            endpoint=API+'/v1',token_file=str(TOKEN_PATH),admission_gib=floors(o.context_size)),indent=2))
        return 0
    return serve(o)


def serve(o):
    r.configure()
    machine=r.MACHINE
    actual=portable.preflight(machine['distro'],machine['user'],machine['models'],machine['dxg'])
    if actual!=machine: raise ValueError('Installed machine configuration drift')
    secret=token()
    run_id=uuid.uuid4().hex
    attempt=LOCAL/'services'/run_id; attempt.mkdir(parents=True)
    log=logger(attempt/'service.log',console=True)
    engine_log=logger(attempt/'engine.log',console=True,raw=True)
    lock=LOCAL/'runner.lock'
    handle=lock.open('x',encoding='utf-8'); handle.write(run_id); handle.flush()
    stop=threading.Event(); heart_stop=threading.Event()
    cid=None; guard_proc=None; follower=None; follower_thread=None; baseline=None
    cache_worker=None; cache_stopped=False
    cleanup=False; recovered=False; ready=False; m=None; error=None; creation_attempted=False
    state=dict(schema=1,run_id=run_id,attempt=str(attempt),phase='starting',
               endpoint=API+'/v1',model=MODEL,context=o.context_size,slots=1,
               serve_seconds=o.serve_seconds,controller_pid=os.getpid(),
               token_file=str(TOKEN_PATH),log_file=str(attempt/'engine.log'),
               controller_log=str(attempt/'service.log'))
    atomic(STATE_PATH,state)
    def sigstop(*_): stop.set()
    old_handler=signal.signal(signal.SIGINT,sigstop)
    def heartbeat():
        while not heart_stop.is_set():
            try: atomic(attempt/'controller.json',{'run_id':run_id,'time':time.time()})
            except BaseException:
                stop.set(); return
            heart_stop.wait(2)
    atomic(attempt/'controller.json',{'run_id':run_id,'time':time.time()})
    heartbeat_thread=threading.Thread(target=heartbeat,daemon=True); heartbeat_thread.start()
    def cancelled():
        if (attempt/'stop.json').exists():
            if read(attempt/'stop.json')!={'run_id':run_id}: raise ValueError('Invalid stop target')
            stop.set()
        return stop.is_set()
    def follow():
        try:
            for line in follower.stdout:
                engine_log.info(line.rstrip().replace(secret,'[REDACTED]'))
        except (OSError,ValueError) as exc:
            log.warning('Engine log stream ended: %s',exc)
    try:
        original=(LOCAL/'entrypoint-wsl.sh').read_bytes()
        portable.check_hash(LOCAL/'entrypoint-wsl.sh',portable.RELEASE['adapted_entrypoint_sha256'])
        (attempt/'entrypoint-service.sh').write_bytes(service_entrypoint(original))
        m=build_manifest(o,attempt,run_id); atomic(attempt/'manifest.json',m)
        host=r.load_module('serving_host',ROOT/'scripts/host_frames.py')
        baseline=admission(host,o.context_size,stop,log)
        r.exclusive_host()
        frame=host.frame(); check_admission(frame,o.context_size)
        atomic(attempt/'admission-create.json',frame)
        log.info('Creating Halogen 0.15.0: context=%s, slots=1; no model download',o.context_size)
        creation_attempted=True
        cid=r.docker(*command(m),timeout=30)
        owned(r.inspect(cid),cid,m); atomic(attempt/'container.json',{'id':cid})
        flags=NO_WINDOW|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        guard_proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__)), '--guard',str(attempt)],
                                    creationflags=flags)
        deadline=time.monotonic()+30
        while not (attempt/'armed.json').exists():
            if guard_proc.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('Independent memory guard did not arm')
            time.sleep(.1)
        # Exact source and fresh-memory checks immediately before model startup.
        if source_hashes()!=m['sources']: raise ValueError('Source changed during admission')
        r.exclusive_host(); baseline=host.frame(); check_admission(baseline,o.context_size)
        atomic(attempt/'admission-start.json',baseline)
        if cancelled(): raise InterruptedError('Startup cancelled')
        r.docker('start',cid)
        cache_worker=StartupMonitor(r.WSL,cid,attempt,run_id,o.startup_timeout,atomic,
            logger(attempt/'startup-cache.jsonl',raw=True))
        follower=subprocess.Popen(r.WSL+['docker','logs','--follow','--timestamps',cid],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
            creationflags=NO_WINDOW)
        follower_thread=threading.Thread(target=follow,daemon=True); follower_thread.start()
        log.info('Loading model; live engine log: %s',attempt/'engine.log')
        deadline=time.monotonic()+o.startup_timeout; last_advice=0; last_note=0
        while time.monotonic()<deadline:
            if cancelled(): raise InterruptedError('Startup cancelled')
            guard_alive(guard_proc,attempt)
            info=r.inspect(cid); owned(info,cid,m,running=info['State']['Running'])
            if not info['State']['Running']: raise startup_exit_error(attempt)
            cache_worker.check()
            try: health=http('/health',secret)
            except (OSError,ValueError): health={}
            if health.get('status')=='ok':
                validate_health(health,o.context_size)
                cache_worker.stop(); cache_stopped=True
                log.info('Startup-cache worker stopped before inference; client cache is retained')
                atomic(attempt/'health.json',health)
                # Negative auth probe: an endpoint is not authenticated merely because valid requests work.
                try: http('/v1/models','incorrect-token')
                except urllib.error.HTTPError as exc:
                    if exc.code!=401: raise
                else: raise RuntimeError('API accepted an invalid token')
                for label,prompt,expected in [('arithmetic','Reply with only the number: 17 + 25','42'),
                    ('german','Antworte mit genau einem Wort: Welche Farbe hat Gras?','grün')]:
                    body={'model':MODEL,'messages':[{'role':'user','content':prompt}],
                          'max_tokens':32,'stream':False,'temperature':0,
                          'drafter':'serial','enable_thinking':False,'reasoning_effort':'none'}
                    response=http('/v1/chat/completions',secret,body,timeout=60)
                    answer=response['choices'][0]['message']['content'].strip().strip('.!').casefold()
                    if answer!=expected: raise ValueError('Incorrect startup answer: '+label)
                    atomic(attempt/(label+'.json'),{'answer':answer,'correct':True})
                r.validate_sample(r.sample(cid,attempt,'ready',9997),cid)
                ready=True; break
            if time.monotonic()-last_note>=20:
                f=host.frame(); log.info('Loading: Windows free %.2f GiB; commit headroom %.2f GiB',
                    f['available_bytes']/r.GIB,f['commit_headroom_bytes']/r.GIB); last_note=time.monotonic()
            time.sleep(1)
        if not ready: raise TimeoutError('Startup timeout; model was not ready')
        state.update(phase='ready',ready_at=time.time(),container_id=cid)
        atomic(STATE_PATH,state); atomic(attempt/'ready.json',state)
        log.info('READY: %s/v1 | model=%s | context=%s | serving=%s',API,MODEL,o.context_size,
                 'until stopped' if not o.serve_seconds else str(o.serve_seconds)+' seconds')
        # The secret is printed to the interactive terminal, NEVER to logger or manifest.
        print('API TOKEN: '+secret,flush=True)
        print('Authorization: Bearer <API TOKEN> | Ctrl+C or Start.ps1 -Stop to stop.',flush=True)
        end=None if o.serve_seconds==0 else time.monotonic()+o.serve_seconds
        last_note=0
        while not cancelled() and (end is None or time.monotonic()<end):
            guard_alive(guard_proc,attempt)
            info=r.inspect(cid); owned(info,cid,m,running=True)
            if time.monotonic()-last_note>=30:
                f=host.frame(); log.info('Serving: free %.2f GiB; commit headroom %.2f GiB; context=%s',
                    f['available_bytes']/r.GIB,f['commit_headroom_bytes']/r.GIB,o.context_size)
                last_note=time.monotonic()
            time.sleep(1)
    except InterruptedError:
        log.info('Startup cancelled by operator')
    except BaseException as exc:
        error=str(exc).replace(secret,'[REDACTED]'); log.error('%s',error)
    finally:
        log.info('Stopping owned server and checking memory recovery')
        if cache_worker and not cache_stopped:
            try: cache_worker.stop(); cache_stopped=True
            except Exception as exc: log.warning('Startup-cache stop: %s',exc)
        try:
            if cid is None and creation_attempted:
                info=r.inspect('halogen-flash-hybrid-service-'+run_id)
                owned(info,info['Id'],m); cid=info['Id']
            if cid:
                if guard_proc and guard_proc.poll() is None:
                    try: r.request_quiescence(attempt,cid,guard_proc)
                    except BaseException as exc:
                        error=(error+'; ' if error else '')+'quiescence: '+str(exc)
                terminal=stop_owned(cid,m); atomic(attempt/'terminal.json',terminal); cleanup=True
            else:
                cleanup=True
            if baseline is not None:
                frames=[]; until=time.monotonic()+180
                while time.monotonic()<until:
                    frame=host.frame(); r.check_frame(frame); frames.append(frame)
                    if r.recovered(frames,baseline['available_bytes']): recovered=True; break
                    time.sleep(1)
                atomic(attempt/'recovery.json',{'passed':recovered,'frames':frames})
            else: recovered=True
            if guard_proc:
                if guard_proc.poll() is None and cleanup and recovered:
                    r.finish_guard(attempt,cid,guard_proc)
                elif guard_proc.poll()!=0:
                    raise RuntimeError('Memory guard stopped abnormally; evidence retained')
            if not cleanup or not recovered: raise RuntimeError('Cleanup/recovery incomplete; lock retained')
        except BaseException as exc:
            error=(error+'; ' if error else '')+'cleanup: '+str(exc)
            log.error('%s',error)
        finally:
            if guard_proc and cleanup and guard_proc.poll() is None:
                guard_proc.terminate()
                try: guard_proc.wait(timeout=10)
                except subprocess.TimeoutExpired: guard_proc.kill(); guard_proc.wait(timeout=5)
            if cache_worker:
                try: cache_worker.close()
                except Exception as exc: log.warning('Startup-cache reader cleanup: %s',exc)
            heart_stop.set(); heartbeat_thread.join(timeout=5)
            if follower:
                if follower.poll() is None: follower.terminate()
                try: follower.wait(timeout=10)
                except subprocess.TimeoutExpired: follower.kill(); follower.wait(timeout=5)
                if follower_thread: follower_thread.join(timeout=5)
                follower.stdout.close()
            handle.close()
            # A failure does not qualify inference. Proven recovery does permit a deliberate retry.
            if cleanup and recovered and (guard_proc is None or not (attempt/'guard-failure.json').exists()):
                if lock.read_text(encoding='utf-8')==run_id: lock.unlink()
            outcome=dict(ready=ready,cleanup=cleanup,recovery=recovered,error=error,
                         stopped_at=time.time(),context=o.context_size)
            atomic(attempt/'outcome.json',outcome)
            state.update(phase='failed' if error else 'stopped',outcome=outcome)
            atomic(STATE_PATH,state)
            signal.signal(signal.SIGINT,old_handler)
        log.info('STOPPED: cleanup=%s recovery=%s; evidence=%s',cleanup,recovered,attempt)
    return 2 if error else 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr); raise SystemExit(2)
