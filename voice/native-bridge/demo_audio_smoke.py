"""Explicitly gated synthetic-microphone acceptance probe; no native UI claim.

Uses the production adapter, real local STT/TTS, and the real ServiceNow bot.
Run only after the coordinator confirms model readiness and an idle backend.
No text is injected into the bot: every user turn crosses an RTP microphone
track and the configured speech recognizer. A changed order summary stops the
probe before confirmation. No inference is performed merely by importing it.
"""
import argparse
import asyncio
from array import array
from dataclasses import replace
from fractions import Fraction
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import re
import secrets
import time
import unicodedata
import wave
import uuid

import numpy as np
from aiohttp import ClientSession, WSMsgType, web
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame, AudioResampler
import native_bridge as production

EXPECTED_SUMMARY = ('Laptop für Alex Sommer zum 1. November 2026 nach Hamburg, '
                    'Vorgesetzter Marcel KAEFKE. Soll ich das bestellen?')


def normalized(text):
    return ' '.join(re.sub(r'[^\w\s]', ' ', unicodedata.normalize('NFKC', text).casefold()).split())


def expected_summary(text):
    # This harness is authorized for one already accepted demo order only.
    # Semantic guesses or summaries with changed fields require human review.
    return normalized(text) == normalized(EXPECTED_SUMMARY)


def name_question(text):
    lowered = normalized(text)
    return ('mitarbeiter' in lowered and
            ('wie heißt' in lowered or 'wie heisst' in lowered or 'name' in lowered))


def review_approved(data, summary_sha256, review_id):
    return (isinstance(data, dict) and data.get('approve') is True
            and data.get('summary_sha256') == summary_sha256 and data.get('review_id') == review_id)


def fatal_probe_event(message):
    """Production uses assistant transcripts for these recoverable UI errors."""
    if message.get('type') == 'error':
        return True
    data = message.get('data')
    return (message.get('type') == 'transcript' and isinstance(data, dict)
            and data.get('role') == 'assistant' and isinstance(data.get('code'), str)
            and data['code'] in {'TURN_FAILED', 'BUSY', 'ASR_FAILED', 'ASR_EMPTY'})


async def review_summary(summary, choices, trace, signaling_closed):
    digest = hashlib.sha256(summary.encode('utf-8')).hexdigest()
    review_id = uuid.uuid4().hex
    approval = trace.target.parent / ('summary-approval-'+review_id+'.json')
    trace.add('summary_review_required', actual_summary=summary, active_choices=choices,
              summary_sha256=digest, review_id=review_id, approval_file=str(approval), timeout_seconds=180)
    deadline = time.monotonic()+180
    while time.monotonic() < deadline:
        await asyncio.sleep(.25)
        if signaling_closed.is_set():
            raise RuntimeError('Signaling ended during operator review; confirmation withheld')
        if approval.exists():
            try:
                decision = json.loads(approval.read_text(encoding='utf-8-sig'))
            except (ValueError, OSError):
                raise RuntimeError('Invalid review file; confirmation withheld')
            if not review_approved(decision, digest, review_id):
                raise RuntimeError('Operator review denied or summary hash mismatched; confirmation withheld')
            trace.add('actual_summary_review_approved', summary_sha256=digest, review_id=review_id)
            return
    raise RuntimeError('Operator review timed out; confirmation withheld')


async def name_then_optional_confirmation(speak_fixture, dialog, trace, signaling_closed,
                                          *, name_fixture, stop_after_name):
    """The non-order mode exits before review or confirmation can be reached."""
    await speak_fixture(str(name_fixture))
    summary = dialog.state.get('inputLabel', '')
    if stop_after_name:
        state = dialog.state
        if (state.get('busy') is not False or state.get('ended') or state.get('failed')
                or not (summary or state.get('choices'))):
            raise RuntimeError('Name turn has no verified next-input readiness; confirmation withheld')
        trace.add('stopped_after_name_before_confirmation', input_label=summary,
                  replies=dialog.latest_replies, choices=state.get('choices', []),
                  confirmation_not_sent=True, operator_review_not_requested=True)
        return False
    if not expected_summary(summary):
        await review_summary(summary, dialog.state.get('choices', []), trace, signaling_closed)
    trace.add('explicit_confirmation_authorized_for_exact_summary', summary=summary)
    await speak_fixture('03-confirm.wav')
    return True


async def drain_signaling(ws, peer, closed):
    """Unlike a browser, aiohttp must read to process heartbeat Ping/Pong."""
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                break
            data = json.loads(message.data)
            if data.get('type') == 'candidate' and peer:
                value = data.get('candidate') or {}
                if value.get('candidate'):
                    candidate = candidate_from_sdp(value['candidate'].removeprefix('candidate:'))
                    candidate.sdpMid = value.get('sdpMid')
                    candidate.sdpMLineIndex = value.get('sdpMLineIndex')
                    await peer.addIceCandidate(candidate)
    finally:
        closed.set()


class Microphone(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.buffer = bytearray()
        self.samples = 0
        self.started = None
        self.finished_at = 0.0

    def load(self, path):
        if self.buffer:
            raise RuntimeError('Previous microphone fixture is still playing')
        with wave.open(str(path), 'rb') as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ValueError('Fixture must be mono PCM16 WAV')
            rate = wav.getframerate()
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
        upsampled = np.interp(np.arange(0, len(pcm), rate/48000), np.arange(len(pcm)), pcm)
        self.buffer.extend(upsampled.astype('<i2').tobytes())
        self.finished_at = 0

    async def recv(self):
        if self.started is None:
            self.started = time.monotonic()
        delay = self.started + self.samples/48000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        count = min(1920, len(self.buffer))
        raw = bytes(self.buffer[:count]).ljust(1920, b'\0')
        del self.buffer[:count]
        if count and not self.buffer:
            self.finished_at = time.monotonic()
        frame = AudioFrame(format='s16', layout='mono', samples=960)
        frame.planes[0].update(raw)
        frame.sample_rate, frame.pts, frame.time_base = 48000, self.samples, Fraction(1, 48000)
        self.samples += 960
        return frame


class Trace:
    def __init__(self, target):
        self.target = target
        self.started = time.monotonic()
        self.events = []

    def add(self, kind, **data):
        event = {'utc':datetime.now(timezone.utc).isoformat(),
                 'seconds':round(time.monotonic()-self.started, 3),'kind':kind,**data}
        self.events.append(event)
        print(json.dumps(event, ensure_ascii=True), flush=True)
        self.save()

    def save(self):
        self.target.write_text(json.dumps({'native_ui_test':False,'real_servicenow':True,
            'user_input':'synthetic microphone RTP through real ASR','events':self.events},
            ensure_ascii=False, indent=2), encoding='utf-8')


class ObservedDialog(production.Dialog):
    def __init__(self, config, trace):
        super().__init__(config)
        self.trace = trace
        self.in_turn = False
        self.state = {}
        self.latest_replies = []
        self.turn_count = 0
        self.seen_events = set()

    async def request(self, method, path, **kwargs):
        result = await super().request(method, path, **kwargs)
        if path == '/api/events':
            self.state = result
            for event in result.get('events', []):
                key = (self.turn_count, event.get('id'))
                if key not in self.seen_events:
                    self.seen_events.add(key)
                    self.trace.add('servicenow_event', turn=self.turn_count, event=event)
        elif path == '/api/message':
            payload = kwargs.get('json', {})
            self.trace.add('servicenow_ack', turn=self.turn_count,
                           input_kind='choice' if 'choice' in payload else 'typed_asr',
                           text=payload.get('text',''))
        return result

    async def turn(self, text, on_reply=None):
        self.in_turn = True
        self.turn_count += 1
        self.trace.add('bot_turn_begin', turn=self.turn_count, text=text)
        try:
            replies = await super().turn(text, on_reply=on_reply)
            self.latest_replies = replies
            self.trace.add('bot_turn_ready', turn=self.turn_count, replies=replies,
                           ended=self.state.get('ended'), choices=self.state.get('choices', []),
                           input_label=self.state.get('inputLabel',''))
            return replies
        finally:
            self.in_turn = False


class ObservedSpeech(production.Speech):
    def __init__(self, http, config, trace):
        super().__init__(http, config)
        self.trace = trace
        self.asr_busy = self.tts_busy = False

    async def transcribe(self, pcm):
        self.asr_busy = True
        self.trace.add('asr_begin', input_audio_seconds=round(len(pcm)/32000,3))
        try:
            text = await super().transcribe(pcm)
            self.trace.add('asr_complete', text=text)
            return text
        finally:
            self.asr_busy = False

    async def synthesize(self, text):
        self.tts_busy = True
        self.trace.add('tts_begin', text=text)
        received = 0
        try:
            async for chunk in super().synthesize(text):
                if not received:
                    self.trace.add('tts_first_pcm', text=text)
                received += len(chunk)
                yield chunk
        finally:
            self.trace.add('tts_complete', pcm_bytes=received, text=text)
            self.tts_busy = False


async def single_call(config, fixtures, trace, output, order, isolation=True, hello_fixture=None,
                      *, stop_after_name=False, name_fixture=None):
    """A private ephemeral local WS listener; never connected to Funnel."""
    if stop_after_name and (order or name_fixture is None):
        raise ValueError('Stop-after-name requires an explicit fixture and non-order mode')
    app_calls = []
    original_call = production.NativeCall
    class ObservedCall(original_call):
        def __init__(self, *args):
            super().__init__(*args)
            app_calls.append(self)
    production.NativeCall = ObservedCall
    local = replace(config)
    local.development_token = secrets.token_urlsafe(40)
    dialog = ObservedDialog(local, trace)
    speech = None
    def speech_factory(http):
        nonlocal speech
        speech = ObservedSpeech(http, local, trace)
        return speech
    app = production.create_app(local, speech_factory=speech_factory, dialog_factory=lambda:dialog)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    microphone = Microphone()
    peer.addTrack(microphone)
    channel = peer.createDataChannel('transcripts')
    messages = []
    received_pcm = bytearray()
    last_audible = 0.0
    connected = asyncio.Event()
    signaling_closed = asyncio.Event()
    signaling_reader = None
    channel.on('open', connected.set)
    def on_message(raw):
        data = json.loads(raw)
        messages.append(data)
        trace.add('native_datachannel', message=data)
    channel.on('message', on_message)
    async def receive(track):
        nonlocal last_audible
        converter = AudioResampler(format='s16', layout='mono', rate=16000)
        try:
            while True:
                frame = await track.recv()
                for mono in converter.resample(frame):
                    raw = mono.to_ndarray().tobytes()
                    received_pcm.extend(raw)
                    samples = array('h', raw)
                    loud = max(map(abs, samples), default=0) > 500
                    if loud:
                        now = time.monotonic()
                        if now-last_audible > 1:
                            trace.add('received_audible_audio')
                        last_audible = now
        except Exception:
            pass
    peer.on('track', lambda track: asyncio.create_task(receive(track)))

    async def speak_fixture(name, timeout_seconds=330):
        trace.add('microphone_fixture', file=name)
        old_turns = dialog.turn_count
        microphone.load(fixtures/name)
        deadline = time.monotonic()+timeout_seconds
        idle_since = None
        while time.monotonic() < deadline:
            await asyncio.sleep(.1)
            if signaling_closed.is_set():
                raise RuntimeError('Test signaling connection ended; no automatic retry')
            errors = [x for x in messages if fatal_probe_event(x)]
            if errors:
                raise RuntimeError('Native adapter reported an error; no automatic retry')
            call = app_calls[0]
            idle = (microphone.finished_at and time.monotonic()-microphone.finished_at > 1.3
                    and dialog.turn_count > old_turns and not dialog.in_turn and speech
                    and not speech.asr_busy and not speech.tts_busy
                    and call.turns.empty() and not call.playback.data)
            if idle:
                idle_since = idle_since or time.monotonic()
                if time.monotonic()-idle_since > 1:
                    return
            else:
                idle_since = None
        trace.add('turn_readiness_timeout', timeout_seconds=timeout_seconds,
                  busy=dialog.state.get('busy'), ended=dialog.state.get('ended'),
                  input_label=dialog.state.get('inputLabel'), replies=dialog.latest_replies)
        raise RuntimeError('Audio turn did not finish within its bounded deadline; no retry')

    try:
        async with ClientSession() as http:
            async with http.ws_connect(f'http://127.0.0.1:{port}/webrtc/connect/agent_operator',
                    params={'instance_name':local.instance_name,'voice_service_id':local.voice_service_id,
                            'auth_token':local.development_token}) as ws:
                offer = await peer.createOffer()
                await ws.send_json({'type':'offer','sdp':{'type':'offer','sdp':offer.sdp}})
                answer = await ws.receive_json(timeout=15)
                await peer.setLocalDescription(offer)
                await peer.setRemoteDescription(RTCSessionDescription(answer['sdp'],'answer'))
                mid, index = None, -1
                for line in peer.localDescription.sdp.splitlines():
                    if line.startswith('m='):
                        index += 1
                    elif line.startswith('a=mid:'):
                        mid = line[6:]
                    elif line.startswith('a=candidate:'):
                        await ws.send_json({'type':'candidate','candidate':{
                            'candidate':line[2:],'sdpMid':mid,'sdpMLineIndex':index}})
                signaling_reader = asyncio.create_task(drain_signaling(ws, peer, signaling_closed))
                await asyncio.wait_for(connected.wait(),15)
                if hello_fixture:
                    deadline = time.monotonic()+15
                    while time.monotonic() < deadline:
                        greeting = any(x.get('type') == 'transcript' and
                            x.get('data', {}).get('role') == 'assistant' and
                            x.get('data', {}).get('turn_num') == 0 for x in messages)
                        if greeting and speech and not speech.tts_busy and not app_calls[0].playback.data:
                            break
                        await asyncio.sleep(.1)
                    else:
                        raise RuntimeError('Actual fallback greeting was not received before hello probe')
                    trace.add('startup_greeting_received_before_user_hello')
                    await speak_fixture(str(hello_fixture.resolve()), timeout_seconds=60)
                    trace.add('hello_turn_ready', replies=dialog.latest_replies,
                              input_label=dialog.state.get('inputLabel'), choices=dialog.state.get('choices'))
                await speak_fixture('01-intent.wav')
                prompt = dialog.state.get('inputLabel','') or ' '.join(dialog.latest_replies)
                if not name_question(prompt):
                    raise RuntimeError('Unexpected first question; review transcript before any more input')
                if not order and not stop_after_name:
                    trace.add('second_conversation_isolated' if isolation else 'first_turn_verified',
                              fresh_name_question=prompt)
                    return
                confirmed = await name_then_optional_confirmation(
                    speak_fixture, dialog, trace, signaling_closed,
                    name_fixture=name_fixture if stop_after_name else '05-name-alex.wav',
                    stop_after_name=stop_after_name)
                if not confirmed:
                    return
                final = ' '.join(dialog.latest_replies)
                if 'REQ0010012' not in final or 'RITM0010011' not in final:
                    trace.add('result_requires_review', actual_result=final)
                    raise RuntimeError('Expected existing REQ/RITM not returned; do not retry or auto-select a choice')
                if not last_audible:
                    raise RuntimeError('No audible RTP was received')
                trace.add('expected_request_reported_and_audio_received', result=final)
    finally:
        if signaling_reader:
            signaling_reader.cancel()
            await asyncio.gather(signaling_reader, return_exceptions=True)
        await peer.close()
        await runner.cleanup()
        await dialog.shutdown()
        production.NativeCall = original_call
        with wave.open(str(output),'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(received_pcm)
        trace.add('call_closed', received_audio_seconds=round(len(received_pcm)/32000,3),
                  bot_release_ok=not dialog.must_reset, received_audio_file=str(output))


async def run(args):
    name_fixture = None
    if args.stop_after_name:
        name_fixture = Path(args.name_fixture).resolve(strict=True)
        with wave.open(str(name_fixture), 'rb') as wav:
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                    or wav.getframerate() != 16000 or not wav.getnframes()):
                raise ValueError('Name fixture must be nonempty mono PCM16 WAV at 16 kHz')
    config = production.load_config(args.config)
    if config.development_token:
        raise RuntimeError('Production config must not contain a development credential')
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    trace = Trace(target/'report.json')
    trace.add('probe_started', first_turn_only=args.first_turn_only, stop_after_name=args.stop_after_name,
              heartbeat_reader=True, inference_started=False)
    async with ClientSession() as http:
        async with http.get('http://127.0.0.1:8860/health') as response:
            status = await response.json()
            if status.get('nativeSessions') != 0 or status.get('authMode') != 'servicenow':
                raise RuntimeError('Production native listener must be idle in authenticated mode')
    try:
        if args.stop_after_name:
            await single_call(config, Path(args.fixtures), trace, target/'name-turn-received.wav',
                              False, isolation=False, stop_after_name=True, name_fixture=name_fixture)
            trace.add('stop_after_name_probe_completed', confirmation_not_sent=True)
            return
        if args.first_turn_only:
            hello_fixture = None
            if args.hello_first:
                hello_fixture = target/'hello-input.wav'
                pcm = bytearray()
                async with ClientSession() as http:
                    speech = production.Speech(http, config)
                    async for chunk in speech.synthesize('Hallo, wunderbar, was benötigen Sie von mir?'):
                        pcm.extend(chunk)
                with wave.open(str(hello_fixture), 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(pcm)
                trace.add('hello_fixture_prepared', file=str(hello_fixture))
            await single_call(config, Path(args.fixtures), trace, target/'first-turn-received.wav',
                              False, isolation=False, hello_fixture=hello_fixture)
            trace.add('first_turn_probe_completed', name_and_confirmation_not_sent=True)
            return
        await single_call(config, Path(args.fixtures), trace, target/'call1-received.wav', True)
        await single_call(config, Path(args.fixtures), trace, target/'call2-received.wav', False)
        trace.add('acceptance_completed', native_ui=False, human_microphone=False)
    except Exception as error:
        trace.add('acceptance_stopped', error=str(error) if type(error) is RuntimeError else type(error).__name__)
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-approved-audio-demo', action='store_true', required=True)
    parser.add_argument('--config', default='config.example.json')
    parser.add_argument('--fixtures', default=r'E:\SCC-Voice\voices\scc-demo\test-inputs')
    parser.add_argument('--output', default='runtime/full-audio-demo')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--first-turn-only', action='store_true',
                        help='Stop after the real employee-name question, without name or confirmation')
    mode.add_argument('--stop-after-name', action='store_true',
                      help='Stop after the name response reaches input readiness; never review or confirm')
    parser.add_argument('--name-fixture', help='Explicit synthetic mono PCM16 16 kHz WAV for stop-after-name')
    parser.add_argument('--hello-first', action='store_true',
                        help='With first-turn-only: actual fallback, natural hello, then laptop intent; never orders')
    args = parser.parse_args(argv)
    if args.hello_first and not args.first_turn_only:
        parser.error('--hello-first requires --first-turn-only')
    if args.stop_after_name and not args.name_fixture:
        parser.error('--stop-after-name requires --name-fixture')
    if args.name_fixture and not args.stop_after_name:
        parser.error('--name-fixture requires --stop-after-name')
    return args


if __name__ == '__main__':
    args = parse_args()
    try:
        asyncio.run(run(args))
    except Exception as error:
        # HTTP exceptions may embed the ephemeral local credential in a URL.
        print(json.dumps({'stopped':True,'error_type':type(error).__name__}), flush=True)
        raise SystemExit(1)
