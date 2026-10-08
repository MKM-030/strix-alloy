"""Profile defaults reach the owned container command without starting it."""
import contextlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'backends/halogen-wsl2-0.17.2'


@contextlib.contextmanager
def backend_service():
    names = ('service', 'portable', 'kernel_controls', 'speculation_policy',
             'startup_monitor', 'runner', 'startup_guard', 'lease_supervisor',
             'bridge_adapter', 'api_defaults')
    saved = {name: sys.modules.pop(name) for name in names if name in sys.modules}
    sys.path.insert(0, str(PACKAGE / 'scripts'))
    try:
        yield importlib.import_module('service')
    finally:
        sys.path.pop(0)
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


class HalogenApiDefaultsTests(unittest.TestCase):
    def engine(self, defaults, launcher='python', version='0.17.2'):
        return dict(kind='halogen', directory='backends/halogen-wsl2-' + version,
                    checkpoint='v2', context=262144, prompt_cache='Off',
                    launcher=launcher, python_executable=sys.executable,
                    powershell='powershell.exe', api_defaults=defaults)

    def test_typed_thinking_defaults_reach_container_on_both_launcher_routes(self):
        for thinking in (True, False):
            defaults = dict(enable_thinking=thinking, reasoning_effort='medium',
                            max_thinking_tokens=2048)
            expected = {'HALOGEN_ENABLE_THINKING': '1' if thinking else '0',
                        'HALOGEN_REASONING_EFFORT': 'medium',
                        'HALOGEN_MAX_THINKING_TOKENS': '2048'}
            for launcher, flag in (('python', '--api-defaults-json'),
                                   ('powershell', '-ApiDefaultsJson')):
                with self.subTest(thinking=thinking, launcher=launcher):
                    engine = self.engine(defaults, launcher)
                    directory = controller.validate_engine(engine, REPO)
                    command = controller.halogen_launch_command(engine, directory)
                    self.assertIn(flag, command, 'Thinking defaults were dropped by the launcher')
                    text = command[command.index(flag) + 1]
                    self.assertEqual(json.loads(text), defaults)
                    with backend_service() as service, tempfile.TemporaryDirectory() as temporary:
                        options = service.options(['--api-defaults-json', text])
                        attempt = Path(temporary)
                        (attempt / 'entrypoint-service.sh').write_text('# fixture\n')
                        manifest = service.build_manifest(options, attempt, '1' * 32)
                        self.assertEqual(manifest['api_defaults'], defaults)
                        self.assertEqual({key: manifest['environment'][key] for key in expected}, expected)
                        docker = service.command(manifest)
                        for key, value in expected.items():
                            self.assertIn(key + '=' + value, docker)

    def test_invalid_or_unqualified_defaults_are_rejected_before_launch(self):
        bad = ({'enable_thinking': 1}, {'max_thinking_tokens': True},
               {'max_thinking_tokens': 0}, {'reasoning_effort': 'none'},
               {'HALOGEN_ENABLE_THINKING': '1'})
        for defaults in bad:
            with self.subTest(defaults=defaults), self.assertRaises(ValueError):
                controller.validate_engine(self.engine(defaults), REPO)
        with self.assertRaises(ValueError):
            controller.validate_engine(self.engine({'enable_thinking': True}, version='0.16.2'), REPO)

    def test_omission_does_not_forward_parent_environment_defaults(self):
        with backend_service() as service, patch.dict('os.environ', {'HALOGEN_ENABLE_THINKING': '1'}):
            env = service.environment(262144)
            self.assertNotIn('HALOGEN_ENABLE_THINKING', env)


if __name__ == '__main__':
    unittest.main()
