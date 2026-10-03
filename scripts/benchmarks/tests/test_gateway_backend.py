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


class GatewayStateSharingTests(unittest.TestCase):
    """Exercise the real cold harness with offline API and state-file fixtures."""

    def run_fixture(self, target=None, *, persistent=False, replacement=None,
                    replacement_raw=None, permanent_error=None, transient=2):
        import copy
        import types
        import controller
        original_read = pathlib.Path.read_text
        memory = {'available_bytes': 30 * 1024**3, 'commit_headroom_bytes': 30 * 1024**3}
        clock = {'now': 0.0, 'sleeps': []}
        successes = {'current.json': 0, 'current-service.json': 0}
        fault = {'remaining': transient}
        posts = []

        def sleep(delay):
            clock['sleeps'].append(delay)
            clock['now'] += delay

        class FixtureClock:
            def __init__(self, *args):
                pass
            def sample(self):
                return {}
            def compare(self, *args):
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

        class FixtureSession:
            def __init__(self, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def get(self, *args, **kwargs):
                return Response({'backend': 'halogen-v2', 'context': 262144, 'active_requests': 0})
            def post(self, url, *, json, **kwargs):
                posts.append(copy.deepcopy(json))
                count = json['max_tokens']
                return Response({'usage': {'prompt_tokens': 512, 'completion_tokens': count,
                                          'total_tokens': 512 + count},
                    'timings': {'prompt_n': 512, 'predicted_n': count, 'cache_n': 0,
                                'prompt_per_second': 1000, 'predicted_per_second': 40},
                    'choices': [{'message': {'content': 'fixture-output'}, 'finish_reason': 'length'}]})

        with tempfile.TemporaryDirectory(dir=REPO / 'server/.local') as directory:
            work = pathlib.Path(directory)
            profile = work / 'profile.json'
            profile.write_text(json.dumps({'engine': {'kind': 'halogen',
                'directory': 'backends/halogen-wsl2-0.16.2'}}), encoding='utf-8')
            token = work / 'token.txt'
            token.write_text('fixture-token', encoding='ascii')
            prompt = work / 'prompt-512-prose.txt'
            prompt.write_text('Fixture prose.', encoding='utf-8')
            (work / 'manifest.json').write_text(json.dumps({'prompts': {'512': {
                'file': prompt.name, 'sha256': hashlib.sha256(prompt.read_bytes()).hexdigest()}}}),
                encoding='utf-8')
            state = {'phase': 'ready', 'run_id': 'fixture-run', 'context': 262144,
                'backend': 'halogen-v2', 'minimum_reserve_gib': 18, 'memory': memory,
                'profile_sha256': hashlib.sha256(profile.read_bytes()).hexdigest()}
            backend = {'phase': 'ready', 'checkpoint': 'v2', 'context': 262144,
                'run_id': 'fixture-engine', 'attempt': str(work / 'attempt')}

            def read_fixture(path, *args, **kwargs):
                name = path.name
                if name in successes:
                    index = successes[name] + 1
                    value = copy.deepcopy(state if name == 'current.json' else backend)
                    if target == (name, index):
                        if permanent_error is not None:
                            raise permanent_error
                        if persistent or fault['remaining']:
                            fault['remaining'] -= 1
                            raise PermissionError(13, 'fixture sharing violation', str(path))
                        if replacement is not None:
                            value.update(replacement)
                        if replacement_raw is not None:
                            successes[name] += 1
                            return replacement_raw
                    successes[name] += 1
                    return json.dumps(value)
                if name == 'machine.json':
                    return json.dumps({'distro': 'fixture-distro', 'user': 'fixture-user'})
                if path == work / 'attempt/manifest.json':
                    return json.dumps({'environment': {'HALOGEN_PROMPT_CACHE': '0'}})
                return original_read(path, *args, **kwargs)

            argv = ['gateway_cold.py', '--backend', 'halogen-v2', '--context', '262144',
                '--sizes', '512', '--prompts', str(work), '--output', str(work / 'output'),
                '--token-file', str(token), '--profile', str(profile)]
            error = None
            fake_time = types.SimpleNamespace(monotonic=lambda: clock['now'], sleep=sleep)
            with patch.object(sys, 'argv', argv), \
                 patch.object(pathlib.Path, 'read_text', read_fixture), \
                 patch.object(controller, 'time', fake_time), \
                 patch.object(clock_probe, 'ClockProbe', FixtureClock), \
                 patch.object(aiohttp, 'ClientSession', FixtureSession), \
                 patch.object(host_frames, 'frame', return_value=memory), \
                 contextlib.redirect_stdout(io.StringIO()):
                try:
                    runpy.run_path(str(BENCHMARKS / 'gateway_cold.py'), run_name='__main__')
                except (PermissionError, FileNotFoundError, ValueError, RuntimeError) as exc:
                    error = exc
            output = work / 'output'
            def artifact(name):
                path = output / name
                return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            samples = output / 'samples.jsonl'
            return {'error': error, 'elapsed': clock['now'], 'sleeps': clock['sleeps'],
                'posts': len(posts), 'identity': artifact('identity.json'),
                'summary': artifact('summary.json'), 'failure': artifact('failure.json'),
                'rows': [json.loads(line) for line in samples.read_text().splitlines()] if samples.exists() else []}

    def test_transient_sharing_preserves_actual_harness_samples_and_identity(self):
        baseline = self.run_fixture()
        self.assertIsNone(baseline['error'])
        self.assertTrue(baseline['summary']['passed'])
        self.assertEqual((len(baseline['rows']), baseline['summary']['samples']), (12, 9))
        fields = ('size', 'output', 'drafter', 'rep', 'phase', 'usage',
                  'request_sha256', 'prompt_sha256', 'output_sha256')
        expected = [{key: row[key] for key in fields} for row in baseline['rows']]
        # Current reads 4 and 5 surround the first retained request, following calibration.
        for target in (('current.json', 1), ('current.json', 4), ('current.json', 5),
                       ('current-service.json', 1)):
            with self.subTest(target=target):
                actual = self.run_fixture(target)
                self.assertIsNone(actual['error'])
                self.assertTrue(actual['summary']['passed'])
                self.assertEqual(actual['identity'], baseline['identity'])
                self.assertEqual(actual['posts'], baseline['posts'])
                self.assertEqual([{key: row[key] for key in fields} for row in actual['rows']], expected)
                self.assertEqual(actual['sleeps'], [0.025, 0.025])

    def test_persistent_startup_sharing_times_out_without_inference_or_success(self):
        actual = self.run_fixture(('current.json', 1), persistent=True)
        self.assertIsInstance(actual['error'], PermissionError)
        self.assertGreaterEqual(actual['elapsed'], 1.0)
        self.assertLessEqual(actual['elapsed'], 1.025000001)
        self.assertEqual(actual['posts'], 0)
        self.assertIsNone(actual['summary'])
        self.assertEqual(actual['rows'], [])
        self.assertIn('PermissionError', actual['failure']['error'])
        self.assertEqual(actual['failure']['completed_requests'], 0)

    def test_retried_snapshot_still_rejects_changed_run_profile_and_terminal_phase(self):
        cases = [
            (('current.json', 5), {'run_id': 'foreign-run'}, RuntimeError,
             'Runtime changed during request', 2),
            (('current.json', 4), {'profile_sha256': '0' * 64}, ValueError,
             'selected profile bytes', 1),
            (('current.json', 1), {'phase': 'stopped'}, RuntimeError,
             'Controller terminal', 0),
        ]
        for target, replacement, kind, message, posts in cases:
            with self.subTest(replacement=replacement):
                actual = self.run_fixture(target, replacement=replacement)
                self.assertIsInstance(actual['error'], kind)
                self.assertIn(message, str(actual['error']))
                self.assertEqual(actual['sleeps'], [0.025, 0.025])
                self.assertEqual(actual['posts'], posts)
                self.assertIsNone(actual['summary'])
                self.assertEqual(actual['rows'], [])
                self.assertEqual(actual['failure']['completed_requests'], 0)

    def test_nonsharing_read_errors_do_not_retry_or_start_inference(self):
        for error in (FileNotFoundError(2, 'fixture state missing'),):
            with self.subTest(error=type(error).__name__):
                actual = self.run_fixture(('current.json', 1), permanent_error=error)
                self.assertIsInstance(actual['error'], FileNotFoundError)
                self.assertEqual(actual['sleeps'], [])
                self.assertEqual(actual['posts'], 0)
                self.assertIsNone(actual['summary'])
        # A successfully opened but malformed snapshot is not a sharing conflict.
        actual = self.run_fixture(('current.json', 1), replacement_raw='{broken', transient=0)
        self.assertIsInstance(actual['error'], json.JSONDecodeError)
        self.assertEqual(actual['sleeps'], [])
        self.assertEqual(actual['posts'], 0)
        self.assertIsNone(actual['summary'])


if __name__ == '__main__':
    unittest.main()
