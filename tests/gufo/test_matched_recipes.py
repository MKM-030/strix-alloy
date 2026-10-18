"""Offline contract for the two fixed, matched 4K workloads."""
from copy import deepcopy
from hashlib import sha256
import importlib
import importlib.util
import json
import unittest
from unittest.mock import patch

from gufo_control import benchmark_recipes as base


class MatchedRecipeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('gufo_control.matched_recipes'))
        self.matched = importlib.import_module('gufo_control.matched_recipes')

    def test_matched_bodies_are_identical(self):
        matched = self.matched
        ar = matched.recipe_definition(matched.PROFILE_AR)
        mtp = matched.recipe_definition(matched.PROFILE_MTP)
        self.assertEqual(len(ar['schedule']), 36)
        self.assertEqual(ar['schedule'], mtp['schedule'])
        bodies = [matched.request_for(row) for row in ar['schedule']]
        self.assertEqual(bodies, [matched.request_for(row) for row in mtp['schedule']])
        self.assertEqual(sha256(base.canonical(bodies).encode()).hexdigest().upper(),
                         matched.REQUESTS_SHA256)
        self.assertEqual([row['expected_prompt_tokens'] for row in ar['schedule']],
                         list(matched.PROMPT_COUNTS))
        self.assertEqual(tuple(matched.CALIBRATION), (13, 373))
        self.assertEqual(matched.REQUESTS_SHA256,
                         'EF677B664873CC42C07E4A22DA69723D6743AB57BF7944A0163A8E4799F394AB')

    def test_definition_metadata_capacity_and_sampler(self):
        matched = self.matched
        reference = base.recipe_definition(base.PROFILE_4K)
        for profile, speculative in ((matched.PROFILE_AR, False), (matched.PROFILE_MTP, True)):
            with self.subTest(profile=profile):
                definition = matched.recipe_definition(profile)
                self.assertEqual(definition, json.loads(matched.recipe_json(profile)))
                self.assertEqual(definition['profile_id'], profile)
                self.assertEqual(definition['reference_profile'], base.PROFILE_4K)
                self.assertEqual(definition['reference_result_sha256'],
                                 '692149EEB38F89E662D9428A725533F14793680F5C70E8477A3B53E2DE8B04F3')
                self.assertEqual(definition['matched_requests_sha256'], matched.REQUESTS_SHA256)
                self.assertEqual(definition['fixed_calibration'], [13, 373])
                self.assertEqual(definition['input_count_provenance'],
                                 'same_pinned_tokenizer_template_and_request')
                self.assertEqual(definition['context_tokens'], 4096)
                self.assertEqual(definition['max_prompt_tokens'], 2304)
                self.assertEqual(definition['max_requests'], 36)
                self.assertEqual(definition['sampled'], reference['sampled'])
                self.assertEqual(definition['speculative'], speculative)
                self.assertEqual(definition['draft_tokens'], int(speculative))
                self.assertEqual(definition['mtp_policy'], 'length' if speculative else None)
                self.assertEqual(definition['mtp_draft_vocab'], 'full' if speculative else None)
                for row, original in zip(definition['schedule'], reference['schedule']):
                    self.assertEqual({k: v for k, v in row.items() if k != 'expected_prompt_tokens'}, original)
                    self.assertLessEqual(row['output_budget'], 256)
        self.assertEqual([row['output_budget'] for row in definition['schedule'][-3:]], [1, 1, 1])
        self.assertEqual([row['expected_prompt_tokens'] for row in definition['schedule'][-3:]], [2047]*3)
        with self.assertRaisesRegex(ValueError, 'unknown_profile'):
            matched.recipe_definition('unknown')

    def test_fixture_and_definition_are_fresh(self):
        matched = self.matched
        requests = matched.validate_fixture()
        self.assertEqual(len(requests), 36)
        requests[0]['messages'][0]['content'] = 'mutated'
        self.assertNotEqual(requests, matched.validate_fixture())
        definition = matched.recipe_definition(matched.PROFILE_AR)
        definition['schedule'][0]['case'] = 'mutated'
        definition['fixed_calibration'][0] = 9
        self.assertEqual(matched.recipe_definition(matched.PROFILE_AR)['schedule'][0]['case'], 'WARMUP')
        self.assertEqual(matched.recipe_definition(matched.PROFILE_AR)['fixed_calibration'], [13, 373])
        with patch.dict(base.FIXTURES['EN'], {'prompt': 'changed'}):
            with self.assertRaisesRegex(ValueError, 'matched_fixture_changed'):
                matched.validate_fixture()

    def test_reference_schedule_kind_is_pinned(self):
        matched = self.matched
        original_recipe_definition = base.recipe_definition

        def changed_recipe_definition(profile_id):
            definition = original_recipe_definition(profile_id)
            definition['schedule'][0]['kind'] = 'changed-kind'
            return definition

        with patch.object(base, 'recipe_definition', side_effect=changed_recipe_definition):
            with self.assertRaisesRegex(ValueError, 'matched_fixture_changed'):
                matched.validate_fixture()
            with self.assertRaisesRegex(ValueError, 'matched_fixture_changed'):
                matched.recipe_definition(matched.PROFILE_AR)

    def test_reference_sampled_metadata_is_pinned(self):
        matched = self.matched
        original_recipe_definition = base.recipe_definition

        def changed_recipe_definition(profile_id):
            definition = original_recipe_definition(profile_id)
            definition['sampled'] = not definition['sampled']
            return definition

        with patch.object(base, 'recipe_definition', side_effect=changed_recipe_definition):
            with self.assertRaisesRegex(ValueError, 'matched_fixture_changed'):
                matched.validate_fixture()
            with self.assertRaisesRegex(ValueError, 'matched_fixture_changed'):
                matched.recipe_definition(matched.PROFILE_AR)

    def test_rows_require_exact_identity_but_allow_runtime_results(self):
        matched = self.matched
        rows = matched.recipe_definition(matched.PROFILE_AR)['schedule']
        for ordinal in (-1, 36, True, 0.0, '0'):
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError):
                matched.request_for(dict(rows[0], ordinal=ordinal))
        mutations = (
            (1, 'case', 'DE'), (1, 'kind', 'warmup'), (1, 'mode', 'sampled'),
            (1, 'repetition', 1), (1, 'target_prompt_tokens', 2048),
            (1, 'cache_prompt', True), (1, 'output_budget', 1),
            (1, 'expected_prompt_tokens', True), (1, 'expected_prompt_tokens', 61.0),
        )
        for ordinal, field, replacement in mutations:
            with self.subTest(field=field, replacement=replacement):
                with self.assertRaises(ValueError):
                    matched.request_for(dict(rows[ordinal], **{field: replacement}))
        for field in ('case', 'kind', 'mode', 'repetition', 'target_prompt_tokens',
                      'cache_prompt', 'output_budget'):
            with self.subTest(missing=field), self.assertRaises(ValueError):
                altered = dict(rows[1])
                del altered[field]
                matched.request_for(altered)
        runtime_row = dict(rows[1], status='complete', result={'ok': True})
        self.assertEqual(matched.request_for(runtime_row), matched.request_for(rows[1]))

    def test_only_pinned_calibration_is_accepted(self):
        matched = self.matched
        row = matched.recipe_definition(matched.PROFILE_AR)['schedule'][-1]
        expected = matched.request_for(row)
        for calibration in (None, [], [13], [13, 373], (13, 373)):
            with self.subTest(calibration=calibration):
                self.assertEqual(matched.request_for(row, calibration), expected)
        for calibration in ([14], [13, 374], [13, 373, 1], [True], [13.0],
                            [13, True], [13, 373.0], 13, '13', [373]):
            with self.subTest(calibration=calibration), self.assertRaises(ValueError):
                matched.request_for(row, calibration)

    def test_request_validation_checks_complete_body_and_count(self):
        matched = self.matched
        rows = matched.recipe_definition(matched.PROFILE_MTP)['schedule']
        for row in rows:
            request = matched.request_for(row)
            self.assertEqual(matched.validate_request(row, request), row['expected_prompt_tokens'])
            self.assertLessEqual(row['expected_prompt_tokens'], 2304)
            self.assertLessEqual(row['expected_prompt_tokens'] + row['output_budget'], 4096)
        request = matched.request_for(rows[2])
        changes = (
            lambda r: r.update(extra=True),
            lambda r: r['messages'][0].update(content=r['messages'][0]['content'] + '!'),
            lambda r: r.update(temperature=True),
            lambda r: r.update(top_k=True),
            lambda r: r.update(seed=True),
            lambda r: r.update(max_tokens=True),
            lambda r: r.update(top_p=True),
            lambda r: r.update(top_p=1),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                altered = deepcopy(request)
                change(altered)
                matched.validate_request(rows[2], altered)
        with self.assertRaises(ValueError):
            matched.validate_request(rows[2], ['not a request'])

    def test_answer_validation_is_delegated(self):
        matched = self.matched
        observation = {'visible_answer': '4', 'finish_reason': 'stop'}
        self.assertEqual(matched.validate_answer('WARMUP', observation),
                         base.validate_answer('WARMUP', observation))


if __name__ == '__main__':
    unittest.main()
