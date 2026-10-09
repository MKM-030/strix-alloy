"""Restore and seal the normal 0.17.2 server in the requested visible console."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

WORK = Path(__file__).resolve().parent
PREP = WORK.parent
ROOT = PREP.parents[3]
STATE = PREP.parent / 'continuation-current.json'
PROFILE = PREP / 'servicenow-thinking-defaults-20261008/thinking-latest-profile.json'
PROFILE_SHA = 'b5d3692b2623034f5a9c4a5f90b234ba6b792793196963fc0e7b474b3937c839'
LAUNCHER = PREP / 'ple0172-native-worker-detour-v1/native_worker_launcher_0172.py'
LAUNCHER_SHA = '93076e4e9451d5881900ea86ebb90c0abf10c963823f4c7584315f4af62f78a7'
LAUNCH = WORK / 'final-visible-stock-launch.json'
sys.path.insert(0, str(ROOT / 'server'))
from controller import atomic, read
spec = importlib.util.spec_from_file_location('actual_identity',
    PREP.parent / 'halogen0171-backend-preparation-20261007/checkpoint_actual_handles.py')
identity_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity_module)

def launch():
    current = read(ROOT / 'server/.local/current.json')
    assert current['phase'] in ('stopped', 'failed')
    assert identity_module.identity(current['pid']) is None
    assert not LAUNCH.exists(), 'Continue the existing visible launch; do not duplicate it'
    assert hashlib.sha256(PROFILE.read_bytes()).hexdigest() == PROFILE_SHA
    assert hashlib.sha256(LAUNCHER.read_bytes()).hexdigest() == LAUNCHER_SHA
    python = ROOT / 'server/.local/venv/Scripts/python.exe'
    text = "& '" + str(python) + "' -B -u '" + str(LAUNCHER) + "' --launcher-sha256 " + LAUNCHER_SHA + " --mode stock --run"
    command = [r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
        '-NoProfile', '-NoExit', '-Command', text]
    process = subprocess.Popen(command, cwd=str(ROOT), close_fds=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE)
    console = identity_module.identity(process.pid)
    assert console and console['executable'].lower().endswith('\\powershell.exe')
    atomic(LAUNCH, dict(utc=datetime.now(timezone.utc).isoformat(), console_identity=console,
        command=command, profile_sha256=PROFILE_SHA, launcher_sha256=LAUNCHER_SHA))
    print(json.dumps(dict(console_pid=process.pid, receipt=str(LAUNCH))), flush=True)

def checkpoint():
    current = read(ROOT / 'server/.local/current.json')
    backend = read(ROOT / 'backends/halogen-wsl2-0.17.2/.local/current-service.json')
    assert current['phase'] == backend['phase'] == 'ready'
    assert current['context'] == backend['context'] == 262144
    assert 0 <= time.time() - current['heartbeat'] <= 15
    assert hashlib.sha256(PROFILE.read_bytes()).hexdigest() == current['profile_sha256'] == PROFILE_SHA
    saved_launch = read(LAUNCH)
    identities = dict(controller=identity_module.identity(current['pid']),
        backend=identity_module.identity(backend['controller_pid']),
        console=identity_module.identity(saved_launch['console_identity']['pid']))
    assert identities['controller'] and identities['backend']
    assert identities['console'] == saved_launch['console_identity']
    profile = read(PROFILE)
    token = Path(profile['token_file']).read_text(encoding='ascii').strip()
    request = urllib.request.Request('http://127.0.0.1:8840/health',
        headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=10) as response:
        health = json.load(response)
        assert response.status == 200 and health['status'] == 'ok'
    assert health['active_requests'] == 0 and not health['draining']
    manifest = read(Path(backend['attempt']) / 'manifest.json')
    assert '_hg_flash_serve' not in manifest['environment']
    assert not any(key.startswith('HG0172_') for key in manifest['environment'])
    assert 'libhalogen0172-host-census.so' not in manifest['environment']['LD_PRELOAD']
    assert 'libhalogen0172-gpu-events.so' not in manifest['environment']['LD_PRELOAD']
    assert not any(k.startswith('PLE0172_') for k in manifest['environment'])
    assert 'libple0172_native_worker_page_order.so' not in manifest['environment']['LD_PRELOAD']
    utc = datetime.now(timezone.utc).isoformat()
    receipt = WORK / 'final-ready-open.json'
    atomic(receipt, dict(utc=utc, version='0.17.2', controller=current, backend=backend,
        identities=identities, health=health, profile_sha256=PROFILE_SHA,
        candidate_removed=True, ready_open=True, inference_performed=False))
    state = read(STATE)
    state['current_user_server'].update(phase='ready', version='0.17.2',
        controller_pid=current['pid'], controller_run_id=current['run_id'],
        backend_controller_pid=backend['controller_pid'], backend_run_id=backend['run_id'],
        controller_identity=identities['controller'], backend_identity=identities['backend'],
        foreground_console_identity=identities['console'], container_id=backend['container_id'],
        profile=str(PROFILE), profile_sha256=PROFILE_SHA, original_ready_open=True,
        latest_ready_open=True, console_trace=True, latest_verified_utc=utc,
        latest_verification=str(receipt), npu_integrated=False, api_defaults=profile['engine']['api_defaults'])
    state['active_engine_sessions'] = [dict(role='latest0172-ready-open', version='0.17.2',
        phase='ready', controller=dict(pid=current['pid'], run_id=current['run_id'], identity=identities['controller']),
        backend=dict(pid=backend['controller_pid'], run_id=backend['run_id'], identity=identities['backend']),
        console_identity=identities['console'], tool_session_id=None)]
    state['active_session'] = dict(role='latest0172-ready-open', engine_session_id=None,
        benchmark_session_id=None, controller_pid=current['pid'], controller_run_id=current['run_id'],
        backend_pid=backend['controller_pid'], backend_run_id=backend['run_id'])
    state['active0172_hc6_registration_comparison'].update(phase='after-completed-stock-ready-open',
        engine_session_id=None, benchmark_session_id=None, final_receipt=str(receipt),
        latest_ready_open=True, full_goal_completed=False)
    state['active_optimization_children'] = []
    state.update(timestamp_utc=utc, controller_run_id=current['run_id'], service_run_id=backend['run_id'],
        pending_user_input=None, full_goal_completed=False)
    atomic(STATE, state)
    print(json.dumps(dict(version='0.17.2', ready_open=True, controller_pid=current['pid'],
        backend_pid=backend['controller_pid'], console_pid=identities['console']['pid'], receipt=str(receipt))))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['launch', 'checkpoint'])
    {'launch': launch, 'checkpoint': checkpoint}[parser.parse_args().action]()
