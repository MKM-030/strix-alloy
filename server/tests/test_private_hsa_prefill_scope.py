"""CPU-only checks for the frozen private-HSA prefill exception."""
import ast
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backends/halogen-wsl2-0.16.2'
sys.path.insert(0, str(BACKEND / 'scripts'))
import service

# Compile the real controller guard without importing its HTTP/lifecycle owner.
# Only the unrelated receipt/library qualification boundary is replaced.
source = REPO / 'server/controller.py'
node = next(item for item in ast.parse(source.read_text(encoding='utf-8')).body
            if isinstance(item, ast.FunctionDef) and item.name == 'halogen_private_hsa_arguments')
receipt = {'receipt': str(REPO / 'server/.local/fixture.json'), 'receipt_sha256': 'a' * 64}
admission = SimpleNamespace(validate_scope=service.hsa.validate_scope,
                            qualify=lambda value: {'configuration': value})
imports = SimpleNamespace(util=SimpleNamespace(
    spec_from_file_location=lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None)),
    module_from_spec=lambda spec: admission))
namespace = {'__file__': str(source), 'Path': Path, 're': re, 'importlib': imports}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
controller_guard = namespace['halogen_private_hsa_arguments']


class PrivateHsaPrefillScopeTests(unittest.TestCase):
    def check_scope(self, controls):
        engine = {'checkpoint': 'v2', 'context': 262144, 'prompt_cache': 'Off', 'draft_tokens': 2,
                  'speculation_policy': {'HALOGEN_PLD': '3,3'}, 'private_hsa': receipt} | controls
        options = service.options(['--checkpoint', 'v2', '--context-size', '262144',
                                   '--draft-tokens', '2', '--speculation-policy-json', '{"HALOGEN_PLD":"3,3"}'])
        options.private_hsa_receipt = receipt['receipt']
        options.private_hsa_receipt_sha256 = receipt['receipt_sha256']
        names = {'kernel_controls': 'kernel_controls_json', 'matmul_tuning': 'matmul_tuning_json',
                 'lookup_tuning': 'lookup_receipt'}
        for key, value in controls.items():
            setattr(options, names.get(key, key), value)
        return engine, options

    def test_default_and_exact_8192_pair_reach_both_guards(self):
        for controls in ({}, {'prefill_chunk': 8192, 'max_prefill_tokens': 8192}):
            engine, options = self.check_scope(controls)
            with self.subTest(controls=controls):
                self.assertEqual(controller_guard(engine, BACKEND),
                                 ['-PrivateHsaReceipt', receipt['receipt'], '-PrivateHsaReceiptSha256', 'a' * 64])
                with patch.object(service.hsa, 'validate_configuration', return_value=receipt):
                    self.assertIsNone(service.validate_options(options))

    def test_mixed_other_and_bad_type_prefill_pairs_are_refused(self):
        cases = [{'prefill_chunk': 8192}, {'max_prefill_tokens': 8192},
                 {'prefill_chunk': 4096, 'max_prefill_tokens': 8192},
                 {'prefill_chunk': 8192, 'max_prefill_tokens': 16384},
                 {'prefill_chunk': 32768, 'max_prefill_tokens': 32768}]
        for key in ('prefill_chunk', 'max_prefill_tokens'):
            for value in (True, '8192', 8192.0):
                cases.append({'prefill_chunk': 8192, 'max_prefill_tokens': 8192} | {key: value})
        for controls in cases:
            engine, options = self.check_scope(controls)
            with self.subTest(controls=controls):
                with self.assertRaises(ValueError):
                    controller_guard(engine, BACKEND)
                with patch.object(service.hsa, 'validate_configuration', return_value=receipt):
                    with self.assertRaises(ValueError):
                        service.validate_options(options)

    def test_conflicting_tuning_stays_refused_with_8192_pair(self):
        for conflict in ({'kernel_controls': {'HALOGEN_DN_SCAN': 0}}, {'matmul_tuning': {}},
                         {'lookup_tuning': 'fixture'}, {'prefill_keep_trunk': True}, {'admit_ticks': 1}):
            engine, options = self.check_scope({'prefill_chunk': 8192, 'max_prefill_tokens': 8192} | conflict)
            with self.subTest(conflict=conflict):
                with self.assertRaises(ValueError):
                    controller_guard(engine, BACKEND)
                with patch.object(service.hsa, 'validate_configuration', return_value=receipt):
                    with self.assertRaises(ValueError):
                        service.validate_options(options)


if __name__ == '__main__':
    unittest.main()
