# Bearer-authenticated ASGI wrapper around the unmodified pinned image API.
import hashlib
import hmac
import json
from pathlib import Path
import re
import runpy
import sys
import time

TOKEN_FILE = Path('/candidate/api-token.txt')
UPSTREAM = '/halogen/tools/serve_api.py'
UPSTREAM_SHA256 = '3eff9866ebc10730f9ad53be2abe6ce4a47f19862138c5487aba34f56d0be266'

class BearerAuth:
    def __init__(self, app, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('Invalid API token file; expected generated 256-bit token')
        self.app, self.expected = app, ('Bearer ' + token).encode('ascii')

    async def __call__(self, scope, receive, send):
        kind = scope['type']
        if kind == 'lifespan':
            return await self.app(scope, receive, send)
        if kind != 'http':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        headers = [v for k, v in scope.get('headers', []) if k.lower() == b'authorization']
        authorized = len(headers) == 1 and hmac.compare_digest(headers[0], self.expected)
        began, status = time.monotonic(), 500
        async def observed(message):
            nonlocal status
            if message['type'] == 'http.response.start': status = message['status']
            await send(message)
        try:
            if not authorized:
                body = b'{"error":{"message":"Valid Bearer API token required","type":"authentication_error"}}'
                await observed({'type':'http.response.start','status':401,
                    'headers':[(b'content-type',b'application/json'),(b'www-authenticate',b'Bearer'),
                               (b'content-length',str(len(body)).encode())]})
                await send({'type':'http.response.body','body':body})
                return
            await self.app(scope, receive, observed)
        finally:
            # No query string, credentials, body, prompts, or generated text.
            print('[api] ' + json.dumps({'method':scope.get('method'),
                'path':scope.get('path'), 'status':status,
                'seconds':round(time.monotonic()-began,3)},ensure_ascii=True), flush=True)

def main():
    if hashlib.sha256(Path(UPSTREAM).read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Pinned upstream API identity changed')
    token = TOKEN_FILE.read_text(encoding='ascii').strip()
    import uvicorn
    original = uvicorn.run
    def authenticated(app, *args, **kwargs):
        kwargs['access_log'] = False
        return original(BearerAuth(app, token), *args, **kwargs)
    uvicorn.run = authenticated
    sys.path.insert(0, str(Path(UPSTREAM).parent))
    runpy.run_path(UPSTREAM, run_name='__main__')

if __name__ == '__main__': main()
