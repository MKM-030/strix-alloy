"""Consume the centrally selected local controller without choosing a model."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 262144:
        raise RuntimeError('Controller-Konfiguration ist zu gross.')
    return json.loads(raw.decode('utf-8-sig'))


def token(profile_path, profile):
    path = Path(profile['token_file'])
    if not path.is_absolute():
        path = profile_path.parent / path
    raw = path.read_bytes()
    value = raw.decode('utf-8-sig').strip()
    if len(raw) > 8192 or not 16 <= len(value) <= 8192:
        raise RuntimeError('Controller-Anmeldung fehlt oder ist ungueltig.')
    return value


def request(path, credential):
    if path not in ('/health', '/v1/models'):
        raise ValueError('Unsupported controller query')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    query = urllib.request.Request('http://127.0.0.1:8840' + path,
        headers={'Authorization': 'Bearer ' + credential})
    with opener.open(query, timeout=6) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise RuntimeError('Controller-Status ungueltig.')
        return json.loads(raw)


def load_selected(services, server, python, current, selection):
    """Live controller wins; a frozen previous selection permits a cold start."""
    sockets = services.listeners(8840)
    if sockets:
        owners = {item.pid for item in sockets}
        if len(owners) != 1 or any(item.laddr.ip != '127.0.0.1' for item in sockets):
            raise RuntimeError('Controller-Port ist nicht eindeutig lokal zugeordnet.')
        actual = services.process_args(next(iter(owners)))
        prefix = ['-u', '-B', str(server / 'controller.py'), 'run', '--config']
        if len(actual) != 9 or actual[1:6] != prefix or actual[7:] != ['--port', '8840']:
            raise RuntimeError('Controller-Prozess entspricht nicht der zentralen Laufzeit.')
        profile_path = Path(actual[6])
        state = read_json(current)
        expected_sha = state.get('profile_sha256')
    else:
        if not selection.is_file():
            raise RuntimeError('Bitte das gewuenschte lokale Modell zuerst zentral starten.')
        saved = read_json(selection)
        profile_path = Path(saved['profile'])
        expected_sha = saved['profile_sha256']
        # A central selection made since the last voice start supersedes this
        # consumer's saved fallback, including when that newer run has failed.
        # Never roll the model back merely because its listener is absent.
        if current.is_file():
            latest = read_json(current)
            if latest.get('profile_sha256') != expected_sha:
                raise RuntimeError('Die zentrale Modellauswahl wurde geaendert. Bitte das dort ausgewaehlte Modell zuerst bereitstellen; kein Start eines aelteren Voice-Profils.')
    if (not profile_path.is_absolute() or not profile_path.is_file()
            or type(expected_sha) is not str or len(expected_sha) != 64):
        raise RuntimeError('Zentrale Modellauswahl ist unvollstaendig.')
    raw = profile_path.read_bytes()
    if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != expected_sha:
        raise RuntimeError('Das ausgewaehlte Controller-Profil wurde veraendert.')
    profile = json.loads(raw.decode('utf-8-sig'))
    backend = profile.get('backend', {})
    if (not all(key in backend for key in ('identifier', 'checkpoint', 'context'))
            or '/v1/chat/completions' not in backend.get('routes', [])):
        raise RuntimeError('Ausgewaehltes Modell bietet keine Gespraechsschnittstelle.')
    # Validate the credential before any service starts, without retaining it.
    token(profile_path, profile)
    return {'profile_path': profile_path, 'profile_sha256': expected_sha,
            'profile': profile, 'args': [str(python), *prefix_args(server, profile_path)]}


def prefix_args(server, profile):
    return ['-u', '-B', str(server / 'controller.py'), 'run', '--config', str(profile), '--port', '8840']


def ready(services, selected, current):
    pid = services.owned_listener(8840, selected['args'])
    if not pid:
        return False
    state = read_json(current)
    backend = selected['profile']['backend']
    if (state.get('pid') != pid or state.get('port') != 8840
            or state.get('profile_sha256') != selected['profile_sha256']
            or not 0 <= time.time() - state.get('heartbeat', 0) <= 15
            or state.get('phase') != 'ready'
            or any(state.get(key) != backend[key] for key in ('checkpoint', 'context'))
            or state.get('backend') != backend['identifier']):
        raise RuntimeError('Der zentrale Controller ist noch nicht bereit oder sein Status ist veraltet.')
    secret = token(selected['profile_path'], selected['profile'])
    health = request('/health', secret)
    models = request('/v1/models', secret)
    if (health.get('status') != 'ok' or health.get('draining') is not False
            or health.get('backend') != backend['identifier']
            or any(health.get(key) != backend[key] for key in ('checkpoint', 'context'))
            or backend['identifier'] not in [item.get('id') for item in models.get('data', [])]):
        raise RuntimeError('Controller-Status und zentrale Modellauswahl stimmen nicht ueberein.')
    return True


def remember(selected, path):
    """Persist only a verified model choice, never a credential or process argv."""
    value = {'schema': 1, 'profile': str(selected['profile_path']),
             'profile_sha256': selected['profile_sha256'],
             'model': selected['profile']['backend']['identifier']}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)
