"""Offline backend capacity contract using source files and tracked static fixtures.

Adapted from the retained candidate portable tests; no installation, private
baseline, model, endpoint, WSL, or lifecycle operations are required.
"""
import ast
from copy import deepcopy
import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service
import memory_budget

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


class CapacityTests(unittest.TestCase):
    def test_capacity_requires_cacheoff_in_options_and_validation(self):
        for slots, pool in ((2, None), (1, 32768), (1, 65536), (2, 65536)):
            flags = ['--context-size', '32768', '--disable-vision', '--slots', str(slots)]
            if pool is not None:
                flags += ['--kv-pool-positions', str(pool)]
            self.assertEqual(service.options(flags).prompt_cache, 'Off')
            for cache in ('Exact', 'Flexible'):
                with self.subTest(slots=slots, pool=pool, cache=cache, boundary='options'), \
                        self.assertRaisesRegex(ValueError, 'CacheOff'):
                    service.options(flags + ['--prompt-cache', cache])
                options = service.options(flags)
                options.prompt_cache = cache
                with self.subTest(slots=slots, pool=pool, cache=cache, boundary='validation'), \
                        self.assertRaisesRegex(ValueError, 'CacheOff'):
                    service.validate_options(options)
        for cache in ('Off', 'Exact', 'Flexible'):
            self.assertEqual(service.options(['--prompt-cache', cache]).prompt_cache, cache)

    def test_capacity_requires_cacheoff_in_direct_environment(self):
        for slots, pool in ((2, None), (1, 32768), (1, 65536), (2, 65536)):
            kwargs = dict(slots=slots, kv_pool_positions=pool, disable_vision=True)
            self.assertEqual(service.environment(32768, prompt_cache='Off', **kwargs)
                             ['HALOGEN_PROMPT_CACHE'], '0')
            for cache in ('Exact', 'Flexible'):
                with self.subTest(slots=slots, pool=pool, cache=cache), \
                        self.assertRaisesRegex(ValueError, 'CacheOff'):
                    service.environment(32768, prompt_cache=cache, **kwargs)
        for cache, encoded in (('Off', '0'), ('Exact', '1'), ('Flexible', '2')):
            self.assertEqual(service.environment(32768, prompt_cache=cache)
                             ['HALOGEN_PROMPT_CACHE'], encoded)

    def test_capacity_requires_cacheoff_in_persisted_manifest(self):
        capacity = importlib.import_module('capacity_policy')
        for slots in (1, 2):
            environment = dict(HALOGEN_CTX='32768', HALOGEN_KV_SLOTS=str(slots),
                               HALOGEN_KV_POOL_POSITIONS='65536', HALOGEN_PROMPT_CACHE='0')
            manifest = dict(context=32768, slots=slots, checkpoint='v2',
                            kv_pool_positions=65536, environment=environment)
            capacity.validate_manifest(manifest)
            service.reject_unqualified_manifest_overrides(manifest)
            for cache in ('<missing>', None, '', 'Off', '1', '2', 0, False, 'unknown'):
                altered = deepcopy(manifest)
                if cache == '<missing>':
                    del altered['environment']['HALOGEN_PROMPT_CACHE']
                else:
                    altered['environment']['HALOGEN_PROMPT_CACHE'] = cache
                with self.subTest(slots=slots, cache=cache), \
                        self.assertRaisesRegex(ValueError, 'CacheOff'):
                    capacity.validate_manifest(altered)
            if slots == 1:
                del manifest['kv_pool_positions']
                manifest['environment']['HALOGEN_KV_POOL_POSITIONS'] = '32768'
                for cache in (None, '0', '1', '2'):
                    if cache is None:
                        manifest['environment'].pop('HALOGEN_PROMPT_CACHE')
                    else:
                        manifest['environment']['HALOGEN_PROMPT_CACHE'] = cache
                    capacity.validate_manifest(manifest)

    def test_explicit_manifest_requires_an_exact_integer_pool(self):
        capacity = importlib.import_module('capacity_policy')
        for context, slots, vision in ((32768, 2, False), (32768, 1, False),
                                       (262144, 1, True)):
            environment = dict(HALOGEN_CTX=str(context), HALOGEN_KV_SLOTS=str(slots),
                               HALOGEN_KV_POOL_POSITIONS=str(context))
            if vision:
                environment['HALOGEN_VISION_TOWER'] = '/models/qwen38-flash-next-vision.hgn'
            manifest = dict(context=context, slots=slots, checkpoint='v2',
                            environment=environment, kv_pool_positions=None)
            with self.subTest(context=context, slots=slots, vision=vision), \
                    self.assertRaisesRegex(ValueError, 'exact KV pool'):
                capacity.validate_manifest(manifest)
            if slots == 1:
                del manifest['kv_pool_positions']
                self.assertEqual(capacity.validate_manifest(manifest),
                                 dict(context=context, slots=1, kv_pool_positions=context))

    def test_source_inventory_covers_package_and_pins_every_file(self):
        inventory = json.loads((ROOT / 'profiles/sources.json').read_text())['files']
        package_files = set()
        for folder, directories, names in os.walk(ROOT):
            directories[:] = [name for name in directories if name not in ('.local', '__pycache__')]
            for name in names:
                path = Path(folder) / name
                if path.suffix != '.pyc' and path != ROOT / 'profiles/sources.json':
                    package_files.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(set(inventory), package_files)
        for name, expected in inventory.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)

    def test_selected_two_full_32k_slots_print_exact_capacity_without_launch(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(service, 'serve') as serve:
            result = service.main(['--print-only', '--context-size', '32768',
                                   '--disable-vision', '--slots', '2',
                                   '--kv-pool-positions', '65536'])
        self.assertEqual(result, 0)
        serve.assert_not_called()
        printed = json.loads(output.getvalue())
        self.assertEqual(printed['slots'], 2)
        self.assertEqual(printed['context'], 32768)
        self.assertEqual(printed['kv_pool_positions'], 65536)
        self.assertEqual(printed['admission_gib'], [30, 131])

    def test_invalid_cli_selectors_and_scope_fail_before_launch(self):
        for flags in (['--slots', '3'], ['--slots', 'true'],
                      ['--kv-pool-positions', '65535'],
                      ['--kv-pool-positions', '65536.0']):
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                service.options(flags)
            self.assertEqual(error.exception.code, 2)
        for flags in (['--slots', '2'],
                      ['--context-size', '32768', '--slots', '2'],
                      ['--context-size', '32768', '--checkpoint', 'w4b',
                       '--disable-vision', '--slots', '2']):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                service.options(flags)

    def test_legacy_options_objects_keep_default_capacity(self):
        legacy = SimpleNamespace(context_size=32768, checkpoint='v2', disable_vision=True)
        self.assertEqual(service.capacity_options(legacy), dict(slots=1, kv_pool_positions=None))
        self.assertFalse(service.explicit_capacity(legacy))
        self.assertEqual(service.resolve_capacity(legacy),
                         dict(context=32768, slots=1, kv_pool_positions=32768))

    def test_all_startup_capacity_calls_propagate_selection(self):
        tree = ast.parse((ROOT / 'scripts/service.py').read_text())
        names = {'environment', 'admission', 'floors', 'check_admission', 'validate_health'}
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id in names]
        self.assertGreaterEqual(len(calls), 9)
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords}
            forwards = any(keyword.arg is None and isinstance(keyword.value, ast.Call)
                           and isinstance(keyword.value.func, ast.Name)
                           and keyword.value.func.id == 'capacity_options'
                           for keyword in call.keywords)
            with self.subTest(function=call.func.id, line=call.lineno):
                self.assertTrue(forwards or {'slots', 'kv_pool_positions'} <= keywords)

    def options(self, slots=2, pool=32768):
        return service.options(['--context-size','32768','--disable-vision',
            '--slots',str(slots),'--kv-pool-positions',str(pool),
            '--prefill-chunk','8192','--max-prefill-tokens','8192'])

    def test_default_capacity_is_unchanged_at_all_existing_contexts(self):
        capacity = importlib.import_module('capacity_policy')
        for context in (4096,4097,32768,262144):
            for checkpoint in ('v2','w4b'):
                self.assertEqual(capacity.resolve(context,checkpoint),
                                 dict(context=context, slots=1, kv_pool_positions=context))

    def test_bounded_opt_in_and_position_accounting(self):
        capacity = importlib.import_module('capacity_policy')
        for slots in (1,2):
            for pool in (32768,65536):
                actual=capacity.resolve(32768,'v2',slots=slots,kv_pool_positions=pool,disable_vision=True)
                self.assertEqual(actual,dict(context=32768,slots=slots,kv_pool_positions=pool))
        self.assertLessEqual(2*(8192+128),32768)
        self.assertGreater(2*(16384+128),32768)
        self.assertLessEqual(2*(16384+128),65536)

    def test_rejects_unbounded_types_pools_and_wrong_scope(self):
        capacity = importlib.import_module('capacity_policy')
        for kwargs in ({'slots':True},{'slots':0},{'slots':3},{'slots':'2'},
                       {'kv_pool_positions':True},{'kv_pool_positions':'65536'},
                       {'kv_pool_positions':33024},{'kv_pool_positions':65535},
                       {'kv_pool_positions':131072}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                capacity.resolve(32768,'v2',disable_vision=True,**kwargs)
        for context,checkpoint,vision in ((262144,'v2',True),(32768,'w4b',True),(32768,'v2',False)):
            with self.subTest(context=context,checkpoint=checkpoint,vision=vision), self.assertRaises(ValueError):
                capacity.resolve(context,checkpoint,slots=2,disable_vision=vision)

    def test_real_service_environment_manifest_and_health_agree(self):
        for slots in (1,2):
            for pool in (32768,65536):
                options=self.options(slots,pool)
                with tempfile.TemporaryDirectory() as folder, \
                        patch.object(service.r,'manifest_for',return_value={'stage':'serve','artifacts':{'bridge':{'path':'C:/fixture/bridge.so','container_path':'/candidate/bridge.so'},'private':{'path':'C:/fixture/private.so','container_path':'/candidate/private.so'}}}), \
                        patch.object(service.r,'MACHINE',{'ngram_source':'fixture.hgn'}), \
                        patch.object(service.r,'FIXED_MOUNTS',{}):
                    attempt=Path(folder); (attempt/'entrypoint-service.sh').write_bytes(b'fixture')
                    manifest=service.build_manifest(options,attempt,'a'*32)
                self.assertEqual(manifest['slots'],slots)
                self.assertEqual(manifest['kv_pool_positions'],pool)
                self.assertEqual(manifest['environment']['HALOGEN_CTX'],'32768')
                self.assertEqual(manifest['environment']['HALOGEN_KV_SLOTS'],str(slots))
                self.assertEqual(manifest['environment']['HALOGEN_KV_POOL_POSITIONS'],str(pool))
                self.assertEqual(manifest['environment']['HALOGEN_HOST_RESERVE_GIB'],'18')
                self.assertNotIn('HALOGEN_PHASE_RAW',manifest['environment'])
                service.reject_unqualified_manifest_overrides(manifest)
                for field in ('HALOGEN_KV_SLOTS','HALOGEN_KV_POOL_POSITIONS','HALOGEN_CTX'):
                    altered=deepcopy(manifest); altered['environment'][field]='unbounded'
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        service.reject_unqualified_manifest_overrides(altered)
                for field,bad in (('slots',True),('slots',3),('kv_pool_positions',33024)):
                    altered=deepcopy(manifest);altered[field]=bad
                    with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):
                        service.reject_unqualified_manifest_overrides(altered)
                h=dict(status='ok',version=dict(api='0.20.1',engine='0.20.1',match=True),
                    context=32768,slot_ctx=32768,kv_pool_positions=pool,slots=slots,
                    vision=dict(enabled=False),capability_probe='ok')
                service.validate_health(h,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                for key,bad in (('slots',3),('slots',True),('kv_pool_positions',12345),
                                ('kv_pool_positions',65536 if pool==32768 else 32768),
                                ('capability_probe','failed')):
                    wrong=deepcopy(h); wrong[key]=bad
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        service.validate_health(wrong,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)

    def test_default_service_env_and_manifest_preserve_normal_semantics(self):
        expected=json.loads((FIXTURES/'halogen0201-capacity-default-environment.json').read_text())
        with patch.object(service.r,'MACHINE',{'ngram_source':'synthetic-fixture.hgn'}):
            actual=service.environment(32768,'v2','Off',prefill_chunk=8192,max_prefill_tokens=8192,
                kernel_controls={'HALOGEN_DECODE_PREFETCH':0},
                speculation_policy={'HALOGEN_PLD':'3,3','HALOGEN_MTP_GATE_P':'0.90'},
                api_defaults={'enable_thinking':False,'reasoning_effort':'low','max_thinking_tokens':2048},disable_vision=True)
        self.assertEqual(actual,expected)
        options=service.options(['--context-size','32768','--disable-vision'])
        with tempfile.TemporaryDirectory() as folder, patch.object(service.r,'FIXED_MOUNTS',{}), \
                patch.object(service.r,'MACHINE',{'ngram_source':'synthetic-fixture.hgn'}):
            attempt=Path(folder);(attempt/'entrypoint-service.sh').write_bytes(b'fixture')
            manifest=service.build_manifest(options,attempt,'a'*32)
        self.assertEqual(manifest['context'],32768);self.assertEqual(manifest['slots'],1)
        self.assertNotIn('kv_pool_positions',manifest)
        self.assertEqual(manifest['environment']['HALOGEN_KV_POOL_POSITIONS'],'32768')
        self.assertEqual(manifest['environment']['HALOGEN_KV_SLOTS'],'1')
        self.assertNotIn('HALOGEN_PHASE_RAW',manifest['environment'])
        service.reject_unqualified_manifest_overrides(manifest)

    def test_default_admission_unchanged_opt_in_never_below_30_131(self):
        import memory_budget
        expected_commits={4096:123,4097:123,32768:124,262144:131}
        for context,commit in expected_commits.items():
            self.assertEqual(memory_budget.admission_floors(context,'v2'),(30,commit))
            self.assertEqual(memory_budget.admission_floors(context,'w4b'),(52,commit))
        for slots in (1,2):
            for pool in (32768,65536):
                physical,commit=service.floors(32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                self.assertGreaterEqual(physical,30);self.assertGreaterEqual(commit,131)
                frame=dict(available_bytes=physical*2**30,commit_headroom_bytes=commit*2**30)
                service.check_admission(frame,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)
                for field in ('available_bytes','commit_headroom_bytes'):
                    bad=dict(frame);bad[field]-=1
                    with self.subTest(slots=slots,pool=pool,field=field),self.assertRaises(ValueError):
                        service.check_admission(bad,32768,disable_vision=True,slots=slots,kv_pool_positions=pool)


if __name__ == "__main__":
    unittest.main()
