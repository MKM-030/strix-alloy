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
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit
import uuid
import wave

from aiohttp import ClientSession, ClientTimeout, FormData, web

INSTANCE = 'https://soprasteriaassvsdemo14.service-now.com'
STATIC = Path(__file__).parent / 'static'
MAX_WAV = 20 * 1024 * 1024
LOG = logging.getLogger('voice-bridge')


@dataclass
class Settings:
    user_id: str = ''
    service_now_enabled: bool = True
    email: str = ''
    inbound_id: str = 'scc-local-voice'
    ui_port: int = 8850
    callback_port: int = 8853
    callback_username: str = ''
    tts_voice: str = 'ryan'
    session_seconds: int = 1800
    turn_seconds: int = 180
    max_sessions: int = 8


@dataclass
class Conversation:
    sid: str = field(default_factory=lambda: uuid.uuid4().hex)
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    created: float = field(default_factory=time.monotonic)
    started: bool = False
    ended: bool = False
    busy: bool = False
    failed: bool = False
    pending_since: float = 0
    now_session: str = ''
    requests: deque = field(default_factory=lambda: deque(maxlen=128))
    fingerprints: deque = field(default_factory=lambda: deque(maxlen=256))
    events: deque = field(default_factory=lambda: deque(maxlen=200))
    sequence: int = 0
    choices: list = field(default_factory=list)
    input_label: str = ''
    change: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def emit(self, text='', kind='bot'):
        self.sequence += 1
        self.events.append({'id': self.sequence, 'kind': kind, 'text': text[:8000]})
        self.change.set()


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


class Bridge:
    def __init__(self, settings, sn_token, audio_token, callback_token):
        if not audio_token or (settings.service_now_enabled and (not settings.user_id or not sn_token or not callback_token)):
            raise ValueError('Server identity and all three credentials are required')
        self.settings = settings
        self.sn_token, self.audio_token = sn_token, audio_token
        if settings.callback_username:
            value = base64.b64encode((settings.callback_username + ':' + callback_token).encode()).decode()
            self.callback_auth = 'Basic ' + value
        else:
            self.callback_auth = 'Bearer ' + callback_token
        self.bot_url = INSTANCE + '/api/sn_va_as_service/bot/integration'
        self.asr_url = 'http://127.0.0.1:8851/v1/audio/transcriptions'
        self.tts_url = 'http://127.0.0.1:8852/v1/audio/speech'
        self.origin = 'http://127.0.0.1:' + str(settings.ui_port)
        self.sessions = {}
        self.http = None
        self.audio_lock = asyncio.Lock()

    async def lifecycle(self, app):
        self.http = ClientSession(timeout=ClientTimeout(total=180), trust_env=False)
        yield
        await self.http.close()

    def expire(self):
        now = time.monotonic()
        for sid, session in list(self.sessions.items()):
            if now - session.created > self.settings.session_seconds:
                del self.sessions[sid]
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
        app.router.add_post('/api/message', self.message)
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
            session = Conversation()
            self.sessions[session.sid] = session
        response = web.json_response({'csrf': session.csrf, 'started': session.started,
            'serviceNowEnabled': self.settings.service_now_enabled,
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
        await self.json(request)
        session = request._voice_session
        async with session.lock:
            if session.started:
                raise web.HTTPConflict(text='Conversation already started')
            session.started = True
            await self.send(session, '', True, 'START_CONVERSATION')
        return web.json_response({'accepted': True}, status=202)

    async def reset(self, request):
        await self.json(request)
        old = request._voice_session
        async with old.lock:
            if old.started and not old.ended:
                # Explicit reset ends the VA session, even if the previous turn timed out.
                await self.send(old, '', True, 'END_CONVERSATION')
            self.sessions.pop(old.sid, None)
        request._voice_session = None
        return await self.session(request)

    async def message(self, request):
        data = await self.json(request)
        session = request._voice_session
        async with session.lock:
            if not session.started or session.busy or session.ended or session.failed:
                raise web.HTTPConflict(text='Conversation is not ready for input')
            typed = 'choice' not in data
            value = data.get('text') if typed else data.get('choice')
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise web.HTTPBadRequest(text='Input must be 1 to 4000 characters')
            if not typed and value not in [item['value'] for item in session.choices]:
                raise web.HTTPBadRequest(text='Choice not available')
            await self.send(session, value.strip() if typed else value, typed)
        return web.json_response({'accepted': True}, status=202)

    async def send(self, session, text, typed, action=''):
        request_id = uuid.uuid4().hex
        payload = {'requestId': request_id, 'appInboundId': self.settings.inbound_id,
            'clientSessionId': session.sid, 'userId': self.settings.user_id,
            'emailId': self.settings.email, 'message': {'text': text, 'typed': typed,
            'clientMessageId': uuid.uuid4().hex}, 'clientVariables': {'voiceSessionId': session.sid}}
        if session.now_session:
            payload['nowSessionId'] = session.now_session
        if action:
            payload['action'] = action
        session.requests.append(request_id)
        session.busy = True
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
        if session.sequence <= cursor and wait:
            session.change.clear()
            try:
                await asyncio.wait_for(session.change.wait(), wait)
            except asyncio.TimeoutError:
                pass
        self.expire()
        return web.json_response({'events': [item for item in session.events if item['id'] > cursor],
            'cursor': session.sequence, 'busy': session.busy, 'ended': session.ended,
            'failed': session.failed, 'started': session.started, 'choices': session.choices,
            'inputLabel': session.input_label})

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
        if session and session.requests and data.get('requestId') == session.requests[-1] and not session.ended:
            if data.get('userId') not in (None, '', self.settings.user_id):
                raise web.HTTPBadRequest(text='Identity mismatch')
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            if fingerprint not in session.fingerprints:
                session.fingerprints.append(fingerprint)
                self.consume(session, data)
        # No audio synthesis, downstream HTTP or long-running work in this handler.
        return web.json_response({'ok': True})

    def consume(self, session, data):
        if any(isinstance(control, dict) and str(control.get('maskType', '')).upper() == 'SECURE'
               for control in data.get('body', [])):
            session.failed = True
            session.busy = False
            session.choices = []
            session.input_label = ''
            session.emit('Dieser Dialog benötigt eine geschützte Eingabe oder Ausgabe. Dieser Sprachclient unterstützt diesen Schritt nicht.', 'notice')
            return
        if data.get('streamState') in ('START', 'INPROGRESS') or data.get('streamActive') is True:
            return
        now_id = data.get('nowSessionId')
        if isinstance(now_id, str) and len(now_id) < 256:
            session.now_session = now_id
        for control in data.get('body', [])[:100]:
            if not isinstance(control, dict):
                continue
            kind = control.get('uiType')
            if kind == 'OutputText':
                # Streaming is disabled for this deployment. Never speak partial chunks.
                streaming = control.get('streaming') or control.get('streamingStatus')
                if streaming and streaming != 'END':
                    continue
                text = text_only(control.get('value') or control.get('label'))
                if text:
                    session.emit(text)
            elif kind in ('InputText', 'Picker', 'TopicPickerControl', 'Boolean', 'Date', 'DateTime', 'Time'):
                session.input_label = text_only(control.get('label') or control.get('promptMsg'))
                choices = control.get('options', [])
                session.choices = [{'label': text_only(option.get('label'))[:200], 'value': option['value']}
                    for option in choices[:50] if isinstance(option, dict) and
                    isinstance(option.get('value'), str) and len(option['value']) <= 4000 and
                    option.get('enabled', True) is not False] if isinstance(choices, list) else []
                session.busy = False
                session.change.set()
            elif kind not in ('ActionMsg', 'StreamStart', 'StreamChunk', None):
                session.emit('Dieser Schritt enthält ein nicht unterstütztes Bedienelement: ' + str(kind)[:80], 'notice')
        if data.get('streamState') == 'END':
            session.busy = False
        if data.get('completed') is True:
            session.ended = True
            session.busy = False
            session.choices = []
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
