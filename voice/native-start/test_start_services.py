import importlib.util
from pathlib import Path
import sys
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

if importlib.util.find_spec('psutil') is None:
    # All OS access in these contract tests is mocked; target Windows uses psutil.
    sys.modules['psutil'] = MagicMock()

spec = importlib.util.spec_from_file_location('startup', Path(__file__).with_name('start_services.py'))
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def test_refuses_foreign_listener_before_health(self):
        with patch.object(startup, 'listeners', return_value=[SimpleNamespace(pid=22, laddr=SimpleNamespace(ip='127.0.0.1'))]), patch.object(startup, 'process_args', return_value=['python.exe','foreign.py']):
            with self.assertRaises(RuntimeError):
                startup.owned_listener(8850, ['python.exe','expected.py'])

    def test_exact_argv_on_public_bind_is_rejected(self):
        with patch.object(startup, 'listeners', return_value=[SimpleNamespace(pid=22, laddr=SimpleNamespace(ip='0.0.0.0'))]), patch.object(startup, 'process_args', return_value=['python.exe','expected.py']):
            with self.assertRaises(RuntimeError):
                startup.owned_listener(8850, ['python.exe','expected.py'])

    def test_owned_loopback_listener_is_reused(self):
        with patch.object(startup, 'listeners', return_value=[SimpleNamespace(pid=22, laddr=SimpleNamespace(ip='127.0.0.1'))]), patch.object(startup, 'process_args', return_value=['python.exe','expected.py']), patch.object(startup.psutil, 'Process', return_value=SimpleNamespace(exe=lambda:'python.exe')):
            self.assertEqual(startup.owned_listener(8850, ['python.exe','expected.py']),22)

    def test_missing_port_is_not_adopted(self):
        with patch.object(startup, 'listeners', return_value=[]):
            self.assertIsNone(startup.owned_listener(8850, ['python.exe','expected.py']))

    def test_prior_boot_gateway_receipt_preserved_without_touching_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            state = {'port':8841, 'gateway':str(startup.ROOT/'server/gateway.py'),
                'config':str(startup.ROOT/'server/.local/scc-gateway.json'),
                'python':r'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe',
                'started_ticks':str((62135596800+100)*10000000), 'pid':22}
            path.write_text(json.dumps(state))
            with patch.object(startup,'listeners',return_value=[]), patch.object(startup.psutil,'boot_time',return_value=200), patch.object(startup.psutil,'Process') as process:
                startup.archive_gateway_state(path)
                process.assert_not_called()
            self.assertFalse(path.exists())
            backups = list(Path(folder).glob('state.prior-boot-*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(json.loads(backups[0].read_text()),state)

    def test_live_gateway_listener_prevents_receipt_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            path.write_text('preserve this')
            with patch.object(startup,'listeners',return_value=[object()]):
                startup.archive_gateway_state(path)
            self.assertEqual(path.read_text(),'preserve this')

if __name__ == '__main__':
    unittest.main()
