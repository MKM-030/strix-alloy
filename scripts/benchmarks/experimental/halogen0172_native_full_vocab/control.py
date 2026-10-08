"""Normal, identity-checked stop/checkpoint of the frozen comparison; no inference."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import uuid

BASE = Path(__file__).resolve().parent.parent
REPO = BASE.parents[3]
STATE = BASE.parent / 'continuation-current.json'
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / 'server'))
from controller import atomic, read

spec = importlib.util.spec_from_file_location('identity_readonly',
    BASE.parent / 'halogen0171-backend-preparation-20261007/checkpoint_actual_handles.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def health(profile):
    token = Path(profile['token_file']).read_text(encoding='ascii').strip()
    request = urllib.request.Request('http://127.0.0.1:8840/health',
        headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stop', 'checkpoint'])
    parser.add_argument('profile', type=Path)
    parser.add_argument('window')
    parser.add_argument('--engine-session', type=int)
    args = parser.parse_args()
    import hashlib
    profile_bytes = args.profile.read_bytes()
    profile = json.loads(profile_bytes.decode('utf-8-sig'))
    profile_sha = hashlib.sha256(profile_bytes).hexdigest()
    package = (REPO / profile['engine']['directory']).resolve()
    require(package.is_relative_to(REPO / 'backends'), 'Backend scope differs')
    current = read(REPO / 'server/.local/current.json')
    inner = read(package / '.local/current-service.json')
    require(current['profile_sha256'] == profile_sha, 'Current profile differs')
    controller_identity = helper.identity(current['pid'])
    backend_identity = helper.identity(inner['controller_pid'])
    require(controller_identity is not None and backend_identity is not None,
        'Actual current process handles missing')
    require(current['phase'] == inner['phase'] == 'ready', 'Current engine is not ready')
    require(0 <= time.time() - current['heartbeat'] <= 10, 'Controller heartbeat stale')
    require(current['context'] == inner['context'] == 262144, 'Context differs')
    checked_health = health(profile)
    require(checked_health['status'] == 'ok' and checked_health['active_requests'] == 0
        and not checked_health['draining'], 'Gateway is active or unavailable')
    state = read(STATE)
    if args.window == 'original':
        expected = state['current_user_server']
        require(controller_identity == expected['controller_identity']
            and backend_identity == expected['backend_identity']
            and current['run_id'] == expected['controller_run_id']
            and inner['run_id'] == expected['backend_run_id'], 'Original ownership differs')
    record = dict(utc=datetime.now(timezone.utc).isoformat(), action=args.action, window=args.window,
        controller=current, backend=inner, identities=dict(controller=controller_identity, backend=backend_identity),
        profile_sha256=profile_sha, health=checked_health, engine_session=args.engine_session,
        original_ready_open=args.window == 'original', inferred_gain=False)
    receipt = WORK / ('control-' + args.action + '-' + uuid.uuid4().hex + '.json')
    atomic(receipt, record)
    if args.action == 'checkpoint':
        state['active_engine_sessions'] = [dict(role=args.window, version=package.name.removeprefix('halogen-wsl2-'),
            phase='ready', controller=dict(pid=current['pid'], run_id=current['run_id'], identity=controller_identity),
            backend=dict(pid=inner['controller_pid'], run_id=inner['run_id'], identity=backend_identity),
            tool_session_id=args.engine_session)]
        state['active_session'] = dict(role=args.window, engine_session_id=args.engine_session,
            controller_pid=current['pid'], controller_run_id=current['run_id'],
            backend_pid=inner['controller_pid'], backend_run_id=inner['run_id'])
        state['active0172_native_full_vocab_comparison'] = dict(phase='ready-' + args.window,
            receipt=str(receipt), engine_session_id=args.engine_session, benchmark_session_id=None)
        state['current_user_server'].update(phase='comparison-' + args.window,
            original_ready_open=args.window == 'original')
        state['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
        atomic(STATE, state)
        print(json.dumps(dict(window=args.window, phase='ready', receipt=str(receipt),
            controller_pid=current['pid'], backend_pid=inner['controller_pid'])))
        return 0
    atomic(REPO / 'server/.local/stop.json', dict(run_id=current['run_id']))
    print(json.dumps(dict(window=args.window, phase='normal-stop-requested',
        controller_pid=current['pid'], backend_pid=inner['controller_pid'])), flush=True)
    while True:
        latest = read(REPO / 'server/.local/current.json')
        require(latest['run_id'] == current['run_id'], 'Another controller replaced the stop target')
        try:
            actual = helper.identity(current['pid'])
        except OSError as exc:
            if exc.winerror != 31:
                raise
            # QueryFullProcessImageName may race the normal process exit.
            # Observe again; this neither marks it closed nor restarts it.
            time.sleep(.1)
            continue
        if actual is not None:
            require(actual == controller_identity, 'Stop target PID reused')
        if latest['phase'] in ('stopped', 'failed') and actual is None:
            final_inner = read(package / '.local/current-service.json')
            require(final_inner['run_id'] == inner['run_id'], 'Backend ownership changed')
            try:
                final_backend_identity = helper.identity(inner['controller_pid'])
            except OSError as exc:
                if exc.winerror != 31:
                    raise
                time.sleep(.1)
                continue
            if final_backend_identity is not None:
                require(final_backend_identity == backend_identity, 'Backend PID reused')
                time.sleep(.1)
                continue
            outcome = read(Path(final_inner['attempt']) / 'outcome.json')
            require(outcome['cleanup'] and outcome['recovery'], 'Normal cleanup/recovery incomplete')
            record.update(phase='terminal-normal-stop', final_controller=latest,
                final_backend=final_inner, outcome=outcome, own_handles_closed=True)
            atomic(receipt, record)
            state = read(STATE)
            state['active_engine_sessions'] = []
            state['active_session'] = None
            state['current_user_server'].update(phase='stopped-for0172-comparison', original_ready_open=False)
            state['active0172_native_full_vocab_comparison'] = dict(phase='stopped-' + args.window, receipt=str(receipt))
            state['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
            atomic(STATE, state)
            print(json.dumps(dict(window=args.window, phase=record['phase'], receipt=str(receipt))), flush=True)
            return 0
        time.sleep(1)

if __name__ == '__main__':
    raise SystemExit(main())
