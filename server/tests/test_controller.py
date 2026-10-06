import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import atomic,read,lease,validate_engine,Engine,halogen_launch_command

class ControllerPolicyTests(unittest.TestCase):
    def test_direct_service_preserves_managed_controls_without_powershell7(self):
        package=Path(__file__).resolve().parents[2]/'backends/halogen-wsl2-0.16.2'
        config={'kind':'halogen','launcher':'python','python_executable':sys.executable,
                'powershell':'unused-by-command','checkpoint':'v2','context':262144,
                'prompt_cache':'Off','draft_tokens':2,'prefill_chunk':8192,
                'max_prefill_tokens':8192,'speculation_policy':{'HALOGEN_PLD':'3,3'}}
        command=halogen_launch_command(config,package)
        self.assertEqual(command[:4],[sys.executable,'-u','-B',str(package/'scripts/service.py')])
        self.assertNotIn('unused-by-command',command)
        self.assertEqual(command[command.index('--max-prefill-tokens')+1],'8192')
        self.assertEqual(command[command.index('--draft-tokens')+1],'2')
        self.assertEqual(json.loads(command[command.index('--speculation-policy-json')+1]),
                         {'HALOGEN_PLD':'3,3'})
        # The backend parser still enforces all serving controls on the direct path.
        sys.path.insert(0,str(package/'scripts'))
        try:
            from service import options
            parsed=options(command[4:])
            self.assertEqual((parsed.context_size,parsed.prefill_chunk,parsed.max_prefill_tokens),
                             (262144,8192,8192))
        finally: sys.path.pop(0)

    def test_direct_service_rejects_another_interpreter_or_backend(self):
        package=Path(__file__).resolve().parents[2]/'backends/halogen-wsl2-0.16.2'
        config={'launcher':'python','python_executable':'relative.exe',
                'checkpoint':'v2','context':262144}
        with self.assertRaises(ValueError): halogen_launch_command(config,package)
        config['python_executable']=sys.executable
        with self.assertRaises(ValueError): halogen_launch_command(config,package.parent/'fixture')

    def test_unqualified_native_backend_is_refused(self):
        with self.assertRaises(ValueError):
            validate_engine({'kind':'native','qualified':False},Path.cwd())

    def test_halogen_directory_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                validate_engine({'kind':'halogen','directory':'../../other',
                                 'checkpoint':'v2','context':262144},Path(td))

    def test_wrong_native_digest_is_refused(self):
        with self.assertRaises(ValueError):
            validate_engine({'kind':'native','qualified':True,'command':[sys.executable],
                             'executable_sha256':'0'*64},Path.cwd())

    def test_atomic_json_and_os_lock(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            atomic(p/'state.json',{'run':'unchanged'})
            self.assertEqual(read(p/'state.json'),{'run':'unchanged'})
            with lease(p/'lock'):
                if os.name=='nt':
                    with self.assertRaises(OSError):
                        with lease(p/'lock'): pass
            with lease(p/'lock'): pass

    def test_no_adoption_of_unrelated_halogen_controller(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); package=root/'backends/fixture'
            (package/'.local').mkdir(parents=True)
            (package/'Start.ps1').write_text('# fixture')
            engine=Engine({'kind':'halogen','directory':'backends/fixture',
                          'checkpoint':'v2','context':262144},Mock(),root,root)
            engine.previous_run='previous'; engine.process=Mock()
            engine.process.contains.return_value=False
            state={'phase':'ready','run_id':'unrelated','context':262144,'checkpoint':'v2','controller_pid':123}
            atomic(package/'.local/current-service.json',state)
            self.assertIsNone(engine.state())
            engine.process.contains.return_value=True
            self.assertEqual(engine.state()['run_id'],'unrelated')

if __name__=='__main__': unittest.main()
