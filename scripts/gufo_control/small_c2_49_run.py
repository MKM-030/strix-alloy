"""User-requested 49 GiB admission for one unchanged small C2 workload.

49 - 4 host - 20 shared - 1 desktop variation = 24 GiB runtime floor.
Historical no-child failures stay immutable; no public recovery bypass.
"""
from dataclasses import asdict
import json
from pathlib import Path
import time

from . import small_c2_active_desktop_run as previous, small_c2_run
from . import small_c2_desktop_policy as desktop, small_c2_no_allocation as disposition
from . import operator_store, operator_probe, service_recovery
from . import pp_remeasure as prior, pp_remeasure_native as native
from .operator_policy import Baseline, GPU_FIELDS, MAX_QUERY_SECONDS, _identity, _series
from .small_c2_suite import start_suite

GIB = 1024**3
PHYSICAL_ADMISSION = 49*GIB
FAILED_ROOT = previous.Store.EVIDENCE
FAILED_RUN = FAILED_ROOT/'20260927T203739Z-df3bb0bc60474298a15928a86e934e54'
FAILED_SHA = '36D2835AEB1190E46574AE0BF4115FD67A935384B5BEF444BF9C1A17C72BB252'
HISTORY = (
    (FAILED_RUN/'result.json', FAILED_SHA),
    (FAILED_ROOT/'incomplete.json', '1D0CE5152A619AF7765C5254E225093EC56E2CA369C67847FBB571504A910805'),
    (FAILED_ROOT/'verification-attempt.json', '464999434B510ED9E092452723F3FA9774685A760AB879F0C1FB0837F2189CF8'),
    (FAILED_RUN/'telemetry.jsonl', '7F5E14922411A6B2DBEA6953AD8A8F4965F238BCD0422BC5591F9C7306FCD114'),
    (prior.REPORTS/'small-c2-active-desktop-audit-20260927.md', '5D4B876103D843D6FD336EEE75FA3C599B4AA4D11E6522E82DB9BD89C344C593'),
)


def definition():
    value = desktop.definition()
    value.update(kind='fixed_active_desktop_c2_49', physical_admission_bytes=PHYSICAL_ADMISSION)
    return value


def history_records():
    for directory in (FAILED_ROOT, FAILED_RUN):
        disposition._directory(directory)
    disposition._files_only(FAILED_ROOT, {FAILED_RUN.name, 'runner.lock',
        'verification-attempt.json', 'incomplete.json'})
    disposition._files_only(FAILED_RUN, {'decisions.jsonl','phase.json','result.json','telemetry.jsonl'})
    records = [native.checked(path,digest) for path,digest in HISTORY]
    result = service_recovery.read_pinned(FAILED_RUN/'result.json', FAILED_SHA)
    if (result['success'] is not False or result['cleanup_confirmed'] is not False
            or result['failure'] != 'ValueError:desktop_baseline_admission:desktop_physical_reserve;RuntimeError:recovery_unconfirmed'
            or result['run'] != str(FAILED_RUN) or result['profile'] != small_c2_run.Store.ID
            or result['runtime_samples'] != 0 or result['service_ready'] is not False):
        raise ValueError('historical_no_child_outcome_changed')
    for key in ('current_baseline','runtime_baseline','identity','resumed_monotonic','http','exit_code','module_inspection'):
        if result[key] is not None:
            raise ValueError('historical_owned_activity:'+key)
    if any(result[key] is not True for key in disposition.TERMINAL_FLAGS):
        raise ValueError('historical_worker_not_terminal')
    if any(result[key] != 59 for key in ('collector_queries','collector_completed_queries','collector_retained_queries')):
        raise ValueError('historical_query_count_changed')
    return records


def variation_baseline(frames):
    errors = _series(frames)
    if errors:
        raise ValueError(errors[0])
    if len(frames) != 11 or not 10 <= frames[-1].query_end-frames[0].query_start <= 30:
        raise ValueError('desktop_baseline_duration')
    for key, cap in desktop.SPANS.items():
        values = [frame.snapshot[key] for frame in frames]
        if max(values)-min(values) > cap:
            raise ValueError('desktop_baseline_variation:'+key)
    if any(frame.snapshot['available_physical_bytes'] < PHYSICAL_ADMISSION
           or frame.snapshot['commit_headroom_bytes'] < desktop.COMMIT_ADMISSION for frame in frames):
        raise ValueError('desktop_extra_reserve_missing')
    return Baseline(_identity(frames[0].snapshot),
        min(frame.snapshot['available_physical_bytes'] for frame in frames),
        max(frame.snapshot['host_committed_bytes'] for frame in frames),
        tuple(max(frame.snapshot[key] for frame in frames) for key in GPU_FIELDS),
        frames[0].query_start,frames[-1].query_end)


class Policy(desktop.Policy):
    def admission_decision(self, profile, base, frame, **kwargs):
        decision = self.parent.admission_decision(profile,base,frame,**kwargs)
        decision['desktop_predicted_available_after_reserve_bytes'] = None
        decision['desktop_predicted_commit_after_reserve_bytes'] = None
        if not decision['reasons']:
            decision['desktop_predicted_available_after_reserve_bytes'] = (
                frame.snapshot['available_physical_bytes']-profile.host_peak_bytes
                -profile.shared_physical_allowance_bytes-GIB)
            decision['desktop_predicted_commit_after_reserve_bytes'] = (
                frame.snapshot['commit_headroom_bytes']-profile.commit_peak_bytes-2*GIB)
            if frame.snapshot['available_physical_bytes'] < PHYSICAL_ADMISSION:
                decision['reasons'].append('desktop_physical_reserve')
            if frame.snapshot['commit_headroom_bytes'] < desktop.COMMIT_ADMISSION:
                decision['reasons'].append('desktop_commit_reserve')
        decision['allowed'] = not decision['reasons']
        decision['desktop_admission'] = definition()
        return decision


class Guardian(desktop.Guardian):
    def _collect_initial_baseline(self):
        frames = []
        deadline = time.monotonic()+30
        for _ in range(11):
            earliest = max(time.monotonic(),
                frames[-1].query_start+operator_probe.QUERY_INTERVAL if frames else 0)
            if earliest+MAX_QUERY_SECONDS > deadline:
                raise TimeoutError('desktop_baseline_timeout')
            frame = operator_probe.collect_one(self.collect,self.run_dir/'telemetry.jsonl',
                'baseline',frames[-1].query_start if frames else None,query_factory=self._query)
            frames.append(frame)
            if frame.query_end > deadline:
                raise TimeoutError('desktop_baseline_timeout')
            reasons = self.policy.admission_reasons(self.profile,self.original,frame,
                now=frame.query_end,now_utc=frame.validated_utc)
            if reasons:
                raise ValueError('desktop_baseline_admission:'+','.join(reasons))
        current = variation_baseline(frames)
        self._write('desktop-baseline.json',dict(policy=definition(),current=asdict(current),
            samples=len(frames),spans_bytes={key:max(f.snapshot[key] for f in frames)
                -min(f.snapshot[key] for f in frames) for key in desktop.SPANS}))
        return current,frames[-1]

    def _baseline_trend_reasons(self, frames):
        variation_baseline(frames)
        return []


class Store(previous.Store):
    MODULE = Path(__file__)
    EVIDENCE = prior.REPORTS/'small-c2-49-20260928-v1-runs'
    APPROVAL = prior.REPORTS/'small-c2-49-20260928-v1-approval.json'
    HELPERS = (*previous.Store.HELPERS, 'small_c2_active_desktop_run.py')

    def history(self):
        original = super().history()
        history_records()
        return original

    def verify_static(self):
        approval = operator_store.read_json(self.APPROVAL)
        if (approval.get('admission') != 'user_requested_49_gib'
                or approval.get('desktop_policy') != definition()
                or approval.get('intended_run_root') != str(self.EVIDENCE)
                or approval.get('historical_disposition') != 'exact_no_child_not_recovered'):
            raise ValueError('reviewed_49_policy_missing')
        records = [*history_records(), *disposition.certificate(),
            native.checked(approval['desktop_review_path'],approval['desktop_review_sha256'])]
        manifest = small_c2_run.Store.verify_static(self)
        manifest['evaluation']['records'].extend(records)
        manifest['evaluation']['admission'] = dict(identity='user_requested_49_gib',
            desktop_policy=definition(),historical_no_child_run=str(FAILED_RUN),
            historical_result_sha256=FAILED_SHA,original_failed_result_and_latch_unchanged=True,
            historical_recovery_not_claimed=True)
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest


def main():
    store = Store()
    guardian = Guardian(store=store,policy_module=Policy(store),profile_id=store.ID,
        collect=native.collect,argv_builder=store.build_argv)
    guardian.http_start = lambda **kw:start_suite(profile_id=store.ID,evidence_dir=guardian.run_dir,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
