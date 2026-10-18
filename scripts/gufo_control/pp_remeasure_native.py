"""One reviewed PP repetition with a pinned, compiled read-only memory probe.

The consumed v1 attempt and failed cleanup result remain intact. No policy change.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from . import pp_remeasure as prior, operator_store, operator_probe, smoke_store
from . import benchmark_recipes as recipes, service_recovery
from .benchmark_runtime import BoundPolicy
from .benchmark_suite import start_suite
from .operator_policy import _frame_reasons, recovery_reasons
from .smoke_guard import _Guardian, check_port, _rising_residual
from .telemetry import collect_snapshot

EVALUATION = 'gufo-pp-repeat-20260927-v2'
EVIDENCE = prior.REPORTS / (EVALUATION + '-runs')
APPROVAL = prior.REPORTS / (EVALUATION + '-r2-approval.json')
BOOTSTRAP_SHA = 'DF82EFB28315021AADEED0BB137BC32A2A2127FDD1FAFDF89238CA99A5DA2DEC'
BOOTSTRAP_ARCHIVE = EVIDENCE / 'first-bootstrap-failed.json'
BOOTSTRAP_CERTIFICATE = EVIDENCE / 'bootstrap-late-recovery.json'
REOBSERVATION_ATTEMPT = EVIDENCE / 'bootstrap-reobservation-attempt.json'
OLD_RUN = prior.EVIDENCE / '20260927T141536Z-4cd4dd7349734cfd89c86e37da114ce6'
OLD_PINS = {
    OLD_RUN / 'result.json': 'D148AA27F79768AFC11A028F09446B4F28764A9247E3E77D76B166EF2EF2A087',
    prior.EVIDENCE / 'attempt.json': 'EE47F5AD712DB809369390D7CA4F4164AAED8D5DDF9731CA0748AA288D22718E',
    prior.EVIDENCE / 'incomplete.json': '96F89307C1FC6D3DA97ED9113F9817DB9C927E36AF462E68381BD71D4CE3D27E',
}
PROBE_DIR = smoke_store.ROOT / 'build' / 'gufo-telemetry-native-20260927-v2'
PROBE = PROBE_DIR / 'gufo-memory-probe.exe'
PROBE_SHA = 'C2A655EFACD774EEF2DC941CABAF591D902706677583181C3447A7A219C8A392'
BUILD_SHA = 'C9C0BA33F77416BAC04F221117416B27C96C884747EBF0FE8BCD53B624FFE18D'


def checked(path, sha):
    record = operator_store.artifact_record(path)
    if record['sha256'] != sha:
        raise ValueError('native_repeat_artifact_changed:' + Path(path).name)
    return record


def exclusive_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def bootstrap_latch():
    if (EVIDENCE / 'attempt.json').exists():
        raise ValueError('gpu_attempt_already_consumed')
    value = service_recovery.read_pinned(EVIDENCE / 'incomplete.json', BOOTSTRAP_SHA)
    if value != dict(collector_terminal=True, evaluation=EVALUATION, phase='late_recovery_failed'):
        raise ValueError('unexpected_bootstrap_latch')


def collect(*, owned=None):
    # Authenticate the tiny binary on every invocation, inside Query's deadline.
    checked(PROBE, PROBE_SHA)
    return collect_snapshot(owned=owned, probe_executable=PROBE)


def probe_records():
    manifest = PROBE_DIR / 'build-manifest.json'
    records = [checked(manifest, BUILD_SHA), checked(PROBE, PROBE_SHA)]
    build = json.loads(manifest.read_text(encoding='utf-8-sig'))
    for item in [*build['sources'], build['compiler'], build['reference']]:
        records.append(checked(item['path'], item['sha256']))
    records.append(checked(PROBE_DIR / 'dxgi-extracted.cs', build['extractedDxgiSha256']))
    if build['executable'] != {'path': str(PROBE), 'sha256': PROBE_SHA}:
        raise ValueError('probe_build_binding_changed')
    return records


class NativeRepeatStore(prior.RepeatStore):
    EVIDENCE = EVIDENCE

    def history(self):
        historical = super().history()
        records = {path: service_recovery.read_pinned(path, sha) for path, sha in OLD_PINS.items()}
        result = records[OLD_RUN / 'result.json']
        if (result['success'] is not False or result['cleanup_confirmed'] is not False
                or result['failure'] != 'TimeoutError:active_query_timeout;ValueError:pending_after_exit:query_timeout;RuntimeError:recovery_unconfirmed'
                or result['exit_code'] != 0 or result['collector_cleanup_confirmed'] is not False
                or any(result[k] is not True for k in ('owned_exit_confirmed', 'collector_terminal',
                    'http_terminal', 'inspection_terminal', 'inspection_duplicate_closed', 'evidence_write_confirmed'))):
            raise ValueError('unexpected_v1_terminal_state')
        if (records[prior.EVIDENCE / 'incomplete.json']['run'] != str(OLD_RUN)
                or records[prior.EVIDENCE / 'attempt.json']['run'] != str(OLD_RUN)):
            raise ValueError('v1_marker_mismatch')
        return historical, result

    def verify_static(self):
        p = self.PINS
        if self.EVIDENCE.resolve() != self.EVIDENCE or self.EVIDENCE.is_symlink():
            raise ValueError('repeat_root_redirected')
        bootstrap_latch()
        if (BOOTSTRAP_ARCHIVE.exists() or BOOTSTRAP_CERTIFICATE.exists()
                or REOBSERVATION_ATTEMPT.exists()
                or any(self.EVIDENCE.glob('bootstrap-reobserve-failed-*.json'))):
            raise ValueError('bootstrap_disposition_already_exists')
        _, old = self.history()
        approval = operator_store.read_json(APPROVAL)
        if (approval.get('evaluation') != EVALUATION or approval.get('decision') != 'approved'
                or approval.get('module_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()
                or approval.get('recipe_sha256') != hashlib.sha256(recipes.recipe_json(recipes.PROFILE_16K).encode()).hexdigest().upper()
                or not approval.get('review_path') or not approval.get('review_sha256')):
            raise ValueError('repeat_review_missing_or_changed')
        records = [checked(approval['review_path'], approval['review_sha256']),
                   operator_store.artifact_record(APPROVAL), operator_store.artifact_record(Path(__file__)),
                   *probe_records(), *(checked(path, sha) for path, sha in OLD_PINS.items())]
        required = {'pp_remeasure.py', 'telemetry.py', 'smoke_store.py', 'smoke_guard.py', 'operator_probe.py'}
        if set(approval.get('helper_sha256', {})) != required:
            raise ValueError('helper_binding_missing')
        records += [checked(Path(__file__).with_name(name), sha) for name, sha in approval['helper_sha256'].items()]
        operator_store.source_identity()
        candidate = smoke_store._verify_candidate_artifacts(p, model_validator=smoke_store.validate_ar4k_model)
        historical, state = smoke_store._operator_sequence(p)
        benchmark = smoke_store._benchmark_records(p)
        qualification, qualification_stamp = smoke_store._qualification(p)
        margin = smoke_store._checked_artifact(p.margin_report,
            (p.margin_report.stat().st_size, p.margin_sha256), 'margin_report')
        ps = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        boot = subprocess.run([str(ps), '-NoProfile', '-NonInteractive', '-Command',
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if boot.returncode or boot.stdout.strip() != prior.BOOT_UTC:
            raise ValueError('unexpected_boot_epoch')
        check_port()
        self.original = service_recovery.baseline_from(old['original_baseline'])
        previous = service_recovery.baseline_from(old['current_baseline'])
        log = self.EVIDENCE / ('late-recovery-' + uuid.uuid4().hex + '.jsonl')

        def factory(fn):
            query = operator_probe.Query(fn)
            self.bootstrap_queries.append(query)
            return query

        exclusive_json(REOBSERVATION_ATTEMPT, dict(evaluation=EVALUATION,
            started_utc=datetime.now(timezone.utc).isoformat(),
            module_sha256=approval['module_sha256'], purpose='one_model_free_reobservation'))
        deadline = time.monotonic() + 60
        try:
            observed, last = operator_probe.collect_baseline(collect, log, query_factory=factory)
            frames = [q.value for q in self.bootstrap_queries if q.done.is_set()]
            while True:
                if not all(q.done.is_set() for q in self.bootstrap_queries):
                    raise ValueError('bootstrap_collector_not_terminal')
                fresh = not _frame_reasons(last, now=time.monotonic(),
                    now_utc=datetime.now(timezone.utc), max_age=2)
                recovered = (fresh and not recovery_reasons(previous, frames[-5:])
                    and not _rising_residual(frames[-5:])
                    and last.snapshot['commit_headroom_bytes'] >= 84 * 2**30
                    and not any(item['pid'] == old['identity']['pid'] for item in last.snapshot['raw']['processes']))
                if recovered and time.monotonic() <= deadline:
                    break
                earliest = max(time.monotonic(), last.query_start + operator_probe.QUERY_INTERVAL)
                if earliest + operator_probe.MAX_QUERY_SECONDS > deadline:
                    raise TimeoutError('fresh_v1_recovery_not_established')
                last = operator_probe.collect_one(collect, log, 'late_recovery',
                    last.query_start, query_factory=factory)
                frames.append(last)
            bootstrap_latch()
            exclusive_json(BOOTSTRAP_CERTIFICATE, dict(evaluation=EVALUATION,
                disposition='later_observed_recovery_not_original_deadline_success',
                old_latch_sha256=BOOTSTRAP_SHA, evidence=operator_store.artifact_record(log),
                final_five_query_starts=[f.query_start for f in frames[-5:]],
                collector_terminal=True, gpu_attempt_not_started=True))
            bootstrap_latch()
            if BOOTSTRAP_ARCHIVE.exists():
                raise ValueError('bootstrap_archive_exists')
            # Windows rename refuses an existing target; no historical evidence is deleted.
            (self.EVIDENCE / 'incomplete.json').rename(BOOTSTRAP_ARCHIVE)
        except BaseException as error:
            exclusive_json(self.EVIDENCE / ('bootstrap-reobserve-failed-' + uuid.uuid4().hex + '.json'),
                dict(phase='late_recovery_failed', evaluation=EVALUATION,
                     failure=type(error).__name__ + ':' + str(error),
                     collector_terminal=all(q.done.is_set() for q in self.bootstrap_queries)))
            raise
        records += [operator_store.artifact_record(log), checked(BOOTSTRAP_ARCHIVE, BOOTSTRAP_SHA),
                    operator_store.artifact_record(BOOTSTRAP_CERTIFICATE),
                    operator_store.artifact_record(REOBSERVATION_ATTEMPT)]
        manifest = dict(profile=p.profile_id, source=p.source_commit, bounds=dict(p.bounds),
            **candidate, **benchmark, margin_report=margin,
            qualification=qualification, qualification_stamp=qualification_stamp,
            operator=dict(original_baseline=asdict(self.original), state=state,
                historical_baseline=asdict(historical)),
            repeat=dict(evaluation=EVALUATION, boot_utc=prior.BOOT_UTC,
                prior_failures_and_latches_retained=True, original_failed_recovery_not_certified=True,
                later_recovery_observed=asdict(observed), records=records))
        self.manifest_bytes = recipes.canonical(manifest)
        return manifest

    def recheck_static(self, manifest, *, current_run=None):
        if recipes.canonical(manifest) != self.manifest_bytes:
            raise ValueError('repeat_manifest_changed')
        self.history()
        operator_store.source_identity()
        smoke_store._recheck_candidate_artifacts(manifest, self.PINS)
        smoke_store._recheck_benchmark(manifest, self.PINS)
        for record in [*manifest['operator']['state'], manifest['margin_report'],
                       manifest['qualification_stamp'], *manifest['repeat']['records']]:
            if operator_store.stamp(record['stamp'][0]) != record['stamp']:
                raise ValueError('repeat_artifact_changed')
        if current_run is None:
            if any((self.EVIDENCE / name).exists() for name in ('attempt.json', 'incomplete.json')):
                raise ValueError('repeat_already_attempted_or_incomplete')
        else:
            smoke_store._current_run_markers(manifest, self.marker_pins, current_run)

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if (run_dir.resolve().parent != self.EVIDENCE or run_dir.is_symlink()
                or asdict(baseline) != manifest['operator']['original_baseline']):
            raise ValueError('repeat_run_mismatch')
        for path, value in (
            (self.EVIDENCE / 'attempt.json', dict(run=str(run_dir), profile=self.PINS.profile_id, evaluation=EVALUATION)),
            (self.EVIDENCE / 'incomplete.json', dict(run=str(run_dir), phase='before_create', original_baseline=asdict(baseline))),
            (run_dir / 'manifest.json', manifest)):
            with path.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())


def main():
    store = NativeRepeatStore()
    guardian = _Guardian(store=store, policy_module=BoundPolicy(store.PINS),
        profile_id=recipes.PROFILE_16K, collect=collect,
        argv_builder=lambda secret: recipes.build_argv(recipes.PROFILE_16K, secret))
    def start(**kwargs):
        return start_suite(profile_id=recipes.PROFILE_16K, evidence_dir=guardian.run_dir, **kwargs)
    guardian.http_start = start
    result = guardian.run()
    print(json.dumps({key: result.get(key) for key in
        ('success', 'failure', 'run', 'cleanup_confirmed', 'exit_code', 'http')}, allow_nan=False))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
