import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller
import draft_profiles


class ManagedKernelControlsTests(unittest.TestCase):
    repo=Path(__file__).resolve().parents[2]

    def profile(self,version='0.16.2'):
        return {'backend':{'identifier':'halogen-v2','context':262144},
                'engine':{'kind':'halogen','directory':'backends/halogen-wsl2-'+version,
                          'checkpoint':'v2','context':262144}}

    def tune(self,source,**options):
        try: return draft_profiles.tune(source,draft_tokens=1,**options)
        except TypeError as error: self.fail('Kernel-controls tuning support missing: '+str(error))

    def test_validated_json_reaches_managed_argv_without_sys_path_mutation(self):
        builder=getattr(controller,'halogen_kernel_arguments',None)
        self.assertIsNotNone(builder,'Managed kernel-controls forwarding is missing')
        engine=self.profile()['engine']; engine['kernel_controls']={'HALOGEN_DN_SCAN':0}
        before=list(sys.path)
        directory=controller.validate_engine(engine,self.repo)
        args=builder(engine,directory)
        self.assertEqual(args[0],'-KernelControlsJson')
        self.assertEqual(json.loads(args[1]),{'HALOGEN_DN_SCAN':0})
        self.assertEqual(sys.path,before)

    def test_unknown_kernel_controls_are_refused_before_launch(self):
        engine=self.profile()['engine']; engine['kernel_controls']={'HALOGEN_HOST_RESERVE_GIB':0}
        with self.assertRaises(ValueError): controller.validate_engine(engine,self.repo)

    def test_old_launcher_cannot_accept_kernel_controls(self):
        engine=self.profile('0.15.1')['engine']; engine['kernel_controls']={'HALOGEN_DN_SCAN':0}
        with self.assertRaisesRegex(ValueError,'kernel'):
            controller.validate_engine(engine,self.repo)

    def test_tuning_copies_validated_kernel_controls(self):
        source=self.profile(); before=copy.deepcopy(source)
        controls={'HALOGEN_DN_SCAN':0}; result=self.tune(source,kernel_controls=controls)
        self.assertEqual(result['engine']['kernel_controls'],controls)
        self.assertEqual(source,before)
        controls['HALOGEN_DN_SCAN']=1
        self.assertEqual(result['engine']['kernel_controls'],{'HALOGEN_DN_SCAN':0})

    def test_invalid_inherited_or_explicit_controls_cannot_be_written(self):
        with self.assertRaises(ValueError):
            self.tune(self.profile(),kernel_controls={'HALOGEN_CACHE_FILE':0})
        source=self.profile(); source['engine']['kernel_controls']={'HALOGEN_DN_SCAN':True}
        with self.assertRaises(ValueError): self.tune(source)
        with self.assertRaises(ValueError):
            self.tune(self.profile('0.15.1'),kernel_controls={'HALOGEN_DN_SCAN':0})
