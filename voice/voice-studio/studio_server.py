"""Private Voice Studio on loopback; reuse immutable consented voice transactions.

This server never starts, downloads or restarts speech models. The public health
and static login page contain no recordings. All profile/audio routes require a
secure browser session. The configured HTTPS origin is the sole mutation origin.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
from collections import deque
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import wave

from aiohttp import ClientSession, ClientTimeout, web

HERE = Path(__file__).resolve().parent
COOKIE_NAME = '__Host-voice_studio'
MAX_WAV_BYTES = 6 * 1024 * 1024
MAX_BODY_BYTES = 8 * 1024 * 1024 + 16 * 1024
SESSION_SECONDS = 8 * 3600
PBKDF_ITERATIONS = 250_000
ID_RE = re.compile(r'\d{8}T\d{6}Z-[a-f0-9]{12}\Z')
REFERENCE_TEXT = ('Guten Tag. Ich spreche heute meine eigene Stimme '
    'für den lokalen Sprachassistenten ein. Bitte helfen Sie mir, einen neuen Laptop '
    'zu bestellen. Vielen Dank für Ihre Unterstützung.')
PREVIEW_TEXT = 'Guten Tag. Wie kann ich Ihnen helfen?'
LOG = logging.getLogger('scc.voice_studio')


@dataclass(frozen=True)
class Config:
    origin: str
    runtime: Path = HERE / 'runtime'
    profile_root: Path = HERE.parent / 'voice-profile' / 'runtime' / 'profiles'
    web_root: Path = HERE / 'web'
    base_path: str = '/voice-studio'

    @property
    def auth_file(self):
        return self.runtime / 'auth.json'


class APIError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def restrict_private_path(path, *, directory=False):
    """Allow only the current Windows operator and SYSTEM; restrict POSIX mode."""
    path = Path(path)
    if sys.platform != 'win32':
        path.chmod(0o700 if directory else 0o600)
        return
    output = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'],
        text=True, encoding='utf-8', errors='replace', stderr=subprocess.DEVNULL)
    sid = next(csv.reader(io.StringIO(output)))[-1]
    if not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise RuntimeError('Cannot resolve the Windows operator SID')
    permissions = '(OI)(CI)(F)' if directory else '(F)'
    subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
        '*' + sid + ':' + permissions, '*S-1-5-18:' + permissions],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def initialize_auth(path, password=None):
    """Create a salted verifier exclusively; never log or overwrite credentials."""
    path = Path(path)
    password = password or secrets.token_urlsafe(18)
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('Access code must contain 12–128 characters')
    salt = secrets.token_bytes(32)
    value = {'schema_version': 1, 'salt': salt.hex(), 'iterations': PBKDF_ITERATIONS,
        'digest': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF_ITERATIONS).hex()}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        restrict_private_path(path)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle); handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        # os.O_EXCL above succeeded, so only this invocation created this file.
        path.unlink(missing_ok=True)
        raise
    return password


def initialize_operator_access(config, access_file):
    """Create matching private operator instructions and verifier as one unit."""
    access_file = Path(access_file)
    if config.auth_file.exists():
        return False
    config.runtime.mkdir(parents=True, exist_ok=True)
    restrict_private_path(config.runtime, directory=True)
    access_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(access_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    auth_created = False
    try:
        restrict_private_path(access_file)
        code = secrets.token_urlsafe(18)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write('Voice Studio – privater Zugang\n\n' + config.origin.rstrip('/') +
                config.base_path + '/\n\nZugangscode: ' + code + '\n\n'
                'Diesen Code privat aufbewahren. Eigene Aufnahmen bleiben auf diesem Windows-PC.\n')
            handle.flush(); os.fsync(handle.fileno())
        initialize_auth(config.auth_file, code)
        auth_created = True
        return True
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        access_file.unlink(missing_ok=True)
        if auth_created:
            config.auth_file.unlink(missing_ok=True)
        raise


def read_auth(path):
    path = Path(path)
    if path.stat().st_size > 4096:
        raise ValueError('Invalid authentication configuration')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if (value.get('schema_version') != 1 or value.get('iterations') != PBKDF_ITERATIONS
            or not re.fullmatch('[a-f0-9]{64}', value.get('salt', ''))
            or not re.fullmatch('[a-f0-9]{64}', value.get('digest', ''))):
        raise ValueError('Invalid authentication configuration')
    return value


def password_matches(auth, password):
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(auth['salt']),
        auth['iterations']).hex()
    return hmac.compare_digest(digest, auth['digest'])


def load_manager():
    path = HERE.parent / 'voice-profile' / 'manage_voice.py'
    spec = importlib.util.spec_from_file_location('scc_studio_voice_manager', path)
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    return manager


def safe_profile(profile, selected_id):
    return {'id': profile['profile_id'], 'name': profile['name'],
        'duration_seconds': profile.get('audio', {}).get('duration_seconds'),
        'created_at_utc': profile.get('created_at_utc'),
        'selected': profile['profile_id'] == selected_id,
        'language': profile['language'], 'kind': profile['kind']}


async def bounded_json(request, limit=MAX_BODY_BYTES):
    if request.content_type != 'application/json':
        raise APIError(415, 'json_required', 'Bitte JSON verwenden.')
    if request.content_length is not None and request.content_length > limit:
        raise APIError(413, 'body_too_large', 'Die Aufnahme ist zu groß (maximal 6 MiB WAV).')
    raw = bytearray()
    async for chunk in request.content.iter_chunked(64 * 1024):
        raw.extend(chunk)
        if len(raw) > limit:
            raise APIError(413, 'body_too_large', 'Die Aufnahme ist zu groß (maximal 6 MiB WAV).')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise APIError(400, 'invalid_json', 'Ungültige JSON-Anfrage.') from None
    if not isinstance(value, dict):
        raise APIError(400, 'invalid_json', 'Die Anfrage muss ein JSON-Objekt sein.')
    return value


async def owned_thread(function, *args):
    # A disconnected browser cannot release our operation guard while its native
    # registration/rollback still runs in a worker thread.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        finally:
            raise


def create_app(config, *, manager=None, register=None, idle_check=None, synthesize=None):
    parsed = urlparse(config.origin)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/')
            or parsed.params or parsed.query or parsed.fragment or parsed.username):
        raise ValueError('Configure an exact HTTPS origin, without credentials or path')
    if not re.fullmatch(r'/[a-z0-9-]+', config.base_path):
        raise ValueError('Configure one simple URL base path')
    manager = manager or load_manager()
    auth = read_auth(config.auth_file)
    sessions = {}
    failed_logins = deque()
    operation_lock = asyncio.Lock()
    upload_lock = asyncio.Lock()
    started = datetime.now(timezone.utc).isoformat()

    def session(request):
        now = time.monotonic()
        for key in list(sessions):
            if sessions[key]['expires'] <= now:
                sessions.pop(key, None)
        return sessions.get(request.cookies.get(COOKIE_NAME, ''))

    def authorized(request):
        result = session(request)
        if result is None:
            raise APIError(401, 'sign_in_required', 'Bitte zuerst mit dem Zugangscode anmelden.')
        return result

    def origin_check(request):
        if request.headers.get('Origin') != config.origin.rstrip('/'):
            raise APIError(403, 'origin_rejected', 'Die Anfrage stammt nicht von Voice Studio.')

    def mutation_check(request):
        origin_check(request)
        found = authorized(request)
        token = request.headers.get('X-CSRF-Token', '')
        if not token or not token.isascii() or not hmac.compare_digest(token, found['csrf']):
            raise APIError(403, 'csrf_rejected', 'Bitte die Seite neu laden und erneut versuchen.')

    def selected_id():
        selected = manager.selected_profile(config.profile_root)
        return selected['profile_id'] if selected else None

    def profile_by_id(profile_id):
        if profile_id == 'synthetic-scc-demo':
            folder = manager.DEFAULT_PROFILE
        elif ID_RE.fullmatch(profile_id):
            folder = config.profile_root / 'revisions' / profile_id
            if folder.resolve().parent != (config.profile_root / 'revisions').resolve():
                raise APIError(404, 'profile_not_found', 'Stimmprofil nicht gefunden.')
        else:
            raise APIError(404, 'profile_not_found', 'Stimmprofil nicht gefunden.')
        try:
            profile = manager.read_profile(folder)
        except FileNotFoundError:
            raise APIError(404, 'profile_not_found', 'Stimmprofil nicht gefunden.') from None
        if profile['profile_id'] != profile_id:
            raise APIError(404, 'profile_not_found', 'Stimmprofil nicht gefunden.')
        return profile

    async def default_idle_check():
        async with ClientSession(timeout=ClientTimeout(total=3)) as http:
            async with http.get('http://127.0.0.1:8860/health', allow_redirects=False) as response:
                if response.status != 200:
                    raise RuntimeError('Native bridge unavailable')
                raw = await response.content.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    raise RuntimeError('Native bridge health exceeds limit')
                value = json.loads(raw).get('nativeSessions')
                if type(value) is not int or value < 0:
                    raise RuntimeError('Native bridge session status missing')
                return value

    async def require_idle():
        count = await (idle_check or default_idle_check)()
        if type(count) is not int or count < 0:
            raise RuntimeError('Invalid native session status')
        if count:
            raise APIError(409, 'call_in_progress',
                'Ein Gespräch läuft. Bitte nach dem Gespräch erneut versuchen; '
                'die gewählte Stimme gilt für den nächsten Now-Anruf.')

    def default_synthesize(text):
        payload = {'model': 'scc-native-qwen3', 'voice': manager.VOICE_ALIAS,
            'input': text, 'response_format': 'pcm', 'seed': 42, 'max_new_tokens': 192}
        native = manager.native_module()
        raw, _ = native.request(8862, '/v1/audio/speech', 'POST',
            json.dumps(payload).encode('utf-8'), timeout=90)
        return raw

    @web.middleware
    async def boundary(request, handler):
        try:
            response = await handler(request)
        except APIError as error:
            response = web.json_response({'error': error.message, 'code': error.code}, status=error.status)
        except web.HTTPRedirection as redirect:
            response = web.Response(status=redirect.status, body=redirect.body, headers=redirect.headers)
        except web.HTTPException as error:
            response = web.json_response({'error': 'Anfrage nicht verfügbar.',
                'code': 'not_found' if error.status == 404 else 'request_rejected'}, status=error.status)
        except ValueError as error:
            # Manager input errors carry only validation instructions, never paths.
            response = web.json_response({'error': str(error), 'code': 'validation_failed'}, status=400)
        except Exception as error:
            LOG.error('Voice Studio operation failed: %s', type(error).__name__)
            response = web.json_response({'error':
                'Die Aktion konnte nicht abgeschlossen werden. Bitte den lokalen Sprachdienst '
                'und die aktuelle Stimmwahl prüfen und erneut versuchen.',
                'code': 'speech_service_unavailable'}, status=503)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Permissions-Policy': 'microphone=(self), camera=()',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    async def health(request):
        return web.json_response({'status': 'ok', 'service': 'scc-voice-studio',
            'version': 1, 'started_at_utc': started})

    async def get_session(request):
        found = session(request)
        value = {'authenticated': bool(found), 'reference_text': REFERENCE_TEXT,
            'max_recording_seconds': 25}
        if found:
            value['csrf'] = found['csrf']
        return web.json_response(value)

    async def login(request):
        origin_check(request)
        now = time.monotonic()
        while failed_logins and failed_logins[0] < now - 600:
            failed_logins.popleft()
        if len(failed_logins) >= 5:
            raise APIError(429, 'login_throttled', 'Zu viele Anmeldeversuche. Bitte in zehn Minuten erneut versuchen.')
        data = await bounded_json(request, 2048)
        if not await owned_thread(password_matches, auth, data.get('password')):
            failed_logins.append(now)
            raise APIError(401, 'invalid_access_code', 'Der Zugangscode ist nicht korrekt.')
        session(request)  # Prune expired entries.
        if len(sessions) >= 64:
            sessions.pop(next(iter(sessions)))
        old = request.cookies.get(COOKIE_NAME, '')
        sessions.pop(old, None)
        identifier = secrets.token_urlsafe(32)
        value = {'csrf': secrets.token_urlsafe(32), 'expires': now + SESSION_SECONDS}
        sessions[identifier] = value
        response = web.json_response({'authenticated': True, 'csrf': value['csrf']})
        response.set_cookie(COOKIE_NAME, identifier, max_age=SESSION_SECONDS, secure=True,
            httponly=True, samesite='Strict', path='/')
        return response

    async def logout(request):
        mutation_check(request)
        sessions.pop(request.cookies.get(COOKIE_NAME, ''), None)
        response = web.json_response({'authenticated': False})
        response.del_cookie(COOKIE_NAME, path='/')
        return response

    async def profiles(request):
        authorized(request)
        def listing():
            active = selected_id()
            results = []
            if manager.DEFAULT_PROFILE.is_dir():
                results.append(safe_profile(manager.read_profile(manager.DEFAULT_PROFILE), active))
            revisions = config.profile_root / 'revisions'
            if revisions.is_dir():
                for folder in sorted(revisions.iterdir(), reverse=True):
                    if ID_RE.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink():
                        try:
                            results.append(safe_profile(profile_by_id(folder.name), active))
                        except (ValueError, FileNotFoundError, APIError):
                            LOG.warning('Skipping invalid immutable voice revision')
            return {'profiles': results, 'selected_profile_id': active, 'active_voice': manager.VOICE_ALIAS}
        return web.json_response(await owned_thread(listing))

    async def upload(request):
        mutation_check(request)
        if upload_lock.locked():
            raise APIError(409, 'upload_in_progress', 'Eine Aufnahme wird bereits gespeichert. Bitte kurz warten.')
        async with upload_lock:
            data = await bounded_json(request)
            encoded = data.get('wav_b64')
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_WAV_BYTES + 2) // 3):
                raise APIError(413, 'audio_too_large', 'Die WAV-Aufnahme fehlt oder überschreitet 6 MiB.')
            try:
                audio = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise APIError(400, 'invalid_audio', 'Die WAV-Aufnahme ist nicht gültig kodiert.') from None
            if len(audio) > MAX_WAV_BYTES:
                raise APIError(413, 'audio_too_large', 'Die WAV-Aufnahme überschreitet 6 MiB.')
            metadata = {key: data.get(key) for key in
                ('name', 'reference_text', 'language', 'source', 'consent')}
            manager.validate_consent(metadata)
            def persist():
                config.runtime.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='upload-', dir=config.runtime) as temporary:
                    wav_path = Path(temporary) / 'recording.wav'
                    wav_path.write_bytes(audio)
                    profile = manager.stage(dict(metadata, wav_path=str(wav_path)), config.profile_root)
                return safe_profile(profile, selected_id())
            profile = await owned_thread(persist)
            return web.json_response({'profile': profile, 'active': False}, status=201)

    async def audio(request):
        authorized(request)
        def read_audio():
            profile = profile_by_id(request.match_info['profile_id'])
            return (Path(profile['profile_dir']) / 'reference.wav').read_bytes()
        return web.Response(body=await owned_thread(read_audio), content_type='audio/wav')

    async def activate(request):
        mutation_check(request)
        await bounded_json(request, 2048)
        if operation_lock.locked():
            raise APIError(409, 'voice_operation_in_progress', 'Eine Stimmaktion läuft bereits. Bitte kurz warten.')
        async with operation_lock:
            await require_idle()
            def select():
                profile = profile_by_id(request.match_info['profile_id'])
                if profile['profile_id'] == 'synthetic-scc-demo':
                    result = manager.restore_synthetic(config.profile_root, register=register)
                else:
                    result = manager.activate(profile['profile_dir'], config.profile_root, register=register)
                return {'profile': safe_profile(profile, result['profile_id']),
                    'selected_profile_id': result['profile_id'], 'active_voice': manager.VOICE_ALIAS}
            return web.json_response(await owned_thread(select))

    async def preview(request):
        mutation_check(request)
        data = await bounded_json(request, 4096)
        text = data.get('text', PREVIEW_TEXT)
        if not isinstance(text, str) or not 3 <= len(text.strip()) <= 300:
            raise APIError(400, 'invalid_preview_text', 'Bitte einen kurzen deutschen Text mit 3–300 Zeichen verwenden.')
        if operation_lock.locked():
            raise APIError(409, 'voice_operation_in_progress', 'Eine Stimmaktion läuft bereits. Bitte kurz warten.')
        async with operation_lock:
            await require_idle()
            def render():
                with manager.activation_lock(config.profile_root):
                    if not manager.selected_profile(config.profile_root):
                        raise APIError(409, 'no_selected_voice', 'Bitte zuerst ein Stimmprofil auswählen.')
                    pcm = (synthesize or default_synthesize)(text.strip())
                    if not pcm or len(pcm) % 2 or len(pcm) > 2_000_000 or pcm.startswith(b'RIFF'):
                        raise RuntimeError('TTS returned invalid or oversized PCM')
                    output = io.BytesIO()
                    with wave.open(output, 'wb') as wav:
                        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
                        wav.writeframes(pcm)
                    return output.getvalue()
            return web.Response(body=await owned_thread(render), content_type='audio/wav')

    async def static(request):
        tail = request.match_info.get('tail', '') or 'index.html'
        if tail.startswith('api/') or tail == 'api' or '\\' in tail:
            raise web.HTTPNotFound()
        root = config.web_root.resolve()
        target = (root / tail).resolve()
        if (not target.is_relative_to(root) or not target.is_file() or target.suffix not in
                ('.html', '.js', '.css', '.svg', '.png', '.ico', '.woff2')):
            raise web.HTTPNotFound()
        return web.FileResponse(target)

    async def base_redirect(request):
        raise web.HTTPFound(config.base_path + '/')

    app = web.Application(middlewares=[boundary], client_max_size=MAX_BODY_BYTES)
    for prefix in ('', config.base_path):
        app.router.add_get(prefix + '/health', health)
        app.router.add_get(prefix + '/api/session', get_session)
        app.router.add_post(prefix + '/api/login', login)
        app.router.add_post(prefix + '/api/logout', logout)
        app.router.add_get(prefix + '/api/profiles', profiles)
        app.router.add_post(prefix + '/api/profiles', upload)
        app.router.add_get(prefix + '/api/profiles/{profile_id}/audio', audio)
        app.router.add_post(prefix + '/api/profiles/{profile_id}/activate', activate)
        app.router.add_post(prefix + '/api/preview', preview)
    app.router.add_get(config.base_path, base_redirect)
    app.router.add_get(config.base_path + '/{tail:.*}', static)
    app.router.add_get('/{tail:.*}', static)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1'])
    parser.add_argument('--port', type=int, default=8863)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--base-path', default='/voice-studio')
    parser.add_argument('--runtime', type=Path, default=HERE / 'runtime')
    parser.add_argument('--init-auth', action='store_true')
    parser.add_argument('--access-file', type=Path)
    args = parser.parse_args()
    config = Config(origin=args.origin, runtime=args.runtime, base_path=args.base_path)
    if args.init_auth:
        if not args.access_file:
            parser.error('--init-auth requires --access-file')
        initialized = initialize_operator_access(config, args.access_file)
        print(json.dumps({'ok': True, 'initialized': initialized,
            'credentials_written': initialized, 'existing_credentials_preserved': not initialized}))
        return 0
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    web.run_app(create_app(config), host=args.host, port=args.port, access_log=None,
        print=lambda message: LOG.info('Voice Studio listening on owned loopback port %s', args.port),
        shutdown_timeout=120)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
