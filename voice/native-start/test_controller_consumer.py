"""Offline controller identity checks using the real listener ownership validator."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch
import controller_consumer as consumer
import start_services as services

class ControllerConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.server = self.root / 'server'; self.server.mkdir()
        (self.server / 'controller.py').write_text('# fixture')
        self.python = self.server / 'venv/Scripts/python.exe'
        self.python.parent.mkdir(parents=True); self.python.touch()
        self.token = self.server / 'token'; self.token.write_text('x' * 32)
        self.profile = self.server / '.local/selected.json'; self.profile.parent.mkdir()
        self.profile.write_text(json.dumps(dict(token_file=str(self.token),backend=dict(
            identifier='selected',checkpoint='v2',context=32768,routes=['/v1/chat/completions']))))
        self.sha = hashlib.sha256(self.profile.read_bytes()).hexdigest()
        self.current = self.server / '.local/current.json'
        self.current.write_text(json.dumps(dict(pid=123,port=8840,profile_sha256=self.sha,
            heartbeat=time.time(),phase='ready',backend='selected',checkpoint='v2',context=32768)))
        self.selection = self.server / '.local/selection.json'
        self.cwd = self.root
        self.exe = str(self.python)
        self.actual = [str(self.python), *consumer.prefix_args(self.server,self.profile)]
        self.sockets = [SimpleNamespace(pid=123,laddr=SimpleNamespace(ip='127.0.0.1'))]
        self.addCleanup(patch.stopall)
        patch.object(services,'PYTHON',self.python).start()
        patch.object(services,'python_base',lambda exe: str(self.root/'base/python.exe')).start()
        patch.object(services,'listeners',lambda port: self.sockets).start()
        patch.object(services,'process_args',lambda pid: list(self.actual)).start()
        patch.object(services.psutil,'Process',lambda pid: SimpleNamespace(cwd=lambda:str(self.cwd),exe=lambda:self.exe)).start()

    def load(self):
        return consumer.load_selected(services,self.server,self.python,self.current,self.selection)

    def test_legitimate_absolute_and_relative_argv_retain_runtime_and_cold_identity(self):
        for relative in (False,True):
            with self.subTest(relative=relative):
                if relative:
                    self.actual[3] = str(Path('server/controller.py'))
                    self.actual[6] = str(Path('server/.local/selected.json'))
                selected = self.load()
                self.assertEqual(selected['runtime_args'],self.actual)
                self.assertEqual(selected['args'],[str(self.python),*consumer.prefix_args(self.server,self.profile)])
                self.assertEqual(selected['profile_path'],self.profile)
                with patch.object(consumer,'request',side_effect=[dict(status='ok',draining=False,
                    backend='selected',checkpoint='v2',context=32768),dict(data=[dict(id='selected')])]):
                    self.assertTrue(consumer.ready(services,selected,self.current))

    def test_foreign_cwd_script_profile_options_and_executable_are_rejected(self):
        foreign = self.root/'foreign'; foreign.mkdir()
        (foreign/'controller.py').write_text('# foreign')
        (foreign/'profile.json').write_bytes(self.profile.read_bytes())
        baseline = list(self.actual)
        cases = ('cwd','script','outside_profile','changed_profile','argv_exe','actual_exe','extra_option','wrong_pid','nonloopback')
        for case in cases:
            with self.subTest(case=case):
                self.actual=list(baseline); self.cwd=self.root; self.exe=str(self.python)
                self.sockets[0].laddr.ip='127.0.0.1'
                original=self.profile.read_bytes(); state=self.current.read_bytes()
                if case=='cwd': self.cwd=foreign
                elif case=='script': self.actual[3]=str(foreign/'controller.py')
                elif case=='outside_profile': self.actual[6]=str(foreign/'profile.json')
                elif case=='changed_profile': self.profile.write_bytes(original+b' ')
                elif case=='argv_exe': self.actual[0]=str(foreign/'python.exe')
                elif case=='actual_exe': self.exe=str(foreign/'python.exe')
                elif case=='extra_option': self.actual.append('--other')
                elif case=='wrong_pid':
                    value=json.loads(state); value['pid']=124; self.current.write_text(json.dumps(value))
                elif case=='nonloopback': self.sockets[0].laddr.ip='0.0.0.0'
                try:
                    with self.assertRaises(RuntimeError): self.load()
                finally:
                    self.profile.write_bytes(original); self.current.write_bytes(state)

    def test_ready_rejects_changed_runtime_arguments_and_executable(self):
        selected=self.load()
        self.actual[3]=str(Path('server/controller.py'))
        with self.assertRaises(RuntimeError): consumer.ready(services,selected,self.current)
        self.actual=list(selected['runtime_args']); self.exe=str(self.root/'foreign/python.exe')
        with self.assertRaises(RuntimeError): consumer.ready(services,selected,self.current)

    def test_cold_selection_retains_canonical_launch_arguments(self):
        self.sockets=[]
        self.selection.write_text(json.dumps(dict(profile=str(self.profile),profile_sha256=self.sha)))
        selected=self.load()
        self.assertIsNone(selected['runtime_args'])
        self.assertEqual(selected['args'],[str(self.python),*consumer.prefix_args(self.server,self.profile)])
        self.assertFalse(consumer.ready(services,selected,self.current))

if __name__=='__main__': unittest.main()
