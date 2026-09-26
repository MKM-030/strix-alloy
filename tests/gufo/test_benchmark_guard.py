from contextlib import redirect_stdout
import importlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.benchmark_guard'))
        self.g=importlib.import_module('gufo_control.benchmark_guard')

    def test_immutable_binding_exact_experiment_and_no_launch_status(self):
        g=self.g; pins=g.profile_pins(g.recipes.PROFILE_4K)
        self.assertEqual(pins.evidence.name,'gufo-ar4k-benchmark-v2-runs')
        self.assertEqual(pins.qualification.name,'gufo-ar4k-benchmark-v2-qualification.json')
        self.assertEqual(pins.predecessors[0].run.name,g.smoke_store.FIRST_PREDECESSOR_RUN)
        experiment=json.loads(pins.experiment_json)
        self.assertEqual(experiment['max_requests'],36)
        self.assertIsNone(pins.acceptance_sha256)
        with patch.object(g,'_Guardian',side_effect=AssertionError('launch')),redirect_stdout(io.StringIO()):
            self.assertEqual(g.main(['status','--profile',g.recipes.PROFILE_4K]),0)

    def test_16k_missing_acceptance_refuses_and_does_not_create(self):
        with tempfile.TemporaryDirectory() as root,patch.object(self.g.smoke_store,'ROOT',Path(root)):
            with self.assertRaises((OSError,ValueError)):
                self.g.profile_pins(self.g.recipes.PROFILE_16K)
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_guard_binding_closure_uses_actual_run_directory(self):
        g=self.g
        guardian=g.make_guardian(g.recipes.PROFILE_4K)
        self.assertEqual(guardian.profile_id,g.recipes.PROFILE_4K)
        guardian.run_dir=Path('actual-assigned-run')
        with patch.object(g,'start_suite',return_value='TASK') as start:
            self.assertEqual(guardian.http_start(api_key='secret',startup_deadline=10,lifetime_deadline=20),'TASK')
            self.assertEqual(start.call_args.kwargs['evidence_dir'],guardian.run_dir)

    def test_unknown_profile_and_overrides_refused(self):
        with self.assertRaises(ValueError): self.g.profile_pins('unknown')
        with self.assertRaisesRegex(ValueError, 'unknown_profile'):
            self.g.profile_pins('ar4k-iq4xs-correctness-pp1-v1')
        with self.assertRaisesRegex(ValueError, 'unknown_profile'):
            self.g.profile_pins('ar16k-iq4xs-pp1-cache-v1')
        with self.assertRaisesRegex(ValueError, 'unknown_profile'):
            self.g.profile_pins('ar16k-iq4xs-pp1-cache-v2')
        with redirect_stdout(io.StringIO()),patch('sys.stderr',io.StringIO()),self.assertRaises(SystemExit):
            self.g.main(['run','--profile',self.g.recipes.PROFILE_4K,'--context','8192'])

    def test_acceptance_schema_digest_and_root_binding(self):
        g=self.g
        with tempfile.TemporaryDirectory() as temp,patch.object(g.smoke_store,'ROOT',Path(temp)):
            reports=Path(temp)/'reports'
            run=reports/'gufo-ar4k-benchmark-v2-runs'/'reviewed-run'; run.mkdir(parents=True)
            g.operator_store.atomic_json(run/'result.json',{'synthetic':'result'})
            digest=g.operator_store.artifact_record(run/'result.json')['sha256']
            accepted=dict(profile_id=g.recipes.PROFILE_4K,run=str(run),result_sha256=digest,semantic_status='passed',review_id='independent')
            path=reports/'gufo-ar4k-benchmark-acceptance.json'
            g.operator_store.atomic_json(path,accepted)
            pins=g.profile_pins(g.recipes.PROFILE_16K)
            self.assertEqual(pins.predecessors[0].run,run)
            self.assertEqual(pins.profile_id,'ar16k-iq4xs-pp1-cache-v3')
            self.assertEqual(pins.evidence.name,'gufo-ar16k-benchmark-v3-runs')
            self.assertEqual(pins.qualification.name,'gufo-ar16k-benchmark-v3-qualification.json')
            self.assertEqual(json.loads(pins.experiment_json)['max_requests'],13)
            self.assertEqual(pins.acceptance_sha256,g.operator_store.artifact_record(path)['sha256'])
            for old in (dict(profile_id='ar4k-iq4xs-correctness-pp1-v1'),
                        dict(run=str(reports/'gufo-ar4k-benchmark-runs'/'reviewed-run'))):
                g.operator_store.atomic_json(path,dict(accepted,**old))
                with self.assertRaises(ValueError): g.profile_pins(g.recipes.PROFILE_16K)
            g.operator_store.atomic_json(path,accepted)
            for changes in [dict(review_id=''),dict(semantic_status='pending'),dict(extra=True),dict(result_sha256='A'*64),dict(run=str(reports))]:
                g.operator_store.atomic_json(path,dict(accepted,**changes))
                with self.assertRaises(ValueError): g.profile_pins(g.recipes.PROFILE_16K)

    def test_fake_guard_preserves_profile_deadlines_recovery_and_consumption(self):
        from dataclasses import replace
        from test_smoke_guard import Harness
        g=self.g
        for variant in ['success','latch','wrong_profile','deadline','recovery']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)/'gufo-ar4k-benchmark-v2-runs'; root.mkdir()
                h=Harness(root)
                pins=replace(g.profile_pins(g.recipes.PROFILE_4K),evidence=root)
                h.pins=pins
                h.manifest.update(profile=pins.profile_id,qualification=g.smoke_store.expected_qualification(pins,'review'),
                    margin_report={'sha256':pins.margin_sha256})
                if variant=='latch': g.operator_store.atomic_json(root/'incomplete.json',{})
                if variant=='wrong_profile': h.manifest['profile']=g.recipes.PROFILE_16K
                if variant=='deadline': h.http_stuck=True
                if variant=='recovery': h.query_changes=lambda phase,index: {'available_physical_bytes':1} if phase=='recovery' else {}
                # Harness substitutes static verification; real predecessor
                # authentication is exercised by the store and suite tests.
                with patch.object(g.smoke_store,'_recheck_benchmark',return_value=None):
                    result=h.run(policy_module=g.BoundPolicy(pins),profile_id=pins.profile_id,
                        argv_builder=lambda key:g.recipes.build_argv(pins.profile_id,key))
                if variant=='success':
                    self.assertTrue(result['success'],result)
                    self.assertEqual(result['recovery_samples'],5)
                    args=h.http_tasks[0].args
                    self.assertEqual(args['startup_deadline']-h.children[0].resume_at,480)
                    self.assertEqual(args['lifetime_deadline']-h.children[0].resume_at,600)
                    self.assertTrue(h.children[0].closed)
                    with patch.object(g.smoke_store,'_recheck_benchmark',return_value=None):
                        again=h.run(policy_module=g.BoundPolicy(pins),profile_id=pins.profile_id)
                    self.assertFalse(again['success']); self.assertEqual(len(h.children),1)
                else:
                    self.assertFalse(result['success'])
                    if variant in ('latch','wrong_profile'): self.assertEqual(h.children,[])
                    else: self.assertTrue(h.children[0].closed)
