from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manage

class ProfileTests(unittest.TestCase):
    def test_context_and_cache_validation(self):
        for capacity in (True,0,262145):
            with self.assertRaises(ValueError): manage.make_profile('Halogen','v2',capacity)
        with self.assertRaises(ValueError): manage.make_profile('Halogen','bad',129024)
        with self.assertRaises(ValueError): manage.make_profile('Halogen','v2',129024,'unknown')

    def test_native_candidates_do_not_silently_fall_back(self):
        with patch.object(Path,'is_file',return_value=False):
            for backend in ('GUFO','Projfix'):
                with self.assertRaisesRegex(ValueError,'no qualified'):
                    manage.make_profile(backend,'w4b',129024)

if __name__=='__main__': unittest.main()
