"""CPU-only release contracts. Captured-file checks skip when inputs are absent.

Set HALOGEN0207_CAPTURE to a passive image extraction directory to exercise the
exact upstream ELF/API/entrypoint. No executable from the image is run.
"""
import ast
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = Path(os.environ.get('HALOGEN0207_CAPTURE', str(
    ROOT.parents[1] / 'server/.local/halogen-update-20261118/primary0207/capture')))
ENGINE_SHA = '523804e4aab8a6203f277fe3632663f91c0aa008bdb187413b6ef4f139415640'
ENTRY_SHA = '2bb8c5124742bc2da4b7676019aa2c7987d10515593fd4f4cd4875ffcd9cf75a'
API_SHA = '71240612de5013fa49780de9243adbf60516afe81729f73aa67f98f9fde75c9f'

def module(test, name):
    path = ROOT / 'scripts' / (name + '.py')
    test.assertTrue(path.is_file(), 'New release adapter has not been prepared: ' + name)
    spec = importlib.util.spec_from_file_location('compat0207_' + name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def captured(test, name):
    path = CAPTURE / name
    if not path.is_file():
        test.skipTest('passive release capture not available: ' + name)
    return path.read_bytes()

def cache_off(auth):
    return list(auth._OFF_CSTAT_PREFIX) + ['3', '1.2', '4', '5', '6', '32768', '7', '8', '9', '10', '11']

def cached():
    result = ['C'] + [str(n) for n in range(1, 59)]
    for n in (10, 11, 12, 13, 16, 35, 40):
        result[n] += '.0'
    result[52] = '/cache/root'
    return result

class ReleaseCompatibility(unittest.TestCase):
    def test_bridge_accepts_exact_new_engine_and_rejects_mutations(self):
        bridge = module(self, 'bridge_adapter')
        data = captured(self, 'flash_serve')
        self.assertEqual(hashlib.sha256(data).hexdigest(), ENGINE_SHA)
        self.assertIsNone(bridge.verify_engine(data))
        for name, position in [('magic', 0), ('site', 0x28b3102),
                               ('function', 0x28b2a20), ('outside_function', 128),
                               ('program_header_count', 56)]:
            with self.subTest(name=name):
                changed = bytearray(data)
                changed[position] ^= 1
                with self.assertRaises(ValueError):
                    bridge.verify_engine(changed)
        with self.assertRaises(ValueError):
            bridge.verify_engine(data[:-1])

    def test_bridge_pins_frame_and_source_names_match_new_release(self):
        bridge = module(self, 'bridge_adapter')
        self.assertEqual(bridge.ENGINE_SHA, ENGINE_SHA)
        self.assertEqual((bridge.ENGINE_BYTES, bridge.SITE_RVA, bridge.SITE_OFFSET),
                         (43105992, 0x28b4102, 0x28b3102))
        self.assertEqual((bridge.FUNCTION_OFFSET, bridge.FUNCTION_END), (0x28b2a20, 0x28b4354))
        for name, digest in bridge.SOURCES.items():
            self.assertEqual(hashlib.sha256((ROOT / 'patches' / name).read_bytes()).hexdigest(), digest)

    def test_entrypoint_transform_preserves_new_upstream_outside_audited_functions(self):
        entry = module(self, 'entrypoint_adapter')
        original = captured(self, 'entrypoint-upstream.sh')
        result = entry.transform(original)
        self.assertEqual(hashlib.sha256(result).hexdigest(), ENTRY_SHA)
        self.assertEqual(result.count(b'/halogen/tools/serve_api.py'), 5)
        self.assertIn(b'halogen0207-dxg', result)
        self.assertIn(b'/candidate/halogen0207_hip_probe', result)
        self.assertIn(b'native_host_preflight', result)
        # Upstream additions remain present; only the existing engine watchdog
        # switches to monotonic uptime. No new NPU service is invoked here.
        self.assertIn(b'conc_mode_check() {', result)
        self.assertIn(b'drafter_head() {', result)
        self.assertIn(b'npu_stall_watchdog() {', result)
        marker = b'engine_watchdog() {\n'
        start = result.index(marker)
        wd = result[start:result.index(b'\n}\n', start) + 3]
        self.assertNotIn(b'$(date +%s)', wd)
        self.assertEqual(wd.count(b'$(wd_uptime_s)'), 3)
        with self.assertRaises(ValueError):
            entry.transform(original + b'\n')

    def test_cacheoff_removes_only_redundant_field_and_preserves_live_counters(self):
        auth = module(self, 'auth_api')
        tokens = cache_off(auth)
        result = auth.normalize_cache_tokens(tokens)
        self.assertEqual(len(tokens), 51)
        self.assertEqual(len(result), 50)
        self.assertEqual(result, tokens[:35] + tokens[36:])
        self.assertEqual(result[39:], tokens[40:])

    def test_new_cached_59_field_wire_is_passed_through_without_counter_loss(self):
        auth = module(self, 'auth_api')
        tokens = cached()
        self.assertIs(auth.normalize_cache_tokens(tokens), tokens)
        self.assertEqual(tokens[57:], ['57', '58'])

    def test_wrong_cache_layouts_and_fields_fail_closed(self):
        auth = module(self, 'auth_api')
        for bad in [[], (), None, cached()[:-2], cached()[:-1], cached() + ['59']]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                auth.normalize_cache_tokens(bad)
        for offset, value in [(0, 'X'), (40, 'nan'), (41, '1.0'), (52, '/cache root'),
                              (57, '1.2'), (58, ''), (58, 0), (58, '1\n')]:
            bad = cached(); bad[offset] = value
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                auth.normalize_cache_tokens(bad)
        for offset, value in [(35, '1'), (40, '-1'), (41, 'nan'), (50, '-1')]:
            bad = cache_off(auth); bad[offset] = value
            with self.subTest(off=offset), self.assertRaises(ValueError):
                auth.normalize_cache_tokens(bad)

    def test_actual_new_cache_method_retains_native_code_and_parses_corrected_pool(self):
        auth = module(self, 'auth_api')
        source = captured(self, 'serve_api.py')
        self.assertEqual(hashlib.sha256(source).hexdigest(), API_SHA)
        code = compile(source, auth.UPSTREAM, 'exec', dont_inherit=True)
        engine_code = next(x for x in code.co_consts if isinstance(x, types.CodeType) and x.co_name == 'Engine')
        method_code = next(x for x in engine_code.co_consts if isinstance(x, types.CodeType) and x.co_name == 'cache_stats')
        namespace = {'asyncio': asyncio, 'time': time, 'HTTPException': RuntimeError}
        engine = type('Engine', (), {'cache_stats': types.FunctionType(method_code, namespace)})
        namespace['Engine'] = engine
        retained = {}
        for name in ('native_split', 'render_once_setup', 'flash_model_refusal'):
            obj = next(x for x in code.co_consts if isinstance(x, types.CodeType) and x.co_name == name)
            retained[name] = namespace[name] = types.FunctionType(obj, namespace)
        auth.install_cache_stats(namespace, source)
        for name, obj in retained.items(): self.assertIs(namespace[name], obj)
        tokens = cache_off(auth)
        class Writer:
            def write(self, value): assert value == b'CSTAT\n'
            async def drain(self): pass
        class Reader:
            async def readline(self): return (' '.join(tokens) + '\n').encode()
        async def ensure(self): pass
        engine._ensure = ensure
        engine._note_pool = lambda self, value: None
        instance = engine(); instance.n_slots = 1; instance.slots = asyncio.Semaphore(1)
        instance.w, instance.r = Writer(), Reader()
        value = asyncio.run(instance.cache_stats())
        self.assertEqual(value['pool'], dict(waiting_for_room=3, waiting_s=1.2, relocated=4,
            cold_resorts=5, used=6, positions=32768, busy_regions=7, held_regions=8,
            room_clamped=9, moved=10, packed=11))
        with self.assertRaises(ValueError): auth.install_cache_stats(namespace, source)

    def test_new_normal_policy_preserves_automatic_drafter_and_floors(self):
        service = (ROOT / 'scripts/service.py').read_text(encoding='utf-8') if (ROOT / 'scripts/service.py').exists() else ''
        self.assertIn("HALOGEN_CK_OVERLAY=''", service)
        upstream = captured(self, 'entrypoint-upstream.sh')
        self.assertIn(b'DRAFTER_NAME="qwen38-flash-next-drafter-r2-ht4.hgn"', upstream)
        self.assertIn(b'case "${HALOGEN_CONC_MODE:-}" in', upstream)
        self.assertIn(b'"") conc_mode_auto; return 0 ;;', upstream)
        self.assertIn(b'CONC_AUTO=1', upstream)
        self.assertIn(b'the default; HALOGEN_CONC_MODE=0 turns it off', upstream)
        self.assertIn(b'${HALOGEN_HT_TG_DEC:-}', upstream)
        self.assertIn(b'${HALOGEN_TICK_TG:-}', upstream)
        self.assertIn(b'case "${HALOGEN_MTP:-1}" in 0*)', upstream)
        self.assertIn(b'*.gguf|*/qwen38-flash-next-w4b.hgn)', upstream)
        self.assertIn(b'export HALOGEN_CONC_MODE=0', upstream)
        self.assertIn(b'is_gguf || drafter_head', upstream)
        self.assertIn(b'export HALOGEN_CK_OVERLAY="$f"', upstream)
        self.assertIn(b'export HALOGEN_MTP_GATE_RULE="${HALOGEN_MTP_GATE_RULE:-cost}"', upstream)
        for name in ('HALOGEN_CONC_MODE', 'HALOGEN_CONC_HEADS', 'HALOGEN_TICK_ONE',
                     'HALOGEN_HT_TG_RING', 'HALOGEN_CONC_SHAPE',
                     'HALOGEN_JHEAD_LAST_ROW', 'HALOGEN_HT_INT'):
            self.assertNotIn("'" + name + "'", service)
        release = json.loads((ROOT / 'profiles/release.json').read_text())
        self.assertEqual(release['service']['windows_admission_physical_gib'], 30)
        self.assertEqual(release['service']['windows_admission_commit_gib'], 124)
        self.assertEqual(release['service']['windows_runtime_physical_gib'], 18)
        self.assertEqual(release['service']['windows_runtime_commit_gib'], 18)
        self.assertFalse(release['actual_runtime_providers']['qualified'])
        self.assertFalse(release['cpu_image_provider_binding_qualified'])
        self.assertFalse(release['actual_engine_provider_binding_qualified'])

if __name__ == '__main__': unittest.main()
