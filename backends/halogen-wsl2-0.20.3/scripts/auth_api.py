# Bearer auth and a narrow in-memory CacheOff correction for the pinned image API.
import ast
import hashlib
import hmac
import json
from pathlib import Path
import re
import runpy
import sys
import time
import types

TOKEN_FILE = Path('/candidate/api-token.txt')
UPSTREAM = '/halogen/tools/serve_api.py'
UPSTREAM_SHA256 = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'
ENGINE = Path('/usr/local/bin/flash_serve')
ENGINE_SHA256 = 'bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c'

# The pinned engine's zero-cache CSTAT literal has one redundant fixed zero
# at field35. The following eleven values are live pool counters, even Off.
_OFF_CSTAT_PREFIX = tuple(('C 0 0 0 0 0 0 0 0 0 0.0 0.0 0.0 0.0 0 0 0.0 '
    '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.0 0 0 0').split())
_CACHE_WIRE_HELPER = '_scc_halogen0203_cache_wire_tokens'


def normalize_cache_tokens(tokens):
    """Only the two producer layouts from the pinned API/engine pair."""
    if (type(tokens) is not list or not tokens or tokens[0] != 'C'
            or any(type(v) is not str or not v or len(v)>4096 or any(c.isspace() for c in v) for v in tokens)):
        raise ValueError('Unrecognized pinned CSTAT layout')
    if len(tokens) == 57:
        for index, value in enumerate(tokens[1:], 1):
            if index == 52:
                continue  # Upstream's cache-root string, unchanged.
            pattern = r'-?[0-9]+\.[0-9]' if index in (10,11,12,13,16,35,40) else r'-?[0-9]+'
            if re.fullmatch(pattern, value) is None:
                raise ValueError('Invalid pinned CSTAT field')
        return tokens
    if len(tokens) != 51 or tuple(tokens[:40]) != _OFF_CSTAT_PREFIX:
        raise ValueError('Unrecognized pinned CSTAT layout')
    for index in range(40,51):
        pattern = r'[0-9]+\.[0-9]' if index == 41 else r'[0-9]+'
        if re.fullmatch(pattern, tokens[index]) is None:
            raise ValueError('Invalid live CSTAT pool field')
    return tokens[:35] + tokens[36:]


def install_cache_stats(namespace, source):
    """Compile only the exact upstream method, retaining its I/O and globals."""
    if type(source) is not bytes or hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Pinned upstream API identity changed')
    engine = namespace.get('Engine')
    method = getattr(engine, 'cache_stats', None)
    if (not isinstance(engine,type) or not callable(method) or method.__globals__ is not namespace
            or method.__code__.co_filename != UPSTREAM or _CACHE_WIRE_HELPER in namespace):
        raise ValueError('Pinned Engine cache_stats binding changed')
    tree = ast.parse(source, filename=UPSTREAM)
    classes = [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'Engine']
    methods = [n for n in classes[0].body if isinstance(n,ast.AsyncFunctionDef) and n.name == 'cache_stats'] if len(classes)==1 else []
    if len(methods)!=1:
        raise ValueError('Pinned Engine cache_stats shape changed')
    function = methods[0]
    def method_code(tree):
        # Module imports affect CPython call compilation. Preserve the complete
        # pinned compilation context without executing any upstream top level.
        module = compile(ast.fix_missing_locations(tree),UPSTREAM,'exec',dont_inherit=True)
        classes = [value for value in module.co_consts if isinstance(value,types.CodeType) and value.co_name=='Engine']
        values = [value for value in classes[0].co_consts if isinstance(value,types.CodeType) and value.co_name=='cache_stats'] if len(classes)==1 else []
        if len(values)!=1:
            raise ValueError('Pinned Engine cache_stats code changed')
        return values[0]
    expected = method_code(tree)
    actual = method.__code__
    if any(getattr(actual,name)!=getattr(expected,name) for name in
            ('co_code','co_consts','co_names','co_varnames','co_argcount','co_kwonlyargcount','co_flags')):
        raise ValueError('Pinned Engine cache_stats method changed')
    sentinel = ast.parse('if not p or p[0] != "C" or len(p) < 10:\n    return None').body[0]
    positions = [i for i,node in enumerate(function.body) if ast.dump(node)==ast.dump(sentinel)]
    if len(positions)!=1:
        raise ValueError('Pinned CSTAT parser boundary changed')
    insertion = ast.parse('p = '+_CACHE_WIRE_HELPER+'(p)').body[0]
    ast.increment_lineno(insertion,function.body[positions[0]].lineno-1)
    function.body.insert(positions[0],insertion)
    patched = types.FunctionType(method_code(tree),namespace,'cache_stats',method.__defaults__,method.__closure__)
    namespace[_CACHE_WIRE_HELPER] = normalize_cache_tokens
    engine.cache_stats = patched


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
    source = Path(UPSTREAM).read_bytes()
    if hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256:
        raise ValueError('Pinned upstream API identity changed')
    digest = hashlib.sha256()
    with ENGINE.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            digest.update(data)
    if digest.hexdigest() != ENGINE_SHA256:
        raise ValueError('Pinned engine identity changed')
    token = TOKEN_FILE.read_text(encoding='ascii').strip()
    import uvicorn
    original = uvicorn.run
    def authenticated(app, *args, **kwargs):
        install_cache_stats(vars(sys.modules['__main__']), source)
        kwargs['access_log'] = False
        return original(BearerAuth(app, token), *args, **kwargs)
    uvicorn.run = authenticated
    sys.path.insert(0, str(Path(UPSTREAM).parent))
    runpy.run_path(UPSTREAM, run_name='__main__')

if __name__ == '__main__': main()
