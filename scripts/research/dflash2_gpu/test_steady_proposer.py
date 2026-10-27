"""Explicit, bounded CPU fixtures; substituted body routing is not model parity.

No full QueryLayer weights, model payloads or accelerator calls are used.
The weight-free layout fixture calls the original QueryLayer.layout verbatim.
"""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = Path(__file__).with_name('steady_proposer.py')


class Passive(unittest.TestCase):
    def test_module_exists_and_import_is_passive(self):
        self.assertTrue(MODULE.is_file(), 'Steady-window private proposer is missing')
        code = ('import sys;from scripts.research.dflash2_gpu import steady_proposer;'
                'assert "torch" not in sys.modules')
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless('--run-cpu' in sys.argv and MODULE.is_file(), 'Explicit bounded CPU fixtures only')
class SteadyCPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from scripts.research.dflash2_gpu.graph import QueryLayer, QueryBackbone, PrivateContext
        from scripts.research.dflash2_gpu.partitions import ContextGraph, ProposalGraph, PrivateProposal
        from scripts.research.dflash2_gpu.producer import DFlashGraph
        from scripts.research.dflash2_gpu.steady_proposer import SteadyProposer
        torch.set_num_threads(1)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.t, cls.QueryLayer, cls.QueryBackbone = torch, QueryLayer, QueryBackbone
        cls.PrivateContext, cls.ContextGraph, cls.ProposalGraph = PrivateContext, ContextGraph, ProposalGraph
        cls.PrivateProposal, cls.DFlashGraph, cls.SteadyProposer = PrivateProposal, DFlashGraph, SteadyProposer

    def layer_metadata(self, dtype):
        layer = self.QueryLayer()
        layer._t, layer.dtype, layer.device = self.t, dtype, self.t.device('cpu')
        layer._frequency = 1.0 / (10000. ** (self.t.arange(0, 128, 2, device='cpu', dtype=self.t.float32) / 128))
        return layer

    def routed_graph(self, dtype=None):
        """Substitute five costly layer forwards and selector, keep real norm/layout.

        This exercises ordering, arguments and persistent input state only. It
        cannot establish trained-body/head parity, CUDA capture or performance.
        """
        t, dtype = self.t, dtype or self.t.bfloat16
        self.calls = []
        layers = []
        for index in range(5):
            layer = self.layer_metadata(dtype)
            def forward(hidden, residual, key, value, layout, index=index):
                self.calls.append((index, key, value, layout))
                return hidden + index + 1, hidden if residual is None else residual
            layer.forward = forward
            layers.append(layer)
        body = self.QueryBackbone._from_owned(tuple(layers), t.ones(2560, device='cpu', dtype=dtype))
        context, selector = self.ContextGraph(), self.ProposalGraph()
        context._body = body
        for part in (context, selector):
            part._t, part.dtype, part.device = t, dtype, t.device('cpu')
        def propose(hidden, anchor):
            block = hidden.shape[0]
            ids = anchor.reshape(1, 1, 1).expand(1, block - 1, 16)
            path = t.zeros((1, block - 1), dtype=t.int64, device='cpu')
            return self.PrivateProposal(anchor.view(1, 1).expand(1, block - 1), ids,
                                        hidden, hidden[:, :16], hidden[:, :16], path)
        selector.propose = propose
        return self.DFlashGraph.from_owned_parts(body, context, selector)

    def inputs(self, block, prefix=8192, *, dtype=None, marker=3):
        t, dtype = self.t, dtype or self.t.bfloat16
        rows = 2048 - block
        # Tiny source backing expanded to real metadata; no second full KV copy.
        key = t.full((5, 1, 1, 1), marker, dtype=dtype, device='cpu').expand(5, rows, 8, 128)
        value = t.full((5, 1, 1, 1), -marker, dtype=dtype, device='cpu').expand_as(key)
        embeds = t.arange(block * 2560, device='cpu', dtype=t.float32).remainder(17).to(dtype).view(block, 2560)
        return embeds, self.PrivateContext(key, value, prefix - rows)

    def prepare(self, wrapper, prefix=8192, anchor=7, marker=3):
        embeds, context = self.inputs(wrapper.block_size, prefix, marker=marker)
        wrapper.prepare(embeds, context, prefix_tokens=prefix, anchor_token_id=anchor)
        return embeds, context

    def test_layout_matches_original_exactly_at_advancing_boundary_and_high_positions(self):
        t = self.t
        from scripts.research.dflash2_gpu.steady_proposer import _steady_layout
        for dtype in (t.float32, t.bfloat16):
            layer = self.layer_metadata(dtype)
            for block in (4, 8):
                rows = 2048 - block
                offsets = t.arange(block, device='cpu', dtype=t.int64)
                prefix_scalar = t.empty((), device='cpu', dtype=t.int64)
                allow = t.ones((block, 2048), device='cpu', dtype=t.bool)
                previous = (offsets >= 1).view(-1, 1, 1)
                old_cos = None
                for prefix in dict.fromkeys((rows, 2044, 8192, 8193, 260000, 262144 - block)):
                    prefix_scalar.fill_(prefix)
                    actual = _steady_layout(layer, prefix_scalar, offsets, allow, previous)
                    expected = layer.layout(prefix_tokens=prefix, context_rows=rows, block_size=block)
                    for name in ('positions', 'cos', 'sin', 'allow_mask', 'previous_allowed'):
                        t.testing.assert_close(getattr(actual, name), getattr(expected, name), rtol=0, atol=0)
                    if old_cos is not None:
                        self.assertFalse(t.equal(old_cos, actual.cos), 'Advancing prefix must change RoPE')
                    old_cos = actual.cos.clone()

    def test_static_mask_stride_matches_original_expanded_row_layout(self):
        for block in (4, 8):
            with self.subTest(block=block):
                graph = self.routed_graph()
                wrapper = self.SteadyProposer.from_owned_graph(graph, block_size=block)
                try:
                    expected = graph.body._layers[0].layout(prefix_tokens=8192, context_rows=2048 - block,
                                                           block_size=block)
                    self.assertEqual(wrapper._allow.stride(), expected.allow_mask.stride())
                    self.t.testing.assert_close(wrapper._allow, expected.allow_mask, rtol=0, atol=0)
                finally:
                    wrapper.close()

    def test_owned_inputs_are_independent_reused_and_route_all_five_layers_then_norm(self):
        t = self.t
        graph = self.routed_graph()
        wrapper = self.SteadyProposer.from_owned_graph(graph, block_size=4)
        embeds, context = self.prepare(wrapper)
        storage = tuple(x.untyped_storage().data_ptr() for x in
                        (wrapper._embeds, wrapper._key, wrapper._value, wrapper._anchor, wrapper._prefix))
        expected = embeds.float() * 2 + 15
        expected = (expected * t.rsqrt(expected.pow(2).mean(-1, keepdim=True) + 1e-6)).to(t.bfloat16)
        embeds.fill_(99)
        context._key._base.fill_(99)
        output = wrapper.eager()
        t.testing.assert_close(output.unary_logits, expected, rtol=0, atol=0)
        self.assertEqual([call[0] for call in self.calls], [0, 1, 2, 3, 4])
        for index, key, value, layout in self.calls:
            self.assertEqual(key.shape, (2044, 8, 128))
            self.assertEqual(key[0, 0, 0], 3)
            self.assertEqual(value[-1, 0, 0], -3)
            self.assertEqual(layout.positions.tolist(), [8192, 8193, 8194, 8195])
        self.prepare(wrapper, prefix=8193, anchor=11, marker=5)
        self.assertEqual(storage, tuple(x.untyped_storage().data_ptr() for x in
                                       (wrapper._embeds, wrapper._key, wrapper._value, wrapper._anchor, wrapper._prefix)))
        # The prior proposal aliases private input storage; callers must copy it
        # with completion/owner proof before preparing a later round.
        self.assertEqual(output.tokens[0, 0], 11)
        updated = wrapper.eager()
        self.assertEqual(updated.tokens[0, 0], 11)
        wrapper.close()

    def test_prepare_is_one_shot_and_bad_update_invalidates_prior_permission(self):
        wrapper = self.SteadyProposer.from_owned_graph(self.routed_graph(), block_size=4)
        with self.assertRaises(RuntimeError):
            wrapper.eager()
        self.prepare(wrapper)
        wrapper.eager()
        with self.assertRaises(RuntimeError):
            wrapper.eager()
        self.prepare(wrapper)
        embeds, context = self.inputs(4)
        with self.assertRaises(ValueError):
            wrapper.prepare(embeds, context, prefix_tokens=8192, anchor_token_id=248077)
        with self.assertRaises(RuntimeError):
            wrapper.eager()
        self.prepare(wrapper, prefix=260000)
        with self.assertRaises(RuntimeError):
            wrapper.replay()
        with self.assertRaises(RuntimeError):
            wrapper.eager()
        wrapper.close()
        for operation in (wrapper.eager, wrapper.replay, lambda: self.prepare(wrapper)):
            with self.assertRaises(RuntimeError):
                operation()

    def test_exact_context_chronology_lengths_dtype_and_host_ids_are_required(self):
        wrapper = self.SteadyProposer.from_owned_graph(self.routed_graph(), block_size=8)
        embeds, context = self.inputs(8)
        invalid = (
            (embeds, context, 2039, 7),
            (embeds, context, 262137, 7),
            (embeds, context, True, 7),
            (embeds, context, 8192, True),
            (embeds, context, 8192, -1),
            (embeds, context, 8192, self.t.tensor(7, device='cpu')),
            (embeds.float(), context, 8192, 7),
            (embeds, self.PrivateContext(context._key, context._value, context.start_position + 1), 8192, 7),
            (embeds, self.PrivateContext(context._key[:, :-1], context._value[:, :-1], context.start_position + 1), 8192, 7),
            (embeds, self.PrivateContext(context._key[:, :1].expand(5, 2048, 8, 128),
                                        context._value[:, :1].expand(5, 2048, 8, 128), 6144), 8192, 7),
        )
        for inp, ctx, prefix, anchor in invalid:
            self.prepare(wrapper)
            with self.assertRaises((TypeError, ValueError)):
                wrapper.prepare(inp, ctx, prefix_tokens=prefix, anchor_token_id=anchor)
            with self.assertRaises(RuntimeError):
                wrapper.eager()
        wrapper.close()

    def test_cpu_never_calls_cuda_and_tensor_paths_do_not_read_device_scalars(self):
        t = self.t
        def forbidden(*args, **kwargs):
            raise AssertionError('Forbidden CUDA/scalar read/host transfer')
        graph = self.routed_graph()
        with patch.object(t.cuda, 'is_available', forbidden), patch.object(t.cuda, 'stream', forbidden), \
             patch.object(t.cuda, 'current_stream', forbidden), patch.object(t.cuda, 'synchronize', forbidden), \
             patch.object(t.cuda, '_lazy_init', forbidden), \
             patch.object(t.cuda, 'CUDAGraph', forbidden), patch.object(t.Tensor, 'item', forbidden), \
             patch.object(t.Tensor, 'cpu', forbidden), patch.object(t.Tensor, 'numpy', forbidden), \
             patch.object(t.Tensor, 'tolist', forbidden), patch.object(t.Tensor, '__bool__', forbidden):
            wrapper = self.SteadyProposer.from_owned_graph(graph, block_size=4)
            self.prepare(wrapper)
            wrapper.eager()
            self.prepare(wrapper)
            with self.assertRaises(ValueError):
                wrapper.capture()
            wrapper.close()

    def test_cpu_rejects_stream_bad_factory_metadata_and_compute_failure_retires(self):
        graph = self.routed_graph()
        for block in (True, 3, 16):
            with self.assertRaises((TypeError, ValueError)):
                self.SteadyProposer.from_owned_graph(graph, block_size=block)
        with self.assertRaises(ValueError):
            self.SteadyProposer.from_owned_graph(graph, block_size=4, stream=object())
        with self.assertRaises(TypeError):
            self.SteadyProposer.from_owned_graph(object(), block_size=4)
        wrapper = self.SteadyProposer.from_owned_graph(graph, block_size=4)
        self.prepare(wrapper)
        def failed(*args):
            raise RuntimeError('Substituted compute failure')
        graph.body._layers[0].forward = failed
        with self.assertRaisesRegex(RuntimeError, 'Substituted compute failure'):
            wrapper.eager()
        with self.assertRaises(RuntimeError):
            self.prepare(wrapper)
        wrapper.close()

    def test_substituted_capture_lifecycle_uses_only_provided_stream_and_needs_fresh_prepare(self):
        """CPU orchestration double only; this does not run/qualify CUDA capture."""
        t = self.t
        wrapper = self.SteadyProposer.from_owned_graph(self.routed_graph(), block_size=4)
        events = []
        class Stream:
            def synchronize(self):
                events.append('stream drain')
        stream = Stream()
        @contextmanager
        def on_stream(selected):
            self.assertIs(selected, stream)
            events.append('enter provided stream')
            try:
                yield
            finally:
                events.append('leave provided stream')
        class Graph:
            def capture_begin(self):
                events.append('capture begin')
            def capture_end(self):
                events.append('capture end')
            def replay(self):
                events.append('replay')
        self.prepare(wrapper)
        # Substitute only GPU orchestration metadata/API. Tensors and all
        # arithmetic remain CPU, and no CUDA implementation is invoked.
        wrapper.device, wrapper._stream = t.device('cuda:0'), stream
        with patch.object(t.cuda, 'stream', on_stream), patch.object(t.cuda, 'CUDAGraph', Graph):
            self.assertIsNone(wrapper.capture(warmup=2))
            self.assertEqual(len(self.calls), 15)  # two warmups plus capture
            self.assertEqual(events, ['enter provided stream', 'stream drain', 'capture begin',
                                      'capture end', 'leave provided stream'])
            with self.assertRaises(RuntimeError):
                wrapper.replay()
            wrapper.device = t.device('cpu')
            self.prepare(wrapper, prefix=8193, anchor=13, marker=9)
            wrapper.device = t.device('cuda:0')
            first = wrapper.replay()
            self.assertEqual(first.tokens[0, 0], 13)
            self.assertEqual(events[-3:], ['enter provided stream', 'replay', 'leave provided stream'])
            with self.assertRaises(RuntimeError):
                wrapper.replay()
            wrapper.close()
            self.assertEqual(events[-1], 'stream drain')
            self.assertIsNone(wrapper._graph)

    def test_substituted_failed_capture_retires_and_failed_drain_retains_storage(self):
        """CPU control-flow double; no inference about real GPU capture cleanup."""
        t = self.t
        graph = self.routed_graph()
        wrapper = self.SteadyProposer.from_owned_graph(graph, block_size=4)
        self.prepare(wrapper)
        events = []
        class Stream:
            failed = False
            def synchronize(self):
                if self.failed:
                    raise RuntimeError('Substituted failed drain')
        stream = Stream()
        @contextmanager
        def on_stream(selected):
            self.assertIs(selected, stream)
            yield
        class Graph:
            def capture_begin(self):
                events.append('begin')
                def fail(*args):
                    raise RuntimeError('Substituted capture compute failure')
                graph.body._layers[0].forward = fail
            def capture_end(self):
                events.append('end')
        wrapper.device, wrapper._stream = t.device('cuda:0'), stream
        with patch.object(t.cuda, 'stream', on_stream), patch.object(t.cuda, 'CUDAGraph', Graph):
            with self.assertRaisesRegex(RuntimeError, 'capture compute failure'):
                wrapper.capture(warmup=1)
            self.assertEqual(events, ['begin', 'end'])
            with self.assertRaises(RuntimeError):
                wrapper.replay()
            stream.failed = True
            with self.assertRaisesRegex(RuntimeError, 'failed drain'):
                wrapper.close()
            self.assertIsNotNone(wrapper._key)
            self.assertIsNotNone(wrapper._graph)
            stream.failed = False
            wrapper.close()
            self.assertIsNone(wrapper._key)


if __name__ == '__main__':
    unittest.main(argv=[arg for arg in sys.argv if arg != '--run-cpu'])
