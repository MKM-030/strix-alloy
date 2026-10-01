import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from profile import command
class ProfileTests(unittest.TestCase):
    def test_mapping_and_conservative_microbatch_are_explicit(self):
        args=command('runtime','target.gguf','draft.gguf',262144)
        self.assertIn('--lazy-mode',args)
        self.assertEqual(args[args.index('--lazy-mode')+1],'on')
        self.assertEqual(args[args.index('-ub')+1],'512')
        self.assertEqual(args[args.index('-ctk')+1],'f16')
        self.assertEqual(args[args.index('-ctv')+1],'f16')
        self.assertEqual(args[args.index('--host')+1],'127.0.0.1')
        self.assertEqual(args[args.index('-c')+1],'262144')
    def test_no_guard_or_timeout_disable_flags(self):
        args=command('runtime','target.gguf','draft.gguf',32768)
        self.assertNotIn('--no-auth',args)
        self.assertNotIn('--no-check',args)
        self.assertNotIn('on-direct',args)
    def test_unreviewed_context_is_rejected(self):
        for value in (0, True, 1048576):
            with self.assertRaises(ValueError):command('runtime','target','draft',value)
if __name__=='__main__':unittest.main()
