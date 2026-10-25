"""Focused CPU tests: canonical payload trust, service wiring and actual RO binds.

The metadata boundary is mocked; this test never invokes WSL, an engine, or a
model/table readback. It reads only the retained small receipt and cache files.
"""
import copy
import ast
import os
import re
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / 'backends/halogen-wsl2-0.18.15').is_dir())
BACKEND = REPO / 'backends/halogen-wsl2-0.18.15'
SOURCES = Path(os.environ.get('ALLOY_LOOKUP_TEST_SOURCE', str(BACKEND / 'scripts')))
def source(name):
    candidate = SOURCES / name
    return candidate if candidate.is_file() else BACKEND / 'scripts' / name
CONFIG = {
    'receipt': str(REPO / 'server/.local/optimization9h-20261004/lookup-native-copy-9447b9641f964497980fcb281b18a5c3/extraction.receipt.json'),
    'receipt_sha256': 'df0dc1e5d2de921b58c4f18f988624687191ec6f80e2336c90c7de454144c7fb',
}


class NativeLookupPortTest(unittest.TestCase):
    def test_cached_payload_needs_fresh_identity_and_exact_engine_mount(self):
        spec = importlib.util.spec_from_file_location('staged_native_lookup', source('lookup_source.py'))
        lookup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lookup)
        lookup.ROOT = BACKEND
        lookup.RECEIPT_ROOTS = (BACKEND / '.local', REPO / 'server/.local')
        receipt = lookup.read_receipt(CONFIG)
        image = 'ghcr.io/peonist-ai/halogen-flash-server@sha256:cde6ae91ab3497a470c848fd5c509b0f4af659a1dea7e74b8789df82cde0510e'
        release = dict(version='0.18.15', image=image,
                       engine_sha256='ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89')
        portable = types.SimpleNamespace(IMAGE=image, RELEASE=release,
            MODELS=[('qwen38-flash-next-w4b.hgn', lookup.SOURCE_BYTES, lookup.SOURCE_SHA)],
            reject_links=lookup.reject_links)
        def receipt_matches(record, identity, *, size, sha, source):
            return (record == {'sha256': sha, 'identity': identity, 'source': source}
                    and identity['size'] == size)
        integrity = types.SimpleNamespace(receipt_matches=receipt_matches)
        calls = []
        def metadata(machine, selected):
            calls.append(selected['output']['identity'])
            return {'source': selected['source']['identity'], 'output': selected['output']['identity']}
        def no_readback(*args):
            self.fail('A trusted existing payload cache must not trigger a 50 GB readback')
        machine = {'models': '/home/revn/halogen-models-native',
                   'ngram_source': receipt['source']['path']}
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(sys.modules, portable=portable, checkpoint_integrity=integrity), \
                patch.object(lookup, 'metadata', side_effect=metadata), \
                patch.object(lookup, 'guarded_hash', side_effect=no_readback):
            local = Path(directory)
            (local / 'ngram-integrity.json').write_text(json.dumps({
                'sha256': lookup.SOURCE_SHA, 'identity': receipt['source']['identity'],
                'source': machine['ngram_source']}))
            seal = lookup.qualify(machine, local, CONFIG)
            self.assertEqual(seal['schema'], 2)
            self.assertEqual(seal['engine_binding'], lookup.ENGINE_BINDING)
            self.assertGreaterEqual(len(calls), 1)
            manifest = {'version': '0.18.15', 'image': image, 'checkpoint': 'v2',
                'mounts': {'/ngram-w4b.hgn': receipt['source']['path']},
                'environment': {'HALOGEN_NGRAM_TABLE': '/ngram-w4b.hgn'}}
            lookup.bind_manifest(manifest, seal)
            lookup.validate_manifest(manifest)
            self.assertTrue(seal['mount_binding']['readonly'])
            self.assertEqual(manifest['mounts']['/candidate/ngram.hgn'], receipt['output']['path'])
            self.assertEqual(manifest['mounts']['/ngram-w4b.hgn'], receipt['source']['path'])
            for field in ('image', 'mounts', 'environment'):
                changed = copy.deepcopy(manifest)
                if field == 'image': changed['image'] = 'unqualified-image'
                elif field == 'mounts': changed['mounts']['/candidate/ngram.hgn'] = '/tmp/other.hgn'
                else: changed['environment']['HALOGEN_NGRAM_TABLE'] = '/ngram-w4b.hgn'
                with self.subTest(binding=field), self.assertRaises(ValueError):
                    lookup.validate_manifest(changed)
            with patch.object(lookup, 'metadata', side_effect=ValueError('Fresh identity changed')):
                with self.assertRaisesRegex(ValueError, 'Fresh identity changed'):
                    lookup.revalidate(machine, seal)

    def test_service_build_command_and_running_ownership_bind_actual_readonly_table(self):
        def module(name):
            spec = importlib.util.spec_from_file_location('lookup_cpu_' + name, source(name + '.py'))
            result = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(result)
            return result
        def functions(path, names, scope):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
            self.assertEqual({node.name for node in nodes}, set(names))
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
            return scope
        lookup = module('lookup_source')
        lookup.ROOT = BACKEND
        lookup.RECEIPT_ROOTS = (BACKEND / '.local', REPO / 'server/.local')
        receipt = lookup.read_receipt(CONFIG)
        image = lookup.ENGINE_BINDING['image']
        portable = types.SimpleNamespace(IMAGE=image, RELEASE=dict(lookup.ENGINE_BINDING),
            digest=lambda path: 'test-entrypoint-source-pin')
        with patch.dict(sys.modules, portable=portable):
            seal = lookup._seal(lookup.validate_configuration(CONFIG), receipt)
            runner_scope = functions(source('runner.py'), ['owned'], dict(re=re, IMAGE=image))
            runner = types.SimpleNamespace(IMAGE=image, GIB=2**30,
                MACHINE={'ngram_source': receipt['source']['path']},
                FIXED_MOUNTS={'/models': '/home/revn/halogen-models-native',
                              '/ngram-w4b.hgn': receipt['source']['path']},
                manifest_for=lambda stage: {'artifacts': {}}, environment=lambda manifest: {},
                linux_path=lambda path: '/unit-sources/' + Path(path).name,
                owned=runner_scope['owned'])
            guard_scope = functions(source('startup_guard.py'), ['validate_target'], dict(re=re))
            guard = types.SimpleNamespace()
            def validate_target(info, cid):
                guard_scope.update(REVIEWED_IMAGES=guard.REVIEWED_IMAGES, EXPECTED_MOUNTS=guard.EXPECTED_MOUNTS)
                guard_scope['validate_target'](info, cid)
            guard.validate_target = validate_target
            names = ['validate_options', 'validate_disable_vision', 'validate_prefill_limits',
                     'environment', 'build_manifest', 'reject_unqualified_manifest_overrides', 'command', 'owned']
            service = functions(source('service.py'), names, dict(
                lookup=lookup, portable=portable, r=runner, sg=guard, ROOT=BACKEND,
                LOCAL=BACKEND / '.local', TOKEN_PATH=Path('/unit-token-path'),
                kc=module('kernel_controls'), sp=module('speculation_policy'), ad=module('api_defaults'),
                source_hashes=lambda: {}))
            options = types.SimpleNamespace(checkpoint='v2', context_size=32768, serve_seconds=0,
                startup_timeout=900, prompt_cache='Flexible', prefill_chunk=8192, max_prefill_tokens=8192,
                kernel_controls_json={'HALOGEN_DECODE_PREFETCH': 0}, speculation_policy_json={
                    'HALOGEN_PLD': '3,3', 'HALOGEN_MTP_GATE_P': '0.90'},
                api_defaults_json={'enable_thinking': False, 'reasoning_effort': 'low', 'max_thinking_tokens': 2048},
                lookup_receipt=None, lookup_receipt_sha256=None, qualified_lookup=None)
            stock = service['build_manifest'](options, Path('/unit-attempt'), 'unit-owned-run')
            self.assertNotIn('lookup_tuning', stock)
            self.assertNotIn(lookup.NATIVE_MOUNT, stock['mounts'])
            options.lookup_receipt, options.lookup_receipt_sha256 = CONFIG['receipt'], CONFIG['receipt_sha256']
            options.qualified_lookup = seal
            selected = service['build_manifest'](options, Path('/unit-attempt'), 'unit-owned-run')
            self.assertEqual(set(selected['mounts']) - set(stock['mounts']), {lookup.NATIVE_MOUNT})
            self.assertEqual({key for key in stock['environment']
                              if stock['environment'][key] != selected['environment'][key]}, {'HALOGEN_NGRAM_TABLE'})
            self.assertEqual(selected['environment']['HALOGEN_HOST_RESERVE_GIB'], '18')
            self.assertEqual(selected['environment']['HALOGEN_DECODE_PREFETCH'], '0')
            self.assertEqual(selected['environment']['HALOGEN_PREFILL_CHUNK'], '8192')
            self.assertEqual(selected['environment']['HALOGEN_MAX_TOK'], '8192')
            argv = service['command'](selected)
            mounts = [argv[index + 1] for index, item in enumerate(argv) if item == '--mount']
            self.assertEqual(len(mounts), len(selected['mounts']))
            self.assertTrue(all(value.endswith(',readonly') for value in mounts))
            self.assertIn(f'type=bind,src={receipt["output"]["path"]},dst=/candidate/ngram.hgn,readonly', mounts)
            self.assertEqual(argv[argv.index('--memory') + 1], str(44 * 2**30))
            cid = 'a' * 64
            name = 'halogen-flash-hybrid-service-' + selected['run_id']
            info = {'Id': cid, 'Name': '/' + name, 'State': {'Running': True},
                'Config': {'Image': image, 'Labels': {'halogen.performance': 'hybrid',
                    'strix-alloy.owner': 'strix-alloy-wsl2', 'strix-alloy.run': name},
                    'Env': [key + '=' + value for key, value in selected['environment'].items()]},
                'Mounts': [{'Destination': destination, 'Source': source, 'Type': 'bind', 'RW': False}
                           for destination, source in selected['mounts'].items()],
                'HostConfig': {'Memory': 44 * 2**30, 'MemorySwap': 44 * 2**30, 'RestartPolicy': {'Name': 'no'}},
                'NetworkSettings': {'Ports': {'8731/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8731'}]}}}
            service['owned'](info, cid, selected, running=True)
            writable = copy.deepcopy(info)
            next(item for item in writable['Mounts'] if item['Destination'] == lookup.NATIVE_MOUNT)['RW'] = True
            with self.assertRaisesRegex(ValueError, 'read-only binding'):
                service['owned'](writable, cid, selected, running=True)
            changed_env = copy.deepcopy(info)
            changed_env['Config']['Env'] = [value for value in changed_env['Config']['Env']
                                           if not value.startswith('HALOGEN_NGRAM_TABLE=')]
            changed_env['Config']['Env'].append('HALOGEN_NGRAM_TABLE=/ngram-w4b.hgn')
            with self.assertRaisesRegex(ValueError, 'Container environment changed'):
                service['owned'](changed_env, cid, selected, running=True)


if __name__ == '__main__':
    unittest.main()
