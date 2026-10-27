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
    from .callback_progress import CallbackProgress
    from .context_updates import ContextRequestAliases, action_acknowledged, update_payload, validate_update
else:
    from callback_progress import CallbackProgress
    from context_updates import ContextRequestAliases, action_acknowledged, update_payload, validate_update

STATIC = Path(__file__).parent / 'static'
MAX_WAV = 20 * 1024 * 1024
TERMINAL_DRAIN_SECONDS = 2.0
LOG = logging.getLogger('voice-bridge')


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
        self.http = None
        self.stopping = False
        self.bootstrap_tasks = set()
        self.audio_lock = asyncio.Lock()

    async def lifecycle(self, app):
        self.stopping = False
        self.http = ClientSession(timeout=ClientTimeout(total=180), trust_env=False)
        yield
        self.stopping = True
        if self.bootstrap_tasks:
            LOG.warning('Bridge startup shutdown unresolved=%d', len(self.bootstrap_tasks))
        await self.http.close()
        if self.bootstrap_tasks:
            await asyncio.gather(*list(self.bootstrap_tasks), return_exceptions=True)

    def expire(self):
        now = time.monotonic()
        for sid, session in list(self.sessions.items()):
            if now - session.created > self.settings.session_seconds:
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
        session = self.sessions.get(request.cookies.get('scc_voice', ''))
        request._voice_session = session
        if request.path.startswith('/api/') and request.path != '/api/session':
            if not session:
                raise web.HTTPUnauthorized(text='Session expired; reload page')
            if request.method != 'GET' and (sent_origin != self.origin or not secrets.compare_digest(
                    request.headers.get('X-CSRF-Token', ''), session.csrf)):
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
            if session.started:
                raise web.HTTPConflict(text='Conversation already started')
            session.voice_context = context
            session.started = True
            if 'global_context_profile' in context:
                # Native Voice creates, then starts, before the first utterance.
                session.bootstrap_stage = 'creating'
                await self.send(session, '', True, 'CREATE_CONVERSATION')
            elif self.settings.defer_start_until_message:
                # Preserve the legacy first-text creation contract.
                session.change.set()
            else:
                await self.send(session, '', True, 'START_CONVERSATION')
        return web.json_response({'accepted': True}, status=202)

    async def reset(self, request):
        await self.json(request)
        old = request._voice_session
        old.ending = True
        async with old.lock:
            if old.started and old.requests and not old.ended:
                # Explicit reset ends the VA session, even if the previous turn timed out.
                await self.send(old, '', True, 'END_CONVERSATION')
            self.sessions.pop(old.sid, None)
        request._voice_session = None
        return await self.session(request)

    async def end(self, request):
        await self.json(request)
        session = request._voice_session
        session.ending = True
        async with session.lock:
            if session.started and session.requests and not session.ended:
                # End only the authenticated cookie's conversation. Keep it if
                # the backend does not acknowledge ending, so retry is explicit.
                await self.send(session, '', True, 'END_CONVERSATION')
            self.sessions.pop(session.sid, None)
            session.ended = True
        response = web.json_response({'ended': True})
        response.del_cookie('scc_voice', path='/')
        return response

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
            await self.send(session, value.strip() if typed else value, typed, history=history)
        return web.json_response({'accepted': True}, status=202)

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

    async def send(self, session, text, typed, action='', history=None):
        # Serialize HTTP dispatch only. Callbacks never acquire this lock, and
        # it is never held for the ensuing business conversation/callback wait.
        async with session.context_lock:
            await self._send_locked(session, text, typed, action, history)

    async def _send_locked(self, session, text, typed, action='', history=None):
        request_id = uuid.uuid4().hex
        payload = {'requestId': request_id, 'appInboundId': self.settings.inbound_id,
            'clientSessionId': session.sid, 'userId': session.user_id,
            'emailId': self.settings.email, 'message': {'text': text, 'typed': typed,
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
        # Reset before the HTTP await: callbacks may arrive before its ACK.
        session.turn_texts.clear()
        session.completion_deadline = 0
        session.context_requests.clear()
        session.input_boundary_request_id = session.input_boundary_kind = ''
        session.requests.append(request_id)
        session.progress.begin_request(request_id)
        LOG.info('Bot request id=%s action=%s', request_id, action or 'MESSAGE')
        session.busy = True
        session.pending_action = action
        session.pending_since = time.monotonic()
        session.choices = []
        session.input_label = ''
        try:
            async with self.http.post(self.bot_url, json=payload, headers={'token': self.sn_token,
                    'Accept': 'application/json'}, allow_redirects=False, timeout=ClientTimeout(total=30)) as response:
                raw = await read_limited(response.content, 65536)
                if response.status not in (200, 201, 202) or len(raw) > 65536:
                    raise RuntimeError('Bot request rejected')
                ack = json.loads(raw) if raw else {}
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
            session.emit('ServiceNow hat die Anfrage nicht bestätigt. Bitte einen neuen Dialog starten.', 'error')
            LOG.warning('Bot request failed; no credentials or payload logged')
            raise web.HTTPBadGateway(text='ServiceNow request failed; delivery may be uncertain')

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
            'cursor': session.sequence, 'busy': session.busy, 'ended': session.ended,
            'failed': session.failed, 'started': session.started, 'choices': session.choices,
            'inputLabel': session.input_label,
            'processing': session.progress.snapshot(now=time.monotonic()) if session.busy else None}
        if session.conversation_binding is not None:
            state['conversationBinding'] = session.conversation_binding.snapshot()
        if (session.input_boundary_request_id and not session.busy and not session.ended
                and not session.failed and session.pending_action in ('', 'START_CREATED_CONVERSATION')
                and not session.bootstrap_stage):
            state['inputBoundary'] = {'source': 'servicenow_input_control',
                'businessRequestId': session.input_boundary_request_id,
                'controlType': session.input_boundary_kind}
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
        if (session and matched_request_id
                and not session.ending and not session.failed
                and (not session.ended or session.completion_deadline)):
            if (data.get('userId') not in (None, '', session.user_id)
                    or is_alias and data.get('userId') != session.user_id):
                raise web.HTTPBadRequest(text='Identity mismatch')
            if self.callback_diagnostics_remaining:
                self.callback_diagnostics_remaining -= 1
                LOG.info('Bot callback metadata request_id=%s utc_ms=%d data=%s',
                         data.get('requestId'), int(time.time()*1000), json.dumps(callback_metadata(data)))
            LOG.info('Bot callback stage=matched elapsed_ms=%d controls=%d',
                     max(0,int((time.monotonic()-session.pending_since)*1000)),len(data.get('body',[])))
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            if fingerprint not in session.fingerprints:
                # Dedup the actual authenticated wire envelope, then normalize
                # only its known request alias for the existing state machines.
                if is_alias:
                    data = dict(data, requestId=matched_request_id)
                self.observe_conversation_binding(session, data)
                session.fingerprints.append(fingerprint)
                if session.progress.observe(data, now=time.monotonic(), clean_text=text_only):
                    session.sequence += 1
                    session.change.set()
                self.consume(session, data)
                self.queue_start_created(session, data['requestId'])
        # No audio synthesis, downstream HTTP or long-running work in this handler.
        return web.json_response({'ok': True})

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
                        or interaction and candidate.interaction_id != interaction):
                    raise web.HTTPBadRequest(text='Conversation binding conflict')
            elif (session.pending_action == 'CREATE_CONVERSATION'
                    and session.bootstrap_stage == 'creating'):
                candidate = ConversationBinding(*ids, data['requestId'], interaction)
        if binding is None and candidate is not None:
            session.conversation_binding = candidate
            session.sequence += 1
            session.change.set()

    def queue_start_created(self, session, create_request_id):
        if (self.stopping or session.ending or session.failed or session.ended
                or session.bootstrap_stage != 'created'):
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
                return
            try:
                await self.send(session, '', True, 'START_CREATED_CONVERSATION')
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
        await callbacks.cleanup()
        await ui.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        asyncio.run(serve(load_config(args.config)))
    except KeyboardInterrupt:
        pass
