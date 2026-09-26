"""Offline contract for the separately reviewed matched draft3 identity."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import (benchmark_guard, benchmark_recipes, matched_profile,
                          matched_recipes, matched_validation, smoke_policy, smoke_store)
from gufo_control.operator_policy import GIB, baseline
from test_operator_policy import frame, series
from test_matched_validation import observation


class Draft3Tests(unittest.TestCase):
    def test_bound_identity_and_old_profiles(self):
        r, p, s = matched_recipes, matched_profile, smoke_store
        pins = p.profile_pins(r.PROFILE_MTP_D3)
        self.assertEqual(pins.evidence.name, 'gufo-matched-mtp4k-d3-v1-runs')
        self.assertEqual(pins.qualification.name, 'gufo-matched-mtp4k-d3-v1-qualification.json')
        self.assertEqual(pins.bounds, dict(s.BOUNDS, gpu_gib=73))
        self.assertEqual(smoke_policy._demand(pins)['commit_peak_bytes'], 77 * GIB)
        self.assertEqual(s._binding(pins)['experiment']['draft_tokens'], 3)
        self.assertEqual(pins.margin_sha256,
                         '825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D')
        self.assertEqual(pins.margin_report.name, 'gufo-mtp-draft3-envelope-review-20260926.md')
        for profile, gpu in ((r.PROFILE_AR, 68), (r.PROFILE_AR_V2, 68),
                             (r.PROFILE_MTP, 72)):
            self.assertEqual(p.profile_pins(profile).bounds['gpu_gib'], gpu)
        self.assertEqual(s.profile_bounds(s.MTP_4K)['gpu_gib'], 71)
        with self.assertRaises(ValueError):
            s._binding(replace(pins, bounds=dict(pins.bounds, gpu_gib=72)))

    def test_fixed_requests_and_argv(self):
        r, p = matched_recipes, matched_profile
        d1 = r.recipe_definition(r.PROFILE_MTP)
        d3 = r.recipe_definition(r.PROFILE_MTP_D3)
        self.assertEqual(d1['schedule'], d3['schedule'])
        self.assertEqual([r.request_for(row) for row in d1['schedule']],
                         [r.request_for(row) for row in d3['schedule']])
        self.assertEqual(d3['draft_tokens'], 3)
        argv = p.build_argv(r.PROFILE_MTP_D3, 'secret')
        self.assertEqual(argv[argv.index('--draft-tokens') + 1], '3')
        self.assertEqual(argv[argv.index('--min-draft-tokens') + 1], '1')
        self.assertEqual(argv[argv.index('--mtp-policy') + 1], 'length')
        self.assertEqual(argv[argv.index('--mtp-draft-vocab') + 1], 'full')

    def test_exact_refusals_and_missing_qualification(self):
        pins = matched_profile.profile_pins(matched_recipes.PROFILE_MTP_D3)
        for change in (dict(margin_sha256='0' * 64),
                       dict(margin_report=pins.margin_report.with_name('other.md')),
                       dict(sidecar=None), dict(sidecar_stamp=None),
                       dict(qualification=pins.qualification.with_name('other.json'))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                smoke_store._binding(replace(pins, **change))
        experiment = json.loads(pins.experiment_json)
        for key, value in (('draft_tokens', 1), ('draft_tokens', True),
                           ('draft_tokens', 3.0), ('min_draft_tokens', 2),
                           ('min_draft_tokens', True), ('mtp_policy', 'other'),
                           ('mtp_draft_vocab', 'sparse')):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                changed = dict(experiment, **{key: value})
                smoke_store._binding(replace(pins,
                    experiment_json=benchmark_recipes.canonical(changed)))
        with patch.object(smoke_store, '_json_artifact', side_effect=OSError('missing')):
            with self.assertRaisesRegex(ValueError, 'guard_review_missing'):
                smoke_store._qualification(pins)

    def test_admission_and_guard_routing(self):
        pins = matched_profile.profile_pins(matched_recipes.PROFILE_MTP_D3)
        b = baseline(series())
        manifest = dict(profile=pins.profile_id, source=pins.source_commit,
            executable=str(pins.build / pins.executable_name), sdk=str(pins.sdk),
            bounds=dict(pins.bounds), model=dict(revision=pins.model_revision,
            first_shard=str(pins.first_shard)), margin_report=dict(sha256=pins.margin_sha256),
            qualification=smoke_store.expected_qualification(pins, 'review'))
        policy = smoke_policy.profile_from_manifest(manifest, pins=pins)
        limit = b.committed_max + 89 * GIB
        for offset, allowed in ((0, True), (-1, False)):
            at = frame(12, host_commit_limit_bytes=limit + offset)
            self.assertEqual(smoke_policy.admission_decision(policy, b, at,
                now=at.query_end, now_utc=at.validated_utc, pins=pins)['allowed'], allowed)
        guardian = benchmark_guard.make_guardian(pins.profile_id)
        guardian.run_dir = smoke_store.ROOT / 'reports' / 'synthetic-run'
        with patch.object(benchmark_guard, 'start_suite', return_value='TASK') as start:
            self.assertEqual(guardian.http_start(api_key='private', startup_deadline=1,
                                                  lifetime_deadline=2), 'TASK')
        self.assertIs(start.call_args.kwargs['recipe_provider'], matched_recipes)
        self.assertIs(start.call_args.kwargs['response_assessor'], matched_validation.assess)
        with tempfile.TemporaryDirectory() as temp:
            old = matched_profile.profile_pins(matched_recipes.PROFILE_MTP)
            old = replace(old, evidence=Path(temp) / smoke_store.PROFILE_ROOTS[old.profile_id])
            sibling = Path(temp) / smoke_store.PROFILE_ROOTS[pins.profile_id]
            sibling.mkdir()
            (sibling / 'incomplete.json').touch()
            with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
                smoke_store._incomplete_latches(old)

    def test_native_counter_shapes(self):
        definition = matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP_D3)
        row = definition['schedule'][0]
        for proposed, accepted in ((0, 0), (4, 0), (4, 3)):
            value = observation(row, mtp=True, proposed=proposed, accepted=accepted)
            value['observed_models'] = ['gufo-flash-next'] * 4
            _, errors = matched_validation.assess(row, value, definition)
            self.assertEqual(errors, [])
            self.assertEqual(value['matched_evidence']['mode'], 'mtp')
            self.assertEqual(value['matched_evidence']['accepted'], accepted)
        for field, bad in (('draft_tokens', True), ('draft_tokens_accepted', 5)):
            value = observation(row, mtp=True, proposed=4, accepted=3)
            value['usage'][field] = bad
            self.assertTrue(matched_validation.assess(row, value, definition)[1])

    def test_saved_draft1_observations_replay_offline(self):
        run = (smoke_store.ROOT / 'reports' / 'gufo-matched-mtp4k-v1-runs' /
               '20260926T212859Z-802ae464aefd43d79a7e409a12424e3f')
        if not run.is_dir():
            self.skipTest('historical native evidence is unavailable')
        definition = matched_recipes.recipe_definition(matched_recipes.PROFILE_MTP_D3)
        repeated_models = False
        for row in definition['schedule']:
            saved = json.loads((run / f"request-{row['ordinal']:03d}.json").read_text())
            repeated_models |= len(saved['observed_models']) > 1
            _, errors = matched_validation.assess(row, saved, definition)
            self.assertEqual(errors, [], row['ordinal'])
            self.assertEqual(saved['matched_evidence']['mode'], 'mtp')
        self.assertTrue(repeated_models)
