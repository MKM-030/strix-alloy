import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import article_metrics as metrics
class ReadinessTests(unittest.TestCase):
    def test_gateway_ready_does_not_skip_halogen_self_tests(self):
        value={'phase':'starting','checkpoint':'v2','context':262144}
        self.assertFalse(metrics.backend_validation_finished('halogen-v2',262144,value))
    def test_exact_checkpoint_and_capacity_are_required(self):
        value={'phase':'ready','checkpoint':'w4b','context':262144}
        with self.assertRaises(ValueError):metrics.backend_validation_finished('halogen-v2',262144,value)
    def test_finished_self_tests_allow_measurement(self):
        value={'phase':'ready','checkpoint':'v2','context':262144}
        self.assertTrue(metrics.backend_validation_finished('halogen-v2',262144,value))
    def test_native_engine_does_not_require_halogen_state(self):
        self.assertTrue(metrics.backend_validation_finished('gufo',262144,None))
if __name__=='__main__':unittest.main()
