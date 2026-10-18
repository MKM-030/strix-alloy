"""One reviewed fresh C2 admission after a preserved no-process rejection."""
from hashlib import sha256
import json
from pathlib import Path

from . import small_c2_run as previous, small_c2_recipe as recipe
from . import complete_answer_run, operator_store, service_recovery
from . import pp_remeasure as prior, pp_remeasure_native as native
from .smoke_guard import _Guardian
from .small_c2_suite import start_suite

FAILED_RUN = previous.Store.EVIDENCE / '20260927T194542Z-fdeb062133d446f6a2d0bd4621b0d447'
FAILED_SHA = '2D5EBE733145123AEE52029526F8F80C1CCCB7F6FFCDECBF1930D48CA4905AB8'


class Store(previous.Store):
    # Same reviewed workload; a new one-use admission identity preserves all v1 markers.
    MODULE = Path(__file__)
    EVIDENCE = prior.REPORTS / (recipe.ID + '-admission2-runs')
    APPROVAL = prior.REPORTS / (recipe.ID + '-admission2-approval.json')
    HELPERS = (*previous.Store.HELPERS, 'small_c2_run.py')

    def history(self):
        original = super().history()
        failed = service_recovery.read_pinned(FAILED_RUN/'result.json', FAILED_SHA)
        if (failed['success'] is not False or failed['cleanup_confirmed'] is not True
                or failed['failure'] != 'ValueError:original_baseline:rising_residual'
                or failed['resumed_monotonic'] is not None or failed['identity'] is not None
                or failed['http'] is not None or failed['exit_code'] is not None
                or failed['collector_terminal'] is not True
                or failed['collector_queries'] != failed['collector_completed_queries']):
            raise ValueError('prelaunch_failure_not_clean_or_unchanged')
        if any((previous.Store.EVIDENCE/name).exists() for name in ('attempt.json','incomplete.json')):
            raise ValueError('previous_launch_attempt_or_cleanup_unconfirmed')
        return original

    def verify_static(self):
        approval = operator_store.read_json(self.APPROVAL)
        if approval.get('admission') != 'second_after_reviewed_zero_process_rejection':
            raise ValueError('requalification_review_missing')
        audit = native.checked(approval['prelaunch_audit_path'], approval['prelaunch_audit_sha256'])
        manifest = super().verify_static()
        manifest['evaluation']['records'].extend([audit,
            native.checked(FAILED_RUN/'result.json', FAILED_SHA),
            operator_store.artifact_record(previous.Store.EVIDENCE/'verification-attempt.json')])
        manifest['evaluation']['admission'] = dict(identity='second_after_reviewed_zero_process_rejection',
            previous_run=str(FAILED_RUN),previous_result_sha256=FAILED_SHA,
            previous_inference_requests=0,guard_and_thresholds_unchanged=True)
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest


def main():
    store = Store()
    guardian = _Guardian(store=store,policy_module=complete_answer_run.Policy(store),
        profile_id=store.ID,collect=native.collect,argv_builder=store.build_argv)
    guardian.http_start = lambda **kw:start_suite(profile_id=store.ID,evidence_dir=guardian.run_dir,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
