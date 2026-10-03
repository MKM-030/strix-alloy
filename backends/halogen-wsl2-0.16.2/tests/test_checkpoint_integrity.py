import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_hash import hash_file
from checkpoint_integrity import receipt_matches,SHA,SIZE
import checkpoint_integrity as integrity
import portable
import service
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

class NgramIntegrityTests(unittest.TestCase):
    SOURCE='/mnt/c/models/qwen38-flash-next-w4b.hgn'
    NGRAM_SHA='9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6'
    NGRAM_IDENTITY={'size':124068083904,'device':71,'inode':1234,'mtime_ns':5,'ctime_ns':6}
    CORE_IDENTITY={'size':66687678432,'device':1,'inode':2,'mtime_ns':3,'ctime_ns':4}

    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.local=self.root/'.local'; self.local.mkdir()
        self.machine={'distro':'Test','user':'tester','models':'/home/tester/models','ngram_source':self.SOURCE}
        (self.local/'v2-integrity.json').write_text(json.dumps({'sha256':SHA,'identity':self.CORE_IDENTITY}))
        self.write_ngram_receipt()
        self.observed=[]
        for owner,name,value in ((portable,'ROOT',self.root),(portable,'LOCAL',self.local),(service,'LOCAL',self.local)):
            patcher=patch.object(owner,name,value); patcher.start(); self.addCleanup(patcher.stop)

    def write_ngram_receipt(self,**changes):
        receipt={'source':self.SOURCE,'sha256':self.NGRAM_SHA,'identity':dict(self.NGRAM_IDENTITY)}
        receipt.update(changes)
        (self.local/'ngram-integrity.json').write_text(json.dumps(receipt))

    def verify(self,identity=None,hash_sha=None):
        selected=self.machine.get('ngram_source') or '/home/tester/models/qwen38-flash-next-w4b.hgn'
        def wsl(distro,user,*args,timeout=30):
            self.assertEqual((distro,user),('Test','tester'))
            self.assertEqual(args[:2],('python3','-c'))
            code,source=args[2:]
            self.observed.append((code,source))
            if source=='/home/tester/models/qwen38-flash-next-v2.hgn':
                self.assertEqual(code,integrity.STAT_CODE)
                return json.dumps(self.CORE_IDENTITY)
            self.assertEqual(source,selected)
            current=dict(self.NGRAM_IDENTITY) if identity is None else identity
            if code==integrity.STAT_CODE: return json.dumps(current)
            self.assertEqual(code,integrity.HASH_CODE)
            if hash_sha is None: raise AssertionError('A matching receipt must avoid model hashing')
            return json.dumps({'sha256':hash_sha,'identity':current})
        with patch.object(portable,'wsl',side_effect=wsl),patch.object(portable,'check_hash'):
            return service.verify_checkpoint(self.machine,'v2')

    def test_matching_selected_receipt_avoids_model_hashing(self):
        self.verify()
        self.assertIn((integrity.STAT_CODE,self.SOURCE),self.observed)

    def test_default_source_is_verified_without_configured_override(self):
        self.machine.pop('ngram_source')
        source='/home/tester/models/qwen38-flash-next-w4b.hgn'
        self.write_ngram_receipt(source=source)
        self.verify()
        self.assertIn((integrity.STAT_CODE,source),self.observed)

    def test_any_changed_file_identity_requires_a_valid_rehash(self):
        for field in ('device','inode','mtime_ns','ctime_ns'):
            with self.subTest(field=field):
                current={**self.NGRAM_IDENTITY,field:self.NGRAM_IDENTITY[field]+1}
                with self.assertRaisesRegex(ValueError,'N-gram'):
                    self.verify(identity=current,hash_sha='0'*64)

    def test_wrong_cached_digest_cannot_authorize_source(self):
        self.write_ngram_receipt(sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'N-gram'):
            self.verify(hash_sha='0'*64)

    def test_receipt_for_another_source_cannot_authorize_selected_path(self):
        self.write_ngram_receipt(source='/mnt/c/models/another-w4b.hgn')
        with self.assertRaisesRegex(ValueError,'N-gram'):
            self.verify(hash_sha='0'*64)

    def test_wrong_source_size_is_refused_before_hashing(self):
        with self.assertRaisesRegex(ValueError,'N-gram'):
            self.verify(identity={**self.NGRAM_IDENTITY,'size':124068083903})

    def test_valid_rehash_replaces_stale_receipt(self):
        current={**self.NGRAM_IDENTITY,'mtime_ns':7}
        self.verify(identity=current,hash_sha=self.NGRAM_SHA)
        receipt=json.loads((self.local/'ngram-integrity.json').read_text())
        self.assertEqual(receipt['identity'],current)
        self.assertEqual(receipt['source'],self.SOURCE)
        self.assertEqual(receipt['sha256'],self.NGRAM_SHA)
if __name__=='__main__':unittest.main()
