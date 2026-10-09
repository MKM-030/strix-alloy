"""Root-owned isolated native bulk-MoE pair; no live hooks or serving changes."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
STATE = PREP.parent/'continuation-current.json'
sys.path.insert(0,str(ROOT/'server'))
from controller import read, atomic
from host_frames import frame
from winjob import OwnedProcess
spec = importlib.util.spec_from_file_location('actual_identity',PREP.parent/'halogen0171-backend-preparation-20261007/checkpoint_actual_handles.py')
identities = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identities)
WS = [r'C:\Windows\System32\wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec']
KEY = 'active0172_bulk_bn64_component_batched'
TEMP = '/tmp/alloy0172-bulk-bn64-v2-batched'
NATIVE_SHA = '18937428b544e8a5ef1dae31db97f36136e8cdeca90e6c49458ef831b822a039'
def utc(): return datetime.now(timezone.utc).isoformat()
def ref(path):
    with path.open('rb') as f: digest = hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)
def linux(path): return '/mnt/c/'+path.resolve().relative_to(Path('C:/')).as_posix()

def main():
    import urllib.request
    assert not (WORK/'result.json').exists(), 'Completed comparison is terminal'
    assert not (WORK/'progress.json').exists(), 'Observe the existing owner; do not duplicate'
    saved = read(STATE)['current_user_server']
    backend = read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')
    assert backend['run_id']==saved['backend_run_id'] and backend['phase']=='ready'
    profile_path = Path(saved['profile'])
    assert ref(profile_path)['sha256']==saved['profile_sha256']
    profile = read(profile_path)
    token = Path(profile['token_file']).read_text(encoding='ascii').strip()
    docker = WS+['docker','exec',backend['container_id']]
    def check_idle(admission=False):
        current = read(ROOT/'server/.local/current.json')
        live_backend = read(ROOT/'backends/halogen-wsl2-0.17.2/.local/current-service.json')
        assert current['phase']==live_backend['phase']=='ready'
        assert (current['pid'],current['run_id'])==(saved['controller_pid'],saved['controller_run_id'])
        assert (live_backend['controller_pid'],live_backend['run_id'],live_backend['container_id'])==(
            backend['controller_pid'],backend['run_id'],backend['container_id'])
        assert 0<=time.time()-current['heartbeat']<=15
        for field in ('controller_identity','backend_identity','foreground_console_identity'):
            assert identities.identity(saved[field]['pid'])==saved[field], field
        request = urllib.request.Request('http://127.0.0.1:8840/health',headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=10) as response: health=json.load(response)
        assert health['status']=='ok' and health['active_requests']==0 and not health['draining']
        memory=frame()
        assert min(memory['available_bytes'],memory['commit_headroom_bytes'])>=(22 if admission else 18)*2**30
        return dict(health=health,memory=memory)
    before=check_idle(admission=True)
    minimum=[before['memory']]
    record=dict(schema='halogen0172.bulk-bn64-synthetic.v2-batched',started_utc=utc(),phase='preparing',
        coordinator_identity=identities.identity(os.getpid()),original_server=saved,
        source=ref(WORK/'host.c'),coordinator=ref(Path(__file__)),before=before,stages=[],
        hardware_executed=False,engine_request_performed=False,lifecycle_performed=False,
        serving_gain_qualified=False,NPU_executed=False)
    def publish():
        atomic(WORK/'progress.json',record)
        state=read(STATE)
        state[KEY]=dict(phase=record['phase'],directory=str(WORK),coordinator_identity=record['coordinator_identity'],
            helper_identity=record.get('helper_identity'),progress=str(WORK/'progress.json'),
            hardware_executed=record['hardware_executed'],serving_gain_qualified=False,NPU_executed=False)
        atomic(STATE,state)
    publish()
    def cmd(args,timeout=30):
        result=subprocess.run(args,capture_output=True,text=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==0, result.stderr[:400]
        return result.stdout
    def stage(name,args,deadline_seconds):
        entry=dict(name=name,args=args)
        record['stages'].append(entry)
        process=OwnedProcess(args,cwd=ROOT,env=dict(os.environ),stdout_path=WORK/(name+'-stdout.txt'),stderr_path=WORK/(name+'-stderr.txt'))
        try:
            entry['identity']=process.identity
            record.update(phase=name,helper_identity=process.identity)
            publish()
            print(json.dumps(dict(phase=name,identity=process.identity)),flush=True)
            process.resume()
            deadline=time.monotonic()+deadline_seconds
            while not process.wait(200):
                memory=frame();minimum.append(memory)
                assert min(memory['available_bytes'],memory['commit_headroom_bytes'])>=18*2**30
                assert time.monotonic()<deadline, 'Owned helper deadline'
            entry['exit_code']=process.exit_code()
        finally:
            process.close();entry['owned_job_closed']=True
            record['helper_identity']=None
        entry['stdout']=ref(WORK/(name+'-stdout.txt'))
        entry['stderr']=ref(WORK/(name+'-stderr.txt'))
        return entry['exit_code']
    def cleanup(compiler=False,abort=False):
        targets=[linux(WORK/'host.c'),linux(WORK/'host')] if compiler else [TEMP+'/host']
        program="""import json,os,pathlib,signal,time
targets=%r; abort=%r
def owned():
 result=[]
 for d in pathlib.Path('/proc').iterdir():
  if not d.name.isdigit(): continue
  try:
   args=[a.decode() for a in (d/'cmdline').read_bytes().split(b'\\0') if a]
   if not args or not any(t in args for t in targets): continue
   if os.path.basename(args[0]) not in ('timeout','gcc','cc1','collect2','ld','host'): continue
   stat=(d/'stat').read_text().rsplit(')',1)[1].split()
   result.append(dict(pid=int(d.name),start_ticks=int(stat[19]),arguments=args))
  except (OSError,UnicodeError): continue
 return result
initial=owned(); signalled=[]
if abort:
 for sig in (signal.SIGTERM,signal.SIGKILL):
  for item in owned():
   if {x['pid']:x for x in owned()}.get(item['pid'])==item:
    try: os.kill(item['pid'],sig);signalled.append(item)
    except ProcessLookupError: pass
  deadline=time.monotonic()+2
  while owned() and time.monotonic()<deadline: time.sleep(.05)
remaining=owned()
print(json.dumps(dict(observed=initial,signalled=signalled,remaining=remaining,closed=not remaining)))
"""%(targets,abort)
        return json.loads(cmd((WS if compiler else docker)+['python3','-c',program]))
    load_code="""$gaming=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'League|Riot'} | Select-Object ProcessId,Name,CreationDate)
$gpu=Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
$samples=@($gpu.CounterSamples)
[pscustomobject]@{gaming=$gaming;sample_count=$samples.Count;active=@($samples|Where-Object {$_.CookedValue -gt 1}|Select-Object InstanceName,CookedValue)} | ConvertTo-Json -Depth 5
"""
    try:
        record['current_load']=json.loads(cmd([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-Command',load_code]))
        load=record['current_load']
        assert not load['gaming'] and load['sample_count']>0 and not load['active'], 'Competing GPU load'
        native=PREP/'ple0172-math-delta-audit/engine0172-gfx1151-bundle0.hsaco'
        record['native']=ref(native)
        assert record['native']['sha256']==NATIVE_SHA
        record['fixture_abi_review']=ref(WORK/'fixture-abi-review.md')
        assert stage('host-build',WS+['timeout','-k','2','30','gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',linux(WORK/'host.c'),'-ldl','-lm','-o',linux(WORK/'host')],45)==0
        record['host_executable']=ref(WORK/'host')
        cmd(docker+['mkdir','-m','700','--',TEMP])
        for source,dest in [(native,'native.hsaco'),(WORK/'host','host')]:
            cmd(WS+['docker','cp',linux(source),backend['container_id']+':'+TEMP+'/'+dest])
        cmd(docker+['chmod','500','--',TEMP+'/host'])
        check_idle(admission=True)
        loader=read(PREP/'profiler-availability/engine-loader.json')['loader']
        env=['env','LD_LIBRARY_PATH='+loader['LD_LIBRARY_PATH'],'LD_PRELOAD='+loader['LD_PRELOAD'],
            'HSA_ENABLE_DXG_DETECTION=1','HSA_DISABLE_COREDUMP_ON_EXCEPTION=1']
        record['hardware_executed']=True
        hip_library='/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7'
        exit_code=stage('component',docker+env+['timeout','-k','2','150',TEMP+'/host',TEMP+'/native.hsaco',hip_library],165)
        record['component_exit_code']=exit_code
        record['component_rows']=[json.loads(line) for line in (WORK/'component-stdout.txt').read_text().splitlines() if line.startswith('{')]
        assert exit_code==0, 'Paired component failed; retain actual output and error'
        assert record['component_rows'] and record['component_rows'][-1].get('passed') is True
        record['passed']=True
    except BaseException as error:
        record.update(passed=False,error=type(error).__name__+': '+str(error))
    finally:
        closed=False;ready=False
        try:
            record['linux_cleanup']=dict(component=cleanup(abort=not record.get('passed',False)),compiler=cleanup(compiler=True,abort=not record.get('passed',False)))
            closed=all(x['closed'] for x in record['linux_cleanup'].values()) and all(x.get('owned_job_closed') for x in record['stages'])
            assert closed
        except BaseException as error:
            record.update(passed=False,cleanup_error=type(error).__name__+': '+str(error))
        try:
            record['after']=check_idle();minimum.append(record['after']['memory']);ready=True
        except BaseException as error:
            record.update(passed=False,final_ready_error=type(error).__name__+': '+str(error))
        record.update(phase='terminal',finished_utc=utc(),coordinator_identity=None,helper_identity=None,
            original_ready_open=ready,own_helpers_closed=closed,
            minimum_available_bytes=min(x['available_bytes'] for x in minimum),
            minimum_commit_headroom_bytes=min(x['commit_headroom_bytes'] for x in minimum))
        atomic(WORK/'result.json',record);publish()
        state=read(STATE)
        state[KEY].update(result=ref(WORK/'result.json'),passed=record.get('passed',False),
            original_ready_open=ready,own_helpers_closed=closed)
        atomic(STATE,state)
    print(json.dumps(dict(passed=record.get('passed',False),error=record.get('error'),original_ready_open=record['original_ready_open'],result=str(WORK/'result.json'))),flush=True)
    return 0 if record.get('passed',False) else 1
if __name__=='__main__': raise SystemExit(main())
