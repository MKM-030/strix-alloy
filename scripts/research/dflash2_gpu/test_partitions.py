"""Synthetic CPU parity for context/head/selector/full81 composition only."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.research.dflash2_gpu import graph, partitions, producer


class Passive(unittest.TestCase):
    def test_all_imports_are_torch_passive(self):
        code = 'import sys;from scripts.research.dflash2_gpu import graph,partitions,producer;assert "torch" not in sys.modules'
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class Numerical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from scripts.research.dflash2_reference import context_kv, proposal, backbone
        cls.t, cls.context_ref, cls.proposal_ref, cls.body_ref = torch, context_kv, proposal, backbone
        torch.set_num_threads(1)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.g = torch.Generator(device='cpu').manual_seed(102618)
        cls.w = {name: torch.zeros(shape, device='cpu', dtype=torch.bfloat16) for name, shape in graph.LAYER_SHAPES.items()}
        for name, value in cls.w.items():
            if name.endswith('base_kernel'):
                value[:, 0] = 1
            elif len(value.shape) == 1:
                value.copy_(torch.linspace(.8, 1.2, value.numel(), device='cpu'))
        for name in ('self_attn.k_proj.weight', 'self_attn.v_proj.weight'):
            cls.w[name].copy_(torch.randn(cls.w[name].shape, generator=cls.g, device='cpu') * .008)
        cls.layer = graph.QueryLayer.from_cpu(cls.w, device='cpu')
        cls.final_norm = torch.linspace(.7, 1.1, 2560, device='cpu').bfloat16()
        cls.body = graph.QueryBackbone.from_owned_layers((cls.layer,) * 5, cls.final_norm)
        cls.context_weights = {
            'fc.weight': (torch.randn((2560, 12800), generator=cls.g, device='cpu') * .008).bfloat16(),
            'hidden_norm.weight': torch.linspace(.8, 1.2, 2560, device='cpu').bfloat16()}
        cls.context = partitions.ContextGraph.from_owned_body(cls.body, cls.context_weights)
        cls.head = (torch.randn((32, 2560), generator=cls.g, device='cpu') * .08).bfloat16()
        cls.sw = dict(zip(partitions.SELECTOR_KEYS,
            ((torch.randn(shape, generator=cls.g, device='cpu') * .08).bfloat16()
             for shape in ((256, 2560), (32, 256), (32, 256)))))
        cls.selector = partitions.ProposalGraph.from_cpu(cls.sw, cls.head, device='cpu', org_vocab_size=24)

    def context_expected(self, x, start):
        weights = dict(self.context_weights)
        for layer in range(5):
            for suffix in ('k_proj.weight', 'v_proj.weight', 'k_norm.weight'):
                weights[f'layers.{layer}.self_attn.{suffix}'] = self.w['self_attn.' + suffix]
        owner = self.context_ref.OwnerMetadata(b'a' * 32, b'b' * 32, b'c' * 32, b'd' * 32, 1, 1)
        result = self.context_ref.prepare_context(x, self.t.arange(start, start + x.shape[0]), weights, owner=owner)
        return result.k, result.v

    def test_context_17_tensor_equations_and_absolute_rope_match_frozen_source(self):
        for start in (0, 259992):
            x = (self.t.randn((8, 12800), generator=self.g, device='cpu') * .1).bfloat16()
            actual = self.context.prepare(x, start_position=start)
            expected = self.context_expected(x, start)
            for a, e in zip(actual.export_copies(), expected):
                self.t.testing.assert_close(a, e, rtol=0, atol=0)

    def test_full_dense_head_and_learned_greedy_selector_match_actual_source_reference(self):
        anchor = self.t.tensor([3], dtype=self.t.int64, device='cpu')
        for block in (4, 8):
            hidden = (self.t.randn((block, 2560), generator=self.g, device='cpu') * .1).bfloat16()
            actual = self.selector.propose(hidden, anchor)
            expected = self.proposal_ref.propose_greedy(hidden, anchor, self.head, self.sw, block_size=block, org_vocab_size=24)
            for name in ('tokens', 'candidate_ids', 'unary_logits', 'edge_scores', 'q_rows', 'path_indices'):
                self.t.testing.assert_close(getattr(actual, name), getattr(expected, name), rtol=0, atol=0)

    def test_context_and_selector_tensor_paths_do_not_read_host_scalars(self):
        t = self.t
        x = (t.randn((8, 12800), generator=self.g, device='cpu') * .1).bfloat16()
        hidden = (t.randn((4, 2560), generator=self.g, device='cpu') * .1).bfloat16()
        anchor = t.tensor([3], dtype=t.int64, device='cpu')
        original_bool, original_item = t.Tensor.__bool__, t.Tensor.item
        def forbidden(*args, **kwargs):
            raise AssertionError('Host scalar read inside private tensor graph')
        try:
            t.Tensor.__bool__, t.Tensor.item = forbidden, forbidden
            context = self.context.prepare(x, start_position=0)
            result = self.selector.propose(hidden, anchor)
        finally:
            t.Tensor.__bool__, t.Tensor.item = original_bool, original_item
        self.assertEqual(context.rows, 8)
        self.assertEqual(tuple(result.tokens.shape), (1, 3))

    def test_exact81_composite_routes_real_width_blocks_to_private_proposals(self):
        weights = {f'layers.{i}.{name}': value for i in range(5) for name, value in self.w.items()}
        weights.update(self.context_weights)
        weights.update(self.sw)
        weights['norm.weight'] = self.final_norm
        self.assertEqual(len(weights), 81)
        complete = producer.DFlashGraph.from_cpu(weights, self.head, device='cpu', org_vocab_size=24)
        x = (self.t.randn((8, 12800), generator=self.g, device='cpu') * .1).bfloat16()
        prepared = complete.context.prepare(x, start_position=0)
        embeds = (self.t.randn((4, 2560), generator=self.g, device='cpu') * .1).bfloat16()
        anchor = self.t.tensor([3], dtype=self.t.int64, device='cpu')
        actual = complete.propose(embeds, prepared, anchor, prefix_tokens=8)
        k, v = self.context_expected(x, 0)
        body_weights = {name: value for name, value in weights.items() if name.startswith('layers.') or name == 'norm.weight'}
        hidden = self.body_ref.query_block(embeds, self.t.arange(8, 12), k, v, self.t.arange(8), body_weights, block_size=4)
        expected = self.proposal_ref.propose_greedy(hidden, anchor, self.head, self.sw, block_size=4, org_vocab_size=24)
        self.t.testing.assert_close(actual.tokens, expected.tokens, rtol=0, atol=0)
        self.t.testing.assert_close(actual.edge_scores, expected.edge_scores, rtol=0, atol=0)

    def test_staged_owned_parts_share_storage_and_reject_foreign_or_mixed_parts(self):
        complete = producer.DFlashGraph.from_owned_parts(self.body, self.context, self.selector)
        self.assertIs(complete.body, self.body)
        self.assertIs(complete.context, self.context)
        self.assertIs(complete.selector, self.selector)
        x = (self.t.randn((8, 12800), generator=self.g, device='cpu') * .1).bfloat16()
        prepared = self.context.prepare(x, start_position=0)
        embeds = (self.t.randn((4, 2560), generator=self.g, device='cpu') * .1).bfloat16()
        anchor = self.t.tensor([3], dtype=self.t.int64, device='cpu')
        actual = complete.propose(embeds, prepared, anchor, prefix_tokens=8)
        expected = self.selector.propose(self.body.forward(embeds, prepared, prefix_tokens=8), anchor)
        self.t.testing.assert_close(actual.tokens, expected.tokens, rtol=0, atol=0)
        self.t.testing.assert_close(actual.edge_scores, expected.edge_scores, rtol=0, atol=0)
        other_body = graph.QueryBackbone.from_owned_layers((self.layer,) * 5, self.final_norm)
        with self.assertRaises(ValueError):
            producer.DFlashGraph.from_owned_parts(other_body, self.context, self.selector)
        fp32_selector = partitions.ProposalGraph.from_cpu({k: v.float() for k, v in self.sw.items()}, self.head,
            device='cpu', org_vocab_size=24)
        with self.assertRaises(ValueError):
            producer.DFlashGraph.from_owned_parts(self.body, self.context, fp32_selector)
        for parts in ((None, self.context, self.selector), (self.body, None, self.selector), (self.body, self.context, None)):
            with self.assertRaises(TypeError):
                producer.DFlashGraph.from_owned_parts(*parts)


if __name__ == '__main__':
    if '--run-cpu' in sys.argv:
        sys.argv.remove('--run-cpu')
        unittest.main(verbosity=2)
    else:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Passive))
        raise SystemExit(not result.wasSuccessful())
