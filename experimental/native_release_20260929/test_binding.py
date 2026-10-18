import copy
import importlib
import unittest
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
binding = importlib.import_module('experimental.native_release_20260929.binding')


class BindingTests(unittest.TestCase):
    def test_binding_surface_exists(self):
        self.assertTrue(hasattr(binding, 'fixed_argv'), 'release adapter is missing')

    def test_fixed_small_ar_arguments(self):
        args = binding.fixed_argv('test-key')
        for flag, value in (('--context', '4096'), ('--think', 'off'),
                            ('--speculative', 'off'), ('--sessions', '1')):
            self.assertEqual(args[args.index(flag)+1], value)
        self.assertNotIn('--request-policy', args)
        self.assertIn('gufo-native-v011', args[0])

    def test_exact_two_requests_no_retry(self):
        recipe = binding.recipe_definition(binding.PROFILE)
        self.assertEqual(len(recipe['schedule']), 2)
        for row, expected in zip(recipe['schedule'], ('42', 'Grün')):
            req = binding.request_for(row, [])
            self.assertFalse(req['cache_prompt'])
            self.assertFalse(req['chat_template_kwargs']['enable_thinking'])
            self.assertEqual(req['max_tokens'], 64)
            observation = dict(success=True, visible_answer=expected, finish_reason='stop',
                               metrics={'logical_prompt_tokens': 40})
            self.assertEqual(binding.assess(row, observation, recipe)[1], [])
            for bad in (expected+' extra', '', expected.lower() if expected=='Grün' else '41'):
                observation['visible_answer'] = bad
                self.assertTrue(binding.assess(row, observation, recipe)[1])

    def test_unknown_recipe_refused(self):
        with self.assertRaises(ValueError):
            binding.recipe_definition('old-success')

    def test_missing_qualification_refuses(self):
        with self.assertRaisesRegex(ValueError, 'qualification'):
            binding.validate_qualification(None, {})

    def test_qualification_exact_identity(self):
        identity = {'source': 'new-source', 'runtime': 'new-runtime'}
        q = binding.qualification_record(identity, 'review-test')
        binding.validate_qualification(q, identity)
        for field in ('profile', 'identity', 'bounds', 'recipe'):
            wrong = copy.deepcopy(q)
            wrong[field] = 'old-success'
            with self.assertRaises(ValueError):
                binding.validate_qualification(wrong, identity)

    def test_cleanup_is_required_for_success(self):
        from gufo_control.smoke_guard import _Guardian
        guardian = _Guardian(profile_id='offline-only')
        guardian.http_result = {'success': True}
        self.assertFalse(guardian._result()['success'])
        guardian.exited = guardian.recovered = True
        self.assertTrue(guardian._result()['success'])

    def test_policy_and_store_available(self):
        self.assertTrue(hasattr(binding, 'ReleaseStore'), 'release store missing')
        self.assertTrue(hasattr(binding, 'ReleasePolicy'), 'release policy missing')

    def test_default_store_refuses_without_review_before_io(self):
        with self.assertRaisesRegex(ValueError, 'independent_release_qualification_missing'):
            binding.ReleaseStore().verify_static()

    def test_policy_rejects_unqualified_or_missing_frame(self):
        policy = binding.ReleasePolicy()
        self.assertIn('unqualified_profile', policy.frame_numeric_reasons(
            None, None, None, now=1, now_utc=None))

    def test_guardian_reuses_ownership_and_http(self):
        from gufo_control.smoke_guard import _Guardian
        guardian = binding.make_guardian()
        self.assertIs(type(guardian), _Guardian)
        self.assertEqual(guardian.profile_id, binding.PROFILE)
        self.assertEqual(guardian.store.BUILD, binding.BUILD)

    def test_real_suite_contract_runs_two_and_stops_on_wrong_answer(self):
        from gufo_control import benchmark_suite
        for wrong in (False, True):
            calls = []
            def request_once(**kwargs):
                index = len(calls)
                calls.append(kwargs)
                return dict(success=True, post_attempted=True,
                    visible_answer='bad' if wrong else binding.ANSWERS[index],
                    finish_reason='stop', metrics=dict(logical_prompt_tokens=40),
                    request=kwargs['request'])
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(benchmark_suite, '_ready'), \
                    patch.object(benchmark_suite.benchmark_http, 'request_once', request_once):
                task = benchmark_suite.start_suite(profile_id=binding.PROFILE,
                    evidence_dir=Path(directory), api_key='offline-key',
                    startup_deadline=time.monotonic()+10, lifetime_deadline=time.monotonic()+20,
                    recipe_provider=binding, response_assessor=binding.assess)
                self.assertTrue(task.done.wait(3))
                self.assertEqual(task.result['success'], not wrong, task.result)
                self.assertEqual(len(calls), 1 if wrong else 2)

    def test_failure_keeps_latch_and_success_requires_cleanup(self):
        from gufo_control import operator_store
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root/'attempt'
            run.mkdir()
            with patch.object(binding, 'EVIDENCE', root):
                for name in ('attempt.json', 'incomplete.json'):
                    operator_store.atomic_json(root/name, dict(run=str(run)))
                binding.ReleaseStore().finish_run(run, dict(success=False, cleanup_confirmed=True))
                self.assertTrue((root/'incomplete.json').exists())
                binding.ReleaseStore().finish_run(run, dict(success=True, cleanup_confirmed=False))
                self.assertTrue((root/'incomplete.json').exists())

    def test_owned_collector_is_bound_to_guardian(self):
        guardian = binding.make_guardian()
        self.assertNotEqual(guardian.collect.__module__, 'gufo_control.telemetry')

    def test_missing_owned_sample_refused_after_request(self):
        self.assertEqual(binding.owned_sample_reasons(
            {'release_owned_required': True, 'owned_counters': {'available': False}}),
            ['release_owned_counters_unavailable'])

    def test_review_pin_is_separate_from_controller_identity(self):
        self.assertTrue((Path(binding.__file__).parent/'review_pin.py').is_file())

    def test_ready_requires_owned_counters(self):
        with self.assertRaisesRegex(ValueError, 'owned'):
            binding.ready_evidence_check({}, {}, 10)

    def test_ready_rejects_external_runtime_dll(self):
        snap = dict(captured_monotonic=10, owned_counters=dict(available=True))
        with self.assertRaisesRegex(ValueError, 'runtime_module'):
            binding.ready_evidence_check(snap, dict(status='verified',
                modules=['C:/foreign/rocblas.dll']), 10)


if __name__ == '__main__':
    unittest.main()
