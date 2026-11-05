"""Loopback speech UI and an isolated, authenticated VA Bot API callback."""
import argparse
import asyncio
import base64
from collections import deque
from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
import io
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit
import uuid
import wave

from aiohttp import ClientSession, ClientTimeout, FormData, web

if __package__:
    from .caller_binding import (CALLER_HEADER, CallerBinding, CallerBootstrapCredential,
        CALLER_CREATE_PATH, CALLER_SERVICE_ID, CALLER_AGENT_ID, CALLER_PROFILE_ID, PRESENTATION_GRANT_PURPOSE,
        valid_authorization, resolve_native_caller, refresh_native_caller_session,
        create_native_caller_conversation, validated_created,
        CALLER_CREATE_FAILURE_CONTRACT, CallerCreateFailure, CallerCreateFailureReceipt)
    from .callback_progress import CallbackProgress
    from .context_updates import ContextRequestAliases, action_acknowledged, update_payload, validate_update
    from .presentation_history import (validate_event, valid_receipt, issue_presentation_grant,
        valid_grant_receipt, _grant_diagnostic)
else:
    from caller_binding import (CALLER_HEADER, CallerBinding, CallerBootstrapCredential,
        CALLER_CREATE_PATH, CALLER_SERVICE_ID, CALLER_AGENT_ID, CALLER_PROFILE_ID, PRESENTATION_GRANT_PURPOSE,
        valid_authorization, resolve_native_caller, refresh_native_caller_session,
        create_native_caller_conversation, validated_created,
        CALLER_CREATE_FAILURE_CONTRACT, CallerCreateFailure, CallerCreateFailureReceipt)
    from callback_progress import CallbackProgress
    from context_updates import ContextRequestAliases, action_acknowledged, update_payload, validate_update
    from presentation_history import (validate_event, valid_receipt, issue_presentation_grant,
        valid_grant_receipt, _grant_diagnostic)

STATIC = Path(__file__).parent / 'static'
MAX_WAV = 20 * 1024 * 1024
TERMINAL_DRAIN_SECONDS = 2.0
CALLER_BOOTSTRAP_SECONDS = 45
MAX_END_RECEIPTS = 128
LOG = logging.getLogger('voice-bridge')
NATIVE_INPUT_UNSET = object()


@dataclass
class Settings:
    user_id: str = ''
    session_scoped_user_id: bool = False
    service_now_enabled: bool = True
    email: str = ''
    inbound_id: str = 'scc-local-voice'
    ui_port: int = 8850
    callback_port: int = 8853
    callback_username: str = ''
    tts_voice: str = 'ryan'
    defer_start_until_message: bool = False
    wait_for_input_control: bool = False
    session_language: str = ''
    callback_metadata_log_limit: int = 0
    session_seconds: int = 1800
    turn_seconds: int = 180
    max_sessions: int = 8
    instance_url: str = ''
    caller_binding_service_id: str = ''
    caller_binding_agent_id: str = ''
    caller_create_api_path: str = ''
    presentation_history_enabled: bool = False


@dataclass(frozen=True)
class ConversationBinding:
    """Opaque CREATE control IDs; server pair correlation is still required."""
    conversation_id: str
    creation_message_id: str
    create_request_id: str
    interaction_id: str = ''

    def snapshot(self):
        value = {'source': 'servicenow_create_conversation',
            'conversationId': self.conversation_id, 'creationMessageId': self.creation_message_id,
            'createRequestId': self.create_request_id}
        if self.interaction_id:
            value['interactionId'] = self.interaction_id
        return value


@dataclass
class Conversation:
    user_id: str = ''
    caller_user_id: str = field(default='', repr=False)
    caller_email: str = field(default='', repr=False)
    caller_bootstrap: object | None = field(default=None, repr=False)
    caller_refresh_started: bool = field(default=False, repr=False)
    caller_authorization_task: object | None = field(default=None, repr=False)
    caller_create_request_id: str = field(default='', repr=False)
    caller_create_task: object | None = field(default=None, repr=False)
    caller_create_failure: object | None = field(default=None, repr=False)
    caller_create_failure_id: str = field(default='', repr=False)
    cleanup_task: object | None = field(default=None, repr=False)
    cleanup_state: str = ''
    cleanup_request_id: str = field(default='', repr=False)
    sid: str = field(default_factory=lambda: uuid.uuid4().hex)
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    created: float = field(default_factory=time.monotonic)
    started: bool = False
    ended: bool = False
    busy: bool = False
    failed: bool = False
    pending_since: float = 0
    completion_deadline: float = 0
    pending_action: str = ''
    bootstrap_stage: str = ''
    bootstrap_input_ready: bool = False
    ending: bool = False
    now_session: str = ''
    conversation_binding: ConversationBinding | None = field(default=None, repr=False)
    requests: deque = field(default_factory=lambda: deque(maxlen=128))
    fingerprints: deque = field(default_factory=lambda: deque(maxlen=256))
    events: deque = field(default_factory=lambda: deque(maxlen=200))
    backend_events: deque = field(default_factory=lambda: deque(maxlen=200))
    backend_fingerprints: deque = field(default_factory=lambda: deque(maxlen=256), repr=False)
    input_control_receipt: dict | None = field(default=None, repr=False)
    turn_texts: deque = field(default_factory=lambda: deque(maxlen=200))
    sequence: int = 0
    choices: list = field(default_factory=list)
    input_label: str = ''
    voice_context: dict = field(default_factory=dict)
    progress: CallbackProgress = field(default_factory=CallbackProgress, repr=False)
    change: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    context_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    context_revision: int = 0
    context_text: str = field(default='', repr=False)
    context_eligible_text: str = field(default='', repr=False)
    context_ack_revision: int = 0
    context_receipt: dict | None = field(default=None, repr=False)
    context_requests: ContextRequestAliases = field(default_factory=ContextRequestAliases, repr=False)
    presentation_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    presentation_owner: str = field(default='', repr=False)
    presentation_sequence: int = 0
    presentation_disabled: bool = False
    presentation_lease: object | None = field(default=None, repr=False)
    presentation_task: object | None = field(default=None, repr=False)
    presentation_nonce: str = field(default='', repr=False)
    presentation_identity: object | None = field(default=None, repr=False)
    presentation_deadline: float = field(default=0, repr=False)
    presentation_timer: object | None = field(default=None, repr=False)
    input_boundary_request_id: str = ''
    input_boundary_kind: str = ''

    def emit(self, text='', kind='bot'):
        self.sequence += 1
        self.events.append({'id': self.sequence, 'kind': kind, 'text': text[:8000]})
        self.change.set()

    def emit_bot_once(self, text):
        if text and text not in self.turn_texts:
            self.turn_texts.append(text)
            self.emit(text)

    def emit_backend_once(self, request_id, ui_type, text, control_uid=''):
        key = (request_id, ui_type, text, control_uid)
        current = self.input_control_receipt
        if current is not None and (current['businessRequestId'], current['uiType'],
                current['text'], current['controlUid']) == key:
            return current
        if key in self.backend_fingerprints:
            return next((item for item in reversed(self.backend_events)
                if (item['businessRequestId'], item['uiType'], item['text'], item['controlUid']) == key), None)
        self.backend_fingerprints.append(key)
        self.sequence += 1
        receipt = dict(id=self.sequence, source='servicenow_bridge_event', businessRequestId=request_id,
            uiType=ui_type, text=text, streamComplete=True, controlUid=control_uid)
        self.backend_events.append(receipt)
        self.change.set()
        return receipt


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('br', 'p', 'div', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def text_only(value):
    if not isinstance(value, str):
        return ''
    parser = PlainText()
    parser.feed(value[:16000])
    return ' '.join(''.join(parser.parts).split())[:8000]


async def read_limited(stream, limit):
    data = bytearray()
    async for chunk in stream.iter_chunked(65536):
        data.extend(chunk)
        if len(data) > limit:
            raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=len(data))
    return bytes(data)


def initial_bot_history(value):
    """One actual primary-bot greeting; never accept invented user history."""
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise web.HTTPBadRequest(text='One initial bot greeting is required')
    item = value[0]
    if (set(item) != {'isBotMessage', 'value', 'displayName', 'type', 'timestamp'}
            or item.get('isBotMessage') is not True or item.get('type') != 'text'
            or item.get('displayName') != 'Bot' or not isinstance(item.get('value'), str)
            or not 1 <= len(item['value'].strip()) <= 4000
            or not isinstance(item.get('timestamp'), str)
            or not re.fullmatch(r'[0-9]{13}', item['timestamp'])):
        raise web.HTTPBadRequest(text='Invalid initial bot greeting')
    return [dict(item)]


def validated_voice_context(value):
    """Private cookie/CSRF-owned native context; never arbitrary bot variables."""
    languages = ('interaction_requester_session_language','interaction_user_language',
                 'requester_session_language')
    allowed = set(languages) | {'voice_assistant','interaction_ai_voice'}
    if (not isinstance(value,dict) or
            set(value) not in (allowed,allowed | {'global_context_profile'})):
        raise web.HTTPBadRequest(text='Invalid voice context')
    language = value.get(languages[0])
    if (not isinstance(language,str) or len(language) > 64
            or not re.fullmatch(r'[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8}){0,15}',language)
            or any(value.get(key) != language for key in languages)
            or not isinstance(value.get('voice_assistant'),str)
            or not re.fullmatch(r'[0-9a-f]{32}',value['voice_assistant'])
            or value.get('interaction_ai_voice') != 'true'):
        raise web.HTTPBadRequest(text='Invalid voice context')
    if 'global_context_profile' in value:
        profile = value['global_context_profile']
        if not isinstance(profile,str) or not re.fullmatch(r'[0-9a-f]{32}',profile):
            raise web.HTTPBadRequest(text='Invalid voice context')
    return dict(value)


def callback_metadata(data):
    """Bounded structural diagnostics: no utterances, identities or credentials."""
    envelope_keys = {'requestId','clientSessionId','userId','body','message','completed',
        'streamState','streamActive','takeControl','nowSessionId','interactionId',
        'nowBotId','appInboundId','enterpriseId','score','agentChat','clientVariables','contextVariables'}
    control_keys = {'uiType','actionType','streaming','streamingStatus','streamId','streamSequence',
        'messageId','conversationId','interactionId','value','label','promptMsg','maskType',
        'group','required','nluTextEnabled','options','type','itemType','spinnerType','waitTime',
        'message','supportQueue','channel','userDetails','chatSessionId','progressMessages',
        'defaultHeader','parentMessageId','header','shouldUpdateParentMessage','status',
        'displayMessage','subHeader','isWaitingForResponse'}
    ui_types = {'OutputText','InputText','ActionMsg','StreamStart','StreamChunk','Picker',
        'TopicPickerControl','Boolean','Date','DateTime','Time','FileUpload','OutputImage',
        'OutputLink','OutputCard','AdaptiveCard'}
    actions = {'CreateConversation','StartConversation','EndConversation','StartTypingIndicator',
        'EndTypingIndicator','StartSpinner','StopSpinner','SubscribeToSupportQueue',
        'SubscribeToChatPresence','ChatSubHeader','EndSpinner','StartTypingIndicatorActionMsg',
        'EndTypingIndicatorActionMsg','SwitchToLiveAgent','SwitchToVirtualAgent',
        'SwitchConversation','System','DynamicLoader','TopicFinishedActionMsg',
        'SeparatorActionMsg','SystemActionMsg'}
    states = {'START','INPROGRESS','END'}
    def known(value, allowed):
        return value if isinstance(value, str) and value in allowed else ('other' if value is not None else None)
    result = {'keys': sorted(set(data) & envelope_keys),
              'unknown_key_count':len(set(data)-envelope_keys)}
    for key in ('streamActive', 'takeControl', 'completed'):
        value = data.get(key)
        result[key] = value if isinstance(value, bool) else None
    result['streamState'] = known(data.get('streamState'), states)
    result['controls'] = []
    for item in data.get('body', [])[:20]:
        if isinstance(item, dict):
            control = {'keys':sorted(set(item) & control_keys),
                'unknown_key_count':len(set(item)-control_keys),
                'uiType':known(item.get('uiType'),ui_types),
                'actionType':known(item.get('actionType'),actions),
                'streaming':known(item.get('streaming'),states),
                'streamingStatus':known(item.get('streamingStatus'),states)}
            if isinstance(item.get('shouldUpdateParentMessage'), bool):
                control['shouldUpdateParentMessage'] = item['shouldUpdateParentMessage']
            if isinstance(item.get('progressMessages'), list):
                control['progressStatuses'] = [known(p.get('status'),
                    {'COMPLETED','IN_PROGRESS','INPROGRESS','STARTED','PENDING','FAILED'})
                    for p in item['progressMessages'][:20] if isinstance(p, dict)]
            result['controls'].append(control)
    return result


def validated_instance_url(value, required=True):
    """Canonical configured HTTPS origin; never infer it from requests or identity."""
    if value == '' and not required:
        return ''
    error = 'Configure a valid HTTPS ServiceNow instance_url origin'
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(error)
    match = re.fullmatch(r'https://([A-Za-z0-9.-]+)(?::([1-9][0-9]{0,4}))?/?', value)
    if not match:
        raise ValueError(error)
    host, port = match.groups()
    labels = host.split('.')
    if len(host) > 253 or any(not re.fullmatch(
            r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in labels):
        raise ValueError(error)
    if port and int(port) > 65535:
        raise ValueError(error)
    # Clients can interpret abbreviated, octal or hexadecimal numeric hosts differently.
    if re.fullmatch(r'(?:[0-9]+|0x[0-9a-f]*)', labels[-1], re.IGNORECASE):
        if len(labels) != 4 or any(not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', label)
                                  or int(label) > 255 for label in labels):
            raise ValueError(error)
    return 'https://' + host.lower() + ((':' + port) if port else '')


class Bridge:
    def __init__(self, settings, sn_token, audio_token, callback_token):
        instance_url = validated_instance_url(settings.instance_url, required=settings.service_now_enabled)
        if not audio_token or (settings.service_now_enabled and (not settings.user_id or not sn_token or not callback_token)):
            raise ValueError('Server identity and all three credentials are required')
        self.settings = settings
        if settings.caller_create_api_path not in ('', CALLER_CREATE_PATH):
            raise ValueError('Only the fixed own caller CREATE path is allowed')
        binding_ids = (settings.caller_binding_service_id, settings.caller_binding_agent_id)
        if any(binding_ids) and not all(type(v) is str and re.fullmatch(r'[0-9a-f]{32}', v) for v in binding_ids):
            raise ValueError('Caller binding requires exact service and agent identifiers')
        if settings.session_language and not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', settings.session_language):
            raise ValueError('Invalid configured session language')
        self.callback_diagnostics_remaining = max(0, min(100, settings.callback_metadata_log_limit))
        self.sn_token, self.audio_token = sn_token, audio_token
        if settings.callback_username:
            value = base64.b64encode((settings.callback_username + ':' + callback_token).encode()).decode()
            self.callback_auth = 'Basic ' + value
        else:
            self.callback_auth = 'Bearer ' + callback_token
        self.bot_url = (instance_url + '/api/sn_va_as_service/bot/integration') if instance_url else ''
        self.asr_url = 'http://127.0.0.1:8851/v1/audio/transcriptions'
        self.tts_url = 'http://127.0.0.1:8852/v1/audio/speech'
        self.origin = 'http://127.0.0.1:' + str(settings.ui_port)
        self.sessions = {}
        self.end_receipts = {}
        self.owned_tasks = set()
        self.http = None
        self.stopping = False
        self.bootstrap_tasks = set()
        self.presentation_tasks = set()
        self.audio_lock = asyncio.Lock()

    async def lifecycle(self, app):
        self.stopping = False
        self.http = ClientSession(timeout=ClientTimeout(total=180), trust_env=False)
        yield
        self.stopping = True
        for session in list(self.sessions.values()):
            if session.caller_create_request_id:
                self.begin_owned_cleanup(session)
            else:
                self.retire_caller_bootstrap(session)
        # CREATE and its one ordered END retain the live HTTP transport while
        # draining their original bounded requests. Unknown delivery stays owned.
        while self.owned_tasks:
            await asyncio.gather(*list(self.owned_tasks), return_exceptions=True)
        if self.bootstrap_tasks:
            await asyncio.gather(*list(self.bootstrap_tasks), return_exceptions=True)
        if self.presentation_tasks:
            await asyncio.gather(*list(self.presentation_tasks), return_exceptions=True)
        unresolved = sum(bool(s.caller_create_request_id and not s.ended)
                         for s in self.sessions.values())
        if unresolved:
            LOG.warning('Bridge shutdown cleanup unresolved=%d', unresolved)
        await self.http.close()
        for session in self.sessions.values():
            self.retire_caller_bootstrap(session)
            if not session.caller_create_request_id:
                session.caller_user_id = session.caller_email = ''

    def expire(self):
        now = time.monotonic()
        for sid, receipt in list(self.end_receipts.items()):
            completed_at = receipt[1]
            if now - completed_at > self.settings.session_seconds:
                del self.end_receipts[sid]
        for sid, session in list(self.sessions.items()):
            if now - session.created > self.settings.session_seconds:
                if session.caller_create_request_id:
                    if session.ended:
                        self.finish_owned_cleanup(session)
                    else:
                        self.begin_owned_cleanup(session)
                    continue
                self.retire_caller_bootstrap(session)
                session.caller_user_id = session.caller_email = ''
                del self.sessions[sid]
            elif session.completion_deadline:
                if now >= session.completion_deadline:
                    session.completion_deadline = 0
                    session.busy = False
                    session.sequence += 1
                    session.change.set()
            elif session.busy and now - session.pending_since > self.settings.turn_seconds:
                session.busy = False
                session.failed = True
                self.retire_caller_bootstrap(session)
                session.emit('Keine abschließende Antwort erhalten. Bitte einen neuen Dialog starten.', 'error')

    @web.middleware
    async def local_guard(self, request, handler):
        origin = urlsplit(self.origin)
        # Exact Host prevents DNS-rebinding; no forwarded headers are trusted.
        if request.host != origin.netloc:
            raise web.HTTPForbidden(text='Local host only')
        sent_origin = request.headers.get('Origin')
        if sent_origin and sent_origin != self.origin:
            raise web.HTTPForbidden(text='Origin rejected')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise web.HTTPForbidden(text='Cross-site request rejected')
        self.expire()
        sid = request.cookies.get('scc_voice', '')
        session = self.sessions.get(sid)
        receipt = self.end_receipts.get(sid) if request.path == '/api/end' and request.method == 'POST' else None
        request._voice_session = session
        request._voice_end_receipt = receipt
        if request.path.startswith('/api/') and request.path != '/api/session':
            if not session and not receipt:
                raise web.HTTPUnauthorized(text='Session expired; reload page')
            if request.method != 'GET' and (sent_origin != self.origin or not secrets.compare_digest(
                    request.headers.get('X-CSRF-Token', ''), session.csrf if session else receipt[0])):
                raise web.HTTPForbidden(text='CSRF check failed')
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text='Invalid request')
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def ui_app(self):
        app = web.Application(middlewares=[self.local_guard], client_max_size=MAX_WAV + 1024 * 1024)
        app.cleanup_ctx.append(self.lifecycle)
        app.router.add_get('/', self.index)
        app.router.add_get('/app.js', self.javascript)
        app.router.add_get('/style.css', self.stylesheet)
        app.router.add_get('/api/session', self.session)
        app.router.add_get('/api/events', self.events)
        app.router.add_post('/api/start', self.start)
        app.router.add_post('/api/reset', self.reset)
        app.router.add_post('/api/end', self.end)
        app.router.add_post('/api/message', self.message)
        app.router.add_post('/api/context-update', self.context_update)
        app.router.add_get('/api/context-status', self.context_status)
        app.router.add_post('/api/presentation-history', self.presentation_history)
        app.router.add_post('/api/transcribe', self.transcribe)
        app.router.add_post('/api/speak', self.speak)
        app.router.add_post('/api/audio-test', self.audio_test)
        return app

    def callback_app(self):
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_post('/callback', self.callback)
        return app

    async def index(self, request):
        return web.FileResponse(STATIC / 'index.html')

    async def javascript(self, request):
        return web.FileResponse(STATIC / 'app.js')

    async def stylesheet(self, request):
        return web.FileResponse(STATIC / 'style.css')

    async def session(self, request):
        session = request._voice_session
        if session is None:
            if len(self.sessions) >= (1 if self.settings.service_now_enabled else self.settings.max_sessions):
                raise web.HTTPServiceUnavailable(text='Too many local sessions')
            # Optional demo workaround for stale external-consumer bindings.
            # Separate from the private cookie/session ID; fixed for this dialog.
            user_id = ('voice-' + uuid.uuid4().hex if self.settings.session_scoped_user_id
                       else self.settings.user_id)
            session = Conversation(user_id=user_id)
            self.sessions[session.sid] = session
            if self.settings.session_scoped_user_id:
                LOG.info('Bot session alias=%s', user_id)
        response = web.json_response({'csrf': session.csrf, 'started': session.started,
            'serviceNowEnabled': self.settings.service_now_enabled,
            'initialBotHistoryAllowed': bool(self.settings.defer_start_until_message and
                not session.requests and not session.failed and not session.ended),
            'expiresIn': max(0, int(self.settings.session_seconds - time.monotonic() + session.created))})
        response.set_cookie('scc_voice', session.sid, httponly=True, samesite='Strict',
                            max_age=self.settings.session_seconds, path='/')
        return response

    async def json(self, request):
        raw = await read_limited(request.content, 16384)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text='JSON object required')
        return data

    async def start(self, request):
        if not self.settings.service_now_enabled:
            raise web.HTTPServiceUnavailable(text='ServiceNow is not configured; audio-only mode')
        data = await self.json(request)
        context = validated_voice_context(data['voice_context']) if 'voice_context' in data else {}
        session = request._voice_session
        async with session.lock:
            if session.started or session.failed or session.ending or session.ended:
                raise web.HTTPConflict(text='Conversation already started')
            if 'global_context_profile' in context:
                if not self.settings.caller_binding_service_id or not self.settings.caller_binding_agent_id:
                    raise web.HTTPServiceUnavailable(text='Caller binding is not configured')
                credentials = request.headers.getall(CALLER_HEADER, [])
                if len(credentials) != 1 or not valid_authorization(credentials[0]):
                    raise web.HTTPUnauthorized(text='Authenticated caller required')
                if context.get('voice_assistant') != self.settings.caller_binding_service_id:
                    raise web.HTTPForbidden(text='Caller binding unavailable')
                if self.settings.caller_create_api_path and (
                        self.settings.caller_binding_service_id != CALLER_SERVICE_ID
                        or self.settings.caller_binding_agent_id != CALLER_AGENT_ID
                        or context['global_context_profile'] != CALLER_PROFILE_ID
                        or self.settings.inbound_id != 'scc-local-voice'):
                    raise web.HTTPForbidden(text='Caller CREATE binding unavailable')
                def expired():
                    if self.sessions.get(session.sid) is session and session.caller_bootstrap is ticket:
                        session.caller_bootstrap = None
                        self.retire_caller_bootstrap(session)
                        if session.caller_create_request_id:
                            self.begin_owned_cleanup(session)
                        if not self.stopping and not session.ending and not session.ended:
                            session.failed = True
                            session.busy = False
                            session.emit('ServiceNow konnte den Dialog nicht starten.', 'error')
                ticket = CallerBootstrapCredential(credentials[0], seconds=CALLER_BOOTSTRAP_SECONDS,
                                                    on_expire=expired)
                session.caller_bootstrap = ticket
                session.caller_authorization_task = asyncio.current_task()
                try:
                    caller = await resolve_native_caller(self.settings.instance_url,
                        self.settings.caller_binding_service_id, self.settings.caller_binding_agent_id,
                        context['global_context_profile'], credentials[0])
                    if (not ticket.available or session.failed or session.ending or session.ended
                            or self.stopping or self.sessions.get(session.sid) is not session):
                        raise ValueError('Caller bootstrap unavailable')
                except asyncio.CancelledError:
                    self.retire_caller_bootstrap(session)
                    raise
                except Exception:
                    self.retire_caller_bootstrap(session)
                    raise web.HTTPForbidden(text='Caller binding unavailable') from None
                finally:
                    session.caller_authorization_task = None
                session.caller_user_id, session.caller_email = caller.user_id, caller.email
                if self.settings.caller_create_api_path:
                    session.user_id = 'voice-' + session.sid
            elif CALLER_HEADER in request.headers:
                raise web.HTTPForbidden(text='Caller binding unavailable')
            session.voice_context = context
            session.started = True
            try:
                if 'global_context_profile' in context:
                    # Native Voice creates, refreshes its owned linked session,
                    # then starts before the first utterance.
                    session.bootstrap_stage = 'creating'
                    await self.send(session, '', True, 'CREATE_CONVERSATION')
                elif self.settings.defer_start_until_message:
                    session.change.set()
                else:
                    await self.send(session, '', True, 'START_CONVERSATION')
            except BaseException:
                self.retire_caller_bootstrap(session)
                if session.caller_create_request_id:
                    self.begin_owned_cleanup(session)
                raise
        return web.json_response({'accepted': True}, status=202)

    async def reset(self, request):
        await self.json(request)
        old = request._voice_session
        if old.caller_create_request_id:
            self.begin_owned_cleanup(old)
            if not old.ended:
                return self.owned_cleanup_response(old)
            self.finish_owned_cleanup(old)
            request._voice_session = None
            return await self.session(request)
        old.ending = True
        self.retire_caller_bootstrap(old)
        async with old.lock:
            if old.started and old.requests and not old.ended:
                # Explicit reset ends the VA session, even if the previous turn timed out.
                await self.send(old, '', True, 'END_CONVERSATION')
            self.sessions.pop(old.sid, None)
            self.retire_caller_bootstrap(old)
            old.caller_user_id = old.caller_email = ''
        request._voice_session = None
        return await self.session(request)

    async def end(self, request):
        await self.json(request)
        session = request._voice_session
        if getattr(request, '_voice_end_receipt', None):
            receipt = request._voice_end_receipt
            response = web.json_response(receipt[2] if len(receipt) == 3 else {'ended': True})
            response.del_cookie('scc_voice', path='/')
            return response
        if session.caller_create_request_id:
            self.begin_owned_cleanup(session)
            if not session.ended:
                return self.owned_cleanup_response(session)
            self.finish_owned_cleanup(session)
            response = web.json_response({'ended': True})
            response.del_cookie('scc_voice', path='/')
            return response
        session.ending = True
        self.retire_caller_bootstrap(session)
        async with session.lock:
            if session.started and session.requests and not session.ended:
                # End only the authenticated cookie's conversation. Keep it if
                # the backend does not acknowledge ending, so retry is explicit.
                await self.send(session, '', True, 'END_CONVERSATION')
            self.sessions.pop(session.sid, None)
            session.ended = True
            session.caller_user_id = session.caller_email = ''
        response = web.json_response({'ended': True})
        response.del_cookie('scc_voice', path='/')
        return response

    def track_owned_task(self, task):
        self.owned_tasks.add(task)
        task.add_done_callback(self.finish_owned_task)
        return task

    def finish_owned_task(self, task):
        self.owned_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            LOG.warning('Owned conversation operation unresolved type=%s', type(task.exception()).__name__)

    def begin_owned_cleanup(self, session):
        session.ending = True
        self.retire_caller_bootstrap(session)
        if session.cleanup_task is None:
            session.cleanup_state = 'draining_create'
            session.cleanup_task = self.track_owned_task(asyncio.create_task(self.drain_owned_cleanup(session)))
        return session.cleanup_task

    async def drain_owned_cleanup(self, session):
        # Never wait for the CREATE owner while holding the start handler's lock.
        try:
            identity = None
            if session.caller_create_task is not None:
                try:
                    identity = await asyncio.shield(session.caller_create_task)
                except CallerCreateFailure:
                    async with session.lock:
                        receipt = self.owned_create_failure(session)
                        if receipt is not None and receipt.outcome == 'not_created':
                            self.finish_not_created(session)
                        else:
                            session.cleanup_state = 'unresolved'
                    return
            async with session.lock:
                if session.ended:
                    return
                if (self.sessions.get(session.sid) is not session
                        or session.conversation_binding is None
                        or identity != self.owned_cleanup_identity(session)):
                    session.cleanup_state = 'unresolved'
                    return
                session.cleanup_state = 'ending'
                await self.send(session, '', True, 'END_CONVERSATION')
                if not session.ended:
                    session.cleanup_state = 'end_enqueued'
        except (Exception, asyncio.CancelledError):
            # The remote mutation may have committed. This latch is never replayed.
            session.cleanup_state = 'unresolved'

    def owned_cleanup_identity(self, session):
        return ((self.settings.instance_url, self.settings.caller_create_api_path,
                 self.settings.caller_binding_service_id, self.settings.caller_binding_agent_id,
                 self.settings.inbound_id, self.bot_url),
                CallerBinding(session.caller_user_id, session.caller_email),
                (session.voice_context.get('voice_assistant'),
                 session.voice_context.get('global_context_profile')), session.sid, session.user_id,
                session.caller_create_request_id, session.conversation_binding)

    @staticmethod
    def owned_cleanup_response(session):
        return web.json_response({'ended': False, 'cleanup': session.cleanup_state}, status=202)

    def record_create_failure(self, session, error, request, caller, context, source):
        receipt = error.receipt
        if (type(receipt) is not CallerCreateFailureReceipt
                or self.sessions.get(session.sid) is not session or session.ended
                or session.conversation_binding is not None
                or self.owned_cleanup_identity(session)[0] != source
                or CallerBinding(session.caller_user_id, session.caller_email) != caller
                or session.voice_context != context
                or session.sid != request['clientSessionId'] or session.user_id != 'voice-'+session.sid
                or session.caller_create_request_id != request['requestId']
                or session.bootstrap_stage != 'creating' or session.pending_action != 'CREATE_CONVERSATION'
                or not session.requests or session.requests[-1] != request['requestId']
                or (receipt.request_id, receipt.client_session_id, receipt.client_message_id) !=
                   (request['requestId'], request['clientSessionId'], request['clientMessageId'])):
            return
        session.caller_create_failure = (receipt, self.owned_cleanup_identity(session),
                                        dict(context), dict(request), asyncio.current_task())
        if receipt.outcome == 'not_created':
            session.caller_create_failure_id = uuid.uuid4().hex

    def owned_create_failure(self, session):
        saved = session.caller_create_failure
        if type(saved) is not tuple or len(saved) != 5:
            return None
        receipt, identity, context, request, task = saved
        if (type(receipt) is not CallerCreateFailureReceipt
                or self.sessions.get(session.sid) is not session or session.ended
                or session.conversation_binding is not None
                or self.owned_cleanup_identity(session) != identity or session.voice_context != context
                or session.caller_create_task is not task or not task.done() or task.cancelled()
                or type(task.exception()) is not CallerCreateFailure
                or task.exception().receipt is not receipt
                or session.caller_create_request_id != request['requestId']
                or session.bootstrap_stage != 'creating' or session.pending_action != 'CREATE_CONVERSATION'
                or not session.requests or session.requests[-1] != request['requestId']
                or receipt.reason not in ('caller_create_unauthorized', 'caller_create_access_denied',
                                           'caller_create_unavailable')
                or receipt.outcome not in ('unknown', 'not_created')):
            return None
        if receipt.outcome == 'not_created' and not (
                receipt.contract == CALLER_CREATE_FAILURE_CONTRACT
                and re.fullmatch(r'[0-9a-f]{32}', session.caller_create_failure_id)
                and ((receipt.dispatch_state == 'not_dispatched' and receipt.http_status == 0)
                     or (receipt.dispatch_state == 'response_received' and receipt.http_status == 403
                         and receipt.close_completed is True))):
            return None
        return receipt

    def caller_create_failure_payload(self, session):
        receipt = self.owned_create_failure(session)
        if receipt is None:
            return None
        return {'error': {'source': CALLER_CREATE_FAILURE_CONTRACT, 'version': 1,
            'reason': receipt.reason, 'creationOutcome': receipt.outcome,
            'receiptId': session.caller_create_failure_id if receipt.outcome == 'not_created' else ''}}

    def finish_not_created(self, session):
        # A local terminal owner, explicitly NOT an acknowledged remote END.
        payload = {'ended': False, 'localTerminal': True, 'creationOutcome': 'not_created',
                   'cleanup': 'not_required', 'receiptId': session.caller_create_failure_id}
        session.busy = False
        session.cleanup_state = 'not_required'
        self.retire_caller_bootstrap(session)
        session.caller_user_id = session.caller_email = ''
        self.sessions.pop(session.sid)
        self.end_receipts[session.sid] = (session.csrf, time.monotonic(), payload)
        while len(self.end_receipts) > MAX_END_RECEIPTS:
            del self.end_receipts[next(iter(self.end_receipts))]
        session.change.set()

    def finish_owned_cleanup(self, session):
        session.ended = True
        session.busy = False
        session.cleanup_state = 'completed'
        self.retire_caller_bootstrap(session)
        session.caller_user_id = session.caller_email = ''
        if self.sessions.get(session.sid) is session:
            self.sessions.pop(session.sid)
        self.end_receipts[session.sid] = (session.csrf, time.monotonic())
        while len(self.end_receipts) > MAX_END_RECEIPTS:
            del self.end_receipts[next(iter(self.end_receipts))]
        session.change.set()

    async def message(self, request):
        data = await self.json(request)
        session = request._voice_session
        async with session.lock:
            if not session.started or session.busy or session.ended or session.failed or session.ending:
                raise web.HTTPConflict(text='Conversation is not ready for input')
            typed = 'choice' not in data
            value = data.get('text') if typed else data.get('choice')
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise web.HTTPBadRequest(text='Input must be 1 to 4000 characters')
            if not typed and value not in [item['value'] for item in session.choices]:
                raise web.HTTPBadRequest(text='Choice not available')
            history = None
            if 'history' in data:
                if session.requests:
                    raise web.HTTPBadRequest(text='History is only accepted on the first request')
                history = initial_bot_history(data['history'])
            if 'voice_context' in data:
                context = validated_voice_context(data['voice_context'])
                if (not session.voice_context or context['voice_assistant'] != session.voice_context['voice_assistant']
                        or context.get('global_context_profile') != session.voice_context.get('global_context_profile')):
                    raise web.HTTPBadRequest(text='Voice assistant/profile binding cannot change')
                session.voice_context = context
            request_id = await self.send(session, value.strip() if typed else value, typed, history=history,
                native_input=data.get('nativeInput', NATIVE_INPUT_UNSET))
        return web.json_response({'accepted': True, 'businessRequestId': request_id}, status=202)

    async def presentation_history(self, request):
        """Optional conversation history; never changes active MESSAGE/control state."""
        if self.settings.presentation_history_enabled is not True:
            raise web.HTTPNotFound()
        session = request._voice_session
        unavailable = {'state':'presentation_history_unavailable', 'stored':False}
        # One monotonic budget covers body, lock, grant and store waits.
        publication_deadline = time.monotonic() + 2
        try:
            async with asyncio.timeout_at(publication_deadline):
                data = await self.json(request)
                async with session.presentation_lock:
                    if session.presentation_disabled:
                        return web.json_response(unavailable)
                    if (not self.settings.service_now_enabled or self.stopping
                            or self.sessions.get(session.sid) is not session or not session.started
                            or session.ending or session.ended or session.failed
                            or session.conversation_binding is None
                            or self.settings.inbound_id != 'scc-local-voice'
                            or self.settings.caller_create_api_path != CALLER_CREATE_PATH
                            or self.settings.caller_binding_service_id != CALLER_SERVICE_ID
                            or self.settings.caller_binding_agent_id != CALLER_AGENT_ID
                            or session.voice_context.get('voice_assistant') != CALLER_SERVICE_ID
                            or session.voice_context.get('global_context_profile') != CALLER_PROFILE_ID
                            or not re.fullmatch('[0-9a-f]{32}', session.caller_user_id)
                            or session.user_id != 'voice-' + session.sid):
                        raise web.HTTPConflict(text='Owned presentation history is unavailable')
                    # Optional publication may wait for its bounded grant, never startup.
                    if session.presentation_task is not None and not session.presentation_nonce:
                        try:
                            await asyncio.shield(session.presentation_task)
                        except asyncio.CancelledError:
                            self.retire_presentation(session)
                            raise
                        except Exception:
                            self.retire_presentation(session)
                    if (session.presentation_disabled or not session.presentation_nonce
                            or time.monotonic() >= session.presentation_deadline
                            or session.ending or session.ended or session.failed or self.stopping
                            or self.sessions.get(session.sid) is not session
                            or session.presentation_identity != self.owned_cleanup_identity(session)):
                        if session.presentation_nonce:
                            self.retire_presentation(session)
                        return web.json_response(unavailable)
                    try:
                        event = validate_event(data)
                    except ValueError:
                        raise web.HTTPBadRequest(text='Invalid bounded presentation history')
                    if (event['sequence'] != session.presentation_sequence + 1
                            or session.presentation_owner and event['owner_id'] != session.presentation_owner):
                        raise web.HTTPBadRequest(text='Presentation owner or sequence mismatch')
                    binding = session.conversation_binding.snapshot()
                    payload = dict(operation='presentation_history_store', requestId=uuid.uuid4().hex,
                        appInboundId=self.settings.inbound_id, clientSessionId=session.sid,
                        userId=session.user_id, callerUserId=session.caller_user_id, conversationBinding=binding,
                        event=event, grantNonce=session.presentation_nonce)
                    # Claim before I/O. Unknown storage is never replayed, including after timeout.
                    session.presentation_owner = event['owner_id']
                    session.presentation_sequence = event['sequence']
                    url = self.bot_url.split('/api/', 1)[0] + '/api/global/scc_voice_context/updates'
                    try:
                        remaining = publication_deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError()
                        async with self.http.post(url, json=payload,
                                headers={'token':self.sn_token, 'Accept':'application/json'},
                                allow_redirects=False, timeout=ClientTimeout(total=remaining)) as response:
                            ack = json.loads(await read_limited(response.content, 16384))
                            receipt = ack.get('result', ack) if type(ack) is dict else None
                            if (response.status != 200 or type(ack) is not dict or ack.get('error')
                                    or ack.get('status', 'success') != 'success'
                                    or not valid_receipt(receipt, event,
                                    binding['conversationId'], payload['requestId'])):
                                raise ValueError('Presentation storage not corroborated')
                    except asyncio.CancelledError:
                        self.retire_presentation(session)
                        raise
                    except Exception:
                        self.retire_presentation(session)
                        return web.json_response(unavailable)
                    finally:
                        payload.pop('grantNonce', None)
                    return web.json_response(receipt)
        except asyncio.CancelledError:
            self.retire_presentation(session)
            raise
        except TimeoutError:
            self.retire_presentation(session)
            return web.json_response(unavailable)

    async def context_update(self, request):
        """Independent control lane; never advances the active MESSAGE request."""
        data = await self.json(request)
        session = request._voice_session
        async with session.context_lock:
            if (not self.settings.service_now_enabled or self.stopping
                    or self.sessions.get(session.sid) is not session or not session.started
                    or not session.busy
                    or session.ending or session.ended or session.failed
                    or session.bootstrap_stage or session.pending_action
                    or not session.requests or not session.voice_context
                    or session.conversation_binding is None):
                raise web.HTTPConflict(text='Conversation is not available for context updates')
            if 'voice_context' in data:
                context = validated_voice_context(data['voice_context'])
                if context != session.voice_context:
                    raise web.HTTPBadRequest(text='Native context binding cannot change')
            previous_snapshot = session.context_text
            try:
                revision, text = validate_update(data, previous_revision=session.context_revision,
                                                previous_text=previous_snapshot)
            except RuntimeError:
                raise web.HTTPConflict(text='Caller context revision already attempted')
            except ValueError:
                raise web.HTTPBadRequest(text='Invalid bounded cumulative caller context')
            delta = text[len(previous_snapshot):]
            # Pure consent stays in the ordinary-input FIFO. Supplemental
            # memory is never a name, business, or order authorization channel.
            confirmation = re.sub(r'[\s.!?,;:]+', ' ', delta.casefold()).strip()
            if not confirmation or confirmation in {
                    'ja', 'nein', 'ok', 'okay', 'genau', 'richtig', 'korrekt',
                    'bestätigt', 'bestätigen', 'ich bestätige', 'ich bestätige das',
                    'einverstanden', 'ja bitte', 'ja genau', 'nein danke'}:
                session.context_revision, session.context_text = revision, text
                session.context_receipt = None
                LOG.info('Caller context queued locally revision=%d; no memory dispatch', revision)
                return web.json_response({'state': 'context_action_acknowledged',
                    'revision': revision, 'contextStored': False, 'queuedOnly': True,
                    'ingested': False})
            # IDs come only from this cookie's authenticated CREATE callback.
            # The owned resource independently verifies provider/user ownership.
            binding = session.conversation_binding.snapshot()
            payload = {'requestId': uuid.uuid4().hex,
                'appInboundId': self.settings.inbound_id, 'clientSessionId': session.sid,
                'userId': session.user_id, 'conversationBinding': binding,
                'revision': revision, 'caller_updates': session.context_eligible_text + delta}
            context_url = self.bot_url.split('/api/', 1)[0] + '/api/global/scc_voice_context/updates'
            business_request_id = session.requests[-1]
            try:
                session.context_requests.bind(payload['requestId'], business_request_id)
            except RuntimeError:
                raise web.HTTPConflict(text='Context update limit reached; input remains queued')
            LOG.info('Context control request_id=%s business_request_id=%s revision=%d',
                     payload['requestId'], business_request_id, revision)
            # Claim before I/O: uncertain delivery is never automatically replayed.
            # These fields belong only to this lane; MESSAGE state stays intact.
            session.context_revision, session.context_text = revision, text
            session.context_eligible_text = payload['caller_updates']
            session.context_receipt = None
            # Only fixed classifications leave this boundary; upstream text may
            # contain caller context, credentials, or internal exception details.
            upstream = {'http_status': None, 'response_format': 'unavailable',
                        'status': 'unavailable', 'error_present': None}
            failure_stage = 'transport'
            try:
                async with self.http.post(context_url, json=payload,
                        headers={'token': self.sn_token, 'Accept': 'application/json'},
                        allow_redirects=False, timeout=ClientTimeout(total=10)) as response:
                    upstream['http_status'] = response.status
                    failure_stage = 'response_read'
                    raw = await read_limited(response.content, 65536)
                    failure_stage = 'json_decode'
                    acknowledgement = json.loads(raw)
                    upstream['response_format'] = 'json'
                    upstream['status'] = 'unrecognized'
                    if type(acknowledgement) is dict:
                        result = acknowledgement.get('result')
                        result = result if type(result) is dict else {}
                        status = acknowledgement.get('status')
                        if status is None:
                            status = result.get('status')
                        upstream['status'] = (status if type(status) is str
                            and status in ('success', 'failure') else
                            'missing' if status is None else 'unrecognized')
                        upstream['error_present'] = bool(
                            acknowledgement.get('error') or result.get('error'))
                    failure_stage = 'acknowledgement'
                    receipt = acknowledgement.get('result', acknowledgement) if type(acknowledgement) is dict else {}
                    if (response.status != 200 or not action_acknowledged(acknowledgement)
                            or type(receipt) is not dict
                            or receipt.get('state') != 'caller_context_stored'
                            or receipt.get('contextStored') is not True
                            or receipt.get('requestId') != payload['requestId']
                            or receipt.get('contextRequestId') != payload['requestId']
                            or type(receipt.get('revision')) is not int or receipt['revision'] != revision
                            or receipt.get('conversationId') != binding['conversationId']
                            or type(receipt.get('executionPlanId')) is not str
                            or not re.fullmatch(r'[0-9a-f]{32}', receipt['executionPlanId'])
                            or receipt.get('promptIncluded') is not False
                            or receipt.get('ingested') is not False):
                        raise ValueError('Owned caller context storage not corroborated')
            except Exception as exc:
                if failure_stage == 'json_decode':
                    upstream['response_format'] = 'invalid_json'
                if isinstance(exc, asyncio.TimeoutError):
                    failure_stage = 'timeout'
                LOG.warning('Context control delivery uncertain upstream=%s failure_stage=%s; '
                            'no identity or payload logged', upstream, failure_stage)
                return web.json_response({'state': 'context_action_uncertain',
                    'revision': revision, 'ingested': False,
                    'upstream': upstream, 'failure_stage': failure_stage}, status=502)
            LOG.info('Caller context stored upstream=%s; next prompt consumption not established', upstream)
            session.context_ack_revision = revision
            session.context_receipt = dict(payload, businessRequestId=business_request_id,
                executionPlanId=receipt['executionPlanId'])
            return web.json_response({'state': 'context_action_acknowledged',
                'revision': revision, 'contextStored': True, 'promptIncluded': False,
                'ingested': False, 'contextRequestId': payload['requestId'],
                'businessRequestId': business_request_id, 'conversationId': binding['conversationId'],
                'executionPlanId': receipt['executionPlanId']})

    async def context_status(self, request):
        """Read only the latest owned receipt, including a completed plan's prompt receipt."""
        if set(request.query) != {'revision'} or not re.fullmatch(r'[1-9][0-9]{0,9}', request.query['revision']):
            raise web.HTTPBadRequest(text='Exact context revision required')
        revision = int(request.query['revision'])
        session = request._voice_session
        async with session.context_lock:
            saved = session.context_receipt
            if (not self.settings.service_now_enabled or self.stopping
                    or self.sessions.get(session.sid) is not session or not session.started
                    or session.ending or type(saved) is not dict
                    or revision != session.context_revision or revision != session.context_ack_revision
                    or saved['revision'] != revision or not session.requests
                    or saved['businessRequestId'] != session.requests[-1]
                    or session.conversation_binding is None
                    or saved['conversationBinding'] != session.conversation_binding.snapshot()):
                raise web.HTTPConflict(text='Exact context receipt is not available')
            payload = {key: saved[key] for key in ('requestId', 'appInboundId', 'clientSessionId',
                'userId', 'conversationBinding', 'revision', 'caller_updates')}
            payload['operation'] = 'status'
            context_url = self.bot_url.split('/api/', 1)[0] + '/api/global/scc_voice_context/updates'
            try:
                async with self.http.post(context_url, json=payload,
                        headers={'token': self.sn_token, 'Accept': 'application/json'},
                        allow_redirects=False, timeout=ClientTimeout(total=10)) as response:
                    acknowledgement = json.loads(await read_limited(response.content, 65536))
                    receipt = acknowledgement.get('result', acknowledgement) if type(acknowledgement) is dict else {}
                    if (response.status != 200 or not action_acknowledged(acknowledgement)
                            or type(receipt) is not dict or receipt.get('state') != 'caller_context_status'
                            or receipt.get('contextStored') is not True
                            or receipt.get('requestId') != saved['requestId']
                            or receipt.get('contextRequestId') != saved['requestId']
                            or type(receipt.get('revision')) is not int or receipt['revision'] != revision
                            or receipt.get('conversationId') != saved['conversationBinding']['conversationId']
                            or receipt.get('executionPlanId') != saved['executionPlanId']
                            or type(receipt.get('promptIncluded')) is not bool
                            or receipt.get('ingested') is not receipt['promptIncluded']):
                        raise ValueError('Exact prompt inclusion receipt not corroborated')
            except Exception as error:
                LOG.warning('Caller context status unavailable type=%s; original input retained', type(error).__name__)
                return web.json_response({'state': 'context_status_unavailable',
                    'revision': revision, 'promptIncluded': False, 'ingested': False}, status=502)
            return web.json_response({'state': 'context_prompt_status', 'revision': revision,
                'contextRequestId': saved['requestId'], 'businessRequestId': saved['businessRequestId'],
                'conversationId': saved['conversationBinding']['conversationId'],
                'executionPlanId': saved['executionPlanId'], 'contextStored': True,
                'inputBoundaryConfirmed': bool(not session.busy and not session.ended
                    and not session.failed and not session.ending and not session.pending_action
                    and not session.bootstrap_stage
                    and session.input_boundary_request_id == saved['businessRequestId']),
                'promptIncluded': receipt['promptIncluded'], 'ingested': receipt['promptIncluded']})

    async def send(self, session, text, typed, action='', history=None, *, native_input=NATIVE_INPUT_UNSET):
        # Serialize HTTP dispatch only. Callbacks never acquire this lock, and
        # it is never held for the ensuing business conversation/callback wait.
        async with session.context_lock:
            return await self._send_locked(session, text, typed, action, history, native_input=native_input)

    def _check_native_input(self, session, native):
        if native is NATIVE_INPUT_UNSET:
            return
        if (type(native) is not dict or set(native) != {'version', 'attemptId', 'ownerId', 'binding'}
                or type(native.get('version')) is not int or native['version'] != 1
                or any(type(native.get(key)) is not str or not re.fullmatch(r'[0-9a-f]{32}', native[key])
                       for key in ('attemptId', 'ownerId'))):
            raise web.HTTPBadRequest(text='Invalid native input binding')
        binding = native['binding']
        if binding is not None and (type(binding) is not dict
                or set(binding) != {'businessRequestId', 'controlType', 'label', 'eventId', 'controlUid'}
                or type(binding.get('businessRequestId')) is not str
                or not re.fullmatch(r'[0-9a-f]{32}', binding['businessRequestId'])
                or binding.get('controlType') != 'Boolean'
                or type(binding.get('label')) is not str or not 0 < len(binding['label']) <= 8000
                or type(binding.get('eventId')) is not int or binding['eventId'] <= 0
                or type(binding.get('controlUid')) is not str or len(binding['controlUid']) > 256):
            raise web.HTTPBadRequest(text='Invalid native control binding')
        receipt = session.input_control_receipt
        current = (dict(businessRequestId=receipt['businessRequestId'], controlType='Boolean',
            label=receipt['text'], eventId=receipt['id'], controlUid=receipt['controlUid'])
            if session.input_boundary_kind == 'Boolean' and receipt is not None else None)
        if (binding != current or session.busy or session.ended or session.failed or session.ending
                or not session.started or session.input_boundary_kind == 'Boolean' and current is None):
            payload = dict(source='servicenow_native_input_conflict', dispatch='not_started',
                attemptId=native['attemptId'], ownerId=native['ownerId'],
                inputControl=dict(receipt) if receipt is not None and not session.ended else None)
            raise web.HTTPConflict(text=json.dumps(payload), content_type='application/json')

    async def _send_locked(self, session, text, typed, action='', history=None, *, native_input=NATIVE_INPUT_UNSET):
        # Compare after context_lock acquisition and before any request mutation.
        self._check_native_input(session, native_input)
        if ('global_context_profile' in session.voice_context
                and (not session.caller_user_id or not session.caller_email)):
            raise ValueError('Authenticated caller binding required')
        request_id = uuid.uuid4().hex
        payload = {'requestId': request_id, 'appInboundId': self.settings.inbound_id,
            'clientSessionId': session.sid, 'userId': session.user_id,
            'emailId': session.caller_email or self.settings.email, 'message': {'text': text, 'typed': typed,
            'clientMessageId': uuid.uuid4().hex}, 'clientVariables': {'voiceSessionId': session.sid}}
        if session.voice_context:
            payload['contextVariables'] = dict(session.voice_context)
        elif self.settings.session_language:
            payload['contextVariables'] = {'requester_session_language':self.settings.session_language}
        if history is not None and not session.requests:
            payload['history'] = history
        if session.now_session:
            payload['nowSessionId'] = session.now_session
        if action:
            payload['action'] = action
        if action == 'START_CREATED_CONVERSATION':
            payload['syncResponse'] = True
        # Reset before the HTTP await: callbacks may arrive before its ACK.
        session.turn_texts.clear()
        session.backend_fingerprints.clear()
        session.input_control_receipt = None
        session.completion_deadline = 0
        session.context_requests.clear()
        session.input_boundary_request_id = session.input_boundary_kind = ''
        session.requests.append(request_id)
        if action == 'END_CONVERSATION' and session.caller_create_request_id:
            session.cleanup_request_id = request_id
        session.progress.begin_request(request_id)
        LOG.info('Bot request id=%s action=%s', request_id, action or 'MESSAGE')
        session.busy = True
        session.pending_action = action
        session.pending_since = time.monotonic()
        session.choices = []
        session.input_label = ''
        try:
            if action == 'CREATE_CONVERSATION' and self.settings.caller_create_api_path:
                await self.send_owned_create(session, payload)
                return request_id
            async with self.http.post(self.bot_url, json=payload, headers={'token': self.sn_token,
                    'Accept': 'application/json'}, allow_redirects=False, timeout=ClientTimeout(total=30)) as response:
                raw = await read_limited(response.content, 65536)
                if response.status not in (200, 201, 202) or len(raw) > 65536:
                    raise RuntimeError('Bot request rejected')
                ack = json.loads(raw) if raw else {}
                if action == 'START_CREATED_CONVERSATION':
                    self.consume_start_response(session, payload, ack)
                    return request_id
                if not isinstance(ack, dict) or ack.get('error') or (isinstance(ack.get('result'), dict) and ack['result'].get('error')):
                    raise RuntimeError('Bot request failed')
                ack_status = ack.get('status')
                if ack_status is None and isinstance(ack.get('result'), dict):
                    ack_status = ack['result'].get('status')
                LOG.info('Bot ACK id=%s http=%s status=%s keys=%s', request_id, response.status, str(ack_status)[:80], sorted(ack.keys()))
                if ack_status != 'success':
                    raise RuntimeError('Bot did not acknowledge successful enqueue')
                # This response is only ACK. Actual bot output arrives at /callback.
        except Exception:
            session.busy = False
            session.failed = True
            self.retire_caller_bootstrap(session)
            session.emit('ServiceNow hat die Anfrage nicht bestätigt. Bitte einen neuen Dialog starten.', 'error')
            LOG.warning('Bot request failed; no credentials or payload logged')
            failure = self.caller_create_failure_payload(session) if action == 'CREATE_CONVERSATION' else None
            if failure is not None:
                raise web.HTTPBadGateway(text=json.dumps(failure), content_type='application/json') from None
            raise web.HTTPBadGateway(text='ServiceNow request failed; delivery may be uncertain')
        return request_id

    async def send_owned_create(self, session, payload):
        request_id = payload['requestId']
        caller = CallerBinding(session.caller_user_id,session.caller_email)
        ticket = session.caller_bootstrap
        context = dict(session.voice_context)
        source = (self.settings.instance_url,self.settings.caller_create_api_path,
                  self.settings.caller_binding_service_id,self.settings.caller_binding_agent_id,
                  self.settings.inbound_id,self.bot_url)
        if (self.settings.caller_create_api_path != CALLER_CREATE_PATH
                or self.settings.caller_binding_service_id != CALLER_SERVICE_ID
                or self.settings.caller_binding_agent_id != CALLER_AGENT_ID
                or session.voice_context.get('voice_assistant') != CALLER_SERVICE_ID
                or session.voice_context.get('global_context_profile') != CALLER_PROFILE_ID
                or self.settings.inbound_id != 'scc-local-voice'
                or self.sessions.get(session.sid) is not session
                or session.user_id != 'voice-'+session.sid or session.caller_create_request_id
                or session.failed or session.ending or session.ended or self.stopping
                or session.bootstrap_stage != 'creating' or session.pending_action != 'CREATE_CONVERSATION'
                or session.conversation_binding is not None or ticket is None):
            raise ValueError('Native caller CREATE unavailable')
        authorization,remaining,deadline = ticket.claim_create()
        if self.settings.presentation_history_enabled is True:
            try:
                session.presentation_lease = ticket.delegate_presentation(session)
                _grant_diagnostic('delegated')
            except Exception:
                session.presentation_disabled = True
        session.caller_create_request_id = request_id
        request = {'version':1,'requestId':request_id,'clientSessionId':session.sid,
                   'clientMessageId':payload['message']['clientMessageId']}
        session.caller_create_task = self.track_owned_task(asyncio.create_task(
            self.run_owned_create(session, request, caller, context, source, ticket,
                                  authorization, min(deadline, time.monotonic()+min(30,remaining)))))
        authorization = None
        await asyncio.shield(session.caller_create_task)

    async def run_owned_create(self, session, request, caller, context, source, ticket,
                               authorization, deadline):
        try:
            async with asyncio.timeout(max(0, deadline-time.monotonic())):
                created = await create_native_caller_conversation(source[0], source[1],
                    self.sn_token, authorization, dict(request),
                    timeout_seconds=max(.001, min(30, deadline-time.monotonic())))
        except BaseException as error:
            session.failed = True
            session.busy = False
            if type(error) is CallerCreateFailure:
                self.record_create_failure(session, error, request, caller, context, source)
            raise
        finally:
            authorization = None
        if (time.monotonic() >= deadline or self.sessions.get(session.sid) is not session
                or CallerBinding(session.caller_user_id,session.caller_email) != caller
                or session.voice_context != context
                or (self.settings.instance_url,self.settings.caller_create_api_path,
                    self.settings.caller_binding_service_id,self.settings.caller_binding_agent_id,
                    self.settings.inbound_id,self.bot_url) != source
                or session.sid != request['clientSessionId'] or session.user_id != 'voice-'+session.sid
                or session.caller_create_request_id != request['requestId']
                or session.bootstrap_stage != 'creating' or session.pending_action != 'CREATE_CONVERSATION'
                or not session.requests or session.requests[-1] != request['requestId']
                or session.conversation_binding is not None):
            LOG.warning('Caller CREATE failed stage=owner_result_changed http_status=200 dispatch_state=response_received')
            raise ValueError('Native caller CREATE changed')
        # Valid late results establish cleanup ownership, never renewed authority.
        created = validated_created({'result':{'status':'success','created':created}},request)
        self.observe_conversation_binding(session,created)
        identity = self.owned_cleanup_identity(session)
        if 'nowSessionId' in created:
            session.now_session = created['nowSessionId']
        if (self.stopping or session.ending or session.failed or session.ended
                or not ticket.available or session.caller_bootstrap is not ticket):
            self.begin_owned_cleanup(session)
            return identity
        self.queue_presentation_attestation(session, identity)
        self.consume(session,created)
        self.queue_start_created(session,request['requestId'])
        return identity

    async def events(self, request):
        session = request._voice_session
        cursor = max(0, int(request.query.get('after', '0')))
        wait = min(20, max(0, float(request.query.get('wait', '20'))))
        # A terminal-only callback can precede its final text. Never let the
        # normal 20-second long poll hide the bounded end of that drain.
        if session.completion_deadline:
            wait = min(wait, max(0, session.completion_deadline - time.monotonic()))
        if session.sequence <= cursor and wait:
            session.change.clear()
            try:
                await asyncio.wait_for(session.change.wait(), wait)
            except asyncio.TimeoutError:
                pass
        self.expire()
        state = {'events': [item for item in session.events if item['id'] > cursor],
            'backendEvents': [item for item in session.backend_events if item['id'] > cursor],
            'cursor': session.sequence, 'busy': session.busy, 'ended': session.ended,
            'failed': session.failed, 'started': session.started, 'choices': session.choices,
            'inputLabel': session.input_label,
            'processing': session.progress.snapshot(now=time.monotonic()) if session.busy else None}
        if session.requests:
            state['backendState'] = dict(source='servicenow_bridge_state', requestId=session.requests[-1],
                action=session.pending_action or 'MESSAGE', busy=session.busy, ended=session.ended, failed=session.failed)
        if session.conversation_binding is not None:
            state['conversationBinding'] = session.conversation_binding.snapshot()
        if (session.input_boundary_request_id and not session.busy and not session.ended
                and not session.failed and session.pending_action in ('', 'START_CREATED_CONVERSATION')
                and not session.bootstrap_stage):
            state['inputBoundary'] = {'source': 'servicenow_input_control',
                'businessRequestId': session.input_boundary_request_id,
                'controlType': session.input_boundary_kind}
            if session.input_control_receipt is not None:
                state['inputControl'] = dict(session.input_control_receipt)
        return web.json_response(state)

    async def callback(self, request):
        if not self.settings.service_now_enabled:
            raise web.HTTPServiceUnavailable(text='ServiceNow is disabled')
        if not secrets.compare_digest(request.headers.get('Authorization', ''), self.callback_auth):
            LOG.warning('Callback authentication rejected; check the configured Basic credential')
            raise web.HTTPUnauthorized()
        try:
            data = await request.json()
        except (ValueError, UnicodeError):
            raise web.HTTPBadRequest(text='JSON required')
        if not isinstance(data, dict) or not isinstance(data.get('body', []), list):
            raise web.HTTPBadRequest(text='Invalid callback envelope')
        self.expire()
        session = self.sessions.get(data.get('clientSessionId'))
        current_request_id = session.requests[-1] if session and session.requests else ''
        matched_request_id = (session.context_requests.resolve(data.get('requestId'), current_request_id)
                              if session else None)
        is_alias = bool(matched_request_id and data.get('requestId') != matched_request_id)
        LOG.info('Bot callback request_id=%s matched=%s match_kind=%s business_request_id=%s completed=%s controls=%s',
                 data.get('requestId'), bool(matched_request_id),
                 'context_alias' if is_alias else 'current' if matched_request_id else 'none',
                 matched_request_id, data.get('completed'),
                 [item.get('uiType') for item in data.get('body', []) if isinstance(item, dict)])
        if session and session.ending and session.caller_create_request_id:
            # Existing native completed flag, exact latched END request only.
            # It proves conversation end, never business-worker/order completion.
            if (session.cleanup_request_id and data.get('requestId') == session.cleanup_request_id
                    and current_request_id == session.cleanup_request_id
                    and data.get('userId') == session.user_id and data.get('completed') is True
                    and data.get('streamActive') is not True
                    and data.get('streamState') not in ('START', 'INPROGRESS')):
                self.finish_owned_cleanup(session)
            return web.json_response({'ok': True})
        if (session and matched_request_id
                and not session.ending and not session.failed
                and (not session.ended or session.completion_deadline)):
            if session.caller_create_request_id and any(isinstance(control,dict)
                    and control.get('actionType') == 'CreateConversation' for control in data.get('body',[])):
                # Only the direct own-API response can bind this selected CREATE.
                return web.json_response({'ok':True})
            if (data.get('userId') not in (None, '', session.user_id)
                    or is_alias and data.get('userId') != session.user_id):
                raise web.HTTPBadRequest(text='Identity mismatch')
            if self.callback_diagnostics_remaining:
                self.callback_diagnostics_remaining -= 1
                LOG.info('Bot callback metadata request_id=%s utc_ms=%d data=%s',
                         data.get('requestId'), int(time.time()*1000), json.dumps(callback_metadata(data)))
            LOG.info('Bot callback stage=matched elapsed_ms=%d controls=%d',
                     max(0,int((time.monotonic()-session.pending_since)*1000)),len(data.get('body',[])))
            self.ingest_output(session, data, matched_request_id)
        # No audio synthesis, downstream HTTP or long-running work in this handler.
        return web.json_response({'ok': True})

    def consume_start_response(self, session, payload, response):
        # HTTP supplies the session association, but content must independently
        # match the exact outstanding START before it can mutate dialogue state.
        if (self.stopping or self.sessions.get(session.sid) is not session
                or session.ending or session.failed or session.ended
                or session.pending_action != 'START_CREATED_CONVERSATION'
                or not session.requests or session.requests[-1] != payload['requestId']):
            return
        if not isinstance(response, dict):
            raise ValueError('Invalid START response')
        content = response.get('result', response)
        if not isinstance(content, dict):
            raise ValueError('Invalid START content')
        for envelope in (response, content):
            if ('error' in envelope or 'errors' in envelope
                    or 'status' in envelope and envelope['status'] != 'success'):
                raise ValueError('START failed')
        if content == {'status': 'success'}:
            return  # Transport confirmation alone never establishes readiness.
        if (content.get('requestId') != payload['requestId']
                or content.get('userId') != payload['userId']
                or any(key in content and content[key] != payload[key]
                       for key in ('clientSessionId', 'appInboundId'))
                or not isinstance(content.get('body'), list)):
            raise ValueError('Invalid START correlation')
        binding = session.conversation_binding
        for control in content['body']:
            if (not isinstance(control, dict) or not isinstance(control.get('uiType'), str)
                    or not control['uiType']
                    or 'options' in control and not isinstance(control['options'], list)):
                raise ValueError('Invalid START control')
            options = control.get('options', [])
            if any(not isinstance(option, dict) or not isinstance(option.get('value'), str)
                   for option in options):
                raise ValueError('Invalid START options')
            if 'uiMetadata' in control and not isinstance(control['uiMetadata'], dict):
                raise ValueError('Invalid START metadata')
            if control['uiType'] == 'TopicPickerControl':
                categories = control.get('uiMetadata', {}).get('categories', [])
                if not isinstance(categories, list):
                    raise ValueError('Invalid START topic categories')
                for category in categories:
                    if not isinstance(category, dict):
                        raise ValueError('Invalid START topic category')
                    options = category.get('options', [])
                    if (not isinstance(options, list)
                            or any(not isinstance(option, dict)
                                   or not isinstance(option.get('value'), str) for option in options)):
                        raise ValueError('Invalid START topic options')
            if control.get('actionType') == 'CreateConversation':
                raise ValueError('Unexpected CREATE during START')
            if control.get('actionType') == 'StartConversation' and binding is not None:
                if any(key in control and control[key] != expected for key, expected in (
                        ('conversationId', binding.conversation_id),
                        ('interactionId', binding.interaction_id))):
                    raise ValueError('START binding conflict')
        self.ingest_output(session, content, payload['requestId'])

    def ingest_output(self, session, data, matched_request_id):
        # Both transport boundaries authenticate/correlate before entering here.
        # Fingerprint the actual content before normalizing callback aliases.
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        if fingerprint in session.fingerprints:
            return
        if data.get('requestId') != matched_request_id:
            data = dict(data, requestId=matched_request_id)
        self.observe_conversation_binding(session, data)
        session.fingerprints.append(fingerprint)
        if session.progress.observe(data, now=time.monotonic(), clean_text=text_only):
            session.sequence += 1
            session.change.set()
        self.consume(session, data)
        if session.failed or session.ended or session.ending:
            self.retire_caller_bootstrap(session)
        self.queue_start_created(session, data['requestId'])

    def observe_conversation_binding(self, session, data):
        # Called only after callback authentication and current request matching.
        # Missing optional envelope identity may serve legacy output, never binding.
        if (data.get('userId') != session.user_id or data.get('streamActive') is True
                or data.get('streamState') in ('START', 'INPROGRESS')):
            return
        binding = session.conversation_binding
        candidate = binding
        for control in data.get('body', [])[:100]:
            if (not isinstance(control, dict) or control.get('uiType') != 'ActionMsg'
                    or control.get('actionType') != 'CreateConversation'):
                continue
            ids = [control.get('conversationId'), control.get('messageId')]
            interaction = control.get('interactionId', '')
            if (any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value)
                    for value in ids) or not isinstance(interaction, str)
                    or interaction and not re.fullmatch(r'[0-9a-f]{32}', interaction)):
                continue
            if candidate is not None:
                if ((candidate.conversation_id, candidate.creation_message_id) != tuple(ids)
                        or interaction and candidate.interaction_id and candidate.interaction_id != interaction):
                    raise web.HTTPBadRequest(text='Conversation binding conflict')
                if (interaction and not candidate.interaction_id and session.pending_action == 'CREATE_CONVERSATION'
                        and session.bootstrap_stage in ('creating','created')
                        and data['requestId'] == candidate.create_request_id):
                    candidate = ConversationBinding(*ids, data['requestId'], interaction)
            elif (session.pending_action == 'CREATE_CONVERSATION'
                    and session.bootstrap_stage in ('creating','created')):
                candidate = ConversationBinding(*ids, data['requestId'], interaction)
        if candidate is not None and candidate != binding:
            session.conversation_binding = candidate
            session.sequence += 1
            session.change.set()

    def queue_start_created(self, session, create_request_id):
        if (self.stopping or session.ending or session.failed or session.ended
                or session.bootstrap_stage != 'created'):
            return
        if 'global_context_profile' in session.voice_context:
            binding = session.conversation_binding
            if (binding is None or binding.create_request_id != create_request_id
                    or not binding.interaction_id or session.caller_bootstrap is None
                    or not session.caller_bootstrap.available):
                return
        # Claim this transition before scheduling, fencing duplicate CREATE callbacks.
        session.bootstrap_stage = 'starting'
        task = asyncio.create_task(self.start_created(session, create_request_id))
        self.bootstrap_tasks.add(task)
        task.add_done_callback(self.finish_bootstrap_task)
        return task

    def finish_bootstrap_task(self, task):
        self.bootstrap_tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                LOG.warning('Voice startup task failed type=%s', type(error).__name__)

    async def start_created(self, session, create_request_id):
        async with session.lock:
            if (self.stopping or self.http is None or self.http.closed
                    or self.sessions.get(session.sid) is not session
                    or session.ending or session.failed or session.ended
                    or session.bootstrap_stage != 'starting'
                    or not session.requests or session.requests[-1] != create_request_id
                    or session.pending_action != 'CREATE_CONVERSATION'):
                self.retire_caller_bootstrap(session)
                return
            try:
                if 'global_context_profile' in session.voice_context:
                    binding = session.conversation_binding
                    ticket = session.caller_bootstrap
                    if (binding is None or binding.create_request_id != create_request_id
                            or not binding.interaction_id or ticket is None or session.caller_refresh_started):
                        raise ValueError('Caller bootstrap unavailable')
                    session.caller_refresh_started = True
                    authorization, remaining, deadline = ticket.take()
                    session.caller_bootstrap = None
                    session.caller_authorization_task = asyncio.current_task()
                    caller = CallerBinding(session.caller_user_id,session.caller_email)
                    try:
                        await refresh_native_caller_session(self.settings.instance_url,
                            self.settings.caller_binding_service_id, self.settings.caller_binding_agent_id,
                            session.voice_context['global_context_profile'], authorization,
                            {'conversation_id':binding.conversation_id,'interaction_id':binding.interaction_id,
                             'create_message_id':binding.creation_message_id},
                            caller,
                            timeout_seconds=min(10,remaining))
                    finally:
                        authorization = None
                        ticket.clear()
                        session.caller_authorization_task = None
                    if (time.monotonic() >= deadline or self.stopping or session.ending or session.failed or session.ended
                            or self.sessions.get(session.sid) is not session or session.conversation_binding != binding
                            or CallerBinding(session.caller_user_id,session.caller_email) != caller
                            or session.bootstrap_stage != 'starting' or session.pending_action != 'CREATE_CONVERSATION'
                            or not session.requests or session.requests[-1] != create_request_id):
                        raise ValueError('Caller bootstrap changed')
                await self.send(session, '', True, 'START_CREATED_CONVERSATION')
            except asyncio.CancelledError:
                session.failed = True
                session.busy = False
                raise
            except web.HTTPException:
                # send already marks uncertain delivery failed; never retry startup.
                return
            except Exception as error:
                session.failed = True
                session.busy = False
                session.emit('ServiceNow konnte den Dialog nicht starten.', 'error')
                LOG.warning('Voice startup failed type=%s', type(error).__name__)
            else:
                if session.ending or session.failed or session.ended:
                    return
                session.bootstrap_stage = 'waiting_input'
                if session.bootstrap_input_ready:
                    session.bootstrap_stage = ''
                    # Retain the startup action until the next send, fencing late welcome text.
                    session.busy = False
                    session.sequence += 1
                    session.change.set()
            finally:
                self.retire_caller_bootstrap(session, preserve_presentation=
                    not (session.failed or session.ending or session.ended or self.stopping))

    def presentation_owner_alive(self, session, identity):
        return (self.settings.presentation_history_enabled is True
            and not self.stopping and self.sessions.get(session.sid) is session
            and session.started and not (session.failed or session.ending or session.ended
                or session.presentation_disabled)
            and self.owned_cleanup_identity(session) == identity)

    def queue_presentation_attestation(self, session, identity):
        lease=session.presentation_lease
        if lease is None or session.presentation_task is not None:
            return
        if not self.presentation_owner_alive(session,identity):
            self.retire_presentation(session)
            return
        task=asyncio.create_task(self.run_presentation_attestation(session,identity,lease))
        session.presentation_task=task
        self.presentation_tasks.add(task)
        task.add_done_callback(self.presentation_tasks.discard)
        _grant_diagnostic('queued',session.conversation_binding.conversation_id)

    async def run_presentation_attestation(self, session, identity, lease):
        authorization=nonce=None
        accepted=False
        try:
            if session.presentation_lease is not lease or not self.presentation_owner_alive(session,identity):
                return
            authorization, remaining, original_deadline=lease.take(session,PRESENTATION_GRANT_PURPOSE)
            _grant_diagnostic('lease_take',session.conversation_binding.conversation_id)
            started=time.monotonic()
            deadline=min(original_deadline,started+2)
            if remaining <= 0 or started >= deadline:
                return
            nonce=secrets.token_hex(32)
            payload=dict(operation='attest_presentation_history_v1',requestId=uuid.uuid4().hex,
                appInboundId=self.settings.inbound_id,clientSessionId=session.sid,
                userId=session.user_id,callerUserId=session.caller_user_id,
                conversationBinding=session.conversation_binding.snapshot(),
                nonceSha256=hashlib.sha256(nonce.encode('ascii')).hexdigest(),
                maxAgeSeconds=self.settings.session_seconds)
            remaining=deadline-time.monotonic()
            if remaining <= 0 or not self.presentation_owner_alive(session,identity):
                return
            async with asyncio.timeout_at(deadline):
                receipt=await issue_presentation_grant(self.settings.instance_url,self.sn_token,
                    authorization,payload,timeout_seconds=remaining)
            if (time.monotonic() >= deadline or session.presentation_lease is not lease
                    or session.presentation_task is not asyncio.current_task()
                    or not self.presentation_owner_alive(session,identity)
                    or not valid_grant_receipt(receipt,payload)):
                return
            session.presentation_nonce=nonce
            session.presentation_identity=identity
            # Conservative elapsed-time bound; never compare native time to host UTC.
            session.presentation_deadline=started+payload['maxAgeSeconds']
            session.presentation_timer=asyncio.get_running_loop().call_later(
                max(0,session.presentation_deadline-time.monotonic()),self.retire_presentation,session)
            accepted=True
            _grant_diagnostic('accepted',session.conversation_binding.conversation_id)
        except (Exception, asyncio.CancelledError):
            pass  # Fixed unavailable state only; optional failure cannot affect CREATE.
        finally:
            authorization=nonce=None
            lease.clear()
            if session.presentation_lease is lease:
                session.presentation_lease=None
            if session.presentation_task is asyncio.current_task():
                session.presentation_task=None
            if not accepted:
                self.retire_presentation(session)

    @staticmethod
    def retire_presentation(session):
        binding=session.conversation_binding
        _grant_diagnostic('retired',getattr(binding,'conversation_id',''))
        session.presentation_nonce=''
        session.presentation_identity=None
        session.presentation_deadline=0
        session.presentation_disabled=True
        if session.presentation_timer is not None:
            session.presentation_timer.cancel()
            session.presentation_timer=None
        if session.presentation_lease is not None:
            session.presentation_lease.clear()
            session.presentation_lease=None
        task=session.presentation_task
        session.presentation_task=None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    @staticmethod
    def retire_caller_bootstrap(session, *, preserve_presentation=False):
        if not preserve_presentation and (session.presentation_lease is not None
                or session.presentation_task is not None or session.presentation_nonce):
            Bridge.retire_presentation(session)
        if session.caller_bootstrap is not None:
            session.caller_bootstrap.clear()
            session.caller_bootstrap = None
        task = session.caller_authorization_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def consume(self, session, data):
        active_message = (session.busy and not session.pending_action
                          and not session.bootstrap_stage)
        suppress_startup_text = ('global_context_profile' in session.voice_context and
            (bool(session.bootstrap_stage) or session.pending_action in
             ('CREATE_CONVERSATION', 'START_CREATED_CONVERSATION')))
        previous_sequence = session.sequence
        previous_state = (session.busy, session.ended, session.failed, session.input_label,
            tuple((item['label'], item['value']) for item in session.choices))
        if any(isinstance(control, dict) and str(control.get('maskType', '')).upper() == 'SECURE'
               for control in data.get('body', [])):
            session.failed = True
            self.retire_caller_bootstrap(session)
            session.busy = False
            session.choices = []
            session.input_label = ''
            session.completion_deadline = 0
            session.emit('Dieser Dialog benötigt eine geschützte Eingabe oder Ausgabe. Dieser Sprachclient unterstützt diesen Schritt nicht.', 'notice')
            return
        if data.get('streamState') in ('START', 'INPROGRESS') or data.get('streamActive') is True:
            return
        now_id = data.get('nowSessionId')
        if not session.ended and isinstance(now_id, str) and len(now_id) < 256:
            session.now_session = now_id
        for control in data.get('body', [])[:100]:
            if not isinstance(control, dict):
                continue
            if any(control.get(name) and control[name] != 'END' for name in ('streaming', 'streamingStatus')):
                continue
            kind = control.get('uiType')
            if session.ended and kind != 'OutputText':
                # Drain final output only; controls cannot reopen this session.
                continue
            if kind == 'OutputText':
                # Publish only complete text; never speak partial stream chunks.
                streaming = control.get('streaming') or control.get('streamingStatus')
                if streaming and streaming != 'END':
                    continue
                if not suppress_startup_text:
                    text = text_only(control.get('value') or control.get('label'))
                    session.emit_bot_once(text)
                    if text:
                        session.emit_backend_once(data['requestId'], kind, text)
            elif kind in ('InputText', 'Picker', 'TopicPickerControl', 'Boolean', 'Date', 'DateTime', 'Time'):
                if session.requests and (active_message or
                        session.pending_action == 'START_CREATED_CONVERSATION'):
                    session.input_boundary_request_id = session.requests[-1]
                    session.input_boundary_kind = kind
                if session.bootstrap_stage:
                    if session.ending or session.pending_action != 'START_CREATED_CONVERSATION':
                        continue
                    session.bootstrap_input_ready = True
                    if session.bootstrap_stage == 'waiting_input':
                        session.bootstrap_stage = ''
                session.input_label = text_only(control.get('label') or control.get('promptMsg'))
                if not suppress_startup_text:
                    session.emit_bot_once(session.input_label)
                uid = control.get('uniqueIdentifier', '')
                uid = uid if type(uid) is str and len(uid) <= 256 else ''
                session.input_control_receipt = session.emit_backend_once(data['requestId'], kind,
                    session.input_label, uid)
                choices = control.get('options', [])
                # The installed topic picker stores its actual offered options
                # under uiMetadata.categories. Submit only those server choices.
                metadata = control.get('uiMetadata')
                if kind == 'TopicPickerControl' and 'options' not in control and isinstance(metadata, dict):
                    categories = metadata.get('categories')
                    choices = [option for category in categories[:50] if isinstance(category, dict)
                        and isinstance(category.get('options'), list) for option in category['options'][:50]] \
                        if isinstance(categories, list) else []
                session.choices = [{'label': text_only(option.get('label'))[:200], 'value': option['value']}
                    for option in choices[:50] if isinstance(option, dict) and
                    isinstance(option.get('value'), str) and len(option['value']) <= 4000 and
                    option.get('enabled', True) is not False] if isinstance(choices, list) else []
                session.busy = bool(session.bootstrap_stage)
                session.change.set()
            elif (kind == 'ActionMsg' and control.get('actionType') == 'CreateConversation'
                  and session.pending_action == 'CREATE_CONVERSATION'
                  and session.bootstrap_stage == 'creating'):
                session.bootstrap_stage = 'created'
            elif (kind == 'ActionMsg' and control.get('actionType') == 'StartConversation'
                  and session.pending_action == 'START_CONVERSATION'
                  and not session.bootstrap_stage):
                # Preserve the legacy START confirmation contract.
                session.pending_action = ''
                session.busy = False
            elif kind not in ('ActionMsg', 'StreamStart', 'StreamChunk', None):
                session.emit('Dieser Schritt enthält ein nicht unterstütztes Bedienelement: ' + str(kind)[:80], 'notice')
        if session.ended:
            # Duplicate terminal callbacks must never extend the fixed deadline.
            return
        if (data.get('streamState') == 'END' and not self.settings.wait_for_input_control
                and not session.bootstrap_stage):
            session.busy = False
        if data.get('completed') is True:
            session.ended = True
            self.retire_caller_bootstrap(session)
            session.caller_user_id = session.caller_email = ''
            # End input immediately, but keep the native reader alive briefly
            # for reordered final OutputText from this same MESSAGE request.
            session.completion_deadline = (time.monotonic() + TERMINAL_DRAIN_SECONDS
                if active_message and not session.ending and not session.failed else 0)
            session.busy = bool(session.completion_deadline)
            session.choices = []
        current_state = (session.busy, session.ended, session.failed, session.input_label,
            tuple((item['label'], item['value']) for item in session.choices))
        if session.sequence == previous_sequence and current_state != previous_state:
            # State-only callbacks advance the same high-water cursor as text.
            # A later poll returns this transition once, then long-polls normally.
            session.sequence += 1
        session.change.set()

    async def transcribe(self, request):
        if self.audio_lock.locked():
            raise web.HTTPServiceUnavailable(text='Audio is busy')
        async with self.audio_lock:
            reader = await request.multipart()
            part = await reader.next()
            if not part or part.name != 'file':
                raise web.HTTPBadRequest(text='WAV file required')
            data = bytearray()
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_WAV:
                    raise web.HTTPRequestEntityTooLarge(max_size=MAX_WAV, actual_size=len(data))
            try:
                with wave.open(io.BytesIO(data)) as wav:
                    if wav.getsampwidth() != 2 or wav.getnchannels() != 1 or wav.getnframes() / wav.getframerate() > 60:
                        raise ValueError()
            except (wave.Error, EOFError, ValueError, ZeroDivisionError):
                raise web.HTTPBadRequest(text='Use mono PCM16 WAV, maximum 60 seconds')
            form = FormData()
            form.add_field('model', 'qwen3-asr-0.6b')
            form.add_field('language', 'de')
            form.add_field('file', bytes(data), filename='utterance.wav', content_type='audio/wav')
            try:
                async with self.http.post(self.asr_url, data=form,
                        headers={'Authorization': 'Bearer ' + self.audio_token}, allow_redirects=False) as response:
                    raw = await read_limited(response.content, 65536)
                    if response.status != 200 or len(raw) > 65536:
                        raise ValueError()
                    result = json.loads(raw)
                    text = result.get('text')
                    if not isinstance(text, str):
                        raise ValueError()
                    return web.json_response({'text': text[:4000]})
            except Exception:
                raise web.HTTPBadGateway(text='Speech recognition unavailable')

    async def speak(self, request):
        data = await self.json(request)
        event = next((event for event in request._voice_session.events if event['id'] == data.get('eventId') and event['kind'] == 'bot'), None)
        if not event:
            raise web.HTTPBadRequest(text='Bot output not found')
        return await self.synthesize(event['text'])

    async def audio_test(self, request):
        data = await self.json(request)
        text = data.get('text', '')
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise web.HTTPBadRequest(text='Audio test text must be 1 to 500 characters')
        return await self.synthesize(text.strip())

    async def synthesize(self, text):
        if len(text) > 1500:
            raise web.HTTPBadRequest(text='Answer exceeds speech limit; read the displayed text')
        if self.audio_lock.locked():
            raise web.HTTPServiceUnavailable(text='Audio is busy')
        async with self.audio_lock:
            try:
                async with self.http.post(self.tts_url, json={'model': 'qwen3-tts-0.6b',
                        'input': text, 'voice': self.settings.tts_voice, 'response_format': 'wav'},
                        headers={'Authorization': 'Bearer ' + self.audio_token}, allow_redirects=False) as response:
                    audio = await read_limited(response.content, MAX_WAV)
                    if response.status != 200 or len(audio) > MAX_WAV or not audio.startswith(b'RIFF'):
                        raise ValueError()
                    return web.Response(body=audio, content_type='audio/wav')
            except Exception:
                raise web.HTTPBadGateway(text='Speech synthesis unavailable; text remains available')


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    settings = Settings(**config['settings'])
    if 'SCC_VOICE_INSTANCE_URL' in os.environ:
        settings.instance_url = os.environ['SCC_VOICE_INSTANCE_URL']
    settings.instance_url = validated_instance_url(settings.instance_url, required=settings.service_now_enabled)
    if not (1 <= settings.max_sessions <= 32 and 60 <= settings.session_seconds <= 3600 and
            10 <= settings.turn_seconds <= 600 and 1024 <= settings.ui_port <= 65535 and
            1024 <= settings.callback_port <= 65535 and settings.ui_port != settings.callback_port):
        raise ValueError('Invalid limits or ports')
    values = []
    for key in ('servicenow_token_file', 'audio_token_file', 'callback_token_file'):
        if not settings.service_now_enabled and key != 'audio_token_file':
            values.append('')
            continue
        value = Path(config[key]).read_text(encoding='utf-8-sig').strip()
        if len(value) < 16 or '\n' in value or '\r' in value:
            raise ValueError('Invalid credential file: ' + key)
        values.append(value)
    return Bridge(settings, *values)


async def serve(bridge):
    ui = web.AppRunner(bridge.ui_app(), access_log=None)
    callbacks = web.AppRunner(bridge.callback_app(), access_log=None)
    await ui.setup()
    await callbacks.setup()
    try:
        await web.TCPSite(ui, '127.0.0.1', bridge.settings.ui_port).start()
        await web.TCPSite(callbacks, '127.0.0.1', bridge.settings.callback_port).start()
        LOG.info('Local UI ready on port %s; isolated callback on port %s', bridge.settings.ui_port, bridge.settings.callback_port)
        await asyncio.Event().wait()
    finally:
        try:
            await ui.cleanup()
        finally:
            await callbacks.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        asyncio.run(serve(load_config(args.config)))
    except KeyboardInterrupt:
        pass
