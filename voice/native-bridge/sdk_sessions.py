"""Inactive SDK 2.26 HTTP transport candidate for the existing NativeCall.

No listener, credentials, platform activation, speech service, or Dialog is
created here. register_sdk_routes must receive the browser transport's active
set and a synchronous make_call() using that same Dialog. The admission callback
must perform original-Bearer ServiceNow authorization before this adapter makes
a NativeCall. Authorization state retains only a SHA-256 bearer fingerprint;
optional managed TURN keeps its OAuth identity in the live RTC transport only.
"""
import asyncio
from dataclasses import dataclass, field

from rtc_diagnostics import reserve_media_diagnostics
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import secrets
import time

from aiohttp import web
from sdk_deployment import SDKDeploymentPolicy, valid_call_duration
from sdk_admission_policy import SDK_AGENT_ID
from mobile_relay import MobileRelayRegistry, MobileRelayUnavailable
from managed_turn import (ManagedTurnBootstrap, ManagedTurnUnavailable,
                          session_host_ice, clear_session_ice)

LOG = logging.getLogger(__name__)

STUN_URL = 'stun:stun.l.google.com:19302'
BASE = '/api/webrtc/sessions'
HANDSHAKE_SECONDS = 30
BODY_SECONDS = 5
ADMISSION_SECONDS = 12
OFFER_SECONDS = 20
CANDIDATE_SECONDS = 5
DELETE_WAIT_SECONDS = .1  # SDK DELETE read timeout is five seconds.
SHUTDOWN_CLEANUP_SECONDS = 5
MAX_CREATE_BYTES = 32768
MAX_SDP_BYTES = 128 * 1024
MAX_ANSWER_BYTES = 8192  # The uploaded SDK's answer validator limit.
MAX_PENDING_CANDIDATES = 32
MAX_CANDIDATES = 128
TOMBSTONE_SECONDS = 60
MAX_TOMBSTONES = 128
_BEARER = re.compile(r'(?i:Bearer) ([A-Za-z0-9._~+/-]+=*)\Z')
_JSON_TYPE = re.compile(r'application/json(?:\s*;\s*charset=utf-8)?\Z', re.I)
_CONFLICTING_AUTH = frozenset(('cookie','proxy-authorization','x-authorization',
    'x-access-token','x-auth-token','x-api-key','x-api-token','x-servicenow-token',
    'x-sn-jwt','sec-websocket-protocol','x-usertoken','x-user-token','x-jwt',
    'x-jwt-token','x-bearer-token','authentication','x-auth','x-token',
    'x-session-token','x-forwarded-authorization','x-forwarded-authentication'))
_PUBLIC = {400:'bad_request',401:'unauthorized',403:'forbidden',404:'not_found',
           408:'request_timeout',409:'conflict',410:'gone',413:'payload_too_large',
           429:'too_many_requests',501:'assistant_settings_unsupported',
           503:'unavailable',504:'gateway_timeout'}
_SDP_ATTRIBUTES = {
    'session':frozenset(('group','msid-semantic','fingerprint','extmap-allow-mixed',
                        'ice-lite','ice-options','setup')),
    'audio':frozenset(('ice-ufrag','ice-pwd','candidate','end-of-candidates',
        'fingerprint','setup','rtcp','rtcp-mux','rtcp-rsize','rtcp-fb','rtpmap',
        'fmtp','ptime','maxptime','mid','msid','ssrc','ssrc-group','extmap',
        'sendrecv','sendonly','recvonly','inactive')),
    'application':frozenset(('ice-ufrag','ice-pwd','candidate','end-of-candidates',
        'fingerprint','setup','mid','sctp-port','max-message-size',
        'sendrecv','sendonly','recvonly','inactive')),
}


def _sdk_answer_compatible(sdp):
    """Fail closed on documented SDK 2.26 SDP bounds; never rewrite an answer.

    This checks the known static SDK validator constraints, not media validity
    or complete validator equivalence. aiortc remains responsible for SDP and
    ICE generation. Actual NativeCall audio/data negotiation needs integration
    validation on the deployment's installed aiortc version.
    """
    if not isinstance(sdp,str):
        return False
    try:
        if len(sdp.encode('utf8')) > MAX_ANSWER_BYTES:
            return False
    except UnicodeError:
        return False
    lines = [line for line in sdp.replace('\r\n','\n').split('\n') if line.strip()]
    if not lines or lines[0] != 'v=0':
        return False
    section, media_count, required, ssrcs, payloads = 'session',0,set(),set(),set()
    for line in lines:
        if (len(line)<3 or not line[0].isascii() or not line[0].isalpha()
                or line[1]!='=' or '\r' in line or '\x00' in line):
            return False
        if line.startswith('m='):
            media = line[2:].split()
            if len(media)<4:
                return False
            section = media[0]
            media_count += 1
            if section not in ('audio','application') or media_count>2:
                return False
            payloads = set(media[3:]) if section == 'audio' else set()
        elif section == 'session':
            required.add(line[:2])
        if line.startswith('a='):
            attribute,_,value = line[2:].partition(':')
            if attribute not in _SDP_ATTRIBUTES[section]:
                return False
            if section == 'audio' and attribute == 'rtpmap':
                fields = value.split()
                if (len(fields)!=2 or fields[0] not in payloads
                        or fields[1].split('/',1)[0].lower() not in (
                        'opus','pcmu','pcma','g722','telephone-event','cn','red')):
                    return False
            if section == 'audio' and attribute == 'ssrc':
                identity = value.split(' ',1)[0]
                if not identity.isascii() or not identity.isdecimal():
                    return False
                ssrcs.add(identity)
                if len(ssrcs)>2:
                    return False
        if section == 'audio' and line.startswith('b='):
            match = re.fullmatch(r'b=(AS|TIAS):([0-9]+)',line)
            if not match or len(match.group(2))>9:
                return False
            if int(match.group(2)) > (510 if match.group(1)=='AS' else 510000):
                return False
    return 1<=media_count<=2 and {'v=','o=','s=','t='} <= required


class _Rejected(Exception):
    def __init__(self, status):
        self.status = status


def _response(value=None, *, status=200):
    headers = {'Cache-Control':'no-store','Pragma':'no-cache',
               'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}
    if status == 204:
        return web.Response(status=204, headers=headers)
    return web.json_response(value, status=status, headers=headers)


def _session_description(sdp, kind):
    from aiortc import RTCSessionDescription
    return RTCSessionDescription(sdp=sdp, type=kind)


def _ice_candidate(value):
    from aiortc.sdp import candidate_from_sdp
    candidate = candidate_from_sdp(value['candidate'].removeprefix('candidate:'))
    candidate.sdpMid = value['sdpMid']
    candidate.sdpMLineIndex = value['sdpMLineIndex']
    return candidate


def _raw_headers(request):
    return [(key.decode('latin1'), value.decode('latin1'))
            for key, value in request.raw_headers]


def _validated_headers(request, policy, *, json_body=False):
    raw = _raw_headers(request)
    if len(raw) > 64 or sum(len(k)+len(v)+4 for k,v in raw) > 32768:
        raise _Rejected(400)
    headers = {}
    for name, value in raw:
        name = name.lower()
        if any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise _Rejected(401 if name == 'authorization' else 400)
        headers.setdefault(name, []).append(value)
    auth = headers.get('authorization', [])
    if len(auth) != 1 or len(auth[0]) > 8192 or not _BEARER.fullmatch(auth[0]):
        raise _Rejected(401)
    if _CONFLICTING_AUTH.intersection(headers):
        raise _Rejected(401)
    origins = headers.get('origin', [])
    if len(origins) > 1:
        raise _Rejected(400)
    if origins and origins[0] != policy.instance_url:
        raise _Rejected(403)
    if 'content-encoding' in headers or 'transfer-encoding' in headers:
        raise _Rejected(400)
    lengths = headers.get('content-length', [])
    if len(lengths) > 1 or (lengths and not re.fullmatch(r'0|[1-9][0-9]*',lengths[0])):
        raise _Rejected(400)
    types = headers.get('content-type', [])
    if len(types) > 1 or (json_body and (not types or not _JSON_TYPE.fullmatch(types[0]))):
        raise _Rejected(400)
    token = _BEARER.fullmatch(auth[0]).group(1)
    return hashlib.sha256(token.encode('ascii')).digest()


async def _body(request, limit):
    if request.content_length is not None and request.content_length > limit:
        raise _Rejected(413)
    data = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            while len(data) <= limit:
                chunk = await request.content.read(min(16384, limit+1-len(data)))
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
    except TimeoutError:
        raise _Rejected(408) from None
    raise _Rejected(413)


def _json(body):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError()
    try:
        value = json.loads(body.decode('utf8'), object_pairs_hook=unique,
                           parse_constant=reject_constant)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (UnicodeError,ValueError,RecursionError):
        raise _Rejected(400) from None


@dataclass(repr=False)
class _Session:
    session_id: str
    fingerprint: bytes
    call: object
    deadline: float
    handshake_seconds: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    accepted: asyncio.Event = field(default_factory=asyncio.Event)
    offered: bool = False
    closing: bool = False
    closed_at: float = 0
    pending: list = field(default_factory=list, repr=False)
    candidate_count: int = 0
    media_diagnostics: object = field(default=None, repr=False)
    operation: object = field(default=None, repr=False)
    close_task: object = field(default=None, repr=False)
    watchers: set = field(default_factory=set, repr=False)

    def __repr__(self):
        return '<SDKSession state=' + ('closed' if self.closed_at else 'closing' if self.closing else 'open') + '>'


class _PendingCreate:
    """Shared-capacity owner before a peer exists; supports bridge cleanup."""
    def __init__(self,operation):
        self.operation = operation

    def __repr__(self):
        return '<PendingSDKCreate>'

    async def close(self):
        operation = self.operation
        if operation is asyncio.current_task():
            return
        if not operation.done() and not operation.cancelling():
            operation.cancel()
        await asyncio.shield(asyncio.gather(operation,return_exceptions=True))


class SDKSessionManager:
    def __init__(self, config, active, make_call, admit, context_call_factory=None):
        self.config, self.active, self.make_call, self.admit = config, active, make_call, admit
        self.context_call_factory = context_call_factory
        self.policy = getattr(config,'sdk_policy',None)
        self.sessions = {}
        self.stopping = False
        self.relay_registry = None
        self.relay_runtime = None
        self.managed_turn = None
        self.creating = set()

    async def startup(self):
        managed = getattr(self.config,'private_managed_turn',None)
        if managed is not None and managed.enabled:
            self.managed_turn = ManagedTurnBootstrap(managed)
        relay = getattr(self.config,'private_mobile_relay',None)
        if relay is not None and relay.enabled:
            from mobile_relay_runtime import MobileRelayRuntime
            self.relay_registry = MobileRelayRegistry(relay)
            try:
                self.relay_runtime = MobileRelayRuntime(relay)
                await self.relay_runtime.start()
            except BaseException:
                try:
                    if self.relay_runtime is not None:
                        await self.relay_runtime.close()
                finally:
                    self.relay_registry.close()
                    self.relay_registry = None
                raise

    def _enabled(self):
        return type(self.policy) is SDKDeploymentPolicy and self.policy.matches_config(self.config)

    def _prune(self):
        now = time.monotonic()
        closed = sorted((s for s in self.sessions.values() if s.closed_at),key=lambda s:s.closed_at)
        for index, session in enumerate(closed):
            if now-session.closed_at > TOMBSTONE_SECONDS or index < len(closed)-MAX_TOMBSTONES:
                self.sessions.pop(session.session_id,None)

    async def _managed_call(self,request,context):
        # Reserve shared capacity before the first remote await. A pending create
        # owns its cancellation/metadata cleanup even before a NativeCall exists.
        if self.context_call_factory is None:
            raise _Rejected(503)
        operation = asyncio.current_task()
        reservation = _PendingCreate(operation)
        self.active.add(reservation)
        self.creating.add(operation)
        host_servers = None
        try:
            authorization = next(value for name,value in _raw_headers(request)
                                 if name.lower()=='authorization')
            token = _BEARER.fullmatch(authorization).group(1)
            servers = await self.managed_turn.ice_servers(token,
                self.policy.instance_name,self.policy.assistant_id)
            if self.stopping or not self._enabled():
                raise _Rejected(503)
            # ServiceNow returns private relay addresses. Both the mobile SDK
            # and the local backend must allocate on the same managed relay.
            host_servers = session_host_ice(servers,token,
                self.policy.instance_name,self.policy.assistant_id)
            call = self.context_call_factory(context,ice_servers=host_servers)
            self.active.add(call)
            host_servers = None  # NativeCall now owns the credential lifetime.
            return call,servers
        except ManagedTurnUnavailable:
            raise _Rejected(503) from None
        finally:
            if host_servers is not None:
                clear_session_ice(host_servers)
            self.active.discard(reservation)
            self.creating.discard(operation)

    async def create(self, request):
        if not self._enabled():
            raise _Rejected(403)
        if self.stopping:
            raise _Rejected(503)
        fingerprint = _validated_headers(request, self.policy, json_body=True)
        body = await _body(request,MAX_CREATE_BYTES)
        try:
            async with asyncio.timeout(ADMISSION_SECONDS):
                context = await self.admit(_raw_headers(request),body,
                    query_string=request.rel_url.raw_query_string)
        except TimeoutError:
            raise _Rejected(403) from None
        except Exception as error:
            # AdmissionDenied's bounded public status; never expose arbitrary details.
            status = getattr(error,'status',403)
            raise _Rejected(status if type(status) is int and status in (400,401,403) else 403) from None
        if not (getattr(context,'instance_url',None)==self.policy.instance_url
                and getattr(context,'assistant_id',None)==self.policy.assistant_id
                and getattr(context,'voice_agent_id',None)==self.policy.voice_agent_id
                and getattr(context,'sdk_agent_id',None)==SDK_AGENT_ID
                and getattr(context,'receive_data',None) is True):
            raise _Rejected(403)
        settings = getattr(context,'call_settings',None)
        if getattr(settings,'unsupported_language_selection',False):
            raise _Rejected(501)
        # No await from capacity check through reservation: browser shares this set.
        if self.stopping or not self._enabled() or self.active:
            LOG.info('SDK create stage=capacity_rejected active=%d stopping=%s enabled=%s',
                     len(self.active),self.stopping,self._enabled())
            raise _Rejected(503)
        if self.relay_runtime is not None:
            self.relay_runtime.ensure_running()
        managed_servers = []
        if self.managed_turn is not None:
            call,managed_servers = await self._managed_call(request,context)
        else:
            call = (self.make_call() if self.context_call_factory is None
                    else self.context_call_factory(context))
            self.active.add(call)
        session = None
        try:
            self._prune()
            session_id = secrets.token_hex(16)
            while session_id in self.sessions:
                session_id = secrets.token_hex(16)
            duration = self.config.max_call_seconds
            call_duration = getattr(getattr(call,'config',None),'max_call_seconds',None)
            if valid_call_duration(call_duration) and call_duration <= duration:
                duration = call_duration
            session = _Session(session_id,fingerprint,call,
                time.monotonic()+duration,min(HANDSHAKE_SECONDS,60))
            if self.relay_registry is not None:
                self.relay_registry.register(session_id,self.policy.instance_name,
                    self.policy.assistant_id,fingerprint.hex(),session.deadline-time.monotonic())
            session.media_diagnostics = reserve_media_diagnostics(lambda:call.peer)
            self.sessions[session_id] = session
            self._watch(session,self._deadline(session))
            self._watch(session,self._input_loss(session))
            ice_servers = ([{'urls':[STUN_URL]}] +
                (self.relay_registry.config.ice_servers() if self.relay_registry is not None else []))
            ice_servers += managed_servers
            # iOS HTTPSignaling requires exactly HTTP 200 before parsing JSON.
            # Android accepts this success status too; use one shared wire contract.
            return _response({'session_id':session_id,'agent_id':SDK_AGENT_ID,
                'created_at':datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
                'iceServers':ice_servers,
                'endpoint_url':self.policy.public_origin},status=200)
        except BaseException:
            if session is not None:
                self._begin_close(session)
            else:
                # Allocation failures still own cleanup and capacity.
                session = _Session('',fingerprint,call,time.monotonic(),0)
                self._begin_close(session)
            raise

    async def _lookup(self, request, *, json_body=False):
        if not self._enabled():
            raise _Rejected(403)
        fingerprint = _validated_headers(request,self.policy,json_body=json_body)
        if request.rel_url.raw_query_string:
            raise _Rejected(400)
        self._prune()
        session = self.sessions.get(request.match_info['session_id'])
        if session is None or not secrets.compare_digest(fingerprint,session.fingerprint):
            raise _Rejected(404)
        if time.monotonic() >= session.deadline and not session.closing:
            self._begin_close(session)
        return session

    @staticmethod
    def _open(session):
        if session.closing:
            raise _Rejected(410)

    async def offer(self, request):
        session = await self._lookup(request,json_body=True)
        body = _json(await _body(request,MAX_SDP_BYTES+1024))
        sdp = body.get('sdp')
        if (set(body) != {'type','sdp'} or body.get('type') != 'offer'
                or not isinstance(sdp,str) or not sdp.startswith('v=0\r\n')
                or '\x00' in sdp or len(sdp.encode('utf8')) > MAX_SDP_BYTES):
            raise _Rejected(400)
        async with session.lock:
            self._open(session)
            if session.offered:
                raise _Rejected(409)
            session.operation = asyncio.current_task()
            try:
                async with asyncio.timeout(OFFER_SECONDS):
                    await session.call.peer.setRemoteDescription(_session_description(sdp,'offer'))
                    self._open(session)
                    while session.pending:
                        await session.call.peer.addIceCandidate(session.pending.pop(0))
                        self._open(session)
                    answer = await session.call.peer.createAnswer()
                    self._open(session)
                    await session.call.peer.setLocalDescription(answer)
                    self._open(session)
                    local = session.call.peer.localDescription
                    if (session.call.peer.iceGatheringState != 'complete' or local is None
                            or local.type != 'answer' or not isinstance(local.sdp,str)
                            or not _sdk_answer_compatible(local.sdp)):
                        raise ValueError()
                    if self.relay_registry is not None:
                        if self.relay_runtime is not None:
                            self.relay_runtime.ensure_running()
                        self.relay_registry.set_peers(session.session_id,session.call.peer)
                    session.offered = True
                    session.accepted.set()
                    session.call.spawn(session.call.process_turns())
                    response = _response({'sdp':{'type':'answer','sdp':local.sdp}})
                    if session.media_diagnostics is not None:
                        await session.media_diagnostics.observe_offer(sdp,local.sdp,response.body)
                    return response
            except asyncio.CancelledError:
                self._begin_close(session)
                raise
            except _Rejected:
                raise
            except MobileRelayUnavailable:
                self._begin_close(session)
                raise _Rejected(503) from None
            except Exception:
                self._begin_close(session)
                raise _Rejected(400) from None
            finally:
                session.operation = None

    async def candidate(self, request):
        session = await self._lookup(request,json_body=True)
        body = _json(await _body(request,8192))
        value, mid, line = body.get('candidate'), body.get('sdpMid'), body.get('sdpMLineIndex')
        if (set(body) != {'candidate','sdpMid','sdpMLineIndex'}
                or not isinstance(value,str) or not value.startswith('candidate:')
                or len(value)>4096 or any(ord(c)<32 or ord(c)>126 for c in value)
                or not isinstance(mid,str) or not 1<=len(mid)<=64
                or any(ord(c)<33 or ord(c)>126 for c in mid)
                or type(line) is not int or not 0<=line<=255):
            raise _Rejected(400)
        try:
            candidate = _ice_candidate(body)
        except Exception:
            raise _Rejected(400) from None
        async with session.lock:
            self._open(session)
            if (session.candidate_count >= MAX_CANDIDATES
                    or (not session.offered and len(session.pending)>=MAX_PENDING_CANDIDATES)):
                raise _Rejected(429)
            session.candidate_count += 1
            if session.media_diagnostics is not None:
                session.media_diagnostics.observe_trickle(body)
            if not session.offered:
                session.pending.append(candidate)
            else:
                session.operation = asyncio.current_task()
                try:
                    async with asyncio.timeout(CANDIDATE_SECONDS):
                        await session.call.peer.addIceCandidate(candidate)
                    self._open(session)
                except asyncio.CancelledError:
                    self._begin_close(session)
                    raise
                except _Rejected:
                    raise
                except Exception:
                    self._begin_close(session)
                    raise _Rejected(400) from None
                finally:
                    session.operation = None
            return _response({})

    async def candidates(self, request):
        session = await self._lookup(request)
        if await _body(request,0):
            raise _Rejected(400)
        self._open(session)
        # setLocalDescription waits for ICE gathering. All local candidates are
        # in the answer SDP; no fabricated or incomplete candidate DTO is sent.
        if not session.offered:
            raise _Rejected(409)
        return _response({'candidates':[]})

    async def delete(self, request):
        session = await self._lookup(request)
        await _body(request,0)
        try:
            await asyncio.wait_for(asyncio.shield(self._begin_close(session)),DELETE_WAIT_SECONDS)
        except TimeoutError:
            # The session still owns capacity and cleanup. A submitted turn
            # after input loss can require much longer than the SDK timeout.
            return _response({},status=202)
        return _response(status=204)

    def _watch(self, session, coroutine):
        task = asyncio.create_task(coroutine)
        session.watchers.add(task)
        task.add_done_callback(session.watchers.discard)

    async def _deadline(self, session):
        try:
            await asyncio.wait_for(session.accepted.wait(),
                min(session.handshake_seconds,max(0,session.deadline-time.monotonic())))
            await asyncio.sleep(max(0,session.deadline-time.monotonic()))
        except TimeoutError:
            pass
        self._begin_close(session)

    async def _input_loss(self, session):
        await session.call.input_ended.wait()
        await session.call.turns_settled.wait()
        self._begin_close(session)

    def _begin_close(self, session):
        if session.close_task is None:
            session.closing = True
            if self.relay_registry is not None:
                try:
                    self.relay_registry.revoke(session.session_id)
                except MobileRelayUnavailable:
                    self.stopping = True
                    if self.relay_runtime is not None:
                        self.relay_runtime.abort()
                    LOG.error('Private mobile relay revocation unavailable; admission stopped')
            session.close_task = asyncio.create_task(self._finish_close(session))
        return session.close_task

    async def _finish_close(self, session):
        operation = session.operation
        if operation is not None and operation is not asyncio.current_task():
            operation.cancel()
            await asyncio.gather(operation,return_exceptions=True)
        watchers = tuple(session.watchers)
        for task in watchers:
            task.cancel()
        await asyncio.gather(*watchers,return_exceptions=True)
        try:
            await session.call.close()
            await session.call.close_complete.wait()
        finally:
            if session.call.close_complete.is_set():
                self.active.discard(session.call)
                session.pending.clear()
                session.closed_at = time.monotonic()

    async def shutdown(self):
        self.stopping = True
        try:
            await self._shutdown_sessions()
        finally:
            try:
                if self.relay_runtime is not None:
                    await self.relay_runtime.close()
            finally:
                if self.relay_registry is not None:
                    self.relay_registry.close()

    async def _shutdown_sessions(self):
        creating = tuple(self.creating)
        for operation in creating:
            if not operation.cancelling():
                operation.cancel()
        if creating:
            done,pending = await asyncio.wait(creating,timeout=SHUTDOWN_CLEANUP_SECONDS)
            if done:
                await asyncio.gather(*done,return_exceptions=True)
            if pending:
                LOG.warning('SDK metadata cleanup unresolved=%d',len(pending))
        tasks = [self._begin_close(s) for s in tuple(self.sessions.values())]
        if tasks:
            done, _ = await asyncio.wait(tasks,timeout=SHUTDOWN_CLEANUP_SECONDS)
            if done:
                await asyncio.gather(*done,return_exceptions=True)
            unresolved = sum(not session.call.close_complete.is_set()
                             for session in self.sessions.values())
            if unresolved:
                LOG.warning('SDK shutdown cleanup unresolved=%d',unresolved)


def register_sdk_routes(app, config, active, make_call, admit_sdk_session, *,
                        context_call_factory=None):
    """Register inactive candidate routes; return an owned shutdown manager.

    The caller must disable aiohttp access logging (Bearer may be in rejected
    query strings) and put this manager's on_shutdown before shared Dialog/http
    cleanup. This function registers on_shutdown automatically. No CORS or
    cookies are issued. Browser and SDK calls share a single active set.
    Optional context_call_factory receives only the rechecked internal admission
    context; the legacy make_call() contract is unchanged when it is omitted.
    """
    manager = SDKSessionManager(config,active,make_call,admit_sdk_session,context_call_factory)
    def route(handler):
        async def guarded(request):
            try:
                return await handler(request)
            except _Rejected as error:
                return _response({'error':_PUBLIC[error.status]},status=error.status)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.warning('SDK request stage=unexpected_failure handler=%s type=%s',
                            handler.__name__,type(error).__name__)
                return _response({'error':'unavailable'},status=503)
        return guarded
    app.router.add_post(BASE,route(manager.create))
    app.router.add_post(BASE+'/{session_id}/offer',route(manager.offer))
    app.router.add_post(BASE+'/{session_id}/candidate',route(manager.candidate))
    app.router.add_get(BASE+'/{session_id}/candidates',route(manager.candidates),allow_head=False)
    app.router.add_delete(BASE+'/{session_id}',route(manager.delete))
    async def startup(app):
        await manager.startup()
    async def shutdown(app):
        await manager.shutdown()
    app.on_startup.append(startup)
    app.on_shutdown.append(shutdown)
    return manager
