import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('model_admission',Path(__file__).with_name('model_admission.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ModelAdmissionTests(unittest.TestCase):
 def setUp(self):self.policy=m.load_policy()
 def frame(self,physical=36,commit=131):
  return {'available_bytes':int(physical*m.GIB),'commit_headroom_bytes':int(commit*m.GIB)}
 def test_start_below36_fails(self):
  with self.assertRaises(ValueError):m.check_start_frame(self.frame(36-1/m.GIB),self.policy)
 def test_start_at36_and131_passes(self):m.check_start_frame(self.frame(),self.policy)
 def test_commit_below131_fails(self):
  with self.assertRaises(ValueError):m.check_start_frame(self.frame(commit=131-1/m.GIB),self.policy)
 def test_restart_at36_requires_five_frames_and_confirmed_cleanup(self):
  self.assertTrue(m.terminal_restart_passed([self.frame()]*5,self.policy,cleanup_confirmed=True))
  self.assertFalse(m.terminal_restart_passed([self.frame()]*5,self.policy,cleanup_confirmed=False))
  self.assertFalse(m.terminal_restart_passed([self.frame()]*4,self.policy,cleanup_confirmed=True))
 def test_restart_any_frame_below36_fails(self):
  self.assertFalse(m.terminal_restart_passed([self.frame()]*4+[self.frame(35.999)],self.policy,cleanup_confirmed=True))
 def test_restart_commit_below131_fails(self):
  self.assertFalse(m.terminal_restart_passed([self.frame()]*4+[self.frame(commit=130.999)],self.policy,cleanup_confirmed=True))
 def test_stale_frame_fails(self):
  with self.assertRaises(ValueError):m.check_start_frame(self.frame(),self.policy,age=2.001)
 def test_runtime18_and_commit131_cannot_be_changed_by_physical_policy(self):
  self.assertEqual(self.policy['runtime_reserve_gib'],18)
  self.assertEqual(self.policy['start_commit_headroom_gib'],131)
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'policy.json'
   for key,value in [('runtime_reserve_gib',17),('start_commit_headroom_gib',130)]:
    policy=dict(self.policy);policy[key]=value;p.write_text(json.dumps(policy))
    with self.assertRaises(ValueError):m.load_policy(p)
if __name__=='__main__':unittest.main()
