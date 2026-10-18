"""One reviewed post-reboot repetition of the unchanged AR16k PP recipe.

Historical failures and consumed attempts stay intact. No service qualification.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from . import benchmark_guard, benchmark_recipes as recipes, operator_probe
from . import operator_store, service_recovery, smoke_store
from .benchmark_runtime import BoundPolicy
from .benchmark_suite import start_suite
from .operator_policy import _identity, _frame_reasons
from .smoke_guard import _Guardian, check_port, _rising_residual
from .telemetry import collect_snapshot

EVALUATION = 'gufo-pp-repeat-20260927-v1'
REPORTS = smoke_store.ROOT / 'reports'
EVIDENCE = REPORTS / (EVALUATION + '-runs')
APPROVAL = REPORTS / (EVALUATION + '-approval.json')
BOOT_UTC = '2026-09-27T14:05:41.5000000Z'
PREVIOUS_PP = REPORTS / 'gufo-ar16k-benchmark-v3-runs' / '20260926T193218Z-fff245a054a3452bba9ba84a3a7b27a2' / 'result.json'
PREVIOUS_PP_SHA = 'A813E83F9EBF362D065DA73E0F7A25ED563CBB1CF0C9888952BC8A679A099809'


class RepeatStore:
    EVIDENCE = EVIDENCE

    def __init__(self):
        self.PINS = benchmark_guard.profile_pins(recipes.PROFILE_16K)
        self.BUILD = self.PINS.build
        self.marker_pins = replace(self.PINS, evidence=self.EVIDENCE)
        self.original = self.manifest_bytes = None
        self.bootstrap_queries = []
        self.boot = None

    def history(self):
        # Exact failed record: original process exited, only recovery floor failed.
        failed = service_recovery.pinned_state()
        service_recovery.require_pid_absent()
        previous = service_recovery.read_pinned(PREVIOUS_PP, PREVIOUS_PP_SHA)
        if previous['success'] is not True or previous['cleanup_confirmed'] is not True:
            raise ValueError('previous_pp_not_clean')
        roots = {self.EVIDENCE, *(REPORTS / name for name in (
            'gufo-ar4k-smoke-runs', 'gufo-ar4k-connect-wait-smoke-runs',
            'gufo-ar4k-benchmark-runs', 'gufo-ar16k-benchmark-runs',
            'gufo-ar16k-benchmark-v2-runs', *smoke_store.PROFILE_ROOTS.values()))}
        for root in roots:
            if root == self.EVIDENCE or root == service_recovery.ROOT:
                continue
            if (root / 'incomplete.json').exists():
                raise ValueError('other_history_incomplete')
        return failed

    def verify_static(self):
        p = self.PINS
        if self.EVIDENCE.resolve() != self.EVIDENCE or self.EVIDENCE.is_symlink():
            raise ValueError('repeat_root_redirected')
        if any((self.EVIDENCE / name).exists() for name in ('attempt.json', 'incomplete.json')):
            raise ValueError('repeat_already_attempted_or_incomplete')
        failed = self.history()
        approval = operator_store.read_json(APPROVAL)
        code_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()
        if (approval.get('evaluation') != EVALUATION or approval.get('module_sha256') != code_sha
                or approval.get('decision') != 'approved'
                or approval.get('recipe_sha256') != hashlib.sha256(recipes.recipe_json(recipes.PROFILE_16K).encode()).hexdigest().upper()
                or not approval.get('review_path') or not approval.get('review_sha256')
                or operator_store.artifact_record(approval['review_path'])['sha256'] != approval['review_sha256']):
            raise ValueError('repeat_review_missing_or_changed')
        operator_store.source_identity()
        candidate = smoke_store._verify_candidate_artifacts(p, model_validator=smoke_store.validate_ar4k_model)
        historical, state = smoke_store._operator_sequence(p)
        benchmark = smoke_store._benchmark_records(p)
        qualification, qualification_stamp = smoke_store._qualification(p)
        margin = smoke_store._checked_artifact(p.margin_report,
            (p.margin_report.stat().st_size, p.margin_sha256), 'margin_report')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        proc = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command',
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        self.boot = proc.stdout.strip()
        if proc.returncode or self.boot != BOOT_UTC:
            raise ValueError('unexpected_boot_epoch')
        boot_time = datetime.fromisoformat(self.boot.replace('Z', '+00:00'))
        failed_started = datetime.strptime(service_recovery.RUN.name[:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if boot_time <= failed_started or time.monotonic() >= failed['current_baseline']['last_end']:
            raise ValueError('new_boot_not_established')
        check_port()
        log = self.EVIDENCE / ('epoch-baseline-' + uuid.uuid4().hex + '.jsonl')

        def query_factory(collect):
            query = operator_probe.Query(collect)
            self.bootstrap_queries.append(query)
            return query

        try:
            self.original, last = operator_probe.collect_baseline(collect_snapshot, log, query_factory=query_factory)
            frames = [query.value for query in self.bootstrap_queries if query.done.is_set()]
            if (not all(q.done.is_set() for q in self.bootstrap_queries)
                    or _frame_reasons(last, now=time.monotonic(), now_utc=datetime.now(timezone.utc), max_age=2)
                    or self.original.identity[1:] != tuple(failed['current_baseline']['identity'][1:])
                    or self.original.identity[0] == failed['current_baseline']['identity'][0]
                    or last.snapshot['available_physical_bytes'] < 49 * 2**30
                    or last.snapshot['commit_headroom_bytes'] < 84 * 2**30
                    or _rising_residual(frames[-5:])):
                raise ValueError('fresh_epoch_baseline_invalid')
        except BaseException:
            operator_store.atomic_json(self.EVIDENCE / 'incomplete.json',
                dict(phase='epoch_baseline_failed', evaluation=EVALUATION,
                     collector_terminal=all(q.done.is_set() for q in self.bootstrap_queries)))
            raise
        manifest = dict(profile=p.profile_id, source=p.source_commit, bounds=dict(p.bounds),
            **candidate, **benchmark, margin_report=margin,
            qualification=qualification, qualification_stamp=qualification_stamp,
            operator=dict(original_baseline=asdict(self.original), state=state,
                historical_baseline=asdict(historical)),
            repeat=dict(evaluation=EVALUATION, boot_utc=self.boot,
                baseline_kind='observed_current_boot_baseline', baseline_evidence=operator_store.artifact_record(log),
                original_failed_run_unchanged=True, original_failed_recovery_not_certified=True,
                failed_result_sha256=service_recovery.RESULT_SHA, retained_latch_sha256=service_recovery.LATCH_SHA,
                previous_pp_result_sha256=PREVIOUS_PP_SHA,
                approval=operator_store.artifact_record(APPROVAL),
                review=operator_store.artifact_record(approval['review_path']),
                module=operator_store.artifact_record(Path(__file__))))
        self.manifest_bytes = recipes.canonical(manifest)
        return manifest

    def load_original_operator_baseline(self):
        if self.original is None:
            raise ValueError('epoch_baseline_missing')
        return self.original

    def recheck_static(self, manifest, *, current_run=None):
        if recipes.canonical(manifest) != self.manifest_bytes:
            raise ValueError('repeat_manifest_changed')
        self.history()
        operator_store.source_identity()
        smoke_store._recheck_candidate_artifacts(manifest, self.PINS)
        smoke_store._recheck_benchmark(manifest, self.PINS)
        records = [*manifest['operator']['state'], manifest['margin_report'], manifest['qualification_stamp'],
                   *(manifest['repeat'][key] for key in ('baseline_evidence', 'approval', 'review', 'module'))]
        for record in records:
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
        # exclusive_json refuses replacement; the Guardian holds both existing locks.
        for path, value in (
            (self.EVIDENCE / 'attempt.json', dict(run=str(run_dir), profile=self.PINS.profile_id, evaluation=EVALUATION)),
            (self.EVIDENCE / 'incomplete.json', dict(run=str(run_dir), phase='before_create', original_baseline=asdict(baseline))),
            (run_dir / 'manifest.json', manifest)):
            with path.open('x', encoding='utf-8') as stream:
                json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())

    def finish_run(self, run_dir, result):
        smoke_store._finish_run(run_dir, result, self.marker_pins)


def main():
    store = RepeatStore()
    guardian = _Guardian(store=store, policy_module=BoundPolicy(store.PINS),
        profile_id=recipes.PROFILE_16K,
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
