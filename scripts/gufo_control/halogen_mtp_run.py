"""One reviewed native MTP measurement; historical attempts are never replayed."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from . import halogen_mtp_recipe as recipe, matched_profile, matched_recipes
from . import pp_remeasure_native as native, pp_remeasure as prior
from . import operator_store, smoke_store, service_recovery
from .benchmark_runtime import BoundPolicy
from .benchmark_suite import start_suite
from .smoke_guard import _Guardian, check_port

ID = recipe.ID
EVIDENCE = prior.REPORTS / (ID + '-runs')
APPROVAL = prior.REPORTS / (ID + '-approval.json')
PARENT_ID = matched_recipes.PROFILE_MTP_D3
PP_RUN = native.EVIDENCE / '20260927T150401Z-3cafec35c1cd4c2ea09576cf916f7c3b'
PP_SHA = '0F9737CF9E13A17C6EE8AEB420D5937C38F10E94F2E5A1898D77D8E213159E21'
MTP_RUN = prior.REPORTS / 'gufo-matched-mtp4k-d3-v1-runs' / '20260926T220412Z-cc4ea26febce4b0187a7065d9a2d8107'
MTP_SHA = '5248F816FB0DAC73685C9E7A8E5F29C8C700AB1CB7C6BF3C6BE3023C0FB39D70'
HELPERS = ('halogen_mtp_recipe.py','pp_remeasure_native.py','pp_remeasure.py',
    'matched_profile.py','matched_recipes.py','benchmark_suite.py','benchmark_http.py',
    'benchmark_recipes.py','smoke_http.py','telemetry.py','smoke_guard.py',
    'smoke_store.py','smoke_policy.py','operator_probe.py','operator_policy.py',
    'operator_store.py','benchmark_runtime.py','service_recovery.py')


def runtime_view(manifest):
    """Explicit private policy view, not the persisted executed recipe identity."""
    if (manifest['profile'] != ID or manifest['workload'] != recipe.recipe_definition(ID)
            or manifest['workload_sha256'] != sha256(recipe.recipe_json(ID).encode()).hexdigest().upper()):
        raise ValueError('workload_binding_changed')
    view = dict(manifest)
    view.update(manifest['historical_runtime_reference'])
    view['profile'] = PARENT_ID
    return view


class Policy:
    def __init__(self, pins):
        self.parent = BoundPolicy(pins)

    def __getattr__(self, name):
        return getattr(self.parent, name)

    def profile_from_manifest(self, manifest):
        return self.parent.profile_from_manifest(runtime_view(manifest))


class Store(native.NativeRepeatStore):
    EVIDENCE = EVIDENCE

    def __init__(self):
        super().__init__()
        self.PINS = matched_profile.profile_pins(PARENT_ID)
        self.BUILD = self.PINS.build
        self.marker_pins = replace(self.PINS, profile_id=ID, evidence=EVIDENCE)

    def history(self):
        super().history()
        if (native.EVIDENCE/'incomplete.json').exists():
            raise ValueError('pp_cleanup_incomplete')
        for path, digest in ((PP_RUN/'result.json',PP_SHA),(MTP_RUN/'result.json',MTP_SHA)):
            r = service_recovery.read_pinned(path,digest)
            if not r['success'] or not r['cleanup_confirmed'] or r['exit_code'] != 0:
                raise ValueError('prior_run_not_clean')
        return service_recovery.read_pinned(PP_RUN/'result.json',PP_SHA)

    def verify_static(self):
        if EVIDENCE.is_symlink() or EVIDENCE.resolve() != EVIDENCE:
            raise ValueError('evidence_redirected')
        if any((EVIDENCE/n).exists() for n in ('attempt.json','incomplete.json','verification-attempt.json')):
            raise ValueError('attempt_consumed')
        old = self.history()
        a = operator_store.read_json(APPROVAL)
        digest = sha256(recipe.recipe_json(ID).encode()).hexdigest().upper()
        if (a.get('evaluation') != ID or a.get('decision') != 'approved'
                or a.get('module_sha256') != sha256(Path(__file__).read_bytes()).hexdigest().upper()
                or a.get('recipe_sha256') != digest or set(a.get('helpers',{})) != set(HELPERS)):
            raise ValueError('review_binding_missing')
        records = [native.checked(a['review_path'],a['review_sha256']),
            operator_store.artifact_record(APPROVAL), operator_store.artifact_record(Path(__file__)),
            native.checked(recipe.CORPUS,recipe.CORPUS_SHA), *native.probe_records(),
            native.checked(PP_RUN/'result.json',PP_SHA), native.checked(MTP_RUN/'result.json',MTP_SHA)]
        records += [native.checked(Path(__file__).with_name(n),h) for n,h in a['helpers'].items()]
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
        # Permanent even if later baseline collection fails; no blind retries.
        native.exclusive_json(EVIDENCE/'verification-attempt.json',
            dict(evaluation=ID,module_sha256=a['module_sha256'],started_utc=datetime.now(timezone.utc).isoformat()))
        records.append(operator_store.artifact_record(EVIDENCE/'verification-attempt.json'))
        manifest = dict(profile=ID,source=p.source_commit,bounds=dict(p.bounds),**candidate,
            workload=recipe.recipe_definition(ID),workload_sha256=digest,
            historical_runtime_reference=dict(profile=PARENT_ID,qualification=q,
                qualification_stamp=qs,margin_report=margin,**benchmark),
            operator=dict(original_baseline=asdict(self.original),state=state,historical_baseline=asdict(historical)),
            evaluation=dict(records=records,boot_utc=prior.BOOT_UTC,
                allocation_review='Historical numerical envelope explicitly extended to this fixed workload by the new review',
                historical_failures_retained=True))
        self.manifest_bytes = json.dumps(manifest,sort_keys=True,allow_nan=False)
        return manifest

    def recheck_static(self, manifest, *, current_run=None):
        if json.dumps(manifest,sort_keys=True,allow_nan=False) != self.manifest_bytes:
            raise ValueError('manifest_changed')
        self.history()
        operator_store.source_identity()
        view = runtime_view(manifest)
        smoke_store._recheck_candidate_artifacts(view,self.PINS)
        smoke_store._recheck_benchmark(view,self.PINS)
        for record in [*manifest['operator']['state'],view['margin_report'],view['qualification_stamp'],
                       *manifest['evaluation']['records']]:
            if operator_store.stamp(record['stamp'][0]) != record['stamp']:
                raise ValueError('artifact_changed')
        if current_run is None:
            if any((EVIDENCE/n).exists() for n in ('attempt.json','incomplete.json')):
                raise ValueError('attempt_consumed')
        else:
            smoke_store._current_run_markers(manifest,self.marker_pins,current_run)

    def begin_run(self, run_dir, manifest, baseline):
        self.recheck_static(manifest)
        if (run_dir.resolve().parent != EVIDENCE or run_dir.is_symlink()
                or asdict(baseline) != manifest['operator']['original_baseline']):
            raise ValueError('run_mismatch')
        for path,value in ((EVIDENCE/'attempt.json',dict(run=str(run_dir),profile=ID)),
            (EVIDENCE/'incomplete.json',dict(run=str(run_dir),phase='before_create',original_baseline=asdict(baseline))),
            (run_dir/'manifest.json',manifest)):
            native.exclusive_json(path,value)


class Guardian(_Guardian):
    def _result(self):
        result = super()._result()
        http = result.get('http')
        if http:
            rows = [r for r in http.get('rows',[]) if r['case'] in recipe.CASES and r['status']=='completed']
            proposed = sum(r['metrics'].get('draft_tokens',0) for r in rows)
            accepted = sum(r['metrics'].get('draft_tokens_accepted',0) for r in rows)
            http['claims'] = dict(scope='completed_halogen_corpus_rows',proposed=proposed,accepted=accepted,
                acceptance=accepted/proposed if proposed else None,
                mtp_draft_path_exercised=proposed>0,useful_accepted_speculation_observed=accepted>0,
                semantic_status='manual_review_required',standard_sustained_tg=False)
        return result


def main():
    store = Store()
    guardian = Guardian(store=store,policy_module=Policy(store.PINS),profile_id=ID,
        collect=native.collect,argv_builder=lambda key:matched_profile.build_argv(PARENT_ID,key))
    guardian.http_start = lambda **kw:start_suite(profile_id=ID,evidence_dir=guardian.run_dir,
        recipe_provider=recipe,request_validator=recipe.validate_request,response_assessor=recipe.assess,**kw)
    result = guardian.run()
    print(json.dumps({k:result.get(k) for k in ('success','failure','run','cleanup_confirmed','exit_code')}))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
