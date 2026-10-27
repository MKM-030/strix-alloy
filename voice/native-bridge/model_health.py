"""Read only the owner-configured controller health, never infer or retry."""
import json
from urllib.parse import urlsplit

from aiohttp import ClientTimeout


def validate_model_health(url, token):
    if type(url) is not str or type(token) is not str:
        raise ValueError('Invalid model health configuration')
    if not url and not token:
        return
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
            or parsed.path != '/health' or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.port
            or not 1024 <= parsed.port <= 65535
            or not 16 <= len(token) <= 8192 or any(ord(c) < 33 or ord(c) > 126 for c in token)):
        raise ValueError('Explicit authenticated loopback model health required')


async def require_model_ready(http, url, token):
    if not url:
        return
    try:
        async with http.get(url, headers={'Authorization': 'Bearer ' + token},
                            allow_redirects=False, timeout=ClientTimeout(total=6)) as response:
            raw = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError()
            value = json.loads(raw)
            if (response.status != 200 or type(value) is not dict
                    or value.get('status') != 'ok' or value.get('draining') is not False):
                raise ValueError()
    except Exception:
        # No upstream body/credential or guessed business outcome is exposed.
        raise RuntimeError('Model controller is unavailable; business outcome unknown') from None
