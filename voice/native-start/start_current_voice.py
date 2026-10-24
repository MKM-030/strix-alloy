"""Start the current Gemma/ServiceNow voice stack without stopping services."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


ACTIVE = Path(r'C:\Projects\strix-alloy-scc-voice')
CLEAN = Path(r'C:\Projects\strix-alloy-clean')
SERVER = CLEAN / 'server'
PYTHON = SERVER / '.local/venv/Scripts/python.exe'
PROFILE = SERVER / '.local/gemma-switch-20261018/serving-gemma4-26b-32k-fast.json'
PROFILE_SHA256 = 'ea335895f0cb8f6ded0698ec940cab808a11162187129822ecd9c010efbdb330'
MANAGED_TURN_SHA256 = '11792b33ecb0cae274d14590aa5bd35aaa430cbb481396d90513054d4b245af9'
CURRENT = SERVER / '.local/current.json'
RUNTIME = ACTIVE / 'voice/native-start/runtime'
BOT_CONFIG = Path(r'E:\SCC-Voice\bridge.json')
NATIVE_CONFIG = SERVER / '.local/voice-deployment/native-config.local.json'
GATEWAY_CONFIG = ACTIVE / 'server/.local/scc-gateway.json'
GATEWAY_STATE = ACTIVE / 'server/.local/scc-gateway-state.json'
ENGINE_PORTS = (8823, 8731, 8826, 8836, 18808)
CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000200 | 0x00000008
services = None
speech_services = None


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_profile():
    reader = ACTIVE / 'voice/native-start/gateway_profile.py'
    # Suppress validator diagnostics, including malformed configuration values.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            validator = load_module('scc_current_profile', reader)
            validator.load_native_profile(PROFILE, PROFILE_SHA256, SERVER)
        raw = PROFILE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != PROFILE_SHA256:
            raise ValueError('changed')
        return json.loads(raw.decode('utf-8-sig'))
    except Exception:
        raise RuntimeError('Das freigegebene Gemma-Profil oder seine Laufzeitdateien konnten nicht verifiziert werden.') from None


def credential(config, key='token_file'):
    path = Path(read_json(config)[key])
    if not path.is_absolute():
        path = config.parent / path
    return path.read_text(encoding='utf-8-sig').strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def health(port, path='/health', token=None, json_body=True):
    if (port, path) not in {(8823, '/health'), (8840, '/health'),
            (8841, '/health'), (8850, '/'), (8860, '/health')}:
        raise RuntimeError('Nicht freigegebene Statusadresse.')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', headers=headers, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=5) as response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('Statusantwort ist zu gross.')
        value = json.loads(raw) if json_body else {}
        result = {'http_status': response.status}
        for key in ('status', 'backend', 'checkpoint', 'context', 'draining'):
            if key in value:
                result[key] = value[key]
        if value.get('authMode') in ('servicenow', 'deny', 'loopback-development'):
            result['auth_mode'] = value['authMode']
        return result


def controller_args():
    return [str(PYTHON), '-u', '-B', str(SERVER / 'controller.py'),
            'run', '--config', str(PROFILE), '--port', '8840']


def model_ready(profile):
    pid = services.owned_listener(8840, controller_args())
    if not pid:
        return False
    state = read_json(CURRENT)
    if (state.get('pid') != pid or state.get('port') != 8840
            or state.get('profile_sha256') != PROFILE_SHA256
            or not 0 <= time.time() - state.get('heartbeat', 0) <= 10
            or state.get('phase') != 'ready'):
        raise RuntimeError('Der laufende Controller passt nicht zum Profil oder sein Status ist veraltet. Keine Prozesse geaendert.')
    # Engine.start appends this private argument. Keep the exact comparison in
    # memory only; neither the argument vector nor the credential is logged.
    engine_args = list(profile['engine']['command'])
    if profile['engine'].get('api_key_from_backend_token'):
        engine_args += ['--api-key', credential(PROFILE, 'backend_token_file')]
    if not services.owned_listener(8823, engine_args):
        raise RuntimeError('Der erwartete Gemma-Prozess fehlt auf Port 8823.')
    result = health(8840, token=credential(PROFILE))
    backend = profile['backend']
    if (result.get('http_status') != 200 or result.get('status') != 'ok'
            or result.get('draining') is True
            or any(result.get(key) != backend[key] for key in ('checkpoint', 'context'))
            or result.get('backend') != backend['identifier']):
        raise RuntimeError('Der Gemma-Controller ist nicht bereit oder meldet ein anderes Modell.')
    backend_health = health(8823, token=credential(PROFILE, 'backend_token_file'))
    if backend_health.get('http_status') != 200 or backend_health.get('status') != 'ok':
        raise RuntimeError('Die Gemma-Modellpruefung auf Port 8823 ist fehlgeschlagen.')
    return True


def cold_model_check():
    for port in ENGINE_PORTS:
        if services.listeners(port):
            raise RuntimeError(f'Port {port} ist bereits belegt. Der Controller wird nicht gestartet; keine Prozesse geaendert.')
    if CURRENT.exists():
        state = read_json(CURRENT)
        pid = state.get('pid')
        # A saved phase is not evidence of a live controller. Verify the process.
        if (type(pid) is int and services.psutil.pid_exists(pid)
                and services.process_args(pid) == controller_args()):
            raise RuntimeError('Ein passender Controller startet bereits ohne bereiten Listener. Auf dessen Ergebnis warten.')


def model_start(profile):
    if model_ready(profile):
        print('Gemma: laufender, verifizierter Controller und Modell wiederverwendet.', flush=True)
        return
    cold_model_check()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if CURRENT.exists():
        shutil.copy2(CURRENT, RUNTIME / f'current.before-start-{time.time_ns()}.json')
    # controller.py alone owns its lock, qualification and memory guards.
    with (RUNTIME / 'gemma-controller.stdout.log').open('ab') as stdout, \
            (RUNTIME / 'gemma-controller.stderr.log').open('ab') as stderr:
        child = subprocess.Popen(controller_args(), cwd=CLEAN, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, creationflags=DETACHED)
    print('Gemma: Modell wird geladen; Speicherpruefungen des Controllers bleiben aktiv.', flush=True)
    deadline = time.monotonic() + 1200
    notice = time.monotonic()
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f'Gemma-Controller wurde beendet. Logs: {RUNTIME}')
        if model_ready(profile):
            print('Gemma: Controller und Modell sind bereit.', flush=True)
            return
        if time.monotonic() - notice >= 15:
            print('Gemma laedt weiter. Bitte dieses Startfenster geoeffnet lassen.', flush=True)
            notice = time.monotonic()
        time.sleep(1)
    raise RuntimeError(f'Gemma wurde innerhalb von 20 Minuten nicht bereit. Logs: {RUNTIME}. Kein automatischer Neustart.')


def gateway_args():
    return [str(PYTHON), '-u', str(ACTIVE / 'server/gateway.py'), '--config',
            str(GATEWAY_CONFIG), '--port', '8841', '--log', str(ACTIVE / 'server/.local/scc-gateway.log')]


def gateway_ready(profile):
    if not services.owned_listener(8841, gateway_args()):
        return False
    state = read_json(GATEWAY_STATE)
    if state.get('profile') != str(PROFILE) or state.get('profile_sha256') != PROFILE_SHA256:
        raise RuntimeError('Das laufende Gateway verwendet ein anderes Profil.')
    result = health(8841, token=credential(GATEWAY_CONFIG))
    if (result.get('http_status') != 200 or result.get('status') != 'ok'
            or result.get('backend') != profile['backend']['identifier']
            or result.get('context') != profile['backend']['context']):
        raise RuntimeError('Das Gateway ist nicht bereit oder meldet ein anderes Modell.')
    return True


def gateway_start(profile):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # This reviewed ACTIVE helper preserves the existing public credential.
    args = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(ACTIVE / 'voice/Start-QueuedGateway.ps1'), '-Action', 'Start',
            '-ProfileConfig', str(PROFILE), '-ProfileSha256', PROFILE_SHA256, '-Python', str(PYTHON)]
    with (RUNTIME / 'current-gateway.stdout.log').open('ab') as stdout, \
            (RUNTIME / 'current-gateway.stderr.log').open('ab') as stderr:
        result = subprocess.run(args, cwd=ACTIVE, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, creationflags=CREATE_NO_WINDOW, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f'Gateway-Start fehlgeschlagen. Logs: {RUNTIME}')
    if not gateway_ready(profile):
        raise RuntimeError('Das erwartete Gateway auf Port 8841 fehlt.')
    print('Gateway: verifiziert und bereit.', flush=True)


def funnel_check():
    executable = shutil.which('tailscale.exe') or r'C:\Program Files\Tailscale\tailscale.exe'
    result = subprocess.run([executable, 'funnel', 'status', '--json'],
        capture_output=True, text=True, check=True, timeout=15, creationflags=CREATE_NO_WINDOW)
    value = json.loads(result.stdout)
    expected = {'/': 'http://127.0.0.1:8841', '/scc-native': 'http://127.0.0.1:8860',
                '/scc-voice': 'http://127.0.0.1:8853'}
    sites = value.get('Web', {})
    if (value.get('TCP', {}).get('443', {}).get('HTTPS') is not True
            or not any(value.get('AllowFunnel', {}).values())
            or not any(all(site.get('Handlers', {}).get(route, {}).get('Proxy') == target
                          for route, target in expected.items())
                       for site in sites.values())):
        raise RuntimeError('Die erwarteten Tailscale-Routen fehlen. Es wurden keine Routen geaendert.')
    print('Tailscale: die vorhandenen HTTPS-Routen stimmen.', flush=True)


def preflight(profile):
    for path in (PYTHON, SERVER / 'controller.py', ACTIVE / 'voice/Start-QueuedGateway.ps1',
            services.PYTHON, ACTIVE / 'voice/bridge.py', ACTIVE / 'voice/native-bridge/native_bridge.py',
            BOT_CONFIG, NATIVE_CONFIG):
        if not path.is_file():
            raise RuntimeError(f'Benoetigte Datei fehlt: {path}')
    native = read_json(NATIVE_CONFIG)
    if (native.get('auth_mode') != 'servicenow' or native.get('development_token')
            or native.get('development_token_file')):
        raise RuntimeError('Die native Konfiguration verwendet nicht die freigegebene ServiceNow-Anmeldung.')
    try:
        reference = native['managed_turn_config_file']
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError('missing reference')
        relay_path = Path(reference)
        if not relay_path.is_absolute():
            relay_path = NATIVE_CONFIG.parent / relay_path
        with relay_path.open('rb') as source:
            relay_bytes = source.read(16385)
        if len(relay_bytes) > 16384 or hashlib.sha256(relay_bytes).hexdigest() != MANAGED_TURN_SHA256:
            raise ValueError('unreviewed relay bytes')
    except (KeyError, TypeError, ValueError, OSError):
        raise RuntimeError('Die Relay-Konfiguration ist veraltet oder nicht freigegeben. Bitte die genehmigte Konfiguration wiederherstellen; kein Dienst wurde gestartet.') from None
    if services.listeners(8851) or services.listeners(8852):
        raise RuntimeError('Alte Sprachdienste auf Port 8851/8852 sind aktiv. Keine Prozesse geaendert.')
    if not model_ready(profile):
        cold_model_check()
    gateway_ready(profile)
    for ports, script, config in (
            ((8850, 8853), ACTIVE / 'voice/bridge.py', BOT_CONFIG),
            ((8860,), ACTIVE / 'voice/native-bridge/native_bridge.py', NATIVE_CONFIG)):
        args = [str(services.PYTHON), '-u', str(script), '--config', str(config)]
        pids = [services.owned_listener(port, args) for port in ports]
        if any(pids) and (not all(pids) or len(set(pids)) != 1):
            raise RuntimeError('Unvollstaendige Sprach-Listener. Keine Prozesse geaendert.')
    funnel_check()


def conversation_stage(check_only):
    owner = load_module('scc_conversation_runtime', ACTIVE / 'voice/native-start/conversation_runtime.py')
    runtime = owner.selected_runtime(NATIVE_CONFIG.parent / 'conversation-selection.local.json', NATIVE_CONFIG)
    if runtime is not None:
        state = runtime.run(check_only=check_only)
        print('Gespraechsmodell: ' + state + '.', flush=True)


def run(check_only=False):
    global services, speech_services
    if services is None:
        services = load_module('scc_current_services', ACTIVE / 'voice/native-start/start_services.py')
    if speech_services is None:
        speech_services = load_module('scc_current_speech_services', CLEAN / 'voice/native-start/start_services.py')
    profile = validate_profile()
    if check_only:
        preflight(profile)
        conversation_stage(check_only=True)
        print('Vorpruefung erfolgreich. Es wurden keine Dienste gestartet.', flush=True)
        return 0
    # Same fixed order on every run; never alter either controller ownership lock.
    with services.startup_lock(), speech_services.startup_lock():
        preflight(profile)
        conversation_stage(check_only=True)
        print('Sprache: vorhandene native Erkennung und ausgewaehlte Stimme pruefen/starten.', flush=True)
        speech_services.speech_start(['asr', 'tts'])
        model_start(profile)
        gateway_start(profile)
        conversation_stage(check_only=False)
        print('ServiceNow: Bot und native Sprachbruecke pruefen/starten.', flush=True)
        status = type('ReadOnlyHealth', (), {'health': staticmethod(health)})
        services.voice_start(status, bot_config=BOT_CONFIG, native_config=NATIVE_CONFIG)
        funnel_check()
    print('BEREIT: Gemma, Spracherkennung, Stimme und ServiceNow-Sprachbruecken.', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Nur lesen und pruefen; keine Dienste starten.')
    options = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('Dieses Startprogramm muss unter Windows laufen.')
    return run(options.check_only)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Never print HTTP error details or arbitrary validator/config values.
        message = str(error) if type(error) is RuntimeError else type(error).__name__
        print('START FEHLGESCHLAGEN: ' + message, file=sys.stderr, flush=True)
        print(f'Logs: {RUNTIME}', file=sys.stderr, flush=True)
        raise SystemExit(1)
