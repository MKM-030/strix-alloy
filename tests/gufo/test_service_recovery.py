"""Offline tests for the exact service smoke late recovery disposition."""
import importlib.util
from contextlib import ExitStack, contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control.operator_policy import Frame, GIB, MIB


class ServiceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gufo_control import service_recovery
        cls.d = service_recovery

    def test_recovery_command_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.service_recovery'))

    def test_pins_bind_exact_original_failed_service_result(self):
        d = self.d
        result = d.read_pinned(d.RUN/'result.json', d.RESULT_SHA)
        d.validate_result(result)
        pins, profile, current, strict = d.policy_inputs(result)
        self.assertEqual(pins, d.service_smoke_store.PINS)
        self.assertEqual(result['manifest']['source'], pins.source_commit)
        self.assertEqual(current.available_min, result['current_baseline']['available_min'])
        self.assertEqual(strict.available_min, result['runtime_baseline']['available_min'])
        for key in d.TERMINAL_FLAGS:
            changed = dict(result, **{key: False})
            with self.subTest(key=key), self.assertRaises(ValueError):
                d.validate_result(changed)
        for key, value in (('profile', 'other'), ('failure', 'none'),
                           ('recovery_samples', 4), ('exit_code', 1),
                           ('success', True), ('cleanup_confirmed', True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                d.validate_result(dict(result, **{key: value}))
        with self.assertRaises(ValueError):
            d.policy_inputs(dict(result, runtime_baseline=result['original_baseline']))
        wrong = json.loads(json.dumps(result))
        wrong['manifest']['source'] = '0'*40
        with self.assertRaises(ValueError):
            d.policy_inputs(wrong)
        wrong = json.loads(json.dumps(result))
        wrong['manifest']['service']['source_tree'] = '0'*40
        with self.assertRaises(ValueError):
            d.policy_inputs(wrong)

    @contextmanager
    def isolated(self):
        d = self.d
        source = d.read_pinned(d.RUN/'result.json', d.RESULT_SHA)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)/'profile'; root.mkdir()
            run = root/'run'; run.mkdir()
            operator = Path(folder)/'operator'; operator.mkdir()
            paths = dict(ROOT=root, RUN=run, LATCH=root/'incomplete.json',
                ATTEMPT=root/'attempt.json', ARCHIVE=run/'late-recovery-original-incomplete.json',
                CERTIFICATE=run/'late-recovery-certificate.json',
                TELEMETRY=run/'late-recovery-telemetry.jsonl',
                AUDIT_ATTEMPT=run/'late-recovery-attempt.json')
            for name, path in paths.items():
                stack.enter_context(patch.object(d, name, path))
            stack.enter_context(patch.object(d.operator_store, 'EVIDENCE', operator))
            source['run'] = str(run)
            result_bytes = (json.dumps(source, sort_keys=True)+'\n').encode()
            (run/'result.json').write_bytes(result_bytes)
            latch_bytes = (json.dumps(dict(run=str(run), original_baseline=source['original_baseline']))+'\n').encode()
            d.LATCH.write_bytes(latch_bytes)
            attempt_bytes = (json.dumps(dict(run=str(run), profile=d.PROFILE_ID))+'\n').encode()
            d.ATTEMPT.write_bytes(attempt_bytes)
            for name, data in (('RESULT_SHA', result_bytes), ('LATCH_SHA', latch_bytes),
                               ('ATTEMPT_SHA', attempt_bytes)):
                stack.enter_context(patch.object(d, name, hashlib.sha256(data).hexdigest().upper()))
            state = {'now': 120000., 'queries': 0, 'variant': None, 'port': 0, 'pid': 0}
            epoch = datetime(2026, 9, 27, tzinfo=timezone.utc)
            class Date(datetime):
                @classmethod
                def now(cls, tz=None):
                    return epoch+timedelta(seconds=state['now'])
            def sleep(seconds):
                state['now'] += max(0, seconds)
            stack.enter_context(patch.object(d.time, 'monotonic', lambda: state['now']))
            stack.enter_context(patch.object(d.time, 'sleep', sleep))
            stack.enter_context(patch.object(d, 'datetime', Date))
            def snapshot(start):
                base = source['current_baseline']; ident = base['identity']
                stamp = (epoch+timedelta(seconds=start)).isoformat()
                s = dict(available_physical_bytes=max(49*GIB, base['available_min']-GIB),
                    host_committed_bytes=base['committed_max'], host_commit_limit_bytes=240*GIB,
                    dedicated_capacity_bytes=ident[6], adapter_dedicated_bytes=base['gpu_max'][0],
                    adapter_shared_bytes=base['gpu_max'][1],
                    adapter_total_committed_bytes=base['gpu_max'][2], adapter_luid=ident[0],
                    adapter_identity=dict(luid=ident[0], vendor_id=ident[1], device_id=ident[2],
                        subsystem_id=ident[3], flags=ident[4], description=ident[5],
                        dedicated_video_memory=ident[6]), captured_monotonic=start,
                    sample_utc_min=stamp, sample_utc_max=stamp, telemetry_ok=True,
                    provider='PDH/Get-Counter;DXGI/EnumAdapters1', gpu_scope='adapter_aggregate',
                    host_scope='host_global', inventory_scope='known_engine_and_guest_names',
                    other_inference_pids=[], raw=dict(processes=[]))
                variant = state['variant']; n = state['queries']
                if variant == 'physical': s['available_physical_bytes'] = 49*GIB-1
                if variant == 'stale': s['captured_monotonic'] -= 10
                if variant == 'malformed': del s['host_committed_bytes']
                if variant == 'adapter': s['adapter_identity']['luid'] = 'unknown'
                if variant == 'inference': s['other_inference_pids'] = [42]
                if variant == 'raw_pid': s['raw']['processes'] = [dict(pid=d.IDENTITY['pid'])]
                if variant == 'commit': s['host_committed_bytes'] += 512*MIB+1
                if variant == 'gpu': s['adapter_shared_bytes'] += 256*MIB+1
                if variant == 'rising': s['host_committed_bytes'] += n*1024
                s['commit_headroom_bytes'] = s['host_commit_limit_bytes']-s.get('host_committed_bytes', 0)
                return s
            class Query:
                def __init__(self, collect):
                    state['queries'] += 1
                    self.started = state['now']
                    self.done = self
                def is_set(self):
                    return state['variant'] != 'nonterminal'
                def poll(self):
                    if state['variant'] == 'timeout':
                        state['now'] += 2.01
                        raise TimeoutError('active_query_timeout')
                    state['now'] += .1
                    return Frame(snapshot(self.started), self.started, state['now'], Date.now())
            stack.enter_context(patch.object(d, 'Query', Query))
            stack.enter_context(patch.object(d, 'require_pid_absent', side_effect=lambda: (_ for _ in ()).throw(ValueError('pid_reused')) if state['pid'] else None))
            stack.enter_context(patch.object(d, 'check_port', side_effect=lambda: (_ for _ in ()).throw(OSError('occupied')) if state['port'] else None))
            output = io.StringIO()
            stack.enter_context(redirect_stdout(output))
            yield state, output

    def test_success_is_bounded_and_preserves_failed_source(self):
        with self.isolated() as (state, output):
            d = self.d
            before_result = (d.RUN/'result.json').read_bytes()
            before_attempt = d.ATTEMPT.read_bytes()
            before_latch = d.LATCH.read_bytes()
            d.main()
            self.assertEqual(state['queries'], 5)
            self.assertEqual((d.RUN/'result.json').read_bytes(), before_result)
            self.assertEqual(d.ATTEMPT.read_bytes(), before_attempt)
            self.assertEqual(d.ARCHIVE.read_bytes(), before_latch)
            self.assertFalse(d.LATCH.exists())
            self.assertFalse((d.operator_store.EVIDENCE/'incomplete.json').exists())
            certificate = json.loads(d.CERTIFICATE.read_bytes())
            self.assertEqual(certificate['meaning'], 'present_recovery_observed_later')
            self.assertTrue(certificate['original_run_still_failed'])
            self.assertTrue(certificate['original_recovery_deadline_not_certified'])
            self.assertEqual(len(certificate['frames']), 5)
            self.assertEqual(len(d.TELEMETRY.read_text().splitlines()), 5)
            self.assertFalse(json.loads(output.getvalue())['launch_performed'])

    def test_failed_windows_keep_recognized_original_blocker(self):
        for variant in ('physical', 'stale', 'malformed', 'adapter', 'inference',
                        'raw_pid', 'commit', 'gpu', 'rising', 'timeout', 'nonterminal'):
            with self.subTest(variant=variant), self.isolated() as (state, _):
                state['variant'] = variant
                with self.assertRaises((ValueError, TimeoutError)):
                    self.d.main()
                self.assertTrue(self.d.LATCH.exists())
                self.assertFalse(self.d.ARCHIVE.exists())
                self.assertTrue(self.d.AUDIT_ATTEMPT.exists())
                before = state['queries']
                with self.assertRaisesRegex(ValueError, 'prior_disposition'):
                    self.d.main()
                self.assertEqual(state['queries'], before)

    def test_preflight_refuses_pid_port_and_existing_artifacts(self):
        for condition in ('pid', 'port', 'prior'):
            with self.subTest(condition=condition), self.isolated() as (state, _):
                if condition == 'prior': self.d.CERTIFICATE.write_text('{}')
                else: state[condition] = 1
                with self.assertRaises((ValueError, OSError)):
                    self.d.main()
                self.assertEqual(state['queries'], 0)
                self.assertTrue(self.d.LATCH.exists())

    def test_changed_pinned_bytes_refuse_before_observation(self):
        for name in ('result', 'latch', 'attempt'):
            with self.subTest(name=name), self.isolated() as (state, _):
                path = dict(result=self.d.RUN/'result.json', latch=self.d.LATCH,
                            attempt=self.d.ATTEMPT)[name]
                path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaises(ValueError): self.d.main()
                self.assertEqual(state['queries'], 0)

    def test_certificate_and_archive_failures_retain_blocker(self):
        for phase in ('certificate', 'after_rename', 'restore', 'rename'):
            with self.subTest(phase=phase), self.isolated() as (state, _):
                d = self.d
                if phase == 'certificate':
                    original = d.write_new
                    def fail_write(path, value):
                        if path == d.CERTIFICATE: raise OSError('write failed')
                        return original(path, value)
                    context = patch.object(d, 'write_new', side_effect=fail_write)
                elif phase == 'after_rename':
                    original = d.read_pinned
                    def fail_read(path, digest):
                        if path == d.ARCHIVE: raise OSError('archive read failed')
                        return original(path, digest)
                    context = patch.object(d, 'read_pinned', side_effect=fail_read)
                else:
                    original = d.os.rename
                    calls = [0]
                    def fail_rename(src, dst):
                        calls[0] += 1
                        if phase == 'rename' or calls[0] == 2:
                            raise OSError('rename failed')
                        return original(src, dst)
                    if phase == 'restore':
                        original_read = d.read_pinned
                        def fail_archive(path, digest):
                            if path == d.ARCHIVE: raise OSError('archive read failed')
                            return original_read(path, digest)
                        stack = ExitStack()
                        stack.enter_context(patch.object(d, 'read_pinned', side_effect=fail_archive))
                        stack.enter_context(patch.object(d.os, 'rename', side_effect=fail_rename))
                        context = stack
                    else:
                        context = patch.object(d.os, 'rename', side_effect=fail_rename)
                with context, self.assertRaises(OSError): d.main()
                self.assertTrue(d.LATCH.exists() or (d.operator_store.EVIDENCE/'incomplete.json').exists())
                if phase in ('after_rename', 'restore', 'rename'):
                    self.assertTrue((d.operator_store.EVIDENCE/'incomplete.json').exists())
                if phase == 'restore':
                    self.assertFalse(d.LATCH.exists())
                    self.assertTrue(d.ARCHIVE.exists())

    def test_state_change_before_archive_keeps_original_latch(self):
        with self.isolated() as (state, _):
            d = self.d
            original = d.require_pid_absent
            checks = [0]
            def changed():
                checks[0] += 1
                if checks[0] == 3:
                    raise ValueError('pid_reused_before_archive')
                return original()
            with patch.object(d, 'require_pid_absent', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'pid_reused_before_archive'):
                    d.main()
            self.assertEqual(state['queries'], 5)
            self.assertTrue(d.LATCH.exists())
            self.assertFalse(d.ARCHIVE.exists())
            self.assertTrue(d.CERTIFICATE.exists())


if __name__ == '__main__':
    unittest.main()
