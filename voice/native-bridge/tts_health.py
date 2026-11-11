"""Bounded, read-only readiness for the configured local speech model."""
import json
from urllib.parse import urlsplit

from aiohttp import ClientTimeout


TTS_MODEL = 'scc-native-qwen3'
TTS_READINESS_TIMEOUT = 2
MAX_MODELS_BYTES = 16384


async def require_tts_ready(http, speech_url):
    try:
        if type(speech_url) is not str:
            raise ValueError()
        parts = urlsplit(speech_url)
        if (parts.scheme != 'http' or parts.hostname != '127.0.0.1'
                or parts.path != '/v1/audio/speech' or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment
                or not parts.port or not 1024 <= parts.port <= 65535):
            raise ValueError()
        url = parts._replace(path='/v1/models').geturl()
        async with http.get(url, allow_redirects=False, auto_decompress=False,
                headers={'Accept-Encoding': 'identity'},
                timeout=ClientTimeout(total=TTS_READINESS_TIMEOUT)) as response:
            if response.status != 200:
                raise ValueError()
            raw = bytearray()
            while True:
                chunk = await response.content.read(min(2048, MAX_MODELS_BYTES + 1 - len(raw)))
                raw.extend(chunk)
                if len(raw) > MAX_MODELS_BYTES:
                    raise ValueError()
                if not chunk:
                    break
            value = json.loads(raw)
            if (type(value) is not dict or value.get('object') != 'list'
                    or type(value.get('data')) is not list or not 1 <= len(value['data']) <= 64
                    or not any(type(item) is dict and item.get('id') == TTS_MODEL
                               and item.get('object') == 'model' for item in value['data'])):
                raise ValueError()
    except Exception:
        # Never expose a URL, body, model list, credential or transport detail.
        # CancelledError is a BaseException and continues to the request owner.
        raise RuntimeError('Selected TTS service is unavailable') from None
