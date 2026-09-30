"""Pinned multi-file source patch acceptance, including a new helper header."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_toolchain import check_source

def sha(value):return hashlib.sha256(value).hexdigest()
class MultiFileSourceTests(unittest.TestCase):
 def fixture(self,root):
  (root/'kernel.cpp').write_bytes(b'ordered kernel')
  (root/'numeric.hpp').write_bytes(b'explicit rounding')
  return {'source_commit':'base','tests':{},'source_patch':{'sha256':'patch',
    'files':{'kernel.cpp':{'after_sha256':sha(b'ordered kernel')},
             'numeric.hpp':{'after_sha256':sha(b'explicit rounding')}}}}
 def commands(self,*args,**kwargs):
  command=args[0]
  if 'rev-parse' in command:return 'base'
  if 'status' in command:return ' M kernel.cpp\n?? numeric.hpp\n'
  if 'diff' in command:return 'kernel.cpp\n'
  if 'ls-files' in command:return 'numeric.hpp\n'
  raise AssertionError(command)
 def test_exact_modified_and_added_source_is_accepted(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pins=self.fixture(root)
   with patch('verify_toolchain.subprocess.check_output',side_effect=self.commands):
    self.assertEqual(check_source(root,pins)['source_patch_sha256'],'patch')
 def test_added_helper_tampering_is_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pins=self.fixture(root);(root/'numeric.hpp').write_bytes(b'different')
   with patch('verify_toolchain.subprocess.check_output',side_effect=self.commands):
    with self.assertRaises(ValueError):check_source(root,pins)
 def test_partial_patch_is_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pins=self.fixture(root);(root/'numeric.hpp').unlink()
   with patch('verify_toolchain.subprocess.check_output',side_effect=self.commands):
    with self.assertRaises(ValueError):check_source(root,pins)
 def test_unrelated_untracked_source_is_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pins=self.fixture(root)
   def extra(*args,**kwargs):
    if 'ls-files' in args[0]:return 'numeric.hpp\nother.cpp\n'
    return self.commands(*args,**kwargs)
   with patch('verify_toolchain.subprocess.check_output',side_effect=extra):
    with self.assertRaises(ValueError):check_source(root,pins)
 def test_header_path_escape_is_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);pins=self.fixture(root)
   pins['source_patch']['files']['../outside']={'after_sha256':'0'*64}
   with patch('verify_toolchain.subprocess.check_output',side_effect=self.commands):
    with self.assertRaises(ValueError):check_source(root,pins)
if __name__=='__main__':unittest.main()
