"""Caller-authorized immutable reference cache; no business or model authority.

Every preparation fetches the selected reference through the existing native
authorization resource, including cache hits. The injected registrar must own
the configured loopback listener and enforce the existing memory reserve.
Neither cached WAVs nor process-bound registration receipts grant access.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import wave

from aiohttp import ClientTimeout

MAX_WAV_BYTES = 6 * 1024 * 1024
MAX_CACHE_ENTRIES = 32
RESOURCE = '/api/sn_voice_aia/ai_voice_agent/agents_authorized'
_ID = re.compile(r'[0-9a-f]{32}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_LANGUAGE = re.compile(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z')
_FIELDS = {'version', 'service_id', 'tts_config_sys_id', 'voice_id', 'attachment_sys_id',
           'sha256', 'size_bytes', 'reference_text', 'reference_language', 'provenance'}
_PROVENANCE = {'kind', 'profile_id', 'consent_scope', 'confirmed_at_utc'}


class ReferenceUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Authorized voice reference unavailable')


def _text(value, minimum, maximum):
    return (type(value) is str and minimum <= len(value) <= maximum
            and bool(value.strip()) and not any(ord(char) < 32 for char in value))


def _language(value):
    return type(value) is str and len(value) <= 64 and bool(_LANGUAGE.fullmatch(value))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def reference_fingerprint(reference):
    """Bind already validated reference metadata, including transcript/provenance."""
    return hashlib.sha256(_canonical(reference)).hexdigest()


def validate_reference(reference, service_id, tts_config_sys_id, voice_id):
    """Validate the complete descriptor against the selected native identities."""
    try:
        if (any(type(value) is not str or not _ID.fullmatch(value)
                for value in (service_id, tts_config_sys_id))
                or not _text(voice_id, 1, 256) or voice_id.strip() != voice_id
                or type(reference) is not dict or set(reference) != _FIELDS
                or type(reference['version']) is not int or reference['version'] != 1
                or reference['service_id'] != service_id
                or reference['tts_config_sys_id'] != tts_config_sys_id
                or reference['voice_id'] != voice_id
                or type(reference['attachment_sys_id']) is not str
                or not _ID.fullmatch(reference['attachment_sys_id'])
                or type(reference['sha256']) is not str or not _SHA.fullmatch(reference['sha256'])
                or type(reference['size_bytes']) is not int
                or not 44 <= reference['size_bytes'] <= MAX_WAV_BYTES
                or not _text(reference['reference_text'], 5, 1500)
                or not _language(reference['reference_language'])):
            raise ValueError()
        provenance = reference['provenance']
        if (type(provenance) is not dict or set(provenance) != _PROVENANCE
                or provenance['kind'] != 'authorized_own_voice'
                or provenance['consent_scope'] != 'local_synthetic_voice_and_servicenow_demo'
                or type(provenance['profile_id']) is not str
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', provenance['profile_id'])
                or not _text(provenance['confirmed_at_utc'], 1, 80)):
            raise ValueError()
        confirmed = datetime.fromisoformat(provenance['confirmed_at_utc'].replace('Z', '+00:00'))
        if confirmed.tzinfo is None or confirmed.utcoffset() is None or len(_canonical(reference)) > 8192:
            raise ValueError()
        return deepcopy(reference)
    except Exception:
        raise ReferenceUnavailable() from None


def _validate_wav(data, reference):
    if (len(data) != reference['size_bytes']
            or hashlib.sha256(data).hexdigest() != reference['sha256']):
        raise ReferenceUnavailable()
    try:
        with wave.open(io.BytesIO(data), 'rb') as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            frames = wav.getnframes()
            if (wav.getcomptype() != 'NONE' or width != 2 or channels not in (1, 2)
                    or not 8000 <= rate <= 48000 or not 3 <= frames / rate <= 30
                    or len(wav.readframes(frames)) != frames * channels * width):
                raise ValueError()
    except Exception:
        raise ReferenceUnavailable() from None


@dataclass(frozen=True)
class PreparedVoice:
    service_id: str
    tts_config_sys_id: str
    selected_voice_id: str
    registry_voice_id: str
    descriptor_sha256: str
    reference_sha256: str
    reference_language: str
    wav_path: Path


class ReferenceCache:
    def __init__(self, http, instance_url, cache_root, *, register, owner_identity):
        if (type(instance_url) is not str
                or not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.service-now\.com', instance_url)
                or not callable(register) or not callable(owner_identity)):
            raise ReferenceUnavailable()
        self.http, self.url = http, instance_url + RESOURCE
        self.root = Path(cache_root).resolve()
        if str(self.root).startswith(('\\\\', '//')):
            raise ReferenceUnavailable()
        self.register, self.owner_identity = register, owner_identity
        self._locks, self._registered = {}, {}

    def _owner(self):
        owner = self.owner_identity()
        if (type(owner) is not tuple or len(owner) != 2 or type(owner[0]) is not int or owner[0] <= 0
                or type(owner[1]) not in (int, float) or not math.isfinite(owner[1]) or owner[1] <= 0):
            raise ReferenceUnavailable()
        return owner

    async def _fetch(self, service_id, language, reference, authorization):
        async with self.http.post(self.url,
                json={'serviceId':service_id, 'assistantSettingsVersion':1, 'voiceReferenceVersion':1,
                      'language':language, 'reference':reference},
                headers={'Authorization':authorization, 'Accept':'audio/wav', 'Accept-Encoding':'identity'},
                allow_redirects=False, auto_decompress=False, timeout=ClientTimeout(total=25)) as response:
            if (response.status != 200
                    or response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'audio/wav'
                    or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
                raise ReferenceUnavailable()
            length = response.headers.get('Content-Length')
            if length is not None and (not length.isdecimal() or int(length) != reference['size_bytes']):
                raise ReferenceUnavailable()
            data = bytearray()
            while True:
                chunk = await response.content.read(min(65536, reference['size_bytes'] + 1 - len(data)))
                data.extend(chunk)
                if len(data) > reference['size_bytes']:
                    raise ReferenceUnavailable()
                if not chunk:
                    break
            return bytes(data)

    def _cached(self, folder, reference, data):
        wav, metadata = folder / 'reference.wav', folder / 'reference.json'
        if folder.is_symlink() or wav.is_symlink() or metadata.is_symlink():
            raise ReferenceUnavailable()
        if (wav.stat().st_size != reference['size_bytes'] or metadata.stat().st_size > 8192
                or wav.read_bytes() != data or json.loads(metadata.read_text(encoding='utf-8')) != reference):
            raise ReferenceUnavailable()
        return wav

    def _cache(self, alias, reference, data):
        self.root.mkdir(parents=True, exist_ok=True)
        folder = self.root / alias
        if folder.exists():
            return self._cached(folder, reference, data)
        if sum(path.is_dir() and path.name.startswith('snref-') for path in self.root.iterdir()) >= MAX_CACHE_ENTRIES:
            raise ReferenceUnavailable()
        with tempfile.TemporaryDirectory(prefix='.reference-', dir=self.root) as temporary:
            staged = Path(temporary) / 'entry'
            staged.mkdir()
            for name, content in (('reference.wav', data), ('reference.json', _canonical(reference))):
                with (staged / name).open('xb') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            try:
                staged.rename(folder)
            except OSError:
                if not folder.exists():
                    raise
                # Another process may have published the exact same immutable
                # entry. Its existence is accepted only after full comparison.
        return self._cached(folder, reference, data)

    async def prepare(self, *, service_id, language, voice_id, tts_config_sys_id, reference, authorization):
        """Fetch under the original caller; register only a detached immutable alias.

        The token is never assigned to this object, returned, or sent to the
        registrar. Call this while admission still owns the original credential.
        """
        reference = validate_reference(reference, service_id, tts_config_sys_id, voice_id)
        if (not _language(language) or type(authorization) is not str or len(authorization) > 8192
                or not re.fullmatch(r'Bearer [A-Za-z0-9._~+/-]+=*', authorization, re.I)):
            raise ReferenceUnavailable()
        try:
            async with asyncio.timeout(30):
                # A disk/registry hit must never bypass this authorization call.
                data = await self._fetch(service_id, language, reference, authorization)
                _validate_wav(data, reference)
                digest = reference_fingerprint(reference)
                alias = 'snref-' + digest
                wav_path = self._cache(alias, reference, data)
                async with self._locks.setdefault(alias, asyncio.Lock()):
                    owner = self._owner()
                    if self._registered.get(alias) != owner:
                        # A possibly committing POST must never leave an older
                        # process receipt reusable after a lost/error response.
                        self._registered.pop(alias, None)
                        await self.register(voice_id=alias, reference_text=reference['reference_text'], wav_bytes=data)
                        if self._owner() != owner:
                            raise ReferenceUnavailable()
                        self._registered[alias] = owner
                return PreparedVoice(service_id, tts_config_sys_id, voice_id, alias,
                    digest, reference['sha256'], reference['reference_language'], wav_path)
        except Exception:
            raise ReferenceUnavailable() from None
