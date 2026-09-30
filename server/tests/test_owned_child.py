import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from owned_child import JobChild

@unittest.skipUnless(os.name=='nt','Windows job ownership')
class OwnedChildTests(unittest.TestCase):
    def test_owned_sleeping_process_is_stopped_by_job_close(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            child=JobChild([sys.executable,'-u','-c','import time; print("owned"); time.sleep(30)'],
                cwd=root,env=dict(os.environ),stdout_path=root/'out',stderr_path=root/'err')
            try:
                self.assertIsNone(child.poll())
                self.assertTrue(child.contains(child.pid))
                self.assertFalse(child.contains(os.getpid()))
            finally:
                child.close()
            self.assertIsNotNone(child.poll())

if __name__=='__main__': unittest.main()
