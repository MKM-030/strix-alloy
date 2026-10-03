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

    @unittest.skipUnless(shutil.which('pwsh'),'PowerShell 7 launcher fixture')
    def test_launcher_preserves_json_as_one_argument(self):
        controls='{"HALOGEN_DN_SCAN":0,"HALOGEN_ATTN_FA":64}'
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
