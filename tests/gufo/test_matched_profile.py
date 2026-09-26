from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from gufo_control import benchmark_guard, benchmark_recipes, matched_recipes, smoke_policy, smoke_store
from gufo_control import matched_profile


class MatchedProfileTests(unittest.TestCase):
    def test_distinct_unchanged_demands(self):
        ar = matched_profile.profile_pins(matched_recipes.PROFILE_AR)
        mtp = matched_profile.profile_pins(matched_recipes.PROFILE_MTP)
        self.assertEqual(ar.bounds['gpu_gib'], 68)
        self.assertEqual(mtp.bounds['gpu_gib'], 72)
        self.assertEqual(smoke_store.MTP_BOUNDS['gpu_gib'], 71)
        self.assertEqual(smoke_policy._demand(mtp)['commit_peak_bytes'], 76 * 2**30)
        with self.assertRaises(ValueError):
            smoke_store._binding(replace(mtp, bounds=dict(mtp.bounds, gpu_gib=71)))
        self.assertEqual(smoke_policy._demand(benchmark_guard.profile_pins(benchmark_recipes.PROFILE_16K))['commit_peak_bytes'],72*2**30)

    def test_exact_bindings_and_no_policy_stat(self):
        for profile in (matched_recipes.PROFILE_AR, matched_recipes.PROFILE_MTP):
            pins = matched_profile.profile_pins(profile)
            self.assertEqual(smoke_store._binding(pins)['experiment'], matched_profile.experiment_definition(profile))
            with patch.object(smoke_store.operator_store, 'stamp', side_effect=AssertionError('stat')):
                q = smoke_store.expected_qualification(pins, 'independent-review')
                self.assertEqual(q['bounds'], pins.bounds)
                self.assertEqual(smoke_policy._demand(pins)['gpu_peak_bytes'], pins.bounds['gpu_gib']*2**30)
            for change in (dict(margin_sha256='0'*64), dict(experiment_json=pins.experiment_json.replace('2304','2305')),
                           dict(sidecar=None) if profile == matched_recipes.PROFILE_MTP else dict(sidecar=smoke_store.MTP_SIDECAR)):
                with self.assertRaises(ValueError): smoke_store._binding(replace(pins, **change))
            changed=json.loads(pins.experiment_json)
            changed['recipe_sha256']='0'*64
            with self.assertRaises(ValueError): smoke_store._binding(replace(pins,
                experiment_json=matched_recipes.base.canonical(changed)))
            experiment=json.loads(pins.experiment_json)
            experiment['speculative']=int(experiment['speculative'])
            with self.assertRaises(ValueError): smoke_store._binding(replace(pins,experiment_json=matched_recipes.base.canonical(experiment)))

    def test_argv_and_unknown_profiles(self):
        ar=matched_profile.build_argv(matched_recipes.PROFILE_AR,'secret')
        mtp=matched_profile.build_argv(matched_recipes.PROFILE_MTP,'secret')
        self.assertEqual(ar,benchmark_recipes.build_argv(benchmark_recipes.PROFILE_4K,'secret'))
        self.assertEqual(mtp[mtp.index('--speculative')+1],'mtp')
        self.assertEqual(mtp[mtp.index('--draft-tokens')+1],'1')
        for call in (matched_profile.profile_pins, matched_profile.experiment_definition,
                     lambda id: matched_profile.build_argv(id,'secret'),smoke_store.profile_bounds):
            with self.assertRaises(ValueError): call('unknown')

    def test_missing_qualification_and_commit_headroom(self):
        from gufo_control import smoke_policy
        from gufo_control.operator_policy import GIB, baseline
        from test_operator_policy import frame, series
        b=baseline(series())
        for profile,charge in ((matched_recipes.PROFILE_AR,72),(matched_recipes.PROFILE_MTP,76)):
            pins=matched_profile.profile_pins(profile)
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError,'guard_review_missing'):
                    smoke_store._qualification(pins)
                manifest=dict(profile=pins.profile_id,source=pins.source_commit,
                    executable=str(pins.build/pins.executable_name),sdk=str(pins.sdk),
                    bounds=dict(pins.bounds),model=dict(revision=pins.model_revision,
                    first_shard=str(pins.first_shard)),margin_report=dict(sha256=pins.margin_sha256),
                    qualification=smoke_store.expected_qualification(pins,'review'))
                policy=smoke_policy.profile_from_manifest(manifest,pins=pins)
                limit=b.committed_max+(charge+12)*GIB
                at=frame(12,host_commit_limit_bytes=limit)
                below=frame(12,host_commit_limit_bytes=limit-1)
                self.assertTrue(smoke_policy.admission_decision(policy,b,at,
                    now=at.query_end,now_utc=at.validated_utc,pins=pins)['allowed'])
                self.assertFalse(smoke_policy.admission_decision(policy,b,below,
                    now=below.query_end,now_utc=below.validated_utc,pins=pins)['allowed'])

    def test_guard_routing_and_cross_profile_latch(self):
        ar=matched_recipes.PROFILE_AR
        guardian=benchmark_guard.make_guardian(ar)
        self.assertEqual(guardian.profile_id,ar)
        guardian.run_dir=smoke_store.ROOT/'reports'/'synthetic-run'
        with patch.object(benchmark_guard,'start_suite',return_value='TASK') as start:
            self.assertEqual(guardian.http_start(api_key='private',startup_deadline=1,lifetime_deadline=2),'TASK')
            args=start.call_args.kwargs
            self.assertIs(args['recipe_provider'],matched_recipes)
            self.assertIs(args['request_validator'],matched_recipes.validate_request)
        mtp=matched_profile.profile_pins(matched_recipes.PROFILE_MTP)
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            pins=replace(mtp,evidence=Path(temp)/smoke_store.PROFILE_ROOTS[mtp.profile_id])
            sibling=Path(temp)/smoke_store.PROFILE_ROOTS[ar]
            sibling.mkdir()
            (sibling/'incomplete.json').touch()
            with self.assertRaisesRegex(ValueError,'prior_smoke_incomplete'):
                smoke_store._incomplete_latches(pins)
