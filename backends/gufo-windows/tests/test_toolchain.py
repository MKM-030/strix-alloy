import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_toolchain import check_sdk,check_source

class ToolchainTests(unittest.TestCase):
    def fixture(self, root):
        (root/'.info').mkdir();(root/'lib/llvm/bin').mkdir(parents=True);(root/'bin').mkdir()
        (root/'.info/version').write_text('10.0.0\n')
        (root/'lib/llvm/bin/clang++.exe').write_bytes(b'compiler fixture')
        (root/'bin/amdhip64_7.dll').write_bytes(b'runtime fixture')
        return {'sdk_version':'10.0.0','compiler_sha256':hashlib.sha256(b'compiler fixture').hexdigest(),
                'runtime_hashes':{'amdhip64_7.dll':hashlib.sha256(b'runtime fixture').hexdigest()}}

    def test_qualified_tuple_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            self.assertEqual(check_sdk(root,pins)['sdk_version'],'10.0.0')

    def test_newer_unsupported_compiler_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pins=self.fixture(root)
            (root/'.info/version').write_text('10.2.0')
            with self.assertRaisesRegex(ValueError,'requires qualified'):
                check_sdk(root,pins)

    def test_compiler_and_dll_tampering_refused(self):
        for name in ('lib/llvm/bin/clang++.exe','bin/amdhip64_7.dll'):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);pins=self.fixture(root)
                (root/name).write_bytes(b'different version')
                with self.assertRaises(ValueError):check_sdk(root,pins)

    def test_changed_source_revision_refused(self):
        with tempfile.TemporaryDirectory() as td,patch('verify_toolchain.subprocess.check_output',return_value='other\n'):
            with self.assertRaisesRegex(ValueError,'source revision'):
                check_source(td,{'source_commit':'expected','tests':{}})

    def test_modified_numerical_tests_refused(self):
        with tempfile.TemporaryDirectory() as td,patch('verify_toolchain.subprocess.check_output',side_effect=['pinned\n','']):
            root=Path(td);p=root/'tests/models/qwen38_flash_next/test_test.cpp'
            p.parent.mkdir(parents=True);p.write_bytes(b'weakened')
            with self.assertRaisesRegex(ValueError,'Numerical test changed'):
                check_source(root,{'source_commit':'pinned','tests':{'test':hashlib.sha256(b'original').hexdigest()}})

    def test_dirty_tracked_source_refused(self):
        with tempfile.TemporaryDirectory() as td,patch('verify_toolchain.subprocess.check_output',side_effect=['pinned\n',' M kernel.cpp']):
            with self.assertRaisesRegex(ValueError,'modified'):
                check_source(td,{'source_commit':'pinned','tests':{}})

if __name__=='__main__':unittest.main()
