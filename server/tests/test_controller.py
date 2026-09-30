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
from controller import atomic,read,lease,validate_engine,Engine

class ControllerPolicyTests(unittest.TestCase):
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
