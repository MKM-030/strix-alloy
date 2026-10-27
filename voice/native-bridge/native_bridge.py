"""Native ServiceNow WebRTC transport, local speech, existing VA conversation.

No own LLM, order logic, HTML client, or replacement chat UI is included.
The HTTP listener remains loopback-only. A trusted TLS proxy and verified
ServiceNow OAuth authorization are required for a native browser deployment.
"""
import argparse
import asyncio
from dataclasses import dataclass, field, replace
from functools import partial
from fractions import Fraction
import io
import json
import logging
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid
import wave

from aiohttp import ClientSession, ClientTimeout, CookieJar, FormData, WSMsgType, web
from aiortc import AudioStreamTrack, RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame, AudioResampler
from core import EndpointGate, PlaybackBuffer, local_auth, authorized_agents
from sdk_deployment import SDKDeploymentPolicy, valid_call_duration
from spoken_output import spoken_text
from assistant_settings import CallSettings
from host_ice import HostIceConfiguration, load_host_ice_file
from managed_turn import ManagedTurnConfiguration, load_managed_turn_file, clear_session_ice
from mobile_relay import MobileRelayConfiguration, load_mobile_relay_file

LOG = logging.getLogger('native-voice')
HTTP_KEY = web.AppKey('http', ClientSession)
# Both peers need a public ICE candidate when they are outside the same LAN.
STUN_URL = 'stun:stun.l.google.com:19302'


@dataclass
class Config:
    instance_name: str = ''
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
    native_sdk_enabled: bool = False
    sdk_public_origin: str = ''
    private_host_ice: HostIceConfiguration = field(default_factory=HostIceConfiguration, repr=False)
    private_mobile_relay: MobileRelayConfiguration = field(default_factory=MobileRelayConfiguration, repr=False)
    private_managed_turn: ManagedTurnConfiguration = field(default_factory=ManagedTurnConfiguration, repr=False)
    sdk_policy: SDKDeploymentPolicy | None = field(init=False, default=None, repr=False)

    def __post_init__(self):
        if not isinstance(self.private_managed_turn,ManagedTurnConfiguration):
            raise ValueError('Managed TURN must be a resolved configuration')
        if self.private_managed_turn.enabled and (not self.native_sdk_enabled
                or self.auth_mode!='servicenow' or self.development_token):
            raise ValueError('Managed TURN requires authenticated native SDK deployment')
        if not isinstance(self.private_mobile_relay,MobileRelayConfiguration):
            raise ValueError('Private mobile relay must be a resolved configuration')
        if self.private_mobile_relay.enabled and (not self.native_sdk_enabled
                or self.auth_mode!='servicenow' or self.development_token):
            raise ValueError('Private mobile relay requires authenticated native SDK deployment')
        if self.private_managed_turn.enabled and self.private_mobile_relay.enabled:
            raise ValueError('Managed TURN and private mobile relay are mutually exclusive')
        if not isinstance(self.private_host_ice,HostIceConfiguration):
            raise ValueError('Private host ICE must be a resolved configuration')
        if type(self.native_sdk_enabled) is not bool:
            raise ValueError('native_sdk_enabled must be a boolean')
        if type(self.vad_silence_ms) is not int or not 200 <= self.vad_silence_ms <= 2000:
            raise ValueError('vad_silence_ms must be an integer between 200 and 2000')
        if not isinstance(self.sdk_public_origin,str):
            raise ValueError('sdk_public_origin must be a string')
        if self.auth_mode == 'servicenow' and (
                not isinstance(self.instance_name, str) or
                not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', self.instance_name)):
            raise ValueError('ServiceNow authentication requires an explicit canonical instance_name')
        if self.native_sdk_enabled or self.sdk_public_origin:
            self.sdk_policy = SDKDeploymentPolicy(self.instance_name,self.voice_service_id,
                                                  self.required_agent_id,self.sdk_public_origin)
            if (self.auth_mode != 'servicenow' or self.development_token
                    or not valid_call_duration(self.max_call_seconds)):
                raise ValueError('SDK policy requires ServiceNow OAuth and a bounded call duration')

    @property
    def instance_url(self):
        return 'https://' + self.instance_name + '.service-now.com' if self.instance_name else ''


class Speech:
    def __init__(self, http, config, call_settings=None):
        self.http, self.config = http, config
        self.call_settings = call_settings

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
        context = self.call_settings.asr_context() if self.call_settings else {'language':'de','terms':[]}
        form.add_field('language', context['language'])
        if context['terms']:
            form.add_field('prompt', ', '.join(context['terms']))
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
    def __init__(self, config, call_settings=None):
        self.config = config
        self.call_settings = call_settings
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
            if path == '/api/end' and response.status == 401:
                # Only the trusted loopback owner can declare its cookie expired.
                return {'ended':True,'expired':True}
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
        voice_context = self.call_settings.native_context() if self.call_settings else {}
        # Profile-bound Voice sends CREATE before user input, consuming the first request.
        self.greeting_history_allowed = (info.get('initialBotHistoryAllowed') is True
                                         and 'global_context_profile' not in voice_context)
        if not info.get('serviceNowEnabled'):
            raise RuntimeError('ServiceNow conversation is disabled')
        if not info.get('started'):
            await self.request('POST', '/api/start', json=(
                {'voice_context':voice_context} if voice_context else {}))
        # Startup is an enqueue ACK; wait for an actual creation/input-ready callback.
        # Legacy deferred-start deployments are immediately ready here.
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

    async def turn(self, text, on_reply=None, voice_context=None):
        payload = {'text':text}
        if self.call_settings:
            payload['voice_context'] = (dict(voice_context) if voice_context is not None
                                        else self.call_settings.native_context())
        if self.first_message_pending and self.greeting_history:
            payload['history'] = self.greeting_history
        # Consume before I/O: uncertain delivery must never replay the greeting.
        self.first_message_pending = False
        self.greeting_history = []
        request_started = time.monotonic()
        await self.request('POST', '/api/message', json=payload)
        LOG.info('Voice dialog stage=request_ack elapsed_ms=%d', int((time.monotonic()-request_started)*1000))
        first_reply = True
        until = time.monotonic() + 185
        result = []
        while time.monotonic() < until:
            state = await self.request('GET', '/api/events', params={'after':str(self.cursor),'wait':'20'})
            self.cursor = state['cursor']
            for event in state.get('events', []):
                if event.get('kind') == 'bot' and event.get('text'):
                    reply = spoken_text(event['text'])
                    LOG.info('Voice dialog stage=callback_content elapsed_ms=%d first=%s',
                             int((time.monotonic()-request_started)*1000), first_reply)
                    first_reply = False
                    result.append(reply)
                    if on_reply:
                        await on_reply(reply)
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

    async def wait_owned_cleanup(self):
        """Retry only the owned END, retaining its private cookie until ACK."""
        attempt, delay = 0, .25
        while self.must_reset:
            await asyncio.sleep(delay)
            attempt += 1
            try:
                await self.reset_owned_session()
            except asyncio.CancelledError:
                LOG.warning('Owned conversation cleanup unresolved stage=shutdown attempts=%d',attempt)
                raise
            except Exception as error:
                LOG.warning('Owned conversation cleanup pending attempt=%d type=%s',attempt,type(error).__name__)
                delay = min(delay*2,30)
        LOG.info('Owned conversation cleanup stage=acknowledged attempts=%d',attempt)

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
        self.first_pcm_drained = False

    async def recv(self):
        if self.start_time is None:
            self.start_time = time.monotonic()
        delay = self.start_time + self.samples / 24000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        frame = AudioFrame(format='s16', layout='mono', samples=480)
        pcm = self.playback.read(960)
        frame.planes[0].update(pcm)
        if not self.first_pcm_drained and any(pcm):
            self.first_pcm_drained = True
            LOG.info('Voice output call=%s stage=first_non_silent_pcm generation=%d '
                     'elapsed_ms=%d pcm_bytes=%d sample_offset=%d sample_rate=24000',
                     getattr(self.playback, 'call_id', ''), self.playback.generation,
                     int((time.monotonic()-self.start_time)*1000), len(pcm), self.samples)
        frame.sample_rate = 24000
        frame.pts = self.samples
        frame.time_base = Fraction(1, 24000)
        self.samples += 480
        return frame


class NativeCall:
    def __init__(self, config, speech, dialog, call_settings=None, *, ice_servers=None):
        self.call_settings = call_settings
        if call_settings:
            # Clone only call-local timing/limits; never mutate startup routing or local voices.
            changes = {'greeting':call_settings.introduction}
            if call_settings.vad_stop_ms is not None:
                changes['vad_silence_ms'] = call_settings.vad_stop_ms
            if call_settings.max_call_seconds is not None:
                changes['max_call_seconds'] = min(config.max_call_seconds,call_settings.max_call_seconds)
            config = replace(config, **changes)
        self.config, self.speech, self.dialog = config, speech, dialog
        host_ice = getattr(config,'private_host_ice',None)
        self._session_ice_servers = list(ice_servers) if ice_servers is not None else []
        if ice_servers is None:
            ice_servers = host_ice.servers() if host_ice is not None else [RTCIceServer(urls=[STUN_URL])]
        else:
            ice_servers = self._session_ice_servers
        self.peer = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))
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
        self.playback.call_id = self.call_id
        self.closed = False
        self.turn_number = 0
        self.turn_contexts = {}
        self.turn_controls = {}
        self.language_selection_pending = bool(getattr(call_settings,'selection_prompt',''))
        self.language_welcome_spoken = False
        self.synthesis_active = False
        self.recognition_active = False
        self.vad_active = False
        self.input_started = False
        self.microphones = set()
        self.input_loss_task = None
        self.input_lost = False
        self.input_ended = asyncio.Event()
        self.turns_settled = asyncio.Event()
        self.turns_settled.set()  # No conversation worker has started yet.
        self.closing = False
        self.close_task = None
        self.close_complete = asyncio.Event()
        self.peer.on('datachannel', self.datachannel)
        self.peer.on('track', self.receive_track)

    @property
    def session_parameters(self):
        """Detached server-only settings; never part of the mobile session DTO."""
        getter = getattr(self.call_settings, 'session_parameters', None)
        parameters = getter() if callable(getter) else {}
        parameters['effective_transport'] = {
            'max_call_seconds': self.config.max_call_seconds,
            'vad_silence_ms': self.config.vad_silence_ms,
            'vad_threshold': self.config.vad_threshold,
            'vad_onset_ms': getattr(self.call_settings, 'vad_start_ms', None) or 100,
        }
        return parameters

    def local_message(self, code, legacy_text=''):
        getter = getattr(self.call_settings, 'notice_text', None)
        return getter(code) if callable(getter) else legacy_text

    def local_notice(self, code, legacy_text, message_key=None):
        text = self.local_message(message_key or code, legacy_text)
        self.notice(code, text)
        return text

    def language_selection_active(self):
        selection = getattr(self.call_settings, 'language_selection', {})
        return (selection.get('enabled') is True and len(selection.get('languages', [])) > 1
                and selection.get('mode', '').strip().casefold() != 'dtmf')

    async def speak_language_control(self, text, generation, code):
        """Serialize local selection feedback with output; never submit a Bot turn."""
        if not text or self.input_lost or generation != self.playback.generation:
            return
        self.notice(code, text)
        self.synthesis_active = True
        try:
            # Speech owns its bounded HTTP timeout; the call owns its lifetime.
            # Healthy playback backpressure must not consume a ten-second prompt budget.
            async for chunk in self.speech.synthesize(text):
                if self.input_lost or generation != self.playback.generation:
                    return
                while len(self.playback.data) > 48000 and generation == self.playback.generation:
                    await asyncio.sleep(.02)
                self.playback.put(chunk, generation)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Local selection feedback may fail without failing or replaying a native turn.
            LOG.warning('Voice language control call=%s stage=tts_failed type=%s',
                        self.call_id, type(error).__name__)
        finally:
            self.synthesis_active = False

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def register_microphone(self, track):
        if self.closed or self.closing or self.input_lost:
            return False
        self.microphones.add(track)
        if self.input_loss_task and not self.input_loss_task.done():
            self.input_loss_task.cancel()
            self.input_loss_task = None
        return True

    def receive_track(self, track):
        # Register before spawning: a replacement must cancel the loss grace
        # even before its receive coroutine gets its first event-loop turn.
        if track.kind == 'audio' and track not in self.microphones and self.register_microphone(track):
            return self.spawn(self.microphone(track))

    @staticmethod
    def drain_queue(queue):
        count = 0
        while not queue.empty():
            queue.get_nowait()
            queue.task_done()
            count += 1
        return count

    async def finish_input_loss(self):
        # Track replacement can briefly leave no receiver. Silence and muted
        # audio never enter this path; only a failed receive worker does.
        await asyncio.sleep(.25)
        if self.closed or self.closing or self.microphones or self.input_lost:
            return
        self.input_lost = True  # Commit before yielding or accepting more input.
        # A lost speaker must not leave on_reply stuck on a full PCM buffer
        # while the submitted ServiceNow request is still being observed.
        self.playback.interrupt()
        try:
            self.local_notice('INPUT_LOST', 'Die Mikrofonverbindung wurde unterbrochen. Weitere Antworten werden nicht weitergeleitet. '
                        'Dieser Anruf wird beendet, sobald die laufende Anfrage abgeschlossen ist.')
        except Exception as error:
            LOG.warning('Voice input call=%s stage=notice_failed type=%s', self.call_id, type(error).__name__)
        if self.asr_task:
            self.asr_task.cancel()
            await asyncio.gather(self.asr_task, return_exceptions=True)
        audio_count = self.drain_queue(self.turns)
        text_count = self.drain_queue(self.recognized_turns)
        if not self.turns_settled.is_set():
            self.recognized_turns.put_nowait(None)  # Wake an idle worker only.
        LOG.info('Voice input call=%s stage=input_lost discarded_audio=%d discarded_text=%d',
                 self.call_id, audio_count, text_count)
        self.input_ended.set()

    def datachannel(self, channel):
        if channel.label != 'transcripts':
            channel.close()
            return
        self.channel = channel
        opened_logged = False
        def opened():
            nonlocal opened_logged
            if not opened_logged:
                opened_logged = True
                LOG.info('Voice transport call=%s stage=datachannel_open pending_events=%d',
                         self.call_id, len(self.pending_events))
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
        if code == 'INPUT_LOST' and len(self.pending_events) >= 30:
            # Retain the terminal notice even if an unopened channel has filled
            # its bounded backlog. Initial greeting history is held separately.
            self.pending_events.pop(0)
        self.emit('transcript', {'role':'assistant','content':text,'code':code,
            'message_id':uuid.uuid4().hex,'caller_turn_id':'','turn_num':0})

    async def microphone(self, track):
        if not self.register_microphone(track):
            return
        started = last_frame = last_report = time.monotonic()
        last_loud = None
        frames = samples = vad_starts = queued = energy = loud_frames = 0
        max_gap = 0.0
        pending = None
        gate = None
        receive_failed = False

        def queue_utterance(utterance, endpoint):
            nonlocal queued
            if not utterance or self.closed or self.failed or self.input_lost or self.closing:
                return
            try:
                self.turns.put_nowait((self.playback.generation, utterance))
                queued += 1
                LOG.info('Voice input call=%s stage=queued audio_ms=%d audio_queue=%d text_queue=%d endpoint=%s',
                         self.call_id, len(utterance)*1000//32000,
                         self.turns.qsize(), self.recognized_turns.qsize(), endpoint)
            except asyncio.QueueFull:
                LOG.info('Voice input call=%s stage=audio_queue_full', self.call_id)
                self.local_notice('BUSY', 'Die letzte Aufnahme konnte nicht angenommen werden. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.', 'BUSY_AUDIO')

        def summary(stage):
            # Numeric counters only: never log audio, transcripts, addresses,
            # tokens, or arbitrary transport/exception representations.
            now = time.monotonic()
            LOG.info('Voice input call=%s stage=input_summary reason=%s seconds=%.3f frames=%d audio_ms=%d vad_starts=%d queued=%d vad_active=%s voiced_ms=%d quiet_ms=%d last_frame_age_ms=%d last_loud_age_ms=%d max_gap_ms=%d rms=%d loud_frames=%d audio_queue=%d text_queue=%d',
                     self.call_id, stage, now-started, frames, samples*1000//16000,
                     vad_starts, queued, bool(gate and gate.active),
                     gate.voiced*1000//16000 if gate else 0,
                     gate.quiet*1000//16000 if gate else 0,
                     int((now-last_frame)*1000),
                     int((now-last_loud)*1000) if last_loud is not None else -1,
                     int(max(max_gap,now-last_frame)*1000),
                     int((energy/max(1,samples))**.5), loud_frames,
                     self.turns.qsize(), self.recognized_turns.qsize())

        try:
            converter = AudioResampler(format='s16', layout='mono', rate=16000)
            gate = EndpointGate(threshold=self.config.vad_threshold,
                                onset_ms=(self.call_settings.vad_start_ms if self.call_settings and
                                          self.call_settings.vad_start_ms is not None else 100),
                                silence_ms=self.config.vad_silence_ms)
            silence_seconds = self.config.vad_silence_ms / 1000
            while not self.closed:
                if pending is None:
                    # Keep one recv alive across timeouts. Repeated wait_for()
                    # cancellation can disrupt aiortc's receive queue itself.
                    pending = asyncio.create_task(track.recv())
                ready, _ = await asyncio.wait((pending,), timeout=min(.25,silence_seconds))
                now = time.monotonic()
                if ready:
                    frame = pending.result()  # Real EOS/errors keep loss handling.
                    pending = None
                    frames += 1
                    max_gap = max(max_gap, now-last_frame)
                    last_frame = now
                    if self.failed or self.input_lost or self.closing:
                        continue
                    for mono in converter.resample(frame):
                        pcm = mono.to_ndarray().tobytes()
                        values = memoryview(pcm).cast('h')
                        power = sum(value*value for value in values)
                        count = len(values)
                        energy += power
                        samples += count
                        loud = bool(count and power >= self.config.vad_threshold**2 * count)
                        loud_frames += int(loud)
                        began, utterance = gate.feed(pcm)
                        self.vad_active = gate.active
                        if gate.active and loud:
                            last_loud = now
                        if began:
                            vad_starts += 1
                            self.input_started = True
                            playback_bytes = len(self.playback.data)
                            interrupted = self.synthesis_active or bool(playback_bytes)
                            if interrupted:
                                self.playback.interrupt()
                            LOG.info('Voice input call=%s stage=vad_start generation=%d interrupted=%s playback_bytes=%d audio_queue=%d text_queue=%d',
                                     self.call_id, self.playback.generation, interrupted, playback_bytes,
                                     self.turns.qsize(), self.recognized_turns.qsize())
                        queue_utterance(utterance, 'pcm_silence_or_limit')
                        if not gate.active:
                            last_loud = None
                # Silence suppression can send no packets or sparse comfort
                # noise. Measure elapsed time since actual loud PCM, rather
                # than requiring a continuous stream of quiet PCM samples.
                if (not self.failed and not self.input_lost and not self.closing
                        and gate.active and last_loud is not None
                        and now-last_loud >= silence_seconds):
                    utterance = gate.finish()
                    self.vad_active = False
                    queue_utterance(utterance, 'wall_silence')
                    summary('wall_silence')
                    last_loud = None
                if now-last_report >= 10:
                    summary('periodic')
                    last_report = now
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not self.closed:
                receive_failed = True
                connection = self.peer.connectionState
                ice = self.peer.iceConnectionState
                connection = connection if connection in ('new', 'connecting', 'connected', 'disconnected', 'failed', 'closed') else 'unknown'
                ice = ice if ice in ('new', 'checking', 'connected', 'completed', 'disconnected', 'failed', 'closed') else 'unknown'
                LOG.warning('Voice input call=%s stage=track_failed type=%s seconds=%.3f frames=%d audio_ms=%d vad_starts=%d queued=%d connection_state=%s ice_state=%s',
                            self.call_id, type(error).__name__, time.monotonic()-started, frames,
                            samples*1000//16000, vad_starts, queued, connection, ice)
        finally:
            if pending is not None:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            summary('closed')
            self.microphones.discard(track)
            if receive_failed and not self.closed and not self.closing and not self.microphones and not self.input_lost:
                if not self.input_loss_task or self.input_loss_task.done():
                    self.input_loss_task = self.spawn(self.finish_input_loss())

    async def recognize_turns(self):
        """Recognize accepted audio independently; never submit backend requests."""
        while not self.closed and not self.failed and not self.input_lost and not self.closing:
            generation, pcm = await self.turns.get()
            started = time.monotonic()
            try:
                self.recognition_active = True
                text = await self.speech.transcribe(pcm)
                if self.closed or self.failed or self.input_lost or self.closing:
                    return
                LOG.info('Voice input call=%s stage=asr_complete audio_ms=%d seconds=%.3f empty=%s text_queue=%d',
                         self.call_id, len(pcm)*1000//32000, time.monotonic()-started,
                         not bool(text), self.recognized_turns.qsize())
                if not text:
                    self.local_notice('ASR_EMPTY', 'Ich konnte keine Sprache erkennen. Bitte wiederholen Sie Ihre Antwort.')
                    continue
                control = None
                selected = self.call_settings and self.call_settings.select_language(text)
                if selected:
                    LOG.info('Voice input call=%s stage=language_selected configured=True', self.call_id)
                    if self.language_selection_active():
                        control = ('selected', getattr(self.call_settings, 'selected_language_welcome', ''))
                elif self.language_selection_pending and self.language_selection_active():
                    prefix = (getattr(self.call_settings, 'configured_retry_prefix', '')
                              or self.local_message('LANGUAGE_RETRY'))
                    prompt = getattr(self.call_settings, 'selection_prompt', '')
                    control = ('retry', ' '.join(part for part in (prefix, prompt) if part))
                self.turn_number += 1
                turn = (generation, text, self.turn_number, uuid.uuid4().hex, started)
                self.transcript(turn, 'user', text)
                try:
                    self.recognized_turns.put_nowait(turn)
                    if self.call_settings:
                        self.turn_contexts[self.turn_number] = self.call_settings.native_context()
                    if control is not None:
                        self.turn_controls[self.turn_number] = control
                        if control[0] == 'selected':
                            self.language_selection_pending = False
                except asyncio.QueueFull:
                    LOG.info('Voice input call=%s stage=text_queue_full turn=%d', self.call_id, self.turn_number)
                    self.local_notice('BUSY', 'Ihre letzte Antwort wurde erkannt, aber nicht weitergeleitet. Bitte warten Sie auf den Abschluss der aktuellen Anfrage.', 'BUSY_TEXT')
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOG.warning('Voice input call=%s stage=asr_failed type=%s', self.call_id, type(error).__name__)
                self.local_notice('ASR_FAILED', 'Die Spracherkennung ist fehlgeschlagen. Bitte wiederholen Sie Ihre Antwort.')
            finally:
                self.recognition_active = False
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
        if self.input_lost:
            # The input-loss notice already explains closure. A lost speaker
            # must not be refilled by failure TTS while cleanup waits to settle.
            return
        notice = ('Der Sprachdialog konnte nicht fortgesetzt werden. Weitere Antworten werden nicht weitergeleitet. '
                  'Bitte beenden Sie diesen Anruf.')
        notice = self.local_notice('TURN_FAILED', notice)
        if not notice:
            return
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

    async def inactivity_goodbye(self):
        text = self.local_message('USER_INACTIVITY',
                                  getattr(self.call_settings,'configured_goodbye',''))
        if not text:
            return True
        generation = self.playback.generation
        self.synthesis_active = True
        try:
            self.notice('USER_INACTIVITY',text)
            async with asyncio.timeout(10):
                async for chunk in self.speech.synthesize(text):
                    if generation != self.playback.generation or self.input_lost:
                        return False
                    while len(self.playback.data) > 48000 and generation == self.playback.generation:
                        await asyncio.sleep(.02)
                    self.playback.put(chunk,generation)
                while self.playback.data and generation == self.playback.generation and not self.input_lost:
                    await asyncio.sleep(.02)
            return generation == self.playback.generation and self.recognized_turns.empty()
        except Exception as error:
            LOG.warning('Voice lifecycle call=%s stage=goodbye_failed type=%s',self.call_id,type(error).__name__)
            return True
        finally:
            self.synthesis_active = False

    async def wait_for_user_turn(self):
        """Idle expiry only between native turns and after local audio drains."""
        seconds = getattr(self.call_settings,'inactivity_seconds',None)
        if seconds is None:
            return await self.recognized_turns.get()
        idle_since = time.monotonic()
        while not self.closed and not self.input_lost and not self.closing:
            if (self.playback.data or self.synthesis_active or self.recognition_active
                    or self.vad_active or not self.turns.empty()):
                idle_since = time.monotonic()
            try:
                return await asyncio.wait_for(self.recognized_turns.get(), min(.1,seconds))
            except asyncio.TimeoutError:
                active = (self.playback.data or self.synthesis_active or self.recognition_active
                          or self.vad_active or not self.turns.empty())
                if not active and time.monotonic()-idle_since >= seconds:
                    if not await self.inactivity_goodbye():
                        idle_since = time.monotonic()
                        continue
                    LOG.info('Voice lifecycle call=%s stage=user_inactivity elapsed_ms=%d',
                             self.call_id,int((time.monotonic()-idle_since)*1000))
                    self.closing = True
                    self.input_ended.set()
                    # A sentinel uses the same queue accounting as input loss.
                    self.recognized_turns.put_nowait(None)
                    return self.recognized_turns.get_nowait()
        return await self.recognized_turns.get()

    async def process_turns(self):
        self.turns_settled.clear()
        self.asr_task = self.spawn(self.recognize_turns())
        try:
            dialog_started = time.monotonic()
            LOG.info('Voice greeting call=%s stage=dialog_open_begin input_started=%s generation=%d input_lost=%s',
                     self.call_id, self.input_started, self.playback.generation, self.input_lost)
            greetings = await self.dialog.open() or []
            LOG.info('Voice greeting call=%s stage=dialog_open_end elapsed_ms=%d greeting_count=%d input_started=%s generation=%d input_lost=%s',
                     self.call_id, int((time.monotonic()-dialog_started)*1000), len(greetings),
                     self.input_started, self.playback.generation, self.input_lost)
            fallback_greeting = False
            selection_prompt = getattr(self.call_settings,'selection_prompt','')
            if (selection_prompt and not greetings and self.playback.generation == 0
                    and not self.input_started and not self.input_lost):
                # This is the native configured phrase, only when multiple languages exist.
                greetings = [('' + self.config.greeting + ' ' if self.config.greeting else '') + selection_prompt]
                fallback_greeting = True
            if (not greetings and self.config.greeting and self.playback.generation == 0
                    and not self.input_started and not self.input_lost):
                greetings = [self.config.greeting]
                fallback_greeting = True
                LOG.info('Voice greeting call=%s stage=greeting_fallback generation=%d',
                         self.call_id, self.playback.generation)
            elif not greetings:
                reason = ('not_configured' if not self.config.greeting else
                          'input_lost' if self.input_lost else
                          'prior_generation' if self.playback.generation else 'prior_input')
                LOG.info('Voice greeting call=%s stage=greeting_skip reason=%s input_started=%s generation=%d input_lost=%s',
                         self.call_id, reason, self.input_started, self.playback.generation, self.input_lost)
            generation = self.playback.generation
            for greeting_index, greeting in enumerate(greetings):
                if self.input_lost:
                    LOG.info('Voice greeting call=%s stage=greeting_skip reason=input_lost greeting_index=%d generation=%d',
                             self.call_id, greeting_index, self.playback.generation)
                    break
                self.emit('transcript', {'role':'assistant','content':greeting,
                    'message_id':uuid.uuid4().hex,'caller_turn_id':'','turn_num':0})
                if fallback_greeting:
                    self.dialog.record_greeting(greeting)
                if generation or self.input_started:
                    LOG.info('Voice greeting call=%s stage=greeting_skip reason=%s greeting_index=%d input_started=%s generation=%d',
                             self.call_id, 'prior_generation' if generation else 'prior_input',
                             greeting_index, self.input_started, generation)
                    continue
                self.synthesis_active = True
                tts_started = time.monotonic()
                tts_bytes = accepted_bytes = chunks = 0
                outcome = 'complete'
                LOG.info('Voice greeting call=%s stage=greeting_tts_begin greeting_index=%d generation=%d',
                         self.call_id, greeting_index, generation)
                try:
                    async for chunk in self.speech.synthesize(greeting):
                        tts_bytes += len(chunk)
                        chunks += 1
                        if chunks == 1:
                            LOG.info('Voice greeting call=%s stage=greeting_tts_first_chunk greeting_index=%d elapsed_ms=%d bytes=%d generation=%d current_generation=%d',
                                     self.call_id, greeting_index, int((time.monotonic()-tts_started)*1000),
                                     len(chunk), generation, self.playback.generation)
                        if generation != self.playback.generation:
                            outcome = 'interrupted'
                            break
                        while len(self.playback.data) > 48000 and generation == self.playback.generation:
                            await asyncio.sleep(.02)
                        if self.playback.put(chunk, generation):
                            accepted_bytes += len(chunk)
                except asyncio.CancelledError:
                    outcome = 'cancelled'
                    raise
                except Exception:
                    outcome = 'error'
                    raise
                finally:
                    self.synthesis_active = False
                    if outcome == 'complete':
                        outcome = ('interrupted' if generation != self.playback.generation else
                                   'empty' if tts_bytes == 0 else 'complete')
                    LOG.info('Voice greeting call=%s stage=greeting_tts_end greeting_index=%d elapsed_ms=%d bytes=%d accepted_bytes=%d chunks=%d outcome=%s generation=%d current_generation=%d',
                             self.call_id, greeting_index, int((time.monotonic()-tts_started)*1000),
                             tts_bytes, accepted_bytes, chunks, outcome, generation, self.playback.generation)
            while not self.closed and not self.failed and not self.input_lost and not self.closing:
                turn = await self.wait_for_user_turn()
                # Loss can commit while this get() or ASR cancellation yields.
                # No queued, unsubmitted turn may cross that commitment.
                if turn is None or self.input_lost or self.closing:
                    self.recognized_turns.task_done()
                    break
                generation, text, number, _, started = turn
                voice_context = self.turn_contexts.pop(number,None)
                control = self.turn_controls.pop(number, None)
                if control is not None:
                    try:
                        if control[0] == 'selected':
                            if not self.language_welcome_spoken:
                                self.language_welcome_spoken = True
                                await self.speak_language_control(control[1], generation, 'LANGUAGE_SELECTED')
                        else:
                            await self.speak_language_control(control[1], generation, 'LANGUAGE_SELECTION_RETRY')
                    finally:
                        self.recognized_turns.task_done()
                    continue
                LOG.info('Voice backend call=%s stage=begin turn=%d text_queue=%d',
                         self.call_id, number, self.recognized_turns.qsize())
                def transcript(role, content):
                    self.transcript(turn, role, content)
                speech_error = None
                backend_started = time.monotonic()
                async def deliver(reply):
                    nonlocal speech_error
                    if self.input_lost:
                        # Output transport may already be gone. Continue
                        # observing the submitted turn without another send.
                        return
                    LOG.info('Voice output call=%s stage=callback_content turn=%d backend_elapsed_ms=%d',
                             self.call_id, number, int((time.monotonic()-backend_started)*1000))
                    transcript('assistant', reply)
                    if generation != self.playback.generation or speech_error:
                        LOG.info('Voice output call=%s stage=tts_skipped turn=%d generation=%d current_generation=%d speech_error=%s',
                                 self.call_id, number, generation, self.playback.generation,
                                 bool(speech_error))
                        return
                    self.synthesis_active = True
                    tts_started = time.monotonic()
                    tts_chunks = tts_bytes = 0
                    LOG.info('Voice output call=%s stage=content_tts_begin turn=%d backend_elapsed_ms=%d',
                             self.call_id, number, int((tts_started-backend_started)*1000))
                    try:
                        async for chunk in self.speech.synthesize(reply):
                            tts_chunks += 1
                            tts_bytes += len(chunk)
                            if tts_chunks == 1:
                                LOG.info('Voice output call=%s stage=content_tts_first_chunk turn=%d elapsed_ms=%d backend_elapsed_ms=%d bytes=%d',
                                         self.call_id, number, int((time.monotonic()-tts_started)*1000),
                                         int((time.monotonic()-backend_started)*1000), len(chunk))
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
                        LOG.info('Voice output call=%s stage=content_tts_end turn=%d elapsed_ms=%d chunks=%d bytes=%d',
                                 self.call_id, number, int((time.monotonic()-tts_started)*1000), tts_chunks, tts_bytes)
                try:
                    if voice_context is not None and isinstance(self.dialog,Dialog):
                        await self.dialog.turn(text, on_reply=deliver, voice_context=voice_context)
                    else:
                        await self.dialog.turn(text, on_reply=deliver)
                finally:
                    self.recognized_turns.task_done()
                if speech_error:
                    raise RuntimeError('Speech output failed after ServiceNow turn settled')
                LOG.info('Voice turn completed call=%s stage=complete turn=%d seconds=%.2f',
                         self.call_id, number, time.monotonic()-started)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Deliberately log type only: network exceptions can contain tokens.
            LOG.warning('Voice turn failed call=%s type=%s', self.call_id, type(error).__name__)
            await self.report_backend_failure()
        finally:
            # Includes failures and cancellation, after submitted-turn observation.
            self.turns_settled.set()

    async def close(self):
        if self.close_task is None:
            self.closing = True
            # Outside self.tasks: cleanup must never cancel/gather itself.
            self.close_task = asyncio.create_task(self.finish_close())
        await asyncio.shield(self.close_task)

    async def finish_close(self):
        cleanup_acknowledged = not getattr(self.dialog,'_call_owned',False)
        try:
            if self.input_lost:
                # Even an independent client disconnect must preserve the
                # submitted turn after terminal input loss has committed.
                await self.turns_settled.wait()
            self.closed = True
            self.playback.interrupt()
            tasks = tuple(self.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.drain_queue(self.turns)
            self.drain_queue(self.recognized_turns)
            self.turn_contexts.clear()
            self.turn_controls.clear()
            try:
                await self.peer.close()
                clear_session_ice(self._session_ice_servers,self.peer)
            finally:
                await self.dialog.close()
                if getattr(self.dialog,'_call_owned',False):
                    if self.dialog.must_reset:
                        await self.dialog.wait_owned_cleanup()
                    await self.dialog.shutdown()
                cleanup_acknowledged = True
        finally:
            if cleanup_acknowledged:
                self.close_complete.set()
            else:
                LOG.warning('Voice cleanup call=%s stage=unresolved capacity_reserved=True',self.call_id)


async def authorize(request, config, http, with_settings=False):
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
        async with http.post(url, json={'serviceId':config.voice_service_id,'clientApp':'admin_test',
                                   **({'assistantSettingsVersion':1} if with_settings else {})},
                             headers={'Authorization':'Bearer '+token,'Accept':'application/json',
                                      **({'Accept-Encoding':'identity'} if with_settings else {})},
                             **({'auto_decompress':False} if with_settings else {}),
                             allow_redirects=False, timeout=ClientTimeout(total=10)) as response:
            if response.status != 200:
                LOG.warning('Native OAuth verification denied status=%s', response.status)
                return False
            if with_settings:
                from sdk_admission import _bounded_response
                data = await _bounded_response(response)
                return CallSettings.from_authorized_response(data,config.voice_service_id,config.required_agent_id)
            data = await response.json()
            accepted = authorized_agents(data, config.required_agent_id)
            if not accepted:
                result = data.get('result') if isinstance(data, dict) else None
                LOG.warning('Native OAuth verification envelope/agent denied result_type=%s', type(result).__name__)
            return accepted
    except Exception:
        return False


def create_app(config, speech_factory=None, dialog_factory=None, probe_backend=False):
    from assistant_settings import CallSettings
    @web.middleware
    async def request_diagnostics(request, handler):
        # Full access logs would expose OAuth query tokens. Keep request
        # diagnostics to fixed classes, a random identifier and status only.
        if request.path == '/health':
            return await handler(request)
        signaling_path = '/webrtc/connect/agent_operator'
        if request.path == '/api/webrtc/sessions' or request.path.startswith('/api/webrtc/sessions/'):
            route = 'native_sdk'
        elif request.path == signaling_path:
            route = 'signaling'
        elif request.path == '/scc-native' + signaling_path:
            route = 'prefixed_signaling'
        elif request.path.count(signaling_path) > 1:
            route = 'duplicated_signaling'
        else:
            route = 'other'
        method = request.method if request.method in {'GET', 'HEAD', 'POST', 'OPTIONS', 'DELETE'} else 'OTHER'
        origin_value = request.headers.get('Origin')
        origin = 'missing' if origin_value is None else ('expected' if origin_value == config.instance_url else 'other')
        query_credential = 'auth_token' in request.query
        header_credential = 'Authorization' in request.headers
        credentials = ('both' if query_credential and header_credential else
                       'query' if query_credential else 'header' if header_credential else 'none')
        upgrade_value = request.headers.get('Upgrade')
        upgrade = 'missing' if upgrade_value is None else ('websocket' if upgrade_value.lower() == 'websocket' else 'other')
        request_id = uuid.uuid4().hex[:12]
        LOG.info('Native HTTP request request=%s route=%s method=%s origin=%s credentials=%s upgrade=%s',
                 request_id, route, method, origin, credentials, upgrade)
        status = 0
        try:
            response = await handler(request)
            value = getattr(response, 'status', 0)
            status = value if type(value) is int and 100 <= value <= 599 else 0
            return response
        except web.HTTPException as error:
            status = error.status
            raise
        except Exception:
            status = 500
            raise
        finally:
            LOG.info('Native HTTP result request=%s status=%d', request_id, status)

    app = web.Application(client_max_size=256*1024, middlewares=[request_diagnostics])
    active = set()
    probe_dialog = Dialog(config) if dialog_factory is None and probe_backend else None
    async def lifecycle(app):
        app[HTTP_KEY] = ClientSession(trust_env=False, timeout=ClientTimeout(total=180))
        if probe_backend and probe_dialog:
            report = {'kind':'safe-greeting-no-order', 'native_ui_test':False}
            started = time.monotonic()
            try:
                await probe_dialog.open()
                report['ready_seconds'] = round(time.monotonic()-started, 3)
                replies = await probe_dialog.turn('Guten Tag. Bitte noch keine Bestellung auslösen.')
                report['response_seconds'] = round(time.monotonic()-started, 3)
                report['responses'] = replies
                report['ok'] = True
            except Exception as error:
                report['ok'] = False
                report['error_type'] = type(error).__name__
                report['elapsed_seconds'] = round(time.monotonic()-started, 3)
            finally:
                await probe_dialog.close()
                if probe_dialog.must_reset:
                    await probe_dialog.wait_owned_cleanup()
                report['reset_ok'] = not probe_dialog.must_reset
            target = Path(__file__).parent / 'runtime' / 'backend-probe.json'
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            LOG.info('Safe backend probe ok=%s elapsed=%.2f', report['ok'], time.monotonic()-started)
        yield
        closing = {asyncio.create_task(call.close()) for call in list(active)}
        if closing:
            done, pending = await asyncio.wait(closing,timeout=5)
            await asyncio.gather(*done,return_exceptions=True)
            if pending:
                LOG.warning('Native shutdown stage=unresolved_owned_cleanup count=%d',len(pending))
        # Unresolved owners keep their cookies/reservations until process exit.
        if probe_dialog:
            await probe_dialog.shutdown()
        await app[HTTP_KEY].close()
    app.cleanup_ctx.append(lifecycle)

    def make_call(settings=None, *, ice_servers=None):
        speech = speech_factory(app[HTTP_KEY]) if speech_factory else Speech(app[HTTP_KEY],config,settings)
        dialog = dialog_factory() if dialog_factory else Dialog(config,settings)
        if dialog_factory is None:
            dialog._call_owned = True
        if ice_servers is not None:
            return NativeCall(config,speech,dialog,call_settings=settings,ice_servers=ice_servers)
        return NativeCall(config,speech,dialog,call_settings=settings)

    async def connect(request):
        admission = await authorize(request, config, app[HTTP_KEY], with_settings=True)
        if not admission:
            LOG.info('Native signaling admission status=401')
            raise web.HTTPUnauthorized(text='Voice authorization rejected')
        if isinstance(admission,CallSettings) and admission.unsupported_language_selection:
            raise web.HTTPNotImplemented(text='Configured language selection input is unsupported by this transport')
        if active:
            LOG.info('Native signaling admission status=503 native_sessions=%d', len(active))
            raise web.HTTPServiceUnavailable(text='Demo voice session is busy')
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=256*1024)
        settings = admission if isinstance(admission,CallSettings) else None
        call = make_call(settings)
        # Reserve without yielding after checking capacity, including WS upgrade.
        active.add(call)
        offered = False
        input_coordinator = None
        async def close_after_input_loss():
            await call.input_ended.wait()
            await call.turns_settled.wait()
            if not call.closed:
                await ws.close()
        try:
            await ws.prepare(request)
            LOG.info('Native signaling admission status=101 call=%s', call.call_id)
            call.spawn(call.process_turns())
            # Kept outside call.tasks. Only the handler owns call.close().
            input_coordinator = asyncio.create_task(close_after_input_loss())
            async with asyncio.timeout(call.config.max_call_seconds):
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
                        await ws.send_json({'type':'answer','sdp':call.peer.localDescription.sdp,'iceServers':[{'urls':[STUN_URL]}]})
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
            try:
                if input_coordinator:
                    input_coordinator.cancel()
                    await asyncio.gather(input_coordinator, return_exceptions=True)
            finally:
                # Start owned cleanup even if another cancellation interrupts
                # the coordinator await above.
                try:
                    await call.close()
                finally:
                    if call.close_complete.is_set():
                        active.discard(call)
                    elif call.close_task is not None:
                        # A second handler cancellation may detach its shielded
                        # close await. Capacity still belongs to owned cleanup.
                        call.close_task.add_done_callback(lambda task: active.discard(call) if call.close_complete.is_set() else None)
                    await ws.close()
        return ws

    async def launch(request):
        import re
        # Only validated operator startup bindings can choose the launch target.
        headers = {'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'}
        if (not isinstance(config.instance_name,str)
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',config.instance_name)
                or not isinstance(config.voice_service_id,str)
                or not re.fullmatch(r'[0-9a-f]{32}',config.voice_service_id)):
            raise web.HTTPNotFound(headers=headers)
        if request.query_string:
            raise web.HTTPBadRequest(text='Launch does not accept query parameters', headers=headers)
        raise web.HTTPFound(
            location=(config.instance_url + '/now/now-assist-with-va/voice-test/'
                      + config.voice_service_id),
            headers=headers)

    async def health(request):
        result = {'status':'ok','nativeSessions':len(active),
                  'authMode':'loopback-development' if config.development_token else config.auth_mode}
        if request.query.get('assistant_settings') == '1':
            result['assistantSettingsSupport'] = {'version':1,'perCallLanguage':True,
                    'nativeCloudVoiceSelection':False,'nativeVadConfidenceAndVolume':False,
                    'nativeDtmfLanguageMapping':False,'nativeFillerMessageDelay':False,
                    'assistantDescriptionConsumptionVerified':False}
        if getattr(config, 'native_sdk_enabled', False):
            result['nativeSdkEnabled'] = True
        return web.json_response(result)
    app.router.add_get('/launch', launch)
    app.router.add_get('/health', health)
    app.router.add_get('/webrtc/connect/agent_operator', connect)
    if getattr(config, 'native_sdk_enabled', False):
        from sdk_admission import admit_sdk_session
        from sdk_sessions import register_sdk_routes
        def make_sdk_call(context, *, ice_servers=None):
            if not isinstance(context.call_settings,CallSettings):
                raise ValueError('Trusted assistant settings required')
            return make_call(context.call_settings,ice_servers=ice_servers)
        # One immutable startup policy binds admission and all session operations.
        register_sdk_routes(app, config, active, lambda: make_call(),
                            partial(admit_sdk_session,policy=config.sdk_policy,assistant_settings_version=1),
                            context_call_factory=make_sdk_call)
        LOG.info('Native SDK HTTP session routes enabled; shared browser capacity')
    return app


def load_config(filename):
    """Resolve private host ICE once; per-call dataclass replacement keeps the snapshot."""
    config_path = Path(filename)
    raw = json.loads(config_path.read_text(encoding='utf-8-sig'))
    if not isinstance(raw,dict):
        raise ValueError('Bridge configuration must be an object')
    if 'private_managed_turn' in raw:
        raise ValueError('Inline managed TURN configuration is forbidden')
    managed_turn_file = raw.pop('managed_turn_config_file','')
    if not isinstance(managed_turn_file,str):
        raise ValueError('Managed TURN configuration path must be a string')
    if managed_turn_file:
        private_path = Path(managed_turn_file)
        if not private_path.is_absolute():
            private_path = config_path.parent / private_path
        raw['private_managed_turn'] = load_managed_turn_file(private_path)
    if 'private_mobile_relay' in raw:
        raise ValueError('Inline private mobile relay configuration is forbidden')
    mobile_relay_file = raw.pop('mobile_relay_config_file','')
    if not isinstance(mobile_relay_file,str):
        raise ValueError('Private mobile relay configuration path must be a string')
    if mobile_relay_file:
        private_path = Path(mobile_relay_file)
        if not private_path.is_absolute():
            private_path = config_path.parent / private_path
        raw['private_mobile_relay'] = load_mobile_relay_file(private_path)
        if Path(raw['private_mobile_relay'].registry_file).resolve()==config_path.resolve():
            raise ValueError('Private mobile relay registry must not overwrite bridge configuration')
    if 'private_host_ice' in raw:
        raise ValueError('Inline private host ICE configuration is forbidden')
    host_ice_file = raw.pop('host_ice_config_file','')
    if not isinstance(host_ice_file,str):
        raise ValueError('Private host ICE configuration path must be a string')
    if host_ice_file:
        private_path = Path(host_ice_file)
        if not private_path.is_absolute():
            private_path = config_path.parent / private_path
        raw['private_host_ice'] = load_host_ice_file(private_path)
    token_file = raw.pop('development_token_file','')
    if 'development_token' in raw:
        raise ValueError('Inline development credentials are forbidden')
    if token_file:
        raw['development_token'] = Path(token_file).read_text().strip()
    return Config(**raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--probe-backend', action='store_true',
                        help='One safe greeting before serving, retaining the owned bot cookie')
    args = parser.parse_args()
    config = load_config(args.config)
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
