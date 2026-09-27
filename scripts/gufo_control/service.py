"""Closed installed service CLI. Only start may create the existing guardian."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time

from . import service_store as store, service_ipc as ipc
from . import service_lifecycle as lifecycle, smoke_guard
from .benchmark_runtime import BoundPolicy


def _base(profile):
    inspection = store.inspect_installed_profile(profile)
    identity = inspection['identity']
    return dict(profile=store.PROFILE_ID, static_valid=inspection['artifacts_valid'],
        persistent_service_qualified=inspection['qualified'], refusals=inspection['refusals'],
        admitted=None, phase='unknown/stale', ready=None, handoff_confirmed=None,
        guardian=None, child=None, endpoint=identity['endpoint'],
        profile_digest=store._digest(identity),
        runtime_digest=identity['runtime']['executable_sha256'],
        runtime_policy_digest=identity['runtime']['policy_sha256'],
        aggregate_sample=None, owned_counters=None, stop_reason=None,
        child_exit=None, workers_terminal=None, cleanup_confirmed=None)


def _terminal_facts(result):
    clean = store._clean(result)
    return dict(phase='stopped' if clean else 'terminal_unresolved', ready=False,
        admitted=result.get('resumed_monotonic') is not None,
        child=result.get('identity'), child_exit=result.get('exit_code'),
        cleanup_confirmed=clean,
        workers_terminal=all(result.get(k) is True for k in
            ('collector_terminal', 'collector_cleanup_confirmed', 'http_terminal',
             'inspection_terminal', 'inspection_duplicate_closed')),
        recovery_samples=result.get('recovery_samples'),
        stop_reason='stop_requested' if result.get('stop_requested') else 'guardian_failure')


def _object(value, name):
    if type(value) is not dict:
        raise ValueError(f'{name}_invalid')
    return value


def _baseline_luid(run):
    baseline = _object(store._read(run/'baseline.json'), 'baseline')
    current = _object(baseline.get('current'), 'baseline_current')
    identity = current.get('identity')
    if (type(identity) is not list or len(identity) != 7
            or type(identity[0]) is not str
            or re.fullmatch(r'0x[0-9a-f]{8}_0x[0-9a-f]{8}', identity[0]) is None
            or any(type(value) is not int for value in identity[1:5])
            or type(identity[5]) is not str or type(identity[6]) is not int):
        raise ValueError('baseline_identity_invalid')
    return identity[0]


def _process_identity(value, *, guardian=False):
    if (type(value) is not dict
            or any(type(value.get(key)) is not int or value[key] <= 0
                   for key in ('pid', 'creation_time_100ns'))
            or type(value.get('executable')) is not str or not value['executable']
            or (guardian and (type(value.get('user_sid')) is not str
                              or not value['user_sid']))):
        raise ValueError('control_identity_invalid')


def _evidence(profile_digest, *, expected_run=None):
    """Read only the exact installed pointer/manifest chain and its bound control."""
    root = store.PINS.evidence
    pointer = _object(store._read(root/'current.json'), 'installed_current')
    if (pointer.get('profile') != store.PROFILE_ID
            or type(pointer.get('run')) is not str
            or type(pointer.get('identity_sha256')) is not str):
        raise ValueError('installed_current_invalid')
    run = store._run_path(store.PINS, pointer['run'])
    if expected_run is not None and str(run) != expected_run:
        raise ValueError('run_changed')
    manifest = _object(store._read(run/'manifest.json'), 'installed_manifest')
    identity = _object(store._read(run/'identity.json'), 'installed_identity')
    if (identity.get('run') != str(run) or identity.get('profile') != store.PROFILE_ID
            or identity.get('manifest_sha256') != store._digest(manifest)
            or pointer.get('identity_sha256') != store._digest(identity)
            or type(manifest.get('installed_profile')) is not dict
            or type(manifest.get('executable')) is not str
            or store._digest(manifest['installed_profile']) != profile_digest):
        raise ValueError('installed_current_identity_invalid')
    result = None
    if (run/'result.json').exists():
        result = _object(store._read(run/'result.json'), 'installed_result')
        if (result.get('run') != str(run) or result.get('profile') != store.PROFILE_ID
                or result.get('manifest') != manifest):
            raise ValueError('installed_result_invalid')
        if store._clean(result):
            if 'result_sha256' not in pointer or (root/'incomplete.json').exists():
                result = None  # finish_run has not committed all terminal evidence.
            else:
                store._prior_run(store.PINS)
    record_path = run/'control.json'
    record = _object(store._read(record_path), 'control_record') if record_path.exists() else None
    if record is not None:
        child = _object(store._read(run/'owned.json'), 'owned_identity')
        _process_identity(record.get('guardian'), guardian=True)
        _process_identity(record.get('child'))
        _process_identity(child)
        run_id = record.get('run_id')
        if (record.get('run') != str(run) or record.get('profile_digest') != profile_digest
                or type(run_id) is not str or re.fullmatch(r'[0-9a-f]{32}', run_id) is None
                or record.get('endpoint') != r'\\.\pipe\gufo-'+run_id
                or record.get('child') != child or child.get('executable') != manifest['executable']):
            raise ValueError('control_evidence_mismatch')
        _baseline_luid(run)
    handoff = False
    if record is not None and (run/'handoff.json').exists():
        handoff = _object(store._read(run/'handoff.json'), 'handoff_evidence') == dict(record, state='committed')
        if not handoff: raise ValueError('handoff_evidence_mismatch')
    return str(run), record, result, handoff


def _live(result, record, response):
    if (response.get('run') != record['run'] or response.get('guardian') != record['guardian']
            or response.get('child') != record['child']):
        raise ValueError('status_identity_mismatch')
    sample = response.get('aggregate_sample')
    if sample is not None:
        if (sample.get('adapter_luid') != _baseline_luid(Path(record['run']))
                or not lifecycle._fresh(sample, time.monotonic(), datetime.now(timezone.utc))):
            raise ValueError('status_sample_stale_or_wrong_adapter')
        sample = {k: sample[k] for k in lifecycle._AGGREGATE_FIELDS}
        if (sample['provider'] not in lifecycle.telemetry.ALLOWED_PROVIDERS
                or sample['gpu_scope'] != 'adapter_aggregate' or sample['host_scope'] != 'host_global'):
            raise ValueError('status_scope_invalid')
        for key in lifecycle._AGGREGATE_FIELDS[7:]:
            lifecycle.telemetry.integer(sample[key], key)
    owned = lifecycle._owned_public(response.get('owned_counters')) if sample is not None else None
    if owned and owned['available'] is True:
        try:
            lifecycle.telemetry._owned_identity(record['child'], owned['identity'])
            if (owned['adapter_luid'] != sample['adapter_luid']
                    or not lifecycle._fresh(owned, time.monotonic(), datetime.now(timezone.utc))):
                raise ValueError('status_owned_scope_invalid')
            for key in lifecycle.telemetry.OWNED_FIELDS:
                lifecycle.telemetry.integer(owned[key], key)
        except (ValueError, KeyError, TypeError):
            owned.update(available=False, reason='owned_sample_invalid_or_stale',
                **dict.fromkeys(lifecycle.telemetry.OWNED_FIELDS))
    result.update({k: response[k] for k in ('phase', 'ready', 'admitted',
        'handoff_confirmed', 'stop_reason',
        'child_exit', 'workers_terminal', 'cleanup_confirmed', 'admission_scope',
        'runtime_observed_samples', 'aggregate_validation', 'snapshot_monotonic',
        'snapshot_utc') if k in response})
    result.update(aggregate_sample=sample, owned_counters=owned)
    if sample is None:
        result.update(phase='unknown/stale', ready=None, admitted=None)
    if response.get('cleanup_error'):
        result['cleanup_error'] = 'control_cleanup_incomplete'


def _status(result, *, stop=False):
    try:
        run, record, terminal, handoff = _evidence(result['profile_digest'])
        result.update(run=run, handoff_confirmed=handoff)
        if record:
            result.update(guardian=record['guardian'], child=record['child'])
        if terminal is not None:
            result.update(_terminal_facts(terminal))
            return 0 if result['cleanup_confirmed'] else 2
        if record is None: raise ValueError('control_record_missing')
        response = ipc.control_request(record, 'stop' if stop else 'status', timeout_seconds=2)
        if response.get('cleanup_error'):
            result['cleanup_error'] = 'control_cleanup_incomplete'
        if not stop:
            _live(result, record, response)
            return 0 if result['phase'] != 'unknown/stale' else 2
        if response.get('state') != 'stopping': raise ValueError('stop_not_acknowledged')
        if response.get('cleanup_error'):
            result['cleanup_error'] = 'control_cleanup_incomplete'
        # Never allocate more IPC connections; receipt is not terminal cleanup.
        deadline = time.monotonic()+75
        while time.monotonic() < deadline:
            _, _, terminal, handoff = _evidence(result['profile_digest'], expected_run=run)
            if terminal is not None:
                result.update(_terminal_facts(terminal), handoff_confirmed=handoff)
                return 0 if result['cleanup_confirmed'] else 2
            time.sleep(.1)
        raise ValueError('stop_terminal_unconfirmed')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        result['refusals'].append('stop_unverified' if stop else 'status_unverified')
        return 2


def _start(profile, result):
    if not result['static_valid'] or not result['persistent_service_qualified']:
        return 2
    try:
        # Provision only the exact absent installed root, after independent gates.
        store.smoke_store._incomplete_latches(store.PINS)
        if not store.PINS.evidence.exists():
            store._candidate(profile, store.PINS)
            anchor, _ = store._anchor(store._read(profile))
            store._acceptance(store._read(profile), store.PINS, anchor)
            store.PINS.evidence.mkdir()
        installed = store.InstalledStore(profile)
        manifest = installed.verify_static()
        result['refusals'] = []
        with tempfile.TemporaryDirectory(prefix='gufo-bootstrap-') as temp:
            descriptor_path = Path(temp)/'bootstrap.json'
            descriptor = dict(parent=ipc._process_identity(os.getpid()),
                profile_digest=store._digest(manifest['installed_profile']),
                record_path=str(Path(temp)/'endpoint.json'))
            store._exclusive_json(descriptor_path, descriptor)
            process = ipc._launch_hidden(descriptor_path)
            deadline = time.monotonic()+490
            while not Path(descriptor['record_path']).exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError('guardian_bootstrap_unconfirmed')
                time.sleep(.05)
            record = store._read(descriptor['record_path'])
            run, bound, _, _ = _evidence(result['profile_digest'], expected_run=record.get('run'))
            if bound != record or record['guardian']['pid'] != process.pid:
                raise ValueError('guardian_bootstrap_identity_mismatch')
            # poll() uses Popen's retained process handle. Bracket the independent
            # identity open so a dead/recycled PID cannot replace our launcher.
            if process.poll() is not None: raise ValueError('guardian_exited')
            ipc._match_identity(record['guardian'], ipc._process_identity(process.pid))
            if process.poll() is not None: raise ValueError('guardian_exited')
            response = ipc.control_request(record, 'handoff', timeout_seconds=max(.01, deadline-time.monotonic()))
            result.update(run=run, run_id=record['run_id'], guardian=record['guardian'], child=record['child'],
                handoff_confirmed=True if response.get('state') == 'committed' else None,
                admitted=True if response.get('state') == 'committed' else None,
                ready=True if response.get('state') == 'committed' else None,
                phase=response.get('state'), requires_status=response.get('state') == 'indeterminate')
            if response.get('cleanup_error'):
                result['cleanup_error'] = 'control_cleanup_incomplete'
            # Lost ACK requires explicit exact-run status; never retry or relaunch.
            return 0 if response.get('state') == 'committed' else 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        result['refusals'].append('start_unverified')
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fixed installed GUFO service')
    parser.add_argument('command', choices=('start', 'print-only', 'status', 'stop', '_guardian'))
    parser.add_argument('--profile', required=True)
    parser.add_argument('--bootstrap', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command == '_guardian':
        if args.profile != store.PROFILE_ID or not args.bootstrap:
            parser.error('invalid private guardian binding')
        path = Path(args.bootstrap)
        if not path.is_absolute() or path.name != 'bootstrap.json':
            parser.error('invalid bootstrap path')
        ipc._reject_reparse(path)
        descriptor = ipc._decode(path.read_bytes())
        installed = store.InstalledStore(store.PROFILE_PATH)
        installed.verify_static()
        guardian = smoke_guard._Guardian(store=installed,
            policy_module=BoundPolicy(store.PINS), profile_id=store.PROFILE_ID,
            argv_builder=lambda key: store.installed_argv(store.PINS, key))
        lifecycle._install_sampler(guardian)
        result = ipc._run_guardian(guardian, descriptor)
        return 0 if result['success'] else 2
    if args.bootstrap or Path(args.profile).resolve() != store.PROFILE_PATH.resolve():
        parser.error('exact installed profile path required')
    result = _base(Path(args.profile))
    if args.command == 'print-only':
        code = 0 if result['static_valid'] else 2
    elif args.command == 'start':
        code = _start(Path(args.profile), result)
    else:
        code = _status(result, stop=args.command == 'stop')
    print(json.dumps(result, allow_nan=False))
    return code


if __name__ == '__main__': raise SystemExit(main())
