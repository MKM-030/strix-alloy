"""Closed installed GUFO candidate with separate, currently absent service acceptance.

Inspection is read only. A future independent review must pin ACCEPTANCE_SHA256
before any installed start can be admitted. Runtime execution belongs to a caller.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
import ntpath
import os
from pathlib import Path
import platform
import sys

from . import operator_store, runtime_package, service_smoke_store, smoke_store
from .benchmark_runtime import BoundStore


PROFILE_ID = smoke_store.INSTALLED_SERVICE
PROFILE_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-service-profile.json'
SOURCE_TREE = service_smoke_store.SOURCE_TREE
RUNTIME_VARIANT = service_smoke_store.RUNTIME_VARIANT
RUNTIME_POLICY_SHA256 = service_smoke_store.RUNTIME_POLICY_SHA256
CONTROLLER_ID = 'gufo-native-installed-controller-v1'
ACCEPTANCE_SHA256 = None  # No independent persistent-service acceptance exists.
PINS = replace(service_smoke_store.PINS, profile_id=PROFILE_ID,
    evidence=smoke_store.ROOT/'reports/gufo-native-installed-v1-runs',
    qualification=smoke_store.ROOT/'reports/gufo-native-installed-v1-acceptance.json')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return sha256(_canonical(value).encode()).hexdigest().upper()


def _read(path):
    try:
        return operator_store.read_json(path)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise ValueError(f'invalid_state:{Path(path).name}') from error


def _exclusive_json(path, value):
    """Create immutable evidence once; a failed write leaves its latch in place."""
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def installed_argv(pins, api_key: str) -> list[str]:
    installed_binding(pins)
    if not isinstance(api_key, str) or not api_key:
        raise ValueError('api_key_required')
    return [str(pins.build/pins.executable_name), 'serve', '--host', '127.0.0.1',
        '--port', '8836', '--sessions', '1', '--max-connections', '3',
        '--max-request-bytes', '16384', '--api-key', api_key, 'llm', '--model',
        str(pins.first_shard), '--served-model-name', 'gufo-flash-next', '--context',
        '4096', '--max-tokens', '64', '--think', 'off', '--speculative', 'off',
        '--max-pending', '1', '--max-pending-per-client', '1',
        '--request-timeout-ms', '60000', '--max-output-bytes', '1048576',
        '--request-policy', 'ar4k-service-v1', '--preserve-thinking', 'off']


def expected_profile(pins):
    """Exact local candidate schema; the caller supplied file grants no trust."""
    return dict(schema=1, profile_id=PROFILE_ID,
        runtime=dict(path=str(pins.build), variant=RUNTIME_VARIANT,
                     policy_sha256=RUNTIME_POLICY_SHA256,
                     executable_sha256=pins.executable[1]),
        source=dict(path=str(pins.source), commit=pins.source_commit, tree=SOURCE_TREE),
        model=dict(first_shard=str(pins.first_shard), revision=pins.model_revision,
                   shards=list(pins.model_descriptors)),
        controller=dict(id=CONTROLLER_ID, python_implementation=platform.python_implementation(),
                        python_version=platform.python_version(), python_executable=sys.executable),
        endpoint=dict(host='127.0.0.1', port=8836, alias='gufo-flash-next'),
        request_flags=dict(sessions=1, context=4096, mtp=False, vision=False,
            projector=False, thinking=False, prompt_lookup=False, disk_cache=False,
            max_connections=3, max_request_bytes=16384, max_pending=1,
            max_pending_per_client=1, request_timeout_ms=60000,
            max_output_bytes=1048576, input_tokens=2304, output_tokens=256),
        envelope=dict(pins.bounds),
        operator_history=dict(source_commit=pins.operator_source_commit,
            failed_run=str(pins.failed_run), failed_result_sha256=pins.failed_result_sha256,
            gdn_run=str(pins.gdn_run), gdn_result_sha256=pins.gdn_result_sha256,
            iq_run=str(pins.iq_run), iq_result_sha256=pins.iq_result_sha256,
            sequence=str(pins.operator_evidence/'sequence.json')),
        evidence=dict(runs=str(pins.evidence), acceptance=str(pins.qualification)),
        candidate_margin=dict(path=str(pins.margin_report), sha256=pins.margin_sha256),
        acceptance_status='persistent_service_unqualified')


def installed_binding(pins):
    if (pins != PINS or pins.profile_id != PROFILE_ID
            or pins.evidence.name != smoke_store.PROFILE_ROOTS[PROFILE_ID]
            or any(type(pins.bounds.get(k)) is not int or pins.bounds[k] != v
                   for k, v in smoke_store.BOUNDS.items())):
        raise ValueError('installed_identity_invalid')
    return {'installed': {'profile_id': PROFILE_ID, 'source_tree': SOURCE_TREE,
            'runtime_variant': RUNTIME_VARIANT, 'runtime_policy_sha256': RUNTIME_POLICY_SHA256,
            'controller_id': CONTROLLER_ID}}


def source_identity():
    return service_smoke_store.source_identity()


def controller_artifacts():
    """Capture current controller bytes without embedding its own hash in source."""
    from . import admission, benchmark_runtime, smoke_guard, smoke_policy
    modules = (service_smoke_store, smoke_store, smoke_policy, admission,
               benchmark_runtime, smoke_guard, operator_store)
    files = [('service_store', Path(__file__)),
             *((module.__name__.rsplit('.', 1)[-1], Path(module.__file__))
               for module in modules)]
    return [dict(module=name, path=str(path.resolve(strict=True)),
                 sha256=operator_store.artifact_record(path)['sha256'])
            for name, path in files]


def expected_acceptance(profile, review_id, envelope_review_id):
    if (not isinstance(review_id, str) or not review_id.strip()
            or not isinstance(envelope_review_id, str) or not envelope_review_id.strip()):
        raise ValueError('service_review_missing')
    finite = service_smoke_store.service_binding(service_smoke_store.PINS)['service']['workload']
    return dict(schema=1, profile_id=PROFILE_ID, profile_sha256=_digest(profile),
        controller=deepcopy(profile['controller']), finite_workload_sha256=_digest(finite),
        controller_artifacts=controller_artifacts(),
        envelope=deepcopy(profile['envelope']), review_id=review_id,
        persistent_envelope_review_id=envelope_review_id,
        status='persistent-service-accepted')


def _profile(profile_path, pins):
    installed_binding(pins)
    profile = _read(profile_path)
    expected = expected_profile(pins)
    if (_canonical(profile) != _canonical(expected)
            or any(type(profile['envelope'][key]) is not int for key in smoke_store.BOUNDS)):
        raise ValueError('installed_profile_mismatch')
    return profile, operator_store.artifact_record(profile_path)


def _acceptance(profile, pins):
    if ACCEPTANCE_SHA256 is None:
        raise ValueError('persistent_service_unqualified')
    try:
        record, stamp = smoke_store._json_artifact(pins.qualification,
            ACCEPTANCE_SHA256, 'service_acceptance')
        if (not isinstance(record, dict) or record != expected_acceptance(
                profile, record.get('review_id'), record.get('persistent_envelope_review_id'))):
            raise ValueError('service_acceptance_mismatch')
        return record, stamp
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError('service_acceptance_invalid') from error


def _candidate(profile_path, pins):
    profile, profile_stamp = _profile(profile_path, pins)
    source_identity()
    package = runtime_package.verify_runtime(pins.build, variant=RUNTIME_VARIANT)
    if package.get('policy_sha256') != RUNTIME_POLICY_SHA256:
        raise ValueError('service_runtime_changed')
    candidate = smoke_store._verify_candidate_artifacts(pins,
        model_validator=smoke_store.validate_ar4k_model)
    baseline, state = smoke_store._operator_sequence(pins)
    margin = smoke_store._checked_artifact(pins.margin_report,
        (pins.margin_report.stat().st_size, pins.margin_sha256), 'candidate_margin')
    return dict(profile=PROFILE_ID, source=pins.source_commit, bounds=dict(pins.bounds),
        **candidate, operator=dict(original_baseline=asdict(baseline), state=state),
        margin_report=margin, installed_profile=profile,
        controller_artifacts=controller_artifacts(),
        installed_profile_stamp=profile_stamp, runtime_package=package,
        runtime_manifest=operator_store.artifact_record(pins.build/'runtime-manifest.json'))


def inspect_installed_profile(profile_path: Path) -> dict:
    """Read-only independent facts; never creates state, child, or telemetry."""
    result = dict(profile=PROFILE_ID, identity=expected_profile(PINS),
                  artifacts_valid=False, qualified=False, refusals=[])
    candidate = None
    try:
        candidate = _candidate(profile_path, PINS)
        result['artifacts_valid'] = True
        result['identity'] = candidate['installed_profile']
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    try:
        _acceptance(candidate['installed_profile'] if candidate else result['identity'], PINS)
        result['qualified'] = True
    except ValueError as error:
        result['refusals'].append(str(error))
    try:
        smoke_store._incomplete_latches(PINS)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    try:
        _prior_run(PINS)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    return result


def _run_path(pins, run):
    path = Path(run)
    root = pins.evidence.resolve(strict=True)
    if (not path.is_absolute() or not path.is_dir() or path.is_symlink()
            or path.resolve(strict=True) != path
            or path.parent.resolve(strict=True) != root):
        raise ValueError('installed_run_path_invalid')
    return path


def _prior_run(pins, *, prepared_run=None):
    prepared = _run_path(pins, prepared_run) if prepared_run is not None else None
    if prepared is not None and any((prepared/name).exists() for name in
            ('manifest.json', 'identity.json', 'result.json')):
        raise ValueError('installed_prepared_run_not_fresh')
    pointer_path = pins.evidence/'current.json'
    if (pins.evidence/'attempt.json').exists():
        raise ValueError('installed_attempt_marker_unexpected')
    if not pointer_path.exists():
        if any(path.is_dir() and any(path.iterdir()) for path in pins.evidence.iterdir()
               if path.name != 'runner.lock' and path != prepared):
            raise ValueError('installed_current_missing')
        return None
    pointer = _read(pointer_path)
    if (type(pointer) is not dict or pointer.get('profile') != PROFILE_ID
            or type(pointer.get('run')) is not str
            or type(pointer.get('result_sha256')) is not str
            or type(pointer.get('identity_sha256')) is not str):
        raise ValueError('installed_current_invalid')
    next_run = pointer['run']
    expected_result = pointer['result_sha256']
    expected_identity = pointer['identity_sha256']
    visited = set()
    while next_run is not None:
        run = _run_path(pins, next_run)
        if run in visited:
            raise ValueError('installed_prior_cycle')
        visited.add(run)
        identity = _read(run/'identity.json')
        manifest = _read(run/'manifest.json')
        if (identity.get('run') != str(run) or identity.get('profile') != PROFILE_ID
                or identity.get('manifest_sha256') != _digest(manifest)
                or expected_identity != _digest(identity)):
            raise ValueError('installed_prior_identity_invalid')
        try:
            result = _read(run/'result.json')
        except ValueError as error:
            raise ValueError('installed_prior_result_missing') from error
        if (expected_result != _digest(result)
                or result.get('run') != str(run) or result.get('profile') != PROFILE_ID
                or _canonical(result.get('manifest')) != _canonical(manifest)
                or not _clean(result)):
            raise ValueError('installed_prior_result_invalid')
        next_run = identity.get('previous_run')
        expected_result = identity.get('previous_result_sha256')
        expected_identity = identity.get('previous_identity_sha256')
        if ((next_run is None and (expected_result is not None or expected_identity is not None))
                or (next_run is not None and (type(next_run) is not str
                    or type(expected_result) is not str
                    or type(expected_identity) is not str))):
            raise ValueError('installed_prior_chain_invalid')
    for directory in pins.evidence.iterdir():
        if (directory.is_dir() and any(directory.iterdir())
                and directory not in visited and directory != prepared):
            raise ValueError('installed_orphaned_run_evidence')
    return pointer


def _clean(result):
    flags = ('owned_exit_confirmed', 'collector_terminal',
             'collector_cleanup_confirmed', 'http_terminal', 'inspection_terminal',
             'inspection_duplicate_closed', 'evidence_write_confirmed',
             'cleanup_confirmed')
    identity = result.get('identity') if type(result) is dict else None
    manifest = result.get('manifest') if type(result) is dict else None
    resumed = result.get('resumed_monotonic') if type(result) is dict else None
    return (type(result) is dict and result.get('success') is True
            and type(resumed) in (int, float) and math.isfinite(resumed) and resumed > 0
            and type(result.get('exit_code')) is int
            and type(identity) is dict
            and type(identity.get('pid')) is int and identity['pid'] > 0
            and type(identity.get('creation_time_100ns')) is int
            and identity['creation_time_100ns'] > 0
            and type(identity.get('executable')) is str
            and type(manifest) is dict and type(manifest.get('executable')) is str
            and ntpath.normcase(ntpath.normpath(identity['executable'])) ==
                ntpath.normcase(ntpath.normpath(manifest['executable']))
            and all(result.get(key) is True for key in flags)
            and type(result.get('recovery_samples')) is int
            and result['recovery_samples'] == 5)


def _current_run_markers(manifest, pins, current_run):
    run = _run_path(pins, current_run)
    pointer = _read(pins.evidence/'current.json')
    latch = _read(pins.evidence/'incomplete.json')
    identity = _read(run/'identity.json')
    if (pointer.get('run') != str(run) or pointer.get('profile') != PROFILE_ID
            or 'result_sha256' in pointer or latch.get('run') != str(run)
            or latch.get('phase') != 'before_create'
            or identity.get('manifest_sha256') != _digest(manifest)
            or pointer.get('identity_sha256') != _digest(identity)
            or _canonical(_read(run/'manifest.json')) != _canonical(manifest)
            or (run/'result.json').exists()):
        raise ValueError('installed_current_mismatch')


class InstalledStore(BoundStore):
    def __init__(self, profile_path: Path):
        super().__init__(PINS)
        self.profile_path = Path(profile_path)

    def verify_static(self):
        smoke_store._incomplete_latches(self.PINS)
        _prior_run(self.PINS)
        manifest = _candidate(self.profile_path, self.PINS)
        qualification, stamp = _acceptance(manifest['installed_profile'], self.PINS)
        manifest['qualification'] = qualification
        manifest['qualification_stamp'] = stamp
        return manifest

    def recheck_static(self, manifest, *, current_run=None, prepared_run=None):
        """prepared_run is the exact direct-child directory before begin_run only."""
        if current_run is not None and prepared_run is not None:
            raise ValueError('installed_run_phase_ambiguous')
        installed_binding(self.PINS)
        source_identity()
        try:
            smoke_store._incomplete_latches(self.PINS, manifest=manifest,
                                            current_run=current_run)
            if (manifest['profile'] != PROFILE_ID or manifest['source'] != self.PINS.source_commit
                    or manifest['bounds'] != self.PINS.bounds
                    or any(type(manifest['bounds'].get(k)) is not int for k in self.PINS.bounds)):
                raise ValueError('installed_manifest_identity_invalid')
            smoke_store._recheck_candidate_artifacts(manifest, self.PINS)
            profile, stamp = _profile(self.profile_path, self.PINS)
            if (manifest['installed_profile'] != profile
                    or manifest['installed_profile_stamp'] != stamp):
                raise ValueError('installed_profile_changed')
            if manifest['controller_artifacts'] != controller_artifacts():
                raise ValueError('installed_controller_changed')
            package = runtime_package.verify_runtime(self.BUILD, variant=RUNTIME_VARIANT)
            if (package != manifest['runtime_package']
                    or operator_store.artifact_record(self.BUILD/'runtime-manifest.json')
                       != manifest['runtime_manifest']):
                raise ValueError('service_runtime_changed')
            baseline, state = smoke_store._operator_sequence(self.PINS)
            if (_canonical(manifest['operator']) != _canonical(
                    {'original_baseline': asdict(baseline), 'state': state})
                    or operator_store.artifact_record(self.PINS.margin_report)
                       != {k: v for k, v in manifest['margin_report'].items() if k != 'label'}):
                raise ValueError('installed_history_changed')
            record, record_stamp = _acceptance(profile, self.PINS)
            if (manifest['qualification'] != record
                    or manifest['qualification_stamp'] != record_stamp):
                raise ValueError('service_acceptance_changed')
            if current_run is not None:
                _current_run_markers(manifest, self.PINS, current_run)
            else:
                _prior_run(self.PINS, prepared_run=prepared_run)
        except (OSError, KeyError, TypeError, IndexError, AttributeError) as error:
            raise ValueError('installed_manifest_recheck_invalid') from error

    def load_original_operator_baseline(self):
        return smoke_store._load_original_operator_baseline(self.PINS)

    def begin_run(self, run_dir, manifest, baseline):
        run = _run_path(self.PINS, run_dir)
        self.recheck_static(manifest, prepared_run=run)
        if ((run/'manifest.json').exists() or (run/'result.json').exists()
                or (run/'identity.json').exists()
                or asdict(baseline) != manifest['operator']['original_baseline']):
            raise ValueError('installed_run_not_fresh')
        previous = _prior_run(self.PINS, prepared_run=run)
        identity = dict(profile=PROFILE_ID, run=str(run),
            manifest_sha256=_digest(manifest), previous_result_sha256=(
                previous['result_sha256'] if previous else None),
            previous_identity_sha256=(previous['identity_sha256'] if previous else None),
            previous_run=(previous['run'] if previous else None))
        # The latch precedes all per-run evidence and every possible create.
        _exclusive_json(self.EVIDENCE/'incomplete.json',
            dict(run=str(run), phase='before_create', original_baseline=asdict(baseline)))
        _exclusive_json(run/'manifest.json', manifest)
        _exclusive_json(run/'identity.json', identity)
        operator_store.atomic_json(self.EVIDENCE/'current.json',
            dict(profile=PROFILE_ID, run=str(run), identity_sha256=_digest(identity)))

    def finish_run(self, run_dir, result):
        run = _run_path(self.PINS, run_dir)
        manifest = _read(run/'manifest.json')
        _current_run_markers(manifest, self.PINS, run)
        _exclusive_json(run/'result.json', result)
        if (result.get('run') != str(run) or result.get('profile') != PROFILE_ID
                or _canonical(result.get('manifest')) != _canonical(manifest)
                or not _clean(result)):
            return
        pointer = _read(self.EVIDENCE/'current.json')
        pointer['result_sha256'] = _digest(result)
        operator_store.atomic_json(self.EVIDENCE/'current.json', pointer)
        latch = _read(self.EVIDENCE/'incomplete.json')
        if latch.get('run') != str(run):
            raise ValueError('installed_latch_changed')
        (self.EVIDENCE/'incomplete.json').unlink()
