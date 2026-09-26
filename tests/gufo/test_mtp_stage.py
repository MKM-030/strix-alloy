"""Offline contract for the bounded native MTP stage."""
from copy import deepcopy
from dataclasses import replace
import unittest
from pathlib import Path
from unittest.mock import patch

from gufo_control import smoke_store, smoke_http, mtp_stage
from gufo_control import smoke_policy
from gufo_control.operator_policy import GIB, baseline
from test_operator_policy import frame, series


class MtpStageTests(unittest.TestCase):
    def test_exact_request_is_copied_and_rejects_mutations(self):
        request = mtp_stage.request_fixture()
        self.assertEqual(request['messages'][0]['content'], mtp_stage.PROMPT)
        self.assertEqual(request['max_tokens'], 64)
        self.assertEqual(request['model'], smoke_http.MODEL)
        self.assertIsNot(request, mtp_stage.request_fixture())
        self.assertEqual(mtp_stage.validate_request(request), 243)
        for change in ('max_completion_tokens', 'unicode', 'extra_message', 'output65', 'bool_output', 'cache'):
            with self.subTest(change=change):
                value = deepcopy(request)
                if change == 'max_completion_tokens': value['max_completion_tokens'] = 64
                elif change == 'unicode': value['messages'][0]['content'] += ' é'
                elif change == 'extra_message': value['messages'].append({'role': 'user', 'content': 'x'})
                elif change == 'output65': value['max_tokens'] = 65
                elif change == 'bool_output': value['max_tokens'] = True
                elif change == 'cache': value['cache_prompt'] = True
                with self.assertRaises(ValueError): mtp_stage.validate_request(value)

    def test_distinct_profile_demand_and_argv(self):
        pins = mtp_stage.profile_pins()
        self.assertEqual(pins.profile_id, 'mtp4k-iq4xs-draft1-bilingual-v1')
        self.assertEqual(pins.bounds, dict(gpu_gib=71, host_gib=4, shared_gib=20,
            prelaunch_gib=49, runtime_gib=24, commit_reserve_gib=12))
        self.assertEqual(smoke_store.BOUNDS['gpu_gib'], 68)
        with self.assertRaises(ValueError):
            smoke_store._binding(replace(pins, bounds=dict(pins.bounds, gpu_gib=72)))
        argv = mtp_stage.build_argv('private')
        for flag, expected in (('--speculative', 'mtp'), ('--mtp-model', str(mtp_stage.SIDECAR)),
                               ('--draft-tokens', '1'), ('--min-draft-tokens', '1'),
                               ('--mtp-policy', 'length'), ('--mtp-draft-vocab', 'full'),
                               ('--max-tokens', '64')):
            self.assertEqual(argv[argv.index(flag)+1], expected)

    def test_guardian_prevalidates_and_uses_actual_run_dir(self):
        guardian = mtp_stage.make_guardian()
        self.assertEqual(guardian.profile_id, mtp_stage.PROFILE_ID)
        self.assertIsNone(guardian.run_dir)

    def test_qualification_binds_recipe_sidecar_margin_and_predecessor(self):
        pins = mtp_stage.profile_pins()
        qualification = smoke_store.expected_qualification(pins, 'independent-review')
        self.assertEqual(qualification['mtp_recipe']['rendered_input_bytes'], 243)
        self.assertEqual(qualification['experiment']['recipe_sha256'], mtp_stage.recipe_sha256())
        self.assertEqual(qualification['sidecar']['stamp'][1], mtp_stage.MTP_SIDECAR.size_bytes)
        self.assertEqual(qualification['margin_report_sha256'], smoke_store.MTP_MARGIN_SHA256)
        self.assertEqual(qualification['predecessors'][0]['result_sha256'],
                         smoke_store.MTP_PREDECESSOR_SHA256)
        for key in ('mtp_recipe', 'sidecar', 'margin_report_sha256', 'predecessors'):
            changed = deepcopy(qualification)
            changed[key] = None
            self.assertNotEqual(changed, smoke_store.expected_qualification(pins, 'independent-review'))

    def test_recorded_sidecar_stamp_keeps_policy_validation_and_admission_pure(self):
        pins = mtp_stage.profile_pins()
        m = dict(profile=pins.profile_id, source=pins.source_commit,
                 executable=str(pins.build/pins.executable_name), sdk=str(pins.sdk),
                 bounds=dict(pins.bounds), model=dict(revision=pins.model_revision,
                 first_shard=str(pins.first_shard)), margin_report=dict(sha256=pins.margin_sha256),
                 qualification=smoke_store.expected_qualification(pins, 'review'))
        b = baseline(series())
        f = frame(12, host_commit_limit_bytes=103*GIB)
        with patch.object(smoke_store.operator_store, 'stamp', side_effect=AssertionError('stamp I/O')), \
             patch.object(Path, 'stat', side_effect=AssertionError('stat I/O')):
            profile = smoke_policy.profile_from_manifest(m, pins=pins)
            self.assertTrue(smoke_policy._profile_valid(profile, pins=pins))
            self.assertTrue(smoke_policy.admission_decision(profile, b, f,
                now=f.query_end, now_utc=f.validated_utc, pins=pins)['allowed'])
            self.assertEqual(smoke_policy.frame_numeric_reasons(profile, b, f,
                now=f.query_end, now_utc=f.validated_utc, pins=pins), [])

    def test_recorded_sidecar_stamp_rejects_bad_types_path_and_size(self):
        pins = mtp_stage.profile_pins()
        self.assertTrue(hasattr(pins, 'sidecar_stamp'))
        for stamp in (None,
                      [str(pins.sidecar.path), pins.sidecar.size_bytes, 1],
                      (str(pins.sidecar.path), True, 1),
                      ('wrong-path', pins.sidecar.size_bytes, 1),
                      (str(pins.sidecar.path), pins.sidecar.size_bytes+1, 1),
                      (str(pins.sidecar.path), pins.sidecar.size_bytes, 0),
                      (str(pins.sidecar.path), pins.sidecar.size_bytes, 1.0)):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                smoke_store.expected_qualification(replace(pins, sidecar_stamp=stamp), 'review')

    def test_selected_policy_has_mtp_75_gib_charge_and_ar_72_unchanged(self):
        pins = mtp_stage.profile_pins()
        m = dict(profile=pins.profile_id, source=pins.source_commit,
                 executable=str(pins.build/pins.executable_name), sdk=str(pins.sdk),
                 bounds=dict(pins.bounds), model=dict(revision=pins.model_revision,
                 first_shard=str(pins.first_shard)), margin_report=dict(sha256=pins.margin_sha256),
                 qualification=smoke_store.expected_qualification(pins, 'review'))
        profile = smoke_policy.profile_from_manifest(m, pins=pins)
        self.assertEqual((profile.gpu_peak_bytes, profile.host_peak_bytes,
                          profile.shared_physical_allowance_bytes, profile.commit_peak_bytes),
                         (71*GIB, 4*GIB, 20*GIB, 75*GIB))
        self.assertEqual(smoke_policy.SmokeProfile().commit_peak_bytes, 72*GIB)
        b = baseline(series())
        f = frame(12, host_commit_limit_bytes=103*GIB)
        decision = smoke_policy.admission_decision(profile, b, f, now=f.query_end,
                                                    now_utc=f.validated_utc, pins=pins)
        self.assertTrue(decision['allowed'], decision)
        f = frame(12, host_commit_limit_bytes=103*GIB-1)
        self.assertFalse(smoke_policy.admission_decision(profile, b, f, now=f.query_end,
            now_utc=f.validated_utc, pins=pins)['allowed'])
        f = frame(12, host_committed_bytes=b.committed_max+75*GIB)
        self.assertNotIn('commit_envelope', smoke_policy.frame_numeric_reasons(profile, b, f,
            now=f.query_end, now_utc=f.validated_utc, pins=pins))
        f = frame(12, host_committed_bytes=b.committed_max+75*GIB+1)
        self.assertIn('commit_envelope', smoke_policy.frame_numeric_reasons(profile, b, f,
            now=f.query_end, now_utc=f.validated_utc, pins=pins))
