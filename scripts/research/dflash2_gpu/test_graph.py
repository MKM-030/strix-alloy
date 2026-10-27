"""Explicit synthetic CPU source-parity checks; no real weights or devices."""
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    if __package__:
        from . import graph as ops
    else:
        import graph as ops
except ModuleNotFoundError:
    ops = None


class Passive(unittest.TestCase):
    def test_explicit_graph_exists(self):
        self.assertIsNotNone(ops, 'Explicit persistent GPU-capable tensor graph missing')

    @unittest.skipIf(ops is None, 'component absent')
    def test_namespace_import_does_not_import_torch(self):
        code = "import sys; from scripts.research.dflash2_gpu import graph; assert 'torch' not in sys.modules"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipIf(ops is None, 'component absent')
class Numerical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from scripts.research.dflash2_reference import backbone
        cls.t = torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.reference = backbone
        cls.g = torch.Generator(device='cpu').manual_seed(261026)
        cls.weights = {}
        for key, shape in backbone.LAYER_SHAPES.items():
            if key.endswith('base_kernel'):
                value = torch.randn(shape, generator=cls.g, device='cpu') * .01
                value[:, 0] += 1
            elif len(shape) == 1:
                value = torch.linspace(.8, 1.2, shape[0], device='cpu')
            else:
                value = torch.randn(shape, generator=cls.g, device='cpu') * .008
            cls.weights[key] = value

    def inputs(self, block, dtype):
        t = self.t
        x = (t.randn((block, 2560), generator=self.g, device='cpu') * .1).to(dtype)
        residual = (t.randn((block, 2560), generator=self.g, device='cpu') * .2).to(dtype)
        k = (t.randn((8, 8, 128), generator=self.g, device='cpu') * .1).to(dtype)
        v = (t.randn((8, 8, 128), generator=self.g, device='cpu') * .1).to(dtype)
        return x, residual, k, v

    def test_owned_packed_layer_matches_frozen_source_first_and_later_residual(self):
        for dtype in (self.t.float32, self.t.bfloat16):
            w = {n: v.to(dtype) for n, v in self.weights.items()}
            layer = ops.QueryLayer.from_cpu(w, device='cpu')
            for block in (4, 8):
                x, r, k, v = self.inputs(block, dtype)
                layout = layer.layout(prefix_tokens=8, context_rows=8, block_size=block)
                for residual in (None, r):
                    actual = layer.forward(x, residual, k, v, layout)
                    expected = self.reference.layer_forward(x, residual, self.t.arange(8, 8 + block), k, v,
                        self.t.arange(8), w, block_size=block)
                    for a, e in zip(actual, expected):
                        self.t.testing.assert_close(a, e, rtol=0, atol=0)
                self.assertEqual(tuple(actual[0].shape), (block, 2560))

    def test_owned_layer_storage_ignores_later_source_mutation(self):
        w = {n: v.to(self.t.bfloat16) for n, v in self.weights.items()}
        layer = ops.QueryLayer.from_cpu(w, device='cpu')
        x, r, k, v = self.inputs(4, self.t.bfloat16)
        layout = layer.layout(prefix_tokens=8, context_rows=8, block_size=4)
        before = layer.forward(x, r, k, v, layout)
        w['self_attn.q_proj.weight'].fill_(999)
        after = layer.forward(x, r, k, v, layout)
        for a, b in zip(before, after):
            self.t.testing.assert_close(a, b, rtol=0, atol=0)

    def test_five_layer_body_and_final_norm_match_frozen_reference(self):
        dtype = self.t.bfloat16
        w = {n: v.to(dtype) for n, v in self.weights.items()}
        layer = ops.QueryLayer.from_cpu(w, device='cpu')
        norm = self.t.linspace(.6, 1.3, 2560, device='cpu').to(dtype)
        body = ops.QueryBackbone.from_owned_layers((layer,) * 5, norm)
        for block in (4, 8):
            x, _, k, v = self.inputs(block, dtype)
            ck = k.unsqueeze(0).expand(5, -1, -1, -1)
            cv = v.unsqueeze(0).expand(5, -1, -1, -1)
            context = body.bind_context(ck, cv, start_position=0)
            actual = body.forward(x, context, prefix_tokens=8)
            weights = {f'layers.{i}.{name}': value for i in range(5) for name, value in w.items()}
            weights['norm.weight'] = norm
            expected = self.reference.query_block(x, self.t.arange(8, 8 + block), ck, cv, self.t.arange(8), weights, block_size=block)
            self.t.testing.assert_close(actual, expected, rtol=0, atol=0)

    def test_no_host_scalar_validation_inside_tensor_critical_path(self):
        # A real tensor execution under a poisoned scalar conversion catches a
        # regression to isfinite().all()/item()/bool(tensor) in each kernel.
        t = self.t
        w = {n: v.to(t.bfloat16) for n, v in self.weights.items()}
        layer = ops.QueryLayer.from_cpu(w, device='cpu')
        x, r, k, v = self.inputs(4, t.bfloat16)
        layout = layer.layout(prefix_tokens=8, context_rows=8, block_size=4)
        original_bool, original_item = t.Tensor.__bool__, t.Tensor.item
        def forbidden(*args, **kwargs):
            raise AssertionError('Host scalar synchronization in critical tensor path')
        try:
            t.Tensor.__bool__ = forbidden
            t.Tensor.item = forbidden
            result = layer.forward(x, r, k, v, layout)
        finally:
            t.Tensor.__bool__, t.Tensor.item = original_bool, original_item
        self.assertEqual(result[0].shape, x.shape)

    def test_bad_startup_weights_and_incomplete_context_decline(self):
        w = {n: v.to(self.t.bfloat16) for n, v in self.weights.items()}
        bad = dict(w)
        del bad['mlp.up_proj.weight']
        with self.assertRaises(ValueError):
            ops.QueryLayer.from_cpu(bad, device='cpu')
        layer = ops.QueryLayer.from_cpu(w, device='cpu')
        for kwargs in (dict(prefix_tokens=260000, context_rows=8, block_size=4),
                       dict(prefix_tokens=1, context_rows=0, block_size=4),
                       dict(prefix_tokens=0, context_rows=0, block_size=3)):
            with self.assertRaises(ValueError):
                layer.layout(**kwargs)

    def test_batched_candidate_keeps_all_rows_visible_through_block_end(self):
        # Zero Q/K produce exact uniform attention. A nonzero LAST query V
        # must affect the FIRST query, independently of its own RoPE position.
        # This checks the actual common noncausal author window without claiming
        # random BF16/GPU bit parity for a different SDPA implementation.
        t = self.t
        for dtype in (t.float32, t.bfloat16):
            weights = {name: t.zeros(shape, device='cpu', dtype=dtype) for name, shape in ops.LAYER_SHAPES.items()}
            weights['self_attn.q_norm.weight'].fill_(1)
            weights['self_attn.k_norm.weight'].fill_(1)
            weights['self_attn.v_proj.weight'][0, 0] = 1
            weights['self_attn.o_proj.weight'][0, 0] = 1
            rowwise = ops.QueryLayer.from_cpu(weights, device='cpu')
            batched = ops.QueryLayer.from_cpu(weights, device='cpu', batched_attention=True)
            for block in (4, 8):
                hidden = t.zeros((block, 2560), device='cpu', dtype=dtype)
                hidden[-1, 0] = block
                empty = t.empty((0, 8, 128), device='cpu', dtype=dtype)
                layout = rowwise.layout(prefix_tokens=0, context_rows=0, block_size=block)
                original = rowwise._attention(hidden, empty, empty, layout)
                candidate = batched._attention(hidden, empty, empty, layout)
                t.testing.assert_close(candidate, original, rtol=0, atol=0)
                self.assertEqual(float(candidate[0, 0]), 1.)


if __name__ == '__main__':
    if '--run-cpu' in sys.argv:
        sys.argv.remove('--run-cpu')
        unittest.main(verbosity=2)
    else:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Passive))
        raise SystemExit(not result.wasSuccessful())
