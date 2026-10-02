import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from compare_reddit import compare_runs


class ComparisonTests(unittest.TestCase):
    def identity(self):
        return {'backend': 'halogen-v2', 'suite_sha256': 'suite',
                'harness_sha256': 'harness', 'tokenizer_sha256': 'tokenizer',
                'context_capacity': 262144, 'ladder_max': 65536, 'reps': 2}

    def rows(self, mode='serial', response='same'):
        return [{'name': 'PP8192', 'rep': index, 'mode': mode,
                 'prompt_sha256': 'prompt', 'sha256': response,
                 'usage': {'prompt_tokens': 8200, 'completion_tokens': 1}}
                for index in range(2)]

    def test_cross_mode_compare_and_output_drift(self):
        result = compare_runs(self.identity(), self.rows(), 'serial',
                              self.identity(), self.rows('speculative'), 'speculative')
        self.assertTrue(result['passed'])
        candidate = self.rows('speculative', 'different')
        result = compare_runs(self.identity(), self.rows(), 'serial',
                              self.identity(), candidate, 'speculative')
        self.assertFalse(result['passed'])
        self.assertEqual(result['output_drift'], ['PP8192/0', 'PP8192/1'])

    def test_input_and_count_drift_fail_closed(self):
        candidate = self.rows()
        candidate[0]['prompt_sha256'] = 'wrong'
        candidate[1]['usage']['completion_tokens'] = 0
        result = compare_runs(self.identity(), self.rows(), 'serial',
                              self.identity(), candidate, 'serial')
        self.assertFalse(result['passed'])
        self.assertEqual(result['input_drift'], ['PP8192/0'])
        self.assertEqual(result['token_count_drift'], ['PP8192/1'])
        with self.assertRaises(ValueError):
            compare_runs(self.identity(), self.rows(), 'serial',
                         self.identity(), candidate[:1], 'serial')

    def test_unmatched_config_or_duplicate_cases_rejected(self):
        changed = {**self.identity(), 'tokenizer_sha256': 'other'}
        with self.assertRaises(ValueError):
            compare_runs(self.identity(), self.rows(), 'serial',
                         changed, self.rows(), 'serial')
        with self.assertRaises(ValueError):
            compare_runs(self.identity(), self.rows() * 2, 'serial',
                         self.identity(), self.rows(), 'serial')


if __name__ == '__main__':
    unittest.main()
