"""Native ServiceNow WebRTC transport, local speech, existing VA conversation.

No own LLM, order logic, HTML client, or replacement chat UI is included.
The HTTP listener remains loopback-only. A trusted TLS proxy and verified
ServiceNow OAuth authorization are required for a native browser deployment.
"""
import argparse
import asyncio
from dataclasses import dataclass
from fractions import Fraction
import io
import json
import logging
import math
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid
import wave

from aiohttp import ClientSession, ClientTimeout, CookieJar, FormData, WSMsgType, web
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame, AudioResampler
from core import EndpointGate, PlaybackBuffer, local_auth, authorized_agents

LOG = logging.getLogger('native-voice')
HTTP_KEY = web.AppKey('http', ClientSession)


@dataclass
class Config:
    instance_name: str = 'soprasteriaassvsdemo14'
    voice_service_id: str = ''
    port: int = 8860
    auth_mode: str = 'deny'
    required_agent_id: str = ''
    development_token: str = ''
    backend_url: str = 'http://127.0.0.1:8850'
    asr_url: str = 'http://127.0.0.1:8861/inference'
    tts_url: str = 'http://127.0.0.1:8862/v1/audio/speech'
    vad_threshold: int = 450
    vad_silence_ms: int = 1200
    max_call_seconds: int = 1800
    greeting: str = ''

    def __post_init__(self):
        if type(self.vad_silence_ms) is not int or not 300 <= self.vad_silence_ms <= 2000:
            raise ValueError('vad_silence_ms must be an integer between 300 and 2000')

    @property
    def instance_url(self):
        return 'https://' + self.instance_name + '.service-now.com'


class Speech:
    def __init__(self, http, config):
        self.http, self.config = http, config

    @staticmethod
    def log_asr_diagnostics(data):
        # Only bounded numeric summaries: never transcript, words or arbitrary keys.
        segments = data.get('segments')
        segments = segments if isinstance(segments, list) else []
        inspected = segments[:256]
        logprobs, silence = [], []
        for segment in inspected:
            if not isinstance(segment, dict):
                continue
            for key, values, low, high in (('avg_logprob', logprobs, -1000, 0),
                                           ('no_speech_prob', silence, 0, 1)):
                value = segment.get(key)
                if (type(value) in (int, float) and low <= value <= high
                        and math.isfinite(value)):
                    values.append(value)
        def formatted(value):
            return 'missing' if value is None else f'{value:.4f}'
        LOG.info('Voice ASR diagnostics segments=%d truncated=%s logprob_count=%d '
                 'avg_logprob_mean=%s avg_logprob_min=%s silence_count=%d no_speech_prob_max=%s',
                 len(inspected), len(segments)>256, len(logprobs),
                 formatted(sum(logprobs)/len(logprobs) if logprobs else None),
                 formatted(min(logprobs) if logprobs else None), len(silence),
                 formatted(max(silence) if silence else None))

    async def transcribe(self, pcm):
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        form = FormData()
        form.add_field('file', buf.getvalue(), filename='speech.wav', content_type='audio/wav')
        form.add_field('language', 'de')
        form.add_field('response_format', 'verbose_json')
        form.add_field('token_timestamps', 'false')
        form.add_field('no_language_probabilities', 'true')
        form.add_field('temperature', '0')
        async with self.http.post(self.config.asr_url, data=form, allow_redirects=False,
                                  timeout=ClientTimeout(total=30)) as response:
            if response.status != 200:
                raise RuntimeError('ASR unavailable')
            data = await response.json()
            text = data.get('text') if isinstance(data, dict) else None
            if not isinstance(text, str) or len(text) > 4000:
                raise RuntimeError('Invalid transcription')
            self.log_asr_diagnostics(data)
            return text.strip()

    async def synthesize(self, text):
        payload = {'model':'scc-native-qwen3', 'voice':'scc-demo', 'input':text,
                   'response_format':'pcm'}
        async with self.http.post(self.config.tts_url, json=payload, allow_redirects=False,
                                  timeout=ClientTimeout(total=120)) as response:
            if response.status != 200:
                raise RuntimeError('TTS unavailable')
            count = 0
            async for chunk in response.content.iter_chunked(4800):
                count += len(chunk)
                yield chunk
            if count % 2:
                raise RuntimeError('TTS returned incomplete PCM sample')


class Dialog:
    """Use the existing loopback bridge; its authenticated callbacks stay intact."""
    def __init__(self, config):
        self.config = config
        self.http = None
        self.csrf = ''
        self.cursor = 0
        self.must_reset = False
        self.first_message_pending = True
        self.greeting_history = []
        self.greeting_history_allowed = False
        self.metadata = {'conversation_id':'', 'interaction_id':''}

    async def request(self, method, path, **kwargs):
        headers = {'Origin':self.config.backend_url, 'X-CSRF-Token':self.csrf}
        async with self.http.request(method, self.config.backend_url + path, headers=headers,
                                     allow_redirects=False, **kwargs) as response:
            if response.status not in (200, 202):
                raise RuntimeError('ServiceNow conversation bridge unavailable')
            return await response.json()

    async def open(self):
        if self.http is None:
            self.http = ClientSession(cookie_jar=CookieJar(unsafe=True), trust_env=False,
                                      timeout=ClientTimeout(total=35))
        if self.must_reset:
            await self.reset_owned_session()
        info = await self.request('GET', '/api/session')
        self.csrf = info['csrf']
        self.greeting_history_allowed = info.get('initialBotHistoryAllowed') is True
        if not info.get('serviceNowEnabled'):
            raise RuntimeError('ServiceNow conversation is disabled')
        if not info.get('started'):
            await self.request('POST', '/api/start', json={})
        # START is an enqueue ACK; wait for an actual input-ready callback.
        # Deferred-start deployments are immediately ready here.
        greetings = []
        until = time.monotonic() + 185
        while time.monotonic() < until:
            state = await self.request('GET', '/api/events', params={'after':str(self.cursor),'wait':'1'})
            self.cursor = state['cursor']
            for event in state.get('events', []):
                if event.get('kind') == 'bot' and event.get('text'):
                    greetings.append(event['text'])
                elif event.get('kind') in ('error', 'notice'):
                    raise RuntimeError('ServiceNow greeting failed')
            if state.get('failed') or state.get('ended'):
                raise RuntimeError('ServiceNow conversation is not ready')
            if not state.get('busy'):
                return greetings
        raise RuntimeError('ServiceNow conversation startup timed out')

    def record_greeting(self, text):
        """Remember only our actually emitted fallback, never a backend greeting."""
        if (self.greeting_history_allowed and self.first_message_pending and
                not self.greeting_history and
                isinstance(text, str) and text.strip() and len(text) <= 4000):
            self.greeting_history = [{'isBotMessage':True, 'value':text,
                'displayName':'Bot', 'type':'text',
                'timestamp':str(int(time.time() * 1000))}]

    async def turn(self, text, on_reply=None):
        payload = {'text':text}
        if self.first_message_pending and self.greeting_history:
            payload['history'] = self.greeting_history
        # Consume before I/O: uncertain delivery must never replay the greeting.
        self.first_message_pending = False
        self.greeting_history = []
        await self.request('POST', '/api/message', json=payload)
        until = time.monotonic() + 185
        result = []
        while time.monotonic() < until:
            state = await self.request('GET', '/api/events', params={'after':str(self.cursor),'wait':'20'})
            self.cursor = state['cursor']
            for event in state.get('events', []):
                if event.get('kind') == 'bot' and event.get('text'):
                    result.append(event['text'])
                    if on_reply:
                        await on_reply(event['text'])
                elif event.get('kind') in ('error', 'notice'):
                    raise RuntimeError('ServiceNow returned an unsupported or failed turn')
            if state.get('failed'):
                raise RuntimeError('ServiceNow conversation failed')
            if not state.get('busy'):
                return result
        raise RuntimeError('ServiceNow conversation timed out')

    async def close(self):
        if self.http and self.csrf:
            # Explicitly end our own cookie session, never another user's session.
            self.must_reset = True
            try:
                await self.reset_owned_session()
            except Exception:
                LOG.warning('Owned conversation reset failed; next call requires reset')

    async def reset_owned_session(self):
        info = await self.request('POST', '/api/end', json={})
        if info.get('ended') is not True:
            raise RuntimeError('Conversation end was not acknowledged')
        self.csrf = ''
        self.cursor = 0
        self.must_reset = False
        self.first_message_pending = True
        self.greeting_history = []
        self.greeting_history_allowed = False

    async def shutdown(self):
        if self.http:
            await self.http.close()
            self.http = None


class SpeakerTrack(AudioStreamTrack):
    def __init__(self, playback):
        super().__init__()
        self.playback = playback
        self.samples = 0
        self.start_time = None

    async def recv(self):
        if self.start_time is None:
            self.start_time = time.monotonic()
        delay = self.start_time + self.samples / 24000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        frame = AudioFrame(format='s16', layout='mono', samples=480)
        frame.planes[0].update(self.playback.read(960))
        frame.sample_rate = 24000
        frame.pts = self.samples
        frame.time_base = Fraction(1, 24000)
        self.samples += 480
        return frame


class NativeCall:
    def __init__(self, config, speech, dialog):
        self.config, self.speech, self.dialog = config, speech, dialog
        self.peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.playback = PlaybackBuffer()
        self.peer.addTrack(SpeakerTrack(self.playback))
        self.channel = None
        self.pending_events = []
        self.tasks = set()
        self.turns = asyncio.Queue(maxsize=2)
        self.recognized_turns = asyncio.Queue(maxsize=2)
        self.asr_task = None
        self.failed = False
        self.call_id = uuid.uuid4().hex[:12]
        self.closed = False
        self.turn_number = 0
        self.synthesis_active = False
        self.input_started = False
        self.peer.on('datachannel', self.datachannel)
        self.peer.on('track', lambda track: self.spawn(self.microphone(track)) if track.kind == 'audio' else None)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def datachannel(self, channel):
        if channel.label != 'transcripts':
            channel.close()
            return
        self.channel = channel
        def opened():
            if any(self.dialog.metadata.values()):
                self.emit('metadata', self.dialog.metadata)
            for message in self.pending_events:
                channel.send(json.dumps(message))
            self.pending_events.clear()
        channel.on('open', opened)
        if channel.readyState == 'open':
            opened()

    def emit(self, kind, data=None):
        message = {'type':kind}
        if data is not None:
            message['data'] = data
        if self.channel and self.channel.readyState == 'open':
            self.channel.send(json.dumps(message))
        elif len(self.pending_events) < 30:
            self.pending_events.append(message)

    def notice(self, code, text):
        # Native type=error immediately closes WSS. A local notice must remain
        # visible without ending a possibly side-effecting ServiceNow request.
        self.emit('transcript', {'role':'assistant','content':text,'code':code,
            'message_id':uuid.uuid4().hex,'caller_turn_id':'','turn_num':0})

    async def microphone(self, track):
        converter = AudioResampler(format='s16', layout='mono', rate=16000)
        gate = EndpointGate(threshold=self.config.vad_threshold,
                            silence_ms=self.config.vad_silence_ms)
        try:
            while not self.closed:
                frame = await track.recv()
                if self.failed:
                    continue
                for mono in converter.resample(frame):
                    pcm = mono.to_ndarray().tobytes()
                    began, utterance = gate.feed(pcm)
                    if began:
                        self.input_started = True
                        # Fence real output interruptions, not speech while the
                        # backend is still thinking and has produced no audio.
                        # A possibly side-effecting ServiceNow request still settles.
                        playback_bytes = len(self.playback.data)
                        interrupted = self.synthesis_active or bool(playback_bytes)
                        if interrupted:
                            self.playback.interrupt()
                        LOG.info('Voice input call=%s stage=vad_start generation=%d interrupted=%s playback_bytes=%d audio_queue=%d text_queue=%d',
                                 self.call_id, self.playback.generation, interrupted, playback_bytes,
                                 self.turns.qsize(), self.recognized_turns.qsize())
                    if utterance:
                        try:
                            self.turns.put_nowait((self.playback.generation, utterance))
                            LOG.info('Voice input call=%s stage=queued audio_ms=%d audio_queue=%d text_queue=%d',
                                     self.call_id, len(utterance)*1000//32000,
                                     self.turns.qsize(), self.recognized_turns.qsize())
                        except asyncio.QueueFull:
                            LOG.info('Voice input call=%s stage=audio_queue_full', self.call_id)
                            self.notice('BUSY', 'Die letzte Aufnahme konnte nicht angenommen werden. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.')
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self.closed:
                LOG.info('Microphone track ended')

    async def recognize_turns(self):
        """Recognize accepted audio independently; never submit backend requests."""
        while not self.closed and not self.failed:
            generation, pcm = await self.turns.get()
            started = time.monotonic()
            try:
                text = await self.speech.transcribe(pcm)
                if self.closed or self.failed:
                    return
                LOG.info('Voice input call=%s stage=asr_complete audio_ms=%d seconds=%.3f empty=%s text_queue=%d',
                         self.call_id, len(pcm)*1000//32000, time.monotonic()-started,
                         not bool(text), self.recognized_turns.qsize())
                if not text:
                    self.notice('ASR_EMPTY', 'Ich konnte keine Sprache erkennen. Bitte wiederholen Sie Ihre Antwort.')
                    continue
                self.turn_number += 1
                turn = (generation, text, self.turn_number, uuid.uuid4().hex, started)
                self.transcript(turn, 'user', text)
                try:
                    self.recognized_turns.put_nowait(turn)
                except asyncio.QueueFull:
                    LOG.info('Voice input call=%s stage=text_queue_full turn=%d', self.call_id, self.turn_number)
                    self.notice('BUSY', 'Ihre letzte Antwort wurde erkannt, aber nicht weitergeleitet. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.')
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.warning('Voice input call=%s stage=asr_failed type=%s', self.call_id, type(error).__name__)
                self.notice('ASR_FAILED', 'Die Spracherkennung ist fehlgeschlagen. Bitte wiederholen Sie Ihre Antwort.')
            finally:
                self.turns.task_done()

    def transcript(self, turn, role, content):
        _, _, number, turn_id, started = turn
        self.emit('transcript', {'role':role,'content':content,'message_id':uuid.uuid4().hex,
            'caller_turn_id':turn_id,'turn_num':number,
            'latency_ms':int((time.monotonic()-started)*1000)})

    async def report_backend_failure(self):
        self.failed = True
        self.playback.interrupt()
        if self.asr_task:
            self.asr_task.cancel()
            await asyncio.gather(self.asr_task, return_exceptions=True)
        for queue in (self.turns, self.recognized_turns):
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
        notice = ('Der Sprachdialog konnte nicht fortgesetzt werden. Weitere Antworten werden nicht weitergeleitet. '
                  'Bitte beenden Sie diesen Anruf.')
        self.notice('TURN_FAILED', notice)
        # Local failure feedback only. Never cancel, retry or close a submitted Bot request here.
        try:
            async with asyncio.timeout(10):
                generation = self.playback.generation
                async for chunk in self.speech.synthesize(notice):
                    while len(self.playback.data) > 48000 and not self.closed:
                        await asyncio.sleep(.02)
                    if self.closed:
                        return
                    self.playback.put(chunk, generation)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Voice failure notice call=%s type=%s', self.call_id, type(error).__name__)

    async def process_turns(self):
        self.asr_task = self.spawn(self.recognize_turns())
        try:
            greetings = await self.dialog.open() or []
            fallback_greeting = False
            if (not greetings and self.config.greeting and self.playback.generation == 0
                    and not self.input_started):
                greetings = [self.config.greeting]
                fallback_greeting = True
            generation = self.playback.generation
            for greeting in greetings:
                self.emit('transcript', {'role':'assistant','content':greeting,
                    'message_id':uuid.uuid4().hex,'caller_turn_id':'','turn_num':0})
                if fallback_greeting:
                    self.dialog.record_greeting(greeting)
                if generation or self.input_started:
                    continue
                self.synthesis_active = True
                try:
                    async for chunk in self.speech.synthesize(greeting):
                        if generation != self.playback.generation:
                            break
                        while len(self.playback.data) > 48000 and generation == self.playback.generation:
                            await asyncio.sleep(.02)
                        self.playback.put(chunk, generation)
                finally:
                    self.synthesis_active = False
            while not self.closed and not self.failed:
                turn = await self.recognized_turns.get()
                generation, text, number, _, started = turn
                LOG.info('Voice backend call=%s stage=begin turn=%d text_queue=%d',
                         self.call_id, number, self.recognized_turns.qsize())
                def transcript(role, content):
                    self.transcript(turn, role, content)
                speech_error = None
                async def deliver(reply):
                    nonlocal speech_error
                    transcript('assistant', reply)
                    if generation != self.playback.generation or speech_error:
                        LOG.info('Voice output call=%s stage=tts_skipped turn=%d generation=%d current_generation=%d speech_error=%s',
                                 self.call_id, number, generation, self.playback.generation,
                                 bool(speech_error))
                        return
                    self.synthesis_active = True
                    try:
                        async for chunk in self.speech.synthesize(reply):
                            if generation != self.playback.generation:
                                break
                            while len(self.playback.data) > 48000 and generation == self.playback.generation:
                                await asyncio.sleep(.02)
                            self.playback.put(chunk, generation)
                    except Exception as error:
                        # Finish observing the already-submitted ServiceNow turn
                        # before reporting TTS failure; never retry/cancel an order.
                        speech_error = error
                        self.playback.interrupt()
                    finally:
                        self.synthesis_active = False
                try:
                    await self.dialog.turn(text, on_reply=deliver)
                finally:
                    self.recognized_turns.task_done()
                if speech_error:
                    raise RuntimeError('Speech output failed after ServiceNow turn settled')
                LOG.info('Voice turn completed seconds=%.2f', time.monotonic()-started)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Deliberately log type only: network exceptions can contain tokens.
            LOG.warning('Voice turn failed type=%s', type(error).__name__)
            await self.report_backend_failure()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        self.playback.interrupt()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.peer.close()
        await self.dialog.close()


async def authorize(request, config, http):
    if request.query.get('instance_name') != config.instance_name or request.query.get('voice_service_id') != config.voice_service_id:
        return False
    token = request.query.get('auth_token', '')
    if len(token) > 8192:
        return False
    if config.development_token:
        return local_auth(token, config.development_token, request.remote or '')
    if config.auth_mode != 'servicenow' or request.headers.get('Origin') != config.instance_url:
        return False
    # Syntax guard only; trust comes exclusively from native ServiceNow validation.
    if len(token.split('.')) != 3 or not all(token.split('.')):
        return False
    url = config.instance_url + '/api/sn_voice_aia/ai_voice_agent/agents_authorized'
    try:
        async with http.post(url, json={'serviceId':config.voice_service_id,'clientApp':'admin_test'},
                             headers={'Authorization':'Bearer '+token,'Accept':'application/json'},
                             allow_redirects=False, timeout=ClientTimeout(total=10)) as response:
            if response.status != 200:
                LOG.warning('Native OAuth verification denied status=%s', response.status)
                return False
            data = await response.json()
            accepted = authorized_agents(data, config.required_agent_id)
            if not accepted:
                result = data.get('result') if isinstance(data, dict) else None
                LOG.warning('Native OAuth verification envelope/agent denied result_type=%s', type(result).__name__)
            return accepted
    except Exception:
        return False


def create_app(config, speech_factory=None, dialog_factory=None, probe_backend=False):
    app = web.Application(client_max_size=256*1024)
    active = set()
    shared_dialog = Dialog(config) if dialog_factory is None else None
    async def lifecycle(app):
        app[HTTP_KEY] = ClientSession(trust_env=False, timeout=ClientTimeout(total=180))
        if probe_backend and shared_dialog:
            report = {'kind':'safe-greeting-no-order', 'native_ui_test':False}
            started = time.monotonic()
            try:
                await shared_dialog.open()
                report['ready_seconds'] = round(time.monotonic()-started, 3)
                replies = await shared_dialog.turn('Guten Tag. Bitte noch keine Bestellung auslösen.')
                report['response_seconds'] = round(time.monotonic()-started, 3)
                report['responses'] = replies
                report['ok'] = True
            except Exception as error:
                report['ok'] = False
                report['error_type'] = type(error).__name__
                report['elapsed_seconds'] = round(time.monotonic()-started, 3)
            finally:
                await shared_dialog.close()
                report['reset_ok'] = not shared_dialog.must_reset
            target = Path(__file__).parent / 'runtime' / 'backend-probe.json'
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            LOG.info('Safe backend probe ok=%s elapsed=%.2f', report['ok'], time.monotonic()-started)
        yield
        await asyncio.gather(*(call.close() for call in list(active)), return_exceptions=True)
        if shared_dialog:
            await shared_dialog.shutdown()
        await app[HTTP_KEY].close()
    app.cleanup_ctx.append(lifecycle)

    async def connect(request):
        if not await authorize(request, config, app[HTTP_KEY]):
            raise web.HTTPUnauthorized(text='Voice authorization rejected')
        if active:
            raise web.HTTPServiceUnavailable(text='Demo voice session is busy')
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=256*1024)
        speech = speech_factory(app[HTTP_KEY]) if speech_factory else Speech(app[HTTP_KEY], config)
        dialog = dialog_factory() if dialog_factory else shared_dialog
        call = NativeCall(config, speech, dialog)
        # Reserve without yielding after checking capacity, including WS upgrade.
        active.add(call)
        offered = False
        try:
            await ws.prepare(request)
            call.spawn(call.process_turns())
            async with asyncio.timeout(config.max_call_seconds):
                async for message in ws:
                    if message.type != WSMsgType.TEXT:
                        break
                    data = json.loads(message.data)
                    kind = data.get('type')
                    if kind == 'offer' and not offered:
                        sdp = data.get('sdp', {})
                        if sdp.get('type') != 'offer' or not isinstance(sdp.get('sdp'), str):
                            raise ValueError('Invalid offer')
                        await call.peer.setRemoteDescription(RTCSessionDescription(sdp['sdp'], 'offer'))
                        await call.peer.setLocalDescription(await call.peer.createAnswer())
                        await ws.send_json({'type':'answer','sdp':call.peer.localDescription.sdp,'iceServers':[]})
                        offered = True
                    elif kind == 'candidate' and offered:
                        value = data.get('candidate')
                        if value and value.get('candidate'):
                            candidate = candidate_from_sdp(value['candidate'].removeprefix('candidate:'))
                            candidate.sdpMid = value.get('sdpMid')
                            candidate.sdpMLineIndex = value.get('sdpMLineIndex')
                            await call.peer.addIceCandidate(candidate)
                    elif kind == 'disconnect':
                        break
                    else:
                        raise ValueError('Invalid signaling message')
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.warning('Signaling ended type=%s', type(error).__name__)
        finally:
            await call.close()
            active.discard(call)
            await ws.close()
        return ws

    async def health(request):
        return web.json_response({'status':'ok','nativeSessions':len(active),
                                  'authMode':'loopback-development' if config.development_token else config.auth_mode})
    app.router.add_get('/health', health)
    app.router.add_get('/webrtc/connect/agent_operator', connect)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--probe-backend', action='store_true',
                        help='One safe greeting before serving, retaining the owned bot cookie')
    args = parser.parse_args()
    raw = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    token_file = raw.pop('development_token_file', '')
    if 'development_token' in raw:
        raise ValueError('Inline development credentials are forbidden')
    if token_file:
        raw['development_token'] = Path(token_file).read_text().strip()
    config = Config(**raw)
    if not config.instance_name.replace('-', '').isalnum() or not config.voice_service_id:
        raise ValueError('Explicit instance and voice assistant allowlist required')
    for url in (config.backend_url, config.asr_url, config.tts_url):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1':
            raise ValueError('Speech and bot services must remain loopback-only')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
    # Access logs would expose the OAuth query parameter and must remain disabled.
    web.run_app(create_app(config, probe_backend=args.probe_backend), host='127.0.0.1', port=config.port, access_log=None)


if __name__ == '__main__':
    main()
