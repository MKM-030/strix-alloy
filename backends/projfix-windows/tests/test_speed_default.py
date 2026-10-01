import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('projfix_speed_profile',Path(__file__).parents[1]/'profile.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)

class SpeedDefaultTests(unittest.TestCase):
    def test_default_uses_measured_fast_serial_placement(self):
        args=profile.command('runtime','target','draft',262144)
        self.assertNotIn('-md',args)
        self.assertNotIn('--spec-type',args)
        self.assertIn('-ot',args)
    def test_explicit_legacy_mtp_does_not_use_failed_mixed_placement(self):
        args=profile.command('runtime','target','draft',262144,mode='mtp')
        self.assertIn('-md',args)
        self.assertNotIn('-ot',args)
        self.assertEqual(args[args.index('--spec-type')+1],'draft-mtp')

if __name__=='__main__':unittest.main()
