"""Bounded host-router fixtures; no ONNX runtime or hardware initialization."""
import hashlib
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

import importlib

SCRIPT = Path(__file__).resolve().parents[1] / 'halogen_npu_routing_host.py'
sys.path.insert(0, str(SCRIPT.parent))


def supplied_logits():
    # Expert IDs deliberately differ from rank order: coefficients must follow IDs.
    ids = (511, 3, 250, 19, 41, 100, 99, 70, 2, 300)
    logits = np.full(512, -100, dtype=np.float32)
    for weight, expert in enumerate(ids, 1):
        logits[expert] = np.log(weight)
    return logits, ids


class HostRoutingTests(unittest.TestCase):
    def run_route(self, logits, *options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logits.json'
            path.write_text(json.dumps(logits.tolist()), encoding='utf-8')
            return subprocess.run([sys.executable, str(SCRIPT), '--logits', str(path), *options],
                                  capture_output=True, text=True, timeout=20)

    def test_cli_packs_supplied_scores_into_canonical_graph_order(self):
        logits, ranked_ids = supplied_logits()
        result = self.run_route(logits, '--coefficient-dtype', 'float32')
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet['selected_experts'], sorted(ranked_ids))
        self.assertEqual(packet['routing_shape'], [10, 1, 1])
        expected = [float(ranked_ids.index(expert) + 1) / 55 for expert in sorted(ranked_ids)]
        np.testing.assert_allclose(np.asarray(packet['routing_weights']).reshape(10), expected,
                                   rtol=2e-6, atol=1e-8)
        self.assertFalse(packet['halogen_equivalence_qualified'])

    def test_cli_bfloat16_coefficients_are_rounded_before_fp32_graph_pack(self):
        logits = np.full(512, -100, dtype=np.float32)
        logits[:10] = 0  # Ten equal selected scores, with an unambiguous boundary.
        result = self.run_route(logits)
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet['coefficient_dtype'], 'bfloat16')
        self.assertEqual(np.asarray(packet['routing_weights']).reshape(10).tolist(),
                         [0.10009765625] * 10)

    def test_cli_refuses_boundary_ties_and_nonfinite_or_wrong_shape_scores(self):
        cases = [(np.zeros(512, dtype=np.float32), 'boundary tie'),
                 (np.zeros(511, dtype=np.float32), '512'),
                 (np.full(512, np.nan, dtype=np.float32), 'finite')]
        for logits, reason in cases:
            with self.subTest(reason=reason):
                result = self.run_route(logits)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)

    def test_cli_bounds_actual_read_when_file_grows_before_open(self):
        from halogen_npu_routing_host import main
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logits.json'
            path.write_text(json.dumps([0] * 512), encoding='utf-8')
            original_open = Path.open
            reads = []

            class TrackedReader:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, *unused):
                    self.stream.close()

                def read(self, size=-1):
                    reads.append(size)
                    return self.stream.read(size)

            def grown_open(chosen, *args, **kwargs):
                if chosen != path:
                    return original_open(chosen, *args, **kwargs)
                # Replace the small file with a real oversized, parseable JSON file.
                with io.open(path, 'w', encoding='utf-8') as output:
                    output.write(' ' * 70_000 + json.dumps([0] * 512))
                return TrackedReader(original_open(chosen, *args, **kwargs))

            stderr = io.StringIO()
            with mock.patch.object(Path, 'open', grown_open), mock.patch.object(sys, 'argv',
                    ['router', '--logits', str(path)]), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn('64 KiB', stderr.getvalue())
            self.assertTrue(reads)
            self.assertTrue(all(0 < size <= 64 * 1024 + 1 for size in reads))

    def test_cli_refuses_dispatch_to_graph_with_different_expert_ids(self):
        logits, _ = supplied_logits()
        result = self.run_route(logits, '--graph-experts', '0,1,2,3,4,5,6,7,8,9')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('graph miss', result.stderr)

    def test_cli_reorders_coefficients_to_existing_graph_order(self):
        logits, ids = supplied_logits()
        result = self.run_route(logits, '--coefficient-dtype', 'float32',
                                '--graph-experts', ','.join(map(str, reversed(ids))))
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet['graph_experts'], list(reversed(ids)))
        np.testing.assert_allclose(np.asarray(packet['routing_weights']).reshape(10),
                                   np.arange(10, 0, -1) / 55, rtol=2e-6, atol=1e-8)

    def test_cache_key_reuses_only_canonical_ids_and_identical_runtime_identities(self):
        helper = importlib.import_module('halogen_npu_routing_host')
        key_fn = getattr(helper, 'graph_cache_key', None)
        self.assertTrue(callable(key_fn), 'content-addressed graph cache key is missing')
        identities = {'checkpoint_manifest_sha256': 'a' * 64, 'builder_sha256': 'b' * 64,
                      'provider_manifest_sha256': 'c' * 64, 'runtime_config_sha256': 'd' * 64}
        baseline = key_fn(tuple(range(10)), **identities)
        self.assertEqual(baseline, key_fn(tuple(reversed(range(10))), **identities))
        self.assertNotEqual(baseline, key_fn(tuple(range(1, 11)), **identities))
        for field in identities:
            changed = dict(identities, **{field: 'e' * 64})
            self.assertNotEqual(baseline, key_fn(tuple(range(10)), **changed))
        with self.assertRaises(ValueError):
            key_fn(tuple(range(10)), **dict(identities, provider_manifest_sha256='bad'))

    def test_admission_preserves_physical_and_commit_reserve_with_unknown_overhead_refused(self):
        helper = importlib.import_module('halogen_npu_routing_host')
        admit = getattr(helper, 'memory_admission', None)
        self.assertTrue(callable(admit), 'memory admission gate is missing')
        gib = 1 << 30
        exact = admit(20 * gib, 20 * gib, 1 * gib, 1 * gib)
        self.assertTrue(exact['admitted'])
        self.assertEqual(exact['physical_remaining_bytes'], 18 * gib)
        self.assertFalse(admit(20 * gib - 1, 30 * gib, gib, gib)['admitted'])
        self.assertFalse(admit(30 * gib, 20 * gib - 1, gib, gib)['admitted'])
        self.assertFalse(admit(30 * gib, 30 * gib, None, gib)['admitted'])
        self.assertFalse(admit(30 * gib, 30 * gib, gib, None)['admitted'])
        with self.assertRaises(ValueError):
            admit(30 * gib, 30 * gib, -1, gib)
        with self.assertRaises(ValueError):
            admit(30 * gib, 30 * gib, 1, gib)

    def test_non_normalized_mass_and_bfloat16_ties_round_to_even(self):
        from halogen_npu_routing_host import route_top10, _bf16_round
        logits = np.full(512, np.log(2), dtype=np.float32)
        logits[:10] = np.log(4)
        route = route_top10(logits, normalize=False, coefficient_dtype='float32')
        np.testing.assert_allclose(route.coefficients, [1 / 261] * 10, rtol=2e-6)
        self.assertAlmostEqual(route.selected_probability_mass, 10 / 261, places=7)
        # Midpoint between BF16 values: even mantissa retained, odd mantissa rounded up.
        actual = _bf16_round(np.array([1.00390625, 1.01171875], dtype=np.float32))
        self.assertEqual(actual.tolist(), [1.0, 1.015625])

    def test_small_router_payload_checks_manifest_and_payload_before_bf16_decode(self):
        helper = importlib.import_module('halogen_npu_routing_host')
        load = getattr(helper, 'load_router_bf16', None)
        self.assertTrue(callable(load), 'bounded BF16 router reader is missing')
        raw = np.zeros((512, 2560), dtype='<u2')
        raw[0, :3] = [0x3f80, 0xc000, 0x3f00]  # 1, -2, 0.5 in BF16.
        payload = raw.tobytes()
        entry = {'name': 'mtp.layers.0.mlp.gate.weight', 'store': 0, 'variant': 0,
                 'rank': 2, 'dims': [512, 2560], 'size': len(payload),
                 'sha256': hashlib.sha256(payload).hexdigest(),
                 'xor32': int(np.bitwise_xor.reduce(np.frombuffer(payload, dtype='<u4')))}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'manifest.json'
            binary = root / 'router.bin'
            binary.write_bytes(payload)
            manifest.write_text(json.dumps({'identity': 'qwen3.8-flash-next', 'version': 2,
                                             'entries': [entry]}), encoding='utf-8')
            expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
            weights = load(manifest, binary, expected_manifest_sha256=expected)
            self.assertEqual(weights.dtype, np.float32)
            self.assertEqual(weights.shape, (512, 2560))
            self.assertEqual(weights[0, :3].tolist(), [1.0, -2.0, 0.5])
            with self.assertRaisesRegex(ValueError, 'manifest SHA'):
                load(manifest, binary, expected_manifest_sha256='f' * 64)
            binary.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'payload size'):
                load(manifest, binary, expected_manifest_sha256=expected)
            binary.write_bytes(b'\x01\x00' + payload[2:])
            with self.assertRaisesRegex(ValueError, 'payload SHA'):
                load(manifest, binary, expected_manifest_sha256=expected)

    def test_router_matvec_uses_finite_one_token_hidden_input_and_full_expert_width(self):
        helper = importlib.import_module('halogen_npu_routing_host')
        matvec = getattr(helper, 'router_logits_fp32', None)
        self.assertTrue(callable(matvec), 'FP32 router reference is missing')
        weights = np.zeros((512, 2560), dtype=np.float32)
        weights[2, :2] = [1.0, -2.0]
        weights[511, :2] = [-1.0, 2.0]
        hidden = np.zeros(2560, dtype=np.float32)
        hidden[:2] = [3.0, 4.0]
        actual = matvec(hidden, weights)
        self.assertEqual(actual.shape, (512,))
        self.assertEqual(actual.dtype, np.float32)
        self.assertEqual(actual[2], -5.0)
        self.assertEqual(actual[511], 5.0)
        with self.assertRaises(ValueError):
            matvec(np.zeros(10240), weights)
        hidden[0] = np.nan
        with self.assertRaises(ValueError):
            matvec(hidden, weights)


if __name__ == '__main__':
    unittest.main()
