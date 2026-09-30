import hashlib,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_toolchain import check_source

class PatchedSourceTests(unittest.TestCase):
    def fixture(self,root):
        (root/'kernel.cpp').write_bytes(b'exact ordered reduction')
        return {'source_commit':'base','tests':{},'source_patch':{
            'path':'kernel.cpp','after_sha256':hashlib.sha256(b'exact ordered reduction').hexdigest(),
            'sha256':'patch identity'}}

    def test_exact_patch_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            with patch('verify_toolchain.subprocess.check_output',side_effect=['base',' M kernel.cpp','kernel.cpp']):
                self.assertEqual(check_source(root,pins)['source_patch_sha256'],'patch identity')

    def test_extra_source_change_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            with patch('verify_toolchain.subprocess.check_output',side_effect=['base',' M kernel.cpp\n M other.cpp','kernel.cpp\nother.cpp']):
                with self.assertRaises(ValueError):check_source(root,pins)

    def test_changed_patch_bytes_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            (root/'kernel.cpp').write_bytes(b'not the approved implementation')
            with patch('verify_toolchain.subprocess.check_output',side_effect=['base',' M kernel.cpp','kernel.cpp']):
                with self.assertRaises(ValueError):check_source(root,pins)

    def test_unpatched_base_is_not_mislabeled_qualified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            with patch('verify_toolchain.subprocess.check_output',side_effect=['base','','']):
                with self.assertRaises(ValueError):check_source(root,pins)

if __name__=='__main__':unittest.main()
