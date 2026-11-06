"""Integrate configured ServiceNow references with the existing owned TTS worker."""
import asyncio
import base64
import importlib.util
import json
from pathlib import Path

import psutil

from voice_reference_cache import ReferenceCache, ReferenceUnavailable


def reference_cache(http, instance_url, tts_url):
    # This adapter has a single installed owned loopback worker. A provider URL
    # or another process cannot acquire reference audio through this path.
    if tts_url != 'http://127.0.0.1:8862/v1/audio/speech':
        raise ReferenceUnavailable()
    root = Path(__file__).resolve().parents[1]
    source = root / 'native-speech-validation' / 'speech_probe.py'
    spec = importlib.util.spec_from_file_location('reference_owned_speech', source)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)

    def owner_identity():
        native.assert_owned_listener(8862)
        record = native.owners()['tts']
        return record['pid'], record['created']

    async def register(*, voice_id, reference_text, wav_bytes):
        owner = owner_identity()
        if psutil.virtual_memory().available < 18 * 1024**3:
            raise ReferenceUnavailable()
        payload = json.dumps({'name':voice_id, 'ref_text':reference_text,
                              'wav_b64':base64.b64encode(wav_bytes).decode('ascii')}).encode('utf-8')
        raw, _ = await asyncio.to_thread(native.request, 8862, '/v1/audio/voices', 'POST', payload,
                                         timeout=25)
        if json.loads(raw).get('status') != 'registered' or owner_identity() != owner:
            raise ReferenceUnavailable()

    return ReferenceCache(http, instance_url, root / 'voice-profile/runtime/servicenow-references',
                          register=register, owner_identity=owner_identity)


async def prepare_references(cache, settings, authorization):
    if settings is None:
        return
    # Never retain the original bearer in call state or on disk. Every new call
    # authorizes even a cached reference; selected language may change later.
    projection = settings.snapshot()
    handles = {}
    for language, voice in projection['tts'].get('voices', {}).items():
        if 'reference' not in voice:
            continue
        handles[language.casefold()] = await cache.prepare(service_id=settings.service_id,
            language=language, voice_id=voice['voice_id'], tts_config_sys_id=voice['tts_config_sys_id'],
            reference=voice['reference'], authorization=authorization)
    settings._prepared_voices = handles
