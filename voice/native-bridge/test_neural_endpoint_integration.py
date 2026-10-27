"""Speech decisions must preserve PCM and control the real native interruption path."""
import asyncio
from array import array
from fractions import Fraction
import inspect
import json
from pathlib import Path
import tempfile
import unittest

from core import EndpointGate

HERE = Path(__file__).resolve().parent


class NeuralEndpointTests(unittest.TestCase):
    def test_speech_decision_rejects_loud_noise_and_preserves_quiet_speech(self):
        # Catches continuing to use energy after an explicit speech classification.
        self.assertIn('voiced', inspect.signature(EndpointGate.feed).parameters,
                      'EndpointGate must consume the actual speech classifier decision')
        gate = EndpointGate(threshold=450, onset_ms=100, silence_ms=1200)
        loud_noise = array('h', [1200, -1200] * 160).tobytes()
        for _ in range(100):
            self.assertEqual(gate.feed(loud_noise, voiced=False), (False, None))
        quiet_speech = array('h', [40, -40] * 160).tobytes()
        events = [gate.feed(quiet_speech, voiced=True) for _ in range(20)]
        events += [gate.feed(bytes(640), voiced=False) for _ in range(65)]
        self.assertEqual(sum(began for began, _ in events), 1)
        utterances = [pcm for _, pcm in events if pcm is not None]
        self.assertEqual(len(utterances), 1)
        self.assertIn(quiet_speech * 20, utterances[0])

    def test_no_classifier_keeps_legacy_energy_contract(self):
        # Catches a regression in existing offline/demo users of the gate.
        gate = EndpointGate(threshold=450, onset_ms=100)
        starts = [gate.feed(array('h', [1000] * 320).tobytes())[0] for _ in range(10)]
        self.assertEqual(sum(starts), 1)


class NeuralNativeInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_relative_profile_is_warmed_and_reported_by_running_app(self):
        # Catches resolving from cwd, skipping startup verification, or stale health.
        from native_bridge import load_config, create_app
        from aiohttp.test_utils import TestClient, TestServer
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'speech.json').write_bytes((HERE / 'speech-activity.profile.json').read_bytes())
            (target / 'bridge.json').write_text(json.dumps({'speech_activity_config_file':'speech.json'}))
            config = load_config(target / 'bridge.json')
            self.assertTrue(config.private_speech_activity.enabled)
            async with TestClient(TestServer(create_app(config))) as client:
                response = await client.get('/health')
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())['speechActivity'], 'silero-cpu')

    async def test_invalid_explicit_profile_never_silently_uses_energy(self):
        # Catches a startup fallback reintroducing noise interruption after asset drift.
        from native_bridge import load_config
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            value = json.loads((HERE / 'speech-activity.profile.json').read_text())
            value['model_sha256'] = '0' * 64
            (target / 'speech.json').write_text(json.dumps(value))
            (target / 'bridge.json').write_text(json.dumps({'speech_activity_config_file':'speech.json'}))
            with self.assertRaises(ValueError):
                load_config(target / 'bridge.json')
            (target / 'bridge.json').write_text(json.dumps({'private_speech_activity':value}))
            with self.assertRaises(ValueError):
                load_config(target / 'bridge.json')

    async def test_real_native_input_ignores_noise_but_quiet_speech_interrupts(self):
        # Catches a classifier wired only to tests, or RMS still suppressing quiet speech.
        from native_bridge import Config, NativeCall
        self.assertIn('private_speech_activity', Config.__dataclass_fields__,
                      'Native calls must retain the validated speech detector snapshot')
        from speech_activity import load_speech_activity_file
        from av import AudioFrame, AudioResampler
        import av
        import numpy as np

        profile = load_speech_activity_file(HERE / 'speech-activity.profile.json')
        reference = Path(r'C:/Projects/strix-alloy-scc-voice/voice/assets/scc-demo/reference.wav')
        chunks = []
        converter = AudioResampler(format='s16', layout='mono', rate=16000)
        with av.open(str(reference)) as source:
            for frame in source.decode(audio=0):
                for mono in converter.resample(frame):
                    values = mono.to_ndarray().reshape(-1).astype(np.float64)
                    chunks.append(np.rint(values * .1).astype('<i2').tobytes())
            for mono in converter.resample(None):
                values = mono.to_ndarray().reshape(-1).astype(np.float64)
                chunks.append(np.rint(values * .1).astype('<i2').tobytes())
        speech = b''.join(chunks)

        class Track:
            kind, readyState = 'audio', 'live'
            def __init__(self):
                self.frames = asyncio.Queue()
                self.idle = asyncio.Event()
                self.offset = 0
            def feed(self, pcm):
                self.idle.clear()
                for pos in range(0, len(pcm), 640):
                    part = pcm[pos:pos+640]
                    if len(part) < 640:
                        part += bytes(640-len(part))
                    frame = AudioFrame(format='s16', layout='mono', samples=320)
                    frame.planes[0].update(part)
                    frame.sample_rate, frame.pts = 16000, self.offset
                    frame.time_base = Fraction(1, 16000)
                    self.offset += 320
                    self.frames.put_nowait(frame)
            async def recv(self):
                if self.frames.empty():
                    self.idle.set()
                return await self.frames.get()

        class Dialog:
            async def close(self): pass

        call = NativeCall(Config(vad_threshold=30000, private_speech_activity=profile), object(), Dialog())
        track = Track()
        # Deterministic broad-band static with amplitude well above the old floor.
        rng = np.random.default_rng(20261023)
        noise = np.clip(rng.normal(0, 1000, 32000), -32768, 32767).astype('<i2').tobytes()
        call.playback.put(b'\x01\x00' * 24000, 0)
        call.synthesis_active = True
        track.feed(noise + bytes(16000 * 2))
        task = call.spawn(call.microphone(track))
        try:
            await asyncio.wait_for(track.idle.wait(), 4)
            self.assertEqual(call.playback.generation, 0, 'Static interrupted the prompt')
            self.assertEqual(len(call.playback.data), 48000)
            self.assertTrue(call.turns.empty(), 'Static was submitted to ASR')
            track.feed(speech + bytes(16000 * 3))
            await asyncio.wait_for(track.idle.wait(), 6)
            self.assertEqual(call.playback.generation, 1, 'Real speech did not interrupt promptly')
            self.assertEqual(len(call.playback.data), 0)
            self.assertFalse(call.turns.empty(), 'Quiet real speech was lost before ASR')
            generation, captured = call.turns.get_nowait()
            call.turns.task_done()
            self.assertEqual(generation, 1)
            self.assertIn(speech[3200:6400], captured, 'Original speech PCM was altered or clipped')
        finally:
            await call.close()
            await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
