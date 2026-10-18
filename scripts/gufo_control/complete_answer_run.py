"""One-use complete-answer qualification; reuses the reviewed native lifecycle."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from . import complete_answer_recipe as recipe, halogen_mtp_run as previous
from . import matched_profile, operator_store, smoke_store, service_recovery
from . import pp_remeasure_native as native, pp_remeasure as prior
from .benchmark_runtime import BoundPolicy
from .benchmark_suite import start_suite
from .smoke_guard import _Guardian, check_port

LAST_RUN = previous.EVIDENCE / '20260927T173323Z-57ca3e581dda4a57a9cb39a178f4c9e4'
LAST_SHA = '30B4E7B45848F16526F579A9288C7ACB0325D291B583CC94CFF79A73144BFDF8'
RUN_ROOTS = ('halogen-ten-mtp-d3-20260927-v1-runs',
             'complete-answer-mtp-d3-20260927-v1-runs',
             'small-c2-mtp-d3-20260927-v1-runs')


class Policy:
    def __init__(self, store):
        self.store = store
        self.parent = BoundPolicy(store.PINS)

    def __getattr__(self, name):
        return getattr(self.parent, name)

    def profile_from_manifest(self, manifest):
        return self.parent.profile_from_manifest(self.store.runtime_view(manifest))


class Store(previous.Store):
    RECIPE = recipe
    MODULE = Path(__file__)
    ID = recipe.ID
    EVIDENCE = prior.REPORTS / (ID + '-runs')
    APPROVAL = prior.REPORTS / (ID + '-approval.json')
    HELPERS = (*previous.HELPERS, 'halogen_mtp_run.py', 'complete_answer_recipe.py')

    def __init__(self):
        super().__init__()
        self.marker_pins = replace(self.PINS, profile_id=self.ID, evidence=self.EVIDENCE)

    @staticmethod
    def build_argv(secret):
        argv = matched_profile.build_argv(previous.PARENT_ID, secret)
        argv[argv.index('--max-tokens')+1] = '1024'
        return argv

    def runtime_view(self, manifest):
        if (manifest['profile'] != self.ID
                or manifest['workload'] != self.RECIPE.recipe_definition(self.ID)
                or manifest['workload_sha256'] != sha256(self.RECIPE.recipe_json(self.ID).encode()).hexdigest().upper()
                or manifest['reviewed_argv'] != self.build_argv('[REDACTED]')):
            raise ValueError('workload_binding_changed')
        view = dict(manifest)
        view.update(manifest['historical_runtime_reference'])
        view['profile'] = previous.PARENT_ID
        return view

    def history(self):
        old = super().history()
        for name in RUN_ROOTS:
            root = prior.REPORTS/name
            if root != self.EVIDENCE and (root/'incomplete.json').exists():
                raise ValueError('other_evaluation_cleanup_incomplete')
        result = service_recovery.read_pinned(LAST_RUN/'result.json', LAST_SHA)
        if not result['success'] or not result['cleanup_confirmed'] or result['exit_code'] != 0:
            raise ValueError('last_mtp_run_not_clean')
        return old

    def verify_static(self):
        root = self.EVIDENCE
        if root.is_symlink() or root.resolve() != root:
            raise ValueError('evidence_redirected')
        if any((root/n).exists() for n in ('attempt.json','incomplete.json','verification-attempt.json')):
            raise ValueError('attempt_consumed')
        old = self.history()
        a = operator_store.read_json(self.APPROVAL)
        digest = sha256(self.RECIPE.recipe_json(self.ID).encode()).hexdigest().upper()
        if (a.get('evaluation') != self.ID or a.get('decision') != 'approved'
                or a.get('module_sha256') != sha256(self.MODULE.read_bytes()).hexdigest().upper()
                or a.get('recipe_sha256') != digest or set(a.get('helpers',{})) != set(self.HELPERS)
                or a.get('reviewed_argv') != self.build_argv('[REDACTED]')):
            raise ValueError('review_binding_missing')
        records = [native.checked(a['review_path'],a['review_sha256']),
            native.checked(a['envelope_review_path'],a['envelope_review_sha256']),
            operator_store.artifact_record(self.APPROVAL), operator_store.artifact_record(self.MODULE),
            native.checked(self.RECIPE.CORPUS,self.RECIPE.CORPUS_SHA), *native.probe_records(),
            native.checked(LAST_RUN/'result.json',LAST_SHA)]
        records += [native.checked(self.MODULE.with_name(n),h) for n,h in a['helpers'].items()]
        p = self.PINS
        operator_store.source_identity()
        candidate = smoke_store._verify_candidate_artifacts(p,model_validator=smoke_store.validate_ar4k_model)
        historical, state = smoke_store._operator_sequence(p)
        benchmark = smoke_store._benchmark_records(p)
        q, qs = smoke_store._qualification(p)
        margin = smoke_store._checked_artifact(p.margin_report,(p.margin_report.stat().st_size,p.margin_sha256),'margin_report')
        ps = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        boot = subprocess.run([str(ps),'-NoProfile','-NonInteractive','-Command',
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"],
            capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if boot.returncode or boot.stdout.strip() != prior.BOOT_UTC:
            raise ValueError('boot_epoch_changed')
        check_port()
        self.original = service_recovery.baseline_from(old['original_baseline'])
        native.exclusive_json(root/'verification-attempt.json',dict(evaluation=self.ID,
            module_sha256=a['module_sha256'],started_utc=datetime.now(timezone.utc).isoformat()))
        records.append(operator_store.artifact_record(root/'verification-attempt.json'))
        manifest = dict(profile=self.ID,source=p.source_commit,bounds=dict(p.bounds),**candidate,
            workload=self.RECIPE.recipe_definition(self.ID),workload_sha256=digest,
            reviewed_argv=self.build_argv('[REDACTED]'),
            historical_runtime_reference=dict(profile=previous.PARENT_ID,qualification=q,
                qualification_stamp=qs,margin_report=margin,**benchmark),
            operator=dict(original_baseline=asdict(self.original),state=state,historical_baseline=asdict(historical)),
            evaluation=dict(records=records,boot_utc=prior.BOOT_UTC,
                allocation_review='Exact workload extension reviewed separately; historical numeric policy unchanged',
                historical_failures_retained=True))
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest

    def recheck_static(self, manifest, *, current_run=None):
        if json.dumps(manifest,sort_keys=True,allow_nan=False) != self.manifest_bytes:
            raise ValueError('manifest_changed')
        self.history()
        operator_store.source_identity()
        view = self.runtime_view(manifest)
        smoke_store._recheck_candidate_artifacts(view,self.PINS)
        smoke_store._recheck_benchmark(view,self.PINS)
        for record in [*manifest['operator']['state'],view['margin_report'],view['qualification_stamp'],
                       *manifest['evaluation']['records']]:
            if operator_store.stamp(record['stamp'][0]) != record['stamp']:
                raise ValueError('artifact_changed')
        if current_run is None:
            if any((self.EVIDENCE/n).exists() for n in ('attempt.json','incomplete.json')):
                raise ValueError('attempt_consumed')
        else:
            smoke_store._current_run_markers(manifest,self.marker_pins,current_run)

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if (run_dir.resolve().parent != self.EVIDENCE or run_dir.is_symlink()
                or asdict(baseline) != manifest['operator']['original_baseline']):
            raise ValueError('run_mismatch')
        for path,value in ((self.EVIDENCE/'attempt.json',dict(run=str(run_dir),profile=self.ID)),
            (self.EVIDENCE/'incomplete.json',dict(run=str(run_dir),phase='before_create',original_baseline=asdict(baseline))),
            (run_dir/'manifest.json',manifest)):
            native.exclusive_json(path,value)


class Guardian(_Guardian):
    def _result(self):
        result = super()._result()
        if result.get('http'):
            result['http']['claims'] = dict(semantic_status='manual_review_required',
                quality_pass_not_inferred_from_transport=True,standard_sustained_tg=False,
                common_window_decode_tokens_per_second=None)
        return result


def main():
    store = Store()
    guardian = Guardian(store=store,policy_module=Policy(store),profile_id=store.ID,
        collect=native.collect,argv_builder=store.build_argv)
    guardian.http_start = lambda **kw:start_suite(profile_id=store.ID,evidence_dir=guardian.run_dir,
        recipe_provider=recipe,request_validator=recipe.validate_request,response_assessor=recipe.assess,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
