import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller as c
REPO=Path(__file__).resolve().parents[2]
class Halogen01816Forwarding(unittest.TestCase):
 def engine(self):
  return dict(kind='halogen',directory='backends/halogen-wsl2-0.18.16',checkpoint='v2',context=32768,prompt_cache='Off',launcher='python',python_executable=sys.executable,powershell='powershell.exe',prefill_chunk=8192,max_prefill_tokens=8192,disable_vision=True,kernel_controls={'HALOGEN_DECODE_PREFETCH':0},speculation_policy={'HALOGEN_PLD':'3,3','HALOGEN_MTP_GATE_P':'0.90'},api_defaults={'enable_thinking':False,'reasoning_effort':'low','max_thinking_tokens':2048})
 def test_fresh_profile_validates_and_forwards(self):
  e=self.engine();directory=c.validate_engine(e,REPO);argv=c.halogen_launch_command(e,directory)
  self.assertEqual(directory,REPO/'backends/halogen-wsl2-0.18.16')
  self.assertEqual(Path(argv[0]),Path(sys.executable));self.assertIn('--disable-vision',argv)
  self.assertEqual(json.loads(argv[argv.index('--speculation-policy-json')+1]),e['speculation_policy'])
  self.assertEqual(json.loads(argv[argv.index('--api-defaults-json')+1]),e['api_defaults'])
  self.assertEqual(json.loads(argv[argv.index('--kernel-controls-json')+1]),{'HALOGEN_DECODE_PREFETCH':0})
  self.assertEqual(argv[argv.index('--prompt-cache')+1],'Off')
 def test_unknown_backend_rejected_by_all_normal_allowlists(self):
  e=self.engine();unknown=REPO/'backends/halogen-wsl2-0.18.17'
  for check in (lambda:c.halogen_speculation_module(unknown),lambda:c.halogen_api_defaults_arguments(e,unknown),lambda:c.halogen_vision_arguments(e,unknown),lambda:c.halogen_launch_command(e,unknown)):
   with self.assertRaises(ValueError):check()
if __name__=='__main__':unittest.main()
