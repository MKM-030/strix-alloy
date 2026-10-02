import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import service as s

class PrefillChunkTests(unittest.TestCase):
    def env(self,value):
        try: return s.environment(262144,'v2','Off',draft_tokens=1,prefill_chunk=value)
        except TypeError as exc: self.fail('Prefill option missing: '+str(exc))
    def test_matching_chunk_and_scratch_limit(self):
        for value in (2048,4096,8192):
            env=self.env(value)
            self.assertEqual(env['HALOGEN_PREFILL_CHUNK'],str(value))
            self.assertGreaterEqual(int(env['HALOGEN_MAX_TOK']),value)
            self.assertEqual(env['HALOGEN_MTP_DEPTH'],'1')
            self.assertEqual(env['HALOGEN_PROMPT_CACHE'],'0')
    def test_default_environment_preserved(self):
        self.assertEqual(self.env(None),s.environment(262144,'v2','Off',draft_tokens=1))
    def test_bad_chunk_refused(self):
        for value in (0,True,'4096',1.5,16384):
            with self.subTest(value=value),self.assertRaises(ValueError): self.env(value)
    def test_cli_rejects_chunk_larger_than_context(self):
        with self.assertRaises((ValueError,SystemExit)):
            s.options(['--context-size','4096','--prefill-chunk','8192'])
