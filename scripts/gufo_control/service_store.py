"""Closed installed GUFO candidate with separate, currently absent service acceptance.

Inspection is read only. A separate local trust-anchor file has no approval by
default. Runtime execution belongs to a caller.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
import ntpath
import os
from pathlib import Path
import platform
import sys

from . import build_identity, operator_store, runtime_package, service_smoke_store, smoke_store
from .benchmark_runtime import BoundStore


PROFILE_ID = smoke_store.INSTALLED_SERVICE
PROFILE_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-service-profile.json'
SOURCE_TREE = '7912be2688d6874c0e13f4723aad00a5c3cbe1cf'
SOURCE_REMOTE = 'https://github.com/pixmaate/gufo.git'
SOURCE_BASE = 'cff564964e8506c0abb3e530cecb55332187ac6c'
RUNTIME_VARIANT = 'service-ar4k-header-v1'
RUNTIME_POLICY_SHA256 = runtime_package.REVIEWED_HEADER_POLICY_SHA256
CONTROLLER_ID = 'gufo-native-installed-controller-v1'
CONTROLLER_SOURCE_DIR = Path(__file__).resolve().parent
ANCHOR_PATH = PROFILE_PATH.with_name('gufo-service-acceptance-anchor.json')
PINS = replace(service_smoke_store.PINS, profile_id=PROFILE_ID,
    source=smoke_store.ROOT/'engine/gufo-ar4k-header-cap',
    source_commit='e6feed7ca52df4661d10434c72a8ea5b5f054bc2',
    build=smoke_store.ROOT/'runtimes/gufo-native-service-header-e6feed7-therock10.2',
    executable=(42440192, '9682019A5198B19CA131D60298A1E896186099ACC971C17B04BB31E302F7FFE9'),
    evidence=smoke_store.ROOT/'reports/gufo-native-installed-v1-runs',
    qualification=smoke_store.ROOT/'reports/gufo-native-installed-v1-acceptance.json',
    margin_report=smoke_store.ROOT/'reports/gufo-header-lifecycle-margin-review-20260927.md',
    margin_sha256='DAF6C99521AC4B751CD13E3462E46FEBB8F33038E24FCF39DCAF8C6309991E9F')


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
    source = build_identity.checked_path(PINS.source, directory=True)
    return build_identity.verify_git(source, Path('git'), remote=SOURCE_REMOTE,
                                     head=PINS.source_commit, tree=SOURCE_TREE,
                                     base=SOURCE_BASE)


def controller_artifacts():
    """Inventory all local controller sources, including future service modules.

    The trust anchor resides in config and is deliberately excluded.
    """
    root = CONTROLLER_SOURCE_DIR.resolve(strict=True)
    if not root.is_dir() or CONTROLLER_SOURCE_DIR.is_symlink():
        raise ValueError('controller_source_root_invalid')
    entries = list(root.rglob('*'))
    if any(path.is_symlink() for path in entries):
        raise ValueError('controller_source_path_invalid')
    files = sorted((path for path in entries
                    if path.suffix in ('.py', '.ps1', '.cs')),
                   key=lambda path: path.relative_to(root).as_posix())
    if not files or not any(path.relative_to(root).as_posix() == 'service_store.py'
                            for path in files):
        raise ValueError('controller_source_inventory_invalid')
    rows = []
    for path in files:
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('controller_source_path_invalid')
        rows.append(dict(name=path.relative_to(root).as_posix(),
                         path=str(path.resolve(strict=True)),
                         sha256=operator_store.artifact_record(path)['sha256']))
    return rows


def expected_anchor(profile):
    return dict(schema=1, profile_id=PROFILE_ID, profile_sha256=_digest(profile),
                controller_id=CONTROLLER_ID, acceptance_sha256=None,
                installed_workload=None)


def _installed_workload(value):
    keys = {'schema', 'kind', 'profile_id', 'lifetime_seconds',
            'max_generation_posts', 'max_model_queries', 'max_prompt_tokens',
            'max_output_tokens', 'context_tokens', 'sessions', 'sole_client'}
    if (type(value) is not dict or set(value) != keys
            or type(value['schema']) is not int or value['schema'] != 1
            or value['kind'] != 'gufo-native-installed-finite-workload'
            or value['profile_id'] != PROFILE_ID
            or type(value['sole_client']) is not bool or value['sole_client'] is not True
            or type(value['context_tokens']) is not int or value['context_tokens'] != 4096
            or type(value['sessions']) is not int or value['sessions'] != 1
            or any(type(value[k]) is not int or not 1 <= value[k] <= limit for k, limit in (
                ('lifetime_seconds', 86400), ('max_generation_posts', 10000),
                ('max_model_queries', 10000), ('max_prompt_tokens', 2304),
                ('max_output_tokens', 256)))):
        raise ValueError('installed_workload_invalid')
    return value


def validate_anchor(profile, anchor):
    expected = expected_anchor(profile)
    if (type(anchor) is not dict or set(anchor) != set(expected)
            or any(anchor[k] != expected[k] for k in (
                'schema', 'profile_id', 'profile_sha256', 'controller_id'))
            or type(anchor['schema']) is not int
            or (anchor['acceptance_sha256'] is not None
                and not smoke_store._digest_valid(anchor['acceptance_sha256']))):
        raise ValueError('acceptance_anchor_invalid')
    if anchor['installed_workload'] is not None:
        _installed_workload(anchor['installed_workload'])
    return anchor


def _anchor(profile):
    if not ANCHOR_PATH.is_absolute() or ANCHOR_PATH.is_symlink():
        raise ValueError('acceptance_anchor_path_invalid')
    try:
        anchor, stamp = smoke_store._json_artifact(ANCHOR_PATH, None, 'acceptance_anchor')
    except OSError as error:
        raise ValueError('persistent_service_unqualified') from error
    validate_anchor(profile, anchor)
    return anchor, stamp


def acceptance_record(profile, review_id, envelope_review_id,
                      installed_workload, artifacts):
    if (not isinstance(review_id, str) or not review_id.strip()
            or not isinstance(envelope_review_id, str) or not envelope_review_id.strip()):
        raise ValueError('service_review_missing')
    workload = _installed_workload(installed_workload)
    required = {'service_store.py', 'smoke_store.py', 'smoke_policy.py',
        'operator_policy.py', 'winjob.py', 'operator_probe.py', 'telemetry.py',
        'smoke_http.py', 'model_identity.py', 'runtime_package.py',
        'windows_probe.ps1', 'windows_counters.cs'}
    if (type(artifacts) is not list or not required.issubset(
            {row.get('name') for row in artifacts if type(row) is dict})
            or any(type(row) is not dict or set(row) != {'name', 'path', 'sha256'}
                   or type(row['name']) is not str or type(row['path']) is not str
                   or not Path(row['path']).is_absolute()
                   or not smoke_store._digest_valid(row['sha256']) for row in artifacts)
            or [row['name'] for row in artifacts] != sorted(
                {row['name'] for row in artifacts})):
        raise ValueError('controller_artifacts_invalid')
    return dict(schema=1, profile_id=PROFILE_ID, profile_sha256=_digest(profile),
        controller=profile['controller'], installed_workload=workload,
        installed_workload_sha256=_digest(workload),
        controller_artifacts=artifacts,
        envelope=profile['envelope'], review_id=review_id,
        persistent_envelope_review_id=envelope_review_id,
        status='persistent-service-accepted')


def expected_acceptance(profile, review_id, envelope_review_id, installed_workload):
    return acceptance_record(profile, review_id, envelope_review_id,
                             installed_workload, controller_artifacts())


def _profile(profile_path, pins):
    installed_binding(pins)
    profile = _read(profile_path)
    expected = expected_profile(pins)
    if (_canonical(profile) != _canonical(expected)
            or any(type(profile['envelope'][key]) is not int for key in smoke_store.BOUNDS)):
        raise ValueError('installed_profile_mismatch')
    return profile, operator_store.artifact_record(profile_path)


def _acceptance(profile, pins, anchor):
    if anchor['acceptance_sha256'] is None or anchor['installed_workload'] is None:
        raise ValueError('persistent_service_unqualified')
    try:
        record, stamp = smoke_store._json_artifact(pins.qualification,
            anchor['acceptance_sha256'], 'service_acceptance')
        if (not isinstance(record, dict) or record != expected_acceptance(
                profile, record.get('review_id'), record.get('persistent_envelope_review_id'),
                anchor['installed_workload'])):
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
        profile = candidate['installed_profile'] if candidate else result['identity']
        anchor, _ = _anchor(profile)
        _acceptance(profile, PINS, anchor)
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
        if (type(identity) is not dict or type(manifest) is not dict
                or identity.get('run') != str(run) or identity.get('profile') != PROFILE_ID
                or identity.get('manifest_sha256') != _digest(manifest)
                or expected_identity != _digest(identity)):
            raise ValueError('installed_prior_identity_invalid')
        try:
            result = _read(run/'result.json')
        except ValueError as error:
            raise ValueError('installed_prior_result_missing') from error
        if (type(result) is not dict or expected_result != _digest(result)
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
        anchor, anchor_stamp = _anchor(manifest['installed_profile'])
        qualification, stamp = _acceptance(manifest['installed_profile'], self.PINS,
                                            anchor)
        manifest['qualification_anchor'] = anchor
        manifest['qualification_anchor_stamp'] = anchor_stamp
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
            anchor, anchor_stamp = _anchor(profile)
            if (manifest['qualification_anchor'] != anchor
                    or manifest['qualification_anchor_stamp'] != anchor_stamp):
                raise ValueError('acceptance_anchor_changed')
            record, record_stamp = _acceptance(profile, self.PINS, anchor)
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
