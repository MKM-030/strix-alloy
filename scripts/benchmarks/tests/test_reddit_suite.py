import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from reddit_suite import compare_quality, compare_top_logprobs, make_prompt, NEEDLE


class RedditSuiteTests(unittest.TestCase):
    def test_tokenizer_bounded_prompt_preserves_hidden_key(self):
        class WordTokenizer:
            def encode(self, text, *, add_special_tokens):
                return SimpleNamespace(ids=text.split())

        tokenizer = WordTokenizer()
        for task in ('retrieval', 'generation'):
            with self.subTest(task=task):
                prompt = make_prompt(512, tokenizer, task=task)
                count = len(tokenizer.encode(prompt, add_special_tokens=False).ids)
                self.assertLessEqual(count, 512)
                self.assertGreater(count + 5, 512)
                self.assertEqual(prompt.count('Hidden key: NEEDLE-7319'), 1)
                self.assertGreater(prompt.index(NEEDLE), len(prompt) // 4)
                self.assertLess(prompt.index(NEEDLE), len(prompt) * 3 // 4)
                self.assertEqual(prompt, make_prompt(512, tokenizer, task=task))

    def test_prompt_is_repeatable_and_buries_needle(self):
        prompt = make_prompt(8192)
        self.assertEqual(prompt, make_prompt(8192))
        self.assertEqual(prompt.count(NEEDLE), 1)
        self.assertGreater(prompt.index(NEEDLE), len(prompt) // 4)
        self.assertLess(prompt.index(NEEDLE), len(prompt) * 3 // 4)
        self.assertNotEqual(prompt, make_prompt(16384))

    def test_occupied_prompt_requests_full_length_generation(self):
        prompt = make_prompt(8192, task='generation')
        self.assertIn('Continue until the token limit.', prompt)
        self.assertNotIn('Return only the hidden key.', prompt)
        self.assertEqual(prompt.count(NEEDLE), 1)
        with self.assertRaises(ValueError):
            make_prompt(8192, task='unreviewed')

    def test_top_n_proxy_requires_overlap_and_finite_scores(self):
        control = [{'token': 'A', 'logprob': -0.1, 'top_logprobs': [
            {'token': 'A', 'logprob': -0.1}, {'token': 'B', 'logprob': -2.5}]}]
        self.assertEqual(compare_top_logprobs(control, control)['max_abs_delta'], 0)
        self.assertIsNone(compare_top_logprobs(control, []))
        self.assertIsNone(compare_top_logprobs(control, [{'token': 'A', 'logprob': -0.1,
                                                          'top_logprobs': []}]))
        changed = [{'token': 'A', 'logprob': -0.1, 'top_logprobs': [
            {'token': 'A', 'logprob': -0.1}, {'token': 'C', 'logprob': -2.5}]}]
        self.assertIsNone(compare_top_logprobs(control, changed))
        self.assertIsNone(compare_top_logprobs([{'token': 'A'}], [{'token': 'A'}]))

    def test_quality_requires_control_capability_if_exposed(self):
        control = {'backend': 'halogen-v2', 'rows': [{'name': 'arithmetic', 'passed': True,
            'sha256': 'abc', 'top_logprobs': [{'token': 'A', 'logprob': -0.1,
                                              'top_logprobs': [{'token': 'A', 'logprob': -0.1}]}]}]}
        candidate = {'backend': 'halogen-v2', 'rows': [{'name': 'arithmetic', 'passed': True,
            'sha256': 'abc', 'top_logprobs': None}]}
        result = compare_quality(control, candidate)
        self.assertFalse(result['passed'])
        self.assertIn('arithmetic:logprob_unavailable', result['failures'])

    def test_quality_rejects_functional_and_hash_drift(self):
        control = {'backend': 'gufo-flash-next', 'rows': [{'name': 'arithmetic', 'passed': True,
                                                          'sha256': 'abc'}]}
        candidate = {'backend': 'gufo-flash-next', 'rows': [{'name': 'arithmetic', 'passed': False,
                                                            'sha256': 'def'}]}
        result = compare_quality(control, candidate)
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatched'], ['arithmetic'])
        self.assertEqual(result['logprob_proxy'], {})

    def test_quality_distinguishes_identical_format_failures_from_output_parity(self):
        row = {'name': 'tool_json', 'passed': False, 'functional_passed': True,
               'format_passed': False, 'sha256': 'fenced-raw-hash'}
        control = {'backend': 'halogen-v2', 'structured_json': False,
                   'grading_policy': 'functional_and_strict_format_v1', 'rows': [row]}
        candidate = dict(control)
        result = compare_quality(control, candidate)
        self.assertFalse(result['passed'])
        self.assertTrue(result['functional_passed'])
        self.assertTrue(result['parity_passed'])
        changed = dict(candidate, rows=[dict(row, sha256='changed-raw-hash')])
        self.assertFalse(compare_quality(control, changed)['parity_passed'])
        for changed in (dict(candidate, structured_json=True),
                        dict(candidate, grading_policy='different-policy')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                compare_quality(control, changed)


if __name__ == '__main__':
    unittest.main()
