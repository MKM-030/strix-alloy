"""Offline lifecycle tests; all process, guest-clock, and memory inputs are fake."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import service as s


class Process:
    def __init__(self, ready, code=None, timeouts=0):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(ready)
        self.code, self.timeouts = code, timeouts
        self.waits, self.terminated, self.killed = 0, False, False

    def poll(self): return self.code

    def wait(self, timeout):
        self.waits += 1
        if self.timeouts:
            self.timeouts -= 1
            raise subprocess.TimeoutExpired('fake-wsl', timeout)
        if self.code is None: self.code = 0
        return self.code

    def terminate(self): self.terminated = True
    def kill(self): self.killed = True


class AdmissionKeepaliveTests(unittest.TestCase):
    def keeper(self, process):
        self.assertTrue(hasattr(s, 'AdmissionKeepalive'), 'Service lacks owned guest keepalive')
        with patch.object(s.subprocess, 'Popen', return_value=process):
            keeper = s.AdmissionKeepalive(['fake-wsl', '--exec'], 'test-run', 900)
        keeper.arm()
        return keeper

    def test_only_a_running_ready_guest_can_back_admission(self):
        process = Process('test-run\n')
        keeper = self.keeper(process)
        keeper.check()
        for code in (0, 124, -15):
            process.code = code
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, 'keepalive stopped'):
                keeper.check()
        keeper.close()

    def test_wrong_guest_identity_cannot_arm(self):
        process = Process('other-run\n')
        self.assertTrue(hasattr(s, 'AdmissionKeepalive'), 'Service lacks owned guest keepalive')
        with patch.object(s.subprocess, 'Popen', return_value=process):
            keeper = s.AdmissionKeepalive(['fake-wsl'], 'test-run', 900)
            with self.assertRaisesRegex(RuntimeError, 'keepalive did not arm'):
                keeper.arm()
        keeper.close()
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertEqual(process.waits, 1)

    def test_close_reaps_proxy_even_when_graceful_and_terminate_waits_expire(self):
        process = Process('test-run\n', timeouts=2)
        keeper = self.keeper(process)
        keeper.close()
        keeper.close()
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(process.waits, 3)

    def test_successful_handoff_requires_a_zero_eof_exit(self):
        for code, timeouts in ((0, 0), (124, 0), (0, 2)):
            process = Process('test-run\n', timeouts=timeouts)
            keeper = self.keeper(process)
            process.code = code
            with self.subTest(code=code, timeouts=timeouts):
                if code or timeouts:
                    with self.assertRaisesRegex(RuntimeError, 'did not release cleanly'):
                        keeper.close(require_clean=True)
                else:
                    keeper.close(require_clean=True)
                self.assertTrue(keeper.closed)

    def test_guest_exits_on_eof_or_its_finite_deadline_without_children(self):
        self.assertTrue(hasattr(s, 'ADMISSION_KEEPALIVE'), 'Service lacks bounded guest program')
        import os
        import select
        for eof, expected in ((True, 0), (False, 124)):
            clock = iter((0, 0, 0, 901))
            with self.subTest(eof=eof), patch.object(sys, 'argv', ['keeper', '900', 'test-run']), \
                 patch.object(s.time, 'monotonic', side_effect=lambda: next(clock)), \
                 patch.object(select, 'select', return_value=([sys.stdin] if eof else [], [], [])), \
                 patch.object(os, 'read', return_value=b''), \
                 patch.object(subprocess, 'Popen', side_effect=AssertionError('Guest spawned a child')), \
                 redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as raised:
                    exec(s.ADMISSION_KEEPALIVE, {})
                self.assertEqual(raised.exception.code, expected)
                self.assertEqual(output.getvalue(), 'test-run\n')

    def test_admission_aborts_before_sampling_when_keeper_dies(self):
        self.assertTrue(hasattr(s, 'AdmissionKeepalive'), 'Service lacks owned guest keepalive')
        host = Mock()
        keeper = Mock()
        keeper.check.side_effect = RuntimeError('keepalive stopped (exit=0)')
        with patch.object(s.r, 'exclusive_host'), patch.object(s.time, 'monotonic', return_value=0):
            with self.assertRaisesRegex(RuntimeError, 'keepalive stopped'):
                s.admission(host, 262144, threading.Event(), Mock(), 'v2', keepalive=keeper)
        host.frame.assert_not_called()

    def test_admission_error_reaps_service_owned_keeper_and_records_cleanup(self):
        processes = []
        def popen(args, **kwargs):
            self.assertEqual(args[:2], ['fake-wsl', '--exec'])
            self.assertEqual(args[2:5], ['python3', '-u', '-c'])
            self.assertGreater(float(args[-2]), 240)
            self.assertLessEqual(float(args[-2]), 4200)
            process = Process(args[-1] + '\n')
            processes.append(process)
            return process
        def reject(host, context, stop, log, checkpoint, *, keepalive=None):
            self.assertIsNotNone(keepalive, 'Admission ran without a guest owner')
            keepalive.check()
            raise ValueError('offline admission rejected')
        outcome, locked = self.run_service(popen, reject)
        self.assertEqual(len(processes), 1)
        self.assertTrue(processes[0].stdin.closed)
        self.assertTrue(processes[0].stdout.closed)
        self.assertEqual(processes[0].waits, 1)
        self.assertEqual((outcome['ready'], outcome['cleanup'], outcome['recovery']), (False, True, True))
        self.assertIn('offline admission rejected', outcome['error'])
        self.assertFalse(locked)

    def test_failed_arming_cleanup_preserves_owner_and_lock(self):
        class FailedCleanup(Process):
            def wait(self, timeout):
                self.waits += 1
                raise RuntimeError('proxy could not be reaped')
        process = FailedCleanup('wrong-run\n')
        outcome, locked = self.run_service(lambda *_args, **_kwargs: process, Mock())
        self.assertFalse(outcome['ready'])
        self.assertFalse(outcome['cleanup'])
        self.assertIn('keepalive did not arm', outcome['error'])
        self.assertIn('proxy could not be reaped', outcome['error'])
        self.assertTrue(locked)
        self.assertGreaterEqual(process.waits, 2)

    def run_service(self, popen, reject):
        machine = {'distro': 'fake', 'user': 'fake', 'models': 'fake', 'dxg': 'fake'}
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            local = Path(directory)
            (local/'entrypoint-wsl.sh').write_bytes(b'offline-entrypoint')
            replacements = [
                patch.object(s, 'LOCAL', local), patch.object(s, 'STATE_PATH', local/'current-service.json'),
                patch.object(s, 'TOKEN_PATH', local/'api-token.txt'), patch.object(s.r, 'configure'),
                patch.object(s.r, 'MACHINE', machine), patch.object(s.r, 'WSL', ['fake-wsl', '--exec']),
                patch.object(s.portable, 'preflight', return_value=machine), patch.object(s, 'verify_checkpoint'),
                patch.object(s, 'token', return_value='offline-test-secret'), patch.object(s.portable, 'check_hash'),
                patch.object(s, 'logger', return_value=Mock()), patch.object(s, 'service_entrypoint', return_value=b'fake'),
                patch.object(s, 'build_manifest', return_value={}), patch.object(s.r, 'load_module', return_value=Mock()),
                patch.object(s, 'admission', side_effect=reject), patch.object(s.subprocess, 'Popen', side_effect=popen),
                patch.object(s.signal, 'signal'),
            ]
            for replacement in replacements: stack.enter_context(replacement)
            self.assertEqual(s.serve(s.options(['--checkpoint', 'v2', '--context-size', '262144'])), 2)
            attempt = next((local/'services').iterdir())
            outcome = json.loads((attempt/'outcome.json').read_text())
            return outcome, (local/'runner.lock').exists()


if __name__ == '__main__': unittest.main()
