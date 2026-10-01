import hashlib,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from profile import validate_runtime
class RuntimeIdentityTests(unittest.TestCase):
    def test_exact_bytes_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);(root/'kernel.dll').write_bytes(b'known')
            pins={'runtime_files':{'kernel.dll':hashlib.sha256(b'known').hexdigest()}}
            self.assertEqual(validate_runtime(root,pins),root.resolve())
            (root/'kernel.dll').write_bytes(b'changed')
            with self.assertRaises(ValueError):validate_runtime(root,pins)
    def test_manifest_cannot_read_outside_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                validate_runtime(folder,{'runtime_files':{'../outside.dll':'0'*64}})
    def test_missing_component_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                validate_runtime(folder,{'runtime_files':{'missing.dll':'0'*64}})
if __name__=='__main__':unittest.main()
