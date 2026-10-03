"""Bounded, authenticated streaming front door for one selected local engine.

Inference engines remain separate processes. Model/engine switching is an
explicit local lifecycle operation, never an arbitrary command in an API body.
"""
import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import aiohttp
from aiohttp import web

LOG=logging.getLogger('alloy.gateway')
POST_ROUTES={'/v1/chat/completions','/v1/completions','/v1/responses',
             '/v1/messages','/v1/messages/count_tokens','/v1/embeddings',
             '/v1/rerank','/v1/reranking'}

@dataclass(frozen=True)
class Backend:
    identifier: str
    upstream: str
    model: str
    health_path: str = '/health'
    expected: dict = None
    routes: tuple = ('/v1/chat/completions','/v1/responses')
    checkpoint: str = 'unspecified'
    context: int = 129024

    def __post_init__(self):
        u=urlsplit(self.upstream)
        if (u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port
            or u.username or u.password or u.path or u.query or u.fragment):
            raise ValueError('Backend must be an explicit IPv4 loopback HTTP origin')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,96}',self.identifier):
            raise ValueError('Invalid public model identifier')
        if not isinstance(self.model,str) or not 1<=len(self.model)<=200:
            raise ValueError('Invalid upstream model identifier')
        if self.health_path not in ('/health','/ready'):
            raise ValueError('Unreviewed health route')
        if not set(self.routes).issubset(POST_ROUTES):
            raise ValueError('Unreviewed inference route')
        if type(self.context) is not int or self.context<4096:
            raise ValueError('Invalid context capacity')

    def validate_health(self, value):
        for dotted,expected in (self.expected or {}).items():
            observed=value
            for key in dotted.split('.'):
                observed=observed.get(key) if isinstance(observed,dict) else None
            if observed!=expected:
                raise ValueError('Backend identity/readiness does not match selected profile')

class Gateway:
    def __init__(self, backend, secret, backend_secret='', *, concurrency=1,
                 body_bytes=16*1024**2, request_seconds=1800):
        if not isinstance(secret,str) or len(secret)<32:
            raise ValueError('At least 32 characters of API key material required')
        if not 1<=concurrency<=16 or not 1024<=body_bytes<=64*1024**2:
            raise ValueError('Invalid request limits')
        if not 1<=request_seconds<=3600:
            raise ValueError('Request timeout must be 1..3600 seconds')
        self.backend=backend; self.secret=secret; self.backend_secret=backend_secret
        self.concurrency=concurrency; self.body_bytes=body_bytes
        self.request_seconds=request_seconds; self.active=0; self.draining=False
        self.completed=0; self.cancelled=0; self.client=None
        self.last_healthy=0.0; self.probe_lock=asyncio.Lock()
        self.app=web.Application(client_max_size=body_bytes,middlewares=[self.authenticate])
        self.app.add_routes([web.get('/health',self.health),web.get('/v1/models',self.models)])
        for path in sorted(POST_ROUTES): self.app.router.add_post(path,self.inference)
        self.app.cleanup_ctx.append(self.session_context)

    @web.middleware
    async def authenticate(self, request, handler):
        # Never accept credentials from URL parameters; no CORS wildcard.
        raw=request.headers.get('Authorization','')
        key=raw[7:] if raw.startswith('Bearer ') else request.headers.get('x-api-key','')
        if not hmac.compare_digest(key.encode('utf-8'),self.secret.encode('utf-8')):
            return web.json_response({'error':{'message':'Unauthorized'}},status=401)
        return await handler(request)

    async def session_context(self, app):
        timeout=aiohttp.ClientTimeout(total=self.request_seconds,connect=5,sock_read=self.request_seconds)
        async with aiohttp.ClientSession(timeout=timeout,trust_env=False,auto_decompress=False) as client:
            self.client=client
            self.last_healthy=0.0
            task=asyncio.create_task(self.health_monitor())
            try: yield
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

    def upstream_headers(self):
        headers={'Accept-Encoding':'identity'}
        if self.backend_secret: headers['Authorization']='Bearer '+self.backend_secret
        return headers

    async def health_monitor(self):
        while True:
            try:
                async with self.probe_lock: await self.probe()
            except (aiohttp.ClientError,TimeoutError,ValueError): self.last_healthy=0.0
            await asyncio.sleep(2)

    async def ensure_ready(self):
        if 0<=time.monotonic()-self.last_healthy<10: return
        async with self.probe_lock:
            if not 0<=time.monotonic()-self.last_healthy<10: await self.probe()

    async def probe(self):
        async with self.client.get(self.backend.upstream+self.backend.health_path,
                headers=self.upstream_headers(),allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status!=200: raise ValueError('Backend is not ready')
            raw=bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>1024*1024: raise ValueError('Excessive health payload')
            value=json.loads(raw)
            self.backend.validate_health(value)
            self.last_healthy=time.monotonic()
            return value

    async def health(self, request):
        try: await self.probe(); ready=not self.draining
        except (aiohttp.ClientError,TimeoutError,ValueError): ready=False
        return web.json_response({'status':'ok' if ready else 'unavailable',
            'backend':self.backend.identifier,'checkpoint':self.backend.checkpoint,
            'context':self.backend.context,'active_requests':self.active,
            'draining':self.draining,'completed':self.completed,'cancelled':self.cancelled},
            status=200 if ready else 503)

    async def models(self, request):
        return web.json_response({'object':'list','data':[{'id':self.backend.identifier,
            'object':'model','owned_by':'strix-alloy','context_capacity':self.backend.context,
            'checkpoint':self.backend.checkpoint,'routes':list(self.backend.routes)}]})

    async def inference(self, request):
        if request.path not in self.backend.routes:
            return web.json_response({'error':{'message':'Route unsupported by selected backend'}},status=501)
        if self.draining or self.active>=self.concurrency:
            return web.json_response({'error':{'message':'Engine busy or draining'}},status=429,
                                     headers={'Retry-After':'1'})
        self.active+=1; began=time.perf_counter(); response=None; status=502
        try:
            try: body=await request.json()
            except (ValueError,UnicodeError):
                raise web.HTTPBadRequest(text='Valid UTF-8 JSON required')
            if not isinstance(body,dict) or body.get('model') not in (self.backend.identifier,self.backend.model):
                raise web.HTTPBadRequest(text='Select a model returned by /v1/models')
            body['model']=self.backend.model
            await self.ensure_ready()
            headers=self.upstream_headers()
            headers['Content-Type']='application/json'
            if 'anthropic-version' in request.headers:
                headers['anthropic-version']=request.headers['anthropic-version']
            async with self.client.post(self.backend.upstream+request.path,json=body,
                    headers=headers,allow_redirects=False) as upstream:
                if 300<=upstream.status<400:
                    raise ValueError('Backend redirect refused')
                status=upstream.status
                safe_headers={k:v for k,v in upstream.headers.items()
                              if k.lower() in ('content-type','cache-control','x-request-id','content-encoding')}
                response=web.StreamResponse(status=status,headers=safe_headers)
                await response.prepare(request)
                async for chunk in upstream.content.iter_any():
                    await response.write(chunk)  # awaits transport backpressure; no whole-response buffer
                await response.write_eof()
                self.completed+=1
                return response
        except asyncio.CancelledError:
            self.cancelled+=1
            raise
        except web.HTTPException:
            raise
        except (aiohttp.ClientError,TimeoutError,ValueError,OSError) as exc:
            self.last_healthy=0.0
            LOG.warning('upstream_failure backend=%s type=%s',self.backend.identifier,type(exc).__name__)
            if response is not None and response.prepared:
                if request.transport: request.transport.close()
                return response
            return web.json_response({'error':{'message':'Selected local backend unavailable; no fallback'}},status=503)
        finally:
            self.active-=1
            LOG.info('request backend=%s path=%s status=%s seconds=%.4f active=%s',
                self.backend.identifier,request.path,status,time.perf_counter()-began,self.active)


def load_config(path):
    path=Path(path)
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema')!=1: raise ValueError('Unsupported gateway configuration')
    backend=Backend(**value['backend'])
    def key(name):
        p=Path(value[name]); p=p if p.is_absolute() else path.parent/p
        return p.read_text(encoding='ascii').strip()
    return Gateway(backend,key('token_file'),
                   key('backend_token_file') if value.get('backend_token_file') else '',
                   concurrency=value.get('concurrency',1),body_bytes=value.get('body_bytes',16*1024**2),
                   request_seconds=value.get('request_seconds',1800))


async def serve(gateway, port, stop_event=None):
    if not 1024<=port<=65535: raise ValueError('Invalid listener port')
    runner=web.AppRunner(gateway.app,handler_cancellation=True,access_log=None,
                         shutdown_timeout=30)
    await runner.setup()
    try:
        site=web.TCPSite(runner,'127.0.0.1',port)
        await site.start()
        LOG.info('gateway_listening port=%d backend=%s context=%d',port,
                 gateway.backend.identifier,gateway.backend.context)
        if stop_event is None: await asyncio.Event().wait()
        else: await stop_event.wait()
    finally:
        gateway.draining=True
        await runner.cleanup()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--port',type=int,default=8840)
    p.add_argument('--log',type=Path)
    args=p.parse_args()
    handlers=[logging.StreamHandler()]
    if args.log:
        args.log.parent.mkdir(parents=True,exist_ok=True)
        handlers.append(RotatingFileHandler(args.log,maxBytes=10*1024**2,
                                            backupCount=3,encoding='utf-8'))
    logging.basicConfig(level=logging.INFO,handlers=handlers,
                        format='%(asctime)s %(levelname)s %(message)s')
    try: asyncio.run(serve(load_config(args.config),args.port))
    except KeyboardInterrupt: return 0
    return 0

if __name__=='__main__': raise SystemExit(main())
