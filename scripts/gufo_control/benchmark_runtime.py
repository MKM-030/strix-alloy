"""Private immutable-profile adapters; importing this module cannot launch a run."""
from functools import partial

from . import operator_store, smoke_store, smoke_policy


class BoundStore:
    def __init__(self, pins):
        smoke_store._binding(pins)
        self.PINS = pins
        self.BUILD = pins.build
        self.EVIDENCE = pins.evidence

    def verify_static(self):
        return smoke_store._verify_static(self.PINS,
            source_validator=operator_store.source_identity,
            model_validator=smoke_store.validate_ar4k_model)

    def recheck_static(self, manifest, *, current_run=None):
        return smoke_store._recheck_static(manifest, self.PINS,
            source_validator=operator_store.source_identity, current_run=current_run)

    def load_original_operator_baseline(self):
        return smoke_store._load_original_operator_baseline(self.PINS)

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        return smoke_store._begin_run(run_dir, manifest, baseline, self.PINS)

    def finish_run(self, run_dir, result):
        return smoke_store._finish_run(run_dir, result, self.PINS)


class BoundPolicy:
    def __init__(self, pins):
        smoke_store._binding(pins)
        for name in ('profile_from_manifest', '_profile_valid', '_common',
                     'admission_decision', 'admission_reasons', 'runtime_decision',
                     'runtime_reasons', 'frame_numeric_reasons'):
            setattr(self, name, partial(getattr(smoke_policy, name), pins=pins))

    owned_inventory_frame = staticmethod(smoke_policy.owned_inventory_frame)
    baseline = staticmethod(smoke_policy.baseline)
    stricter_runtime_baseline = staticmethod(smoke_policy.stricter_runtime_baseline)
    recovery_reasons = staticmethod(smoke_policy.recovery_reasons)
