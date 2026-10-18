"""Offline command contract; no installed state or real collector is used."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import unittest
from unittest.mock import patch, Mock

from gufo_control import service_store, service_ipc, service_lifecycle
import test_service_store
from test_service_lifecycle import installed_harness
from test_telemetry import fixture, NOW, LUID
from gufo_control.telemetry import normalize_snapshot


def module():
    assert importlib.util.find_spec('gufo_control.service'), 'service CLI missing'
    return importlib.import_module('gufo_control.service')


class ServiceTests(unittest.TestCase):
    def fixture(self, *, accepted=False):
        root = self.enterContext(tempfile.TemporaryDirectory())
        f = test_service_store.InstalledStoreTests.fixture(self, root, accepted=accepted)
        self.enterContext(patch.object(service_store, 'PROFILE_PATH', f.profile))
        return f

    def invoke(self, command, f):
        out = io.StringIO()
        with redirect_stdout(out):
            code = module().main([command, '--profile', str(f.profile)])
        return code, json.loads(out.getvalue())

    def test_print_only_and_status_are_read_only_without_admission(self):
        f = self.fixture()
        f.f.pins.evidence.rmdir()
        with patch.object(service_ipc, '_launch_hidden', side_effect=AssertionError('launch')):
            for command in ('print-only', 'status'):
                code, result = self.invoke(command, f)
                self.assertTrue(result['static_valid'], result)
                self.assertFalse(result['persistent_service_qualified'])
                self.assertIsNone(result['admitted'])
                self.assertEqual(result['phase'], 'unknown/stale')
                self.assertIsNone(result['cleanup_confirmed'])
                self.assertFalse(f.f.pins.evidence.exists())

    def test_start_refuses_missing_qualification_and_historical_latch(self):
        f = self.fixture()
        with patch.object(service_ipc, '_launch_hidden') as launch:
            code, result = self.invoke('start', f)
            self.assertEqual(code, 2)
            self.assertIn('persistent_service_unqualified', result['refusals'])
            launch.assert_not_called()
            f.accepted()
            sibling = f.f.root/service_store.smoke_store.PROFILE_ROOTS[service_store.smoke_store.SERVICE_SMOKE]
            sibling.mkdir()
            (sibling/'incomplete.json').write_text('{}')
            code, result = self.invoke('start', f)
            self.assertEqual(code, 2)
            self.assertTrue(any('incomplete' in x for x in result['refusals']))
            launch.assert_not_called()

    def test_public_cli_has_closed_commands_and_private_profile_mapping(self):
        s = module()
        with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
            for args in (['start'], ['start', '--profile', 'wrong'],
                         ['start', '--profile', str(service_store.PROFILE_PATH), '--force'],
                         ['_guardian', '--profile', 'wrong', '--bootstrap', 'x']):
                with self.subTest(args=args):
                    with self.assertRaises(SystemExit): s.main(args)

    def test_terminal_stop_requires_five_recovery_samples_and_is_idempotent(self):
        s = module()
        with installed_harness() as (h, life, bindings, f):
            with patch.object(service_store, 'PROFILE_PATH', f.profile):
                result = h.run(**bindings)
                self.assertTrue(result['success'], result)
                with patch.object(service_ipc, 'control_request', side_effect=AssertionError('IPC')):
                    code, status = self.invoke('stop', f)
                self.assertEqual(code, 0, status)
                self.assertTrue(status['cleanup_confirmed'])
                self.assertEqual(status['recovery_samples'], 5)
                self.assertTrue(status['workers_terminal'])
                bad = deepcopy(result)
                bad['recovery_samples'] = 4
                self.assertFalse(s._terminal_facts(bad)['cleanup_confirmed'])

    def test_guardian_snapshot_is_allowlisted_fresh_and_identity_scoped(self):
        self.assertTrue(hasattr(service_lifecycle, '_snapshot'), 'guardian snapshot missing')
        sample = normalize_snapshot(fixture(), captured_monotonic=100, now_monotonic=101, now_utc=NOW)
        with installed_harness() as (h, life, bindings, f):
            h.run(**bindings)
            h.guard.status_sample = sample
            h.guard.child = None  # Inspect cached observation, not a terminal child.
            h.guard.failures = ['secret child log']
            result = service_lifecycle._snapshot(h.guard, now=101, now_utc=NOW)
            self.assertEqual(result['aggregate_sample']['adapter_luid'], LUID)
            self.assertNotIn('raw', result['aggregate_sample'])
            self.assertNotIn('secret child log', json.dumps(result))
            stale = service_lifecycle._snapshot(h.guard, now=111, now_utc=NOW)
            self.assertEqual(stale['phase'], 'unknown/stale')
            self.assertIsNone(stale['ready'])

    def live_record(self, f):
        """Persist the existing store's real manifest/latch/identity sequence."""
        s = module()
        manifest = f.store.verify_static()
        run = f.f.pins.evidence/'synthetic-run'
        run.mkdir()
        f.store.begin_run(run, manifest, f.f.base)
        child = dict(pid=42, creation_time_100ns=123456, executable=str(f.f.exe))
        guardian = dict(pid=43, creation_time_100ns=654321, executable='python.exe', user_sid='S-test')
        record = dict(run=str(run), run_id='a'*32, profile_digest=service_store._digest(f.value),
            guardian=guardian, child=child, endpoint='\\\\.\\pipe\\gufo-'+'a'*32)
        for name, data in (('owned.json', child), ('control.json', record),
                           ('baseline.json', {'current': {'identity': [LUID, *f.f.base.identity[1:]]}})):
            service_store.operator_store.atomic_json(run/name, data)
        now = datetime.now(timezone.utc)
        raw = fixture()
        for row in raw['counters']: row['timestamp_utc'] = now.isoformat()
        sample = normalize_snapshot(raw, captured_monotonic=time.monotonic(),
            now_monotonic=time.monotonic(), now_utc=now)
        response = dict(state='running', phase='serving_attempt', ready=True, admitted=True,
            handoff_confirmed=True, run=str(run), guardian=guardian, child=child,
            aggregate_sample={k:sample[k] for k in service_lifecycle._AGGREGATE_FIELDS},
            owned_counters=sample['owned_counters'])
        return record, response

    def test_malformed_durable_records_refuse_status_and_stop_without_ipc(self):
        f = self.fixture(accepted=True)
        record, _ = self.live_record(f)
        run = Path(record['run'])
        paths = {'current.json': f.f.pins.evidence/'current.json',
                 'result.json': run/'result.json', 'control.json': run/'control.json',
                 'owned.json': run/'owned.json', 'manifest.json': run/'manifest.json',
                 'identity.json': run/'identity.json'}
        for name, malformed in (('current.json', []), ('current.json', None),
                                ('result.json', [1]), ('control.json', [1]),
                                ('control.json', dict(record, guardian={})),
                                ('control.json', dict(record, endpoint='wrong')),
                                ('owned.json', [1]), ('manifest.json', [1]),
                                ('identity.json', [1])):
            path = paths[name]
            original = path.read_bytes() if path.exists() else None
            with self.subTest(record=name, value=malformed):
                service_store.operator_store.atomic_json(path, malformed)
                try:
                    with patch.object(service_ipc, 'control_request',
                                      side_effect=AssertionError('invalid evidence reached IPC')) as ipc:
                        for command in ('status', 'stop'):
                            code, result = self.invoke(command, f)
                            self.assertEqual(code, 2, result)
                            self.assertEqual(result['phase'], 'unknown/stale')
                            self.assertIsNone(result['cleanup_confirmed'])
                            self.assertIn(command+'_unverified', result['refusals'])
                    ipc.assert_not_called()
                finally:
                    if original is None:
                        path.unlink()
                    else:
                        path.write_bytes(original)

    def test_malformed_baseline_identity_refuses_status_and_stop_before_ipc(self):
        f = self.fixture(accepted=True)
        record, _ = self.live_record(f)
        path = Path(record['run'])/'baseline.json'
        for malformed in ([], None, {'current': []}, {'current': {'identity': []}},
                          {'current': {'identity': [LUID]}},
                          {'current': {'identity': ['wrong']}},
                          {'current': {'identity': [None]}}):
            with self.subTest(baseline=malformed):
                service_store.operator_store.atomic_json(path, malformed)
                with patch.object(service_ipc, 'control_request',
                                  side_effect=AssertionError('invalid baseline reached IPC')) as ipc:
                    for command in ('status', 'stop'):
                        code, result = self.invoke(command, f)
                        self.assertEqual(code, 2, result)
                        self.assertEqual(result['phase'], 'unknown/stale')
                        self.assertIsNone(result['cleanup_confirmed'])
                        self.assertIn(command+'_unverified', result['refusals'])
                ipc.assert_not_called()

    def test_completed_pointer_malformed_records_refuse_public_commands(self):
        f = self.fixture(accepted=True)
        manifest = f.store.verify_static()
        run = f.f.pins.evidence/'completed'; run.mkdir()
        f.store.begin_run(run, manifest, f.f.base)
        f.store.finish_run(run, test_service_store.InstalledStoreTests.clean_result(run, manifest))
        self.assertIn('result_sha256', service_store._read(f.f.pins.evidence/'current.json'))
        for name, malformed in (('identity.json', []), ('identity.json', None),
                                ('manifest.json', []), ('result.json', [])):
            path = run/name
            original = path.read_bytes()
            with self.subTest(record=name, value=malformed):
                service_store.operator_store.atomic_json(path, malformed)
                corrupted = path.read_bytes()
                try:
                    with patch.object(service_ipc, 'control_request',
                                      side_effect=AssertionError('invalid evidence reached IPC')) as ipc:
                        for command in ('status', 'stop'):
                            code, result = self.invoke(command, f)
                            self.assertEqual(code, 2, result)
                            self.assertEqual(result['phase'], 'unknown/stale')
                            self.assertIsNone(result['cleanup_confirmed'])
                            self.assertIn(command+'_unverified', result['refusals'])
                    ipc.assert_not_called()
                    self.assertEqual(path.read_bytes(), corrupted)
                finally:
                    path.write_bytes(original)

    def test_linked_prior_identity_malformed_refuses_public_commands(self):
        f = self.fixture(accepted=True)
        manifest = f.store.verify_static()
        first = f.f.pins.evidence/'first'; first.mkdir()
        f.store.begin_run(first, manifest, f.f.base)
        f.store.finish_run(first, test_service_store.InstalledStoreTests.clean_result(first, manifest))
        second = f.f.pins.evidence/'second'; second.mkdir()
        f.store.begin_run(second, manifest, f.f.base)
        f.store.finish_run(second, test_service_store.InstalledStoreTests.clean_result(second, manifest))
        pointer_path = f.f.pins.evidence/'current.json'
        pointer_before = pointer_path.read_bytes()
        path = first/'identity.json'
        service_store.operator_store.atomic_json(path, [])
        corrupted = path.read_bytes()
        with patch.object(service_ipc, 'control_request',
                          side_effect=AssertionError('invalid history reached IPC')) as ipc:
            for command in ('status', 'stop'):
                code, result = self.invoke(command, f)
                self.assertEqual(code, 2, result)
                self.assertEqual(result['phase'], 'unknown/stale')
                self.assertIsNone(result['cleanup_confirmed'])
                self.assertIn(command+'_unverified', result['refusals'])
        ipc.assert_not_called()
        self.assertEqual(pointer_path.read_bytes(), pointer_before)
        self.assertEqual(path.read_bytes(), corrupted)

    def test_status_verifies_identity_adapter_and_surfaces_transport_uncertainty_once(self):
        f = self.fixture(accepted=True)
        record, response = self.live_record(f)
        for edit in (lambda r: None, lambda r: r['guardian'].update(creation_time_100ns=5),
                     lambda r: r['aggregate_sample'].update(adapter_luid='wrong')):
            value = deepcopy(response)
            edit(value)
            value['cleanup_error'] = 'control_cleanup_incomplete'
            with patch.object(service_ipc, 'control_request', return_value=value) as ipc:
                code, result = self.invoke('status', f)
            self.assertEqual(ipc.call_count, 1)
            if value['guardian'] == record['guardian'] and value['aggregate_sample']['adapter_luid'] == LUID:
                self.assertEqual(code, 0, result)
                self.assertEqual(result['cleanup_error'], 'control_cleanup_incomplete')
                self.assertTrue(result['handoff_confirmed'])
            else:
                self.assertEqual(code, 2)
                self.assertEqual(result['phase'], 'unknown/stale')
                self.assertIsNone(result['ready'])

    def test_live_status_drops_unknown_owned_and_aggregate_fields(self):
        f = self.fixture(accepted=True)
        _, response = self.live_record(f)
        response['aggregate_sample']['private_body'] = 'DO_NOT_EXPOSE'
        response['owned_counters']['private_body'] = 'DO_NOT_EXPOSE'
        with patch.object(service_ipc, 'control_request', return_value=response):
            code, result = self.invoke('status', f)
        self.assertEqual(code, 0, result)
        self.assertNotIn('DO_NOT_EXPOSE', json.dumps(result))

    def test_start_lost_ack_never_relaunches_and_status_resolves_same_run(self):
        f = self.fixture(accepted=True)
        s = module()
        def launch(path):
            record, response = self.live_record(f)
            launch.response = response
            descriptor = json.loads(path.read_text())
            service_store.operator_store.atomic_json(Path(descriptor['record_path']), record)
            service_store.operator_store.atomic_json(Path(record['run'])/'handoff.json', dict(record, state='committed'))
            return Mock(pid=43, poll=lambda: None)
        with patch.object(service_ipc, '_launch_hidden', side_effect=launch) as hidden:
            with patch.object(service_ipc, '_process_identity', return_value=dict(
                pid=43, creation_time_100ns=654321, executable='python.exe', user_sid='S-test')):
                with patch.object(service_ipc, 'control_request', return_value=dict(
                    state='indeterminate', run_id='a'*32, requires_status=True,
                    cleanup_error='control_cleanup_incomplete')) as ipc:
                    code, result = self.invoke('start', f)
            self.assertEqual(code, 2, result)
            self.assertEqual(result['phase'], 'indeterminate')
            self.assertIsNone(result['handoff_confirmed'])
            self.assertTrue(result['requires_status'])
            self.assertEqual(ipc.call_count, 1)
            with patch.object(service_ipc, 'control_request', return_value=launch.response):
                code, actual = self.invoke('status', f)
            self.assertEqual(code, 0, actual)
            self.assertTrue(actual['handoff_confirmed'])
            self.assertEqual(actual['run'], result['run'])
            self.invoke('start', f)
            self.assertEqual(hidden.call_count, 1)

    def test_stop_waits_for_durable_result_without_reconnecting(self):
        f = self.fixture(accepted=True)
        record, response = self.live_record(f)
        s = module()
        terminal = dict(cleanup_confirmed=True, recovery_samples=4, success=True)
        evidence = (record['run'], record, None, True)
        with patch.object(s, '_evidence', side_effect=[evidence, evidence,
             (record['run'], record, terminal, True)]), patch.object(s.time, 'sleep'):
            with patch.object(service_ipc, 'control_request', return_value=dict(
                state='stopping', cleanup_error='control_cleanup_incomplete')) as ipc:
                code, result = self.invoke('stop', f)
        self.assertEqual(code, 2)
        self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(result['recovery_samples'], 4)
        self.assertEqual(ipc.call_count, 1)
        self.assertEqual(result['cleanup_error'], 'control_cleanup_incomplete')

    def test_dead_or_recycled_guardian_does_not_claim_stopped(self):
        f = self.fixture(accepted=True)
        self.live_record(f)
        with patch.object(service_ipc, 'control_request', side_effect=ValueError('peer_identity_mismatch')):
            for command in ('status', 'stop'):
                code, result = self.invoke(command, f)
                self.assertEqual(code, 2)
                self.assertEqual(result['phase'], 'unknown/stale')
                self.assertIsNone(result['cleanup_confirmed'])

    def test_sampler_keeps_one_allowlisted_atomic_observation_and_owned_tuple(self):
        from types import SimpleNamespace
        sample = normalize_snapshot(fixture(), captured_monotonic=100, now_monotonic=101, now_utc=NOW)
        g = SimpleNamespace(identity=None)
        with patch.object(service_lifecycle.telemetry, 'collect_snapshot', return_value=sample) as collect:
            service_lifecycle._install_sampler(g)
            self.assertIs(g.collect(), sample)
            collect.assert_called_once_with(owned=None)
            self.assertNotIn('raw', g.status_sample)
            g.identity = dict(pid=42, creation_time_100ns=123, executable='engine.exe')
            g.collect()
            self.assertEqual(collect.call_args.kwargs['owned'], dict(g.identity, adapter_luid=LUID))
            self.assertIn('owned_counters', g.status_sample)

    def test_successful_start_first_install_and_clean_second_start(self):
        f = self.fixture(accepted=True)
        f.f.pins.evidence.rmdir()
        def launch(path):
            record, _ = self.live_record(f)
            descriptor = json.loads(path.read_text())
            service_store.operator_store.atomic_json(Path(descriptor['record_path']), record)
            return Mock(pid=43, poll=lambda: None)
        with patch.object(service_ipc, '_launch_hidden', side_effect=launch) as hidden, patch.object(
            service_ipc, '_process_identity', return_value=dict(pid=43, creation_time_100ns=654321,
                executable='python.exe', user_sid='S-test')), patch.object(
            service_ipc, 'control_request', return_value=dict(state='committed', cleanup_error='control_cleanup_incomplete')) as ipc:
            code, result = self.invoke('start', f)
        self.assertEqual(code, 0, result)
        self.assertTrue(result['admitted'])
        self.assertTrue(result['ready'])
        self.assertTrue(result['handoff_confirmed'])
        self.assertEqual(hidden.call_count, 1)
        self.assertEqual(ipc.call_count, 1)
        with installed_harness() as (h, life, bindings, clean):
            h.run(**bindings)
            with patch.object(service_store, 'PROFILE_PATH', clean.profile), patch.object(
                service_ipc, '_launch_hidden', side_effect=ValueError('test boundary')) as second:
                self.invoke('start', clean)
            self.assertEqual(second.call_count, 1)

    def test_private_entry_requires_static_gate_before_guardian_construction(self):
        s = module()
        f = self.fixture()
        path = f.f.root/'bootstrap.json'
        path.write_text('{}')
        with patch.object(s.smoke_guard, '_Guardian') as guardian, patch.object(s.ipc, '_run_guardian') as run:
            with self.assertRaises(ValueError):
                s.main(['_guardian', '--profile', service_store.PROFILE_ID, '--bootstrap', str(path)])
        guardian.assert_not_called()
        run.assert_not_called()

    def test_invalid_optional_identity_cannot_erase_valid_aggregate(self):
        from test_telemetry import owned_fixture
        f = self.fixture(accepted=True)
        _, response = self.live_record(f)
        request, raw = owned_fixture()
        owned = service_lifecycle.telemetry._owned_snapshot(raw, request, luid=LUID,
            captured_monotonic=time.monotonic(), now_utc=NOW)
        owned['identity']['creation_time_100ns'] = 999
        response['owned_counters'] = owned
        with patch.object(service_ipc, 'control_request', return_value=response):
            code, result = self.invoke('status', f)
        self.assertEqual(code, 0, result)
        self.assertIsNotNone(result['aggregate_sample'])
        self.assertFalse(result['owned_counters']['available'])
        self.assertIsNone(result['owned_counters']['private_bytes'])

    def test_stale_snapshot_drops_owned_values_as_well_as_readiness(self):
        f = self.fixture(accepted=True)
        _, response = self.live_record(f)
        response.update(aggregate_sample=None, owned_counters={'available':True, 'private_bytes':100})
        with patch.object(service_ipc, 'control_request', return_value=response):
            code, result = self.invoke('status', f)
        self.assertEqual(code, 2)
        self.assertIsNone(result['owned_counters'])

    def test_stopping_unknown_deadline_keeps_terminal_cleanup_unknown(self):
        f = self.fixture(accepted=True)
        self.live_record(f)
        s = module()
        with patch.object(service_ipc, 'control_request', return_value={'state':'stopping'}), patch.object(
            s.time, 'monotonic', side_effect=[100,176]):
            code, result = self.invoke('stop', f)
        self.assertEqual(code, 2)
        self.assertIsNone(result['cleanup_confirmed'])

    def test_hidden_launch_resolves_module_from_fixed_controller_location(self):
        f = self.fixture()
        path = f.f.root/'bootstrap.json'
        parent = dict(pid=1, creation_time_100ns=2, executable='python.exe', user_sid='S-test')
        descriptor = dict(parent=parent, profile_digest='a'*64, record_path=str(f.f.root/'endpoint.json'))
        service_store._exclusive_json(path, descriptor)
        with patch.object(service_ipc, '_validate_descriptor', return_value=Mock()), patch.object(
            service_ipc, '_process_identity', return_value=parent), patch.object(service_ipc.subprocess, 'Popen') as launch:
            service_ipc._launch_hidden(path)
        argv = launch.call_args.args[0]
        self.assertEqual(argv[1:5], ['-m','gufo_control.service','_guardian','--profile'])
        self.assertEqual(argv[5], service_store.PROFILE_ID)
        self.assertEqual(launch.call_args.kwargs['env']['PYTHONPATH'],
            str(Path(service_ipc.__file__).resolve().parents[1]))

    def test_terminal_write_preceding_pointer_and_latch_commit_is_still_pending(self):
        s = module()
        with installed_harness() as (h, life, bindings, f):
            terminal = h.run(**bindings)
            pointer_path = f.f.pins.evidence/'current.json'
            pointer = service_store._read(pointer_path)
            del pointer['result_sha256']
            service_store.operator_store.atomic_json(pointer_path, pointer)
            service_store.operator_store.atomic_json(f.f.pins.evidence/'incomplete.json',
                dict(run=terminal['run'], phase='before_create'))
            _, _, observed, _ = s._evidence(service_store._digest(f.value))
            self.assertIsNone(observed)

    def test_snapshot_checks_retained_child_identity_before_live_claim(self):
        from types import SimpleNamespace
        sample = normalize_snapshot(fixture(), captured_monotonic=100, now_monotonic=101, now_utc=NOW)
        child = Mock()
        child.verify_live_identity.side_effect = ValueError('owned_identity_mismatch')
        g = SimpleNamespace(status_sample=sample, child=child, identity={'pid':42},
            resumed_at=99, exited=False, phase='serving_attempt', ready=True,
            runtime_samples=4, stop_requested=False, failures=[], exit_code=None)
        result = service_lifecycle._snapshot(g, now=101, now_utc=NOW)
        self.assertEqual(result['phase'], 'unknown/stale')
        self.assertIsNone(result['admitted'])

    def test_live_optional_unavailable_never_carries_numeric_values(self):
        f = self.fixture(accepted=True)
        _, response = self.live_record(f)
        response['owned_counters'].update(available=False, private_bytes=123)
        with patch.object(service_ipc, 'control_request', return_value=response):
            code, result = self.invoke('status', f)
        self.assertEqual(code, 0)
        self.assertIsNone(result['owned_counters']['private_bytes'])

    def test_start_rejects_same_pid_with_different_guardian_creation_time(self):
        f = self.fixture(accepted=True)
        def launch(path):
            record, _ = self.live_record(f)
            descriptor = json.loads(path.read_text())
            service_store.operator_store.atomic_json(Path(descriptor['record_path']), record)
            return Mock(pid=43, poll=lambda: None)
        with patch.object(service_ipc, '_launch_hidden', side_effect=launch), patch.object(
            service_ipc, '_process_identity', return_value=dict(pid=43, creation_time_100ns=1,
                executable='python.exe', user_sid='S-test')), patch.object(
            service_ipc, 'control_request', return_value={'state':'committed'}) as ipc:
            code, result = self.invoke('start', f)
        self.assertEqual(code, 2)
        ipc.assert_not_called()


class ServiceWrapperTests(unittest.TestCase):
    """Invoke the native entry points against a temporary, inert service module."""

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = self.root/'app'
        self.app.mkdir()
        source = Path(__file__).resolve().parents[2]/'app'
        for name in ('launch-gufo-flash-next.ps1', 'Launch GUFO Flash Next.cmd'):
            original = source/name
            self.assertTrue(original.is_file(), f'wrapper missing: {original}')
            shutil.copyfile(original, self.app/name)
        package = self.root/'scripts'/'gufo_control'
        package.mkdir(parents=True)
        (package/'__init__.py').write_text('')
        (package/'service.py').write_text(
            'import json, os, sys\n'
            'def main(argv=None):\n'
            '    with open(os.environ["WRAPPER_CAPTURE"], "w") as stream:\n'
            '        json.dump({"argv": argv, "path": sys.path[0]}, stream)\n'
            '    print(json.dumps({"phase": "unknown/stale", "ready": None, "refusals": ["persistent_service_unqualified"]}))\n'
            '    return int(os.environ["WRAPPER_CLI_EXIT"])\n')
        config = self.root/'config'
        config.mkdir()
        self.profile = config/'gufo-service-profile.json'
        self.profile.write_text(json.dumps({'evidence': {
            'runs': str(self.root/'runs'), 'acceptance': str(self.root/'acceptance.json')}}))
        self.capture = self.root/'capture.json'

    def invoke_wrapper(self, *args, cmd=False, cli_exit=0):
        env = dict(os.environ, WRAPPER_CAPTURE=str(self.capture),
                   WRAPPER_CLI_EXIT=str(cli_exit))
        entry = self.app/('Launch GUFO Flash Next.cmd' if cmd else 'launch-gufo-flash-next.ps1')
        argv = (['cmd.exe', '/d', '/c', str(entry)] if cmd else
                ['powershell.exe', '-NoProfile', '-File', str(entry)])
        return subprocess.run(argv + list(args), cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=15)

    def test_four_commands_forward_exact_profile_and_cli_exit(self):
        for command in ('start', 'print-only', 'status', 'stop'):
            with self.subTest(command=command):
                result = self.invoke_wrapper('-Command', command, '-PythonExe', sys.executable,
                                             cli_exit=2)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('persistent_service_unqualified', result.stdout)
                self.assertIn(str(self.root/'acceptance.json'), result.stderr)
                observed = json.loads(self.capture.read_text())
                self.assertEqual(observed['argv'],
                                 [command, '--profile', str(self.profile)])
                self.assertEqual(observed['path'], str(self.root/'scripts'))
                self.capture.unlink()
        result = self.invoke_wrapper('-Command', 'print-only', '-PythonExe', sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.capture.unlink()

    def test_missing_prerequisites_and_unknown_argument_refuse_before_cli(self):
        cases = (
            (('-Command', 'start'), 'PythonExe'),
            (('-Command', 'start', '-PythonExe', str(self.root/'missing-python.exe')), 'PythonExe'),
            (('-Command', 'start', '-PythonExe', sys.executable, '-Extra', 'x'), 'Extra'),
            (('-Command', 'restart', '-PythonExe', sys.executable), 'restart'),
        )
        for args, reason in cases:
            with self.subTest(args=args):
                result = self.invoke_wrapper(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason.lower(), result.stderr.lower())
                self.assertFalse(self.capture.exists())
        self.profile.unlink()
        result = self.invoke_wrapper('-Command', 'start', '-PythonExe', sys.executable)
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(self.profile), result.stderr)
        self.assertFalse(self.capture.exists())
        self.profile.write_text('{}')
        (self.root/'scripts'/'gufo_control'/'service.py').unlink()
        result = self.invoke_wrapper('-Command', 'start', '-PythonExe', sys.executable)
        self.assertEqual(result.returncode, 2)
        self.assertIn('controller', result.stderr.lower())
        self.assertFalse(self.capture.exists())

    def test_cmd_forwards_and_preserves_cli_exit(self):
        result = self.invoke_wrapper('-Command', 'status', '-PythonExe', sys.executable,
                                     cmd=True, cli_exit=2)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text())['argv'],
                         ['status', '--profile', str(self.profile)])


if __name__ == '__main__': unittest.main()
