import hashlib,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_article_inputs import write_verified

class InputTests(unittest.TestCase):
    def test_only_digest_matched_bytes_are_written(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample';data=b'fixture';sha=hashlib.sha256(data).hexdigest()
            write_verified(p,data,sha);self.assertEqual(p.read_bytes(),data)
    def test_wrong_source_digest_creates_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample'
            with self.assertRaises(ValueError):write_verified(p,b'changed','0'*64)
            self.assertFalse(p.exists())
    def test_existing_unrelated_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample';p.write_bytes(b'keep me');data=b'new data'
            with self.assertRaises(ValueError):write_verified(p,data,hashlib.sha256(data).hexdigest())
            self.assertEqual(p.read_bytes(),b'keep me')
if __name__=='__main__':unittest.main()
