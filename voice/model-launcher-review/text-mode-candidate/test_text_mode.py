"""Focused text-mode regression tests using only selected production function ASTs.

No complete service/controller module is imported. WSL, checkpoint reads,
container operations and model execution are unavailable in these harnesses.
Use --service-source/--controller-source/--profile-source to test pre-change
snapshots or an explicitly selected candidate. Temporary backend fixtures
contain only parser declarations and a fake Python executable.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SERVICE = HERE / 'service.py'
CONTROLLER = HERE / 'controller.py'
PROFILE = HERE / 'serving0181-full262-exact-text-voice-candidate-20261013.json'
ORIGINAL_PROFILE = HERE / 'profile-original.json'
ORIGINAL_SHA = 'f62b654bd0cfd0bcd00b4ced7416b64584ca530e6be8120e5d61dc45b931c323'
GIB = 2**30


def extracted(path, names, namespace):
    """Execute function declarations only; never execute module top-level code."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    definitions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    missing = set(names) - definitions.keys()
    if missing:
        raise AssertionError('Production text-mode interface missing: ' + ', '.join(sorted(missing)))
    nodes = [definitions[name] for name in names]
    if any(node.decorator_list for node in nodes):
        raise AssertionError('Refusing executable function decorators')
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    namespace = dict(namespace)
    exec(compile(module, str(path) + ':selected-functions-only', 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


def service_functions(*names, seed_environment=None, portable=None):
    r = types.SimpleNamespace(
        GIB=GIB, MACHINE={},
        manifest_for=lambda role: {'role': role},
        environment=lambda manifest: dict(seed_environment or {}),
    )
    controls = types.SimpleNamespace(parse=lambda value: json.loads(value),
                                    validate=lambda value: value,
                                    environment=lambda value: {})
    namespace = dict(argparse=argparse, Path=Path, math=__import__('math'),
                     DEFAULT_CONTEXT=262144, r=r, kc=controls, sp=controls,
                     ad=controls, portable=portable,
                     LOCAL=Path('/not-an-accessible-backend/.local'))
    wanted = list(dict.fromkeys(['validate_disable_vision', 'validate_prefill_limits', *names]))
    return extracted(SERVICE, wanted, namespace)


class ServiceTextMode(unittest.TestCase):
    def test_boolean_rejects_non_booleans(self):
        module = service_functions()
        for value in (None, 0, 1, -1, '', 'false', 'true', [], {}, 0.0, 1.0):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                module.validate_disable_vision(value)
        for value in (False, True):
            module.validate_disable_vision(value)

    def test_true_is_v2_only(self):
        module = service_functions()
        for checkpoint in ('w4b', 'other', None):
            with self.subTest(checkpoint=checkpoint), self.assertRaises(ValueError):
                module.validate_disable_vision(True, checkpoint)
        module.validate_disable_vision(False, 'w4b')

    def test_cli_defaults_to_vision_and_opt_in_disables_only_v2(self):
        module = service_functions('validate_options', 'options')
        self.assertIs(module.options([]).disable_vision, False)
        options = module.options(['--disable-vision', '--checkpoint', 'v2',
                                  '--prompt-cache', 'Exact', '--context-size', '262144'])
        self.assertIs(options.disable_vision, True)
        self.assertEqual((options.prompt_cache, options.context_size), ('Exact', 262144))
        with self.assertRaises(ValueError):
            module.options(['--disable-vision', '--checkpoint', 'w4b'])

    def test_programmatic_options_reject_invalid_flag(self):
        module = service_functions('validate_options', 'options')
        options = module.options([])
        options.disable_vision = 'false'
        with self.assertRaises(ValueError):
            module.validate_options(options)

    def test_default_environment_retains_vision(self):
        module = service_functions('environment')
        environment = module.environment(262144, 'v2', 'Exact')
        self.assertEqual(environment['HALOGEN_VISION_TOWER'], '/models/qwen38-flash-next-vision.hgn')

    def test_text_environment_removes_even_seeded_vision_and_preserves_model_controls(self):
        module = service_functions('environment', seed_environment={
            'HALOGEN_VISION_TOWER': '/unexpected-seeded-tower', 'KEEP_ME': 'unchanged'})
        environment = module.environment(262144, 'v2', 'Exact', disable_vision=True)
        self.assertNotIn('HALOGEN_VISION_TOWER', environment)
        self.assertEqual(environment['KEEP_ME'], 'unchanged')
        expected = {'HALOGEN_CTX': '262144', 'HALOGEN_KV_POOL_POSITIONS': '262144',
                    'HALOGEN_KV_SLOTS': '1', 'HALOGEN_PROMPT_CACHE': '1',
                    'HALOGEN_HOST_RESERVE_GIB': '18', 'HF_HUB_OFFLINE': '1',
                    'HALOGEN_CHECKPOINT': '/models/qwen38-flash-next-v2.hgn',
                    'HALOGEN_PREFLIGHT_PROFILE': 'flash0181-v2-device64-chunk64-v1',
                    'HALOGEN_HYBRID_COPY_BYTES': '68719476736'}
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(environment[key], value)

    def test_text_and_default_environments_differ_only_in_vision_tower(self):
        module = service_functions('environment')
        default = module.environment(262144, 'v2', 'Exact', draft_tokens=2,
                                     prefill_chunk=4096, max_prefill_tokens=4096)
        text = module.environment(262144, 'v2', 'Exact', draft_tokens=2,
                                  prefill_chunk=4096, max_prefill_tokens=4096,
                                  disable_vision=True)
        default.pop('HALOGEN_VISION_TOWER')
        self.assertEqual(default, text)

    def test_environment_rejects_invalid_flag_and_unsupported_checkpoint(self):
        module = service_functions('environment')
        for flag, checkpoint in [('false', 'v2'), (1, 'v2'), (True, 'w4b')]:
            with self.subTest(flag=flag, checkpoint=checkpoint), self.assertRaises(ValueError):
                module.environment(262144, checkpoint, disable_vision=flag)

    def checkpoint_harness(self, tower_sha='d62e0ae553fe88afd3833733d4a4c669f34d20fd8dfce4b9610525bed2134b10'):
        calls = []
        machine = {'models': '/models', 'distro': 'reviewed-distro', 'user': 'reviewed-user'}
        integrity = types.ModuleType('checkpoint_integrity')
        integrity.verify = lambda machine, local: calls.append(('checkpoint', machine, local))
        integrity.verify_ngram = lambda machine, local: calls.append(('ngram', machine, local))
        def wsl(*args):
            calls.append(('tower', args))
            return '897916416' if 'stat' in args else tower_sha + '  /models/qwen38-flash-next-vision.hgn'
        portable = types.SimpleNamespace(
            wsl=wsl, RELEASE={'v2_bridge_sha256': 'unchanged-bridge-pin'},
            check_hash=lambda path, pin: calls.append(('bridge', path, pin)))
        return service_functions('verify_checkpoint', portable=portable), integrity, calls, machine

    def test_text_checkpoint_keeps_checkpoint_ngram_and_bridge_verification(self):
        module, integrity, calls, machine = self.checkpoint_harness()
        with patch.dict(sys.modules, {'checkpoint_integrity': integrity}):
            module.verify_checkpoint(machine, 'v2', disable_vision=True)
        self.assertEqual([call[0] for call in calls], ['checkpoint', 'ngram', 'bridge'])
        self.assertEqual(calls[-1][1].name, 'libhalogen0181-v2-preflight.so')
        self.assertEqual(calls[-1][2], 'unchanged-bridge-pin')

    def test_default_checkpoint_checks_tower_size_and_pinned_hash(self):
        module, integrity, calls, machine = self.checkpoint_harness()
        with patch.dict(sys.modules, {'checkpoint_integrity': integrity}):
            module.verify_checkpoint(machine, 'v2')
        self.assertEqual([call[0] for call in calls], ['checkpoint', 'ngram', 'tower', 'tower', 'bridge'])
        module, integrity, calls, machine = self.checkpoint_harness(tower_sha='wrong-tower-hash')
        with patch.dict(sys.modules, {'checkpoint_integrity': integrity}), self.assertRaises(ValueError):
            module.verify_checkpoint(machine, 'v2')
        self.assertNotIn('bridge', [call[0] for call in calls])

    def healthy(self, vision='absent'):
        health = {'status': 'ok', 'version': {'api': '0.18.1', 'engine': '0.18.1', 'match': True},
                  'context': 262144, 'slot_ctx': 262144, 'kv_pool_positions': 262144, 'slots': 1}
        if vision != 'absent':
            health['vision'] = {'enabled': vision}
        return health

    def test_default_health_requires_vision_true(self):
        module = service_functions('validate_health')
        module.validate_health(self.healthy(True), 262144)
        for health in (self.healthy(), self.healthy(False)):
            with self.assertRaises(ValueError):
                module.validate_health(health, 262144)

    def test_text_health_accepts_absent_or_false_and_rejects_true(self):
        module = service_functions('validate_health')
        for health in (self.healthy(), self.healthy(False)):
            module.validate_health(health, 262144, disable_vision=True)
        with self.assertRaises(ValueError):
            module.validate_health(self.healthy(True), 262144, disable_vision=True)

    def test_text_health_keeps_version_context_and_single_slot_identity(self):
        module = service_functions('validate_health')
        for key, value in [('context', 129024), ('slot_ctx', 129024), ('kv_pool_positions', 129024),
                           ('slots', 2), ('version', {'api': '0.18.0', 'engine': '0.18.0', 'match': True})]:
            health = self.healthy(False)
            health[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.validate_health(health, 262144, disable_vision=True)

    def test_text_helpers_reject_invalid_boolean_at_their_entry_points(self):
        module = service_functions('validate_health')
        with self.assertRaises(ValueError):
            module.validate_health(self.healthy(False), 262144, disable_vision='false')
        module, integrity, calls, machine = self.checkpoint_harness()
        with patch.dict(sys.modules, {'checkpoint_integrity': integrity}), self.assertRaises(ValueError):
            module.verify_checkpoint(machine, 'v2', disable_vision=1)
        self.assertEqual(calls, [])

    def test_runtime_physical_commit_reserve_remains_18_and_samples_remain_fresh(self):
        module = extracted(SERVICE, ['check_runtime_frame'], {'r': types.SimpleNamespace(GIB=GIB)})
        module.check_runtime_frame({'available_bytes': 18*GIB, 'commit_headroom_bytes': 18*GIB}, 2)
        for frame, age in [({'available_bytes': 18*GIB-1, 'commit_headroom_bytes': 18*GIB}, 0),
                           ({'available_bytes': 18*GIB, 'commit_headroom_bytes': 18*GIB-1}, 0),
                           ({'available_bytes': 18*GIB, 'commit_headroom_bytes': 18*GIB}, 2.001)]:
            with self.assertRaises(ValueError):
                module.check_runtime_frame(frame, age)


class ControllerTextMode(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.directory = self.repo / 'backends/halogen-wsl2-0.18.1'
        (self.directory / 'scripts').mkdir(parents=True)
        self.service = self.directory / 'scripts/service.py'
        self.service.write_text("def options():\n    p.add_argument('--disable-vision',action='store_true')\n")
        (self.directory / 'Start.ps1').write_text('# isolated fixture; never executed\n')
        self.python = self.repo / 'python.exe'
        self.python.touch()
        self.engine = dict(kind='halogen', directory='backends/halogen-wsl2-0.18.1',
                           checkpoint='v2', context=262144, prompt_cache='Exact',
                           launcher='python', python_executable=str(self.python),
                           powershell='reviewed-powershell', draft_tokens=2,
                           prefill_chunk=4096, max_prefill_tokens=4096)

    def functions(self, *names):
        namespace = dict(Path=Path, ROOT=self.repo / 'server', re=re,
                         sys=types.SimpleNamespace(executable=str(self.python)),
                         validate_halogen_launcher_controls=lambda *args: None)
        for name in ('halogen_kernel_arguments', 'halogen_speculation_arguments',
                     'halogen_api_defaults_arguments', 'halogen_matmul_arguments',
                     'halogen_lookup_arguments', 'halogen_private_hsa_arguments'):
            namespace[name] = lambda *args: []
        return extracted(CONTROLLER,
                         list(dict.fromkeys(['halogen_vision_arguments', 'halogen_draft_arguments', *names])),
                         namespace)

    def test_missing_or_false_keeps_existing_profile_path(self):
        module = self.functions()
        self.assertEqual(module.halogen_vision_arguments(self.engine, self.directory), [])
        self.engine['disable_vision'] = False
        self.assertEqual(module.halogen_vision_arguments(self.engine, self.directory), [])

    def test_true_forwards_one_flag_only_for_supported_scope(self):
        module = self.functions()
        self.engine['disable_vision'] = True
        self.assertEqual(module.halogen_vision_arguments(self.engine, self.directory), ['--disable-vision'])

    def test_controller_rejects_invalid_booleans(self):
        module = self.functions()
        for value in (None, 0, 1, 'false', 'true', [], {}, 1.0):
            self.engine['disable_vision'] = value
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                module.halogen_vision_arguments(self.engine, self.directory)

    def test_controller_rejects_wrong_kind_checkpoint_or_launcher(self):
        module = self.functions()
        for key, value in [('kind', 'native'), ('checkpoint', 'w4b'), ('launcher', 'powershell')]:
            engine = dict(self.engine, disable_vision=True)
            engine[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.halogen_vision_arguments(engine, self.directory)

    def test_controller_rejects_other_backend_and_missing_parser_support(self):
        module = self.functions()
        engine = dict(self.engine, disable_vision=True)
        other = self.repo / 'backends/halogen-wsl2-0.18.0'
        (other / 'scripts').mkdir(parents=True)
        (other / 'scripts/service.py').write_text(self.service.read_text())
        with self.assertRaises(ValueError):
            module.halogen_vision_arguments(engine, other)
        self.service.write_text('def options():\n    pass\n')
        with self.assertRaises(ValueError):
            module.halogen_vision_arguments(engine, self.directory)

    def test_validate_engine_does_not_allow_invalid_boolean_to_bypass_new_gate(self):
        module = self.functions('validate_engine')
        engine = dict(self.engine, disable_vision='false')
        with self.assertRaises(ValueError):
            module.validate_engine(engine, self.repo)
        engine['disable_vision'] = True
        self.assertEqual(module.validate_engine(engine, self.repo), self.directory.resolve())

    def test_native_engine_cannot_bypass_flag_validation(self):
        module = self.functions('validate_engine')
        engine = dict(kind='native', qualified=True, command=[str(self.python)], disable_vision=True)
        with self.assertRaises(ValueError):
            module.validate_engine(engine, self.repo)

    def test_launch_command_appends_flag_without_changing_existing_arguments(self):
        module = self.functions('halogen_launch_command')
        original = module.halogen_launch_command(self.engine, self.directory)
        text = module.halogen_launch_command(dict(self.engine, disable_vision=True), self.directory)
        self.assertEqual(text, original + ['--disable-vision'])
        self.assertEqual(text.count('--disable-vision'), 1)
        self.assertEqual(text[text.index('--context-size')+1], '262144')
        self.assertEqual(text[text.index('--prompt-cache')+1], 'Exact')
        self.assertEqual(text[text.index('--draft-tokens')+1], '2')
        self.assertEqual(text[text.index('--prefill-chunk')+1], '4096')
        self.assertEqual(text[text.index('--max-prefill-tokens')+1], '4096')
        self.assertEqual(text[3], str(self.directory / 'scripts/service.py'))


class ProfileSnapshot(unittest.TestCase):
    def test_voice_profile_changes_only_explicit_text_flag_from_pinned_original(self):
        self.assertEqual(hashlib.sha256(ORIGINAL_PROFILE.read_bytes()).hexdigest(), ORIGINAL_SHA)
        self.assertTrue(PROFILE.is_file(), 'New explicit Voice text-mode profile is missing')
        original = json.loads(ORIGINAL_PROFILE.read_text(encoding='utf-8-sig'))
        candidate = json.loads(PROFILE.read_text(encoding='utf-8-sig'))
        expected = copy.deepcopy(original)
        expected['engine']['disable_vision'] = True
        self.assertEqual(candidate, expected)
        self.assertEqual(candidate['minimum_reserve_gib'], 18)
        self.assertEqual(candidate['engine']['context'], 262144)
        self.assertEqual(candidate['engine']['prompt_cache'], 'Exact')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-source', type=Path, default=SERVICE)
    parser.add_argument('--controller-source', type=Path, default=CONTROLLER)
    parser.add_argument('--profile-source', type=Path, default=PROFILE)
    chosen, unittest_arguments = parser.parse_known_args()
    SERVICE, CONTROLLER, PROFILE = chosen.service_source, chosen.controller_source, chosen.profile_source
    print('Selected isolated test sources:', flush=True)
    for path in (SERVICE, CONTROLLER, PROFILE):
        print(str(path), hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'MISSING', flush=True)
    unittest.main(argv=[sys.argv[0], *unittest_arguments])
