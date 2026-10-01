import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from article_metrics import normalized_seconds, acceptance, score_retrieval, phase_rates

class MetricsTests(unittest.TestCase):
    def test_normalized_three_turn_time_not_elapsed(self):
        self.assertAlmostEqual(sum(normalized_seconds(2,50) for _ in range(3)),66)
    def test_invalid_rate_is_rejected(self):
        for value in (0,-1,float('nan')):
            with self.assertRaises(ValueError):normalized_seconds(1,value)
    def test_acceptance_uses_drafted_tokens_not_rounds(self):
        self.assertEqual(acceptance([{'drafted':10,'accepted':9},{'drafted':90,'accepted':45}]),.54)
    def test_missing_acceptance_is_unknown_not_zero(self):
        self.assertIsNone(acceptance([{'drafted':None,'accepted':None}]))
    def test_exact_json_values_preserve_ampersand(self):
        expected={'spinner':'&["◐", "◓"]','name':'blue'}
        self.assertEqual(score_retrieval('```json\n{"spinner":"[\\"◐\\", \\"◓\\"]","name":"blue"}\n```',expected),{'correct':1,'total':2,'missing':['spinner']})
    def test_scoring_ignores_reasoning_and_substring_hits(self):
        self.assertEqual(score_retrieval('name is blue',{'name':'blue'})['correct'],0)
    def test_clock_adjustment_does_not_adjust_windows_wall(self):
        r=phase_rates({'prompt_per_second':100,'predicted_per_second':20},1.1)
        self.assertAlmostEqual(r['pp'],110);self.assertAlmostEqual(r['decode'],22)
if __name__=='__main__':unittest.main()
