import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from draft_profiles import tune


class LookupRouterTests(unittest.TestCase):
    def source(self):
        return {'backend': {'identifier': 'gufo-flash-next', 'context': 262144},
                'engine': {'kind': 'native', 'qualified': True,
                           'command': ['gufo.exe', '--speculative', 'mtp', '--mtp-model', 'head.gguf']}}

    def test_explicit_copy_workload_selects_isolated_lookup_profile(self):
        source = self.source()
        result = tune(source, draft_tokens=3, lookup_workload='copy')
        self.assertIn('--prompt-lookup', result['engine']['command'])
        self.assertNotIn('--prompt-lookup', source['engine']['command'])
        self.assertEqual(result['qualification']['lookup_workload'], 'copy')

    def test_prose_and_unknown_workloads_do_not_enable_lookup(self):
        result = tune(self.source(), draft_tokens=3, lookup_workload='prose')
        self.assertNotIn('--prompt-lookup', result['engine']['command'])
        with self.assertRaises(ValueError):
            tune(self.source(), draft_tokens=3, lookup_workload='magical')
        with self.assertRaises(ValueError):
            tune(self.source(), draft_tokens=3, lookup_workload='copy', prompt_lookup=False)


if __name__ == '__main__':
    unittest.main()
