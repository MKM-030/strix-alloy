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
import shutil
import stat
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
PERSONAL_ID_RE = re.compile(r'personal-[a-f0-9]{16}\Z')
PERSONAL_CODE_RE = re.compile(r'VSP-([a-f0-9]{16})-[A-Za-z0-9_-]{24}\Z')
ADMIN_PRINCIPAL = 'administrator'
MAX_PERSONAL_CODES = 64
MAX_FAILED_PURGES = 8
MAX_QUARANTINE_BYTES = 64 * 1024 * 1024
REFERENCE_TEXT = ('Willkommen zur Smart Country Convention. Mit Sopra Steria und ServiceNow '
    'erlebe ich, wie einfach digitale Services werden. Bitte helfen Sie mir, '
    'einen neuen Laptop für meinen Mitarbeiter zu bestellen.')
PREVIEW_TEXT = 'Guten Tag. Wie kann ich Ihnen helfen?'
LOG = logging.getLogger('scc.voice_studio')


@dataclass(frozen=True)
class Config:
    origin: str
    runtime: Path = HERE / 'runtime'
    profile_root: Path = HERE.parent / 'voice-profile' / 'runtime' / 'profiles'
    web_root: Path = HERE / 'web'
    base_path: str = '/voice-studio'
    retention_policy: Path = HERE / 'retention-policy.json'

    @property
    def auth_file(self):
        return self.runtime / 'auth.json'

    @property
    def personal_codes_file(self):
        return self.runtime / 'access-codes.json'


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
    value = make_verifier(password)
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
    validate_verifier(value)
    return value


def make_verifier(password):
    salt = secrets.token_bytes(32)
    return {'schema_version': 1, 'salt': salt.hex(), 'iterations': PBKDF_ITERATIONS,
        'digest': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF_ITERATIONS).hex()}


def validate_verifier(value):
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or value.get('iterations') != PBKDF_ITERATIONS
            or not re.fullmatch('[a-f0-9]{64}', value.get('salt', ''))
            or not re.fullmatch('[a-f0-9]{64}', value.get('digest', ''))):
        raise ValueError('Invalid authentication configuration')


def atomic_private_json(path, value):
    """Publish complete metadata with a private DACL before the atomic replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(16) + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        restrict_private_path(temporary)
        handle = os.fdopen(descriptor, 'w', encoding='utf-8')
        descriptor = None  # The handle owns it; never close a reused FD twice.
        with handle:
            json.dump(value, handle, ensure_ascii=False); handle.write('\n')
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def read_personal_codes(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.stat().st_size > 128 * 1024:
        raise ValueError('Invalid personal access-code configuration')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    entries = value.get('codes')
    if value.get('schema_version') != 1 or not isinstance(entries, list) or len(entries) > MAX_PERSONAL_CODES:
        raise ValueError('Invalid personal access-code configuration')
    result = {}
    for entry in entries:
        identifier = entry.get('id', '')
        if (not PERSONAL_ID_RE.fullmatch(identifier) or identifier in result
                or not isinstance(entry.get('label'), str) or not 1 <= len(entry['label']) <= 80
                or not isinstance(entry.get('created_at_utc'), str)):
            raise ValueError('Invalid personal access-code identity')
        validate_verifier(entry.get('verifier'))
        result[identifier] = entry
    return result


def public_access_code(entry):
    return {key: entry[key] for key in ('id', 'label', 'created_at_utc')}


def read_retention_policy(path):
    path = Path(path)
    if path.stat().st_size > 4096:
        raise ValueError('Invalid fair retention policy')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if (value.get('schema_version') != 1 or value.get('scope') != 'authorized_own_voice_demo_recordings'
            or value.get('keep_access_codes') is not True or value.get('keep_packaged_synthetic_voice') is not True):
        raise ValueError('Invalid fair retention policy')
    deadline = datetime.fromisoformat(value['due_at_utc'].replace('Z', '+00:00'))
    if deadline.utcoffset() is None or deadline.utcoffset().total_seconds() != 0:
        raise ValueError('Fair retention deadline must be timezone-aware UTC')
    return value, deadline


def is_reparse_path(path):
    info = Path(path).lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) &
        getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def revision_owner(folder):
    path = Path(folder) / 'owner.json'
    if not path.exists():
        return ADMIN_PRINCIPAL
    if is_reparse_path(path) or path.stat().st_size > 4096:
        raise ValueError('Invalid voice ownership metadata')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    owner = value.get('principal_id', '')
    if value.get('schema_version') != 1 or (owner != ADMIN_PRINCIPAL and not PERSONAL_ID_RE.fullmatch(owner)):
        raise ValueError('Invalid voice ownership metadata')
    return owner


def plain_revision_size(folder):
    """Staged revisions are flat files. Reject symlinks, junctions and directories."""
    folder = Path(folder)
    if is_reparse_path(folder) or not folder.is_dir():
        raise APIError(403, 'profile_unsafe_path', 'Dieses Profil kann nicht sicher gelöscht werden.')
    size = 0
    for child in folder.iterdir():
        info = child.lstat()
        if is_reparse_path(child) or not stat.S_ISREG(info.st_mode):
            raise APIError(403, 'profile_unsafe_path', 'Dieses Profil kann nicht sicher gelöscht werden.')
        size += info.st_size
    return size


def purge_quarantined_revision(folder, quarantine_root):
    folder, quarantine_root = Path(folder), Path(quarantine_root)
    if is_reparse_path(quarantine_root) or folder.resolve().parent != quarantine_root.resolve():
        raise APIError(403, 'profile_unsafe_path', 'Die Löschung wurde aus Sicherheitsgründen angehalten.')
    plain_revision_size(folder)
    shutil.rmtree(folder)
    if folder.exists():
        raise OSError('Quarantined profile remains after purge')


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


def create_app(config, *, manager=None, register=None, idle_check=None, synthesize=None, now=None):
    parsed = urlparse(config.origin)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/')
            or parsed.params or parsed.query or parsed.fragment or parsed.username):
        raise ValueError('Configure an exact HTTPS origin, without credentials or path')
    if not re.fullmatch(r'/[a-z0-9-]+', config.base_path):
        raise ValueError('Configure one simple URL base path')
    manager = manager or load_manager()
    auth = read_auth(config.auth_file)
    personal_codes = read_personal_codes(config.personal_codes_file)
    retention, deadline = read_retention_policy(config.retention_policy)
    utc_clock = now or (lambda: datetime.now(timezone.utc))
    sessions = {}
    failed_logins = deque()
    operation_lock = asyncio.Lock()
    upload_lock = asyncio.Lock()
    code_lock = asyncio.Lock()
    started = datetime.now(timezone.utc).isoformat()

    def fair_expired_error():
        return APIError(409, 'fair_retention_expired',
            'Die Messe ist beendet. Neue Demo-Aufnahmen und eigene Stimmwahlen sind nicht mehr möglich. '
            'Die Demo-Aufnahmen werden automatisch gelöscht.')

    def require_fair_open():
        if utc_clock() >= deadline:
            raise fair_expired_error()

    class ExpiredRegistration(manager.RegistrationRejected):
        """A due-time gate rejects before native HTTP, without a rollback call."""

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
        return found

    def public_session(found):
        return {key: found[key] for key in ('principal_id', 'is_admin', 'label')}

    def identity_for_password(password):
        if password_matches(auth, password):
            return {'principal_id': ADMIN_PRINCIPAL, 'is_admin': True,
                'label': 'Administrator', 'verifier': auth}
        matched = PERSONAL_CODE_RE.fullmatch(password) if isinstance(password, str) else None
        entry = personal_codes.get('personal-' + matched[1]) if matched else None
        if entry and password_matches(entry['verifier'], password):
            return {'principal_id': entry['id'], 'is_admin': False,
                'label': entry['label'], 'verifier': entry['verifier']}
        return None

    def visible_profile(profile, active, found):
        value = safe_profile(profile, active)
        own = revision_owner(profile['profile_dir']) == found['principal_id']
        value.update(owner_is_self=own, can_delete=bool((own or found['is_admin']) and
            profile['profile_id'] != 'synthetic-scc-demo'))
        return value

    def administrator(request):
        found = authorized(request)
        if not found['is_admin']:
            raise APIError(403, 'admin_required', 'Nur der Administrator kann persönliche Zugangscodes verwalten.')
        return found

    def selected_id():
        selected = manager.selected_profile(config.profile_root)
        return selected['profile_id'] if selected else None

    def profile_by_id(profile_id):
        if profile_id == 'synthetic-scc-demo':
            folder = manager.DEFAULT_PROFILE
        elif ID_RE.fullmatch(profile_id):
            folder = config.profile_root / 'revisions' / profile_id
            if (folder.is_symlink() or (folder.exists() and is_reparse_path(folder))
                    or folder.resolve().parent != (config.profile_root / 'revisions').resolve()):
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
            'max_recording_seconds': 25, 'recording_allowed': utc_clock() < deadline,
            'retention_due_at_utc': retention['due_at_utc']}
        if found:
            value['csrf'] = found['csrf']
            value.update(public_session(found))
        return web.json_response(value)

    async def login(request):
        origin_check(request)
        now = time.monotonic()
        while failed_logins and failed_logins[0] < now - 600:
            failed_logins.popleft()
        if len(failed_logins) >= 5:
            raise APIError(429, 'login_throttled', 'Zu viele Anmeldeversuche. Bitte in zehn Minuten erneut versuchen.')
        data = await bounded_json(request, 2048)
        identity = await owned_thread(identity_for_password, data.get('password'))
        if not identity:
            failed_logins.append(now)
            raise APIError(401, 'invalid_access_code', 'Der Zugangscode ist nicht korrekt.')
        session(request)  # Prune expired entries.
        if len(sessions) >= 64:
            sessions.pop(next(iter(sessions)))
        old = request.cookies.get(COOKIE_NAME, '')
        sessions.pop(old, None)
        identifier = secrets.token_urlsafe(32)
        value = dict(identity, csrf=secrets.token_urlsafe(32), expires=now + SESSION_SECONDS)
        sessions[identifier] = value
        response = web.json_response(dict(public_session(value), authenticated=True, csrf=value['csrf']))
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
        found = authorized(request)
        def listing():
            active = selected_id()
            results = []
            if manager.DEFAULT_PROFILE.is_dir():
                results.append(visible_profile(manager.read_profile(manager.DEFAULT_PROFILE), active, found))
            revisions = config.profile_root / 'revisions'
            if revisions.is_dir():
                for folder in sorted(revisions.iterdir(), reverse=True):
                    if ID_RE.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink():
                        try:
                            results.append(visible_profile(profile_by_id(folder.name), active, found))
                        except (ValueError, FileNotFoundError, APIError):
                            LOG.warning('Skipping invalid immutable voice revision')
            return {'profiles': results, 'selected_profile_id': active, 'active_voice': manager.VOICE_ALIAS}
        return web.json_response(await owned_thread(listing))

    async def upload(request):
        found = mutation_check(request)
        require_fair_open()
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
                require_fair_open()
                config.runtime.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='upload-', dir=config.runtime) as temporary:
                    wav_path = Path(temporary) / 'recording.wav'
                    wav_path.write_bytes(audio)
                    # Ownership is complete before this immutable revision is
                    # atomically made visible to profile readers or activation.
                    profile = manager.stage(dict(metadata, wav_path=str(wav_path)), Path(temporary) / 'profiles')
                    staged = Path(profile['profile_dir'])
                    atomic_private_json(staged / 'owner.json', {'schema_version': 1,
                        'principal_id': found['principal_id']})
                    revisions = config.profile_root / 'revisions'
                    revisions.mkdir(parents=True, exist_ok=True)
                    target = revisions / profile['profile_id']
                    # Cleanup owns the same lock. A request which started before
                    # the deadline cannot publish a late normalized recording.
                    with manager.activation_lock(config.profile_root):
                        require_fair_open()
                        staged.rename(target)
                    profile['profile_dir'] = str(target)
                return visible_profile(profile, selected_id(), found)
            profile = await owned_thread(persist)
            return web.json_response({'profile': profile, 'active': False}, status=201)

    async def audio(request):
        authorized(request)
        def read_audio():
            profile = profile_by_id(request.match_info['profile_id'])
            return (Path(profile['profile_dir']) / 'reference.wav').read_bytes()
        return web.Response(body=await owned_thread(read_audio), content_type='audio/wav')

    async def activate(request):
        found = mutation_check(request)
        await bounded_json(request, 2048)
        if request.match_info['profile_id'] != 'synthetic-scc-demo':
            require_fair_open()
        if operation_lock.locked():
            raise APIError(409, 'voice_operation_in_progress', 'Eine Stimmaktion läuft bereits. Bitte kurz warten.')
        async with operation_lock:
            await require_idle()
            def select():
                profile = profile_by_id(request.match_info['profile_id'])
                if profile['profile_id'] == 'synthetic-scc-demo':
                    result = manager.restore_synthetic(config.profile_root, register=register)
                else:
                    first_registration = True
                    def fair_register(value):
                        nonlocal first_registration
                        if first_registration:
                            # manager.activate already owns its OS lock here.
                            if utc_clock() >= deadline:
                                raise ExpiredRegistration('Fair retention deadline passed before registration')
                            first_registration = False
                        # Rollback of a genuine ambiguous native failure must
                        # still restore the prior voice even across the deadline.
                        return (register or manager.native_register)(value)
                    try:
                        result = manager.activate(profile['profile_dir'], config.profile_root, register=fair_register)
                    except ExpiredRegistration:
                        raise fair_expired_error() from None
                return {'profile': visible_profile(profile, result['profile_id'], found),
                    'selected_profile_id': result['profile_id'], 'active_voice': manager.VOICE_ALIAS}
            return web.json_response(await owned_thread(select))

    async def get_access_codes(request):
        administrator(request)
        return web.json_response({'access_codes': [public_access_code(entry) for entry in personal_codes.values()]})

    async def create_access_code(request):
        mutation_check(request); administrator(request)
        data = await bounded_json(request, 2048)
        label = data.get('label')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
            raise APIError(400, 'invalid_access_label', 'Bitte einen Namen mit 1–80 Zeichen für den Zugang eingeben.')
        if code_lock.locked():
            raise APIError(409, 'access_code_operation_in_progress', 'Ein Zugangscode wird bereits angelegt. Bitte kurz warten.')
        async with code_lock:
            if len(personal_codes) >= MAX_PERSONAL_CODES:
                raise APIError(409, 'access_code_limit', 'Die maximale Anzahl persönlicher Zugänge ist erreicht.')
            identifier = 'personal-' + secrets.token_hex(8)
            code = 'VSP-' + identifier.removeprefix('personal-') + '-' + secrets.token_urlsafe(18)
            def persist_code():
                entry = {'id': identifier, 'label': label.strip(),
                    'created_at_utc': manager.utc_now(), 'verifier': make_verifier(code)}
                atomic_private_json(config.personal_codes_file, {'schema_version': 1,
                    'codes': list(personal_codes.values()) + [entry]})
                return entry
            entry = await owned_thread(persist_code)
            personal_codes[identifier] = entry
            return web.json_response({'access_code': public_access_code(entry), 'code': code}, status=201)

    async def delete_profile(request):
        found = mutation_check(request)
        data = await bounded_json(request, 2048)
        password = data.get('password')
        def verify_confirmation():
            if password_matches(auth, password):
                return True, True
            return password_matches(found['verifier'], password), found['is_admin']
        confirmed, admin_override = await owned_thread(verify_confirmation)
        if not confirmed:
            raise APIError(403, 'delete_confirmation_rejected', 'Bitte den eigenen Zugangscode oder den Administratorcode bestätigen.')
        if operation_lock.locked():
            raise APIError(409, 'voice_operation_in_progress', 'Eine Stimmaktion läuft bereits. Bitte kurz warten.')
        async with operation_lock:
            await require_idle()
            def remove():
                profile_id = request.match_info['profile_id']
                if profile_id == 'synthetic-scc-demo':
                    raise APIError(403, 'profile_protected', 'Die mitgelieferte Standardstimme kann nicht gelöscht werden.')
                try:
                    with manager.activation_lock(config.profile_root):
                        profile = profile_by_id(profile_id)
                        folder = Path(profile['profile_dir'])
                        revisions = config.profile_root / 'revisions'
                        if is_reparse_path(revisions) or folder.parent != revisions.resolve():
                            raise APIError(403, 'profile_unsafe_path', 'Dieses Profil kann nicht sicher gelöscht werden.')
                        if not admin_override and revision_owner(folder) != found['principal_id']:
                            raise APIError(403, 'profile_delete_forbidden', 'Mit diesem Zugang können nur eigene Stimmprofile gelöscht werden.')
                        if selected_id() == profile_id:
                            raise APIError(409, 'selected_voice_protected', 'Diese Stimme ist ausgewählt. Bitte zuerst eine andere Stimme wählen.')
                        size = plain_revision_size(folder)
                        quarantine = config.runtime / 'delete-quarantine'
                        quarantine.mkdir(parents=True, exist_ok=True)
                        if is_reparse_path(quarantine):
                            raise APIError(403, 'profile_unsafe_path', 'Die Löschung wurde aus Sicherheitsgründen angehalten.')
                        restrict_private_path(quarantine, directory=True)
                        journal_root = config.runtime / 'delete-journal'
                        journal_root.mkdir(parents=True, exist_ok=True)
                        if is_reparse_path(journal_root):
                            raise APIError(403, 'profile_unsafe_path', 'Die Löschung wurde aus Sicherheitsgründen angehalten.')
                        restrict_private_path(journal_root, directory=True)
                        retained = list(quarantine.iterdir())
                        if (len(retained) >= MAX_FAILED_PURGES or len(list(journal_root.iterdir())) >= MAX_FAILED_PURGES or
                                sum(plain_revision_size(item) for item in retained) + size > MAX_QUARANTINE_BYTES):
                            raise APIError(503, 'delete_quarantine_full', 'Eine frühere Löschung muss zuerst vom Administrator geprüft werden.')
                        operation_id = secrets.token_hex(16)
                        target = quarantine / (profile_id + '-' + operation_id)
                        journal = journal_root / (operation_id + '.json')
                        record = {'schema_version': 1, 'profile_id': profile_id,
                            'requested_by': found['principal_id'], 'quarantine_name': target.name,
                            'created_at_utc': manager.utc_now(), 'status': 'pending_purge'}
                        atomic_private_json(journal, record)
                        try:
                            folder.rename(target)
                        except Exception:
                            journal.unlink(missing_ok=True)
                            raise
                        try:
                            purge_quarantined_revision(target, quarantine)
                        except Exception:
                            atomic_private_json(journal, dict(record, status='purge_failed'))
                            raise APIError(503, 'delete_purge_failed',
                                'Die endgültige Löschung ist fehlgeschlagen. Das Profil wurde aus der Liste genommen; '
                                'verbliebene Daten sind privat gesperrt. Bitte den Administrator informieren.') from None
                        try:
                            journal.unlink()
                        except OSError:
                            atomic_private_json(journal, dict(record, status='purged', completed_at_utc=manager.utc_now()))
                            raise APIError(503, 'delete_finalize_failed',
                                'Die Audiodaten wurden gelöscht, aber die Abschlussbestätigung ist fehlgeschlagen. '
                                'Bitte den Administrator informieren.') from None
                        return {'id': profile_id, 'deleted': True}
                except RuntimeError as error:
                    if str(error) == 'Another voice activation is in progress':
                        raise APIError(409, 'voice_operation_in_progress', 'Eine Stimmaktion läuft bereits. Bitte kurz warten.') from None
                    raise
            return web.json_response(await owned_thread(remove))

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
        app.router.add_delete(prefix + '/api/profiles/{profile_id}', delete_profile)
        app.router.add_get(prefix + '/api/profiles/{profile_id}/audio', audio)
        app.router.add_post(prefix + '/api/profiles/{profile_id}/activate', activate)
        app.router.add_post(prefix + '/api/preview', preview)
        app.router.add_get(prefix + '/api/access-codes', get_access_codes)
        app.router.add_post(prefix + '/api/access-codes', create_access_code)
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
