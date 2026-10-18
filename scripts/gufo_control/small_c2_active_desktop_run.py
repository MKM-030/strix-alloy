"""One reviewed C2 measurement after exact no-allocation disposition."""
from hashlib import sha256
import json
from pathlib import Path

from . import small_c2_run, small_c2_requalify
from . import small_c2_no_allocation as disposition
from . import small_c2_desktop_policy as desktop
from . import operator_store, pp_remeasure as prior, pp_remeasure_native as native
from .small_c2_suite import start_suite


class Store(small_c2_requalify.Store):
    MODULE = Path(__file__)
    EVIDENCE = prior.REPORTS / 'small-c2-active-desktop-20260927-v1-runs'
    APPROVAL = prior.REPORTS / 'small-c2-active-desktop-20260927-v1-approval.json'
    HELPERS = (*small_c2_requalify.Store.HELPERS, 'small_c2_requalify.py',
        'small_c2_no_allocation.py', 'small_c2_desktop_policy.py')

    def history(self):
        original = super().history()
        disposition.certificate()
        return original

    def verify_static(self):
        approval = operator_store.read_json(self.APPROVAL)
        if (approval.get('admission') != 'active_desktop_reserved_variation'
                or approval.get('desktop_policy') != desktop.definition()
                or approval.get('intended_run_root') != str(self.EVIDENCE)):
            raise ValueError('desktop_admission_review_missing')
        policy_review = native.checked(approval['desktop_review_path'],approval['desktop_review_sha256'])
        if not disposition.CERTIFICATE.exists():
            disposition.create_certificate(self.APPROVAL)
        records = disposition.certificate()
        # Reuse the original C2 manifest constructor, not admission2's already
        # consumed requalification identity. History still authenticates BOTH.
        manifest = small_c2_run.Store.verify_static(self)
        manifest['evaluation']['records'].extend([policy_review,*records])
        manifest['evaluation']['admission'] = dict(identity='active_desktop_reserved_variation',
            desktop_policy=desktop.definition(), historical_disposition=str(disposition.CERTIFICATE),
            original_failed_result_and_latch_unchanged=True)
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest


def main():
    store = Store()
    guardian = desktop.Guardian(store=store,policy_module=desktop.Policy(store),
        profile_id=store.ID,collect=native.collect,argv_builder=store.build_argv)
    guardian.http_start = lambda **kw:start_suite(profile_id=store.ID,evidence_dir=guardian.run_dir,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
