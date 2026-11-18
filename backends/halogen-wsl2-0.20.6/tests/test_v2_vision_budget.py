"""Vision adds full pinned tower admission demand, without changing reserves."""
import ast
import importlib.util
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('memory_budget', ROOT / 'scripts/memory_budget.py')
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)
sys.modules['memory_budget'] = budget
tree = ast.parse((ROOT / 'scripts/service.py').read_text())
selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                           and node.name in ('floors', 'check_admission', 'validate_disable_vision')],
                      type_ignores=[])
service_functions = {'r': SimpleNamespace(GIB=1024 ** 3)}
exec(compile(selected, 'actual_service_admission', 'exec'), service_functions)

class V2VisionBudgetTests(unittest.TestCase):
    def test_full_tower_charge_only_for_explicit_vision(self):
        self.assertIn('vision', inspect.signature(budget.admission_floors).parameters)
        for context in (4096, 32768, 262144):
            with self.subTest(context=context):
                baseline = budget.admission_floors(context, 'v2', vision=False)
                vision = budget.admission_floors(context, 'v2', vision=True)
                self.assertEqual(vision, (baseline[0] + 1, baseline[1] + 1))
        self.assertEqual(budget.admission_floors(262144, 'v2', vision=False), (30, 131))
        self.assertEqual(budget.admission_floors(262144, 'v2', vision=True), (31, 132))
        self.assertEqual(budget.RUNTIME_RESERVE_GIB, 18)

    def test_vision_argument_cannot_silently_apply_to_unknown_mode(self):
        self.assertIn('vision', inspect.signature(budget.admission_floors).parameters)
        for vision in (None, 1, 'true'):
            with self.subTest(vision=vision):
                with self.assertRaises(ValueError): budget.admission_floors(262144, 'v2', vision=vision)
        with self.assertRaises(ValueError): budget.admission_floors(262144, 'w4b', vision=True)

    def test_actual_service_rejects_memory_sufficient_only_for_text(self):
        check = service_functions['check_admission']
        self.assertIn('disable_vision', inspect.signature(check).parameters)
        frame = {'available_bytes': int(30.5 * 1024 ** 3), 'commit_headroom_bytes': int(131.5 * 1024 ** 3)}
        check(frame, 262144, 'v2', disable_vision=True)
        with self.assertRaisesRegex(ValueError, '31 GiB.*132 GiB'):
            check(frame, 262144, 'v2', disable_vision=False)
        check({'available_bytes': 31 * 1024 ** 3, 'commit_headroom_bytes': 132 * 1024 ** 3},
              262144, 'v2', disable_vision=False)

    def test_all_startup_admission_calls_propagate_the_selected_vision_mode(self):
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id in ('floors', 'check_admission', 'admission')]
        self.assertGreaterEqual(len(calls), 7)
        for call in calls:
            with self.subTest(function=call.func.id, line=call.lineno):
                self.assertIn('disable_vision', [keyword.arg for keyword in call.keywords])

if __name__ == '__main__':
    unittest.main()
