"""Actual source regressions for live microphone silence suppression.

RTC/PyAV boundaries are substituted; no platform, model or speech services.
"""
import ast
import asyncio
from array import array
from dataclasses import dataclass
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import time
import types
import unittest
import uuid
from managed_turn import clear_session_ice
from noise_guard import SpeechNoiseGuard
from test_input_lifecycle import PassThroughDenoiser, configuration

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('NATIVE_GAP_SOURCE', str(HERE / 'native_bridge.py')))
CORE = Path(os.environ.get('NATIVE_GAP_CORE', str(HERE / 'core.py')))
spec = importlib.util.spec_from_file_location('test_gap_core', CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class Peer:
    connectionState = 'connected'
    iceConnectionState = 'completed'
    def __init__(self, conf): self.handlers = {}
    def on(self, key, value): self.handlers[key] = value
    def addTrack(self, track): pass
    async def close(self): pass

class Frame:
    def __init__(self, loud): self.audio = array('h', [3000 if loud else 0] * 320)
    def to_ndarray(self): return self.audio

class Track:
    kind = 'audio'
    readyState = 'live'
    def __init__(self):
        self.queue = asyncio.Queue()
        self.calls = self.cancelled = 0
    def feed(self, count, loud=True):
        for _ in range(count): self.queue.put_nowait(Frame(loud))
    def end(self): self.queue.put_nowait(None)
    async def recv(self):
        self.calls += 1
        try:
            frame = await self.queue.get()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        if frame is None:
            self.readyState = 'ended'
            raise RuntimeError('synthetic_track_end_forbidden_secret')
        return frame

class Resampler:
    def __init__(self, **kwargs): pass
    def resample(self, frame): return [frame]

scope = dict(asyncio=asyncio, time=time, uuid=uuid, json=json, math=math, LOG=logging.getLogger('native-voice'),
    dataclass=dataclass, SpeechNoiseGuard=SpeechNoiseGuard,
    StreamingPCM16Denoiser=PassThroughDenoiser, clear_session_ice=clear_session_ice,
    AudioResampler=Resampler, RTCPeerConnection=Peer, RTCConfiguration=lambda **kw:kw,
    SpeakerTrack=lambda playback:object(), EndpointGate=core.EndpointGate, PlaybackBuffer=core.PlaybackBuffer,
    RTCIceServer=lambda **kw:kw, STUN_URL='unit-test')
nodes = [n for n in ast.parse(SOURCE.read_text()).body
         if isinstance(n, ast.ClassDef) and n.name in {'NativeCall', '_InputEnvelope'}]
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
NativeCall = scope['NativeCall']

async def until(test, timeout=1):
    async with asyncio.timeout(timeout):
        while not test(): await asyncio.sleep(.002)

class GapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config = configuration()
        self.call = NativeCall(config, None, types.SimpleNamespace(metadata={}))
        self.track = Track()
        self.worker = asyncio.create_task(self.call.microphone(self.track))
    async def asyncTearDown(self):
        self.call.closed = True
        self.worker.cancel()
        await asyncio.gather(self.worker, return_exceptions=True)
        for task in tuple(self.call.tasks): task.cancel()
        await asyncio.gather(*tuple(self.call.tasks), return_exceptions=True)

    async def test_live_track_gap_after_real_voice_is_queued_exactly_once(self):
        self.track.feed(20)
        await until(lambda:self.track.queue.empty())
        await asyncio.sleep(1.55)
        self.assertEqual(self.call.turns.qsize(), 1,
            '400ms voice followed by1.55s live-track recv gap mustfinish withoutPCM silence')
        self.assertFalse(self.call.input_lost)
        self.assertEqual(self.track.cancelled, 0, 'polling mustnotcancelpendingRTCrecv')
        self.assertEqual(self.track.calls, 21, 'onlyonependingRTCrecv allowed')
        await asyncio.sleep(.3)
        self.assertEqual(self.call.turns.qsize(), 1, 'wall gap submittedsameutterancetwice')

    async def test_sparse_quiet_comfort_noise_uses_wall_silence(self):
        self.track.feed(20)
        await until(lambda:self.track.queue.empty())
        for _ in range(4):
            await asyncio.sleep(.4)
            self.track.feed(1, False)
        await asyncio.sleep(.05)
        self.assertEqual(self.call.turns.qsize(), 1,
            'Sparse20ms quietframes mustnotstretch1200ms speechsilence to24seconds')
        self.assertEqual(self.track.cancelled, 0)

    async def test_short_pause_can_continue_same_utterance_without_frames(self):
        self.track.feed(20)
        await until(lambda:self.track.queue.empty())
        await asyncio.sleep(.35)
        self.track.feed(20)
        self.track.feed(70, False)
        await until(lambda:self.call.turns.qsize() == 1)
        self.assertEqual(self.call.turns.qsize(), 1)
        self.assertEqual(self.track.cancelled, 0)

    async def test_gap_without_voice_does_not_submit_or_lose_input(self):
        self.track.feed(20, False)
        await until(lambda:self.track.queue.empty())
        await asyncio.sleep(1.4)
        self.assertEqual(self.call.turns.qsize(), 0)
        self.assertFalse(self.call.input_lost)
        self.assertEqual(self.track.cancelled, 0)

    async def test_onset_below_minimum_does_not_become_turn_on_gap(self):
        self.track.feed(5)
        await until(lambda:self.track.queue.empty())
        await asyncio.sleep(1.4)
        self.assertEqual(self.call.turns.qsize(), 0)
        self.assertFalse(self.call.input_lost)

    async def test_close_during_pending_gap_never_queues(self):
        self.track.feed(20)
        await until(lambda:self.track.queue.empty())
        self.call.closing = True
        await asyncio.sleep(1.4)
        self.assertEqual(self.call.turns.qsize(), 0)

    async def test_actual_track_end_keeps_terminal_loss_semantics(self):
        self.track.feed(20)
        self.track.end()
        await asyncio.wait_for(self.worker, 1)
        await until(lambda:self.call.input_lost)
        self.assertEqual(self.call.turns.qsize(), 0)
        self.assertTrue(self.call.input_ended.is_set())

    async def test_continuous_pcm_silence_queues_before_any_wall_gap(self):
        self.track.feed(20)
        self.track.feed(70, False)
        await until(lambda:self.call.turns.qsize() == 1)
        self.assertEqual(self.call.turns.qsize(), 1)
        self.assertEqual(self.track.cancelled, 0)

if __name__ == '__main__': unittest.main()
