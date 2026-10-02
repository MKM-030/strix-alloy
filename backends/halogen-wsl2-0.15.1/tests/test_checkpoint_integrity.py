import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_hash import hash_file
from checkpoint_integrity import receipt_matches,SHA,SIZE
class IntegrityTests(unittest.TestCase):
    def test_streamed_digest_matches_reference(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'weights'; data=bytes(range(256))*400
            path.write_bytes(data); result=hash_file(path,4096)
            self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual(result['identity']['size'],len(data))
    def test_cache_advice_is_range_limited(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'weights'; path.write_bytes(b'x'*12288)
            with patch('bounded_hash.os.posix_fadvise',create=True) as advise, patch('bounded_hash.os.POSIX_FADV_DONTNEED',4,create=True):
                hash_file(path,4096)
            self.assertEqual([(c.args[1],c.args[2]) for c in advise.call_args_list],[(0,4096),(4096,4096),(8192,4096)])
    def test_receipt_is_bound_to_full_file_identity(self):
        identity={'size':SIZE,'device':1,'inode':2,'mtime_ns':3,'ctime_ns':4}
        receipt={'sha256':SHA,'identity':identity}
        self.assertTrue(receipt_matches(receipt,identity))
        self.assertFalse(receipt_matches(receipt,{**identity,'mtime_ns':5}))
        self.assertFalse(receipt_matches({**receipt,'sha256':'0'*64},identity))
    def test_invalid_read_size_refused(self):
        with self.assertRaises(ValueError):hash_file('never-opened',2**31)
if __name__=='__main__':unittest.main()
