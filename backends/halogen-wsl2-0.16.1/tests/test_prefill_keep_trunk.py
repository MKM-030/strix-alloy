import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import service

class PrefillKeepTrunkTests(unittest.TestCase):
    def test_v2_opt_in_is_explicit(self):
        base=service.environment(262144,'v2','Off',draft_tokens=2,prefill_chunk=8192)
        tuned=service.environment(262144,'v2','Off',draft_tokens=2,prefill_chunk=8192,prefill_keep_trunk=True)
        self.assertNotIn('HALOGEN_PREFILL_KEEP_TRUNK',base)
        self.assertEqual(tuned['HALOGEN_PREFILL_KEEP_TRUNK'],'1')
        self.assertEqual(tuned['HALOGEN_PREFILL_CHUNK'],'8192')
    def test_w4b_refused(self):
        with self.assertRaises(ValueError):
            service.environment(262144,'w4b','Off',prefill_keep_trunk=True)
    def test_admit_ticks_is_bitwise_policy(self):
        env=service.environment(262144,'v2','Off',admit_ticks=8)
        self.assertEqual(env['HALOGEN_ADMIT_TICKS'],'8')
        for value in (0,1025,True,'8'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                service.environment(262144,'v2','Off',admit_ticks=value)
