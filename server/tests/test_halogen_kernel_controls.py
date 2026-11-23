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

    def test_0172_draft_vocab_q8_uses_existing_numeric_route(self):
        source=self.profile('0.17.2')
        controls={'HALOGEN_DRAFT_VOCAB_Q8':1}
        result=self.tune(source,kernel_controls=controls)
        self.assertNotIn('kernel_controls',source['engine'])
        directory=controller.validate_engine(result['engine'],self.repo)
        args=controller.halogen_kernel_arguments(result['engine'],directory)
        self.assertEqual(args[0],'-KernelControlsJson')
        self.assertEqual(json.loads(args[1]),controls)
        module=controller.halogen_kernel_module(directory)
        self.assertEqual(module.environment(controls),{'HALOGEN_DRAFT_VOCAB_Q8':'1'})
        self.assertNotIn('HALOGEN_DRAFT_VOCAB_Q8',module.environment({}))

    def test_0207_concurrency_mode_control_is_forwarded_and_bounded(self):
        source=self.profile('0.20.7')
        controls={'HALOGEN_CONC_MODE':0}
        result=self.tune(source,kernel_controls=controls)
        directory=controller.validate_engine(result['engine'],self.repo)
        args=controller.halogen_kernel_arguments(result['engine'],directory)
        self.assertEqual(json.loads(args[1]),controls)
        module=controller.halogen_kernel_module(directory)
        self.assertEqual(module.environment(controls),{'HALOGEN_CONC_MODE':'0'})
        self.assertNotIn('HALOGEN_CONC_MODE',module.environment({}))
        with self.assertRaises(ValueError):
            module.environment({'HALOGEN_CONC_MODE':2})

    def test_0207_draft_vocab_q8_uses_the_same_exact_integer_route(self):
        source=self.profile('0.20.7')
        controls={'HALOGEN_DRAFT_VOCAB_Q8':1}
        result=self.tune(source,kernel_controls=controls)
        directory=controller.validate_engine(result['engine'],self.repo)
        args=controller.halogen_kernel_arguments(result['engine'],directory)
        self.assertEqual(json.loads(args[1]),controls)
        module=controller.halogen_kernel_module(directory)
        self.assertEqual(module.environment(controls),
                         {'HALOGEN_DRAFT_VOCAB_Q8':'1'})

    def test_0207_i4r_two_row_decode_group_is_an_explicit_trial(self):
        engine = self.profile('0.20.7')['engine']
        flag = 'HALOGEN_I4R_DEC_GROUP'
        module = controller.halogen_kernel_module(self.repo / engine['directory'])
        self.assertNotIn(flag, module.environment({}))
        engine['kernel_controls'] = {flag: 2}
        directory = controller.validate_engine(engine, self.repo)
        args = controller.halogen_kernel_arguments(engine, directory)
        self.assertEqual(json.loads(args[1]), {flag: 2})
        self.assertEqual(module.environment({flag: 2}), {flag: '2'})
        for invalid in (True, '2', 1, 3, 4, 0):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                module.environment({flag: invalid})

    def test_0207_nested_admission_2048_is_an_explicit_trial(self):
        engine = self.profile('0.20.7')['engine']
        flag = 'HALOGEN_ADMIT_NEST_MAX'
        module = controller.halogen_kernel_module(self.repo / engine['directory'])
        self.assertNotIn(flag, module.environment({}))
        engine['kernel_controls'] = {flag: 2048}
        directory = controller.validate_engine(engine, self.repo)
        args = controller.halogen_kernel_arguments(engine, directory)
        self.assertEqual(json.loads(args[1]), {flag: 2048})
        self.assertEqual(module.environment({flag: 2048}), {flag: '2048'})
        for invalid in (True, '2048', 0, 1024, 4096):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                module.environment({flag: invalid})

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
