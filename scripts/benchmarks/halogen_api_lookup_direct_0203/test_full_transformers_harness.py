"""Fake-only protocol tests; no actual Transformers/tokenizer/native import."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
API = Path(os.environ['HALOGEN0203_LOOKUP_API_SOURCE']) if os.environ.get('HALOGEN0203_LOOKUP_API_SOURCE') else None
ADAPTER = HERE / 'direct_backend_adapter.py'


def subject():
    path = HERE / 'full_transformers_harness.py'
    if not path.is_file():
        raise AssertionError('The inactive full-Transformers harness is not implemented')
    spec = importlib.util.spec_from_file_location('full_hf_subject', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeHF:
    def __init__(self, wrong_batch=False):
        self.wrong_batch = wrong_batch
        self.chat_template = 'fixture template'

    def __call__(self, value, **kwargs):
        assert kwargs == {'add_special_tokens': False}
        if isinstance(value, list):
            return {'input_ids': [[9] if self.wrong_batch else [ord(c) for c in part] for part in value]}
        return {'input_ids': [ord(c) for c in value]}

    def decode(self, ids, **kwargs):
        assert kwargs == {'skip_special_tokens': False, 'clean_up_tokenization_spaces': False}
        return ''.join(chr(value) for value in ids)

    @staticmethod
    def convert_tokens_to_ids(value):
        return {'<tool_response>': 900001, '</tool_response>': 900002}[value]


class Clock:
    def __init__(self):
        self.calls = 0
    def __call__(self):
        self.calls += 1
        return self.calls * 100


@unittest.skipUnless(API is not None, 'Set the explicit extracted API input path')
class Tests(unittest.TestCase):
    def protocol(self):
        module = subject()
        adapter = module.load_adapter(ADAPTER)
        templates = module.make_templates(adapter, API.read_bytes())
        # These protocol doubles intentionally use the HF fallback. Native/type
        # qualification is covered by Source's separate pure adapter fixtures.
        templates['direct_backend_scalar']['_LOOKUP_DIRECT_TYPES'][0] = False
        return module, templates

    def test_import_default_inert(self):
        module = subject()
        with patch.object(module, 'run', side_effect=AssertionError('No implicit execution')):
            self.assertEqual(module.main([]), 0)

    def test_actual_serving_loader_has_no_added_kwargs(self):
        module = subject()
        calls = []
        tokenizer = FakeHF()
        auto = NS(from_pretrained=lambda *args, **kwargs: (calls.append((args, kwargs)), tokenizer)[1])
        with patch.dict(sys.modules, {'transformers': NS(AutoTokenizer=auto)}), \
                patch.dict(module.os.environ, {'HALOGEN_CHAT_TEMPLATE': ''}):
            result = module.serving_loader(API.read_bytes(), '/tokenizer')
        self.assertIs(result, tokenizer)
        self.assertEqual(calls, [(('/tokenizer',), {})])

    def test_actual_serving_loader_retains_template_override(self):
        module = subject()
        tokenizer = FakeHF()
        with tempfile.TemporaryDirectory() as td:
            template = Path(td) / 'template.jinja'
            template.write_text('a fixture override', encoding='utf-8')
            auto = NS(from_pretrained=lambda *args, **kwargs: tokenizer)
            with patch.dict(sys.modules, {'transformers': NS(AutoTokenizer=auto)}), \
                    patch.dict(module.os.environ, {'HALOGEN_CHAT_TEMPLATE': str(template)}):
                module.serving_loader(API.read_bytes(), '/tokenizer')
        self.assertEqual(tokenizer.chat_template, 'a fixture override')

    def test_fresh_namespaces_share_only_immutable_code_and_regex(self):
        module, templates = self.protocol()
        first = module.fresh_namespace(templates['stock'])
        second = module.fresh_namespace(templates['stock'])
        self.assertIsNot(first['_VIEW_CACHE'], second['_VIEW_CACHE'])
        self.assertIsNot(first['_VIEW_CACHE_IDS'], second['_VIEW_CACHE_IDS'])
        self.assertIs(first['lookup_view'].__code__, second['lookup_view'].__code__)
        self.assertIs(first['lookup_view'].__globals__, first)

    def test_eight_original_fixture_bodies_and_untimed_parity(self):
        module, templates = self.protocol()
        fixtures = module.prepare_fixtures(FakeHF())
        self.assertEqual(len(fixtures), 8)
        result = module.untimed_parity(templates, FakeHF(), fixtures)
        self.assertEqual(result['HF_wrapper_encode_calls'], {'stock': 85, 'direct_backend_scalar': 85})
        self.assertTrue(result['passed'])

    def test_parity_failure_prevents_timing(self):
        module, templates = self.protocol()
        tokenizer = FakeHF()
        def wrong_ids(tok, segments):
            return [[9] for segment in segments]
        templates['direct_backend_scalar']['_lookup_encode_segments'] = wrong_ids
        fixtures = module.prepare_fixtures(tokenizer)
        with self.assertRaisesRegex(ValueError, 'parity'):
            module.untimed_parity(templates, tokenizer, fixtures)

    def test_error_and_cache_contracts_with_fake_HF(self):
        module, templates = self.protocol()
        result = module.contract_checks(templates, FakeHF())
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['cases']), 3)

    def test_untimed_profile_observes_real_object_and_direct_scalar_calls_without_counter_facade(self):
        module, templates = self.protocol()
        class BPE:
            dropout = None
        class Backend:
            padding = truncation = None
            encode_special_tokens = False
            def __init__(self):
                self.model, self.calls = BPE(), 0
            def encode(self, text, *, add_special_tokens):
                assert add_special_tokens is False
                self.calls += 1
                return NS(ids=[ord(char) for char in text])
        class SupportedHF(FakeHF):
            def __init__(self):
                super().__init__()
                self._tokenizer = self.backend_tokenizer = Backend()
                self.split_special_tokens = False
                self._in_target_context_manager = False
                self.model_max_length = 1000000
        tokenizer = SupportedHF()
        templates['direct_backend_scalar']['_LOOKUP_DIRECT_TYPES'][0] = (SupportedHF, Backend, BPE)
        before = sys.getprofile()
        result = module.untimed_parity(templates, tokenizer, module.prepare_fixtures(tokenizer))
        self.assertEqual(result['HF_wrapper_encode_calls'], {'stock': 85, 'direct_backend_scalar': 0})
        self.assertEqual(tokenizer._tokenizer.calls, 85)
        self.assertIs(sys.getprofile(), before)
        self.assertTrue(result['actual_HF_object_used'])

    def test_timing_is_direct_HF_and_has_fresh_cache(self):
        module, templates = self.protocol()
        tokenizer = FakeHF()
        fixture = module.prepare_fixtures(tokenizer)[3]
        seen = []
        original = templates['stock']['lookup_view']
        # Replace only this unit fixture's function code to observe the exact arg.
        def observe(tok, ids, opening, closing):
            seen.append(tok)
            return original(tok, ids, opening, closing)
        templates['stock']['lookup_view'] = observe
        result, signature = module.time_arm(templates['stock'], tokenizer, fixture, Clock())
        self.assertEqual(seen, [tokenizer])
        self.assertEqual(result['call_ns'], [100])
        self.assertFalse(result['counter_wrapper_used'])

    def test_alternating_pairs_and_warmup_exclusion(self):
        module, templates = self.protocol()
        tokenizer = FakeHF()
        fixture = module.prepare_fixtures(tokenizer)[3]
        warmups, pairs = module.time_case(templates, tokenizer, fixture, 4, 0, Clock())
        self.assertEqual(len(warmups), 2)
        self.assertTrue(all(row['excluded_warmup'] for row in warmups))
        self.assertEqual([row['order'] for row in pairs], [['stock', 'direct_backend_scalar'], ['direct_backend_scalar', 'stock']] * 2)
        summary = module.aggregate_pairs(pairs)
        self.assertEqual(summary['measured_pairs'], 4)
        self.assertEqual(summary['stock']['mean_ns'], 100)

    def test_warm_cache_timing_is_separate_from_untimed_priming(self):
        module, templates = self.protocol()
        tokenizer = FakeHF()
        fixture = module.prepare_fixtures(tokenizer)[6]
        result, _ = module.time_arm(templates['direct_backend_scalar'], tokenizer, fixture, Clock())
        self.assertEqual(result['cache_mode'], 'warm')
        self.assertTrue(result['primed_outside_timing'])
        self.assertEqual(result['call_ns'], [100, 100, 100])


if __name__ == '__main__':
    unittest.main()
