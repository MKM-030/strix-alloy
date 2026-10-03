"""Offline release lifecycle tests; no Docker, WSL, model, or GPU."""
import importlib.util
import sys
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/runner.py'


sys.path.insert(0,str(SOURCE.parent))

class ReleaseRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('halogen0161_release_runner', SOURCE)
        cls.r = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.r)
        cls.r.MACHINE={"distro":"Test-Distro","user":"tester"}
        cls.r.WSL=["wsl-fixture"]

    def test_quiesce_ack_follows_inflight_sample_and_host_frames_continue(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            entered = threading.Event()
            finish = threading.Event()
            frame_after_request = threading.Event()
            frames = []
            valid = {'containerId': 'a'*64, 'guest': {'memory.current': 0,
                     'memory.peak': 0, 'memory.swap.current': 0},
                     'gpuInstances': [{'name': 'gpu', 'dedicatedBytes': 0,
                     'sharedBytes': 0, 'totalCommittedBytes': 0}]}
            class Host:
                def frame(self):
                    frames.append(time.monotonic())
                    if (attempt/'quiesce-request.json').exists():
                        frame_after_request.set()
                    return {'available_bytes': 24*r.GIB, 'commit_headroom_bytes': 98*r.GIB}
            class Startup:
                def validate_target(self, *_): pass
            info = {'State': {'Running': True}}
            def slow_sample(*_):
                entered.set()
                self.assertTrue(finish.wait(30))
                return valid
            result = []
            with patch.object(r, 'guards', return_value=(Startup(), Host())), \
                 patch.object(r, 'inspect', return_value=info), \
                 patch.object(r, 'owned'), patch.object(r, 'sample', side_effect=slow_sample):
                thread = threading.Thread(target=lambda: result.append(
                    r.guard_process({'stage': 'smoke', 'timeout_seconds': 30},
                                    'a'*64, 'owned', attempt)))
                thread.start()
                request = attempt/'quiesce-request.json'
                exit_request = attempt/'guard-exit-request.json'
                record = json.dumps({'schema': 1, 'container_id': 'a'*64})
                try:
                    self.assertTrue(entered.wait(10))
                    request.write_text(record)
                    self.assertTrue(frame_after_request.wait(10))
                    self.assertFalse((attempt/'quiesce-ack.json').exists())
                    self.assertGreaterEqual(len(frames), 2)
                    finish.set()
                    deadline = time.monotonic()+10
                    while not (attempt/'quiesce-ack.json').exists() and time.monotonic()<deadline:
                        time.sleep(.05)
                    self.assertTrue((attempt/'quiesce-ack.json').exists())
                    self.assertTrue(thread.is_alive(), 'host guard must remain active through recovery')
                finally:
                    finish.set()
                    if not request.exists(): request.write_text(record)
                    exit_request.write_text(record)
                    thread.join(12)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, [0])
            self.assertEqual(json.loads((attempt/'quiesce-ack.json').read_text())['container_id'], 'a'*64)

    def test_failed_sampler_records_subprocess_diagnostics(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            failure = subprocess.CompletedProcess(['sampler'], 7, 'stdout detail', 'stderr detail')
            with patch.object(r.subprocess, 'run', return_value=failure):
                with self.assertRaises(RuntimeError):
                    r.sample('a'*64, attempt, 'inference', 19)
            record = json.loads((attempt/'telemetry-0019-process.json').read_text())
            self.assertEqual(record['returncode'], 7)
            self.assertEqual(record['stdout'], 'stdout detail')
            self.assertEqual(record['stderr'], 'stderr detail')
            self.assertLessEqual(record['started_utc'], record['ended_utc'])

    def test_sampler_launch_error_is_retained(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            with patch.object(r.subprocess, 'run', side_effect=OSError('sampler unavailable')):
                with self.assertRaises(OSError):
                    r.sample('a'*64, attempt, 'inference', 20)
            record = json.loads((attempt/'telemetry-0020-process.json').read_text())
            self.assertIn('sampler unavailable', record['failure'])

    def test_quiesce_timeout_fails_closed(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            watcher = type('Watcher', (), {'poll': lambda self: None})()
            with patch.object(r, 'guard_alive'):
                with self.assertRaises(TimeoutError):
                    r.request_quiescence(attempt, 'a'*64, watcher, timeout=0.1)
            self.assertTrue((attempt/'quiesce-request.json').exists())
            self.assertFalse((attempt/'quiesce-ack.json').exists())

    def test_release_marker_requires_clean_guard_terminal_and_recovery(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            for guard_code, errors, expected in [(2, [], False), (0, ['telemetry'], False), (0, [], True)]:
                marker = attempt/'release.json'
                if marker.exists(): marker.unlink()
                with self.assertRaises(RuntimeError) if not expected else self.subTest('clean'):
                    r.commit_release(attempt, cleanup=True, recovery=True,
                                     guard_returncode=guard_code, cleanup_errors=errors,
                                     qualification_passed=True, primary_error=None)
                self.assertEqual(marker.exists(), expected)

    def test_handshake_record_is_invisible_until_complete_and_never_overwrites(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'quiesce-request.json'
            original = r.json.dump
            def interrupted(value, stream, **kwargs):
                stream.write('{')
                stream.flush()
                self.assertFalse(target.exists(), 'partial final JSON became visible')
                original(value, stream, **kwargs)
            with patch.object(r.json, 'dump', side_effect=interrupted):
                r.publish_record(target, {'schema': 1, 'container_id': 'a'*64})
            first = target.read_bytes()
            with self.assertRaises(FileExistsError):
                r.publish_record(target, {'schema': 1, 'container_id': 'b'*64})
            self.assertEqual(target.read_bytes(), first)

    def test_raw_sample_selection_excludes_process_diagnostics(self):
        r = self.r
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory)
            (attempt/'telemetry-0001.json').write_text('{}')
            (attempt/'telemetry-0001-process.json').write_text('{}')
            self.assertEqual([p.name for p in r.raw_samples(attempt)], ['telemetry-0001.json'])

    def test_admission_needs_stable_45_117_window_and_final_frame(self):
        r = self.r
        good = {'available_bytes': 45*r.GIB, 'commit_headroom_bytes': 117*r.GIB}
        class Host:
            def __init__(self, frames): self.frames = iter(frames); self.count = 0
            def frame(self): self.count += 1; return next(self.frames)
        host = Host([good]*61)
        with patch.object(r, 'docker', return_value=''), patch.object(r, 'invoke', return_value='0'), \
             patch.object(r.time, 'sleep'):
            self.assertEqual(r.admission(host), good)
        self.assertEqual(host.count, 61)
        for key in good:
            bad = {**good, key: good[key]-1}
            host = Host([good]*30+[bad]+[good]*30)
            with patch.object(r, 'docker', return_value=''), patch.object(r, 'invoke', return_value='0'), \
                 patch.object(r.time, 'sleep'):
                with self.assertRaises(ValueError): r.admission(host)

    @unittest.skipUnless(__import__('os').name=='nt', 'Windows-only controller lifecycle; exercised on Windows')
    def test_controller_success_and_failed_answer_release_gate(self):
        r = self.r
        cid = 'a'*64
        valid = {'containerId': cid, 'guest': {'memory.current': 0,
                 'memory.peak': 0, 'memory.swap.current': 0},
                 'gpuInstances': [{'name': 'gpu', 'dedicatedBytes': 0,
                 'sharedBytes': 0, 'totalCommittedBytes': 0}]}
        frame = {'available_bytes': 44*r.GIB, 'commit_headroom_bytes': 113*r.GIB}
        class Host:
            def frame(self): return frame
        class Watcher:
            def __init__(self, args, **kwargs):
                attempt = Path(args[args.index('--attempt')+1])
                (attempt/'armed.json').write_text('{}')
            def poll(self): return None
            def wait(self, timeout=None): return 0
            def terminate(self): pass
        terminal = {'State': {'Running': False, 'Pid': 0, 'OOMKilled': False,
                             'Error': '', 'ExitCode': 137}}
        def sample(cid_arg, attempt, phase, index):
            (attempt/f'telemetry-{index:04d}.json').write_text(json.dumps(valid))
            (attempt/f'telemetry-{index:04d}-process.json').write_text('{}')
            return valid
        for fail_answer in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root/'attempts').mkdir()
                replies = iter([{'status': 'ok', 'version': {'api': '0.16.1',
                                'engine': '0.16.1', 'match': True}},
                                {'choices': [{'message': {'content': 'wrong' if fail_answer else '42'}}]},
                                {'choices': [{'message': {'content': 'grün'}}]}])
                immediate_checks = []
                def immediate(host):
                    immediate_checks.append(host)
                    return frame
                def docker(*args, **_):
                    if args[0]=='create':
                        self.assertEqual(len(immediate_checks), 1)
                    if args[0]=='start':
                        self.assertEqual(len(immediate_checks), 2)
                    return cid if args[0]=='create' else ''
                patches = [
                    patch.object(r, 'ARTIFACT_ROOT', root),
                    patch.object(r, 'validate_manifest', return_value=[]),
                    patch.object(r, 'make_seal', return_value={'seal_sha256': 'a'*64}),
                    patch.object(r, 'check_review'), patch.object(r, 'require_trace'),
                    patch.object(r, 'guards', return_value=(None, Host())),
                    patch.object(r, 'admission', return_value=frame),
                    patch.object(r, 'immediate_admission', side_effect=immediate),
                    patch.object(r, 'command', return_value=['create']),
                    patch.object(r, 'docker', side_effect=docker),
                    patch.object(r, 'inspect', return_value={'State': {'Running': True}}),
                    patch.object(r, 'owned'), patch.object(r, 'guard_alive'),
                    patch.object(r, 'http', side_effect=lambda *_: next(replies)),
                    patch.object(r, 'sample', side_effect=sample),
                    patch.object(r, 'request_quiescence'),
                    patch.object(r, 'stop_owned', return_value=terminal),
                    patch.object(r, 'recovered', return_value=True),
                    patch.object(r, 'finish_guard', return_value=0),
                    patch.object(r.subprocess, 'Popen', Watcher),
                    patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')),
                ]
                with ExitStack() as stack:
                    for item in patches: stack.enter_context(item)
                    if fail_answer:
                        with self.assertRaises(ValueError): r.run({'stage':'smoke','timeout_seconds':30}, {}, root/'manifest.json')
                    else:
                        r.run({'stage':'smoke','timeout_seconds':30}, {}, root/'manifest.json')
                attempt = next((root/'attempts').iterdir())
                self.assertEqual((attempt/'release.json').exists(), not fail_answer)
                self.assertEqual((root/'runner.lock').exists(), fail_answer)
                self.assertEqual(json.loads((attempt/'outcome.json').read_text())['passed'], not fail_answer)
                self.assertEqual(len(immediate_checks), 2)


if __name__ == '__main__': unittest.main()
