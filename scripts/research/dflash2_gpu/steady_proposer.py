"""Default-off private fixed-window proposer; importing this module is passive.

Only from_owned_graph allocates. No Torch import, device discovery, file access,
threads, serving hooks, native authority or proposal publication occurs here.
Existing QueryLayer arithmetic and the complete owned selector are unchanged.
"""
from contextlib import nullcontext
from .graph import Layout, PrivateContext, QueryBackbone, _metadata, _norm
from .partitions import ContextGraph, ProposalGraph
from .producer import DFlashGraph

WINDOW, MAX_POSITION, DEFINED_IDS = 2048, 262144, 248077


def _steady_layout(layer, prefix, offsets, allow_mask, previous_allowed):
    """Compute source-exact RoPE from an owned device scalar, never a host P.

    Layout.prefix_tokens holds that scalar as private metadata; layer.forward
    consumes only fixed shape fields and these computed tensors. In the long
    window every committed/query key is visible, so the mask is constant.
    """
    t = layer._t
    with t.inference_mode():
        positions = prefix + offsets
        angles = t.einsum('i,j -> ij', positions.float(), layer._frequency)
        cos = angles.cos().to(layer.dtype)[:, None, :]
        sin = angles.sin().to(layer.dtype)[:, None, :]
        block = offsets.shape[0]
        return Layout(prefix, WINDOW - block, block, positions, cos, sin, allow_mask, previous_allowed)


class SteadyProposer:
    """Owned inputs for one private B4/B8 long-window graph, serialized by caller.

    GPU callers supply one exact-device stream and establish model setup and
    producer dependencies before entry. All allocation, input copy, eager work,
    capture and replay are submitted on that stream. No stream discovery,
    device-wide synchronization, event or implicit cross-stream wait is added.

    prepare grants one local consumption by eager/capture/replay. This is not
    GEN, commit, readiness, completion or weight-provenance authentication.
    Outputs are borrowed mutable tensors, expiring on the next compute/update;
    native completion, immutable copies and publication belong to the caller.
    Calls must not race each other or other users of the borrowed model.
    """
    def __init__(self):
        raise TypeError('Use explicit SteadyProposer.from_owned_graph')

    @classmethod
    def from_owned_graph(cls, graph, *, block_size, stream=None):
        if type(graph) is not DFlashGraph:
            raise TypeError('Already-owned DFlashGraph required')
        body, context, selector = graph.body, graph.context, graph.selector
        if type(body) is not QueryBackbone or type(context) is not ContextGraph or type(selector) is not ProposalGraph:
            raise TypeError('Already-owned graph partitions required')
        if context._body is not body or any(part.device != body.device or part.dtype != body.dtype for part in (context, selector)):
            raise ValueError('Owned partition identity/device/dtype differs')
        if type(block_size) is not int or block_size not in (4, 8):
            raise ValueError('Exact block4/8 required')
        t, device, dtype = body._t, body.device, body.dtype
        if dtype not in (t.float32, t.bfloat16) or device.type not in ('cpu', 'cuda'):
            raise ValueError('Owned FP32/BF16 CPU or CUDA/ROCm graph required')
        if device.type == 'cpu':
            if stream is not None:
                raise ValueError('CPU fixture does not take a CUDA stream')
        elif device.index is None or not isinstance(stream, t.cuda.Stream) or stream.device != device:
            raise ValueError('Caller-owned stream on this exact indexed device required')
        obj = object.__new__(cls)
        obj._model, obj._t, obj.device, obj.dtype = graph, t, device, dtype
        obj.block_size, obj.context_rows, obj._stream = block_size, WINDOW - block_size, stream
        obj._state, obj._ready = 'live', False
        obj._graph, obj._captured_output = None, None
        with obj._on_stream(), t.inference_mode():
            obj._embeds = t.empty((block_size, 2560), dtype=dtype, device=device)
            obj._key = t.empty((5, obj.context_rows, 8, 128), dtype=dtype, device=device)
            obj._value = t.empty_like(obj._key)
            obj._anchor = t.empty((1,), dtype=t.int64, device=device)
            obj._prefix = t.empty((), dtype=t.int64, device=device)
            obj._offsets = t.arange(block_size, dtype=t.int64, device=device)
            obj._allow = t.ones((1, WINDOW), dtype=t.bool, device=device).expand(block_size, -1)
            obj._previous = (obj._offsets >= 1).view(-1, 1, 1)
        return obj

    def _on_stream(self):
        return nullcontext() if self._stream is None else self._t.cuda.stream(self._stream)

    def _live(self):
        if self._state != 'live':
            raise RuntimeError('Private proposer is failed or closed')

    def _consume(self):
        self._live()
        ready, self._ready = self._ready, False
        if not ready:
            raise RuntimeError('Fresh successful prepare required for one private consumption')

    def prepare(self, input_embeds, context, *, prefix_tokens, anchor_token_id):
        """Validate exact host metadata, then copy; a bad update revokes readiness.

        Host anchor IDs must be actual ordinary target IDs. Their source and
        relation to embeddings/native history are caller assertions only. No
        tensor scalar, finite scan or device-to-host read occurs on this path.
        Context may be a ring view; its producers must precede these copies on
        the provided stream and retain their storage through copy completion.
        """
        self._ready = False
        self._live()
        if type(prefix_tokens) is not int or not self.context_rows <= prefix_tokens <= MAX_POSITION - self.block_size:
            raise ValueError('Exact in-range long-window anchor position required')
        if type(anchor_token_id) is not int or not 0 <= anchor_token_id < DEFINED_IDS:
            raise ValueError('Ordinary host anchor ID0..248076 required')
        if type(context) is not PrivateContext or type(context.start_position) is not int or type(context.rows) is not int:
            raise ValueError('Exact PrivateContext chronology metadata required')
        if context.rows != self.context_rows or context.start_position != prefix_tokens - self.context_rows:
            raise ValueError('Exact visible committed window ending immediately before anchor required')
        t = self._t
        _metadata(input_embeds, (self.block_size, 2560), self.dtype, self.device, t, 'anchor/mask embeddings')
        shape = (5, self.context_rows, 8, 128)
        _metadata(context._key, shape, self.dtype, self.device, t, 'steady context key')
        _metadata(context._value, shape, self.dtype, self.device, t, 'steady context value')
        try:
            with self._on_stream(), t.inference_mode():
                self._embeds.copy_(input_embeds)
                self._key.copy_(context._key)
                self._value.copy_(context._value)
                self._anchor.fill_(anchor_token_id)
                self._prefix.fill_(prefix_tokens)
        except BaseException:
            self._state = 'failed'
            raise
        self._ready = True

    def _compute(self):
        body = self._model.body
        layout = _steady_layout(body._layers[0], self._prefix, self._offsets, self._allow, self._previous)
        hidden, residual = self._embeds, None
        for index, layer in enumerate(body._layers):
            hidden, residual = layer.forward(hidden, residual, self._key[index], self._value[index], layout)
        hidden, _ = _norm(hidden, body._norm, residual, self._t)
        return self._model.selector.propose(hidden, self._anchor)

    def eager(self):
        """Consume one preparation; returned private tensors have no owner proof."""
        self._consume()
        try:
            with self._on_stream(), self._t.inference_mode():
                return self._compute()
        except BaseException:
            self._state = 'failed'
            raise

    def capture(self, *, warmup=2):
        """Consume preparation for warmup/capture; returns no publishable output.

        Warmup drains only the provided stream. Direct capture_begin/end avoid
        torch.cuda.graph's device-wide synchronization/cache cleanup. Capture
        is once per wrapper; a fresh prepare is required before public replay.
        A failed capture retires this object even if cleanup can end capture.
        """
        self._consume()
        if self.device.type != 'cuda':
            raise ValueError('Capture requires explicit GPU and caller-owned stream')
        if type(warmup) is not int or not 1 <= warmup <= 16:
            raise ValueError('Exact warmup count1..16 required')
        if self._graph is not None:
            raise RuntimeError('This private graph has already been captured')
        try:
            with self._on_stream(), self._t.inference_mode():
                for _ in range(warmup):
                    self._compute()
                self._stream.synchronize()
                self._graph = self._t.cuda.CUDAGraph()
                self._graph.capture_begin()
                try:
                    output = self._compute()
                finally:
                    # Attempt to end even after compute fails. Ending itself
                    # may fail too; either case permanently retires the wrapper.
                    self._graph.capture_end()
                self._captured_output = output
        except BaseException:
            self._ready, self._state = False, 'failed'
            # All references remain owned for explicit close/drain. A failed
            # capture is never treated as safe or made available for replay.
            raise

    def replay(self):
        """Consume one preparation and enqueue replay on the exact same stream."""
        self._consume()
        if self._graph is None or self._captured_output is None:
            raise RuntimeError('Successful private capture required before replay')
        try:
            with self._on_stream(), self._t.inference_mode():
                self._graph.replay()
            return self._captured_output
        except BaseException:
            self._state = 'failed'
            raise

    def close(self):
        """Drain this wrapper's stream before releasing its captured/input storage.

        If the drain raises, references are retained and the failed wrapper
        cannot prepare/replay. The caller must resolve that device failure.
        The caller must retain this object and call close; GC is not a fence.
        """
        self._ready = False
        if self._state == 'closed':
            return
        self._state = 'failed'
        if self._stream is not None:
            self._stream.synchronize()
        self._captured_output, self._graph = None, None
        self._embeds = self._key = self._value = self._anchor = self._prefix = None
        self._offsets = self._allow = self._previous = self._model = None
        self._state = 'closed'
