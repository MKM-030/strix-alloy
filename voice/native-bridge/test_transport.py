import asyncio
import math
import time
import unittest
from array import array

try:
    from native_bridge import Config, create_app
except ImportError:
    Config = create_app = None

LIVE_WAV = ''


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_deferred_offer_trickle_audio_and_transcripts(self):
        self.assertIsNotNone(create_app, 'native WebRTC adapter is missing')
        from aiohttp import ClientSession, web
        from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription, AudioStreamTrack
        from av import AudioFrame
        from fractions import Fraction

        class Microphone(AudioStreamTrack):
            def __init__(self):
                super().__init__()
                self.n = 0
                self.sound = None
                if LIVE_WAV:
                    import wave
                    import numpy as np
                    with wave.open(LIVE_WAV, 'rb') as wav:
                        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                            raise ValueError('Probe fixture must be mono PCM16 WAV')
                        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
                        self.sound = np.interp(np.arange(0, len(samples), wav.getframerate()/48000),
                                               np.arange(len(samples)), samples).astype('<i2').tobytes()

            async def recv(self):
                await asyncio.sleep(.02)
                loud = 25 <= self.n < 65
                pcm = array('h', [int(5000 * math.sin(2*math.pi*440*j/48000)) if loud else 0
                                  for j in range(960)])
                raw = pcm.tobytes()
                if self.sound is not None:
                    offset = (self.n-25)*1920
                    raw = (self.sound[offset:offset+1920] if offset >= 0 else b'').ljust(1920, b'\0')
                frame = AudioFrame(format='s16', layout='mono', samples=960)
                frame.planes[0].update(raw)
                frame.sample_rate = 48000
                frame.pts = self.n * 960
                frame.time_base = Fraction(1, 48000)
                self.n += 1
                return frame

        class Speech:
            async def transcribe(self, pcm):
                self.input = pcm
                if LIVE_WAV:
                    return await self.real.transcribe(pcm)
                return 'Test ohne Bestellung'

            async def synthesize(self, text):
                self.text = text
                if LIVE_WAV:
                    async for chunk in self.real.synthesize(text):
                        yield chunk
                    return
                for _ in range(25):
                    yield array('h', [int(6000*math.sin(2*math.pi*660*j/24000))
                                      for j in range(480)]).tobytes()

        class Dialog:
            metadata = {'conversation_id':'transport-only', 'interaction_id':''}
            async def open(self):
                pass
            async def turn(self, text):
                self.received = text
                return ['Der Sprachkanal funktioniert.']
            async def close(self):
                pass

        secret = 'test-only-long-credential-never-use-in-deployment'
        speech, dialog = Speech(), Dialog()
        config = Config(instance_name='test', voice_service_id='demo', development_token=secret)
        def speech_factory(http):
            if LIVE_WAV:
                from native_bridge import Speech as RealSpeech
                speech.real = RealSpeech(http, config)
            return speech
        app = create_app(config, speech_factory=speech_factory, dialog_factory=lambda: dialog)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        peer.addTrack(Microphone())
        channel = peer.createDataChannel('transcripts')
        messages, audible = [], asyncio.Event()
        channel.on('message', lambda data: messages.append(__import__('json').loads(data)))
        async def record(track):
            try:
                while True:
                    frame = await track.recv()
                    if abs(frame.to_ndarray()).max() > 1000:
                        audible.set()
            except Exception:
                pass
        peer.on('track', lambda track: asyncio.create_task(record(track)))
        try:
            async with ClientSession() as http:
                base = f'http://127.0.0.1:{port}/webrtc/connect/agent_operator'
                params = {'instance_name':'test', 'voice_service_id':'demo', 'auth_token':secret}
                denied = await http.get(base, params={**params, 'auth_token':'invalid'})
                self.assertEqual(denied.status, 401)
                async with http.ws_connect(base, params=params) as ws:
                    offer = await peer.createOffer()
                    self.assertNotIn('a=candidate:', offer.sdp)
                    await ws.send_json({'type':'offer', 'sdp':{'type':'offer','sdp':offer.sdp}})
                    answer = await ws.receive_json(timeout=10)
                    self.assertEqual(answer['type'], 'answer')
                    self.assertIn('a=msid:', answer['sdp'])
                    await peer.setLocalDescription(offer)
                    await peer.setRemoteDescription(RTCSessionDescription(answer['sdp'], 'answer'))
                    mid = None
                    index = -1
                    for line in peer.localDescription.sdp.splitlines():
                        if line.startswith('m='):
                            index += 1
                        elif line.startswith('a=mid:'):
                            mid = line[6:]
                        elif line.startswith('a=candidate:'):
                            await ws.send_json({'type':'candidate','candidate':{
                                'candidate':line[2:], 'sdpMid':mid, 'sdpMLineIndex':index}})
                    started = time.monotonic()
                    await asyncio.wait_for(audible.wait(), 35 if LIVE_WAV else 12)
                    if LIVE_WAV:
                        self.assertTrue(dialog.received.strip())
                        spoken = [m['data']['content'] for m in messages
                                  if m['type']=='transcript' and m['data']['role']=='user']
                        print(__import__('json').dumps({'real_speech_transport':True,
                            'native_ui':False,'servicenow_dialog':False,
                            'recognized_turns':spoken,'received_speech_pcm_bytes':len(speech.input),
                            'connect_to_first_audio_seconds':round(time.monotonic()-started,3)}, ensure_ascii=False))
                    else:
                        self.assertEqual(dialog.received, 'Test ohne Bestellung')
                    self.assertGreater(len(speech.input), 10000)
                    self.assertTrue(any(m['type']=='metadata' for m in messages))
                    roles = [m['data']['role'] for m in messages if m['type']=='transcript']
                    # A real fixture may contain pauses longer than the endpoint
                    # timeout and legitimately create multiple conversational turns.
                    self.assertEqual(roles, ['user','assistant']*(len(roles)//2))
                    if not LIVE_WAV:
                        self.assertEqual(roles, ['user','assistant'])
        finally:
            await peer.close()
            await runner.cleanup()


if __name__ == '__main__':
    import sys
    if '--live-wav' in sys.argv:
        index = sys.argv.index('--live-wav')
        LIVE_WAV = sys.argv[index+1]
        del sys.argv[index:index+2]
    unittest.main()
