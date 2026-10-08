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
import kernel_controls as kc
import speculation_policy as sp
from startup_monitor import StartupMonitor
import runner as r
import startup_guard as sg
from lease_supervisor import fresh, lease_record

DEFAULT_CONTEXT = 262144
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
API = 'http://127.0.0.1:8731'
MODEL = 'halogen-qwen3.8-flash-next'
TOKEN_PATH = LOCAL / 'api-token.txt'
STATE_PATH = LOCAL / 'current-service.json'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
ADMISSION_KEEPALIVE = '''import os, select, sys, time
deadline = time.monotonic() + float(sys.argv[1])
print(sys.argv[2], flush=True)
while time.monotonic() < deadline:
    remaining = max(0, deadline - time.monotonic())
    if select.select([sys.stdin], [], [], min(1, remaining))[0]:
        if not os.read(sys.stdin.fileno(), 4096):
            raise SystemExit(0)
raise SystemExit(124)
'''


class AdmissionKeepalive:
    """Own one bounded foreground guest until the engine takes over WSL life."""
    def __init__(self, wsl, run_id, seconds):
        self.ready, self.line, self.closed = threading.Event(), None, False
        self.run_id = run_id
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.process = subprocess.Popen(wsl + ['python3', '-u', '-c', ADMISSION_KEEPALIVE,
            str(seconds), run_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
            creationflags=NO_WINDOW)

    def arm(self):
        # The service owns this object before any handshake can fail.
        self.reader.start()
        if not self.ready.wait(15) or self.line != self.run_id+'\n':
            raise RuntimeError('WSL admission keepalive did not arm')
        self.check()

    def _read(self):
        try: self.line = self.process.stdout.readline(128)
        except (OSError, ValueError): pass
        finally: self.ready.set()

    def check(self):
        code = self.process.poll()
        if code is not None:
            raise RuntimeError(f'WSL admission keepalive stopped (exit={code})')

    def close(self, require_clean=False):
        if self.closed: return
        forced = False
        try: self.process.stdin.close()
        except (OSError, ValueError): pass
        try: code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forced = True
            self.process.terminate()
            try: code = self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); code = self.process.wait(timeout=5)
        if self.reader.ident is not None: self.reader.join(timeout=3)
        if self.reader.is_alive(): raise RuntimeError('WSL admission keepalive reader did not stop')
        self.process.stdout.close()
        self.closed = True
        if require_clean and (forced or code != 0):
            raise RuntimeError(f'WSL admission keepalive did not release cleanly (exit={code})')


def options(argv=None):
    p = argparse.ArgumentParser(description='Halogen service: authenticated, logged, continuous by default')
    p.add_argument('--checkpoint',choices=['w4b','v2'],default='v2')
    p.add_argument('--prompt-cache',choices=['Off','Exact','Flexible'],default='Off')
    p.add_argument('--draft-tokens',type=int,choices=(1,2,3),default=None)
    p.add_argument('--prefill-chunk',type=int,choices=(2048,4096,8192,16384,32768),default=None)
    p.add_argument('--max-prefill-tokens',type=int,choices=(2048,4096,8192,16384,32768),default=None)
    p.add_argument('--prefill-keep-trunk',action='store_true')
    p.add_argument('--admit-ticks',type=int,default=None)
    p.add_argument('--kernel-controls-json',type=kc.parse,default=None)
    p.add_argument('--matmul-tuning-json',default=None)
    p.add_argument('--speculation-policy-json',type=sp.parse,default=None)
    p.add_argument('--lookup-receipt',default=None)
    p.add_argument('--lookup-receipt-sha256',default=None)
    p.add_argument('--private-hsa-receipt',default=None)
    p.add_argument('--private-hsa-receipt-sha256',default=None)
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
    hsa_path = getattr(o, 'private_hsa_receipt', None)
    hsa_sha = getattr(o, 'private_hsa_receipt_sha256', None)
    if (hsa_path is None) != (hsa_sha is None):
        raise ValueError('Private HSA receipt and independent receipt SHA-256 must be supplied together')
    if hsa_path is not None:
        raise ValueError('Private HSA receipts are pinned to 0.16.2 and are not qualified for 0.17.2; use the stock runtime')
    if getattr(o, 'qualified_hsa', None) is not None:
        raise ValueError('Private HSA overrides are not qualified for 0.17.2; use the stock runtime')
    lookup_path = getattr(o, 'lookup_receipt', None)
    lookup_sha = getattr(o, 'lookup_receipt_sha256', None)
    if (lookup_path is None) != (lookup_sha is None):
        raise ValueError('Lookup receipt and independent receipt SHA-256 must be supplied together')
    if lookup_path is not None or getattr(o, 'qualified_lookup', None) is not None:
        raise ValueError('Private lookup receipts are not rebound to 0.17.2; use the stock lookup source')
    kc.validate(getattr(o, 'kernel_controls_json', None) or {})
    if getattr(o, 'speculation_policy_json', None) is not None:
        sp.validate(o.speculation_policy_json)
    if getattr(o, 'matmul_tuning_json', None) is not None:
        raise ValueError('Private matmul tuning configurations are not rebound to 0.17.2; use the stock image tuning')
    if getattr(o, 'qualified_matmul_tuning', None) is not None:
        raise ValueError('Private matmul tuning receipts are not rebound to 0.17.2; use the stock image tuning')
    validate_prefill_limits(o.context_size,getattr(o,'prefill_chunk',None),getattr(o,'max_prefill_tokens',None))
    if getattr(o,'prefill_keep_trunk',False) and getattr(o,'checkpoint','v2') != 'v2':
        raise ValueError('PREFILL_KEEP_TRUNK is supported only for the v2 checkpoint')
    if getattr(o,'admit_ticks',None) is not None and (type(o.admit_ticks) is not int or not 1 <= o.admit_ticks <= 1024):
        raise ValueError('AdmitTicks must be 1..1024')
    if type(o.context_size) is not int or not 4096 <= o.context_size <= 262144:
        raise ValueError('ContextSize must be 4096..262144 positions (prompt + output), one slot')
    if type(o.serve_seconds) is not int or not 0 <= o.serve_seconds <= 604800:
        raise ValueError('ServeSeconds must be 0 (continuous) or 1..604800')
    if type(o.startup_timeout) is not int or not 120 <= o.startup_timeout <= 3600:
        raise ValueError('StartupTimeoutSeconds must be 120..3600; it is not a serving timeout')


def floors(context, checkpoint='v2'):
    from memory_budget import admission_floors
    return admission_floors(context,checkpoint)


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


def read(path):
    from state_io import read_json
    return read_json(path)


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


def native_logs(cid):
    # Docker preserves the engine's stderr stream, which contains tuning notices.
    return subprocess.run(r.WSL+['docker','logs',cid], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',check=True,
        timeout=15,creationflags=NO_WINDOW).stdout


def verify_checkpoint(machine, checkpoint, lookup_override=None):
    if lookup_override is not None:
        raise ValueError('Private lookup receipts are not rebound to 0.17.2')
    if checkpoint=='w4b': return
    if checkpoint!='v2': raise ValueError('Unknown checkpoint')
    from checkpoint_integrity import verify, verify_ngram
    verify(machine,LOCAL)
    verify_ngram(machine,LOCAL)
    portable.check_hash(LOCAL/'libhalogen0172-v2-preflight.so',portable.RELEASE['v2_bridge_sha256'])


def validate_prefill_limits(context, prefill_chunk, max_prefill_tokens):
    allowed=(2048,4096,8192,16384,32768)
    if prefill_chunk is not None and (type(prefill_chunk) is not int or prefill_chunk not in allowed or prefill_chunk>context):
        raise ValueError('Invalid prefill chunk for context')
    if max_prefill_tokens is not None:
        if type(max_prefill_tokens) is not int or max_prefill_tokens not in allowed or max_prefill_tokens>context:
            raise ValueError('Invalid max prefill tokens for context')
        if prefill_chunk is None or prefill_chunk>max_prefill_tokens:
            raise ValueError('Max prefill tokens requires an explicit chunk no larger than the token arena')


def environment(context, checkpoint="v2", prompt_cache="Off", draft_tokens=None, prefill_chunk=None, prefill_keep_trunk=False, admit_ticks=None, kernel_controls=None, speculation_policy=None, max_prefill_tokens=None):
    if draft_tokens is not None and (type(draft_tokens) is not int or draft_tokens not in (1,2,3)):
        raise ValueError("Draft depth must be 1, 2 or 3")
    validate_prefill_limits(context,prefill_chunk,max_prefill_tokens)
    if prefill_keep_trunk and checkpoint != 'v2': raise ValueError('PREFILL_KEEP_TRUNK requires v2')
    if admit_ticks is not None and (type(admit_ticks) is not int or not 1 <= admit_ticks <= 1024): raise ValueError('Invalid admit ticks')
    env=r.environment(r.manifest_for('serve'))
    # The bounded 4K diagnostics retain their old arena; continuous serving
    # starts with this release's compute defaults unless explicitly tuned.
    for key in ('HALOGEN_PREFILL_CHUNK', 'HALOGEN_MAX_TOK',
                'HALOGEN_FLASH_ROUTE_GEMM', 'HALOGEN_TOPK_REPLAY'):
        env.pop(key, None)
    env.update(HALOGEN_CTX=str(context),HALOGEN_KV_POOL_POSITIONS=str(context),
               HALOGEN_KV_SLOTS='1',HALOGEN_API_PORT='8731',HALOGEN_VERBOSE='1',HALOGEN_HOST_RESERVE_GIB='18',
               HF_HUB_OFFLINE='1')
    if checkpoint == 'v2':
        env.update(HALOGEN_CHECKPOINT='/models/qwen38-flash-next-v2.hgn',
            HALOGEN_CK_OVERLAY='',
            HALOGEN_NGRAM_TABLE=('/ngram-w4b.hgn' if (r.MACHINE or {}).get('ngram_source')
                                 else '/models/qwen38-flash-next-w4b.hgn'),
            HALOGEN_CHECKPOINT_VARIANT='v2', HALOGEN_PREFLIGHT_PROFILE='flash0172-v2-device64-chunk64-v1',
            HALOGEN_HYBRID_PROFILE='vgm64-0172-v2-device64-v1', HALOGEN_HYBRID_COPY_BYTES='68719476736',
            LD_PRELOAD='/candidate/libhalogen0172-v2-preflight.so:/candidate/hip-register-private-rw.so')
    elif checkpoint != 'w4b':
        raise ValueError('Unknown checkpoint; no silent fallback')
    if prompt_cache not in ('Off','Exact','Flexible'): raise ValueError('Unknown cache policy')
    if draft_tokens is not None: env['HALOGEN_MTP_DEPTH']=str(draft_tokens)
    if prefill_chunk is not None:
        env['HALOGEN_PREFILL_CHUNK']=str(prefill_chunk)
        # Existing chunk profiles keep the stock arena unless explicitly bounded.
        env['HALOGEN_MAX_TOK']=str(32768 if max_prefill_tokens is None else max_prefill_tokens)
    if prefill_keep_trunk: env['HALOGEN_PREFILL_KEEP_TRUNK']='1'
    if admit_ticks is not None: env['HALOGEN_ADMIT_TICKS']=str(admit_ticks)
    env['HALOGEN_PROMPT_CACHE']={'Off':'0','Exact':'1','Flexible':'2'}[prompt_cache]
    env.update(kc.environment(kernel_controls or {}))
    env.update(sp.environment(speculation_policy))
    return env


def service_entrypoint(source):
    if hashlib.sha256(source).hexdigest()!=portable.RELEASE['adapted_entrypoint_sha256']:
        raise ValueError('Pinned WSL entrypoint identity changed')
    needle=b'/halogen/tools/serve_api.py'
    if source.count(needle)!=5: raise ValueError('Unexpected upstream API launch sites')
    return source.replace(needle,b'/candidate/auth_api.py')


def source_hashes():
    paths=sorted((ROOT/'scripts').glob('*'))+sorted((ROOT/'patches').glob('*'))
    paths += [ROOT/'profiles/release.json',ROOT/'profiles/sources.json']
    return {str(p.relative_to(ROOT)):portable.digest(p) for p in paths if p.is_file() and p.suffix in ('.py','.ps1','.c','.S','.h','.json')}


def build_manifest(o, attempt, run_id):
    validate_options(o)
    checkpoint=getattr(o,'checkpoint','v2')
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
    if checkpoint=='v2':
        mounts['/candidate/libhalogen0172-v2-preflight.so']=r.linux_path(LOCAL/'libhalogen0172-v2-preflight.so')
    result=dict(schema=1,version='0.17.2',image=r.IMAGE,run_id=run_id,checkpoint=checkpoint,
        context=o.context_size,slots=1,serve_seconds=o.serve_seconds,startup_timeout=o.startup_timeout,
        mounts=mounts,environment=environment(o.context_size,checkpoint,getattr(o,'prompt_cache','Off'),getattr(o,'draft_tokens',None),getattr(o,'prefill_chunk',None),getattr(o,'prefill_keep_trunk',False),getattr(o,'admit_ticks',None),getattr(o,'kernel_controls_json',None),getattr(o,'speculation_policy_json',None),max_prefill_tokens=getattr(o,'max_prefill_tokens',None)),sources=source_hashes(),
        entrypoint_sha256=portable.digest(attempt/'entrypoint-service.sh'))
    if getattr(o, 'speculation_policy_json', None) is not None:
        result['speculation_policy'] = sp.validate(o.speculation_policy_json)
    return result


def reject_unqualified_manifest_overrides(m):
    for key in ('private_hsa', 'lookup_tuning', 'matmul_tuning'):
        if m.get(key) is not None:
            raise ValueError('Private runtime override is not rebound to 0.17.2: '+key)


def command(m):
    reject_unqualified_manifest_overrides(m)
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


def check_admission(frame, context, checkpoint='v2'):
    phys,commit=floors(context,checkpoint)
    if frame.get('available_bytes',0)<phys*r.GIB or frame.get('commit_headroom_bytes',0)<commit*r.GIB:
        raise ValueError(f'Context {context} needs {phys} GiB free physical / {commit} GiB commit headroom; '
            f'observed {frame.get("available_bytes",0)/r.GIB:.2f} / {frame.get("commit_headroom_bytes",0)/r.GIB:.2f}')


def admission(host,context,stop,log,checkpoint='v2',keepalive=None):
    r.exclusive_host()
    log.info('Checking memory admission: context=%s, required physical/commit GiB=%s',context,floors(context,checkpoint))
    deadline=time.monotonic()+240; safe_since=None; last_note=-20; last_error=None
    while time.monotonic()<deadline:
        if stop.is_set(): raise InterruptedError('Startup cancelled')
        if keepalive is not None: keepalive.check()
        started=time.monotonic(); frame=host.frame()
        r.check_frame(frame,age=time.monotonic()-started)
        if keepalive is not None: keepalive.check()
        try:
            check_admission(frame,context,checkpoint)
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
    if any(frame[key] < 18*r.GIB for key in fields):
        raise ValueError('Physical/commit memory reserve crossed: '
            f'{frame[fields[0]]/r.GIB:.3f}/{frame[fields[1]]/r.GIB:.3f} GiB; minimum 18/18 GiB')


def startup_exit_error(attempt):
    try: reason = read(attempt/'guard-failure.json').get('error')
    except (OSError, ValueError): reason = None
    return RuntimeError('Engine exited during startup; ' + (
        'guard cause: '+str(reason) if reason else 'inspect engine.log and startup-cache.jsonl'))


def guard(attempt):
    r.configure()
    m=read(attempt/'manifest.json'); cid=read(attempt/'container.json')['id']
    reject_unqualified_manifest_overrides(m)
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


def guard_exit_failed(code):
    """None means still running, not an abnormal process exit."""
    return code is not None and code != 0


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
    if h.get('status')!='ok' or h.get('version')!={'api':'0.17.2','engine':'0.17.2','match':True}:
        raise ValueError('Expected ready, matching Halogen 0.17.2 engine and API')
    for key,expected in [('context',context),('slot_ctx',context),('kv_pool_positions',context),('slots',1)]:
        if h.get(key)!=expected: raise ValueError(f'Server silently changed {key}: {h.get(key)} != {expected}')


def main(argv=None):
    o=options(sys.argv[1:] if argv is None else argv)
    if o.guard:
        try: return guard(o.guard)
        except Exception as exc:
            atomic(o.guard/'guard-failure.json',{'error':str(exc),'stage':'bootstrap','type':type(exc).__name__})
            print('Guard bootstrap failed: '+str(exc),file=sys.stderr,flush=True)
            return 2
    if o.stop or o.status: return request_stop(o)
    if o.print_only:
        print(json.dumps(dict(context=o.context_size,slots=1,serve_seconds=o.serve_seconds,
            continuous=o.serve_seconds==0,startup_timeout=o.startup_timeout,checkpoint=getattr(o,'checkpoint','v2'),
            endpoint=API+'/v1',token_file=str(TOKEN_PATH),admission_gib=floors(o.context_size,getattr(o,'checkpoint','v2'))),indent=2))
        return 0
    return serve(o)


def serve(o):
    validate_options(o)
    r.configure()
    machine=r.MACHINE
    actual=portable.preflight(machine['distro'],machine['user'],machine['models'],machine['dxg'],checkpoint=getattr(o,'checkpoint','v2'),ngram_source=machine.get('ngram_source'))
    if actual!=machine: raise ValueError('Installed machine configuration drift')
    verify_checkpoint(machine,getattr(o,'checkpoint','v2'))
    secret=token()
    run_id=uuid.uuid4().hex
    attempt=LOCAL/'services'/run_id; attempt.mkdir(parents=True)
    log=logger(attempt/'service.log',console=True)
    engine_log=logger(attempt/'engine.log',console=True,raw=True)
    lock=LOCAL/'runner.lock'
    handle=lock.open('x',encoding='utf-8'); handle.write(run_id); handle.flush()
    stop=threading.Event(); heart_stop=threading.Event()
    cid=None; guard_proc=None; follower=None; follower_thread=None; baseline=None
    keepalive=None; keepalive_clean=True
    cache_worker=None; cache_stopped=False
    cleanup=False; recovered=False; ready=False; m=None; error=None; creation_attempted=False
    state=dict(schema=1,run_id=run_id,attempt=str(attempt),phase='starting',
               endpoint=API+'/v1',model=MODEL,context=o.context_size,slots=1,checkpoint=getattr(o,'checkpoint','v2'),
               prompt_cache=getattr(o,'prompt_cache','Off'),
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
        # Admission, command/guard setup, and smoke checks surround the model timeout.
        keepalive=AdmissionKeepalive(r.WSL,run_id,o.startup_timeout+600)
        keepalive.arm()
        baseline=admission(host,o.context_size,stop,log,getattr(o,'checkpoint','v2'),keepalive=keepalive)
        keepalive.check()
        r.exclusive_host()
        frame=host.frame(); check_admission(frame,o.context_size,getattr(o,'checkpoint','v2'))
        atomic(attempt/'admission-create.json',frame)
        log.info('Creating Halogen 0.17.2: context=%s, slots=1; no model download',o.context_size)
        keepalive.check()
        creation_attempted=True
        cid=r.docker(*command(m),timeout=30)
        owned(r.inspect(cid),cid,m); atomic(attempt/'container.json',{'id':cid})
        flags=NO_WINDOW|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        with (attempt/'guard-process.log').open('a',encoding='utf-8') as guard_output:
            guard_proc=subprocess.Popen([sys.executable,'-B',str(Path(__file__)), '--guard',str(attempt)],
                creationflags=flags,stdout=guard_output,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+30
        while not (attempt/'armed.json').exists():
            if guard_proc.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError(f'Independent memory guard did not arm (exit={guard_proc.poll()}); see guard-process.log and guard-failure.json')
            time.sleep(.1)
        # Exact source and fresh-memory checks immediately before model startup.
        if source_hashes()!=m['sources']: raise ValueError('Source changed during admission')
        keepalive.check()
        r.exclusive_host(); baseline=host.frame(); check_admission(baseline,o.context_size,getattr(o,"checkpoint","v2"))
        atomic(attempt/'admission-start.json',baseline)
        if cancelled(): raise InterruptedError('Startup cancelled')
        keepalive.check()
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
            keepalive.check()
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
                keepalive.check()
                for label,prompt,expected in [('arithmetic','Reply with only the number: 17 + 25','42'),
                    ('german','Antworte mit genau einem Wort: Welche Farbe hat Gras?','grün')]:
                    body={'model':MODEL,'messages':[{'role':'user','content':prompt}],
                          'max_tokens':32,'stream':False,'temperature':0,
                          'drafter':'serial','enable_thinking':False,'reasoning_effort':'none'}
                    response=http('/v1/chat/completions',secret,body,timeout=60)
                    keepalive.check()
                    answer=response['choices'][0]['message']['content'].strip().strip('.!').casefold()
                    if answer!=expected: raise ValueError('Incorrect startup answer: '+label)
                    atomic(attempt/(label+'.json'),{'answer':answer,'correct':True})
                r.validate_sample(r.sample(cid,attempt,'ready',9997),cid)
                keepalive.check()
                keepalive.close(require_clean=True); keepalive=None
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
        if os.environ.get('ALLOY_MANAGED')!='1':
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
        state['phase']='stopping'
        try: atomic(STATE_PATH,state)
        except OSError as exc: log.warning('Stopping-state write failed; continuing owned cleanup: %s',exc)
        log.info('Stopping owned server and checking memory recovery')
        if keepalive:
            try: keepalive.close()
            except BaseException as exc:
                keepalive_clean=False
                error=(error+'; ' if error else '')+'keepalive cleanup: '+str(exc)
                log.error('%s',error)
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
            cleanup=cleanup and keepalive_clean
            if baseline is not None:
                frames=[]; until=time.monotonic()+180
                while time.monotonic()<until:
                    frame=host.frame(); r.check_frame(frame); frames.append(frame)
                    if r.recovered(frames,baseline['available_bytes']): recovered=True; break
                    time.sleep(1)
                atomic(attempt/'recovery.json',{'passed':recovered,'frames':frames,
                    'baseline_available_bytes':baseline['available_bytes'],
                    'required_available_bytes':max(24*r.GIB,baseline['available_bytes']-2*r.GIB)})
                if not recovered:
                    log.error('Memory recovery below original baseline threshold; required %.3f GiB, last %.3f GiB',
                        max(24*r.GIB,baseline['available_bytes']-2*r.GIB)/r.GIB,
                        frames[-1]['available_bytes']/r.GIB if frames else -1)
            else: recovered=True
            if guard_proc:
                if guard_proc.poll() is None and cleanup and recovered:
                    r.finish_guard(attempt,cid,guard_proc)
                elif guard_exit_failed(guard_proc.poll()):
                    raise RuntimeError('Memory guard stopped abnormally; evidence retained')
            if not cleanup or not recovered: raise RuntimeError('Cleanup/recovery incomplete; lock retained')
        except BaseException as exc:
            error=(error+'; ' if error else '')+'cleanup: '+str(exc)
            log.error('%s',error)
        finally:
            if keepalive and not keepalive.closed:
                try: keepalive.close()
                except BaseException as exc: log.warning('WSL admission keepalive cleanup: %s',exc)
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
