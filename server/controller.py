"""Foreground Windows lifecycle owner for the selected engine and API gateway."""
import argparse
import asyncio
import contextlib
import ctypes
import hashlib
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from gateway import load_config,serve
from owned_child import JobChild

ROOT=Path(__file__).resolve().parent
LOCAL=ROOT/'.local'
LOG=logging.getLogger('alloy.controller')


def read(path):
    deadline=time.monotonic()+1
    while True:
        try: return json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except PermissionError:
            if time.monotonic()>=deadline: raise
            time.sleep(.025)

def atomic(path, value):
    path=Path(path); temporary=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    temporary.write_text(json.dumps(value,indent=2),encoding='utf-8')
    deadline=time.monotonic()+2
    try:
        while True:
            try: temporary.replace(path); return
            except PermissionError:
                if time.monotonic()>=deadline: raise
                time.sleep(.025)
    finally:
        temporary.unlink(missing_ok=True)

@contextlib.contextmanager
def lease(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if f.tell()==0: f.write(b'0'); f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            try: yield
            finally: f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try: yield
            finally: fcntl.flock(f,fcntl.LOCK_UN)

class MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
        (name,ctypes.c_ulonglong) for name in ('total','available','pagefile_total',
        'pagefile_available','virtual_total','virtual_available','extended')]


def memory_reserve_gib(configuration):
    value=configuration.get("minimum_reserve_gib",12)
    if type(value) not in (int,float) or not math.isfinite(value) or not 12<=value<=128:
        raise ValueError("Memory reserve must be finite, 12..128 GiB; protection cannot be relaxed")
    return float(value)


def available_gib():
    if os.name!='nt': return None
    value=MemoryStatus(); value.length=ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise OSError('Windows physical-memory telemetry unavailable')
    return value.available/(1024**3)


def halogen_draft_arguments(engine):
    args=[]
    for key,flag,allowed in (("draft_tokens","-DraftTokens",(1,2,3)),
                             ("prefill_chunk","-PrefillChunk",(2048,4096,8192,16384,32768)),
                             ("max_prefill_tokens","-MaxPrefillTokens",(2048,4096,8192,16384,32768)),
                             ("admit_ticks","-AdmitTicks",tuple(range(1,1025)))):
        if key not in engine: continue
        value=engine[key]
        if type(value) is not int or value not in allowed:
            raise ValueError("Invalid Halogen option: "+key)
        if key in ("prefill_chunk","max_prefill_tokens") and "context" in engine and value>engine["context"]:
            raise ValueError("Halogen prefill limit exceeds context: "+key)
        args += [flag,str(value)]
    if 'max_prefill_tokens' in engine:
        if 'prefill_chunk' not in engine or engine['prefill_chunk']>engine['max_prefill_tokens']:
            raise ValueError('Max prefill tokens requires an explicit chunk no larger than the token arena')
    if 'prefill_keep_trunk' in engine:
        if engine['prefill_keep_trunk'] is not True: raise ValueError('Invalid Halogen option: prefill_keep_trunk')
        if engine.get('checkpoint')!='v2': raise ValueError('Prefill keep trunk requires the v2 checkpoint')
        args += ['-PrefillKeepTrunk']
    return args


def validate_halogen_launcher_controls(engine, repo):
    extended_chunk=engine.get('prefill_chunk') in (16384,32768)
    if not (extended_chunk or 'max_prefill_tokens' in engine or 'prefill_keep_trunk' in engine or 'admit_ticks' in engine):
        return
    if not isinstance(engine.get('directory'),str):
        raise ValueError('Halogen controls require a declared backend launcher')
    directory=(repo/engine['directory']).resolve()
    launcher=directory/'Start.ps1'
    if not directory.is_relative_to((repo/'backends').resolve()) or not launcher.is_file():
        raise ValueError('Halogen backend launcher is unavailable')
    # Inspect declarations without executing the launcher. Legacy packages do not
    # accept these newer controls, even though their basic managed path is valid.
    script=launcher.read_text(encoding='utf-8-sig')
    match=re.search(r'\bparam\s*\((.*?)^\)',script,re.S|re.M|re.I)
    parameters=match.group(1) if match else ''
    if extended_chunk:
        match=re.search(r'\[ValidateSet\(([^)]*)\)\]\s*\[int\]\s*\$PrefillChunk\b',parameters,re.I)
        values={value.strip() for value in match.group(1).split(',')} if match else set()
        if str(engine['prefill_chunk']) not in values:
            raise ValueError('Halogen launcher does not support the selected prefill chunk')
    for key,kind,name in (('max_prefill_tokens','int','MaxPrefillTokens'),
                          ('prefill_keep_trunk','switch','PrefillKeepTrunk'),
                          ('admit_ticks','int','AdmitTicks')):
        if key in engine and not re.search(r'\['+kind+r'\]\s*\$'+name+r'\b',parameters,re.I):
            raise ValueError('Halogen launcher does not support '+key)


def halogen_kernel_module(directory):
    source=directory/'scripts/kernel_controls.py'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Selected backend has no managed kernel-controls support')
    spec=importlib.util.spec_from_file_location('alloy_halogen_kernel_controls',source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def halogen_kernel_arguments(engine, directory):
    if 'kernel_controls' not in engine: return []
    controls=halogen_kernel_module(directory).validate(engine['kernel_controls'])
    return ['-KernelControlsJson',json.dumps(controls,sort_keys=True,separators=(',',':'))]


def halogen_speculation_module(directory):
    supported = Path(__file__).resolve().parents[1] / 'backends/halogen-wsl2-0.16.2'
    if directory.resolve() != supported.resolve():
        raise ValueError('Speculation policy requires the pinned Halogen 0.16.2 backend')
    source = directory / 'scripts/speculation_policy.py'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Selected backend has no managed speculation-policy support')
    if not re.search(r'\[string\]\s*\$SpeculationPolicyJson\b',
                     (directory / 'Start.ps1').read_text(encoding='utf-8-sig'), re.I):
        raise ValueError('Selected launcher has no managed speculation-policy support')
    spec = importlib.util.spec_from_file_location('alloy_halogen_speculation_policy', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def halogen_speculation_arguments(engine, directory):
    if 'speculation_policy' not in engine:
        return []
    policy = halogen_speculation_module(directory).validate(engine['speculation_policy'])
    return ['-SpeculationPolicyJson', json.dumps(policy, sort_keys=True, separators=(',', ':'))]


def halogen_matmul_arguments(engine, directory):
    if 'matmul_tuning' not in engine: return []
    source=directory/'scripts/matmul_tuning.py'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Selected backend has no managed matmul-plan support')
    if not re.search(r'\[string\]\s*\$MatmulTuningJson\b', (directory/'Start.ps1').read_text(encoding='utf-8-sig'), re.I):
        raise ValueError('Selected launcher has no managed matmul-plan support')
    if engine.get('checkpoint')!='v2':
        raise ValueError('Matmul tuning experiment requires the pinned v2 checkpoint')
    spec=importlib.util.spec_from_file_location('alloy_halogen_matmul_tuning',source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config=module.validate(engine['matmul_tuning'])
    return ['-MatmulTuningJson',json.dumps(config,sort_keys=True,separators=(',',':'))]


def halogen_lookup_arguments(engine, directory):
    if 'lookup_tuning' not in engine: return []
    supported = Path(__file__).resolve().parents[1] / 'backends/halogen-wsl2-0.16.2'
    if directory.resolve() != supported.resolve() or engine.get('checkpoint') != 'v2':
        raise ValueError('Lookup source experiment requires Halogen 0.16.2 v2')
    source = directory / 'scripts/lookup_source.py'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Selected backend has no managed lookup-source support')
    launcher = (directory / 'Start.ps1').read_text(encoding='utf-8-sig')
    for name in ('LookupReceipt', 'LookupReceiptSha256'):
        if not re.search(r'\[string\]\s*\$' + name + r'\b', launcher, re.I):
            raise ValueError('Selected launcher has no managed lookup-source support')
    spec = importlib.util.spec_from_file_location('alloy_halogen_lookup_source', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.validate_configuration(engine['lookup_tuning'])
    return ['-LookupReceipt', value['receipt'], '-LookupReceiptSha256', value['receipt_sha256']]


def halogen_private_hsa_arguments(engine, directory):
    if 'private_hsa' not in engine: return []
    supported = Path(__file__).resolve().parents[1] / 'backends/halogen-wsl2-0.16.2'
    if directory.resolve() != supported.resolve():
        raise ValueError('Private HSA experiment requires the pinned Halogen 0.16.2 backend')
    if any(key in engine for key in ('kernel_controls', 'matmul_tuning', 'lookup_tuning',
                                   'prefill_chunk', 'max_prefill_tokens', 'prefill_keep_trunk', 'admit_ticks')):
        raise ValueError('Private HSA experiment requires the unchanged Stock8K service controls')
    source = directory / 'scripts/private_hsa.py'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Selected backend has no managed private-HSA support')
    launcher = (directory / 'Start.ps1').read_text(encoding='utf-8-sig')
    for name in ('PrivateHsaReceipt', 'PrivateHsaReceiptSha256'):
        if not re.search(r'\[string\]\s*\$' + name + r'\b', launcher, re.I):
            raise ValueError('Selected launcher has no managed private-HSA support')
    spec = importlib.util.spec_from_file_location('alloy_halogen_private_hsa', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_scope(engine.get('checkpoint'), engine.get('context'), engine.get('prompt_cache', 'Off'),
                          engine.get('draft_tokens'), engine.get('speculation_policy'))
    value = module.qualify(engine['private_hsa'])['configuration']
    return ['-PrivateHsaReceipt', value['receipt'], '-PrivateHsaReceiptSha256', value['receipt_sha256']]


def validate_engine(engine, repo):
    if engine.get('kind')=='halogen':
        halogen_draft_arguments(engine)
        directory=(repo/engine['directory']).resolve()
        if not directory.is_relative_to((repo/'backends').resolve()):
            raise ValueError('Halogen backend directory is outside this repository')
        if engine.get('checkpoint') not in ('w4b','v2'):
            raise ValueError('Unknown checkpoint')
        if type(engine.get('context')) is not int or not 4096<=engine['context']<=262144:
            raise ValueError('Invalid context')
        if not (directory/'Start.ps1').is_file(): raise ValueError('Backend launcher missing')
        validate_halogen_launcher_controls(engine,repo)
        halogen_kernel_arguments(engine,directory)
        halogen_speculation_arguments(engine,directory)
        halogen_matmul_arguments(engine,directory)
        halogen_lookup_arguments(engine,directory)
        halogen_private_hsa_arguments(engine,directory)
        return directory
    if 'kernel_controls' in engine:
        raise ValueError('Managed kernel controls apply only to Halogen')
    if 'speculation_policy' in engine:
        raise ValueError('Managed speculation policies apply only to Halogen')
    if 'matmul_tuning' in engine:
        raise ValueError('Managed matmul plans apply only to Halogen')
    if 'lookup_tuning' in engine:
        raise ValueError('Managed lookup sources apply only to Halogen')
    if 'private_hsa' in engine:
        raise ValueError('Managed private HSA applies only to Halogen')
    if engine.get('kind')!='native' or engine.get('qualified') is not True:
        raise ValueError('Native backend requires an explicitly qualified local profile')
    executable=Path(engine['command'][0])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('Native executable must be an existing absolute path')
    with executable.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=engine.get('executable_sha256'):
        raise ValueError('Native runtime identity changed; requalification required')
    for name, expected in engine.get('runtime_hashes',{}).items():
        if not isinstance(name,str) or Path(name).name!=name or '/' in name or '\\' in name:
            raise ValueError('Runtime pin must be an app-local filename')
        artifact=executable.parent/name
        if artifact.is_symlink() or not artifact.is_file():
            raise ValueError('Pinned native runtime component missing: '+name)
        with artifact.open('rb') as stream: observed=hashlib.file_digest(stream,'sha256').hexdigest()
        if observed!=expected:
            raise ValueError('Native runtime bytes changed; requalification required: '+name)
    command=engine['command']
    if any(not isinstance(x,str) or '\x00' in x for x in command):
        raise ValueError('Invalid native argument vector')
    if not any(command[i:i+2]==['--host','127.0.0.1'] for i in range(len(command)-1)):
        raise ValueError('Native runtime must explicitly bind IPv4 loopback')
    return executable.parent


class Engine:
    def __init__(self, config, gateway, repo, logs):
        self.config=config; self.gateway=gateway; self.repo=repo; self.logs=logs
        self.directory=validate_engine(config,repo)
        self.process=None; self.output=None; self.halogen_run=None
        self.previous_run=None; self.tail_stop=threading.Event()

    def start(self):
        env=os.environ.copy()
        for name in list(env):
            if name.startswith(('GGML_','GUFO_','A3B_','HIP_','HSA_','HALOGEN_')):
                env.pop(name)
        if self.config['kind']=='halogen':
            if (self.directory/'.local/runner.lock').exists():
                raise ValueError('Existing or unresolved Halogen ownership lock')
            previous=self.directory/'.local/current-service.json'
            self.previous_run=read(previous).get('run_id') if previous.exists() else None
            command=[self.config['powershell'],'-NoProfile','-File',str(self.directory/'Start.ps1'),
                     '-Checkpoint',self.config['checkpoint'],'-ContextSize',str(self.config['context']),
                     '-PromptCache',self.config.get('prompt_cache','Off')]
            command+=halogen_draft_arguments(self.config)
            command+=halogen_kernel_arguments(self.config,self.directory)
            command+=halogen_speculation_arguments(self.config,self.directory)
            command+=halogen_matmul_arguments(self.config,self.directory)
            command+=halogen_lookup_arguments(self.config,self.directory)
            command+=halogen_private_hsa_arguments(self.config,self.directory)
        else:
            command=list(self.config['command'])
            if self.config.get('api_key_from_backend_token'):
                if not self.gateway.backend_secret or '--api-key' in command:
                    raise ValueError('A unique backend token is required for the native API')
                command+=['--api-key',self.gateway.backend_secret]
            env['PATH']=str(self.directory)+os.pathsep+env.get('PATH','')
            env.update(self.config.get('environment',{}))
        env['ALLOY_MANAGED']='1'
        env['PYTHONUTF8']='1'
        name=uuid.uuid4().hex
        paths=[self.logs/(name+'-stdout.log'),self.logs/(name+'-stderr.log')]
        self.process=JobChild(command,cwd=self.directory,env=env,
                             stdout_path=paths[0],stderr_path=paths[1])
        def output():
            streams=[p.open('r',encoding='utf-8',errors='replace') for p in paths]
            try:
                while not self.tail_stop.is_set():
                    for stream in streams:
                        for line in stream:
                            for key in (self.gateway.secret,self.gateway.backend_secret):
                                if key: line=line.replace(key,'[REDACTED]')
                            LOG.info('engine %s',line.rstrip())
                    self.tail_stop.wait(.1)
            finally:
                for stream in streams: stream.close()
        self.output=threading.Thread(target=output,daemon=True); self.output.start()

    def state(self):
        if self.config['kind']!='halogen': return None
        path=self.directory/'.local/current-service.json'
        if not path.exists(): return None
        value=read(path)
        if (value.get('controller_pid') and value.get('phase') in ('starting','ready')
            and value.get('run_id')!=self.previous_run
            and value.get('context')==self.config.get('context')
            and value.get('checkpoint')==self.config.get('checkpoint')
            and self.process is not None and self.process.contains(value['controller_pid'])):
            if self.halogen_run is None: self.halogen_run=value['run_id']
        return value if value.get('run_id')==self.halogen_run else None

    def stopped_unexpectedly(self):
        return self.process is not None and self.process.poll() is not None

    async def stop(self):
        if self.process is None: return
        if self.config['kind']=='halogen':
            state=self.state()
            if state and state.get('phase') not in ('stopped','failed'):
                attempt=Path(state['attempt'])
                if attempt.resolve().parent!=(self.directory/'.local/services').resolve():
                    raise ValueError('Unexpected Halogen state directory')
                atomic(attempt/'stop.json',{'run_id':self.halogen_run})
            try: await asyncio.to_thread(self.process.wait,240)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Halogen cleanup unresolved; controller did not kill unrelated WSL tasks')
            state=self.state()
            if state and (not state.get('outcome',{}).get('cleanup') or
                          not state.get('outcome',{}).get('recovery')):
                raise RuntimeError('Halogen cleanup/recovery did not complete')
        elif self.process.poll() is None:
            # The public gateway has already drained/cancelled its requests.
            # Close ONLY the retained native job, never taskkill by image name.
            self.process.close()
            LOG.info('owned_native_job_stopped')
        self.tail_stop.set()
        if self.output: await asyncio.to_thread(self.output.join,5)
        self.process.close()



def control(action):
    state=read(LOCAL/'current.json')
    if action=='status':
        state['controller_fresh']=0<=time.time()-state.get('heartbeat',0)<=10
        print(json.dumps(state,indent=2)); return 0
    if state.get('phase') in ('stopped','failed'):
        print('Controller is already terminal.'); return 0
    atomic(LOCAL/'stop.json',{'run_id':state['run_id']})
    print('Stop requested; wait for STOPPED before starting another backend.')
    return 0


async def run(config_path, port):
    profile_bytes=Path(config_path).read_bytes()
    configuration=json.loads(profile_bytes.decode('utf-8-sig'))
    reserve=memory_reserve_gib(configuration)
    if 'private_hsa' in configuration['engine'] and (
            reserve != 18 or configuration.get('concurrency', 1) != 1 or
            configuration['backend'].get('identifier') != 'halogen-v2' or
            configuration['backend'].get('checkpoint') != 'v2' or
            configuration['backend'].get('context') != 262144):
        raise ValueError('Private HSA requires the singleton Stock8K gateway with its 18 GiB reserve')
    gateway=load_config(config_path)
    if Path(config_path).read_bytes()!=profile_bytes:
        raise ValueError('Selected profile changed while loading')
    if not 1024<=port<=65535 or int(gateway.backend.upstream.rsplit(':',1)[1])==port:
        raise ValueError('Public and backend ports must be valid and distinct')
    engine=Engine(configuration['engine'],gateway,ROOT.parent,LOCAL)
    run_id=uuid.uuid4().hex
    state={'schema':1,'run_id':run_id,'pid':os.getpid(),'phase':'starting',
           'backend':gateway.backend.identifier,'checkpoint':gateway.backend.checkpoint,
           'context':gateway.backend.context,'port':port,'heartbeat':time.time(),
           'minimum_reserve_gib':reserve,
           'profile_sha256':hashlib.sha256(profile_bytes).hexdigest()}
    stop=asyncio.Event(); loop=asyncio.get_running_loop(); original=None
    def interrupt(*_): loop.call_soon_threadsafe(stop.set)
    original=signal.signal(signal.SIGINT,interrupt)
    error=None; server_task=None; guard_task=None
    def cancelled():
        path=LOCAL/'stop.json'
        return stop.is_set() or (path.exists() and read(path).get('run_id')==run_id)
    try:
        atomic(LOCAL/'current.json',state)
        # Refuse to adopt any pre-existing listener or an unrelated process.
        import socket
        origin=gateway.backend.upstream.rsplit(':',1)
        for candidate_port in {port,int(origin[1]),8731,8826,8836,18808}:
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',candidate_port))==0:
                    raise RuntimeError(f'Inference port {candidate_port} occupied; existing process not adopted')
        engine.start()
        async def memory_guard():
            from host_frames import frame
            while not stop.is_set():
                snapshot=frame()
                state['memory']=snapshot
                state['minimum_available_gib']=min(state.get('minimum_available_gib',float('inf')),
                                                   snapshot['available_bytes']/1024**3)
                if min(snapshot['available_bytes'],snapshot['commit_headroom_bytes'])<reserve*1024**3:
                    if engine.config['kind']=='native': engine.process.close()
                    stop.set()
                    raise RuntimeError(f'Windows physical/commit reserve crossed {reserve:g} GiB')
                await asyncio.sleep(.5)
        guard_task=asyncio.create_task(memory_guard())
        deadline=time.monotonic()+1200
        import aiohttp
        async with aiohttp.ClientSession(trust_env=False,auto_decompress=False) as client:
            gateway.client=client
            while True:
                if guard_task.done(): await guard_task
                if cancelled(): raise InterruptedError('Startup stopped by operator')
                if engine.stopped_unexpectedly(): raise RuntimeError('Engine exited before readiness')
                state['heartbeat']=time.time(); atomic(LOCAL/'current.json',state)
                if time.monotonic()>deadline: raise TimeoutError('Engine readiness timeout')
                model_state=engine.state()
                if engine.config['kind']=='halogen' and not model_state:
                    await asyncio.sleep(.2); continue
                try: await gateway.probe(); break
                except (aiohttp.ClientError,TimeoutError,ValueError): await asyncio.sleep(1)
        state['phase']='ready'; state['ready_at']=time.time()
        server_task=asyncio.create_task(serve(gateway,port,stop))
        while not cancelled():
            if guard_task.done(): await guard_task
            if server_task.done(): await server_task; raise RuntimeError('Gateway unexpectedly stopped')
            if engine.stopped_unexpectedly(): raise RuntimeError('Engine process exited')
            free=available_gib()
            if free is not None and free<reserve: raise RuntimeError(f'Windows physical reserve crossed {reserve:g} GiB')
            state.update(heartbeat=time.time(),active_requests=gateway.active,available_gib=free)
            atomic(LOCAL/'current.json',state)
            await asyncio.sleep(1)
    except InterruptedError:
        LOG.info('startup_cancelled')
    except Exception as exc:
        error=str(exc); LOG.error('controller_failed type=%s detail=%s',type(exc).__name__,error)
    finally:
        state.update(phase='stopping',heartbeat=time.time())
        try: atomic(LOCAL/'current.json',state)
        except OSError as exc: LOG.warning('Stopping-state write failed; cleanup continues: %s',exc)
        gateway.draining=True; stop.set()
        if guard_task:
            try: await guard_task
            except Exception as exc: error=error or str(exc)
        try:
            if server_task: await server_task
        except BaseException as exc:
            error=(error+'; ' if error else '')+'gateway cleanup: '+type(exc).__name__
        try: await engine.stop()
        except Exception as exc:
            error=(error+'; ' if error else '')+'cleanup: '+str(exc)
            LOG.error('cleanup_unresolved %s',type(exc).__name__)
            if engine.process: engine.process.close()
            engine.tail_stop.set()
        state.update(phase='failed' if error else 'stopped',heartbeat=time.time(),error=error)
        atomic(LOCAL/'current.json',state)
        signal.signal(signal.SIGINT,original)
        LOG.info('STOPPED backend=%s error=%s',gateway.backend.identifier,bool(error))
    return 2 if error else 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['run','status','stop'])
    p.add_argument('--config',type=Path)
    p.add_argument('--port',type=int,default=8840)
    args=p.parse_args(); LOCAL.mkdir(parents=True,exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[
        logging.StreamHandler(),RotatingFileHandler(LOCAL/'controller.log',
            maxBytes=10*1024**2,backupCount=3,encoding='utf-8')])
    if args.action!='run': return control(args.action)
    if args.config is None: raise ValueError('--config is required for run')
    with lease(LOCAL/'controller.lock'):
        return asyncio.run(run(args.config,args.port))

if __name__=='__main__': raise SystemExit(main())
