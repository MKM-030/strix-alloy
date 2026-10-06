"""Root-only frozen Prefill component replay; always restore stock open.

Use an independently reviewed sealed plan. No inference request or serving
rate claim is made. Observation timeouts continue the same live process.
"""
import argparse
import asyncio
import datetime
import hashlib
import math
import re
import importlib
import importlib.util
import json
import os
from pathlib import Path
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


def state_sharing_error(error):
    return (isinstance(error, PermissionError) and os.name == 'nt' and
            (getattr(error, 'winerror', None) in (5,32,33) or error.errno == 13) and
            error.filename is not None and Path(error.filename).resolve() in (
                (ROOT / 'server/.local/current.json').resolve(),
                (BACKEND / '.local/current-service.json').resolve()))


def sha(p):
    with Path(p).open('rb') as f:
        before = os.fstat(f.fileno())
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
        after = os.fstat(f.fileno())
    fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    require(tuple(getattr(before,k) for k in fields) == tuple(getattr(after,k) for k in fields),
            'File changed during streaming hash: ' + str(p))
    return digest


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
    temp = p.with_name('continuation-prefill-replay-' + uuid.uuid4().hex + '.tmp')
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
    require(not value['gpu'], 'GPU activity above2% before replay')


OUTPUT_LIMITS = {'activation.json': 2048, 'replay.receipt': 2048, 'armed': 64,
                 'replay.json': 32768, 'complete.json': 256}
POLL_PROGRAM = r"""import json,os,pathlib,re,stat,sys
p=pathlib.Path(sys.argv[1]);assert re.fullmatch('/tmp/alloy-prefill-ht-replay-[0-9a-f]{32}',str(p))
s=p.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and s.st_mode&0o777==0o700
q=p/'complete.json'
try:
 fd=os.open(q,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
except FileNotFoundError:print('{"complete":false}')
else:
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and s.st_mode&0o777==0o600 and 0<=s.st_size<=256
  d=f.read(257);after=os.fstat(f.fileno());assert len(d)<=256
 status=dict(complete=False)
 if len(d)==s.st_size and (s.st_size,s.st_mtime_ns,s.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
  try:v=json.loads(d)
  except json.JSONDecodeError:pass
  else:
   assert v['schema']==1 and v['token_rate_claim'] is False
   status=dict(complete=True,result=v)
 print(json.dumps(status))
"""
INVENTORY_PROGRAM = r"""import hashlib,json,os,pathlib,re,stat,sys
p=pathlib.Path(sys.argv[1]);assert re.fullmatch('/tmp/alloy-prefill-ht-replay-[0-9a-f]{32}',str(p))
s=p.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and s.st_mode&0o777==0o700
limits={'activation.json':2048,'replay.receipt':2048,'armed':64,'replay.json':32768,'complete.json':256}
rows={};total=0;fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
for q in p.iterdir():
 s=q.lstat();assert q.name in limits and stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and s.st_mode&0o777==0o600 and 0<s.st_size<=limits[q.name]
 fd=os.open(q,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());digest=hashlib.file_digest(f,'sha256').hexdigest();b=os.fstat(f.fileno())
 assert len({tuple(getattr(x,k) for k in fields) for x in (s,a,b)})==1
 total+=s.st_size;assert total<=65536;rows[q.name]=dict(bytes=s.st_size,sha256=digest)
assert set(rows)==set(limits)
print(json.dumps(dict(files=rows,bytes=total,file_count=len(rows))))
"""


def validate_replay(directory, receipt_sha, y_sha):
    activation = read(directory / 'activation.json'); complete = read(directory / 'complete.json')
    result = read(directory / 'replay.json')
    require(activation['mode'] == result['mode'] == 'ordinary-qkv8192-replay-v1' and
            activation['manifest_sha256'] == result['manifest_sha256'] == receipt_sha and
            activation['run_limit'] == 43 and activation['constructor_hardware_calls'] == 0 and
            activation['host_hooks'] == 0 and activation['recapture'] is False,
            'Replay activation/manifest scope differs')
    require(result['passed'] is True and complete['passed'] is True and complete['token_rate_claim'] is False and
            result['raw_y_contract'] == 'exact-native16-bit-words' and
            result['measurement'] == 'cpu-submission-to-full-device-completion-wall' and
            result['stock_pipeline'] == 'original-preparation-plus-library' and
            result['native_pipeline'] == 'original-rotation-plus-packed-multiply' and
            result['cached_pipeline'] == 'original-prepared-weight-resident-plus-library' and
            result['token_rate_claim'] is False and result['acceptance_claim'] is False and
            result['gpu_busy_time_claim'] is False and result['serving_substitution'] is False and
            result['tolerance_widened'] is False and result['keep_trunk'] is False and
            result['ht_threshold_changed'] is False and result['error'] is None and
            result['cleanup_errors'] == 0 and result['own_device_allocations'] == result['own_device_frees'] == 7 and
            result['cached_preparations_excluded'] == 1 and result['cached_weight_resident_bytes'] == 52428800 and
            result['engine_sha256'] == activation['engine_sha256'] ==
            'ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b' and
            (result['M'],result['N'],result['K'],result['descriptor_mode']) == (8192,10240,2560,4),
            'Replay completion/exact-contract/owned cleanup differs')
    runs = result['runs']; comparisons = result['comparisons']
    require(3 <= len(runs) <= 43 and complete['runs'] == len(runs) and
            len(comparisons) == 2 and
            [x['candidate'] for x in comparisons] == ['native-ht','cached-original'],
            'Finite replay schedule differs')
    for i, row in enumerate(runs):
        require(row['index'] == i and row['arm'] in ('stock','native-ht','cached-original') and
                type(row['wall_ns']) is int and row['wall_ns'] >= 0 and
                type(row['word_mismatches']) is int and row['word_mismatches'] >= 0,
                'Run identity/timing differs')
        if row['exact']:
            require(row['completed'] is True and row['word_mismatches'] == 0 and
                    row['output_sha256'] == y_sha and row['wall_ns'] > 0, 'Exact run differs')
        elif row['completed']:
            require(row['word_mismatches'] > 0 and row['wall_ns'] > 0, 'Retired raw-output record differs')
        else:
            require(row['arm'] == 'native-ht' and row['wall_ns'] == 0, 'Incomplete non-native run')
    require(runs[0]['arm'] == 'stock' and runs[0]['cohort'] == runs[0]['phase'] == runs[0]['pair'] == 0 and
            runs[0]['exact'] is True, 'Stock qualification missing')
    require([(x['arm'],x['cohort'],x['phase'],x['pair']) for x in runs[1:3]] ==
            [('native-ht',1,0,0),('cached-original',2,0,0)], 'Qualification schedule differs')
    position = 3
    for cohort, comparison in enumerate(comparisons,1):
        name = comparison['candidate']; block = []
        while position < len(runs) and runs[position]['cohort'] == cohort:
            block.append(runs[position]); position += 1
        schedule = []
        for phase, pairs in ((1,2),(2,8)):
            for pair in range(pairs):
                order = (name,'stock') if pair & 1 else ('stock',name)
                schedule.extend((arm,cohort,phase,pair) for arm in order)
        require([(r['arm'],r['cohort'],r['phase'],r['pair']) for r in block] == schedule[:len(block)],
                'Balanced complete-pipeline order differs')
        measured = [r for r in block if r['phase'] == 2 and r['completed'] and r['exact']]
        stock = [r for r in measured if r['arm'] == 'stock']
        candidate = [r for r in measured if r['arm'] == name]
        require(comparison['stock_count'] == len(stock) and comparison['candidate_count'] == len(candidate),
                'Measured complete/exact counts differ')
        if comparison['qualified']:
            require(comparison['retired'] is False and comparison['error'] is None and
                    runs[cohort]['exact'] is True and len(block) == 20 and all(r['exact'] for r in block) and
                    comparison['warmup_pairs'] == 2 and comparison['measured_pairs'] == 8 and
                    len(stock) == len(candidate) == 8, 'Qualified candidate cohort incomplete')
            for key, rows in (('stock_mean_wall_ms',stock),('candidate_mean_wall_ms',candidate)):
                mean = sum(r['wall_ns'] for r in rows) / len(rows) / 1e6
                require(isinstance(comparison[key],(int,float)) and math.isfinite(comparison[key]) and
                        abs(comparison[key] - mean) <= 1e-8, 'Component wall mean differs')
        else:
            require(comparison['retired'] is True and comparison['error'] in
                    ('native-ht-declined','native-raw-y-mismatch','cached-original-raw-y-mismatch') and
                    comparison['stock_mean_wall_ms'] is None and comparison['candidate_mean_wall_ms'] is None,
                    'Retired candidate has usable timing')
            terminal = block[-1] if block else runs[cohort]
            require(terminal['arm'] == name and terminal['exact'] is False and
                    all(r['exact'] for r in block[:-1]), 'Retired candidate continued execution')
            require(not block or runs[cohort]['exact'] is True,
                    'Retired qualification entered warmup/timing')
    require(position == len(runs), 'Unexpected replay cohort')
    return result


def wait_replay(base, cell, check, trace, work, seal, threshold):
    began = time.monotonic(); observation_reported = False
    while True:
        check(); base.identity(cell)
        reply = base.service.r.docker('exec','--user','0',cell['cid'],'python3','-c',
                                     POLL_PROGRAM,trace,timeout=15)
        require(len(reply) <= 2048, 'Replay poll budget exceeded')
        status = json.loads(reply)
        if status['complete']:
            write(work / 'worker-complete.json',status)
            return
        if not observation_reported and time.monotonic() - began >= threshold:
            observation_reported = True
            seal('continuing-same-finite-replay-worker')
        time.sleep(.25)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--source-sha256', required=True)
    a = p.parse_args(); require(os.name == 'nt' and not sys.flags.optimize, 'Local unoptimized Python required')
    require(sha(__file__) == a.source_sha256 and sha(a.plan) == a.plan_sha256, 'Coordinator/plan seal changed')
    plan = read(a.plan); require(plan['schema'] == 'halogen.prefill-ht.owned-replay.v1', 'Wrong plan')
    work = Path(plan['work']); require(not (work / 'result.json').exists(), 'Replay already terminal')
    for path, digest in plan['source_pins'].items(): require(sha(path) == digest, 'Pinned source changed: ' + path)
    replay_launcher = load('prefill_replay_launcher', Path(__file__).with_name('replay_launcher.py'))
    launch_plan = replay_launcher.load_plan(plan['launch_plan'], plan['launch_plan_sha256'])
    require(plan['profile_sha256'] == launch_plan['profile_sha256'] and plan['profile'] == launch_plan['profile'] and
            plan['runtime'] == launch_plan['runtime'] and plan['arm_content'] == replay_launcher.ARM_CONTENT and
            type(plan['worker_observation_seconds']) is int and 1 <= plan['worker_observation_seconds'] <= 300 and
            plan['leave_original_open'] is True and plan['serving_gain_claim'] is False,
            'Owned replay/launch plan scope differs')
    saved = read(BASE / 'continuation-current.json')
    require(not saved['active_engine_sessions'] and not saved['active_optimization_children'] and
            not any(isinstance(v, dict) and v.get('active_handle') is not None for v in saved.values()),
            'Another hardware/lifecycle handle exists')
    sys.path[:0] = [str(ROOT / 'server'), str(ROOT / 'scripts/benchmarks'), str(BACKEND / 'scripts')]
    base = load('prefill_replay_base', BASE / 'run_rocr_engine_stock8k.py')
    base.io = load('prefill_replay_io', base.IO_PATH); base.lifecycle = load('prefill_replay_lifecycle', base.LIFECYCLE_PATH)
    base.component = load('prefill_replay_identity', base.COMPONENT_PATH)
    base.controller = importlib.import_module('controller'); base.service = importlib.import_module('service')
    base.service.r.configure(); base.PINS = {Path(k): v for k, v in plan['source_pins'].items()}; base.verify()
    # This private observer uses the normal controller's bounded Windows
    # sharing-error reader. Global lifecycle and production files stay pinned.
    base.lifecycle.read = base.controller.read
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
    replayed = restored = pending = False

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
        change(lambda s: s.update(active_prefill_ht_replay=dict(phase=phase, work=str(work),
                 active_handle=dict(pid=os.getpid(), controller_identity=ident), hardware_owner='/root',
                 original_ready_open=restored, serving_gain_qualified=False)))
        print(json.dumps(dict(phase=phase, work=str(work))), flush=True)

    def stop():
        seal('normal-stop-' + current['name'])
        return base.stop(current, env)

    def start(name, terminal, command=None, *, restoration_only=False):
        nonlocal current, hold, pending
        out = work / name; out.mkdir()
        current = dict(name=name, variant='stock', out=out, profile=Path(plan['profile']),
                       profile_sha256=plan['profile_sha256'], stopped=False, restore_terminal=terminal)
        # Match the existing normal lifecycle's restoration-only contract:
        # a failed terminal is admissible only with the exact identities and
        # proved cleanup/recovery below. Measurement launches remain strict.
        if not restoration_only:
            base.lifecycle.stopped_preflight(BACKEND)
        base.service.r.exclusive_host()
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
            except (TimeoutError, PermissionError) as observation_error:
                if isinstance(observation_error, PermissionError):
                    require(state_sharing_error(observation_error),
                            'Unclassified readiness access error')
                require(current['process'].poll() is None, 'Launched controller is terminal')
                current['handle'].verify(); check()
                pending = True; seal('continuing-same-' + name)
                state, inner = base.lifecycle.ready(current['process'], current['profile_sha256'],
                                                   current['previous_backend_run'], BACKEND, deadline_seconds=300)
            pending = False
            current.update(controller_run=state['run_id'], backend_run=inner['run_id'], cid=inner['container_id'], completed=0)
            base.identity(current); check(); seal('ready-' + name)
        finally:
            if hold is not None: hold.close(); hold = None

    try:
        monitor.start(); check(); base.identity(current); seal('admitting-finite-replay')
        health = asyncio.run(base.gateway_idle(current)); current['completed'] = health['completed']
        require(health['cancelled'] == 0, 'Original cancellation counter nonzero')
        base.io.reserve(frame, 22); preflight(out / 'gpu-before-stop.json')
        terminal = stop(); start('replay', terminal, plan['replay_command'])
        state, inner, manifest = base.identity(current)
        binding = manifest['prefill_ht_replay']
        require(binding['plan_sha256'] == plan['launch_plan_sha256'] and
                binding['receipt'] == launch_plan['receipt'] and
                binding['fixture_files'] == launch_plan['fixture_files'] and binding['run_limit'] == 43 and
                binding['inference_gateway_blocked'] is True,
                'Actual replay manifest differs')
        trace = binding['trace_directory']; cid = current['cid']
        require(re.fullmatch('/tmp/alloy-prefill-ht-replay-[0-9a-f]{32}',trace), 'Invalid owned replay directory')
        health = asyncio.run(base.gateway_idle(current))
        require(health['completed'] == health['cancelled'] == 0, 'Replay engine already used')
        current['completed'] = 0; check(); base.io.reserve(frame,22)
        preflight(current['out'] / 'gpu-before-arm.json')
        receipt_copy = "import hashlib,os,sys; f=os.open('/candidate/prefill-ht-replay.receipt',os.O_RDONLY|os.O_NOFOLLOW); d=os.read(f,2049); os.close(f); assert len(d)<=2048 and hashlib.sha256(d).hexdigest()==sys.argv[2]; f=os.open(sys.argv[1]+'/replay.receipt',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); assert os.write(f,d)==len(d); os.fsync(f);os.close(f)"
        trigger = "import os,sys; f=os.open(sys.argv[1]+'/armed',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); d=sys.argv[2].encode('ascii'); assert os.write(f,d)==len(d);os.fsync(f);os.close(f)"
        base.service.r.docker('exec','--user','0',cid,'python3','-c',receipt_copy,trace,
                              binding['receipt']['sha256'],timeout=15)
        check(); base.identity(current); base.io.reserve(frame,22)
        health = asyncio.run(base.gateway_idle(current))
        require(health['completed'] == health['cancelled'] == 0, 'Concurrent request before arm')
        base.service.r.docker('exec','--user','0',cid,'python3','-c',trigger,trace,plan['arm_content'],timeout=15)
        seal('finite-three-arm-replay-worker')
        wait_replay(base,current,check,trace,work,seal,plan['worker_observation_seconds'])
        seal('exporting-small-replay-result')
        text = base.service.r.docker('exec','--user','0',cid,'python3','-c',INVENTORY_PROGRAM,trace,timeout=15)
        require(len(text)<=8192,'Replay inventory budget exceeded')
        inventory=json.loads(text);write(work/'replay-inventory.json',inventory)
        require(set(inventory['files']) == set(OUTPUT_LIMITS) and inventory['bytes'] <= 65536,
                'Unexpected replay export set')
        destination=work/'replay-results';destination.mkdir()
        for name,record in inventory['files'].items():
            require(name in OUTPUT_LIMITS and 0<record['bytes']<=OUTPUT_LIMITS[name],'Large replay export refused')
            base.service.r.docker('cp',cid+':'+trace+'/'+name,base.service.r.linux_path(destination/name),timeout=15)
            file=destination/name
            require(file.stat().st_size==record['bytes'] and sha(file)==record['sha256'],'Exported replay result differs')
        require((destination/'armed').read_bytes()==plan['arm_content'].encode('ascii') and
                sha(destination/'replay.receipt')==binding['receipt']['sha256'],'Exported arm/receipt differs')
        component=validate_replay(destination,binding['receipt']['sha256'],
                                  launch_plan['fixture_files']['y-reference-u16.bin']['sha256'])
        write(work/'component-validation.json',dict(passed=True,qualified_candidates=[
              row['candidate'] for row in component['comparisons'] if row['qualified']],
              token_rate_claim=False,acceptance_claim=False))
        replayed = True; check(); base.identity(current)
        health=asyncio.run(base.gateway_idle(current))
        require(health['completed']==health['cancelled']==0,'Inference contaminated component window')
        stop()
        require(not current.get('stop_contaminated',False),'Additional request contaminated replay window')
        start('restored-stock', current['terminal'], restoration_only=True); restored = True
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
                start('restored-after-error', terminal, restoration_only=True); restored = True
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
        state_observation_errors = []
        def optional_state_snapshot(path):
            try:
                return base.controller.read(path)
            except PermissionError as snapshot_error:
                require(state_sharing_error(snapshot_error), 'Unclassified pending-state access error')
                state_observation_errors.append(dict(path=str(path), error=str(snapshot_error),
                                                     observation_unavailable=True))
                return None
        pending_receipt = dict(pid=os.getpid(), recovery_pending=pending,
            controller_identity=pending_identity, controller_name=current['name'],
            profile=str(current['profile']), profile_sha256=current['profile_sha256'],
            previous_backend_run=current.get('previous_backend_run'), controller_run=current.get('controller_run'),
            backend_run=current.get('backend_run'), container_id=current.get('cid'),
            command=plan['replay_command'] if current['name']=='replay' else base.lifecycle.controller_command(current['profile'],runtime),
            current_controller=optional_state_snapshot(ROOT / 'server/.local/current.json'),
            current_backend=optional_state_snapshot(BACKEND / '.local/current-service.json'),
            state_observation_errors=state_observation_errors)
        if current.get('handle') is not None:
            try: current['handle'].close()
            except BaseException as e: errors.append('Read-only handle cleanup: ' + str(e))
        result = dict(replayed=replayed, original_ready_open=restored, recovery_pending=pending,
                      errors=errors, guard_errors=guard_errors, minimum_memory=minimum,
                      pending_controller=None if restored else pending_receipt,
                      serving_rates_qualified=False, passed=replayed and restored and not errors and not guard_errors)
        write(work / 'result.json', result)
        change(lambda s: s['active_prefill_ht_replay'].update(
            phase='terminal-original-ready' if restored else 'restoration-observation-pending',
            active_handle=None if restored else pending_receipt,
            original_ready_open=restored, result=str(work / 'result.json')))
    print(json.dumps(dict(work=str(work), **result)), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
