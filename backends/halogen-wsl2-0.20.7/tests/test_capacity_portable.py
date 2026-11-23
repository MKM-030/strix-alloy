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
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service
import memory_budget
import checkpoint_integrity as ci

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def bridge_receipts():
    def receipt(size, sha, inode):
        return {'sha256':sha,'identity':{'size':size,'device':2049,'inode':inode,
            'mtime_ns':10000000001,'ctime_ns':20000000002}}
    return {'main':receipt(ci.SIZE,ci.SHA,41),
            'r2':receipt(ci.DRAFTER_SIZE,ci.DRAFTER_SHA,42)}


class CapacityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Managed lookup receipt needs a Windows drive path')
    def test_canonical_lookup_builds_read_only_candidate_and_keeps_stock_bind(self):
        lookup = service.lookup
        config = {
            'receipt': str(ROOT.parents[1] / lookup.CANONICAL_RECEIPT_RELATIVE),
            'receipt_sha256': 'df0dc1e5d2de921b58c4f18f988624687191ec6f80e2336c90c7de454144c7fb',
        }
        flags = ['--lookup-receipt', config['receipt'],
                 '--lookup-receipt-sha256', config['receipt_sha256']]
        opts = service.options(['--disable-vision', *flags])
        receipt = {'source': {'path': '/mnt/c/models/stock.hgn'},
                   'tensor': {}, 'output': {'path': '/home/fixture/canonical.hgn'}}
        reread_binding = {'cache_key': lookup.TRUSTED_CACHE_KEY,
                          'cache_sha256': lookup.TRUSTED_CACHE_SHA}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(lookup, 'read_receipt', return_value=receipt), \
                patch.object(lookup, '_trusted_payload_seal', return_value=reread_binding), \
                patch.object(service.r, 'MACHINE', {'ngram_source': receipt['source']['path']}), \
                patch.object(service.r, 'FIXED_MOUNTS', {'/ngram-w4b.hgn': receipt['source']['path']}):
            attempt = Path(folder)
            (attempt / 'entrypoint-service.sh').write_bytes(b'fixture')
            opts.qualified_lookup = lookup._seal(config, receipt)
            manifest = service.build_manifest(
                opts, attempt, 'a' * 32, checkpoint_receipts=bridge_receipts())
            self.assertEqual(manifest['mounts']['/ngram-w4b.hgn'], '/mnt/c/models/stock.hgn')
            self.assertEqual(manifest['environment']['HALOGEN_NGRAM_TABLE'], '/candidate/ngram.hgn')
            command = service.command(manifest)
            self.assertIn('type=bind,src=/home/fixture/canonical.hgn,dst=/candidate/ngram.hgn,readonly',
                          command)
            self.assertIn('HALOGEN_NGRAM_TABLE=/candidate/ngram.hgn', command)
            for change in ('reverse_mount', 'stale_binding', 'missing_seal'):
                altered = deepcopy(manifest)
                if change == 'reverse_mount':
                    altered['mounts']['/candidate/ngram.hgn'] = '/home/fixture/other.hgn'
                elif change == 'stale_binding':
                    altered['lookup_tuning']['engine_binding']['engine_sha256'] = (
                        'ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89')
                else:
                    del altered['lookup_tuning']
                with self.subTest(change=change), self.assertRaises(ValueError):
                    service.command(altered)

    @unittest.skipUnless(os.name == 'nt', 'Managed lookup receipt needs a Windows drive path')
    def test_native_lookup_requires_canonical_paired_receipt_and_v2(self):
        lookup = service.lookup
        canonical = str(ROOT.parents[1] / lookup.CANONICAL_RECEIPT_RELATIVE)
        for args, message in (
                (['--lookup-receipt', canonical], 'supplied together'),
                (['--lookup-receipt', canonical, '--lookup-receipt-sha256', '0' * 64],
                 'retained canonical'),
                (['--checkpoint', 'w4b', '--lookup-receipt', canonical,
                  '--lookup-receipt-sha256', lookup.CANONICAL_RECEIPT_SHA],
                 'pinned v2 checkpoint')):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, message):
                service.options(args)

    def test_native_lookup_engine_binding_covers_released_entrypoint(self):
        lookup = service.lookup
        expected = '71bfab8eaaea0bc10c9e5e8010af8ed8e537cbca7f61ddae7fc4a32f422a75d9'
        self.assertEqual(lookup._engine_binding()['entrypoint_sha256'], expected)
        stale = dict(service.portable.RELEASE, entrypoint_sha256='0' * 64)
        with patch.object(service.portable, 'RELEASE', stale), \
                self.assertRaisesRegex(ValueError, 'exact 0.20.7'):
            lookup._engine_binding()

    def test_v2_checkpoint_verification_requires_the_official_r2_head(self):
        machine = {'models': '/models'}
        with patch('checkpoint_integrity.verify') as verify, \
                patch('checkpoint_integrity.verify_ngram') as verify_ngram, \
                patch('checkpoint_integrity.verify_drafter') as verify_drafter, \
                patch.object(service.portable, 'check_hash'):
            service.verify_checkpoint(machine, 'v2', disable_vision=True)
        verify.assert_called_once()
        verify_ngram.assert_called_once()
        verify_drafter.assert_called_once()

    def test_ready_v2_log_proves_r2_selection_and_completed_registration(self):
        text_only = '\n'.join((
            'halogen: concurrency mode ON (the default; HALOGEN_CONC_MODE=0 turns it off): '
            'up to 8 requests at a time are served with drafting, 9 to 16 together without it; '
            'this start has 1 slots (HALOGEN_KV_SLOTS: how many requests are served at once).',
            'halogen: draft head qwen38-flash-next-drafter-r2-ht4.hgn '
            '(HALOGEN_CK_OVERLAY=none for the checkpoint\'s own)',
            'halogen: overlay /models/qwen38-flash-next-drafter-r2-ht4.hgn',
            'overlay: 54 tensors, 1.39 GiB from '
            '/models/qwen38-flash-next-drafter-r2-ht4.hgn (HALOGEN_CK_OVERLAY)',
            '[preflight] complete phase=1 copied=65163800576 host=0',
            '[preflight] complete phase=2 copied=66652069248 host=0',
        ))
        service.validate_v2_runtime_log(text_only, disable_vision=True)
        native = text_only + '\nn-gram table: 47.68 GiB from /candidate/ngram.hgn (HALOGEN_NGRAM_TABLE)'
        service.validate_v2_runtime_log(native, disable_vision=True, native_lookup=True)
        with self.assertRaisesRegex(ValueError, 'native lookup'):
            service.validate_v2_runtime_log(text_only, disable_vision=True, native_lookup=True)
        concurrency_off = '\n'.join(text_only.splitlines()[1:])
        service.validate_v2_runtime_log(
            concurrency_off, disable_vision=True, concurrency_mode=0)
        explicit_on = text_only.replace(
            '(the default; HALOGEN_CONC_MODE=0 turns it off)',
            '(HALOGEN_CONC_MODE=1)')
        service.validate_v2_runtime_log(
            explicit_on, disable_vision=True, concurrency_mode=1)
        both_on = text_only + '\n' + explicit_on.splitlines()[0]
        with self.assertRaises(ValueError):
            service.validate_v2_runtime_log(
                both_on, disable_vision=True, concurrency_mode=None)
        with self.assertRaises(ValueError):
            service.validate_v2_runtime_log(
                both_on, disable_vision=True, concurrency_mode=1)
        with self.assertRaises(ValueError):
            service.validate_v2_runtime_log(
                text_only, disable_vision=True, concurrency_mode=0)
        with self.assertRaises(ValueError):
            service.validate_v2_runtime_log(
                concurrency_off, disable_vision=True, concurrency_mode=1)
        vision = text_only + '\n[preflight] complete phase=3 copied=67549932416 host=0'
        service.validate_v2_runtime_log(vision, disable_vision=False)
        for bad in (
            text_only.replace('halogen: concurrency mode ON',
                              'halogen: concurrency mode OFF'),
            text_only.replace('/models/qwen38-flash-next-drafter-r2-ht4.hgn',
                              '/models/other.hgn'),
            text_only.replace('complete phase=2 copied=66652069248 host=0',
                              'complete phase=2 copied=66687364671 host=0'),
            text_only + '\n[preflight] reject phase=2 next=0 copied=0 host=0 reason=test',
        ):
            with self.subTest(log=bad[-120:]), self.assertRaises(ValueError):
                service.validate_v2_runtime_log(bad, disable_vision=True)

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

    def test_explicit_concurrency_requires_the_current_checkpoint_format(self):
        with self.assertRaises(ValueError):
            service.options([
                '--checkpoint', 'w4b', '--kernel-controls-json',
                '{"HALOGEN_CONC_MODE":1}',
            ])

    def test_live_guard_revalidates_a_short_stall_without_weakening_the_floor(self):
        with tempfile.TemporaryDirectory() as folder:
            attempt = Path(folder)
            guard_log = attempt / 'host-guard.jsonl'
            guard_log.write_text('{}\n', encoding='utf-8')
            process = SimpleNamespace(poll=lambda: None)
            safe = {'available_bytes': 19 * service.r.GIB,
                    'commit_headroom_bytes': 19 * service.r.GIB}
            host = SimpleNamespace(frame=lambda: safe)
            with patch.object(service.r, 'guard_alive',
                              side_effect=RuntimeError('stale')):
                now = time.time()
                os.utime(guard_log, (now - 16, now - 16))
                service.guard_alive(process, attempt, host=host)
                def refresh_guard_frame():
                    os.utime(guard_log, None)
                    return safe
                os.utime(guard_log, (now - 16, now - 16))
                service.guard_alive(
                    process, attempt, host=SimpleNamespace(frame=refresh_guard_frame))
                polls = iter((None, 1))
                exiting = SimpleNamespace(poll=lambda: next(polls))
                os.utime(guard_log, (now - 16, now - 16))
                with self.assertRaises(RuntimeError):
                    service.guard_alive(exiting, attempt, host=host)
                failure = attempt / 'guard-failure.json'
                def publish_failure_frame():
                    failure.write_text('{"error":"guard stopped"}\n', encoding='utf-8')
                    return safe
                os.utime(guard_log, (now - 16, now - 16))
                with self.assertRaisesRegex(RuntimeError, 'guard stopped'):
                    service.guard_alive(
                        process, attempt, host=SimpleNamespace(frame=publish_failure_frame))
                failure.unlink()
                os.utime(guard_log, (now - 31, now - 31))
                with self.assertRaises(RuntimeError):
                    service.guard_alive(process, attempt, host=host)
                os.utime(guard_log, (984, 984))
                with patch.object(service.time, 'time', side_effect=(1000, 1031)), \
                        self.assertRaises(RuntimeError):
                    service.guard_alive(process, attempt, host=host)
                low = SimpleNamespace(frame=lambda: {
                    'available_bytes': 18 * service.r.GIB - 1,
                    'commit_headroom_bytes': 19 * service.r.GIB,
                })
                os.utime(guard_log, (now - 16, now - 16))
                with self.assertRaises(ValueError):
                    service.guard_alive(process, attempt, host=low)
                dead = SimpleNamespace(poll=lambda: 1)
                with self.assertRaises(RuntimeError):
                    service.guard_alive(dead, attempt, host=host)
                guard_log.unlink()
                with self.assertRaises(RuntimeError):
                    service.guard_alive(process, attempt, host=host)

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
                    manifest=service.build_manifest(
                        options,attempt,'a'*32,checkpoint_receipts=bridge_receipts())
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
                h=dict(status='ok',version=dict(api='0.20.7',engine='0.20.7',match=True),
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
        expected=json.loads((FIXTURES/'halogen0207-capacity-default-environment.json').read_text())
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
            manifest=service.build_manifest(
                options,attempt,'a'*32,checkpoint_receipts=bridge_receipts())
        self.assertEqual(manifest['context'],32768);self.assertEqual(manifest['slots'],1)
        self.assertNotIn('kv_pool_positions',manifest)
        self.assertEqual(manifest['environment']['HALOGEN_KV_POOL_POSITIONS'],'32768')
        self.assertEqual(manifest['environment']['HALOGEN_KV_SLOTS'],'1')
        self.assertNotIn('HALOGEN_PHASE_RAW',manifest['environment'])
        service.reject_unqualified_manifest_overrides(manifest)

    def test_confidence_rule_is_a_bounded_opt_in(self):
        key = 'HALOGEN_MTP_GATE_RULE'
        policy = {'HALOGEN_MTP_GATE_P': '0.90', key: 'gate'}
        options = service.options(['--speculation-policy-json', json.dumps(policy)])
        baseline = service.environment(32768, speculation_policy={'HALOGEN_MTP_GATE_P': '0.90'})
        candidate = service.environment(32768, speculation_policy=options.speculation_policy_json)
        self.assertNotIn(key, baseline)
        self.assertEqual(candidate, {**baseline, key: 'gate'})
        for unsupported in ('cost', 'drop', 'ride', '0', 0):
            with self.subTest(unsupported=unsupported), self.assertRaises(ValueError):
                service.environment(32768, speculation_policy={key: unsupported})

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


class LookupSourceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.machine = {'distro': 'fixture', 'user': 'fixture'}
        self.source = '/mnt/e/models/qwen38-flash-next-w4b.hgn'
        self.ext4 = '/home/fixture/service.lookup.hgn'
        stock = dict(size=service.lookup.SOURCE_BYTES, device=71, inode=10, mtime_ns=20, ctime_ns=30)
        ext4 = dict(size=service.lookup.OUTPUT_BYTES, device=100, inode=11, mtime_ns=21, ctime_ns=31)
        self.receipt = {
            'source': {'path': self.source, 'identity': stock, 'header_sha256': 'a' * 64},
            'output': {'path': self.ext4, 'identity': ext4},
        }
        self.live = {'source': {**stock, 'device': 43}, 'output': ext4.copy(),
                     'source_header_sha256': 'a' * 64}
        self.integrity = {'source': self.source, 'sha256': service.lookup.SOURCE_SHA,
                          'identity': self.live['source'].copy()}

    def preflight(self, live, integrity):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            (local / 'ngram-integrity.json').write_text(json.dumps(integrity), encoding='utf-8')
            with patch.object(service.portable, 'LOCAL', local), \
                    patch.object(service.portable, 'wsl', return_value=json.dumps(live)):
                return service.lookup.metadata(self.machine, self.receipt, local=local)

    def test_current_stock_receipt_allows_device_only_rebind(self):
        self.assertEqual(self.preflight(self.live, self.integrity), self.live)

    def test_stale_or_foreign_stock_receipt_cannot_rebind(self):
        for wrong in (
            {**self.integrity, 'identity': self.receipt['source']['identity']},
            {**self.integrity, 'source': '/mnt/e/models/other.hgn'},
            {**self.integrity, 'sha256': 'b' * 64},
        ):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, 'stock integrity receipt'):
                self.preflight(self.live, wrong)

    def test_new_inode_size_or_timestamp_still_fails(self):
        for field in ('inode', 'size', 'mtime_ns', 'ctime_ns'):
            observed = deepcopy(self.live)
            observed['source'][field] += 1
            newer = {**self.integrity, 'identity': observed['source']}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'identity'):
                self.preflight(observed, newer)

    def test_rebind_cannot_admit_mutated_ext4_identity_or_header(self):
        bad_ext4 = {**self.live, 'output': {**self.live['output'], 'device': 55}}
        bad_header = {**self.live, 'source_header_sha256': 'c' * 64}
        for observed in (bad_ext4, bad_header):
            with self.subTest(observed=observed), self.assertRaisesRegex(ValueError, 'identity or source header'):
                self.preflight(observed, self.integrity)

    def test_standalone_metadata_call_stays_strict(self):
        with patch.object(service.portable, 'wsl', return_value=json.dumps(self.live)):
            with self.assertRaisesRegex(ValueError, 'identity or source header'):
                service.lookup.metadata(self.machine, self.receipt)



if __name__ == "__main__":
    unittest.main()
