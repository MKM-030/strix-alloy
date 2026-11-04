"""CPU-only admission tests: synthetic memory and ephemeral in-process HTTP."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'server'))
import controller
import host_frames
from gateway import Backend, Gateway

KEY = 'synthetic-capacity-entry-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + KEY}
CHAT = '/v1/chat/completions'
GIB = 1024 ** 3


def memory(physical=22 * GIB, commit=22 * GIB):
    return dict(available_bytes=physical, committed_bytes=100 * GIB,
                commit_limit_bytes=100 * GIB + commit, commit_headroom_bytes=commit)


def profile(slots=2):
    value = json.loads((REPO / 'server/tests/fixtures/halogen01822-capacity-text32k-profile.json').read_text())
    value['concurrency'] = 2
    value['engine'].update(slots=slots, kv_pool_positions=65536)
    value['backend']['expected'].update(slots=slots, kv_pool_positions=65536, capability_probe='ok')
    return value


class EntryPolicyTests(unittest.TestCase):
    def guard(self):
        guard = getattr(controller, 'halogen_request_entry_guard', None)
        self.assertTrue(callable(guard), 'Two-slot controller request-entry guard is missing')
        return guard

    def test_exact_22_gib_and_fresh_sample_are_admitted_once(self):
        guard = self.guard()
        samples = []
        def sample():
            samples.append('sample')
            return memory()
        with patch.object(host_frames, 'frame', sample):
            guard()
        self.assertEqual(samples, ['sample'])

    def test_low_invalid_and_inconsistent_telemetry_is_rejected(self):
        guard = self.guard()
        cases = [memory(22 * GIB - 1), memory(commit=22 * GIB - 1), {}, None, [],
                 memory(physical=True), memory(commit=True), memory(physical=22.0 * GIB)]
        for field in ('available_bytes', 'committed_bytes', 'commit_limit_bytes', 'commit_headroom_bytes'):
            for bad in (None, True, -1, '22', 22.0):
                value = memory()
                value[field] = bad
                cases.append(value)
            value = memory()
            del value[field]
            cases.append(value)
        value = memory()
        value['commit_headroom_bytes'] += 1
        cases.append(value)
        value = memory()
        value['committed_bytes'] = value['commit_limit_bytes'] + 1
        cases.append(value)
        for value in cases:
            with self.subTest(value=value), patch.object(host_frames, 'frame', return_value=value):
                with self.assertRaises((ValueError, OSError)):
                    guard()

    def test_slow_stale_and_failed_samples_are_rejected_without_resampling(self):
        guard = self.guard()
        for elapsed in (1, 1.5, -0.1, float('nan'), float('inf')):
            with self.subTest(elapsed=elapsed), patch.object(host_frames, 'frame', return_value=memory()), \
                    patch.object(controller.time, 'monotonic', side_effect=[100, 100 + elapsed]):
                with self.assertRaises(ValueError):
                    guard()
        with patch.object(host_frames, 'frame', side_effect=OSError('synthetic telemetry failure')):
            with self.assertRaises(OSError):
                guard()

    def test_only_complete_explicit_two_slot_halogen_profile_installs_guard(self):
        install = getattr(controller, 'install_halogen_request_entry_guard', None)
        self.assertTrue(callable(install), 'Controller guard installation is missing')
        def gateway():
            return Gateway(Backend('halogen-v2', 'http://127.0.0.1:8731', 'fixture'), KEY)
        guarded = gateway()
        install(profile(), guarded, REPO)
        self.assertIs(guarded._inference_entry_guard, self.guard())
        for value in (profile(slots=1), {'engine': {'kind': 'native'}},
                      {'engine': {'kind': 'halogen'}, 'concurrency': 1}):
            untouched = gateway()
            install(value, untouched, REPO)
            self.assertIsNone(untouched._inference_entry_guard)
        invalid = profile()
        del invalid['engine']['kv_pool_positions']
        with self.assertRaises(ValueError):
            install(invalid, gateway(), REPO)


class ControllerEntryWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_installs_guard_before_any_engine_construction_only_for_two_slots(self):
        normal = json.loads((REPO / 'server/tests/fixtures/halogen01822-capacity-text32k-profile.json').read_text())
        for configuration, guarded in ((normal, False), (profile(), True)):
            with self.subTest(guarded=guarded), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'synthetic-profile.json'
                path.write_text(json.dumps(configuration))
                gateway = Gateway(Backend('halogen-v2', 'http://127.0.0.1:8731', 'fixture'), KEY)
                # Stop before constructing any engine, telemetry or listener.
                with patch.object(controller, 'load_config', return_value=gateway), \
                        patch.object(controller, 'Engine', side_effect=RuntimeError('synthetic construction boundary')):
                    with self.assertRaisesRegex(RuntimeError, 'synthetic construction boundary'):
                        await controller.run(path, 8840)
                self.assertEqual(gateway._inference_entry_guard is not None, guarded)


class EntryTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        install = getattr(controller, 'install_halogen_request_entry_guard', None)
        self.assertTrue(callable(install), 'Controller guard installation is missing')
        self.sample = memory()
        self.samples = []
        self.seen = []
        self.started = asyncio.Queue()
        self.release = asyncio.Event()
        self.tasks = []

        def sample():
            self.samples.append(deepcopy(self.sample))
            if isinstance(self.sample, Exception):
                raise self.sample
            return deepcopy(self.sample)
        self.memory_patch = patch.object(host_frames, 'frame', sample)
        self.memory_patch.start()

        async def health(request):
            return web.json_response({'status': 'ok'})
        async def chat(request):
            body = await request.json()
            name = body['messages'][-1]['content']
            self.seen.append(name)
            self.started.put_nowait(name)
            if name == 'held business':
                await self.release.wait()
            return web.json_response({'choices': [{'message': {'content': 'synthetic reply'}}]})
        upstream = web.Application()
        upstream.router.add_get('/health', health)
        upstream.router.add_post(CHAT, chat)
        self.upstream = TestServer(upstream, handler_cancellation=True)
        await self.upstream.start_server()
        self.gateway = Gateway(Backend('halogen-v2', str(self.upstream.make_url('')).rstrip('/'),
                                      'fixture', checkpoint='v2', context=32768, routes=(CHAT,)),
                               KEY, concurrency=2, queue_limit=2, queue_seconds=2)
        install(profile(), self.gateway, REPO)
        self.direct = TestClient(TestServer(self.gateway.app, handler_cancellation=True))
        await self.direct.start_server()
        self.public_gateway = Gateway(Backend('controller-selected',
            str(self.direct.make_url('')).rstrip('/'), 'controller-selected', routes=(CHAT,)),
            KEY, KEY, concurrency=1, queue_limit=8, queue_seconds=2, controller_consumer=True)
        self.public = TestClient(TestServer(self.public_gateway.app, handler_cancellation=True))
        await self.public.start_server()

    async def asyncTearDown(self):
        self.release.set()
        for task in getattr(self, 'tasks', []):
            if not task.done():
                task.cancel()
        await asyncio.gather(*getattr(self, 'tasks', []), return_exceptions=True)
        for name in ('public', 'direct', 'upstream'):
            if hasattr(self, name):
                await getattr(self, name).close()
        if hasattr(self, 'memory_patch'):
            self.memory_patch.stop()

    def post(self, client, text):
        task = asyncio.create_task(client.post(CHAT, headers=HEADERS,
            json={'model': 'halogen-v2', 'messages': [{'role': 'user', 'content': text}]}))
        self.tasks.append(task)
        return task

    async def test_business_and_direct_voice_share_entry_guard_and_overlap(self):
        business = self.post(self.public, 'held business')
        self.assertEqual(await asyncio.wait_for(self.started.get(), 2), 'held business')
        voice = await self.post(self.direct, 'short voice')
        self.assertEqual(voice.status, 200)
        await voice.read()
        self.assertEqual(self.seen, ['held business', 'short voice'])
        self.assertEqual(len(self.samples), 2)
        self.release.set()
        response = await business
        self.assertEqual(response.status, 200)
        await response.read()

    async def test_waiting_request_checks_memory_after_grant(self):
        self.gateway.concurrency = 1
        business = self.post(self.public, 'held business')
        self.assertEqual(await asyncio.wait_for(self.started.get(), 2), 'held business')
        voice = self.post(self.direct, 'queued voice')
        async with asyncio.timeout(2):
            while len(self.gateway.waiters) != 1:
                await asyncio.sleep(.001)
        self.assertEqual(len(self.samples), 1, 'Queued request sampled before its slot grant')
        self.sample = memory(physical=22 * GIB - 1)
        self.release.set()
        response = await business
        await response.read()
        rejected = await voice
        self.assertEqual(rejected.status, 503)
        await rejected.read()
        self.assertEqual(self.seen, ['held business'])
        self.assertEqual(len(self.samples), 2)
        self.assertEqual(self.gateway.active, 0)

    async def test_invalid_telemetry_never_posts_and_gets_do_not_sample(self):
        for invalid in ({}, memory(physical=True), memory(commit=0), OSError('unavailable')):
            self.sample = invalid
            response = await self.post(self.direct, 'rejected voice')
            self.assertEqual(response.status, 503)
            await response.read()
        self.assertEqual(self.seen, [])
        before = len(self.samples)
        for client in (self.direct, self.public):
            for path in ('/health', '/v1/models'):
                response = await client.get(path, headers=HEADERS)
                self.assertEqual(response.status, 200)
                await response.read()
        self.assertEqual(len(self.samples), before)
        self.assertEqual(self.gateway.active, 0)


if __name__ == '__main__':
    unittest.main()
