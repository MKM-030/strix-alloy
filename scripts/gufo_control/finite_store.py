"""Private two-attempt evidence; no process, telemetry or recovery execution."""
from dataclasses import asdict
import math
from pathlib import Path
import time

from . import build_identity, finite_profile as fp, operator_store
from . import runtime_package, service_store, smoke_store
from .benchmark_runtime import BoundPolicy, BoundStore
from .finite_ledger import _read as strict_read, _exclusive
from .finite_workload import WORKLOAD_PATH, WORKLOAD_SHA256, load_workload
from .operator_policy import MAX_PRELAUNCH_AGE_SECONDS

PINS = fp.PINS
ANCHOR_PATH = fp.ANCHOR_PATH
LIMIT = 2*1024*1024
_digest = service_store._digest
_canonical = service_store._canonical


def _read(path):
    return strict_read(Path(path), LIMIT)


def _write(path, value):
    return _exclusive(Path(path), value, LIMIT)


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _run(pins, value):
    raw = Path(value)
    root = build_identity.checked_path(pins.evidence, directory=True)
    run = build_identity.checked_path(raw, directory=True)
    if raw != run or run.parent != root:
        raise ValueError('finite_run_path')
    return run


def _source(pins):
    return build_identity.verify_git(
        build_identity.checked_path(pins.source, directory=True), Path('git'),
        remote=service_store.SOURCE_REMOTE, head=pins.source_commit,
        tree=service_store.SOURCE_TREE, base=service_store.SOURCE_BASE)


def _candidate(pins):
    binding = fp.finite_binding(pins)
    _source(pins)
    load_workload()
    package = runtime_package.verify_runtime(pins.build, variant=service_store.RUNTIME_VARIANT)
    if package.get('policy_sha256') != service_store.RUNTIME_POLICY_SHA256:
        raise ValueError('finite_runtime_policy')
    artifacts = smoke_store._verify_candidate_artifacts(
        pins, model_validator=smoke_store.validate_ar4k_model)
    original, state = smoke_store._operator_sequence(pins)
    margin = smoke_store._checked_artifact(pins.margin_report,
        (pins.margin_report.stat().st_size, pins.margin_sha256), 'candidate_margin')
    return dict(profile=fp.PROFILE_ID, source=pins.source_commit,
        bounds=dict(pins.bounds), finite_profile=binding, **artifacts,
        operator=dict(original_baseline=asdict(original), state=state),
        margin_report=margin, workload_stamp=operator_store.artifact_record(WORKLOAD_PATH),
        controller_artifacts=service_store.controller_artifacts(), runtime_package=package,
        runtime_manifest=operator_store.artifact_record(pins.build/'runtime-manifest.json'))


def _recheck_candidate(manifest, pins):
    fp.finite_binding(pins)
    _source(pins)
    smoke_store._recheck_candidate_artifacts(manifest, pins)
    load_workload()
    original, state = smoke_store._operator_sequence(pins)
    if (not _same(manifest['operator'], dict(original_baseline=asdict(original), state=state))
            or manifest['controller_artifacts'] != service_store.controller_artifacts()
            or manifest['workload_stamp'] != operator_store.artifact_record(WORKLOAD_PATH)
            or manifest['runtime_manifest'] != operator_store.artifact_record(pins.build/'runtime-manifest.json')
            or manifest['runtime_package'] != runtime_package.verify_runtime(
                pins.build, variant=service_store.RUNTIME_VARIANT)
            or {k: v for k, v in manifest['margin_report'].items() if k != 'label'} !=
                operator_store.artifact_record(pins.margin_report)):
        raise ValueError('finite_candidate_changed')


def _review(candidate, pins):
    build_identity.checked_path(ANCHOR_PATH)
    anchor = _read(ANCHOR_PATH)
    fp.validate_anchor(anchor)
    if anchor['certificate_sha256'] is None:
        raise ValueError('finite_review_absent')
    build_identity.checked_path(pins.qualification)
    q = _read(pins.qualification)
    fp.validate_review(q)
    # Strict bounded parsing precedes the reused hashing/parser helper.
    if any(path.stat().st_size > LIMIT for path in (ANCHOR_PATH, pins.qualification)):
        raise ValueError('finite_record_size')
    hashed_anchor, anchor_stamp = smoke_store._json_artifact(
        ANCHOR_PATH, None, 'finite_review_anchor')
    hashed_q, stamp = smoke_store._json_artifact(pins.qualification,
        anchor['certificate_sha256'], 'finite_review')
    if (not _same(anchor, hashed_anchor) or not _same(q, hashed_q)
            or not _same(anchor, _read(ANCHOR_PATH))
            or not _same(q, _read(pins.qualification))):
        raise ValueError('finite_review_changed')
    if q['candidate_sha256'] != _digest(candidate):
        raise ValueError('finite_review_candidate_changed')
    return q, stamp, anchor, anchor_stamp


def phase_record(run_dir, manifest, lifecycle, coverage):
    """Validate serialization only; live receipt provenance belongs to the wrapper."""
    run = Path(run_dir)
    expected_keys = {'run_id', 'lifecycle', 'returned_slots', 'ready_count', 'models_count',
        'post_count', 'workers_terminal', 'phase_boundaries', 'idle_windows', 'wave_proofs',
        'pending_semantic_review', 'failure', 'complete'}
    posts = 66 if lifecycle == 1 else 6
    if (type(lifecycle) is not int or lifecycle not in (1, 2)
            or type(coverage) is not dict or set(coverage) != expected_keys
            or coverage['run_id'] != run.name or type(coverage['lifecycle']) is not int
            or coverage['lifecycle'] != lifecycle or coverage['complete'] is not True
            or coverage['workers_terminal'] is not True or coverage['failure'] is not None
            or type(coverage['pending_semantic_review']) is not bool
            or type(coverage['ready_count']) is not int or not 1 <= coverage['ready_count'] <= 240
            or type(coverage['models_count']) is not int or coverage['models_count'] != 1
            or type(coverage['post_count']) is not int or coverage['post_count'] != posts
            or type(coverage['returned_slots']) not in (list, tuple)
            or len(coverage['returned_slots']) != posts-1
            or set(coverage['returned_slots']) != {f'post-{n:03d}' for n in range(2, posts+1)}
            or type(coverage['phase_boundaries']) not in (list, tuple)
            or type(coverage['idle_windows']) not in (list, tuple)
            or type(coverage['wave_proofs']) not in (list, tuple)):
        raise ValueError('finite_phase_incomplete')
    idle, waves = coverage['idle_windows'], coverage['wave_proofs']
    if (len(idle) != (4 if lifecycle == 1 else 0)
            or len(waves) != (2 if lifecycle == 1 else 0)):
        raise ValueError('finite_phase_coverage')
    # Executor owns durations/rendezvous semantics. Store rejects malformed serialized proof.
    for rows, width in ((coverage['phase_boundaries'], 2), (idle, 3), (waves, 4)):
        for row in rows:
            if (type(row) not in (list, tuple) or len(row) != width
                    or type(row[0]) is not int or not 1 <= row[0] <= posts
                    or any(not _time(t) for t in row[1:])):
                raise ValueError('finite_phase_proof')
    if lifecycle == 1 and ([row[0] for row in idle] != [6, 18, 30, 48]
                           or [row[0] for row in waves] != [45, 48]):
        raise ValueError('finite_phase_schedule')
    if (any(row[2]-row[1] < 30 for row in idle)
            or any(not row[1] <= row[2] <= row[3] for row in waves)):
        raise ValueError('finite_phase_timing')
    return dict(schema=1, profile=fp.PROFILE_ID, run=str(run), lifecycle=lifecycle,
        manifest_sha256=_digest(manifest), workload_sha256=WORKLOAD_SHA256,
        acceptance='structural_only', coverage=coverage)


def _terminal(run, manifest, identity, result):
    admission = _read(run/'finite-admission.json')
    if (type(result) is not dict or result.get('run') != str(run)
            or result.get('profile') != fp.PROFILE_ID
            or not _same(result.get('manifest'), manifest)
            or not _same(result.get('original_baseline'), manifest['operator']['original_baseline'])
            or not _same(result.get('current_baseline'), admission['current_baseline'])
            or not service_store._clean(result)
            or result.get('service_ready') is not True or result.get('stop_requested') is not True
            or not _time(result.get('finite_recovery_completed_monotonic'))
            or result['finite_recovery_completed_monotonic'] < result['resumed_monotonic']):
        raise ValueError('finite_terminal_incomplete')
    phase = _read(run/'phase-evidence.json')
    expected = phase_record(run, manifest, identity['lifecycle'], phase['coverage'])
    if (not _same(phase, expected) or result.get('finite_phase_sha256') != _digest(phase)):
        raise ValueError('finite_terminal_phase')
    return result


def _history(pins, *, prepared_run=None, active_run=None):
    root = build_identity.checked_path(pins.evidence, directory=True, exists=False)
    if not root.exists():
        if prepared_run is not None: raise ValueError('finite_prepared_missing')
        return []
    if active_run is not None and prepared_run is not None:
        raise ValueError('finite_run_phase_ambiguous')
    prepared = _run(pins, prepared_run) if prepared_run is not None else None
    if prepared and any((prepared/n).exists() for n in ('manifest.json', 'identity.json', 'result.json')):
        raise ValueError('finite_prepared_not_fresh')
    if (root/'attempt.json').exists(): raise ValueError('finite_legacy_attempt')
    pointer = _read(root/'current.json') if (root/'current.json').exists() else None
    active_identity = None
    if active_run is not None:
        prepared = _run(pins, active_run)
        active_identity = _read(prepared/'identity.json')
        pointer = (dict(profile=fp.PROFILE_ID, run=active_identity['previous_run'],
            identity_sha256=active_identity['previous_identity_sha256'],
            result_sha256=active_identity['previous_result_sha256'])
            if active_identity['previous_run'] is not None else None)
    chain, seen = [], set()
    while pointer is not None:
        if (type(pointer) is not dict or set(pointer) !=
                {'profile', 'run', 'identity_sha256', 'result_sha256'}
                or pointer['profile'] != fp.PROFILE_ID or len(chain) >= 2):
            raise ValueError('finite_history_pointer')
        run = _run(pins, pointer['run'])
        if run in seen: raise ValueError('finite_history_cycle')
        seen.add(run)
        identity, manifest, result = (_read(run/name) for name in
                                     ('identity.json', 'manifest.json', 'result.json'))
        keys = {'profile', 'run', 'lifecycle', 'manifest_sha256', 'admission_sha256',
                'previous_run', 'previous_identity_sha256', 'previous_result_sha256'}
        if (type(identity) is not dict or set(identity) != keys
                or identity['profile'] != fp.PROFILE_ID or identity['run'] != str(run)
                or type(identity['lifecycle']) is not int or identity['lifecycle'] not in (1, 2)
                or identity['manifest_sha256'] != _digest(manifest)
                or pointer['identity_sha256'] != _digest(identity)
                or pointer['result_sha256'] != _digest(result)
                or identity['admission_sha256'] != _digest(_read(run/'finite-admission.json'))):
            raise ValueError('finite_history_identity')
        _terminal(run, manifest, identity, result)
        chain.append(dict(run=run, identity=identity, result=result))
        previous = identity['previous_run']
        if previous is None:
            if (identity['lifecycle'] != 1 or identity['previous_identity_sha256'] is not None
                    or identity['previous_result_sha256'] is not None):
                raise ValueError('finite_history_origin')
            pointer = None
        else:
            if identity['lifecycle'] != 2: raise ValueError('finite_history_order')
            pointer = dict(profile=fp.PROFILE_ID, run=previous,
                identity_sha256=identity['previous_identity_sha256'],
                result_sha256=identity['previous_result_sha256'])
    chain.reverse()
    if [row['identity']['lifecycle'] for row in chain] != list(range(1, len(chain)+1)):
        raise ValueError('finite_history_order')
    if active_identity is not None and (active_identity['lifecycle'] != len(chain)+1
            or (not chain and (active_identity['previous_identity_sha256'] is not None
                              or active_identity['previous_result_sha256'] is not None))):
        raise ValueError('finite_history_order')
    for entry in root.iterdir():
        build_identity.checked_path(entry, directory=entry.is_dir())
        if entry.is_dir() and entry not in seen and entry != prepared:
            raise ValueError('finite_orphan')
    return chain


def _current_run_markers(manifest, pins, current_run):
    run = _run(pins, current_run)
    pointer, latch, identity = (_read(path) for path in
        (pins.evidence/'current.json', pins.evidence/'incomplete.json', run/'identity.json'))
    identity_keys = {'profile', 'run', 'lifecycle', 'manifest_sha256', 'admission_sha256',
                     'previous_run', 'previous_identity_sha256', 'previous_result_sha256'}
    if (type(identity) is not dict or set(identity) != identity_keys
            or not _same(pointer, dict(profile=fp.PROFILE_ID, run=str(run), identity_sha256=_digest(identity)))
            or not _same(latch, dict(run=str(run), phase='before_create',
                original_baseline=manifest['operator']['original_baseline']))
            or identity.get('profile') != fp.PROFILE_ID or identity.get('run') != str(run)
            or type(identity.get('lifecycle')) is not int or identity['lifecycle'] not in (1, 2)
            or identity.get('manifest_sha256') != _digest(manifest)
            or identity.get('admission_sha256') != _digest(_read(run/'finite-admission.json'))
            or not _same(_read(run/'manifest.json'), manifest) or (run/'result.json').exists()):
        raise ValueError('finite_current_mismatch')
    history = _history(pins, active_run=run)
    if history and not _same(history[0]['result']['manifest'], manifest):
        raise ValueError('finite_pair_manifest_changed')


class FiniteStore(BoundStore):
    def __init__(self):
        super().__init__(PINS)

    def verify_static(self):
        smoke_store._incomplete_latches(self.PINS)
        history = _history(self.PINS)
        if len(history) == 2: raise ValueError('finite_attempts_exhausted')
        manifest = _candidate(self.PINS)
        q, stamp, anchor, anchor_stamp = _review(manifest, self.PINS)
        manifest.update(qualification=q, qualification_stamp=stamp,
            qualification_anchor=anchor, qualification_anchor_stamp=anchor_stamp)
        fp.bind_manifest(manifest, pins=self.PINS)
        if history and not _same(history[0]['result']['manifest'], manifest):
            raise ValueError('finite_pair_manifest_changed')
        return manifest

    def recheck_static(self, manifest, *, current_run=None, prepared_run=None):
        if current_run is not None and prepared_run is not None:
            raise ValueError('finite_run_phase_ambiguous')
        fp.bind_manifest(manifest, pins=self.PINS)
        smoke_store._incomplete_latches(self.PINS, manifest=manifest, current_run=current_run)
        _recheck_candidate(manifest, self.PINS)
        q, stamp, anchor, anchor_stamp = _review(fp.candidate_part(manifest), self.PINS)
        if not _same((q, stamp, anchor, anchor_stamp), tuple(manifest[k] for k in
                ('qualification', 'qualification_stamp', 'qualification_anchor', 'qualification_anchor_stamp'))):
            raise ValueError('finite_review_changed')
        if current_run is not None:
            _current_run_markers(manifest, self.PINS, current_run)
        elif len(_history(self.PINS, prepared_run=prepared_run)) >= 2:
            raise ValueError('finite_attempts_exhausted')

    def load_original_operator_baseline(self):
        return smoke_store._load_original_operator_baseline(self.PINS)

    def record_admission(self, run_dir, manifest, current_baseline, frame, *, now, now_utc):
        run = _run(self.PINS, run_dir)
        self.recheck_static(manifest, prepared_run=run)
        history = _history(self.PINS, prepared_run=run)
        original = smoke_store._baseline(manifest['operator']['original_baseline'])
        policy = BoundPolicy(self.PINS)
        effective = policy.stricter_runtime_baseline(original, current_baseline)
        if history and current_baseline.first_start <= history[-1]['result']['finite_recovery_completed_monotonic']:
            raise ValueError('finite_admission_before_recovery')
        decision = policy.admission_decision(policy.profile_from_manifest(manifest),
            effective, frame, now=now, now_utc=now_utc)
        if decision['allowed'] is not True: raise ValueError('finite_admission_refused')
        if not _time(now) or not 0 <= time.monotonic()-now <= MAX_PRELAUNCH_AGE_SECONDS:
            raise ValueError('finite_admission_stale')
        proof = dict(schema=1, profile=fp.PROFILE_ID, run=str(run), lifecycle=len(history)+1,
            manifest_sha256=_digest(manifest), current_baseline=asdict(current_baseline),
            decision=decision, checked_monotonic=now, query_start=frame.query_start,
            query_end=frame.query_end, sample=frame.snapshot)
        _write(run/'finite-admission.json', proof)
        return proof

    def begin_run(self, run_dir, manifest, baseline):
        run = _run(self.PINS, run_dir)
        self.recheck_static(manifest, prepared_run=run)
        history = _history(self.PINS, prepared_run=run)
        if not _same(asdict(baseline), manifest['operator']['original_baseline']):
            raise ValueError('finite_original_baseline_changed')
        proof = _read(run/'finite-admission.json')
        if (proof.get('profile') != fp.PROFILE_ID or proof.get('run') != str(run)
                or type(proof.get('lifecycle')) is not int or proof['lifecycle'] != len(history)+1
                or proof.get('manifest_sha256') != _digest(manifest)
                or proof.get('decision', {}).get('allowed') is not True
                or not _time(proof.get('query_start'))
                or not 0 <= time.monotonic()-proof['query_start'] <= MAX_PRELAUNCH_AGE_SECONDS):
            raise ValueError('finite_admission_stale')
        previous = history[-1] if history else None
        if previous and not _same(previous['result']['manifest'], manifest):
            raise ValueError('finite_pair_manifest_changed')
        if previous and proof['current_baseline']['first_start'] <= previous['result']['finite_recovery_completed_monotonic']:
            raise ValueError('finite_admission_before_recovery')
        identity = dict(profile=fp.PROFILE_ID, run=str(run), lifecycle=len(history)+1,
            manifest_sha256=_digest(manifest), admission_sha256=_digest(proof),
            previous_run=str(previous['run']) if previous else None,
            previous_identity_sha256=_digest(previous['identity']) if previous else None,
            previous_result_sha256=_digest(previous['result']) if previous else None)
        _write(self.EVIDENCE/'incomplete.json', dict(run=str(run), phase='before_create',
            original_baseline=asdict(baseline)))
        _write(run/'manifest.json', manifest)
        _write(run/'identity.json', identity)
        operator_store.atomic_json(self.EVIDENCE/'current.json', dict(profile=fp.PROFILE_ID,
            run=str(run), identity_sha256=_digest(identity)))

    def finish_run(self, run_dir, result):
        run = _run(self.PINS, run_dir)
        manifest = _read(run/'manifest.json')
        _current_run_markers(manifest, self.PINS, run)
        identity = _read(run/'identity.json')
        # Always preserve the first terminal report, including failure/incomplete evidence.
        _write(run/'result.json', result)
        try:
            _terminal(run, manifest, identity, result)
        except (ValueError, OSError, KeyError, TypeError) as error:
            if type(result) is dict and result.get('success') is True:
                raise ValueError('finite_success_incomplete') from error
            return
        latch = _read(self.EVIDENCE/'incomplete.json')
        if not _same(latch, dict(run=str(run), phase='before_create',
                               original_baseline=manifest['operator']['original_baseline'])):
            raise ValueError('finite_latch_changed')
        operator_store.atomic_json(self.EVIDENCE/'current.json', dict(profile=fp.PROFILE_ID,
            run=str(run), identity_sha256=_digest(identity), result_sha256=_digest(result)))
        # Only this exact finite run's owned latch, after durable terminal evidence.
        if not _same(_read(self.EVIDENCE/'incomplete.json'), latch):
            raise ValueError('finite_latch_changed')
        (self.EVIDENCE/'incomplete.json').unlink()


def inspect_finite_profile():
    result = dict(profile=fp.PROFILE_ID, artifacts_valid=False, reviewed=False,
        history_valid=False, attempts_completed=None, next_lifecycle=None,
        installed_service_accepted=False, refusals=[])
    try:
        candidate = _candidate(PINS)
        result['artifacts_valid'] = True
        _review(candidate, PINS)
        result['reviewed'] = True
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    try:
        smoke_store._incomplete_latches(PINS)
        history = _history(PINS)
        result.update(history_valid=True, attempts_completed=len(history),
                      next_lifecycle=len(history)+1 if len(history) < 2 else None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['refusals'].append(str(error))
    return result
