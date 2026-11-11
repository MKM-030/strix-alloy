"""Fake-only parity/state/fallback contracts; no native tokenizer is imported."""
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
API = Path(os.environ['HALOGEN0203_LOOKUP_API_SOURCE']) if os.environ.get('HALOGEN0203_LOOKUP_API_SOURCE') else None
HF_SOURCE = Path(os.environ['HALOGEN0203_LOOKUP_HF_SOURCE']) if os.environ.get('HALOGEN0203_LOOKUP_HF_SOURCE') else None
OPEN, CLOSE = 900001, 900002


def subject():
    path = HERE / 'direct_backend_adapter.py'
    if not path.is_file():
        raise AssertionError('The inactive direct-backend adapter is not implemented')
    spec = importlib.util.spec_from_file_location('tested_direct_backend_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBPE:
    dropout = None


class FakeBackend:
    def __init__(self):
        self.padding = self.truncation = None
        self.encode_special_tokens = False
        self.model = FakeBPE()
        self.calls = []
        self.error = self.malformed = None

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        ids = [ord(char) for char in text] if self.malformed is None else self.malformed
        return SimpleNamespace(ids=ids)


class FakeHF:
    def __init__(self):
        self._tokenizer = FakeBackend()
        self.backend_tokenizer = self._tokenizer
        self.split_special_tokens = False
        self._in_target_context_manager = False
        self.model_max_length = 1000000
        self.hf_calls = []
        self.scalar_error = None
        self.decode_text = '1\ta\n2\tb\n3\tc\nseparator\n11\tx\n12\ty\n13\tz'

    def __call__(self, text, **kwargs):
        assert kwargs == {'add_special_tokens': False}
        self.hf_calls.append(text)
        if self.scalar_error is not None:
            raise self.scalar_error
        # Mimic the actual HF call's configuration reset without native work.
        self._tokenizer.padding = self._tokenizer.truncation = None
        self._tokenizer.encode_special_tokens = self.split_special_tokens
        return {'input_ids': [ord(char) for char in text]}

    def decode(self, ids, **kwargs):
        assert kwargs == {'skip_special_tokens': False, 'clean_up_tokenization_spaces': False}
        return self.decode_text


def cache(namespace):
    return ([(key, list(value)) for key, value in namespace['_VIEW_CACHE'].items()],
            list(namespace['_VIEW_CACHE_IDS']))


def fake_modules():
    """Source-file identities are real; all imported classes/modules are fake."""
    source = HF_SOURCE
    names = ('transformers', 'transformers.models', 'transformers.models.qwen2',
        'transformers.tokenization_utils_base', 'transformers.tokenization_utils_tokenizers',
        'transformers.models.qwen2.tokenization_qwen2', 'tokenizers', 'tokenizers.models')
    modules = {name: ModuleType(name) for name in names}
    for module in modules.values(): module.__path__ = []
    for name in names:
        if '.' in name:
            parent, child = name.rsplit('.', 1)
            setattr(modules[parent], child, modules[name])
    for name, file in (('transformers.tokenization_utils_base', 'tokenization_utils_base.py'),
            ('transformers.tokenization_utils_tokenizers', 'tokenization_utils_tokenizers.py'),
            ('transformers.models.qwen2.tokenization_qwen2', 'tokenization_qwen2.py')):
        modules[name].__file__ = str(source / file)
    modules['transformers'].__version__ = '5.15.0'
    modules['tokenizers'].__version__ = '0.22.2'
    modules['tokenizers'].Tokenizer = FakeBackend
    modules['tokenizers.models'].BPE = FakeBPE
    modules['transformers.models.qwen2.tokenization_qwen2'].Qwen2Tokenizer = FakeHF
    return modules


@unittest.skipUnless(API is not None and HF_SOURCE is not None, 'Set explicit API and pinned HF source directories')
class Tests(unittest.TestCase):
    def setup_subject(self, enabled=True):
        module = subject()
        source = API.read_bytes()
        stock = module.lookup_namespace(source)
        candidate = module.lookup_namespace(module.patch_source(source))
        candidate['_LOOKUP_DIRECT_ENABLED'] = enabled
        candidate['_LOOKUP_DIRECT_TYPES'][0] = (FakeHF, FakeBackend, FakeBPE)
        return module, stock, candidate

    def test_default_module_plan_and_generated_candidate_are_inert(self):
        module = subject()
        self.assertFalse(module.plan()['executed'])
        candidate = module.lookup_namespace(module.patch_source(API.read_bytes()))
        self.assertFalse(candidate['_LOOKUP_DIRECT_ENABLED'])
        self.assertEqual(candidate['_LOOKUP_DIRECT_TYPES'], [None])

    def test_exact_API_source_is_required(self):
        module = subject()
        with self.assertRaises(ValueError):
            module.patch_source(API.read_bytes() + b'\n')

    def test_exact_source_binding_uses_only_fake_imports_and_is_cached(self):
        _, _, candidate = self.setup_subject()
        candidate['_LOOKUP_DIRECT_TYPES'][0] = None
        tok = FakeHF()
        with patch.dict(sys.modules, fake_modules()):
            self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['a'])), [[97]])
        self.assertEqual(candidate['_LOOKUP_DIRECT_TYPES'][0], (FakeHF, FakeBackend, FakeBPE))
        self.assertEqual(tok.hf_calls, [])
        # A cached positive binding needs no further module import or file read.
        self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['b'])), [[98]])

    def test_unknown_source_binding_falls_back_and_negative_binding_is_cached(self):
        for changed in ('version', 'source'):
            _, _, candidate = self.setup_subject()
            candidate['_LOOKUP_DIRECT_TYPES'][0] = None
            tok, modules = FakeHF(), fake_modules()
            if changed == 'version': modules['transformers'].__version__ = 'unknown'
            else: modules['transformers.tokenization_utils_base'].__file__ = __file__
            with patch.dict(sys.modules, modules):
                self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['a'])), [[97]])
            self.assertIs(candidate['_LOOKUP_DIRECT_TYPES'][0], False)
            self.assertEqual(tok._tokenizer.calls, [])

    def test_direct_scalar_path_preserves_LOOK_separators_and_warm_cache(self):
        _, stock, candidate = self.setup_subject()
        left, right = FakeHF(), FakeHF()
        for _ in range(3):
            before = stock['lookup_view'](left, [OPEN, 1, CLOSE], OPEN, CLOSE)
            after = candidate['lookup_view'](right, [OPEN, 1, CLOSE], OPEN, CLOSE)
            self.assertEqual(after, before)
            self.assertEqual(cache(candidate), cache(stock))
        self.assertEqual(len(right._tokenizer.calls), 2)
        self.assertEqual(right.hf_calls, [])
        self.assertEqual(len(left.hf_calls), 2)

    def test_off_path_uses_only_original_HF_scalar(self):
        _, _, candidate = self.setup_subject(False)
        tok = FakeHF()
        values = list(candidate['_lookup_encode_segments'](tok, ['a', 'b']))
        self.assertEqual(values, [[97], [98]])
        self.assertEqual(tok._tokenizer.calls, [])

    def test_unknown_types_or_backend_state_fall_back_without_direct_mutation(self):
        def subclass(tok):
            class Other(FakeHF): pass
            return Other()
        cases = [lambda t: setattr(t._tokenizer, 'padding', {'length': 7}),
            lambda t: setattr(t._tokenizer, 'truncation', {'max_length': 2}),
            lambda t: setattr(t._tokenizer, 'encode_special_tokens', True),
            lambda t: setattr(t, 'split_special_tokens', 0),
            lambda t: setattr(t, 'backend_tokenizer', FakeBackend()),
            lambda t: setattr(t, '_in_target_context_manager', True),
            lambda t: setattr(t, '_switch_to_input_mode', lambda: None),
            lambda t: setattr(t, '_encode_plus', lambda *a, **k: None),
            lambda t: setattr(t, 'model_max_length', None),
            lambda t: setattr(t._tokenizer, 'model', SimpleNamespace(dropout=None)),
            lambda t: setattr(t._tokenizer, 'model', type('DropoutBPE', (FakeBPE,), {'dropout': .1})()),
            subclass]
        for change in cases:
            with self.subTest(change=change):
                _, _, candidate = self.setup_subject()
                tok = FakeHF()
                changed = change(tok)
                if isinstance(changed, FakeHF): tok = changed
                self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['abc'])), [[97, 98, 99]])
                self.assertEqual(tok._tokenizer.calls, [])
                self.assertEqual(tok.hf_calls, ['abc'])

    def test_special_token_true_default_is_supported_when_backend_matches(self):
        _, _, candidate = self.setup_subject()
        tok = FakeHF()
        tok.split_special_tokens = tok._tokenizer.encode_special_tokens = True
        self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['abc'])), [[97, 98, 99]])
        self.assertEqual(tok.hf_calls, [])

    def test_native_error_or_malformed_ids_use_original_scalar_fallback(self):
        for value in ([True], ['bad'], [-1], [2**31], (1, 2)):
            with self.subTest(value=value):
                _, _, candidate = self.setup_subject()
                tok = FakeHF(); tok._tokenizer.malformed = value
                self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['abc'])), [[97, 98, 99]])
                self.assertEqual(tok.hf_calls, ['abc'])
        _, _, candidate = self.setup_subject()
        tok = FakeHF(); tok._tokenizer.error = RuntimeError('native unavailable')
        self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['abc'])), [[97, 98, 99]])

    def test_too_long_sequence_uses_original_HF_diagnostic_path(self):
        _, _, candidate = self.setup_subject()
        tok = FakeHF(); tok.model_max_length = 2
        self.assertEqual(list(candidate['_lookup_encode_segments'](tok, ['abc'])), [[97, 98, 99]])
        self.assertEqual(tok.hf_calls, ['abc'])

    def test_native_control_flow_exception_is_not_swallowed(self):
        _, _, candidate = self.setup_subject()
        tok = FakeHF(); tok._tokenizer.error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            list(candidate['_lookup_encode_segments'](tok, ['abc']))

    def test_original_scalar_error_leaves_lookup_cache_unpublished(self):
        _, _, candidate = self.setup_subject()
        tok = FakeHF(); tok._tokenizer.error = RuntimeError('native error')
        tok.scalar_error = ValueError('original scalar error')
        with self.assertRaisesRegex(ValueError, 'original scalar error'):
            candidate['lookup_view'](tok, [OPEN, 1, CLOSE], OPEN, CLOSE)
        self.assertEqual(cache(candidate), ([], [0]))

    def test_unclosed_and_budget_limited_tool_blocks_preserve_exact_cache(self):
        for ids in ([OPEN, 1], [OPEN, 1, CLOSE, OPEN, 2, CLOSE]):
            _, stock, candidate = self.setup_subject()
            for ns in (stock, candidate):
                ns['VIEW_CACHE_MAX_IDS'], ns['VIEW_LOOK_MAX_IDS'] = 7, 12
            left, right = FakeHF(), FakeHF()
            self.assertEqual(stock['lookup_view'](left, ids, OPEN, CLOSE), candidate['lookup_view'](right, ids, OPEN, CLOSE))
            self.assertEqual(cache(stock), cache(candidate))


if __name__ == '__main__':
    unittest.main()
