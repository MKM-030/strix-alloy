"""Existing desktop startup must require the same V2 model with Vision."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

admission = load('desktop_vision_admission', 'model_admission.py')
status_file = ROOT / 'stack_status.py'
if not status_file.exists():
    status_file = ROOT.parent / 'native-speech-validation/stack_status.py'
status = load('desktop_vision_status', status_file)
coordinator = load('desktop_vision_coordinator', 'start_services.py')

class ExistingModelVisionStartTests(unittest.TestCase):
    def test_desktop_policy_covers_full_tower_and_retains_runtime_reserve(self):
        policy = admission.load_policy(ROOT / 'model-start-policy.json')
        self.assertEqual(policy['start_physical_gib'], 36)
        self.assertEqual(policy['start_commit_headroom_gib'], 132)
        self.assertEqual(policy['runtime_reserve_gib'], 18)
        with self.assertRaises(ValueError):
            admission.check_start_frame({'available_bytes': 36 * admission.GIB,
                                         'commit_headroom_bytes': int(131.5 * admission.GIB)}, policy)

    def test_local_health_exposes_only_an_actual_vision_boolean(self):
        for field in (True, False, None, 1, 'true'):
            with self.subTest(field=field):
                body = {'status': 'ok', 'model': 'halogen-qwen3.8-flash-next',
                        'version': {'api': status.DEPLOYMENT['expected']['version.api'],
                                    'engine': status.DEPLOYMENT['expected']['version.engine'], 'match': True},
                        'vision': {'enabled': field}}
                response = mock.MagicMock()
                response.__enter__.return_value = SimpleNamespace(status=200, read=lambda count: json.dumps(body).encode())
                opener = SimpleNamespace(open=lambda *args, **kwargs: response)
                with mock.patch.object(status.urllib.request, 'build_opener', return_value=opener):
                    result = status.health(8731, token='fixture-local-key')
                self.assertIs(result.get('vision_enabled'), field is True)

    def test_desktop_start_waits_until_existing_model_vision_is_ready(self):
        calls = []
        def health(port, **kwargs):
            calls.append(port)
            if port == 8840:
                return {'status': 'ok', 'http_status': 200}
            return {'http_status': 200, 'expected_model': True, 'version_matches': True,
                    'profile_matches': True, 'context': status.DEPLOYMENT['context'],
                    'slots': status.DEPLOYMENT['slots'], 'vision_enabled': len(calls) > 2}
        fixture = SimpleNamespace(health=health, MODEL=SimpleNamespace(read_text=lambda **kwargs: 'fixture-local-key'),
                                  PROFILE='same-existing-profile', credential=lambda path: 'fixture-local-key',
                                  DEPLOYMENT=status.DEPLOYMENT)
        with mock.patch.object(coordinator, 'powershell') as launch, mock.patch.object(coordinator.time, 'sleep'):
            coordinator.model_start(fixture)
        self.assertEqual(calls, [8731, 8840, 8731, 8840])
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(launch.call_args.args[1:], ('-Action', 'Start'))

if __name__ == '__main__':
    unittest.main()
