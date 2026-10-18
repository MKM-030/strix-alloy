"""Start the installed native voice services; never stop, restart or order."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'runtime'
NATIVE = ROOT / 'voice/native-bridge'
PYTHON = NATIVE / '.venv/Scripts/python.exe'
BOT_CONFIG = ROOT / 'voice/bridge.local.json'
NATIVE_CONFIG = NATIVE / 'config.local.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def listeners(port):
    return [c for c in psutil.net_connections(kind='tcp')
            if c.status == psutil.CONN_LISTEN and c.laddr.port == port]


def process_args(pid):
    return psutil.Process(pid).cmdline()


def python_base(executable):
    config = Path(executable).parents[1] / 'pyvenv.cfg'
    for line in config.read_text(encoding='utf-8').splitlines():
        if line.startswith('home = '):
            return str(Path(line[7:]) / 'python.exe')
    raise RuntimeError('Native venv has no verified base Python path')


def owned_listener(port, args):
    sockets = listeners(port)
    if not sockets:
        return None
    owners = {c.pid for c in sockets}
    if len(owners) != 1 or any(c.laddr.ip != '127.0.0.1' for c in sockets):
        raise RuntimeError(f'Port {port}: foreign or non-loopback listener; no process changed')
    pid = owners.pop()
    actual = process_args(pid)
    accepted_exes = {os.path.normcase(args[0])}
    if os.path.normcase(args[0]) == os.path.normcase(str(PYTHON)):
        accepted_exes.add(os.path.normcase(python_base(args[0])))
    elif (Path(args[0]).parent.parent / 'pyvenv.cfg').is_file():
        accepted_exes.add(os.path.normcase(python_base(args[0])))
    if not actual or os.path.normcase(actual[0]) not in accepted_exes or actual[1:] != args[1:]:
        raise RuntimeError(f'Port {port}: command differs from intended service; no process changed')
    if os.path.normcase(psutil.Process(pid).exe()) not in accepted_exes:
        raise RuntimeError(f'Port {port}: executable identity differs')
    return pid


@contextmanager
def startup_lock():
    # OS lock is released on exit/crash; no retained model ownership lock is touched.
    import msvcrt
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / 'startup.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Another SCC startup window is active; wait for its result') from None
        try:
            yield
        finally:
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def powershell(script, *args):
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(script), *args], cwd=ROOT, check=True)


def speech_start(selected):
    speech = module('scc_speech_start', ROOT / 'voice/native-speech-validation/speech_probe.py')
    # Reuse its existing PID/create-time/executable/argv checks and ownership file.
    speech.SERVICES = {name: value for name, value in speech.SERVICES.items() if name in selected}
    speech.start()
    if 'tts' in selected:
        manager = module('scc_voice_profiles', ROOT / 'voice/voice-profile/manage_voice.py')
        # The same activation lock protects recorder updates and startup restore.
        # Invalid consent/hash fails closed; do not silently replace an own voice.
        with manager.activation_lock(manager.PROFILE_ROOT):
            profile = manager.selected_profile()
            if profile is None:
                raise RuntimeError('No validated German voice reference is available')
            owner = speech.owners()['tts']
            receipt = RUNTIME / 'registered-voice.json'
            stamp = {'pid':owner['pid'], 'created':owner['created'],
                     'reference_sha256':profile['reference_sha256']}
            if receipt.exists() and json.loads(receipt.read_text()) == stamp:
                print('TTS: existing owned voice registration reused', flush=True)
            else:
                manager.native_register(profile)
                manager.atomic_json(receipt, stamp)
                print('TTS: selected German voice registered: ' + profile['name'], flush=True)


def start_python(name, ports, script, config, health):
    args = [str(PYTHON), '-u', str(script), '--config', str(config)]
    pids = [owned_listener(port, args) for port in ports]
    if any(pids) and (not all(pids) or len(set(pids)) != 1):
        raise RuntimeError(f'{name}: incomplete listener set; inspect logs, no restart attempted')
    if not any(pids):
        for path in (PYTHON, script, config):
            if not path.is_file():
                raise FileNotFoundError(path)
        with (RUNTIME / f'{name}.stdout.log').open('ab') as stdout, (RUNTIME / f'{name}.stderr.log').open('ab') as stderr:
            child = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        print(f'{name}: loading (launcher PID {child.pid})', flush=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        pids = [owned_listener(port, args) for port in ports]
        if all(pids) and len(set(pids)) == 1:
            info = health()
            if info.get('http_status') != 200:
                raise RuntimeError(f'{name}: health failed; inspect {RUNTIME}')
            process = psutil.Process(pids[0])
            (RUNTIME / f'{name}-owner.json').write_text(json.dumps({'pid':process.pid,
                'created':process.create_time(), 'exe':process.exe(), 'cmdline':process.cmdline()}), encoding='utf-8')
            print(f'{name}: ready, PID {process.pid}', flush=True)
            return
        time.sleep(.25)
    raise RuntimeError(f'{name}: not ready in 30 seconds; inspect {RUNTIME}; no automatic retry')


def gateway_start(status):
    archive_gateway_state(ROOT / 'server/.local/scc-gateway-state.json')
    powershell(ROOT / 'voice/Start-QueuedGateway.ps1', '-Action', 'Start', '-DemoNoThinking')
    state = json.loads((ROOT / 'server/.local/scc-gateway-state.json').read_text(encoding='utf-8-sig'))
    args = [state['python'], '-u', str(ROOT / 'server/gateway.py'), '--config',
            str(status.GATEWAY), '--port', '8841', '--log', str(ROOT / 'server/.local/scc-gateway.log')]
    if not owned_listener(8841, args):
        raise RuntimeError('Gateway owned loopback listener absent; health request refused')
    health = status.health(8841, token=status.credential(status.GATEWAY))
    if health.get('http_status') != 200:
        raise RuntimeError('Gateway HTTP health failed')
    print('Gateway: authenticated health OK', flush=True)


def archive_gateway_state(path):
    """Preserve only a prior-boot gateway receipt; never touch a PID/model lock."""
    if not path.exists() or listeners(8841):
        return
    state = json.loads(path.read_text(encoding='utf-8-sig'))
    expected = {'port':8841, 'gateway':str(ROOT / 'server/gateway.py'),
        'config':str(ROOT / 'server/.local/scc-gateway.json'),
        'python':r'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe'}
    if any(state.get(key) != value for key,value in expected.items()):
        raise RuntimeError('Gateway saved identity differs; receipt left unchanged')
    created = int(state['started_ticks']) / 10_000_000 - 62_135_596_800
    if created >= psutil.boot_time():
        return
    backup = path.with_name(path.stem + '.prior-boot-' + str(time.time_ns()) + '.json')
    path.replace(backup)
    print('Gateway: preserved prior-boot receipt; no process stopped', flush=True)


def model_start(status):
    powershell(ROOT / 'voice/Start-NativeModel.ps1', '-Action', 'Start')
    print('HaloGen: waiting for the original controller readiness (up to 10 minutes)', flush=True)
    deadline = time.monotonic() + 600
    last_notice = 0
    while time.monotonic() < deadline:
        try:
            result = status.health(8731, token=status.MODEL.read_text(encoding='utf-8-sig').strip())
            controller = status.health(8840, token=status.credential(status.PROFILE))
            if (result.get('http_status') == 200 and result.get('expected_model') is True
                    and result.get('version_matches') is True and result.get('profile_matches') is True
                    and result.get('context') == status.DEPLOYMENT['context']
                    and result.get('vision_enabled') is True
                    and result.get('slots') == status.DEPLOYMENT['slots']
                    and controller.get('status') in ('ok','ready')):
                print('HaloGen: original model and controller ready', flush=True)
                return
        except (OSError, ValueError):
            pass
        if time.monotonic()-last_notice >= 15:
            print('HaloGen: still loading; original memory guards remain active', flush=True)
            last_notice = time.monotonic()
        time.sleep(2)
    raise RuntimeError('HaloGen did not become ready; inspect its controller logs/retained lock. No lock was removed and no retry attempted.')


def selected_config(value, environment_name, default):
    selected = value if value is not None else os.environ.get(environment_name, default)
    if not isinstance(selected, (str, os.PathLike)) or not str(selected).strip():
        raise RuntimeError('Configure ' + environment_name + ' as an existing local config file')
    selected = Path(selected).expanduser()
    selected = (ROOT / selected).resolve() if not selected.is_absolute() else selected.resolve()
    if not selected.is_file():
        raise RuntimeError('Configure ' + environment_name + ' as an existing local config file')
    return selected


def voice_start(status, bot_config=None, native_config=None):
    bot_config = selected_config(bot_config, 'SCC_VOICE_BOT_CONFIG', BOT_CONFIG)
    native_config = selected_config(native_config, 'SCC_VOICE_NATIVE_CONFIG', NATIVE_CONFIG)
    config = json.loads(native_config.read_text(encoding='utf-8-sig'))
    if (config.get('auth_mode') != 'servicenow' or config.get('development_token')
            or config.get('development_token_file')):
        raise RuntimeError('Native production authentication configuration rejected')
    start_python('bot', [8850,8853], ROOT / 'voice/bridge.py', bot_config,
                 lambda:status.health(8850, '/', json_body=False))
    def native_health():
        result = status.health(8860)
        if result.get('auth_mode') != 'servicenow':
            raise RuntimeError('Native listener is not in ServiceNow auth mode')
        return result
    start_python('native', [8860], NATIVE / 'native_bridge.py', native_config, native_health)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stt','tts','model','gateway','voice','all','status'])
    parser.add_argument('--bot-config', type=Path)
    parser.add_argument('--native-config', type=Path)
    options = parser.parse_args()
    action = options.action
    if sys.platform != 'win32':
        raise RuntimeError('Run this launcher on Windows')
    status = module('scc_readonly_status', ROOT / 'voice/native-speech-validation/stack_status.py')
    if action == 'status':
        return status.main()
    with startup_lock():
        if listeners(8851) or listeners(8852):
            raise RuntimeError('Legacy CPU speech workers8851/8852 are active; do not run Start-Voice.ps1. Stop only their verified owned processes first.')
        if action in ('stt','tts','model','all'):
            selected = ['asr'] if action == 'stt' else ['tts'] if action == 'tts' else ['asr','tts']
            speech_start(selected)
        if action in ('model','all'):
            model_start(status)
        if action in ('gateway','all'):
            gateway_start(status)
        if action in ('voice','all'):
            voice_start(status, bot_config=options.bot_config, native_config=options.native_config)
        if action == 'all':
            if not all(value for key,value in status.funnel().items() if key.endswith('_matches') or key in ('https_443_configured','funnel_allowed')):
                raise RuntimeError('Expected Funnel route missing; no routes changed')
            return status.main()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # HTTP error details could include credentials; only our RuntimeErrors are displayed.
        print('START FEHLGESCHLAGEN: ' + (str(error) if type(error) is RuntimeError else type(error).__name__), file=sys.stderr, flush=True)
        print(f'Logs: {RUNTIME}', file=sys.stderr, flush=True)
        raise SystemExit(1)
