"""Inactive exact-source adapter; importing and default invocation do no work.

Only --prepare with explicit --api and --output emits a candidate API copy
and unified diff into a fresh output directory. It never changes an installed backend, loads an engine, or calls HTTP.
"""
import argparse
import array
import ast
import collections
import difflib
import hashlib
import json
import os
from pathlib import Path

API_ENV = 'HALOGEN0203_LOOKUP_API_SOURCE'
API_SHA256 = '7f529cd224e973265237d70e8b9157350302a19faffdc70c05eee3a884e2f4f4'

HELPER = '''def _lookup_encode_segments(tok, segments):
    if len(segments) >= 2:
        try:
            groups = tok(segments, add_special_tokens=False)["input_ids"]
            if (not isinstance(groups, (list, tuple)) or len(groups) != len(segments)
                    or any(not isinstance(group, (list, tuple))
                           or any(type(token) is not int for token in group)
                           for group in groups)):
                raise ValueError("unsupported batch token IDs")
            return groups
        except Exception:
            # Preserve the original scalar path and its errors on unsupported
            # batches. A partial view is never published to the view cache.
            pass
    return (tok(segment, add_special_tokens=False)["input_ids"]
            for segment in segments)


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
        raise ValueError('Exact tool-view source pattern is required')
    return source.replace(OLD_LOOP, NEW_LOOP, 1).replace(
        '\ndef lookup_view(', '\n' + HELPER + 'def lookup_view(', 1).encode('utf-8')


def lookup_namespace(data):
    """Compile only the original view methods and their inert cache assignments."""
    tree = ast.parse(data.decode('utf-8'))
    names = {'_VIEW_NUM', '_VIEW_CACHE', '_VIEW_CACHE_IDS',
             'VIEW_CACHE_MAX_IDS', 'VIEW_LOOK_MAX_IDS'}
    functions = {'view_segments', 'lookup_view', '_lookup_encode_segments'}
    body = []
    captured = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            found = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if found & names:
                body.append(node)
                captured |= found
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            body.append(node)
            captured.add(node.name)
    if not names | {'view_segments', 'lookup_view'} <= captured:
        raise ValueError('Incomplete actual lookup function closure')
    namespace = {'array': array, 'collections': collections, 'json': json}
    unit = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    exec(compile(unit, 'isolated-halogen0203-tool-view.py', 'exec'), namespace)
    return namespace


def plan():
    return {'source_only': True, 'executed': False, 'version': '0.20.3',
            'upstream_api_sha256': API_SHA256, 'installed_backend_changed': False,
            'GPU_NPU_HTTP_engine_calls': False}


def prepare(api, output):
    api, output = Path(api).resolve(), Path(output).resolve()
    original = api.read_bytes()
    candidate = patch_source(original)
    if output.exists():
        raise ValueError('Retain existing generated evidence; do not overwrite')
    output.mkdir()
    (output / 'serve_api.candidate.py').write_bytes(candidate)
    diff = ''.join(difflib.unified_diff(original.decode('utf-8').splitlines(True),
        candidate.decode('utf-8').splitlines(True), fromfile='a/serve_api.py', tofile='b/serve_api.py'))
    (output / 'lookup-segment-batch.patch').write_text(diff, encoding='utf-8')
    receipt = {**plan(), 'executed': True, 'kind': 'private_source_export_only',
               'candidate_api_sha256': source_sha(candidate), 'output': str(output)}
    (output / 'source-export.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--api', type=Path, default=os.environ.get(API_ENV), help='Exact extracted 0.20.3 serve_api.py; or '+API_ENV)
    parser.add_argument('--output', type=Path, help='Fresh explicit output directory; never an active backend')
    args = parser.parse_args(argv)
    if args.prepare and (args.api is None or args.output is None):
        parser.error('--prepare requires --api (or '+API_ENV+') and --output')
    print(json.dumps(prepare(args.api, args.output) if args.prepare else plan()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
