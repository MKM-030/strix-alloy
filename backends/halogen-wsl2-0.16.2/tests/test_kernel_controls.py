"""Offline control validation and launcher forwarding; no inference runtime."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'scripts/kernel_controls.py'
MODULE=None
if SOURCE.is_file():
    spec=importlib.util.spec_from_file_location('test_halogen_kernel_controls',SOURCE)
    MODULE=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)


class KernelControlsTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(MODULE,'Explicit kernel-controls validator is missing')
        return MODULE

    def test_exact_controls_preserve_input_and_become_string_environment(self):
        controls={'HALOGEN_DN_SCAN':0,'HALOGEN_DN_FUSED':1,'HALOGEN_ATTN_FA':64,
                  'HALOGEN_FA_OPT':5,'HALOGEN_FLASH_MOE_GEMM':8,'HALOGEN_FLASH_MOE_V2':2}
        before=copy.deepcopy(controls)
        self.assertEqual(self.module().validate(controls),before)
        self.assertEqual(self.module().environment(controls),
                         {'HALOGEN_DN_SCAN':'0','HALOGEN_DN_FUSED':'1','HALOGEN_ATTN_FA':'64',
                          'HALOGEN_FA_OPT':'5','HALOGEN_FLASH_MOE_GEMM':'8','HALOGEN_FLASH_MOE_V2':'2'})
        self.assertEqual(controls,before)

    def test_unknown_memory_path_driver_and_npu_keys_are_refused(self):
        for key in ('DN_SCAN','HALOGEN_UNKNOWN','HALOGEN_HOST_RESERVE_GIB','HALOGEN_CHECKPOINT',
                    'HALOGEN_CACHE_FILE','HIP_VISIBLE_DEVICES','HALOGEN_NPU_MODELS'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.module().validate({key:0})

    def test_switches_require_integer_zero_or_one(self):
        for value in (-1,2,True,False,'0',None,0.5):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.module().validate({'HALOGEN_DN_SCAN':value})

    def test_counters_are_bounded_nonnegative_integers(self):
        for key in ('HALOGEN_FLASH_MOE_FUSED_N','HALOGEN_CACHE_BRANCHES','HALOGEN_CACHE_ENTRIES',
                    'HALOGEN_CACHE_CKPT','HALOGEN_CACHE_RESERVE_MB'):
            for value in (-1,1000000000,True,'1',1.5):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    self.module().validate({key:value})

    def test_json_duplicate_keys_and_nonobjects_are_refused(self):
        for value in ('{"HALOGEN_DN_SCAN":0,"HALOGEN_DN_SCAN":1}','[]','null','1','{bad}'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.module().parse(value)
        self.assertEqual(self.module().parse('{"HALOGEN_DN_SCAN":0}'),{'HALOGEN_DN_SCAN':0})

    def test_lookup_io_threads_accept_only_the_matched_probe_values(self):
        for value in (32,64):
            with self.subTest(value=value):
                controls={'HALOGEN_NGRAM_GATHER_THREADS':value}
                try:
                    parsed=self.module().parse(json.dumps(controls))
                except ValueError as error:
                    self.fail('Documented lookup-I/O probe value was refused: '+str(error))
                self.assertEqual(parsed,controls)
                self.assertEqual(self.module().environment(controls),
                                 {'HALOGEN_NGRAM_GATHER_THREADS':str(value)})

    def test_lookup_io_threads_refuse_coercion_and_unmeasured_values(self):
        for value in (0,1,16,31,33,63,65,128,-1,True,False,'32',32.0,None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.module().validate({'HALOGEN_NGRAM_GATHER_THREADS':value})

    def test_lookup_io_threads_do_not_add_a_default_override(self):
        self.assertNotIn('HALOGEN_NGRAM_GATHER_THREADS',self.module().environment({}))

    def test_gram_requires_explicit_standalone_norm_selection(self):
        for controls in ({'HALOGEN_DN_FUSED_GRAM':1},
                         {'HALOGEN_DN_FUSED_GRAM':1,'HALOGEN_DN_FUSED':1,
                          'HALOGEN_DN_SCAN':0,'HALOGEN_DN_FUSED_PAIR':0,
                          'HALOGEN_DN_NORM_FOLD':0}):
            with self.subTest(controls=controls),self.assertRaisesRegex(
                    ValueError,'explicit HALOGEN_DN_FUSED_NORM=0'):
                self.module().validate(controls)

    def test_gram_refuses_the_norm_omitting_native_combination(self):
        with self.assertRaisesRegex(ValueError,'explicit HALOGEN_DN_FUSED_NORM=0'):
            self.module().validate({'HALOGEN_DN_FUSED_GRAM':1,
                                    'HALOGEN_DN_FUSED_NORM':1})

    def test_complete_guarded_gram_combo_parses_and_reaches_environment(self):
        controls={'HALOGEN_DN_FUSED_GRAM':1,'HALOGEN_DN_FUSED_NORM':0,
                  'HALOGEN_DN_FUSED_PAIR':0,'HALOGEN_DN_NORM_FOLD':0,
                  'HALOGEN_DN_FUSED':1,'HALOGEN_DN_SCAN':0}
        before=copy.deepcopy(controls)
        try:
            parsed=self.module().parse(json.dumps(controls))
        except ValueError as error:
            self.fail('Guarded known native Gram combination was refused: '+str(error))
        self.assertEqual(parsed,before)
        self.assertEqual(self.module().environment(parsed),
                         {'HALOGEN_DN_FUSED_GRAM':'1','HALOGEN_DN_FUSED_NORM':'0',
                          'HALOGEN_DN_FUSED_PAIR':'0','HALOGEN_DN_NORM_FOLD':'0',
                          'HALOGEN_DN_FUSED':'1','HALOGEN_DN_SCAN':'0'})
        self.assertEqual(controls,before)

    def test_gram_uses_pinned_branch_defaults_without_adding_overrides(self):
        controls={'HALOGEN_DN_FUSED_GRAM':1,'HALOGEN_DN_FUSED_NORM':0}
        try:
            validated=self.module().validate(controls)
        except ValueError as error:
            self.fail('Pinned default branches should admit guarded Gram: '+str(error))
        self.assertEqual(validated,controls)
        self.assertEqual(self.module().environment(validated),
                         {'HALOGEN_DN_FUSED_GRAM':'1','HALOGEN_DN_FUSED_NORM':'0'})

    def test_gram_refuses_incompatible_resolved_branches(self):
        for key,value,required in (('HALOGEN_DN_FUSED',0,1),
                                   ('HALOGEN_DN_SCAN',1,0),
                                   ('HALOGEN_DN_FUSED_PAIR',1,0),
                                   ('HALOGEN_DN_NORM_FOLD',1,0)):
            controls={'HALOGEN_DN_FUSED_GRAM':1,'HALOGEN_DN_FUSED_NORM':0,
                      key:value}
            with self.subTest(key=key),self.assertRaisesRegex(
                    ValueError,'resolved '+key+'='+str(required)):
                self.module().validate(controls)

    def test_gram_omission_and_explicit_off_preserve_existing_stock_controls(self):
        self.assertEqual(self.module().environment({}),{})
        stock={'HALOGEN_DN_SCAN':1,'HALOGEN_DN_FUSED':0,
               'HALOGEN_DN_FUSED_NORM':1,'HALOGEN_DN_FUSED_PAIR':1,
               'HALOGEN_DN_NORM_FOLD':1}
        self.assertEqual(self.module().validate(stock),stock)
        self.assertEqual(self.module().environment(stock),
                         {'HALOGEN_DN_SCAN':'1','HALOGEN_DN_FUSED':'0',
                          'HALOGEN_DN_FUSED_NORM':'1','HALOGEN_DN_FUSED_PAIR':'1',
                          'HALOGEN_DN_NORM_FOLD':'1'})
        explicit_off={**stock,'HALOGEN_DN_FUSED_GRAM':0}
        try:
            validated=self.module().validate(explicit_off)
        except ValueError as error:
            self.fail('Explicit Gram off must preserve existing branches: '+str(error))
        self.assertEqual(validated,explicit_off)
        self.assertEqual(self.module().environment(validated),
                         {'HALOGEN_DN_SCAN':'1','HALOGEN_DN_FUSED':'0',
                          'HALOGEN_DN_FUSED_NORM':'1','HALOGEN_DN_FUSED_PAIR':'1',
                          'HALOGEN_DN_NORM_FOLD':'1','HALOGEN_DN_FUSED_GRAM':'0'})

    @unittest.skipUnless(shutil.which('pwsh'),'PowerShell 7 launcher fixture')
    def test_launcher_preserves_json_as_one_argument(self):
        controls='{"HALOGEN_DN_SCAN":0,"HALOGEN_ATTN_FA":64,"HALOGEN_NGRAM_GATHER_THREADS":32}'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'scripts').mkdir()
            shutil.copyfile(ROOT/'Start.ps1',root/'Start.ps1')
            (root/'scripts/service.py').write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n',encoding='utf-8')
            result=subprocess.run([shutil.which('pwsh'),'-NoProfile','-File',str(root/'Start.ps1'),
                                   '-Checkpoint','v2','-KernelControlsJson',controls,'-PrintOnly'],
                                  capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            args=json.loads(result.stdout)
            self.assertEqual(args[args.index('--kernel-controls-json')+1],controls)
            self.assertIn('--print-only',args)
