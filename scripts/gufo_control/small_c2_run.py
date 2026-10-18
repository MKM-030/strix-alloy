"""One small two-session experiment, after the complete-answer C1 audit."""
from hashlib import sha256
import json
from pathlib import Path

from . import complete_answer_run as previous, small_c2_recipe as recipe
from . import operator_store, service_recovery
from . import pp_remeasure as prior, pp_remeasure_native as native
from .smoke_guard import _Guardian
from .small_c2_suite import start_suite

C1_RUN = previous.Store.EVIDENCE / '20260927T193706Z-3afd151ef6a94b3e9b31a692f572e892'
C1_SHA = '303D2148F8625D5A468D278C4EF513070D6D3EDE797511BDCB8F3ABD474B2DE2'


class Store(previous.Store):
    RECIPE = recipe
    MODULE = Path(__file__)
    ID = recipe.ID
    EVIDENCE = prior.REPORTS / (ID + '-runs')
    APPROVAL = prior.REPORTS / (ID + '-approval.json')
    HELPERS = (*previous.Store.HELPERS, 'complete_answer_run.py',
               'small_c2_recipe.py', 'small_c2_suite.py')

    @staticmethod
    def build_argv(secret):
        argv = previous.Store.build_argv(secret)
        for flag in ('--sessions', '--max-pending', '--max-pending-per-client'):
            argv[argv.index(flag)+1] = '2'
        return argv

    def history(self):
        original = super().history()
        result = service_recovery.read_pinned(C1_RUN/'result.json', C1_SHA)
        if not result['success'] or not result['cleanup_confirmed'] or result['exit_code'] != 0:
            raise ValueError('c1_run_not_clean')
        rows = result['http']['rows']
        if len(rows) != 7 or any(r['status'] != 'completed' for r in rows):
            raise ValueError('c1_run_incomplete')
        for ordinal, case, count in ((1,'code_a',376),(2,'proof_a',703)):
            row = rows[ordinal]
            if (row['case'] != case or row['finish_reason'] != 'stop'
                    or row['metrics']['completion_tokens'] != count):
                raise ValueError('c1_reference_mismatch')
        return original

    def verify_static(self):
        approval = operator_store.read_json(self.APPROVAL)
        review = native.checked(approval['c1_audit_path'], approval['c1_audit_sha256'])
        manifest = super().verify_static()
        manifest['evaluation']['records'].extend([
            review, native.checked(C1_RUN/'result.json', C1_SHA)])
        manifest['evaluation']['c1_reference'] = dict(run=str(C1_RUN), result_sha256=C1_SHA,
            scope='Manually reviewed code_a/proof_a only; no whole-model semantic certification')
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest


def main():
    store = Store()
    guardian = _Guardian(store=store,policy_module=previous.Policy(store),profile_id=store.ID,
        collect=native.collect,argv_builder=store.build_argv)
    guardian.http_start = lambda **kw:start_suite(profile_id=store.ID,evidence_dir=guardian.run_dir,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
