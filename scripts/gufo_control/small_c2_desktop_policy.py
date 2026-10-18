"""Reviewed fixed-window active-desktop admission, only for the finite C2 run.

Bounded desktop variation consumes EXTRA admission reserves, not model memory.
Runtime and post-model recovery remain inherited and unchanged.
"""
from dataclasses import asdict
import time

from . import complete_answer_run, operator_probe
from .operator_policy import Baseline, GPU_FIELDS, MAX_QUERY_SECONDS, _identity, _series
from .smoke_guard import _Guardian

GIB = 1024**3
MIB = 1024**2
PHYSICAL_ADMISSION = 50*GIB
COMMIT_ADMISSION = 91*GIB
SPANS = {'available_physical_bytes': GIB, 'host_committed_bytes': 2*GIB,
         **{key: 256*MIB for key in GPU_FIELDS}}


def definition():
    return dict(kind='fixed_active_desktop_c2', samples=11, minimum_seconds=10,
        maximum_seconds=30, span_caps_bytes=SPANS.copy(),
        physical_admission_bytes=PHYSICAL_ADMISSION,
        commit_admission_headroom_bytes=COMMIT_ADMISSION,
        extra_physical_variation_reserve_bytes=GIB,
        extra_commit_variation_reserve_bytes=2*GIB,
        prelaunch_zero_amplitude_trend_veto=False,
        all_samples_retained=True, post_model_recovery_unchanged=True,
        runtime_floors_and_original_strict_baseline_unchanged=True)


def variation_baseline(frames):
    errors = _series(frames)
    if errors:
        raise ValueError(errors[0])
    if len(frames) != 11 or not 10 <= frames[-1].query_end-frames[0].query_start <= 30:
        raise ValueError('desktop_baseline_duration')
    for key, cap in SPANS.items():
        values = [frame.snapshot[key] for frame in frames]
        if max(values)-min(values) > cap:
            raise ValueError('desktop_baseline_variation:'+key)
    if any(frame.snapshot['available_physical_bytes'] < PHYSICAL_ADMISSION
           or frame.snapshot['commit_headroom_bytes'] < COMMIT_ADMISSION for frame in frames):
        raise ValueError('desktop_extra_reserve_missing')
    return Baseline(_identity(frames[0].snapshot),
        min(frame.snapshot['available_physical_bytes'] for frame in frames),
        max(frame.snapshot['host_committed_bytes'] for frame in frames),
        tuple(max(frame.snapshot[key] for frame in frames) for key in GPU_FIELDS),
        frames[0].query_start,frames[-1].query_end)


class Policy(complete_answer_run.Policy):
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
            if frame.snapshot['commit_headroom_bytes'] < COMMIT_ADMISSION:
                decision['reasons'].append('desktop_commit_reserve')
        decision['allowed'] = not decision['reasons']
        decision['desktop_admission'] = definition()
        return decision

    def admission_reasons(self, profile, base, frame, **kwargs):
        return self.admission_decision(profile,base,frame,**kwargs)['reasons']


class Guardian(_Guardian):
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
        self._write('desktop-baseline.json',dict(policy=definition(),
            current=asdict(current),samples=len(frames),
            spans_bytes={key:max(f.snapshot[key] for f in frames)-min(f.snapshot[key] for f in frames)
                         for key in SPANS}))
        return current,frames[-1]

    def _baseline_trend_reasons(self, frames):
        # No owned allocation exists yet. Fixed-window variation is bounded and
        # charged above; the post-allocation recovery trend rule is NOT changed.
        variation_baseline(frames)
        return []
