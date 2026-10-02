import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from article_metrics import validate_backend

class IdentityTests(unittest.TestCase):
    def test_actual_backend_must_match_label(self):
        self.assertEqual(validate_backend('gufo','gufo-flash-next'),'gufo-flash-next')
        self.assertEqual(validate_backend('halogen-v2','halogen-v2'),'halogen-v2')
    def test_same_context_is_not_enough_to_identify_backend(self):
        with self.assertRaises(ValueError):validate_backend('gufo','halogen-v2')
    def test_unknown_profile_is_refused(self):
        with self.assertRaises(ValueError):validate_backend('unknown','unknown')
if __name__=='__main__':unittest.main()
