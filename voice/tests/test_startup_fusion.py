"""Offline launch-environment and identity checks; no process or service probe."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def repository_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'voice/native_qwen_asr.py').is_file() and (parent / 'voice/native-start/start_current_voice.py').is_file():
            return parent
    raise RuntimeError('Cannot find repository Voice sources')


ROOT = repository_root()
HELPER = ROOT / 'voice/native-start/qwen_asr_start.py'
FUSION = 'CRISPASR_QWEN3_ASR_FUSED_QKV'


def source_scope():
    tree = ast.parse(HELPER.read_bytes())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('runtime', 'worker_environment', 'process_identity')]
    scope = dict(os=os, Path=Path, ROOT=ROOT, SCRIPT=ROOT / 'voice/audio_service.py',
                 PYTHON=Path('inert-asr/Scripts/python.exe'),
                 BASE=Path('inert-base/python.exe'), CACHE=Path('inert-cache'))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(HELPER), 'exec'), scope)
    ensure = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'ensure')
    assignment = next(node for node in ast.walk(ensure) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'environment' for target in node.targets))
    return scope, assignment.value


def launch_environment(runtime, inherited):
    scope, expression = source_scope()
    scope['native'] = {'asr_runtime': runtime}
    with patch.dict(os.environ, inherited, clear=True):
        before = dict(os.environ)
        result = eval(compile(ast.Expression(expression), str(HELPER), 'eval'), scope)
        if dict(os.environ) != before:
            raise AssertionError('Launch environment builder mutated the parent process environment')
    return result


def process_identity(runtime, fusion):
    scope, _ = source_scope()
    native = {'asr_runtime': runtime}
    dtype = 'mixed-gguf' if runtime == 'crispasr' else 'float32'
    argv = [str(scope['BASE']), '-u', str(scope['SCRIPT']), '--mode', 'asr', '--dtype', dtype]
    environment = {'HF_HOME': str(scope['CACHE']), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    if fusion is not None:
        environment[FUSION] = fusion
    process = SimpleNamespace(cmdline=lambda: argv, exe=lambda: str(scope['BASE']),
        cwd=lambda: str(ROOT), environ=lambda: dict(environment), create_time=lambda: 1234.5)
    scope['psutil'] = SimpleNamespace(Process=lambda pid: process)
    scope['arguments'] = lambda native: [str(scope['PYTHON']), *argv[1:]]
    return scope['process_identity'](123, native)


class FusionBindingTests(unittest.TestCase):
    def test_native_launch_overrides_inherited_unqualified_zero(self):
        environment = launch_environment('crispasr', {FUSION: '0', 'KEEP': 'unchanged'})
        self.assertEqual(environment[FUSION], '1')
        self.assertEqual(environment['KEEP'], 'unchanged')
        self.assertEqual(environment['OMP_NUM_THREADS'], '6')

    def test_native_launch_pins_one_when_parent_has_no_override(self):
        self.assertEqual(launch_environment('crispasr', {}).get(FUSION), '1')

    def test_torch_launch_keeps_its_existing_environment_contract(self):
        self.assertEqual(launch_environment('torch', {FUSION: '0'})[FUSION], '0')
        self.assertNotIn(FUSION, launch_environment('torch', {}))

    def test_native_identity_rejects_explicit_unqualified_zero(self):
        with self.assertRaises(RuntimeError):
            process_identity('crispasr', '0')

    def test_native_identity_rejects_unbound_missing_fusion(self):
        with self.assertRaises(RuntimeError):
            process_identity('crispasr', None)

    def test_native_identity_accepts_the_qualified_one(self):
        self.assertEqual(process_identity('crispasr', '1'), {'pid': 123, 'created': 1234.5})

    def test_torch_identity_does_not_gain_a_native_only_requirement(self):
        for value in (None, '0', '1'):
            self.assertEqual(process_identity('torch', value), {'pid': 123, 'created': 1234.5})


if __name__ == '__main__':
    unittest.main(verbosity=2)
