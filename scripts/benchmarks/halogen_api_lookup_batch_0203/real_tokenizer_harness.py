"""Explicit CPU-only parity/call-count harness using the existing target tokenizer.

No latency is measured. The facade implements the API's callable/decode contract
using the already installed tokenizers backend; Transformers itself is not loaded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import struct
import sys

try:
    from . import adapter
except ImportError:
    import adapter

TOKENIZER_SHA = '0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3'


def pin(path):
    path = Path(path)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def ids_sha(ids):
    return hashlib.sha256(struct.pack('<' + 'i' * len(ids), *ids)).hexdigest()


def vendor_package_root(vendor):
    vendor = Path(vendor).resolve(strict=True)
    package = (vendor / 'tokenizers').resolve(strict=True) if (vendor / 'tokenizers').exists() else None
    if (not vendor.is_dir() or package is None or not package.is_dir()
            or not package.is_relative_to(vendor) or not (package / '__init__.py').is_file()
            or not (package / '__init__.py').resolve().is_relative_to(package)):
        raise ValueError('Explicit vendor must contain the actual tokenizers package')
    return package


def validate_package_path(package_root, module):
    value = getattr(module, '__file__', None)
    if not isinstance(value, str) or Path(value).resolve(strict=True) != (package_root / '__init__.py').resolve():
        raise ValueError('Imported tokenizers package is outside the explicit vendor')


def validate_vendor_binding(vendor, module, native):
    package_root = vendor_package_root(vendor)
    validate_package_path(package_root, module)
    value = getattr(native, '__file__', None)
    if not isinstance(value, str):
        raise ValueError('Loaded native tokenizer file is missing')
    native_path = Path(value).resolve(strict=True)
    if (not native_path.is_file() or not native_path.is_relative_to(package_root)
            or native_path.suffix.lower() not in ('.pyd', '.so')):
        raise ValueError('Loaded native tokenizer is outside the explicit vendor')
    if getattr(module, 'Tokenizer', None) is not getattr(native, 'Tokenizer', None) or not hasattr(native, 'Tokenizer'):
        raise ValueError('Tokenizer class does not match the bound native module')
    return {'package': pin(module.__file__), 'native': pin(native_path),
            'Tokenizer_class_matches_loaded_native': True}


def load_vendor_tokenizers(vendor):
    package_root = vendor_package_root(vendor)
    original_path = list(sys.path)
    sys.path.insert(0, str(Path(vendor).resolve()))
    try:
        module = importlib.import_module('tokenizers')
        validate_package_path(package_root, module)
        native = importlib.import_module('tokenizers.tokenizers')
        return module, validate_vendor_binding(vendor, module, native)
    finally:
        sys.path[:] = original_path


class RealTokenizerInterface:
    def __init__(self, backend):
        self.backend = backend
        self.scalar_calls = self.batch_calls = self.decode_calls = 0

    def __call__(self, value, *, add_special_tokens):
        assert add_special_tokens is False
        if isinstance(value, list):
            self.batch_calls += 1
            return {'input_ids': [enc.ids for enc in self.backend.encode_batch(
                value, add_special_tokens=add_special_tokens)]}
        self.scalar_calls += 1
        return {'input_ids': self.backend.encode(value, add_special_tokens=add_special_tokens).ids}

    def decode(self, ids, *, skip_special_tokens, clean_up_tokenization_spaces):
        assert skip_special_tokens is False and clean_up_tokenization_spaces is False
        self.decode_calls += 1
        return self.backend.decode(ids, skip_special_tokens=skip_special_tokens)

    def counts(self):
        return {'scalar_encode': self.scalar_calls, 'batch_encode': self.batch_calls,
                'total_encode': self.scalar_calls + self.batch_calls, 'decode': self.decode_calls}


def numbered(groups):
    return '\n-- another tool excerpt --\n'.join('\n'.join((
        f'{10 * group + 1}\tconst row{group} = new GlideRecord("incident");',
        f'{10 * group + 2}\trow{group}.addQuery("short_description", "é 今日は 👩🏽‍💻");',
        f'{10 * group + 3}\trow{group}.query();')) for group in range(groups))


def cache_state(namespace):
    return {'ids_budget': list(namespace['_VIEW_CACHE_IDS']),
            'entries': [{'key': key, 'count': len(value), 'ids_sha256': ids_sha(value)}
                        for key, value in namespace['_VIEW_CACHE'].items()]}


def run(api, tokenizer_path, vendor, output):
    api, tokenizer_path, vendor, output = (Path(path).resolve() for path in (api, tokenizer_path, vendor, output))
    if output.exists():
        raise ValueError('Retain the completed CPU harness result; do not overwrite')
    tokenizer_pin = pin(tokenizer_path)
    if tokenizer_pin['sha256'] != TOKENIZER_SHA:
        raise ValueError('Existing target tokenizer identity changed')
    tokenizers, backend_binding = load_vendor_tokenizers(vendor)
    if tokenizers.__version__ != '0.23.2':
        raise ValueError('Unexpected existing CPU tokenizer version')
    backend = tokenizers.Tokenizer.from_file(str(tokenizer_path))
    backend.no_padding()
    backend.no_truncation()
    open_id = backend.token_to_id('<tool_response>')
    close_id = backend.token_to_id('</tool_response>')
    if open_id is None or close_id is None:
        raise ValueError('Target tokenizer lacks the API tool-response boundary tokens')
    original = api.read_bytes()
    candidate = adapter.patch_source(original)
    cases = [
        ('no-tool-block', 'plain prompt', 1, False),
        ('unrecognized-tool-text', 'plain tool text without line numbers', 1, True),
        ('one-json-output', json.dumps({'output': 'é 今日は 👩🏽‍💻\nreturn 1;'}), 1, True),
        ('four-numbered-segments', numbered(4), 1, True),
        ('twelve-numbered-segments', numbered(12), 1, True),
        ('fortyeight-numbered-segments', numbered(48), 1, True),
        ('warm-view-cache', numbered(12), 3, True),
        ('json-numbered-segments', json.dumps({'output': numbered(8)}, ensure_ascii=False), 1, True),
    ]
    rows = []
    for name, body, repetitions, tool_block in cases:
        stock = adapter.lookup_namespace(original)
        proposed = adapter.lookup_namespace(candidate)
        left, right = RealTokenizerInterface(backend), RealTokenizerInterface(backend)
        body_ids = backend.encode(body, add_special_tokens=False).ids
        ids = [open_id, *body_ids, close_id] if tool_block else body_ids
        outputs = []
        for _ in range(repetitions):
            before = stock['lookup_view'](left, ids, open_id, close_id)
            after = proposed['lookup_view'](right, ids, open_id, close_id)
            if before != after or cache_state(stock) != cache_state(proposed):
                raise AssertionError('Actual CPU tokenizer parity failed: ' + name)
            outputs.append({'LOOK_count': len(before), 'LOOK_ids_sha256': ids_sha(before)})
        rows.append({'name': name, 'owned_synthetic_tool_fixture': True,
                     'body_utf8_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
                     'actual_input_ids': len(ids), 'input_ids_sha256': ids_sha(ids),
                     'repetitions': repetitions, 'stock_calls': left.counts(),
                     'candidate_calls': right.counts(), 'outputs': outputs,
                     'exact_LOOK_ID_and_cache_state_parity': True})
    total_before = sum(row['stock_calls']['total_encode'] for row in rows)
    total_after = sum(row['candidate_calls']['total_encode'] for row in rows)
    result = {'schema': 'halogen0203.cpu-lookup-batch-harness.v1',
              'utc': datetime.now(timezone.utc).isoformat(), 'api_source': pin(api),
              'candidate_api_sha256': adapter.source_sha(candidate),
              'adapter': pin(Path(adapter.__file__)), 'tokenizer': tokenizer_pin,
              'tokenizers_version': tokenizers.__version__,
              'tokenizer_backend_files': [backend_binding['native']],
              'actual_loaded_tokenizer_binding': backend_binding,
              'interface': 'Actual existing tokenizers backend via the API callable/decode facade; full Transformers wrapper not loaded.',
              'tool_boundary_ids': {'open': open_id, 'close': close_id}, 'cases': rows,
              'total_actual_encode_calls': {'stock': total_before, 'candidate': total_after},
              'actual_encode_call_reduction_percent': (1 - total_after / total_before) * 100,
              'all_exact_LOOK_ID_and_cache_state_parity': True,
              'latency_measured': False, 'latency_or_tok_s_estimate': None,
              'GPU_NPU_HTTP_engine_calls': False, 'installed_backend_changed': False,
              'NPU_cohort_changed': False, 'prefill_decode_acceptance_gain_qualified': False}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return {'result': pin(output), 'actual_encode_calls': result['total_actual_encode_calls'],
            'exact_parity': True, 'latency_measured': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--api', type=Path, default=os.environ.get(adapter.API_ENV))
    parser.add_argument('--tokenizer', type=Path, default=os.environ.get('HALOGEN0203_LOOKUP_TOKENIZER_JSON'))
    parser.add_argument('--vendor', type=Path, default=os.environ.get('HALOGEN0203_LOOKUP_TOKENIZER_VENDOR'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.run and any(value is None for value in (args.api, args.tokenizer, args.vendor, args.output)):
        parser.error('--run requires explicit --api, --tokenizer, --vendor and --output (input paths may also use the documented environment variables)')
    print(json.dumps(run(args.api, args.tokenizer, args.vendor, args.output) if args.run else {'CPU_source_only': True, 'executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
