"""Parity and failure contracts over actual AST-isolated 0.20.3 functions."""
import collections
import importlib.util
import json
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
API = Path(os.environ['HALOGEN0203_LOOKUP_API_SOURCE']) if os.environ.get('HALOGEN0203_LOOKUP_API_SOURCE') else None
OPEN, CLOSE = 900001, 900002


def subject():
    path = HERE / 'adapter.py'
    if not path.is_file():
        raise AssertionError('The inactive batch adapter is not implemented yet')
    spec = importlib.util.spec_from_file_location('lookup_batch_subject', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def numbered(groups=3):
    return '\nseparator\n'.join(
        '\n'.join(f'{10 * group + line}\trow {group}/{line} é 今日は' for line in (1, 2, 3))
        for group in range(groups))


class InterfaceTokenizer:
    """Unit-test interface double. Real CPU tokenizer is used by the separate harness."""
    def __init__(self, text, *, batch_error=None, malformed=None, scalar_error=None):
        self.text = text
        self.batch_error = batch_error
        self.malformed = malformed
        self.scalar_error = scalar_error
        self.scalar_calls = self.batch_calls = self.decode_calls = 0

    @staticmethod
    def ids(text):
        return [ord(char) for char in text]

    def __call__(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        if isinstance(text, list):
            self.batch_calls += 1
            if self.batch_error is not None:
                raise self.batch_error
            if self.malformed is not None:
                return self.malformed
            return {'input_ids': [self.ids(segment) for segment in text]}
        self.scalar_calls += 1
        if self.scalar_error and self.scalar_error[0] in text:
            raise self.scalar_error[1]
        return {'input_ids': self.ids(text)}

    def decode(self, ids, *, skip_special_tokens, clean_up_tokenization_spaces):
        assert skip_special_tokens is False and clean_up_tokenization_spaces is False
        self.decode_calls += 1
        return self.text


def state(namespace):
    return ([(key, list(value)) for key, value in namespace['_VIEW_CACHE'].items()],
            list(namespace['_VIEW_CACHE_IDS']))


@unittest.skipUnless(API is not None, 'Set HALOGEN0203_LOOKUP_API_SOURCE to the exact extracted API')
class LookupBatchTests(unittest.TestCase):
    def namespaces(self):
        module = subject()
        original = API.read_bytes()
        candidate = module.patch_source(original)
        return module, module.lookup_namespace(original), module.lookup_namespace(candidate)

    def compare(self, text, *, ids=None, repeats=1, factory=None, configure=None):
        module, stock, candidate = self.namespaces()
        factory = factory or (lambda: InterfaceTokenizer(text))
        left, right = factory(), factory()
        if configure:
            configure(stock)
            configure(candidate)
        ids = ids if ids is not None else [OPEN, 17, 18, CLOSE]
        values = []
        for _ in range(repeats):
            before = stock['lookup_view'](left, ids, OPEN, CLOSE)
            after = candidate['lookup_view'](right, ids, OPEN, CLOSE)
            self.assertEqual(after, before)
            self.assertEqual(state(candidate), state(stock))
            values.append(after)
        return left, right, stock, candidate, values

    def test_default_source_module_and_plan_import_are_inert(self):
        module = subject()
        self.assertFalse(module.plan()['executed'])

    def test_exact_upstream_pin_and_source_transform_are_required(self):
        module = subject()
        source = API.read_bytes()
        self.assertEqual(module.source_sha(source), module.API_SHA256)
        changed = module.patch_source(source)
        self.assertNotEqual(changed, source)
        with self.assertRaisesRegex(ValueError, 'source'):
            module.patch_source(source + b'\n')

    def test_no_tool_response_has_no_tokenizer_calls(self):
        left, right, *_ = self.compare(numbered(), ids=[1, 2, 3])
        self.assertEqual((left.scalar_calls, right.scalar_calls, right.batch_calls), (0, 0, 0))

    def test_empty_unrecognized_tool_text_preserves_empty_cache_entry(self):
        left, right, *_ = self.compare('ordinary text without numbered runs')
        self.assertEqual((left.scalar_calls, right.scalar_calls, right.batch_calls), (0, 0, 0))

    def test_one_json_output_segment_keeps_scalar_behavior(self):
        left, right, *_ = self.compare(json.dumps({'output': 'é 今日は 👩🏽‍💻\n<tool_response> code'}))
        self.assertEqual((left.scalar_calls, right.scalar_calls, right.batch_calls), (1, 1, 0))

    def test_multiple_whole_segments_are_batched_with_exact_ids(self):
        left, right, *_ = self.compare(numbered(8))
        self.assertEqual((left.scalar_calls, right.scalar_calls, right.batch_calls), (8, 0, 1))

    def test_tabs_arrows_bars_and_unicode_preserve_segment_boundaries(self):
        text = numbered(4).replace('1\t', '1→').replace('2\t', '2| ')
        self.compare(text)

    def test_unclosed_tool_response_preserves_end_of_input_behavior(self):
        self.compare(numbered(3), ids=[OPEN, 71, 72])

    def test_repeated_tool_response_hits_same_cache_without_extra_batch(self):
        left, right, *_ = self.compare(numbered(4), repeats=3)
        self.assertEqual((left.scalar_calls, right.batch_calls), (4, 1))
        self.assertEqual((left.decode_calls, right.decode_calls), (1, 1))

    def test_multiple_tool_blocks_preserve_look_separators_and_cache_order(self):
        self.compare(numbered(3), ids=[OPEN, 1, CLOSE, 6, OPEN, 2, CLOSE])

    def test_view_budget_and_strict_output_limit_unchanged(self):
        def configure(namespace):
            namespace['VIEW_CACHE_MAX_IDS'] = 16
            namespace['VIEW_LOOK_MAX_IDS'] = 28
        self.compare(numbered(4), ids=[OPEN, 1, CLOSE, OPEN, 2, CLOSE], configure=configure)

    def test_batch_exception_falls_back_to_original_scalar_calls(self):
        for error in (TypeError('batch unsupported'), ValueError('batch rejected'), RuntimeError('batch failed')):
            with self.subTest(error=type(error).__name__):
                left, right, *_ = self.compare(numbered(3), factory=lambda: InterfaceTokenizer(numbered(3), batch_error=error))
                self.assertEqual((left.scalar_calls, right.scalar_calls, right.batch_calls), (3, 3, 1))

    def test_malformed_batch_shape_or_type_falls_back(self):
        for malformed in ({}, {'input_ids': [1, 2, 3]}, {'input_ids': [[1]]}, {'input_ids': [['x'], [], []]}):
            with self.subTest(malformed=malformed):
                left, right, *_ = self.compare(numbered(3), factory=lambda: InterfaceTokenizer(numbered(3), malformed=malformed))
                self.assertEqual((left.scalar_calls, right.scalar_calls), (3, 3))

    def test_fallback_preserves_original_scalar_error_and_cache_failure_state(self):
        _, stock, candidate = self.namespaces()
        text = numbered(3)
        left = InterfaceTokenizer(text, scalar_error=('row 1/', ValueError('bad scalar segment')))
        right = InterfaceTokenizer(text, batch_error=TypeError('no batch'), scalar_error=('row 1/', ValueError('bad scalar segment')))
        errors = []
        for namespace, tokenizer in ((stock, left), (candidate, right)):
            with self.assertRaises(ValueError) as found:
                namespace['lookup_view'](tokenizer, [OPEN, 7, CLOSE], OPEN, CLOSE)
            errors.append(str(found.exception))
        self.assertEqual(errors, ['bad scalar segment'] * 2)
        self.assertEqual(state(candidate), state(stock))
        self.assertEqual((left.scalar_calls, right.scalar_calls), (2, 2))

    def test_decode_error_is_unchanged_and_does_not_call_tokenizer(self):
        _, stock, candidate = self.namespaces()
        for namespace in (stock, candidate):
            tok = InterfaceTokenizer(numbered())
            def fail(*args, **kwargs):
                raise ValueError('decode failure')
            tok.decode = fail
            with self.assertRaisesRegex(ValueError, 'decode failure'):
                namespace['lookup_view'](tok, [OPEN, 1, CLOSE], OPEN, CLOSE)
            self.assertEqual((tok.scalar_calls, tok.batch_calls), (0, 0))

    def test_control_flow_exceptions_are_not_swallowed(self):
        _, _, candidate = self.namespaces()
        tok = InterfaceTokenizer(numbered(), batch_error=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            candidate['lookup_view'](tok, [OPEN, 1, CLOSE], OPEN, CLOSE)

    def test_empty_segment_separator_behavior_is_exact(self):
        _, stock, candidate = self.namespaces()
        segments = ['', 'a', '', '', 'b', '']
        for namespace in (stock, candidate):
            namespace['view_segments'] = lambda text: segments
        left, right = InterfaceTokenizer('unused'), InterfaceTokenizer('unused')
        before = stock['lookup_view'](left, [OPEN, 1, CLOSE], OPEN, CLOSE)
        after = candidate['lookup_view'](right, [OPEN, 1, CLOSE], OPEN, CLOSE)
        self.assertEqual(after, before)
        self.assertEqual(after, [ord('a'), -1, -1, -1, ord('b'), -1])
        self.assertEqual(state(candidate), state(stock))


if __name__ == '__main__':
    unittest.main()
