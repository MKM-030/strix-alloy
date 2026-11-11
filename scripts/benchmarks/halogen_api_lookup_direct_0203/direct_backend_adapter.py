"""Inactive exact-source scalar backend candidate. Import/default CLI does no work.

Only --prepare with explicit --api and fresh --output emits a private API copy.
The generated candidate defaults off; Root may enable its isolated namespace for
CPU qualification. No installed backend, tokenizer state or environment is changed.
"""
import argparse
import array
import ast
import collections
import difflib
import hashlib
import json
from pathlib import Path

API_SHA256 = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'

HELPER = '''_LOOKUP_DIRECT_ENABLED = False
_LOOKUP_DIRECT_TYPES = [None]

def _lookup_encode_segments(tok, segments):
    binding = None
    if _LOOKUP_DIRECT_ENABLED:
        binding = _LOOKUP_DIRECT_TYPES[0]
        if binding is None:
            try:
                import hashlib
                from pathlib import Path
                import transformers
                import tokenizers
                from transformers import tokenization_utils_base as base
                from transformers import tokenization_utils_tokenizers as wrapper
                from transformers.models.qwen2 import tokenization_qwen2 as qwen
                from tokenizers.models import BPE
                sources = (
                    (base, "520a914d0dcc873f8c8788e60ad3007f7db032c82c0b2b2c44ee7f44f2cdad8e"),
                    (wrapper, "bf921a160f483c7a32973952ed82a08c7d8982f769726bd220933aae2df98de8"),
                    (qwen, "fac4e6576bfe2369731be147a4e530f262bdf32f2ac50436f96f0d8bdd2fc628"),
                )
                if (transformers.__version__ != "5.15.0" or tokenizers.__version__ != "0.22.2"
                        or any(hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != sha
                               for module, sha in sources)):
                    raise ValueError("unqualified HF source or software")
                binding = (qwen.Qwen2Tokenizer, tokenizers.Tokenizer, BPE)
            except Exception:
                binding = False
            _LOOKUP_DIRECT_TYPES[0] = binding
    for segment in segments:
        direct_ids = None
        if binding:
            try:
                backend = tok.backend_tokenizer
                overrides = ("__call__", "_encode_plus", "_get_padding_truncation_strategies",
                             "set_truncation_and_padding", "_convert_encoding",
                             "_eventual_warn_about_too_long_sequence")
                if (type(tok) is binding[0] and type(backend) is binding[1]
                        and backend is tok._tokenizer and type(backend.model) is binding[2]
                        and backend.model.dropout is None and type(segment) is str
                        and backend.padding is None and backend.truncation is None
                        and type(tok.split_special_tokens) is bool
                        and backend.encode_special_tokens is tok.split_special_tokens
                        and tok._in_target_context_manager is False
                        and not hasattr(tok, "_switch_to_input_mode")
                        and not hasattr(tok, "_switch_to_target_mode")
                        and not any(name in tok.__dict__ for name in overrides)
                        and type(tok.model_max_length) is int and tok.model_max_length > 0):
                    values = backend.encode(segment, add_special_tokens=False).ids
                    if (type(values) is list and len(values) <= tok.model_max_length
                            and all(type(value) is int and 0 <= value < 2147483648 for value in values)):
                        direct_ids = values
            except Exception:
                # The ordinary HF call below owns any legacy error/diagnostic.
                # No partial lookup view is published to the cache on failure.
                pass
        if direct_ids is None:
            direct_ids = tok(segment, add_special_tokens=False)["input_ids"]
        yield direct_ids


'''

OLD_LOOP = '''            for seg in view_segments(text):
                if parts:
                    parts.append(-1)
                parts.extend(tok(seg, add_special_tokens=False)["input_ids"])
'''
NEW_LOOP = '''            for encoded_ids in _lookup_encode_segments(tok, view_segments(text)):
                if parts:
                    parts.append(-1)
                parts.extend(encoded_ids)
'''


def source_sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_source(data):
    if source_sha(data) != API_SHA256:
        raise ValueError('Exact extracted 0.20.3 API source is required')
    source = data.decode('utf-8')
    if source.count(OLD_LOOP) != 1 or source.count('\ndef lookup_view(') != 1:
        raise ValueError('Exact lookup source pattern is required')
    return source.replace(OLD_LOOP, NEW_LOOP, 1).replace(
        '\ndef lookup_view(', '\n' + HELPER + 'def lookup_view(', 1).encode('utf-8')


def lookup_namespace(data):
    """Compile only actual lookup functions and their inert private globals."""
    names = {'_VIEW_NUM', '_VIEW_CACHE', '_VIEW_CACHE_IDS', 'VIEW_CACHE_MAX_IDS',
             'VIEW_LOOK_MAX_IDS', '_LOOKUP_DIRECT_ENABLED', '_LOOKUP_DIRECT_TYPES'}
    functions = {'view_segments', 'lookup_view', '_lookup_encode_segments'}
    body, captured = [], set()
    for node in ast.parse(data).body:
        if isinstance(node, ast.Assign):
            found = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if found & names:
                body.append(node)
                captured |= found
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            body.append(node)
            captured.add(node.name)
    required = names - {'_LOOKUP_DIRECT_ENABLED', '_LOOKUP_DIRECT_TYPES'}
    if not required | {'view_segments', 'lookup_view'} <= captured:
        raise ValueError('Incomplete actual lookup closure')
    namespace = {'array': array, 'collections': collections, 'json': json}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
                 'isolated-halogen0203-direct-lookup.py', 'exec'), namespace)
    return namespace


def plan():
    return dict(source_only=True, executed=False, version='0.20.3',
                upstream_api_sha256=API_SHA256, default_off=True,
                installed_backend_changed=False, tokenizer_state_or_env_changed=False,
                GPU_NPU_HTTP_engine_calls=False, tok_s_gain_qualified=False)


def prepare(api, output):
    original = Path(api).read_bytes()
    candidate = patch_source(original)
    output = Path(output)
    if output.exists():
        raise ValueError('Retain existing evidence; fresh output required')
    output.mkdir()
    (output / 'serve_api.candidate.py').write_bytes(candidate)
    patch = ''.join(difflib.unified_diff(original.decode().splitlines(True),
        candidate.decode().splitlines(True), fromfile='a/serve_api.py', tofile='b/serve_api.py'))
    (output / 'lookup-direct-backend.patch').write_text(patch, encoding='utf-8')
    result = dict(plan(), executed=True, candidate_api_sha256=source_sha(candidate), output=str(output))
    (output / 'source-export.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--api', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.prepare and (args.api is None or args.output is None):
        parser.error('--prepare requires explicit --api and fresh --output')
    print(json.dumps(prepare(args.api, args.output) if args.prepare else plan()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
