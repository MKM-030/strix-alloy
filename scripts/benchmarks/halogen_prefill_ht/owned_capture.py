"""Root-only one-request Prefill fixture capture; always restore stock open.

Use an independently reviewed sealed plan. No serving rate claim is made by
this intrusive capture. Observation timeouts continue the same live process.
"""
import argparse
import asyncio
import datetime
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'server/.local/optimization9h-20261004'
BACKEND = ROOT / 'backends/halogen-wsl2-0.16.2'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False); f.write('\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def change(fn):
    p = BASE / 'continuation-current.json'; state = read(p); fn(state)
    state['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    temp = p.with_name('continuation-prefill-capture-' + uuid.uuid4().hex + '.tmp')
    write(temp, state); os.replace(temp, p)


def preflight(out):
    code = r"$ErrorActionPreference='Stop'; $procs=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'League|Riot|llama|flash_serve|gufo|nativeengine' } | Select-Object Name,ProcessId,CreationDate); $gpu=@(Get-Counter '\GPU Engine(*)\Utilization Percentage' | Select-Object -ExpandProperty CounterSamples | Where-Object { $_.CookedValue -gt 2 } | Select-Object InstanceName,CookedValue); [pscustomobject]@{processes=$procs;gpu=$gpu}|ConvertTo-Json -Depth 5 -Compress"
    r = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', code],
                       capture_output=True, text=True, check=True, timeout=30,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(r.stdout); write(out, value)
    require(not any('league' in p['Name'].lower() or p['Name'].lower() in
                    ('llama-server.exe', 'gufo.exe', 'gufo-server.exe', 'nativeengine.exe', 'flash_serve.exe')
                    for p in value['processes']), 'Competing game/model process present')
    require(not value['gpu'], 'GPU activity above2% before capture')


async def request(base, cell, plan, check, work):
    import aiohttp
    require(sha(plan['request']) == plan['request_sha256'], 'Frozen natural request changed')
    body = read(plan['request']); token = (BACKEND / '.local/api-token.txt').read_text(encoding='ascii').strip()
    check(); base.io.reserve(base.frame, 22); base.identity(cell)
    started = time.monotonic()
    async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=300)) as client:
        async def fetch():
            async with client.post('http://127.0.0.1:8840/v1/completions',
                                   headers={'Authorization': 'Bearer ' + token}, json=body) as reply:
                require(reply.status == 200, 'Capture request HTTP ' + str(reply.status))
                result = bytearray()
                async for part in reply.content.iter_chunked(65536):
                    result.extend(part); require(len(result) <= 2 << 20, 'Response budget exceeded')
                return json.loads(result)
        task = asyncio.create_task(fetch())
        try:
            while not task.done():
                check(); require(cell['process'].poll() is None, 'Capture controller exited')
                await asyncio.sleep(.2)
            result = await task
        finally:
            if not task.done(): task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    write(work / 'response.json', result)
    usage = result['usage']
    require(usage['prompt_tokens'] == 16384 and usage['completion_tokens'] == 128 and
            usage.get('cached_tokens', 0) == 0 and
            usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) == 0,
            'Frozen input/output/cache counts differ')
    health = await base.gateway_idle(cell); cell['completed'] = health['completed']
    require(health['completed'] == 1 and health['cancelled'] == 0, 'Extra/cancelled request')
    text = result['choices'][0].get('text')
    require(isinstance(text, str) and hashlib.sha256(text.encode()).hexdigest() == plan['expected_output_sha256'],
            'Capture changed the frozen output')
    write(work / 'request-result.json', dict(usage=usage, wall_seconds=time.monotonic()-started,
          intrusive_capture=True, serving_rates_qualified=False, output_sha256=plan['expected_output_sha256']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--source-sha256', required=True)
    a = p.parse_args(); require(os.name == 'nt' and not sys.flags.optimize, 'Local unoptimized Python required')
    require(sha(__file__) == a.source_sha256 and sha(a.plan) == a.plan_sha256, 'Coordinator/plan seal changed')
    plan = read(a.plan); require(plan['schema'] == 'halogen.prefill-ht.owned-capture.v1', 'Wrong plan')
    work = Path(plan['work']); require(not (work / 'result.json').exists(), 'Capture already terminal')
    for path, digest in plan['source_pins'].items(): require(sha(path) == digest, 'Pinned source changed: ' + path)
    saved = read(BASE / 'continuation-current.json')
    require(not saved['active_engine_sessions'] and not saved['active_optimization_children'] and
            not any(isinstance(v, dict) and v.get('active_handle') is not None for v in saved.values()),
            'Another hardware/lifecycle handle exists')
    sys.path[:0] = [str(ROOT / 'server'), str(ROOT / 'scripts/benchmarks'), str(BACKEND / 'scripts')]
    base = load('prefill_capture_base', BASE / 'run_rocr_engine_stock8k.py')
    base.io = load('prefill_capture_io', base.IO_PATH); base.lifecycle = load('prefill_capture_lifecycle', base.LIFECYCLE_PATH)
    base.component = load('prefill_capture_identity', base.COMPONENT_PATH)
    base.controller = importlib.import_module('controller'); base.service = importlib.import_module('service')
    base.service.r.configure(); base.PINS = {Path(k): v for k, v in plan['source_pins'].items()}; base.verify()
    from host_frames import frame
    from winjob import OwnedProcess
    base.frame = frame; runtime = base.lifecycle.controller_runtime()
    require(runtime == plan['runtime'], 'Native runtime changed')
    env = base.lifecycle.controller_environment(os.environ, runtime)
    out = work / 'initial'; out.mkdir()
    handle = base.retained_type()(plan['initial']['controller_identity'])
    current = dict(name='original', variant='stock', out=out, profile=Path(plan['profile']),
                   profile_sha256=plan['profile_sha256'], process=handle, handle=handle, stopped=False,
                   controller_run=plan['initial']['controller_run_id'], backend_run=plan['initial']['backend_run_id'],
                   cid=plan['initial']['container_id'])
    done = threading.Event(); guard_errors = []; errors = []; minimum = {}; hold = None
    captured = restored = pending = False

    def guard():
        with (work / 'runtime-memory.jsonl').open('x', encoding='utf-8') as f:
            while not done.is_set():
                try:
                    sample = base.io.reserve(frame, 18)
                    for k in ('available_bytes', 'commit_headroom_bytes'):
                        minimum[k] = min(minimum.get(k, sample[k]), sample[k])
                    f.write(json.dumps(dict(time=time.time(), **sample)) + '\n'); f.flush()
                except BaseException as e:
                    guard_errors.append(type(e).__name__ + ': ' + str(e)); return
                done.wait(.1)

    monitor = threading.Thread(target=guard, daemon=True)

    def check():
        require(monitor.is_alive() and not guard_errors, 'Memory reserve guard failed: ' + str(guard_errors))

    def seal(phase):
        ident = None
        if current.get('process') is not None and current['process'].poll() is None:
            ident = current['handle'].verify()
        change(lambda s: s.update(active_prefill_ht_capture=dict(phase=phase, work=str(work),
                 active_handle=dict(pid=os.getpid(), controller_identity=ident), hardware_owner='/root',
                 original_ready_open=restored, serving_gain_qualified=False)))
        print(json.dumps(dict(phase=phase, work=str(work))), flush=True)

    def stop():
        seal('normal-stop-' + current['name'])
        return base.stop(current, env)

    def start(name, terminal, command=None):
        nonlocal current, hold, pending
        out = work / name; out.mkdir()
        current = dict(name=name, variant='stock', out=out, profile=Path(plan['profile']),
                       profile_sha256=plan['profile_sha256'], stopped=False, restore_terminal=terminal)
        base.lifecycle.stopped_preflight(BACKEND); base.service.r.exclusive_host()
        state = read(ROOT / 'server/.local/current.json'); inner = read(BACKEND / '.local/current-service.json')
        require(state['phase'] in ('stopped', 'failed') and
                all(state.get(k) == terminal['controller'].get(k) for k in ('pid','run_id','profile_sha256')) and
                inner['run_id'] == terminal['backend']['run_id'] and base.lifecycle.recovered(inner) and
                not (BACKEND / '.local/runner.lock').exists(), 'Exact terminal cleanup/restoration link differs')
        try:
            hold = OwnedProcess([r'C:\Windows\System32\wsl.exe', '-d', 'Ubuntu-24.04', '-u', 'revn', '--exec', 'sleep', '1800'],
                                cwd=ROOT, env=os.environ.copy(), stdout_path=out / 'hold.stdout.log', stderr_path=out / 'hold.stderr.log')
        except BaseException as e:
            hold = getattr(e, 'owner', None)
            raise
        hold.resume(); write(out / 'hold-identity.json', hold.verify_live_identity())
        frames = []; stable = None; until = time.monotonic() + 240
        try:
            while time.monotonic() < until:
                check(); hold.verify_live_identity(); sample = base.io.reserve(frame, 18); frames.append(sample)
                good = sample['available_bytes'] >= 44 * 2**30 and sample['commit_headroom_bytes'] >= 131 * 2**30
                stable = (stable if stable is not None else time.monotonic()) if good else None
                if stable is not None and time.monotonic() - stable >= 60: break
                time.sleep(1)
            admitted = stable is not None and time.monotonic() - stable >= 60
            write(out / 'startup-admission.json', dict(admitted=admitted, frames=frames,
                  physical_gib=44, commit_gib=131, stable_seconds=60, deadline_seconds=240))
            require(admitted, 'Unchanged startup admission not met with WSL resident')
            preflight(out / 'gpu-startup.json'); base.verify()
            current['previous_backend_run'] = base.service.read(BACKEND / '.local/current-service.json')['run_id']
            cmd = command or base.lifecycle.controller_command(current['profile'], runtime)
            with (out / 'controller.log').open('x', encoding='utf-8') as log:
                current['process'] = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            current['handle'] = base.retained_type()(base.persistent_identity(current['process'], runtime['executable']))
            seal('observing-same-' + name)
            try:
                state, inner = base.lifecycle.ready(current['process'], current['profile_sha256'],
                                                   current['previous_backend_run'], BACKEND)
            except TimeoutError:
                require(current['process'].poll() is None, 'Launched controller is terminal')
                pending = True; seal('continuing-same-' + name)
                state, inner = base.lifecycle.ready(current['process'], current['profile_sha256'],
                                                   current['previous_backend_run'], BACKEND, deadline_seconds=300)
            pending = False
            current.update(controller_run=state['run_id'], backend_run=inner['run_id'], cid=inner['container_id'], completed=0)
            base.identity(current); check(); seal('ready-' + name)
        finally:
            if hold is not None: hold.close(); hold = None

    try:
        monitor.start(); check(); base.identity(current); seal('admitting-finite-capture')
        health = asyncio.run(base.gateway_idle(current)); current['completed'] = health['completed']
        require(health['cancelled'] == 0, 'Original cancellation counter nonzero')
        base.io.reserve(frame, 22); preflight(out / 'gpu-before-stop.json')
        terminal = stop(); start('capture', terminal, plan['capture_command'])
        state, inner, manifest = base.identity(current)
        require(manifest['prefill_ht_capture']['plan_sha256'] == plan['launch_plan_sha256'], 'Actual capture manifest differs')
        trace = manifest['prefill_ht_capture']['trace_directory']; cid = current['cid']
        trigger = "import os,sys; f=os.open(sys.argv[1]+'/'+sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); d=sys.argv[3].encode(); assert os.write(f,d)==len(d); os.fsync(f);os.close(f)"
        receipt_copy = "import hashlib,os,sys; f=os.open('/candidate/prefill-ht-tensor.receipt',os.O_RDONLY|os.O_NOFOLLOW); d=os.read(f,4097); os.close(f); assert len(d)<=4096 and hashlib.sha256(d).hexdigest()==sys.argv[2]; f=os.open(sys.argv[1]+'/tensor.receipt',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); assert os.write(f,d)==len(d); os.fsync(f);os.close(f)"
        base.service.r.docker('exec', '--user', '0', cid, 'python3', '-c', receipt_copy, trace,
                              manifest['prefill_ht_capture']['receipt']['sha256'], timeout=15)
        base.service.r.docker('exec', '--user', '0', cid, 'python3', '-c', trigger, trace, 'armed', plan['arm_content'], timeout=15)
        seal('single-natural16k-capture-request'); preflight(current['out'] / 'gpu-before-request.json')
        asyncio.run(request(base, current, plan, check, work))
        base.service.r.docker('exec', '--user', '0', cid, 'python3', '-c', trigger, trace, 'harvest', plan['harvest_content'], timeout=15)
        seal('harvesting-single-capture')
        inventory_program = plan['inventory_program']
        text = base.service.r.docker('exec', '--user', '0', cid, 'python3', '-c', inventory_program, trace, timeout=45)
        inventory = json.loads(text); write(work / 'trace-inventory.json', inventory)
        destination = work / 'trace'; destination.mkdir()
        base.service.r.docker('cp', cid + ':' + trace + '/.', base.service.r.linux_path(destination), timeout=60)
        for name, record in inventory['files'].items():
            file = destination / name
            require(file.parent == destination and file.stat().st_size == record['bytes'] and sha(file) == record['sha256'],
                    'Exported fixture differs: ' + name)
        require(set(p.name for p in destination.iterdir()) == set(inventory['files']), 'Exported file set differs')
        captured = True; check(); base.identity(current); stop()
        require(not current.get('stop_contaminated', False), 'Additional request contaminated capture window')
        start('restored-stock', current['terminal']); restored = True
    except BaseException as e:
        errors.append(type(e).__name__ + ': ' + str(e))
    finally:
        try:
            if current.get('process') is not None and not current['stopped'] and current['name'] == 'original':
                base.identity(current); restored = True
            elif not restored and not pending:
                if current.get('process') is not None and not current['stopped']: terminal = stop()
                else:
                    terminal = current.get('terminal') or dict(controller=read(ROOT / 'server/.local/current.json'),
                                      backend=read(BACKEND / '.local/current-service.json'))
                    require(base.lifecycle.recovered(terminal['backend']), 'Terminal cleanup not proved')
                start('restored-after-error', terminal); restored = True
            if restored:
                state, inner, _ = base.identity(current); health = asyncio.run(base.gateway_idle(current))
                identity = current['handle'].verify()
                receipt = work / 'final-ready.json'
                write(receipt, dict(controller=state, backend=inner, health=health, controller_identity=identity,
                                    original_ready_open=True, NPU_integrated=False))
                def save(s):
                    s['current_user_server'].update(phase='ready', controller_pid=state['pid'],
                        controller_run_id=state['run_id'], backend_controller_pid=inner['controller_pid'],
                        backend_run_id=inner['run_id'], container_id=inner['container_id'],
                        controller_identity=identity, restoration_receipt=str(receipt))
                    s['controller_run_id']=state['run_id']; s['service_run_id']=inner['run_id']
                change(save)
        except BaseException as e:
            errors.append('Restore: ' + type(e).__name__ + ': ' + str(e))
            restored = False
            pending = current.get('process') is not None and current['process'].poll() is None
        done.set(); monitor.join(timeout=5)
        if hold is not None:
            try: hold.close(); hold = None
            except BaseException as e: errors.append('Hold cleanup: ' + str(e))
        pending_identity = None
        if not restored and current.get('handle') is not None:
            try:
                if current['process'].poll() is None: pending_identity = current['handle'].verify()
            except BaseException as e: errors.append('Pending identity: ' + str(e))
        pending_receipt = dict(pid=os.getpid(), recovery_pending=pending,
            controller_identity=pending_identity, controller_name=current['name'],
            profile=str(current['profile']), profile_sha256=current['profile_sha256'],
            previous_backend_run=current.get('previous_backend_run'), controller_run=current.get('controller_run'),
            backend_run=current.get('backend_run'), container_id=current.get('cid'),
            command=plan['capture_command'] if current['name']=='capture' else base.lifecycle.controller_command(current['profile'],runtime),
            current_controller=read(ROOT / 'server/.local/current.json'),
            current_backend=read(BACKEND / '.local/current-service.json'))
        if current.get('handle') is not None:
            try: current['handle'].close()
            except BaseException as e: errors.append('Read-only handle cleanup: ' + str(e))
        result = dict(captured=captured, original_ready_open=restored, recovery_pending=pending,
                      errors=errors, guard_errors=guard_errors, minimum_memory=minimum,
                      pending_controller=None if restored else pending_receipt,
                      serving_rates_qualified=False, passed=captured and restored and not errors and not guard_errors)
        write(work / 'result.json', result)
        change(lambda s: s['active_prefill_ht_capture'].update(
            phase='terminal-original-ready' if restored else 'restoration-observation-pending',
            active_handle=None if restored else pending_receipt,
            original_ready_open=restored, result=str(work / 'result.json')))
    print(json.dumps(dict(work=str(work), **result)), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
