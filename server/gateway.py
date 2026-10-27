"""Bounded, authenticated streaming front door for one selected local engine.

Inference engines remain separate processes. Model/engine switching is an
explicit local lifecycle operation, never an arbitrary command in an API body.
"""
import argparse
import asyncio
from collections import deque
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
from uuid import uuid4
import aiohttp
from aiohttp import web
from console_trace import ConsoleTrace,RequestTrace

LOG=logging.getLogger('alloy.gateway')
CONSOLE_TRACE_KEY=web.RequestKey('console_trace',RequestTrace)
NATIVE_SDK_URL='http://127.0.0.1:8860'
NATIVE_SDK_SESSION='/api/webrtc/sessions'
NATIVE_SDK_CHILD=re.compile(r'/api/webrtc/sessions/[a-f0-9]{32}(?:/(offer|candidate|candidates))?\Z')
POST_ROUTES={'/v1/chat/completions','/v1/completions','/v1/responses',
             '/v1/messages','/v1/messages/count_tokens','/v1/embeddings',
             '/v1/rerank','/v1/reranking'}
VOICE_STATIC_SEGMENTS=frozenset({'webrtc','auth','token','auth_token','authenticate','authorize',
    'connect','agent_operator','agent_operator_mobile','get_jwt_token','offer','answer','create_room',
    'create','room','rooms','session','sessions','mobile','start','signaling','signalling','api','v1',
    'scc-native','jwt','jwt_token','get_jwt','get_token','generate_token','create_token',
    'agent_operator_token','get_auth_token','create_session','start_session','ice_servers',
    'get_ice_servers','ticket','config','configuration','settings','service','services',
    'bootstrap','handshake','call','calls','init','initialize','capabilities','status','health'})
VOICE_STATIC_KEYS=frozenset({'token','auth_token','jwt','jwt_token','access_token','authorization',
    'api_key','client_id','client_secret','agent_id','agent_operator','agent_operator_mobile',
    'session_id','room_id','call_id','user_id','conversation_id','channel','client','platform',
    'version','client_version','clientVersion','device_id','deviceId','metadata','config',
    'configuration','context','data','type','sdp','offer','answer','candidate','candidates',
    'ice_servers','iceServers','audio','transcript','message','error','status','success','expires_in',
    'instance_name','voice_service_id','oauth_client_id','mobileChannelType','mobileChannelId',
    'voiceServiceId','voiceWebhookURL','client_app','clientApp','ws_ticket'})

UPSTREAM_ERROR_LIMIT=16384
INFERENCE_PARAMETER_NAMES=frozenset({'messages','prompt','input','max_tokens',
    'max_completion_tokens','max_output_tokens','temperature','top_p','min_p','top_k',
    'response_format','tools','tool_choice','logprobs','top_logprobs','reasoning_effort',
    'reasoning','thinking','enable_thinking','chat_template_kwargs','stream','stop',
    'presence_penalty','frequency_penalty','repetition_penalty','drafter','logit_bias',
    'prompt_cache_policy','continue_final_message','add_generation_prompt',
    'previous_response_id'})


def inference_request_metrics(body, context):
    """Numeric sizes only. Never estimate token counts or copy request values."""
    def integer(value):
        return value if type(value) is int and 0<=value<=2147483647 else -1
    messages=body.get('messages')
    tools=body.get('tools')
    chars=0
    shape={name:0 for name in ('role_system','role_user','role_assistant','role_tool',
        'role_other','content_string','content_list','content_null','content_other',
        'image_parts','tool_response_wrappers')}
    if isinstance(messages,list):
        for message in messages[:4096]:
            role=message.get('role') if isinstance(message,dict) else None
            role_key='role_'+role if role in ('system','user','assistant','tool') else 'role_other'
            shape[role_key]+=1
            content=message.get('content') if isinstance(message,dict) else None
            if isinstance(content,str):
                shape['content_string']+=1
                chars+=len(content)
                text=content.strip()
                if text.startswith('<tool_response>') and text.endswith('</tool_response>'):
                    shape['tool_response_wrappers']+=1
            elif isinstance(content,list):
                shape['content_list']+=1
                for part in content[:256]:
                    if isinstance(part,dict) and isinstance(part.get('text'),str):
                        chars+=len(part['text'])
                    if isinstance(part,dict) and ('image_url' in part or 'image' in part
                            or part.get('type') in ('image','image_url','input_image')):
                        shape['image_parts']+=1
            elif content is None: shape['content_null']+=1
            else: shape['content_other']+=1
    elif isinstance(body.get('prompt'),str): chars=len(body['prompt'])
    elif isinstance(body.get('input'),str): chars=len(body['input'])
    result={'message_count':len(messages) if isinstance(messages,list) else 0,
            'tool_count':len(tools) if isinstance(tools,list) else 0,
            'prompt_chars':chars,'configured_context_tokens':integer(context)}
    result.update(shape)
    thinking=body.get('enable_thinking')
    result['thinking_enabled']=int(thinking) if type(thinking) is bool else -1
    effort=body.get('reasoning_effort')
    result['reasoning_effort_class']=(effort if effort in
        ('none','minimal','low','medium','high','xhigh') else 'missing' if effort is None else 'other')
    for name in ('max_tokens','max_completion_tokens','max_output_tokens'):
        result[name]=integer(body.get(name))
    return result


def upstream_error_metrics(raw, *, oversized=False, encoded=False):
    """Classify reviewed engine errors; unrecognized text never leaves memory."""
    if encoded: return {'error_class':'encoded_body_skipped'}
    if oversized: return {'error_class':'oversized_body_skipped'}
    result={'error_class':'unclassified'}
    try:
        value=json.loads(raw)
    except (ValueError,UnicodeError,RecursionError):
        return result
    error=value.get('error') if isinstance(value,dict) else None
    message=error.get('message') if isinstance(error,dict) else None
    if not isinstance(message,str): return result
    template_prefix='chat template rejected the request: '
    if message.startswith(template_prefix):
        reason=message[len(template_prefix):]
        known={
            'No user query found in messages.':'no_user_query',
            'No messages provided.':'no_messages',
            'Unexpected message role.':'unexpected_role',
            'Unexpected content type.':'unexpected_content_type',
            'Unexpected item type in content.':'unexpected_content_item',
            'System message must be at the beginning.':'system_message_position',
            'System message cannot contain images.':'system_image',
            'System message cannot contain videos.':'system_video',
            'Already borrowed':'tokenizer_already_borrowed',
        }
        code=known.get(reason,'unclassified')
        if reason.startswith('Unexpected reasoning effort ') and reason.endswith(
                '. Supported types are xhigh (default), medium, and low.'):
            code='unsupported_reasoning_effort'
        return {'error_class':'chat_template_rejected','template_reason':code,
                'template_error_chars':len(reason)}
    # Patterns extract bounded decimal token counts only, never arbitrary text.
    match=re.fullmatch(r'max_tokens ([0-9]{1,9}) does not fit: prompt is ([0-9]{1,9}) '
        r'tokens and the context is ([0-9]{1,9}), leaving room for ([0-9]{1,9})\.',message)
    if match:
        return dict(zip(('requested_max_tokens','prompt_tokens','context_tokens',
                         'available_output_tokens'),map(int,match.groups())),
                    error_class='output_budget_exceeds_context')
    match=re.match(r'the prompt does not fit: it is ([0-9]{1,9}) tokens and '
        r'the context is ([0-9]{1,9}), [0-9]{1,9} tokens over\. ',message)
    if match:
        return {'error_class':'prompt_exceeds_context',
                'prompt_tokens':int(match[1]),'context_tokens':int(match[2])}
    match=re.match(r'max_tokens ([0-9]{1,9}) exceeds this server\'s cap of ([0-9]{1,9})\. ',message)
    if match:
        return {'error_class':'output_budget_exceeds_policy',
                'requested_max_tokens':int(match[1]),'output_tokens_cap':int(match[2])}
    fields=sorted({part.split(':',1)[0] for part in message.split('; ')
                   if part.split(':',1)[0] in INFERENCE_PARAMETER_NAMES})
    if fields: return {'error_class':'request_validation','invalid_fields':fields}
    if message.startswith('body: Value error, conflicting token budgets ('):
        return {'error_class':'conflicting_token_budgets'}
    if message.startswith('body:'):
        return {'error_class':'request_validation','invalid_fields':[]}
    for prefix,code in (
            ('chat template rejected the request:','chat_template_rejected'),
            ('response_format (`text.format` on /v1/responses)', 'structured_output_unavailable'),
            ('response_format json_schema needs a ', 'invalid_json_schema'),
            ('this engine build decodes greedy only ', 'sampling_unavailable'),
            ('logprobs with stream=true ', 'stream_logprobs_unsupported'),
            ('continue_final_message cannot be combined ', 'invalid_final_message_mode'),
            ('the engine refused this request:', 'engine_refused'),
            ('the engine rejected this request.', 'engine_refused'),
            ('the chat template emitted ', 'chat_template_rejected'),
            ('this server does not accept images:', 'image_input_invalid'),
            ('this server does not fetch image URLs;', 'image_input_invalid'),
            ('this server has no video path;', 'image_input_invalid'),
            ('only base64 data: URLs are supported', 'image_input_invalid'),
            ('image_url.url ', 'image_input_invalid'),
            ('image payload is empty', 'image_input_invalid'),
            ('cannot decode the image:', 'image_input_invalid'),
            ('file inputs are not supported ', 'image_input_invalid')):
        if message.startswith(prefix): return {'error_class':code}
    field=re.split(r'[ =:\[\.]',message,maxsplit=1)[0]
    if field in INFERENCE_PARAMETER_NAMES:
        return {'error_class':'invalid_parameter','invalid_fields':[field]}
    return result


def voice_contract_shape(value):
    """Top-level reviewed key names and JSON types only; never traverse values."""
    def kind(child):
        return ('null' if child is None else 'boolean' if type(child) is bool else
                'number' if type(child) in (int,float) else 'string' if type(child) is str else
                'array' if type(child) is list else 'object' if type(child) is dict else 'other')
    if not isinstance(value,dict): return kind(value)
    result={}
    for index,(key,child) in enumerate(value.items()):
        if index>=32:
            result['[truncated]']='other'
            break
        result[key if key in VOICE_STATIC_KEYS else '[redacted_%d]' % index]=kind(child)
    return result


def voice_media_type(value):
    media=value.split(';',1)[0].strip().lower()
    return media if media in {'application/json','application/sdp','text/plain',
        'application/octet-stream','multipart/form-data','audio/wav','audio/pcm','audio/opus'} else 'other'

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
                 body_bytes=16*1024**2, request_seconds=1800, console_trace=False,
                 queue_limit=0, queue_seconds=120, demo_no_thinking_model='',
                 voice_contract_diagnostics=False, native_sdk_proxy=False,
                 controller_consumer=False, controller_aliases=()):
        if not isinstance(secret,str) or len(secret)<32:
            raise ValueError('At least 32 characters of API key material required')
        if not 1<=concurrency<=16 or not 1024<=body_bytes<=64*1024**2:
            raise ValueError('Invalid request limits')
        if not 1<=request_seconds<=3600:
            raise ValueError('Request timeout must be 1..3600 seconds')
        if type(queue_limit) is not int or not 0<=queue_limit<=64:
            raise ValueError('Queue limit must be an integer from 0..64')
        if type(queue_seconds) not in (int,float) or not 0<queue_seconds<=3600:
            raise ValueError('Queue timeout must be finite and greater than 0, up to 3600 seconds')
        if type(console_trace) is not bool:
            raise ValueError('console_trace must be a boolean')
        if type(voice_contract_diagnostics) is not bool:
            raise ValueError('voice_contract_diagnostics must be a boolean')
        if type(native_sdk_proxy) is not bool:
            raise ValueError('native_sdk_proxy must be a boolean')
        if (type(controller_consumer) is not bool
                or not isinstance(controller_aliases,(list,tuple)) or len(controller_aliases)>32
                or any(type(alias) is not str or not 1<=len(alias)<=200
                       or any(ord(char)<32 for char in alias) for alias in controller_aliases)
                or len(set(controller_aliases))!=len(controller_aliases)
                or controller_aliases and not controller_consumer
                or controller_consumer and len(backend_secret)<32):
            raise ValueError('Explicit authenticated controller consumer and unique logical aliases required')
        if (not isinstance(demo_no_thinking_model,str) or
                demo_no_thinking_model not in ('',backend.identifier,*controller_aliases)):
            raise ValueError('demo_no_thinking_model must be empty or the selected public model alias')
        self.demo_no_thinking_model=demo_no_thinking_model
        self.backend=backend; self.secret=secret; self.backend_secret=backend_secret
        self.concurrency=concurrency; self.body_bytes=body_bytes
        self.request_seconds=request_seconds; self.active=0; self._draining=False
        self.queue_limit=queue_limit; self.queue_seconds=queue_seconds; self.waiters=deque()
        self.completed=0; self.cancelled=0; self.client=None
        self.last_healthy=0.0; self.probe_lock=asyncio.Lock()
        self.console_trace=ConsoleTrace(secrets=(secret,backend_secret)) if console_trace else None
        self.voice_contract_diagnostics=voice_contract_diagnostics
        self.native_sdk_proxy=native_sdk_proxy
        self.controller_consumer=controller_consumer
        self.controller_aliases=tuple(controller_aliases)
        self.controller_backend=None
        self.controller_health=None
        self.app=web.Application(client_max_size=body_bytes,
            middlewares=[self.sdk_dispatch,self.diagnose_voice_contract,self.authenticate] if voice_contract_diagnostics
            else [self.sdk_dispatch,self.authenticate])
        self.app.add_routes([web.get('/health',self.health),web.get('/v1/models',self.models)])
        for path in sorted(POST_ROUTES): self.app.router.add_post(path,self.inference)
        self.app.cleanup_ctx.append(self.session_context)

    @web.middleware
    async def sdk_dispatch(self, request, handler):
        if request.path!=NATIVE_SDK_SESSION and not request.path.startswith(NATIVE_SDK_SESSION+'/'):
            return await self._sdk_dispatch(request,handler)
        status=None
        try:
            response=await self._sdk_dispatch(request,handler)
            status=response.status
            return response
        except web.HTTPException as response:
            status=response.status
            raise
        finally:
            # Telemetry must neither read the body nor affect dispatch results.
            try:
                child=NATIVE_SDK_CHILD.fullmatch(request.path)
                operation='other'
                if request.raw_path.split('?',1)[0]==request.path:
                    if request.method=='POST' and request.path==NATIVE_SDK_SESSION:
                        operation='create'
                    elif child:
                        suffix=child.group(1)
                        if request.method=='POST' and suffix in ('offer','candidate'):
                            operation=suffix
                        elif request.method=='GET' and suffix=='candidates':
                            operation='poll'
                        elif request.method=='DELETE' and suffix is None:
                            operation='delete'
                user_agent=request.headers.get('User-Agent','')[:256].lower()
                family=('android' if 'android' in user_agent else
                        'okhttp' if 'okhttp' in user_agent else
                        'ios' if any(marker in user_agent for marker in ('cfnetwork','darwin','iphone','ipad')) else
                        'web' if 'mozilla/' in user_agent else 'unknown')
                LOG.info('Gateway SDK dispatch %s',json.dumps({
                    'operation':operation,'status':status,'client_family':family,
                    'authorization_header_count':min(len(request.headers.getall('Authorization',[])),255),
                    'cookie_present':'Cookie' in request.headers,
                    'transfer_encoding_present':'Transfer-Encoding' in request.headers},
                    separators=(',',':'),sort_keys=True))
            except Exception:
                pass

    async def _sdk_dispatch(self, request, handler):
        # Separate platform OAuth admission lives in the fixed loopback native
        # service. This exception never reaches the inference dispatcher.
        path=request.path
        child=NATIVE_SDK_CHILD.fullmatch(path)
        allowed=(request.method=='POST' and path==NATIVE_SDK_SESSION) or bool(child and (
            (request.method=='POST' and child.group(1) in ('offer','candidate')) or
            (request.method=='GET' and child.group(1)=='candidates') or
            (request.method=='DELETE' and child.group(1) is None)))
        if (not self.native_sdk_proxy or not allowed or
                request.raw_path.split('?',1)[0]!=path):
            return await handler(request)
        authorization=request.headers.getall('Authorization',[])
        competing={'cookie','proxy-authorization','x-api-key','x-authorization',
            'x-access-token','x-auth-token','x-api-token','x-servicenow-token','x-sn-jwt',
            'sec-websocket-protocol','x-usertoken','x-user-token','x-jwt','x-jwt-token',
            'x-bearer-token','authentication','x-auth','x-token','x-session-token',
            'x-forwarded-authorization','x-forwarded-authentication'}
        if (len(authorization)!=1 or len(authorization[0])>8192 or
                not re.fullmatch(r'(?i:Bearer) [A-Za-z0-9._~+/-]+=*',authorization[0]) or
                any(name.lower() in competing for name in request.headers)):
            return web.json_response({'error':'unauthorized'},status=401)
        token=authorization[0][7:]
        if any(value and hmac.compare_digest(token,value) for value in (self.secret,self.backend_secret)):
            return web.json_response({'error':'unauthorized'},status=401)
        if (any(len(request.headers.getall(name,[]))>1 for name in ('Origin','Content-Type')) or
                'Content-Encoding' in request.headers or 'Transfer-Encoding' in request.headers):
            return web.json_response({'error':'bad_request'},status=400)
        limit=32768 if path==NATIVE_SDK_SESSION else 65536
        if request.content_length is not None and request.content_length>limit:
            return web.json_response({'error':'request_too_large'},status=413)
        body=bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.content.iter_chunked(4096):
                    body.extend(chunk)
                    if len(body)>limit:
                        return web.json_response({'error':'request_too_large'},status=413)
        except TimeoutError:
            return web.json_response({'error':'request_timeout'},status=408)
        # No cookies, API keys, user-selected destination or proxy headers.
        headers=[(name,value) for name,value in request.headers.items()
                 if name.lower() in {'authorization','origin','content-type','accept'}]
        headers.append(('Accept-Encoding','identity'))
        try:
            async with self.client.request(request.method,NATIVE_SDK_URL+request.raw_path,
                    data=bytes(body),headers=headers,allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=35,connect=3)) as response:
                if 300<=response.status<400 or 'Content-Encoding' in response.headers:
                    return web.json_response({'error':'native_unavailable'},status=502)
                result=bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    result.extend(chunk)
                    if len(result)>65536:
                        return web.json_response({'error':'native_unavailable'},status=502)
                return web.Response(body=bytes(result),status=response.status,
                    headers={'Content-Type':response.headers.get('Content-Type','application/json'),
                             'Cache-Control':'no-store'})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Native SDK proxy unavailable type=%s',type(error).__name__)
            return web.json_response({'error':'native_unavailable'},status=503)

    @property
    def draining(self):
        return self._draining

    @draining.setter
    def draining(self, value):
        self._draining=value
        if value:
            while self.waiters:
                waiter=self.waiters.popleft()
                if not waiter.done(): waiter.set_result(False)

    async def acquire_slot(self):
        # No await between checking capacity and reserving it: all admission
        # and handoff bookkeeping runs atomically on this event loop.
        if self.draining: return False
        if self.active<self.concurrency and not self.waiters:
            self.active+=1
            return True
        if len(self.waiters)>=self.queue_limit: return False
        waiter=asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        try:
            # Waiting has its own finite budget; request_seconds remains the
            # upstream execution budget, including streamed response reads.
            acquired=await asyncio.wait_for(asyncio.shield(waiter),self.queue_seconds)
        except (asyncio.CancelledError,TimeoutError) as exc:
            if waiter.done() and not waiter.cancelled() and waiter.result():
                # A grant may race with timeout/disconnect before we resume.
                self.release_slot()
            else:
                waiter.cancel()
                try: self.waiters.remove(waiter)
                except ValueError: pass
            if isinstance(exc,asyncio.CancelledError): raise
            return False
        if acquired and self.draining:
            self.release_slot()
            return False
        return acquired

    def release_slot(self):
        self.active-=1
        while self.waiters and not self.draining and self.active<self.concurrency:
            waiter=self.waiters.popleft()
            if not waiter.done():
                # Reserve for the oldest waiter before letting new calls in.
                self.active+=1
                waiter.set_result(True)

    @web.middleware
    async def diagnose_voice_contract(self, request, handler):
        if request.method!='POST' or 'webrtc' not in request.path.lower():
            return await handler(request)
        response=None
        try:
            response=await handler(request)
            return response
        except web.HTTPException as error:
            response=error
            raise
        finally:
            # Observe only bodies already rejected by the unmodified auth/router.
            # Read no streams, SDP/audio, encoded, oversized, or unknown-size bodies.
            if response is not None and response.status in (401,404):
                try: await self.record_voice_contract(request,response)
                except Exception: pass  # Observation never replaces the selected response.

    async def record_voice_contract(self, request, response):
        parts=[part.lower() for part in request.path.split('/') if part]
        path_shape='/'+'/'.join(part if part in VOICE_STATIC_SEGMENTS else '[redacted]' for part in parts[:12])
        if len(parts)>12: path_shape+='/[truncated]'
        raw=request.headers.get('Authorization','')
        credential_syntax=('missing' if not raw else 'bearer' if raw.startswith('Bearer ') else
            'bearer_other_case' if raw[:7].lower()=='bearer ' else 'basic' if raw[:6].lower()=='basic ' else 'other')
        media=voice_media_type(request.headers.get('Content-Type',''))
        body_shape='not_json'
        if media=='application/json':
            length=request.content_length
            if 'Content-Encoding' in request.headers: body_shape='encoding_skipped'
            elif length is None or not 0<=length<=32768: body_shape='size_skipped'
            else:
                try:
                    payload=await asyncio.wait_for(request.read(),timeout=.25)
                    body_shape=voice_contract_shape(json.loads(payload)) if payload else 'empty'
                    del payload
                except TimeoutError: body_shape='timeout_skipped'
                except (ValueError,UnicodeError,RecursionError,web.HTTPRequestEntityTooLarge): body_shape='invalid_json'
        response_shape='not_json'
        raw_response=getattr(response,'body',None)
        if response.content_type=='application/json' and isinstance(raw_response,bytes) and len(raw_response)<=32768:
            try: response_shape=voice_contract_shape(json.loads(raw_response))
            except (ValueError,UnicodeError,RecursionError): response_shape='invalid_json'
        row={'request_id':uuid4().hex[:12], 'method':'POST','path_shape':path_shape,
             'credential_syntax':credential_syntax,'content_type':media,
             'header_presence':{name.replace('-','_'):name in request.headers for name in
                                ('authorization','x-api-key','origin','upgrade','content-encoding')},
             'query_credential_present':'auth_token' in request.query,
             'body_shape':body_shape,'status':response.status,'response_shape':response_shape}
        LOG.info('Gateway voice contract %s',json.dumps(row,separators=(',',':')))

    @web.middleware
    async def authenticate(self, request, handler):
        trace=(self.console_trace.start(request.method,request.path,self.backend.identifier)
               if self.console_trace and request.method=='POST' and request.path in POST_ROUTES else None)
        if trace is not None: request[CONSOLE_TRACE_KEY]=trace
        status=500; outcome=None
        # Never accept credentials from URL parameters; no CORS wildcard.
        raw=request.headers.get('Authorization','')
        key=raw[7:] if raw.startswith('Bearer ') else request.headers.get('x-api-key','')
        try:
            if not hmac.compare_digest(key.encode('utf-8'),self.secret.encode('utf-8')):
                status=401
                return web.json_response({'error':{'message':'Unauthorized'}},status=status)
            response=await handler(request)
            status=response.status
            return response
        except web.HTTPException as exc:
            status=exc.status
            raise
        except asyncio.CancelledError:
            status=trace.status if trace is not None and trace.status is not None else 499
            outcome='cancelled'
            raise
        finally:
            if trace is not None: trace.finish(status,outcome)

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
        if self.controller_consumer:
            # Resolve only metadata, freshly after acquiring the local queue slot.
            # A central switch must never reuse a cached previous model identity.
            async with self.probe_lock:
                await self.probe()
                return self.controller_backend
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
            if self.controller_consumer:
                if (type(value) is not dict or value.get('status')!='ok'
                        or type(value.get('backend')) is not str
                        or type(value.get('draining')) is not bool
                        or any(type(value.get(key)) is not int or value[key]<0
                               for key in ('active_requests','queued_requests'))):
                    raise ValueError('Controller is not ready')
                self.controller_health={key:value[key] for key in
                    ('backend','active_requests','queued_requests','draining')}
                if value['draining']:
                    raise ValueError('Controller is draining')
                async with self.client.get(self.backend.upstream+'/v1/models',
                        headers=self.upstream_headers(),allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=5)) as models_response:
                    if models_response.status!=200:
                        raise ValueError('Controller model identity unavailable')
                    models_raw=bytearray()
                    async for chunk in models_response.content.iter_chunked(65536):
                        models_raw.extend(chunk)
                        if len(models_raw)>1024*1024:
                            raise ValueError('Excessive controller model payload')
                    catalog=json.loads(models_raw)
                models=catalog.get('data') if type(catalog) is dict else None
                if type(models) is not list or len(models)!=1 or type(models[0]) is not dict:
                    raise ValueError('Controller must expose exactly one selected model')
                model=models[0]
                routes=model.get('routes')
                if (type(routes) is not list or not routes or any(type(route) is not str for route in routes)
                        or len(set(routes))!=len(routes) or not set(routes)<=POST_ROUTES
                        or type(model.get('id')) is not str
                        or not re.fullmatch(r'[A-Za-z0-9._-]{1,96}',model['id'])
                        or type(model.get('context_capacity')) is not int
                        or value.get('backend')!=model.get('id')
                        or value.get('context')!=model.get('context_capacity')
                        or value.get('checkpoint')!=model.get('checkpoint')
                        or type(model.get('checkpoint')) is not str
                        or not 1<=len(model['checkpoint'])<=200):
                    raise ValueError('Controller health and selected model identity differ')
                selected=Backend(model['id'],self.backend.upstream,model['id'],
                    expected={'status':'ok'},routes=tuple(route for route in routes if route in self.backend.routes),
                    checkpoint=model['checkpoint'],context=model['context_capacity'])
                self.controller_backend=selected
            self.last_healthy=time.monotonic()
            return value

    async def health(self, request):
        try:
            async with self.probe_lock: await self.probe()
            ready=not self.draining
        except (aiohttp.ClientError,TimeoutError,ValueError): ready=False
        backend=(self.controller_backend if ready else None) if self.controller_consumer else self.backend
        value={'status':'ok' if ready else 'unavailable',
            'backend':backend.identifier if backend else None,'checkpoint':backend.checkpoint if backend else None,
            'context':backend.context if backend else None,'active_requests':self.active,
            'queued_requests':len(self.waiters),
            'draining':self.draining or bool(self.controller_health and self.controller_health['draining']),
            'completed':self.completed,'cancelled':self.cancelled}
        if self.controller_consumer:
            value.update(controller_consumer=True,controller=self.controller_health if ready else None)
        return web.json_response(value,status=200 if ready else 503)

    async def models(self, request):
        backend=self.backend
        if self.controller_consumer:
            try: backend=await self.ensure_ready()
            except (aiohttp.ClientError,TimeoutError,ValueError):
                return web.json_response({'error':{'message':'Selected controller unavailable'}},status=503)
        model={'id':backend.identifier,'object':'model','owned_by':'strix-alloy',
               'context_capacity':backend.context,'checkpoint':backend.checkpoint,'routes':list(backend.routes)}
        if self.controller_consumer:
            model['compatibility_aliases']=list(self.controller_aliases)
        return web.json_response({'object':'list','data':[model]})

    async def inference(self, request):
        trace=request.get(CONSOLE_TRACE_KEY)
        if request.path not in self.backend.routes:
            return web.json_response({'error':{'message':'Route unsupported by selected backend'}},status=501)
        acquired=False; began=time.perf_counter(); response=None; status=502
        backend=self.backend
        try:
            try: body=await request.json()
            except (ValueError,UnicodeError):
                raise web.HTTPBadRequest(text='Valid UTF-8 JSON required')
            if trace is not None: trace.payload(body)
            if not isinstance(body,dict):
                raise web.HTTPBadRequest(text='JSON object required')
            if self.controller_consumer:
                acquired=await self.acquire_slot()
                if not acquired:
                    status=429
                    return web.json_response({'error':{'message':'Engine busy or draining'}},status=status,
                                             headers={'Retry-After':'1'})
                backend=await self.ensure_ready()
                if request.path not in backend.routes:
                    status=501
                    return web.json_response({'error':{'message':'Route unsupported by selected backend'}},status=status)
            if body.get('model') not in (backend.identifier,backend.model,*self.controller_aliases):
                raise web.HTTPBadRequest(text='Select a model returned by /v1/models')
            # Explicit demo mode affects only the configured inbound public alias.
            # It is intentionally shared by all callers of that alias, never prompt-matched.
            if (self.demo_no_thinking_model and request.path=='/v1/chat/completions'
                    and body['model']==self.demo_no_thinking_model):
                body['enable_thinking']=False
                body['reasoning_effort']='none'
            if ((self.demo_no_thinking_model and body['model']==self.demo_no_thinking_model
                    and self.demo_no_thinking_model=='halogen-v2')
                    or self.controller_consumer and backend.identifier=='halogen-v2') and request.path=='/v1/chat/completions':
                # The flat ServiceNow provider places task/history in one
                # system string. Qwen requires a user query as well. Retain
                # the provider's system priority and add only a dispatch.
                messages=body.get('messages')
                tools=body.get('tools')
                if (isinstance(messages,list) and len(messages)==1
                        and isinstance(messages[0],dict) and messages[0].get('role')=='system'
                        and isinstance(messages[0].get('content'),str) and messages[0]['content'].strip()
                        and (tools is None or tools==[])):
                    body['messages']=[messages[0],{'role':'user','content':
                        'Bitte bearbeite die im Systemtext beschriebene Aufgabe und beachte das dort geforderte Ausgabeformat.'}]
                    LOG.info('Gateway compatibility=single_system_flat_prompt')
            body['model']=backend.model
            request_metrics=inference_request_metrics(body,backend.context)
            if not acquired: acquired=await self.acquire_slot()
            if not acquired:
                status=429
                return web.json_response({'error':{'message':'Engine busy or draining'}},status=status,
                                         headers={'Retry-After':'1'})
            if not self.controller_consumer: await self.ensure_ready()
            headers=self.upstream_headers()
            headers['Content-Type']='application/json'
            if 'anthropic-version' in request.headers:
                headers['anthropic-version']=request.headers['anthropic-version']
            async with self.client.post(backend.upstream+request.path,json=body,
                    headers=headers,allow_redirects=False) as upstream:
                if 300<=upstream.status<400:
                    raise ValueError('Backend redirect refused')
                status=upstream.status
                if trace is not None:
                    trace.response(status,upstream.headers.get('Content-Type',''),
                                   upstream.headers.get('Content-Encoding',''))
                safe_headers={k:v for k,v in upstream.headers.items()
                              if k.lower() in ('content-type','cache-control','x-request-id','content-encoding','retry-after')}
                response=web.StreamResponse(status=status,headers=safe_headers)
                await response.prepare(request)
                # Retain at most16KiB of rejected JSON for classification. All
                # bytes still stream unchanged; success/audio/SSE never buffer.
                rejected=bytearray() if status==400 else None
                rejected_oversized=False
                async for chunk in upstream.content.iter_any():
                    await response.write(chunk)  # awaits transport backpressure; no whole-response buffer
                    if trace is not None: trace.feed(chunk)
                    if rejected is not None and not rejected_oversized:
                        if len(rejected)+len(chunk)>UPSTREAM_ERROR_LIMIT:
                            rejected.clear()
                            rejected_oversized=True
                        else: rejected.extend(chunk)
                await response.write_eof()
                if rejected is not None:
                    diagnostic=upstream_error_metrics(rejected,oversized=rejected_oversized,
                        encoded='Content-Encoding' in upstream.headers)
                    diagnostic.update(request_metrics)
                    LOG.info('Gateway upstream rejection %s',json.dumps(diagnostic,separators=(',',':')))
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
            if trace is not None:
                trace.outcome='upstream_error'
                trace.emit('error',type=type(exc).__name__)
            if response is not None and response.prepared:
                if request.transport: request.transport.close()
                return response
            status=503
            return web.json_response({'error':{'message':'Selected local backend unavailable; no fallback'}},status=status)
        finally:
            if acquired: self.release_slot()
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
                   request_seconds=value.get('request_seconds',1800),
                   queue_limit=value.get('queue_limit',0),queue_seconds=value.get('queue_seconds',120),
                   console_trace=value.get('console_trace',False),
                   demo_no_thinking_model=value.get('demo_no_thinking_model',''),
                   voice_contract_diagnostics=value.get('voice_contract_diagnostics',False),
                   native_sdk_proxy=value.get('native_sdk_proxy',False),
                   controller_consumer=value.get('controller_consumer',False),
                   controller_aliases=value.get('controller_aliases',()))


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
