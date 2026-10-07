"""Root-owned bounded component study; normal stop and visible restoration.

No import performs hardware work. A sealed command plan is required. Historical
raw receipts are never overwritten. Observation timeouts retain the same child.
"""
import argparse
import asyncio
import contextlib
import ctypes
from ctypes import wintypes as W
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'server/.local/optimization9h-20261004'
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'
PS51 = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
sys.path[:0] = [str(ROOT/'server'), str(ROOT/'scripts/benchmarks'), str(BACKEND/'scripts')]
from host_frames import frame
from owned_child import JobChild
import controller
import winjob


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def setup():
    base = load('handoff_lifecycle_base', BASE/'run_rocr_engine_stock8k.py')
    base.io = load('handoff_io', base.IO_PATH)
    base.lifecycle = load('handoff_lifecycle', base.LIFECYCLE_PATH)
    base.component = load('handoff_identity', base.COMPONENT_PATH)
    base.controller = controller
    base.service = load('service', BACKEND/'scripts/service.py')
    base.service.r.configure()
    base.frame = frame
    native = load('handoff_native_identity', BASE/'save_servicenow_current_20261006.py')
    return base, native


def status(base, native, saved, out):
    expected = saved['current_user_server']
    identities = {key: native.identity(expected[key]['pid']) for key in
                  ('controller_identity', 'backend_identity', 'foreground_console_identity')}
    require(all(identities[key] == expected[key] for key in identities), 'Live server birth changed')
    state, inner = read(ROOT/'server/.local/current.json'), read(BACKEND/'.local/current-service.json')
    require(state['phase'] == inner['phase'] == 'ready' and state['run_id'] == expected['controller_run_id'] and
            inner['run_id'] == expected['backend_run_id'], 'Live server run/phase changed')
    profile = [p for p in (ROOT/'server/.local/servicenow-sessions').glob('*.json')
               if sha(p) == expected['profile_sha256']]
    require(profile, 'Current HistoricalStock profile bytes not found')
    handle = base.retained_type()(identities['controller_identity'])
    cell = dict(name='initial-HistoricalStock', variant='stock', out=out, process=handle, handle=handle,
                controller_run=state['run_id'], backend_run=inner['run_id'], cid=inner['container_id'],
                profile=profile[0], profile_sha256=expected['profile_sha256'], stopped=False)
    base.identity(cell)
    health = asyncio.run(base.gateway_idle(cell))
    cell['completed'] = health['completed']
    memory = frame()
    require(min(memory['available_bytes'], memory['commit_headroom_bytes']) >= 18*2**30,
            'Original runtime requires18GiB physical and commit reserve')
    receipt = dict(identities=identities, controller=state, backend=inner, health=health, memory=memory)
    write(out/'preflight.json', receipt)
    return cell, receipt


def parents():
    # Toolhelp supplies the actual foreground launcher ancestry, not timestamps.
    class Entry(ctypes.Structure):
        _fields_ = [('size',W.DWORD),('cnt',W.DWORD),('pid',W.DWORD),('heap',ctypes.c_size_t),
                    ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),
                    ('flags',W.DWORD),('exe',W.WCHAR*260)]
    api = winjob._api()
    api.CreateToolhelp32Snapshot.argtypes = [W.DWORD,W.DWORD]
    api.CreateToolhelp32Snapshot.restype = W.HANDLE
    api.Process32FirstW.argtypes = api.Process32NextW.argtypes = [W.HANDLE,ctypes.POINTER(Entry)]
    api.Process32FirstW.restype = api.Process32NextW.restype = W.BOOL
    h = winjob._check(api.CreateToolhelp32Snapshot(2,0))
    try:
        e, result = Entry(), {}
        e.size = ctypes.sizeof(e)
        winjob._check(api.Process32FirstW(h,ctypes.byref(e)))
        while True:
            result[int(e.pid)] = int(e.parent)
            if not api.Process32NextW(h,ctypes.byref(e)):
                require(ctypes.get_last_error() == 18, 'Process census incomplete')
                return result
    finally:
        winjob._check(api.CloseHandle(h))


def restore(base, native, work, runtime, env, expected_profile, guard, capture=None):
    out = work/'restore-HistoricalStock'
    out.mkdir()
    base.lifecycle.stopped_preflight(BACKEND)
    base.service.r.exclusive_host()
    # Keep WSL resident while measuring startup admission; no global WSL edits.
    with contextlib.closing(JobChild([r'C:\Windows\System32\wsl.exe','-d','Ubuntu-24.04','-u','revn','--exec','sleep','1800'],
                  cwd=ROOT, env=env, stdout_path=out/'hold.stdout',stderr_path=out/'hold.stderr')) as hold:
        stable, samples, deadline = None, [], time.monotonic()+240
        while time.monotonic() < deadline:
            guard()
            sample = frame()
            samples.append(sample)
            good = sample['available_bytes'] >= 44*2**30 and sample['commit_headroom_bytes'] >= 131*2**30
            stable = (stable if stable is not None else time.monotonic()) if good else None
            if stable is not None and time.monotonic()-stable >= 60:
                break
            time.sleep(1)
        write(out/'startup-admission.json',dict(samples=samples,stable_seconds=60,physical_gib=44,commit_gib=131))
        require(stable is not None and time.monotonic()-stable >= 60, 'Startup admission did not stabilize')
        previous_run = read(BACKEND/'.local/current-service.json')['run_id']
        old_profiles = set((ROOT/'server/.local/servicenow-sessions').glob('*.json'))
        command = [PS51,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/Start-Halogen-ServiceNow.ps1'),
                   '-Profile','HistoricalStock','-ConsoleTrace']
        trace = None
        if capture:
            trace = JobChild(capture['record_command'],cwd=ROOT,env=env,
                             stdout_path=out/'record.jsonl',stderr_path=out/'record.stderr')
            write(out/'record-retained.json',trace.owner.verify_live_identity())
            until_trace=time.monotonic()+10
            while time.monotonic()<until_trace and trace.poll() is None:
                text=(out/'record.jsonl').read_text(encoding='utf-8')
                if '"event":"capture_ready"' in text.replace(' ',''):
                    break
                time.sleep(.05)
            # Tracing failure never prevents the required server restoration.
        console = subprocess.Popen(command,cwd=ROOT,env=env,creationflags=subprocess.CREATE_NEW_CONSOLE)
        console_id = base.persistent_identity(console,PS51)
        write(out/'retained-console.json',dict(identity=console_id,command=command))
        until = time.monotonic()+900
        cell = None
        while time.monotonic() < until:
            guard()
            require(console.poll() is None, 'Visible restoration console exited')
            state = read(ROOT/'server/.local/current.json')
            if state.get('phase') not in ('stopped','failed'):
                ancestry, pid, census = [], state['pid'], parents()
                for _ in range(8):
                    if pid == console.pid:
                        break
                    require(pid in census and pid not in ancestry, 'Foreground ancestry unresolved')
                    ancestry.append(pid)
                    pid = census[pid]
                require(pid == console.pid, 'Unrelated controller replaced state')
                matches = [p for p in (ROOT/'server/.local/servicenow-sessions').glob('*.json')
                           if p not in old_profiles and sha(p) == state['profile_sha256']]
                require(len(matches) == 1 and read(matches[0]) == expected_profile, 'Restored profile changed')
                observed = native.identity(state['pid'])
                require(os.path.normcase(observed['executable']) == os.path.normcase(runtime['executable']),
                        'Restored interpreter changed')
                handle = base.retained_type()(observed)
                cell = dict(name='restore-HistoricalStock',variant='stock',out=out,process=handle,handle=handle,
                            profile=matches[0],profile_sha256=state['profile_sha256'],stopped=False)
                break
            time.sleep(1)
        require(cell is not None, 'Visible foreground binding timed out; retain console, do not duplicate')
        while True:
            guard()
            try:
                state, inner = base.lifecycle.ready(cell['process'],cell['profile_sha256'],previous_run,
                                                    BACKEND,deadline_seconds=45)
                break
            except TimeoutError:
                cell['handle'].verify()
                print(json.dumps(dict(phase='same-handle-ready-observation',pid=cell['process'].pid)),flush=True)
        cell.update(controller_run=state['run_id'],backend_run=inner['run_id'],cid=inner['container_id'])
        base.identity(cell)
        health = asyncio.run(base.gateway_idle(cell))
        receipt = dict(controller=state,backend=inner,health=health,controller_identity=cell['handle'].verify(),
                       backend_identity=native.identity(inner['controller_pid']),
                       foreground_console_identity=native.identity(console_id['pid']),open=True,
                       profile_sha256=cell['profile_sha256'],profile='HistoricalStock',console_trace=True)
        write(work/'final-ready.json',receipt)
        if capture and trace:
            marker=Path(capture['record_stop'])
            if not marker.exists():
                marker.touch()
            try:
                while trace.poll() is None:
                    guard()
                    time.sleep(.1)
                write(out/'record-exit.json',dict(exit_code=trace.poll()))
            finally:
                trace.close()
            if read(out/'record-exit.json')['exit_code']==0:
                with contextlib.closing(JobChild(capture['decode_command'],cwd=ROOT,env=env,
                        stdout_path=out/'decode.stdout',stderr_path=out/'decode.stderr')) as decoder:
                    deadline=time.monotonic()+90
                    while decoder.poll() is None:
                        guard()
                        require(time.monotonic()<deadline,'Restoration trace decoder deadline')
                        time.sleep(.1)
                    write(out/'decode-exit.json',dict(exit_code=decoder.poll()))
        saved = read(BASE/'continuation-current.json')
        saved['current_user_server'].update(phase='ready',controller_pid=state['pid'],controller_run_id=state['run_id'],
            backend_controller_pid=inner['controller_pid'],backend_run_id=inner['run_id'],container_id=inner['container_id'],
            controller_identity=receipt['controller_identity'],backend_identity=receipt['backend_identity'],
            foreground_console_identity=receipt['foreground_console_identity'],profile_sha256=cell['profile_sha256'],
            latest_observation=str(work/'final-ready.json'),npu_integrated=False)
        saved.update(controller_run_id=state['run_id'],service_run_id=inner['run_id'])
        controller.atomic(BASE/'continuation-current.json',saved)
        cell['handle'].close()
        return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan',type=Path)
    p.add_argument('--sha256')
    p.add_argument('--preflight-only',action='store_true')
    args = p.parse_args()
    base, native = setup()
    work = BASE/('npu-copy-handoff-'+uuid.uuid4().hex)
    work.mkdir()
    initial, preflight = status(base,native,read(BASE/'continuation-current.json'),work)
    if args.preflight_only:
        initial['handle'].close()
        print(json.dumps(dict(work=str(work),memory=preflight['memory'],ready_open=True)),flush=True)
        return 0
    require(args.plan and args.sha256 and sha(args.plan) == args.sha256, 'Sealed plan required')
    plan = read(args.plan)
    for path,digest in plan['source_pins'].items():
        require(sha(path) == digest,'Changed study input: '+path)
    require(plan['initial'] == preflight['identities'],'Sealed live identity changed')
    write(work/'plan.json',plan)
    runtime = base.lifecycle.controller_runtime()
    env = base.lifecycle.controller_environment(os.environ.copy(),runtime)
    saved = read(BASE/'continuation-current.json')
    saved['active_session'] = dict(coordinator=native.identity(os.getpid()),work=str(work),
                                  plan=str(args.plan),phase='verified-starting-owned-study')
    controller.atomic(BASE/'continuation-current.json',saved)
    print(json.dumps(dict(phase='verified-starting-owned-study',pid=os.getpid(),work=str(work))),flush=True)
    errors, stop_attempted, restored = [], False, False
    guard_error, finished, minimum = [], threading.Event(), {}
    def guard():
        require(not guard_error,'Runtime reserve failed: '+str(guard_error))
    def monitor():
        with (work/'memory.jsonl').open('x',encoding='utf-8') as stream:
            while not finished.is_set():
                f = frame()
                for key in ('available_bytes','commit_headroom_bytes'):
                    minimum[key] = min(minimum.get(key,f[key]),f[key])
                stream.write(json.dumps(dict(qpc=time.perf_counter_ns(),**f))+'\n')
                stream.flush()
                if min(f['available_bytes'],f['commit_headroom_bytes']) < 18*2**30 and not guard_error:
                    guard_error.append(f)
                finished.wait(.1)
    t = threading.Thread(target=monitor,daemon=True)
    t.start()
    try:
        stop_attempted = True
        base.stop(initial,env)
        require(initial['terminal']['controller']['phase'] == 'stopped','Original normal stop failed')
        for index,command in enumerate(plan['commands']):
            guard()
            require(min(frame()[key] for key in ('available_bytes','commit_headroom_bytes')) >= 22*2**30,
                    'New component request requires22GiB')
            out = work/('command-'+str(index))
            out.mkdir()
            print(json.dumps(dict(phase='component-command',index=index,work=str(work))),flush=True)
            with contextlib.closing(JobChild(command,cwd=ROOT,env=env,stdout_path=out/'stdout.log',stderr_path=out/'stderr.log')) as child:
                write(out/'retained.json',dict(identity=child.owner.verify_live_identity(),command=command))
                deadline = time.monotonic()+450
                while child.poll() is None:
                    guard()
                    require(time.monotonic()<deadline,'Bounded study command deadline; retained job will close')
                    time.sleep(.2)
                require(child.poll() == 0,'Component command failed: '+str(index)+'; '+str(out))
    except BaseException as error:
        errors.append(type(error).__name__+': '+str(error))
    finally:
        if stop_attempted:
            try:
                # No new engine until the exact original stop/recovery is proven.
                if not initial.get('stopped'):
                    base.stop(initial,env)
                def restore_guard():
                    sample=frame()
                    require(min(sample['available_bytes'],sample['commit_headroom_bytes'])>=18*2**30,
                            'Restoration current physical/commit reserve below18GiB')
                capture=plan.get('restore_capture')
                if capture:
                    # Bind fresh trace paths to this run's actual restoration.
                    capture=json.loads(json.dumps(capture).replace('{RESTORE}',str(work/'restore-HistoricalStock').replace('\\','\\\\')))
                restore(base,native,work,runtime,env,read(initial['profile']),restore_guard,capture)
                restored = True
            except BaseException as error:
                errors.append('Restoration pending: '+type(error).__name__+': '+str(error))
        finished.set()
        t.join(2)
        if guard_error:
            errors.append('Runtime18GiB reserve violation recorded')
        result = dict(work=str(work),errors=errors,original_ready_open=restored,minimum_memory=minimum,
                      engine_gain_measured=False,goal_completed=False)
        write(work/'study-result.json',result)
        saved = read(BASE/'continuation-current.json')
        if restored:
            saved['active_session']=None
        saved['latest_npu_handoff_study']=dict(work=str(work),result=str(work/'study-result.json'),
                                              original_ready_open=restored,errors=errors)
        controller.atomic(BASE/'continuation-current.json',saved)
        print(json.dumps(result),flush=True)
    return 0 if restored and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
