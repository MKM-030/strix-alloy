"""Offline gateway recovery identity with existing executable/health fences."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import start_current_voice as launcher
import start_services as services

class GatewayRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); (self.root/'server/.local').mkdir(parents=True)
        (self.root/'server/gateway.py').write_text('# fixture')
        self.config=self.root/'server/.local/scc-gateway.json'; self.config.write_text('{}')
        self.python=self.root/'venv/Scripts/python.exe'; self.python.parent.mkdir(parents=True); self.python.touch()
        self.exe=str(self.python); self.cwd=self.root
        self.socket=SimpleNamespace(pid=123,laddr=SimpleNamespace(ip='127.0.0.1'))
        self.sockets=[self.socket]
        self.addCleanup(patch.stopall)
        patch.object(launcher,'ACTIVE',self.root).start()
        patch.object(launcher,'GATEWAY_CONFIG',self.config).start()
        patch.object(launcher,'PYTHON',self.python).start()
        patch.object(launcher,'services',services).start()
        patch.object(services,'PYTHON',self.python).start()
        patch.object(services,'python_base',lambda exe:str(self.root/'base/python.exe')).start()
        patch.object(services,'listeners',lambda port:self.sockets).start()
        patch.object(services,'process_args',lambda pid:list(self.actual)).start()
        patch.object(services.psutil,'Process',lambda pid:SimpleNamespace(cwd=lambda:str(self.cwd),exe=lambda:self.exe)).start()
        self.actual=self.relative()

    def relative(self):
        return [str(self.python),'-u','-B',str(Path('server/gateway.py')),'--config',
                str(Path('server/.local/scc-gateway.json')),'--port','8841']

    def test_canonical_and_bounded_relative_recovery_keep_cold_args(self):
        canonical=launcher.gateway_args()
        for actual in (canonical,self.relative()):
            with self.subTest(actual=actual):
                self.actual=list(actual)
                self.assertEqual(launcher.gateway_listener(),123)
                self.assertEqual(launcher.gateway_args(),canonical)
        self.sockets=[]; self.assertIsNone(launcher.gateway_listener())

    def test_foreign_cwd_paths_flags_and_executable_rejected(self):
        foreign=self.root/'foreign'; foreign.mkdir()
        for path in ('gateway.py','config.json'): (foreign/path).write_text('# foreign')
        for case in ('cwd','script','config','flag','extra','missing_B','argv_exe','actual_exe','nonloopback'):
            with self.subTest(case=case):
                self.actual=self.relative(); self.cwd=self.root; self.exe=str(self.python); self.socket.laddr.ip='127.0.0.1'
                if case=='cwd': self.cwd=foreign
                elif case=='script': self.actual[3]=str(foreign/'gateway.py')
                elif case=='config': self.actual[5]=str(foreign/'config.json')
                elif case=='flag': self.actual[2]='-I'
                elif case=='extra': self.actual+=['--log',str(self.root/'server/.local/scc-gateway.log')]
                elif case=='missing_B': self.actual.pop(2)
                elif case=='argv_exe': self.actual[0]=str(foreign/'python.exe')
                elif case=='actual_exe': self.exe=str(foreign/'python.exe')
                elif case=='nonloopback': self.socket.laddr.ip='0.0.0.0'
                with self.assertRaises(RuntimeError): launcher.gateway_listener()

    def test_recovery_retains_authenticated_health_and_model_checks(self):
        profile=dict(backend=dict(identifier='selected',context=32768))
        config=dict(controller_consumer=True,backend=dict(upstream='http://127.0.0.1:8840'))
        good=dict(http_status=200,status='ok',draining=False,backend='selected',context=32768)
        with patch.object(launcher,'read_json',return_value=config), patch.object(launcher,'credential',return_value='secret'):
            with patch.object(launcher,'health',return_value=good) as health:
                self.assertTrue(launcher.gateway_ready(profile))
                health.assert_called_once_with(8841,token='secret')
            for field,value in (('backend','foreign'),('context',8192),('draining',True),('status','error'),('http_status',401)):
                with self.subTest(field=field),patch.object(launcher,'health',return_value={**good,field:value}):
                    with self.assertRaises(RuntimeError): launcher.gateway_ready(profile)
            with patch.object(launcher,'credential',side_effect=['gateway-secret','different-controller-secret']):
                with self.assertRaises(RuntimeError): launcher.gateway_ready(profile)

if __name__=='__main__': unittest.main()
