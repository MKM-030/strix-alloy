"""Own only the installed, offline Qwen0.6B ASR worker; never stop services."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

import psutil

ROOT = Path(r'C:\Projects\strix-alloy-scc-voice')
RUNTIME = ROOT / 'voice/native-start/runtime'
PYTHON = Path(r'E:\SCC-Voice\asr-env\Scripts\python.exe')
BASE = Path(r'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe')
SCRIPT = ROOT / 'voice/audio_service.py'
TOKEN = Path(r'C:\Projects\strix-alloy-clean\server\.local\servicenow-api-token.txt')
CACHE = Path(r'E:\SCC-Voice\models')
REVISION = '5eb144179a02acc5e5ba31e748d22b0cf3e303b0'
MODEL = CACHE / 'hub/models--Qwen--Qwen3-ASR-0.6B'
SNAPSHOT = MODEL / 'snapshots' / REVISION
OWNER = RUNTIME / 'qwen-asr-owner.json'
BACKEND = 'qwen3-asr-0.6b'
URL = 'http://127.0.0.1:8851/v1/audio/transcriptions'
PINS = {
    SCRIPT: '72ebaf81da831482b2c840627d2f3d2d5ab58e1697d600671ac8fa50333a69ec',
    PYTHON: '0b471133e110cfb53a061cad528ce8e517d7b9ac41a0a396c39ad795a487fc14',
    PYTHON.parents[1] / 'pyvenv.cfg': '34f8160307cbea6ea9c0709a07d2a0404e37a678221d9d5cec6d12c9b878688f',
    SNAPSHOT / 'model.safetensors': '79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea',
    SNAPSHOT / 'config.json': '76d3ae4601ce939830b2517f4a6cadb86cc51316c3900af6b020b051c21a478c',
    SNAPSHOT / 'preprocessor_config.json': '45e120a4eda2c20c5d7f2ea9354e63536bf35e27aa573fb7cdf78017b378770d',
    SNAPSHOT / 'tokenizer_config.json': '4942d005604266809309cabc9f4e9cb89ce855d59b14681fdc0e1cc62ea26c4c',
    SNAPSHOT / 'chat_template.json': '75a8cfca24f00de72d796fbfed6858fc9614ef3dabd8696684cc3bc03a9c58ff',
    SNAPSHOT / 'merges.txt': '8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5',
    SNAPSHOT / 'vocab.json': 'ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910',
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def selection():
    return {'asr_backend': BACKEND, 'asr_url': URL, 'asr_token_file': str(TOKEN)}


def selected(native):
    backend = native.get('asr_backend', 'whisper')
    if backend == 'whisper':
        return False
    if (backend != BACKEND or native.get('asr_url') != URL
            or not isinstance(native.get('asr_token_file'), str)
            or Path(native['asr_token_file']).resolve() != TOKEN.resolve()):
        raise RuntimeError('Qwen-ASR-Auswahl oder private Endpunktbindung ist ungueltig.')
    return True


def verify_files():
    if any(not path.is_file() or sha(path) != expected for path, expected in PINS.items()):
        raise RuntimeError('Die freigegebene Qwen-ASR-Laufzeit oder der lokale Modellcache wurde veraendert.')
    if (MODEL / 'refs/main').read_text().strip() != REVISION or not TOKEN.is_file():
        raise RuntimeError('Qwen-ASR-Modellrevision oder private Token-Datei fehlt.')


def arguments():
    return [str(PYTHON), '-u', str(SCRIPT), '--mode', 'asr', '--port', '8851',
            '--threads', '6', '--dtype', 'float32', '--token-file', str(TOKEN),
            '--cache-dir', str(CACHE)]


def sockets(port):
    return [item for item in psutil.net_connections(kind='tcp')
            if item.status == psutil.CONN_LISTEN and item.laddr.port == port]


def process_identity(pid):
    process = psutil.Process(pid)
    args = process.cmdline()
    accepted = {os.path.normcase(str(PYTHON)), os.path.normcase(str(BASE))}
    if (not args or os.path.normcase(args[0]) not in accepted
            or args[1:] != arguments()[1:]
            or os.path.normcase(process.exe()) not in accepted
            or Path(process.cwd()).resolve() != ROOT.resolve()):
        raise RuntimeError('Port8851 gehoert nicht dem vorgesehenen Qwen-ASR-Prozess.')
    environment = process.environ()  # Memory only; never log values.
    if (environment.get('HF_HUB_OFFLINE') != '1'
            or environment.get('TRANSFORMERS_OFFLINE') != '1'
            or environment.get('HF_HOME') != str(CACHE)):
        raise RuntimeError('Qwen-ASR hat nicht die freigegebene Offline-Umgebung.')
    return {'pid': pid, 'created': process.create_time()}


def listener_identity():
    found = sockets(8851)
    if not found:
        return None
    owners = {item.pid for item in found}
    if len(owners) != 1 or any(item.laddr.ip != '127.0.0.1' for item in found):
        raise RuntimeError('Port8851 hat einen fremden oder oeffentlichen Listener.')
    return process_identity(owners.pop())


def listener():
    identity = listener_identity()
    if identity is None:
        return None
    if not OWNER.is_file() or json.loads(OWNER.read_text(encoding='utf-8')) != identity:
        raise RuntimeError('Qwen-ASR-Listener besitzt keinen passenden Eigentumsnachweis.')
    return identity['pid']


def adopt_launched_listener(launch_identity):
    """A Windows venv redirector may own a separate base-Python child."""
    identity = listener_identity()
    if identity is None:
        return None
    if identity != launch_identity:
        parents = [{'pid':parent.pid, 'created':parent.create_time()}
                   for parent in psutil.Process(identity['pid']).parents()]
        if launch_identity not in parents:
            raise RuntimeError('Der ASR-Listener stammt nicht vom einmal gestarteten Prozess.')
    OWNER.write_text(json.dumps(identity), encoding='utf-8')
    return identity['pid']


def pending_owner():
    if OWNER.is_file():
        recorded = json.loads(OWNER.read_text(encoding='utf-8'))
        try:
            process = psutil.Process(recorded['pid'])
            if process.create_time() == recorded['created']:
                if process_identity(recorded['pid']) != recorded:
                    raise RuntimeError('Qwen-ASR-Startidentitaet wurde veraendert.')
                return True
        except psutil.NoSuchProcess:
            pass
    # Refuse an unrecorded loading copy, even before it has a listener.
    for process in psutil.process_iter(['cmdline']):
        args = process.info.get('cmdline') or []
        if str(SCRIPT) in args and '--mode' in args:
            index = args.index('--mode')
            if index + 1 < len(args) and args[index + 1] == 'asr':
                raise RuntimeError('Ein ASR-Prozess startet bereits ohne passenden Listenernachweis.')
    return False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_health(port=8851):
    if port not in (8851, 8860):
        raise RuntimeError('Nicht freigegebener Statusendpunkt.')
    headers = {}
    if port == 8851:
        token = TOKEN.read_text(encoding='utf-8-sig').strip()
        if not token or '\r' in token or '\n' in token:
            raise RuntimeError('Die private ASR-Authentifizierung ist ungueltig.')
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(f'http://127.0.0.1:{port}/health', headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=5)
    except urllib.error.HTTPError as error:
        if port != 8860 or error.code != 503:
            raise
        response = error
    with response:
        data = response.read(65537)
        if response.status not in ((200, 503) if port == 8860 else (200,)) or len(data) > 65536:
            raise RuntimeError('ASR-Statusantwort ist ungueltig.')
        status = response.status
    value = json.loads(data)
    if port == 8860:
        if type(value) is not dict:
            raise RuntimeError('Native-Statusantwort ist ungueltig.')
        value['_http_status'] = status
    return value


def worker_health(pid):
    if listener() != pid:
        raise RuntimeError('Qwen-ASR-Identitaet wurde vor der Statuspruefung veraendert.')
    value = request_health()
    expected = {'status':'ready', 'mode':'asr', 'model':'Qwen/Qwen3-ASR-0.6B',
                'device':'cpu', 'dtype':'float32', 'busy':False, 'max_parallel':1}
    if any(type(value.get(key)) is not type(want) or value[key] != want for key, want in expected.items()):
        raise RuntimeError('Qwen-ASR meldet nicht das bereite, untätige freigegebene Modell.')


def native_identity():
    found = sockets(8860)
    if not found:
        return None
    if len({item.pid for item in found}) != 1 or any(item.laddr.ip != '127.0.0.1' for item in found):
        raise RuntimeError('Native-Statuslistener ist nicht privat.')
    try:
        owner = json.loads((RUNTIME / 'native-owner.json').read_text(encoding='utf-8'))
        process = psutil.Process(found[0].pid)
        args = process.cmdline()
        accepted = {os.path.normcase(str(BASE)),
                    os.path.normcase(str(ROOT / 'voice/native-bridge/.venv/Scripts/python.exe'))}
        tail = ['-u', str(ROOT / 'voice/native-bridge/native_bridge.py'), '--config',
                r'C:\Projects\strix-alloy-clean\server\.local\voice-deployment\native-config.local.json']
        if (owner['pid'] != process.pid or owner['created'] != process.create_time()
                or os.path.normcase(owner['exe']) != os.path.normcase(process.exe())
                or owner['cmdline'] != args or not args or os.path.normcase(args[0]) not in accepted
                or os.path.normcase(process.exe()) not in accepted or args[1:] != tail
                or Path(process.cwd()).resolve() != ROOT.resolve()):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, psutil.Error):
        raise RuntimeError('Native-Listener besitzt keinen passenden Eigentumsnachweis.') from None
    return owner


def native_idle():
    identity = native_identity()
    if identity is None:
        return
    value = request_health(8860)
    counts = ('nativeSessions', 'sdkSessions', 'nativeSdkSessions',
              'activeSdkSessions', 'pendingSdkSessions')
    common = (value.get('authMode') == 'servicenow' and 'nativeSessions' in value
        and all(type(value[key]) is int and value[key] == 0 for key in counts if key in value))
    known = {'status', 'authMode', 'conversationLayer', 'conversationPipeline',
             'conversationSentenceStreaming', 'asrBackend', 'asrReady', '_http_status', *counts}
    # An absent selected ASR is the only supported 503 from the inspected Native
    # health route. Keep active, foreign, malformed or other failures closed.
    missing_asr = (value.get('_http_status') == 503 and value.get('status') == 'unavailable'
        and value.get('asrBackend') == BACKEND and value.get('asrReady') is False
        and not (set(value) - known))
    healthy = value.get('_http_status') == 200 and value.get('status') == 'ok'
    if not common or not (healthy or missing_asr) or native_identity() != identity:
        raise RuntimeError('Vor dem ASR-Modellstart muss Native untätig sein.')


@contextmanager
def startup_lock():
    import msvcrt
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / 'qwen-asr-start.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Ein Qwen-ASR-Start ist bereits aktiv.') from None
        try:
            yield
        finally:
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def ensure(native, check_only=False):
    if not selected(native):
        return 'not-selected'
    verify_files()
    pid = listener()
    if pid:
        worker_health(pid)
        return 'ready'
    if pending_owner():
        raise RuntimeError('Qwen-ASR wird bereits geladen; kein zweiter Start.')
    if check_only:
        return 'absent'
    with startup_lock():
        if listener() or pending_owner():
            raise RuntimeError('ASR-Zustand hat sich geaendert; kein automatischer weiterer Start.')
        native_idle()
        if psutil.virtual_memory().available < 18 * 1024**3:
            raise RuntimeError('ASR-Start benoetigt weiterhin 18GiB freien Speicher.')
        environment = dict(os.environ, HF_HOME=str(CACHE), HF_HUB_OFFLINE='1',
            TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
            TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='6')
        with (RUNTIME / 'qwen-asr.stdout.log').open('ab') as stdout, \
                (RUNTIME / 'qwen-asr.stderr.log').open('ab') as stderr:
            child = subprocess.Popen(arguments(), cwd=ROOT, env=environment,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        launch_identity = {'pid':child.pid, 'created':psutil.Process(child.pid).create_time()}
        OWNER.write_text(json.dumps(launch_identity), encoding='utf-8')
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Qwen-ASR-Start beendet; Logs pruefen, kein automatischer Neustart.')
            pid = adopt_launched_listener(launch_identity)
            if pid:
                worker_health(pid)
                return 'started'
            time.sleep(.25)
        raise RuntimeError('Qwen-ASR nach drei Minuten nicht bereit; kein automatischer Neustart.')
