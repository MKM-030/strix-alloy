"""Explicit one-thread CPU source-equation checks; default prints a passive plan."""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
if __package__:
    from . import contract, math_ops as ops, source_oracle
else:
    import contract
    import math_ops as ops
    import source_oracle

class ImportTests(unittest.TestCase):
    def test_root_namespace_import_with_foreign_module_names_is_passive(self):
        repository = Path(__file__).resolve().parents[3]
        code = '''import sys,types
sys.modules['contract'] = types.ModuleType('contract')
sys.modules['source_oracle'] = types.ModuleType('source_oracle')
from scripts.research.dflash2_reference import math_ops,contract,source_oracle
assert math_ops.WIDTH == 2560
assert contract.verify_saved_contract()['tensors'] == 81
assert source_oracle.extracted_tree().body
assert 'torch' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=repository,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_imports_and_extraction_do_not_import_torch(self):
        self.assertNotIn('torch', sys.modules)
        tree = source_oracle.extracted_tree()
        self.assertEqual([n.name for n in tree.body], list(source_oracle.NAMES) + list(source_oracle.CLASSES))
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)))

    def test_actual_model_header_and_source_pins(self):
        result = contract.verify_saved_contract()
        self.assertEqual(result['tensors'], 81)
        self.assertEqual(result['parameters'], 603065600)
        self.assertFalse(result['model_payload_opened'])

    def test_oracle_rejects_foreign_source_before_execution(self):
        old = source_oracle.SOURCE
        try:
            with tempfile.TemporaryDirectory(prefix='dflash2-source-test-') as folder:
                foreign = Path(folder) / 'foreign.py'; foreign.write_text('raise RuntimeError("must not execute")')
                source_oracle.SOURCE = foreign
                with self.assertRaisesRegex(ValueError, 'Pinned SGLang'):source_oracle.extracted_tree()
        finally:source_oracle.SOURCE = old

class MathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.t = torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.oracle = source_oracle.source_functions()
        cls.generator = torch.Generator(device='cpu').manual_seed(19261)

    def rand(self, shape, dtype, scale=.1):
        return (self.t.randn(shape, generator=self.generator, device='cpu', dtype=self.t.float32) * scale).to(dtype)

    def same(self, actual, expected):
        self.assertEqual(actual.device.type, 'cpu')
        self.assertEqual(actual.dtype, expected.dtype)
        self.t.testing.assert_close(actual, expected, rtol=0, atol=0)

    def conv_fixture(self, dtype, block=4, strided=False):
        rows = 2 * block
        if strided:
            x = self.rand((rows, 5120), dtype)[:, ::2]
            delta = self.rand((rows, 2, 320), dtype)[:, :, ::2]
            base = self.rand((2, 5120), dtype)[:, ::2]
            self.assertFalse(x.is_contiguous())
        else:
            x = self.rand((rows, 2560), dtype)
            delta = self.rand((rows, 2, 160), dtype)
            base = self.rand((2, 2560), dtype)
        return x, delta, base

    def test_conv_matches_source_real_width_both_blocks_and_dtypes(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            for block in (4, 8):
                with self.subTest(dtype=dtype, block=block):
                    x, delta, base = self.conv_fixture(dtype, block)
                    expected = self.oracle['_grouped_conv'](x, delta, base, block, 160, 16, 2)
                    self.same(ops.grouped_conv(x, delta, base, block, 160, 16, 2), expected)

    def test_conv_strided_matches_source(self):
        x, delta, base = self.conv_fixture(self.t.bfloat16, 8, True)
        expected = self.oracle['_grouped_conv'](x, delta, base, 8, 160, 16, 2)
        self.same(ops.grouped_conv(x, delta, base, 8, 160, 16, 2), expected)

    def test_conv_block_boundary_has_no_previous_block_leakage(self):
        for block in (4, 8):
            x = self.t.zeros((2 * block, 2560), dtype=self.t.float32, device='cpu')
            x[block-1] = 7; x[block] = 3
            delta = self.t.zeros((2 * block, 2, 160), dtype=x.dtype, device='cpu')
            base = self.t.ones((2, 2560), dtype=x.dtype, device='cpu')
            result = ops.grouped_conv(x, delta, base, block, 160, 16, 2)
            self.same(result[block], x[block])
            self.same(result[block+1], x[block])

    def test_prepare_finish_both_distinct_sides_and_materializations(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            for block in (4, 8):
                with self.subTest(dtype=dtype, block=block):
                    x = self.rand((2 * block, 2560), dtype)
                    projection = self.rand((640, 2560), dtype, .01)
                    base = self.rand((2, 2, 2560), dtype)
                    coefficients = self.t.nn.functional.linear(x, projection).reshape(2 * block, 2, 2, 160)
                    prepared, output_coefficients = ops.prepare_convolution(x, projection, base, block)
                    self.same(prepared, self.oracle['_grouped_conv'](x, coefficients[:, 0], base[0], block, 160, 16, 2))
                    self.same(output_coefficients, coefficients[:, 1])
                    sublayer = self.rand(x.shape, dtype)
                    self.same(ops.finish_convolution(sublayer, output_coefficients, base, block), self.oracle['_grouped_conv'](sublayer, coefficients[:, 1], base[1], block, 160, 16, 2))

    def test_prepare_finish_match_actual_source_class(self):
        self.assertIn('DFlashGroupedConv', self.oracle)
        for dtype in (self.t.float32, self.t.bfloat16):
            for block in (4, 8):
                x = self.rand((2 * block, 2560), dtype)
                projection = self.rand((640, 2560), dtype, .01)
                base = self.rand((2, 2, 2560), dtype)
                with self.t.device('cpu'):
                    oracle = self.oracle['DFlashGroupedConv'](2560, block, 2, 16).to(dtype=dtype, device='cpu')
                oracle.kernel_projection.weight.copy_(projection);oracle.base_kernel.copy_(base)
                expected, expected_coefficients = oracle.prepare(x)
                actual, coefficients = ops.prepare_convolution(x, projection, base, block)
                self.same(actual, expected); self.same(coefficients, expected_coefficients)
                output = self.rand(x.shape, dtype)
                self.same(ops.finish_convolution(output, coefficients, base, block), oracle.finish(output, expected_coefficients))

    def selector_fixture(self, dtype, strided=False):
        # 32 deterministic fixture IDs, actual trained rank256 and top16. No full model/table allocation.
        batch, slots, vocab, top_k = 2, 3, 32, 16
        table = self.rand((vocab, 512 if strided else 256), dtype)
        predecessor = table[:, ::2] if strided else table
        successor = self.rand((vocab, 256), dtype)
        ids = self.t.arange(batch * slots * top_k, dtype=self.t.int64, device='cpu').reshape(batch, slots, top_k) % vocab
        unary = self.rand((batch, slots, top_k), self.t.float32)
        hidden = self.rand((batch, slots, 256), dtype)
        anchors = self.t.tensor([4, 29], dtype=self.t.int64, device='cpu')
        return dict(predecessor_table=predecessor, successor_table=successor, candidate_ids=ids, unary_logits=unary, hidden=hidden, anchor_token_ids=anchors, top_k=top_k)

    def test_selector_edge_scores_match_source_and_anchor_contract(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            for strided in (False, True):
                kw = self.selector_fixture(dtype, strided)
                expected = self.oracle['_score_edges'](**kw)
                actual = ops.score_edges(**kw)
                self.same(actual, expected)
                # Initial edge uses the same verified anchor for every predecessor slot.
                self.same(actual[:, 0, 0], actual[:, 0, -1])
                self.assertEqual(actual.dtype, self.t.float32)

    def test_follow_maps_and_complete_greedy_selector_walk(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            kw = self.selector_fixture(dtype)
            scores = self.oracle['_score_edges'](**kw)
            maps = scores[:, 1:].argmax(-1)
            initial = scores[:, 0, 0].argmax(-1)
            path = ops.follow_maps(maps, initial, 2)
            self.same(path, self.oracle['_follow_maps'](maps, initial, 2))
            actual_ids = kw['candidate_ids'].gather(-1, path[..., None])[..., 0]
            expected_ids = []
            for b in range(2):
                index = int(initial[b]); row = [int(kw['candidate_ids'][b, 0, index])]
                for edge in range(2):
                    index = int(maps[b, edge, index]); row.append(int(kw['candidate_ids'][b, edge+1, index]))
                expected_ids.append(row)
            self.same(actual_ids, self.t.tensor(expected_ids, dtype=self.t.int64, device='cpu'))

    def test_follow_maps_zero_edges_and_strided(self):
        initial = self.t.tensor([15, 0], dtype=self.t.int64, device='cpu')
        maps = (self.t.arange(2 * 3 * 32, dtype=self.t.int64, device='cpu') % 16).reshape(2, 3, 32)[:, :, ::2]
        self.assertFalse(maps.is_contiguous())
        self.same(ops.follow_maps(maps, initial, 3), self.oracle['_follow_maps'](maps, initial, 3))
        self.same(ops.follow_maps(maps[:, :0], initial, 0), initial[:, None])

    def test_conv_rejects_wrong_geometry_shape_and_dtype(self):
        x, delta, base = self.conv_fixture(self.t.float32)
        bad = [(x[:, :-1], delta, base, 4, 160, 16, 2), (x, delta[:, :1], base, 4, 160, 16, 2), (x, delta, base, 4, 80, 32, 2), (x, delta, base, 3, 160, 16, 2), (x, delta.to(self.t.bfloat16), base, 4, 160, 16, 2), (x.to(self.t.int64), delta.to(self.t.int64), base.to(self.t.int64), 4, 160, 16, 2)]
        for args in bad:
            with self.subTest(shapes=[getattr(a, 'shape', a) for a in args]):
                with self.assertRaises((ValueError, TypeError)):ops.grouped_conv(*args)

    def test_prepare_finish_reject_wrong_shapes_or_dtypes(self):
        x, delta, _ = self.conv_fixture(self.t.float32)
        projection = self.t.zeros((640, 2560), dtype=x.dtype, device='cpu')
        base = self.t.zeros((2, 2, 2560), dtype=x.dtype, device='cpu')
        for weight in (projection[:-1], projection.to(self.t.bfloat16)):
            with self.assertRaises((ValueError, TypeError)):ops.prepare_convolution(x, weight, base, 4)
        with self.assertRaises((ValueError, TypeError)):ops.finish_convolution(x, delta[:, :, :-1], base, 4)
        with self.assertRaises((ValueError, TypeError)):ops.finish_convolution(x, delta, base[0], 4)

    def test_selector_rejects_bad_shapes_ids_and_dtypes(self):
        for key, change in [('hidden', lambda x:x[..., :-1]), ('candidate_ids', lambda x:x.float()), ('candidate_ids', lambda x:x+100), ('anchor_token_ids', lambda x:x-100), ('unary_logits', lambda x:x[..., :-1]), ('successor_table', lambda x:x.to(self.t.bfloat16))]:
            kw = self.selector_fixture(self.t.float32);kw[key] = change(kw[key])
            with self.subTest(key=key):
                with self.assertRaises((ValueError, TypeError)):ops.score_edges(**kw)

    def test_maps_reject_bad_shapes_dtypes_and_indices(self):
        maps = self.t.zeros((2, 2, 16), dtype=self.t.int64, device='cpu')
        initial = self.t.zeros((2,), dtype=self.t.int64, device='cpu')
        for args in ((maps.float(), initial, 2), (maps, initial.float(), 2), (maps, initial+16, 2), (maps+16, initial, 2), (maps, initial, 3), (maps, initial, -1)):
            with self.assertRaises((ValueError, TypeError)):ops.follow_maps(*args)

if __name__ == '__main__':
    if '--run-cpu' not in sys.argv:
        print(json.dumps(dict(prepared=True,executed=False,provider_calls=0,CPU_only=True,threads=1)))
    else:
        sys.argv.remove('--run-cpu');unittest.main(verbosity=2)
