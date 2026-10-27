"""Start voice with the centrally selected local model; never switch models."""
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
PROFILE = None
PROFILE_SHA256 = None
CONTROLLER_SELECTION = SERVER / '.local/voice-deployment/controller-selection.local.json'
selected_controller = None
controller_consumer = None
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
OMNI_PYTHON = Path(r'C:\AI\runtimes\qwen3-omni-native\Scripts\python.exe')
OMNI_START_HELPER = Path(r'C:\Users\Marcel\Documents\Codex\2026-10-19\fahre-den-chat-servicenow-bergabe-bzw\duplex-implementation-20261023\task30-omni-runtime\ensure_owned_text.py')
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
    global PROFILE, PROFILE_SHA256, selected_controller, controller_consumer
    controller_consumer = load_module('scc_controller_consumer', ACTIVE / 'voice/native-start/controller_consumer.py')
    selected_controller = controller_consumer.load_selected(services, SERVER, PYTHON, CURRENT, CONTROLLER_SELECTION)
    PROFILE = selected_controller['profile_path']
    PROFILE_SHA256 = selected_controller['profile_sha256']
    return selected_controller['profile']



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
    return selected_controller['args']



def model_ready(profile):
    return controller_consumer.ready(services, selected_controller, CURRENT)



def cold_model_check():
    if services.listeners(8840):
        raise RuntimeError('Ein zentraler Controller ist bereits aktiv; auf dessen Bereitschaft warten.')
    engine = selected_controller['profile'].get('engine', {})
    if engine.get('kind') == 'halogen':
        backend_directory = Path(engine['directory'])
        if not backend_directory.is_absolute():
            backend_directory = CLEAN / backend_directory
        if (backend_directory / '.local/runner.lock').exists():
            raise RuntimeError('Halogen hat einen geschuetzten Abschluss offen. Erst den belegten Lauf bereinigen; kein automatischer Wiederholungsstart.')
    expected = controller_args()
    accepted = {os.path.normcase(expected[0]), os.path.normcase(services.python_base(expected[0]))}
    for process in services.psutil.process_iter(['cmdline', 'exe']):
        actual = process.info.get('cmdline') or []
        executable = process.info.get('exe') or ''
        if (actual and os.path.normcase(executable) in accepted
                and str(SERVER / 'controller.py') in actual):
            raise RuntimeError('Ein zentraler Controller startet bereits; kein zweiter Modellstart.')
    if CURRENT.exists():
        state = read_json(CURRENT)
        pid = state.get('pid')
        if type(pid) is int and services.psutil.pid_exists(pid) and services.process_args(pid) == controller_args():
            raise RuntimeError('Der ausgewaehlte Controller startet bereits. Bitte auf sein Ergebnis warten.')



def model_start(profile):
    if not model_ready(profile):
        cold_model_check()
        if hashlib.sha256(PROFILE.read_bytes()).hexdigest() != PROFILE_SHA256:
            raise RuntimeError('Zentral ausgewaehltes Profil wurde veraendert; kein Modellstart.')
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with (RUNTIME / 'selected-controller.stdout.log').open('ab') as stdout, (RUNTIME / 'selected-controller.stderr.log').open('ab') as stderr:
            child = subprocess.Popen(controller_args(), cwd=CLEAN, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, creationflags=DETACHED)
        print('Das zentral ausgewaehlte lokale Modell wird gestartet.', flush=True)
        deadline = time.monotonic() + 1200
        last_notice = time.monotonic()
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Der ausgewaehlte Controller wurde beendet. Kein automatischer Neustart.')
            try:
                if model_ready(profile):
                    break
            except RuntimeError:
                pass
            if time.monotonic() - last_notice >= 15:
                print('Modell laedt weiter; die vorhandenen Schutzpruefungen bleiben aktiv.', flush=True)
                last_notice = time.monotonic()
            time.sleep(1)
        else:
            raise RuntimeError('Das ausgewaehlte Modell wurde nicht rechtzeitig bereit.')
    controller_consumer.remember(selected_controller, CONTROLLER_SELECTION)
    print('Zentral ausgewaehltes Modell bereit: ' + profile['backend']['identifier'], flush=True)



def gateway_args():
    return [str(PYTHON), '-u', str(ACTIVE / 'server/gateway.py'), '--config',
            str(GATEWAY_CONFIG), '--port', '8841', '--log', str(ACTIVE / 'server/.local/scc-gateway.log')]


def gateway_ready(profile, require_health=True):
    config = read_json(GATEWAY_CONFIG)
    # Fixed model identities cannot be dynamic compatibility aliases.
    if (config.get('controller_consumer') is True
            and any(alias in ('gemma4-26b-a4b', 'Gemma 4 26B-A4B')
                    for alias in config.get('controller_aliases', ()))):
        raise RuntimeError('Die feste Gemma-Auswahl muss zuerst mit Control Tower abgestimmt werden.')
    if (config.get('controller_consumer') is not True
            or config.get('backend', {}).get('upstream') != 'http://127.0.0.1:8840'
            or credential(GATEWAY_CONFIG, 'backend_token_file') != credential(PROFILE)):
        raise RuntimeError('Gateway ist noch nicht mit dem zentralen Controller verbunden.')
    if not services.owned_listener(8841, gateway_args()):
        return False
    if not require_health:
        return True
    result = health(8841, token=credential(GATEWAY_CONFIG))
    if (result.get('http_status') != 200 or result.get('status') != 'ok'
            or result.get('draining') is True
            or result.get('backend') != profile['backend']['identifier']
            or result.get('context') != profile['backend']['context']):
        raise RuntimeError('Das Gateway meldet noch nicht das zentral ausgewaehlte Modell.')
    return True



def gateway_start(profile):
    if not gateway_ready(profile):
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with (RUNTIME / 'current-gateway.stdout.log').open('ab') as stdout, (RUNTIME / 'current-gateway.stderr.log').open('ab') as stderr:
            subprocess.Popen(gateway_args(), cwd=ACTIVE, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, creationflags=DETACHED)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if gateway_ready(profile):
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Gateway wurde nicht bereit; kein automatischer Neustart.')
    print('Gateway: mit zentraler Modellauswahl verbunden.', flush=True)



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
    for path in (PYTHON, SERVER / 'controller.py', ACTIVE / 'voice/native-start/controller_consumer.py',
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
    backend = native.get('asr_backend')
    if backend != 'qwen3-asr-0.6b':
        raise RuntimeError('Dieser Starter benoetigt die freigegebene Qwen-ASR-Auswahl; keine Dienste gestartet.')
    if services.listeners(8852) or (backend != 'qwen3-asr-0.6b' and services.listeners(8851)):
        raise RuntimeError('Nicht ausgewaehlte alte Sprachdienste sind aktiv. Keine Prozesse geaendert.')
    asr_stage(check_only=True)
    controller_ready = model_ready(profile)
    if not controller_ready:
        cold_model_check()
    gateway_ready(profile, require_health=controller_ready)
    for ports, script, config in (
            ((8850, 8853), ACTIVE / 'voice/bridge.py', BOT_CONFIG),
            ((8860,), ACTIVE / 'voice/native-bridge/native_bridge.py', NATIVE_CONFIG)):
        args = [str(services.PYTHON), '-u', str(script), '--config', str(config)]
        pids = [services.owned_listener(port, args) for port in ports]
        if any(pids) and (not all(pids) or len(set(pids)) != 1):
            raise RuntimeError('Unvollstaendige Sprach-Listener. Keine Prozesse geaendert.')
    funnel_check()


def conversation_stage(check_only):
    native = read_json(NATIVE_CONFIG)
    if native.get('conversation_transport') != 'controller-text':
        raise RuntimeError('Bitte den freigegebenen Controller-Sprachtransport auswaehlen.')



def omni_stage(check_only):
    # The controller text transport uses the current model; no Omni process.
    conversation_stage(check_only)



def asr_stage(check_only=False):
    native = read_json(NATIVE_CONFIG)
    if native.get('asr_backend') != 'qwen3-asr-0.6b':
        raise RuntimeError('Qwen-Spracherkennung ist nicht ausgewaehlt; kein anderer ASR-Start.')
    helper = load_module('scc_qwen_asr_start', ACTIVE / 'voice/native-start/qwen_asr_start.py')
    state = helper.ensure(native, check_only=check_only)
    print('Qwen-Spracherkennung (' + helper.runtime(native) + '): ' + state + '.', flush=True)


def speech_stage():
    native = read_json(NATIVE_CONFIG)
    if native.get('asr_backend') != 'qwen3-asr-0.6b':
        raise RuntimeError('Qwen-Spracherkennung ist nicht ausgewaehlt; kein anderer ASR-Start.')
    speech_services.speech_start(['tts'])
    asr_stage(check_only=False)



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
        omni_stage(check_only=True)
        print('Vorpruefung erfolgreich. Es wurden keine Dienste gestartet.', flush=True)
        return 0
    # Same fixed order on every run; never alter either controller ownership lock.
    with services.startup_lock(), speech_services.startup_lock():
        preflight(profile)
        conversation_stage(check_only=True)
        omni_stage(check_only=True)
        print('Sprache: vorhandene native Erkennung und ausgewaehlte Stimme pruefen/starten.', flush=True)
        speech_stage()
        model_start(profile)
        gateway_start(profile)
        conversation_stage(check_only=False)
        omni_stage(check_only=False)
        print('ServiceNow: Bot und native Sprachbruecke pruefen/starten.', flush=True)
        status = type('ReadOnlyHealth', (), {'health': staticmethod(health)})
        services.voice_start(status, bot_config=BOT_CONFIG, native_config=NATIVE_CONFIG)
        funnel_check()
    print('BEREIT: zentrales lokales Modell, Qwen-Spracherkennung, eigene Stimme und ServiceNow.', flush=True)
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
