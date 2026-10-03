import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import service

class GuardExitStateTests(unittest.TestCase):
    def test_running_guard_is_not_an_abnormal_exit(self):
        self.assertFalse(service.guard_exit_failed(None))

    def test_clean_exit_is_not_a_failure(self):
        self.assertFalse(service.guard_exit_failed(0))

    def test_nonzero_and_signal_exit_are_failures(self):
        self.assertTrue(service.guard_exit_failed(2))
        self.assertTrue(service.guard_exit_failed(-15))

if __name__=='__main__':unittest.main()
