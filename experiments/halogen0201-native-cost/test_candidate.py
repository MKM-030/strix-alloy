"""CPU-only private clone and ordinary controller forwarding regressions."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
spec = importlib.util.spec_from_file_location('halogen0201_cost_preparation', HERE / 'prepare.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)
_TEMP = tempfile.TemporaryDirectory(prefix='halogen0201-cost-tests-')
_TEST_ROOT = Path(_TEMP.name)
PACKAGE = _TEST_ROOT / 'candidate'
preparation.export_candidate(REPOSITORY / 'backends/halogen-wsl2-0.20.1', PACKAGE)
CURRENT = _TEST_ROOT / 'baseline.profile.json'
CURRENT.write_text(json.dumps({'engine': {
    'kind': 'halogen', 'directory': 'backends/halogen-wsl2-0.20.1',
    'checkpoint': 'v2', 'context': 32768, 'prompt_cache': 'Off',
    'launcher': 'python', 'python_executable': sys.executable,
    'powershell': 'powershell.exe', 'slots': 1, 'kv_pool_positions': 32768,
    'speculation_policy': {'HALOGEN_PLD': '3,3', 'HALOGEN_MTP_GATE_P': '0.90'},
    'prefill_chunk': 2048, 'max_prefill_tokens': 2048,
    'api_defaults': {'enable_thinking': False, 'reasoning_effort': 'low', 'max_thinking_tokens': 2048},
    'disable_vision': True, 'kernel_controls': {'HALOGEN_DECODE_PREFETCH': 0}
}}))
RULE = 'HALOGEN_MTP_GATE_RULE'
LINE = 'HALOGEN_MTP_GATE_LINE'
sys.path.insert(0, str(PACKAGE / 'scripts'))
# These are the actual temporary clone modules, not synthetic policy stubs.
import service
import speculation_policy as policy


def tearDownModule():
    sys.path.remove(str(PACKAGE / 'scripts'))
    _TEMP.cleanup()


class CostGateTests(unittest.TestCase):
    def options(self, rule=None):
        selected = json.loads(CURRENT.read_bytes())['engine']
        selected['kernel_controls']['HALOGEN_DRAFT_VOCAB_Q8'] = 0
        controls = copy.deepcopy(selected['speculation_policy'])
        if rule is not None:
            controls[RULE] = rule
        return service.options(['--context-size', '32768', '--disable-vision', '--slots', '1',
            '--kv-pool-positions', '32768', '--prefill-chunk', '2048', '--max-prefill-tokens',
            '2048', '--kernel-controls-json', json.dumps(selected['kernel_controls']),
            '--api-defaults-json', json.dumps(selected['api_defaults']),
            '--speculation-policy-json', json.dumps(controls)])

    def manifest(self, rule=None):
        options = self.options(rule)
        with tempfile.TemporaryDirectory(dir=_TEST_ROOT) as folder:
            attempt = Path(folder)
            (attempt / 'entrypoint-service.sh').write_bytes(b'CPU-only manifest digest fixture\n')
            return service.build_manifest(options, attempt, '02010201020102010201020102010201')

    def test_baseline_source_drift_rejects_before_output_creation(self):
        with tempfile.TemporaryDirectory(dir=_TEST_ROOT) as folder:
            root = Path(folder)
            baseline = root / 'baseline'
            source = REPOSITORY / 'backends/halogen-wsl2-0.20.1'
            manifest = json.loads((source / 'profiles/sources.json').read_bytes())
            for name in list(manifest['files']) + ['profiles/sources.json']:
                dest = baseline / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((source / name).read_bytes())
            with (baseline / 'scripts/speculation_policy.py').open('ab') as stream:
                stream.write(b'\n# deliberate drift\n')
            output = root / 'new-candidate'
            with self.assertRaises(ValueError):
                preparation.export_candidate(baseline, output)
            self.assertFalse(output.exists())

    def test_existing_or_repository_output_is_rejected(self):
        source = REPOSITORY / 'backends/halogen-wsl2-0.20.1'
        for output in (PACKAGE, REPOSITORY / 'new-cost-export-forbidden'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                preparation.export_candidate(source, output)
        self.assertFalse((REPOSITORY / 'new-cost-export-forbidden').exists())

    def test_exact_native_gate_and_cost_strings_are_forwarded(self):
        for value in ('gate', 'cost'):
            with self.subTest(value=value):
                self.assertEqual(policy.environment({RULE: value}), {RULE: value})
                self.assertEqual(policy.parse(json.dumps({RULE: value})), {RULE: value})

    def test_omission_leaves_rule_and_line_absent_despite_host_environment(self):
        self.assertEqual(policy.environment(None), {})
        self.assertEqual(policy.environment({}), {})
        with patch.dict(os.environ, {RULE: 'cost', LINE: '0.88'}):
            manifest = self.manifest()
        self.assertNotIn(RULE, manifest['speculation_policy'])
        self.assertNotIn(RULE, manifest['environment'])
        self.assertNotIn(LINE, manifest['environment'])
        self.assertEqual(manifest['environment']['HALOGEN_MTP_GATE_P'], '0.90')

    def test_noncanonical_strings_types_unknown_keys_and_duplicate_json_rejected(self):
        for value in ('', 'Cost', 'GATE', 'cost ', ' gate', 'cost\n', 'drop', 'ride', '0', '1',
                      None, True, False, 0, 1, 0.9, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy.validate({RULE: value})
        for value in ('0.88', '/tmp/calibration', None):
            with self.subTest(line=value), self.assertRaises(ValueError):
                policy.validate({LINE: value})
        with self.assertRaises(ValueError):
            policy.parse('{"HALOGEN_MTP_GATE_RULE":"gate","HALOGEN_MTP_GATE_RULE":"cost"}')

    def test_real_service_manifest_and_container_argv_preserve_rule(self):
        for value in ('gate', 'cost'):
            with self.subTest(value=value):
                manifest = self.manifest(value)
                self.assertEqual(manifest['speculation_policy'][RULE], value)
                self.assertEqual(manifest['environment'][RULE], value)
                self.assertNotIn(LINE, manifest['environment'])
                self.assertEqual(manifest['environment']['HALOGEN_HOST_RESERVE_GIB'], '18')
                self.assertEqual(manifest['environment']['HALOGEN_DRAFT_VOCAB_Q8'], '0')
                self.assertEqual(manifest['environment']['HALOGEN_PLD'], '3,3')
                self.assertEqual(manifest['environment']['HALOGEN_MTP_GATE_P'], '0.90')
                argv = service.command(manifest)
                self.assertEqual(argv.count(RULE + '=' + value), 1)
                self.assertEqual(argv[argv.index(RULE + '=' + value) - 1], '--env')

    def test_persisted_environment_requires_exact_declared_projection(self):
        for declared, actual in ((None, 'cost'), ('gate', 'cost'), ('cost', 'gate'),
                                 (None, None), (None, True), (None, 'cost\n')):
            with self.subTest(declared=declared, actual=actual):
                manifest = self.manifest(declared)
                manifest['environment'][RULE] = actual
                with self.assertRaises(ValueError):
                    service.reject_unqualified_manifest_overrides(manifest)
        manifest = self.manifest('cost')
        del manifest['environment'][RULE]
        with self.assertRaises(ValueError):
            service.reject_unqualified_manifest_overrides(manifest)

    def test_replayed_gate_line_environment_is_rejected(self):
        for value in ('0.88', '/tmp/calibration', None, True):
            with self.subTest(value=value):
                manifest = self.manifest()
                manifest['environment'][LINE] = value
                with self.assertRaises(ValueError):
                    service.reject_unqualified_manifest_overrides(manifest)

    def test_normal_controller_import_validation_and_argv_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=_TEST_ROOT) as folder:
            repo = Path(folder)
            package = repo / 'backends/halogen-wsl2-0.20.1'
            shutil.copytree(PACKAGE, package)
            server = repo / 'server'
            server.mkdir()
            for source in (REPOSITORY / 'server').glob('*.py'):
                shutil.copy2(source, server / source.name)
            sys.path.insert(0, str(server))
            try:
                spec = importlib.util.spec_from_file_location('cost_shadow_controller', server / 'controller.py')
                controller = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(controller)
                for value in ('gate', 'cost'):
                    with self.subTest(value=value):
                        engine = json.loads(CURRENT.read_bytes())['engine']
                        engine['speculation_policy'][RULE] = value
                        engine['python_executable'] = sys.executable
                        directory = controller.validate_engine(engine, repo)
                        argv = controller.halogen_launch_command(engine, directory)
                        parsed = service.options(argv[4:])
                        self.assertEqual(directory, package)
                        self.assertEqual(parsed.speculation_policy_json[RULE], value)
            finally:
                sys.path.pop(0)

    def test_real_clone_print_only_preserves_capacity_and_admission(self):
        for value in ('gate', 'cost'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, '-B', str(PACKAGE / 'scripts/service.py'),
                    '--print-only', '--context-size', '32768', '--disable-vision', '--slots', '1',
                    '--kv-pool-positions', '32768', '--prefill-chunk', '2048',
                    '--max-prefill-tokens', '2048', '--speculation-policy-json',
                    json.dumps({RULE: value})], capture_output=True, text=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                printed = json.loads(result.stdout)
                self.assertEqual((printed['context'], printed['slots'], printed['kv_pool_positions']),
                                 (32768, 1, 32768))
                self.assertEqual(printed['admission_gib'], [30, 131])

    def test_profile_projection_changes_only_the_rule_and_keeps_selected_file_exact(self):
        profile_for_arm = preparation.profile_for_arm
        before = CURRENT.read_bytes()
        original = json.loads(before)
        expected = copy.deepcopy(original)
        expected['engine']['kernel_controls']['HALOGEN_DRAFT_VOCAB_Q8'] = 0
        for arm, value in zip(('before', 'candidate', 'after'), ('gate', 'cost', 'gate')):
            projected = profile_for_arm(original, arm)
            self.assertEqual(projected['engine']['speculation_policy'].pop(RULE), value)
            self.assertEqual(projected, expected)
        self.assertEqual(CURRENT.read_bytes(), before)

    def test_candidate_source_manifest_passes_normal_verification(self):
        service.portable.verify_sources()


if __name__ == '__main__':
    unittest.main()
