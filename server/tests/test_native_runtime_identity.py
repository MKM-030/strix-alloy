import hashlib,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import validate_engine

class RuntimeIdentityTests(unittest.TestCase):
    def fixture(self, root):
        executable=root/'engine.exe';executable.write_bytes(b'executable fixture')
        dll=root/'amdhip64_7.dll';dll.write_bytes(b'qualified runtime')
        return {'kind':'native','qualified':True,
            'command':[str(executable),'--host','127.0.0.1'],
            'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'runtime_hashes':{'amdhip64_7.dll':hashlib.sha256(dll.read_bytes()).hexdigest()}}
    def test_matching_runtime_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=self.fixture(root)
            self.assertEqual(validate_engine(config,root),root)
    def test_changed_runtime_refused_before_launch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=self.fixture(root)
            (root/'amdhip64_7.dll').write_bytes(b'new unqualified runtime')
            with self.assertRaisesRegex(ValueError,'runtime bytes changed'):
                validate_engine(config,root)
    def test_pin_cannot_escape_runtime_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);config=self.fixture(root)
            config['runtime_hashes']={'../outside.dll':'0'*64}
            with self.assertRaisesRegex(ValueError,'app-local filename'):
                validate_engine(config,root)
if __name__=='__main__':unittest.main()
