import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from profile import command
class ModeTests(unittest.TestCase):
    def test_serial_does_not_load_or_enable_a_draft(self):
        args=command('runtime','target','draft',262144,mode='serial')
        self.assertNotIn('-md',args)
        self.assertNotIn('draft-mtp',args)
        self.assertEqual(args[args.index('--lazy-mode')+1],'on')
    def test_mtp_is_explicit(self):
        args=command('runtime','target','draft',262144,mode='mtp')
        self.assertEqual(args[args.index('-md')+1],'draft')
        self.assertEqual(args[args.index('--spec-type')+1],'draft-mtp')
    def test_unknown_mode_cannot_silently_fallback(self):
        with self.assertRaises(ValueError):command('runtime','target','draft',262144,mode='automatic')
if __name__=='__main__':unittest.main()
