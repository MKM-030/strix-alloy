import json
import contextlib
import hashlib
import io
import pathlib
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1]
REPO = BENCHMARKS.parents[1]
sys.path.insert(0, str(BENCHMARKS))
import article_metrics
import clock_probe
sys.path.insert(0, str(REPO / 'server'))
import host_frames
import aiohttp


class SelectedBackend(Exception):
    pass


class GatewayBackendTests(unittest.TestCase):
    def test_runner_retains_input_manifest_for_native_and_halogen(self):
        original_read = pathlib.Path.read_text
        memory = {'available_bytes': 30 * 1024**3, 'commit_headroom_bytes': 30 * 1024**3}

        class FixtureClock:
            def __init__(self, distribution, user):
                pass
            def sample(self):
                return {}
            def compare(self, first, last):
                return {'monotonic_per_raw': 1.0}
            def close(self):
                pass

        class Response:
            status = 200
            def __init__(self, value):
                self.value = value
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def json(self):
                return self.value

        for label, kind, model in (('gufo', 'native', 'gufo-flash-next'),
                                   ('halogen-v2', 'halogen', 'halogen-v2')):
            with self.subTest(backend=label), tempfile.TemporaryDirectory(
                    dir=REPO / 'server/.local') as directory:
                work = pathlib.Path(directory)
                profile = work / 'profile.json'
                profile.write_text(json.dumps({'engine': {'kind': kind,
                    'directory': 'backends/halogen-wsl2-0.16.2'}}), encoding='utf-8')
                token = work / 'token.txt'
                token.write_text('fixture-token', encoding='ascii')
                prompt = work / 'prompt-512-prose.txt'
                prompt.write_text('Fixture prose.', encoding='utf-8')
                (work / 'manifest.json').write_text(json.dumps({'prompts': {'512': {
                    'file': prompt.name, 'sha256': hashlib.sha256(prompt.read_bytes()).hexdigest()}}}),
                    encoding='utf-8')
                state = {'phase': 'ready', 'run_id': 'fixture-run', 'context': 262144,
                         'backend': model, 'minimum_reserve_gib': 18, 'memory': memory,
                         'profile_sha256': hashlib.sha256(profile.read_bytes()).hexdigest()}

                def read_fixture(path, *args, **kwargs):
                    if path.name == 'current.json':
                        return json.dumps(state)
                    if path.name == 'machine.json':
                        return json.dumps({'distro': 'fixture-distro', 'user': 'fixture-user'})
                    if path.name == 'current-service.json':
                        return json.dumps({'phase': 'ready', 'checkpoint': 'v2', 'context': 262144,
                                           'run_id': 'fixture-engine', 'attempt': str(work / 'attempt')})
                    if path == work / 'attempt/manifest.json':
                        return json.dumps({'environment': {'HALOGEN_PROMPT_CACHE': '0'}})
                    return original_read(path, *args, **kwargs)

                class FixtureSession:
                    def __init__(self, **kwargs):
                        pass
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *args):
                        pass
                    def get(self, url, **kwargs):
                        return Response({'backend': model, 'context': 262144, 'active_requests': 0})
                    def post(self, url, *, json, **kwargs):
                        count = json['max_tokens']
                        return Response({'usage': {'prompt_tokens': 512, 'completion_tokens': count},
                            'timings': {'prompt_n': 512, 'predicted_n': count, 'cache_n': 0,
                                        'prompt_per_second': 1000, 'predicted_per_second': 40},
                            'choices': [{'message': {'content': 'fixture-output'},
                                         'finish_reason': 'length'}]})

                argv = ['gateway_cold.py', '--backend', label, '--context', '262144', '--sizes', '512',
                        '--prompts', str(work), '--output', str(work / 'output'),
                        '--token-file', str(token), '--profile', str(profile)]
                with patch.object(sys, 'argv', argv), \
                     patch.object(pathlib.Path, 'read_text', read_fixture), \
                     patch.object(clock_probe, 'ClockProbe', FixtureClock), \
                     patch.object(aiohttp, 'ClientSession', FixtureSession), \
                     patch.object(host_frames, 'frame', return_value=memory), \
                     contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(BENCHMARKS / 'gateway_cold.py'), run_name='__main__')
                result = json.loads((work / 'output/summary.json').read_text(encoding='utf-8'))
                identity = json.loads((work / 'output/identity.json').read_text(encoding='utf-8'))
                self.assertTrue(result['passed'])
                self.assertEqual(result['samples'], 9 if kind == 'halogen' else 6)
                self.assertEqual(identity['input_manifest_sha256'],
                                 hashlib.sha256((work / 'manifest.json').read_bytes()).hexdigest())

    def test_cold_runner_uses_selected_profile_for_guest_clock(self):
        original_read = pathlib.Path.read_text

        def read_fixture(path, *args, **kwargs):
            if path.name == 'machine.json':
                return json.dumps({'distro': path.parent.parent.name, 'user': 'fixture-user'})
            return original_read(path, *args, **kwargs)

        def selected_clock(distribution, user):
            raise SelectedBackend(distribution)

        for version in ('0.16.2', '0.15.1'):
            with self.subTest(version=version), tempfile.TemporaryDirectory(
                    dir=REPO / 'server/.local') as directory:
                work = pathlib.Path(directory)
                profile = work / 'profile.json'
                profile.write_text(json.dumps({'engine': {'kind': 'halogen',
                    'directory': f'backends/halogen-wsl2-{version}'}}), encoding='utf-8')
                token = work / 'token.txt'
                token.write_text('fixture-token', encoding='ascii')
                argv = ['gateway_cold.py', '--backend', 'halogen-v2', '--context', '262144',
                        '--prompts', str(work), '--output', str(work / 'output'),
                        '--token-file', str(token), '--profile', str(profile)]
                with patch.object(sys, 'argv', argv), \
                     patch.object(pathlib.Path, 'read_text', read_fixture), \
                     patch.object(clock_probe, 'ClockProbe', selected_clock), \
                     self.assertRaises(SelectedBackend) as selected:
                    runpy.run_path(str(BENCHMARKS / 'gateway_cold.py'), run_name='__main__')
                self.assertEqual(str(selected.exception), f'halogen-wsl2-{version}')

    def test_backend_directory_refuses_native_and_outside_paths(self):
        profiles = [
            {'engine': {'kind': 'native', 'directory': 'backends/halogen-wsl2-0.16.2'}},
            {'engine': {'kind': 'halogen', 'directory': '../other-checkout/backends'}},
            {'engine': {'kind': 'halogen', 'directory': 'server'}},
            {'engine': {'kind': 'halogen'}},
        ]
        for profile in profiles:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                article_metrics.halogen_backend_directory(REPO, profile)


if __name__ == '__main__':
    unittest.main()
