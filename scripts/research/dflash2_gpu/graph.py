"""Explicit persistent TP1 query tensor graph for CPU or ROCm/CUDA PyTorch.

Equations adapted from SGLang3c560089e1818a5217a73f2168273485a5350341,
Apache-2.0; ../dflash2_reference/sources/SGLANG_LICENSE applies. No Torch
import, file read, provider lookup, allocation or device selection at import.
Only from_cpu factories explicitly clone/pack caller-owned startup weights
onto the exact caller-selected device. No native publication or readiness.
"""
from dataclasses import dataclass

WIDTH, HEAD_DIM, QUERY_HEADS, KV_HEADS = 2560, 128, 32, 8
LAYER_SHAPES = {
    'input_layernorm.weight': (2560,), 'post_attention_layernorm.weight': (2560,),
    'self_attn.q_proj.weight': (4096, 2560), 'self_attn.k_proj.weight': (1024, 2560),
    'self_attn.v_proj.weight': (1024, 2560), 'self_attn.o_proj.weight': (2560, 4096),
    'self_attn.q_norm.weight': (128,), 'self_attn.k_norm.weight': (128,),
    'mlp.gate_proj.weight': (7680, 2560), 'mlp.up_proj.weight': (7680, 2560),
    'mlp.down_proj.weight': (2560, 7680),
}
for _conv_name in ('attention_conv', 'mlp_conv'):
    LAYER_SHAPES[_conv_name + '.base_kernel'] = (2, 2, 2560)
    LAYER_SHAPES[_conv_name + '.kernel_projection.weight'] = (640, 2560)


def _check_cpu_weights(weights, shapes, torch):
    if type(weights) is not dict or set(weights) != set(shapes):
        raise ValueError('Exact startup tensor mapping required')
    dtype = next(iter(weights.values())).dtype
    if dtype not in (torch.float32, torch.bfloat16):
        raise TypeError('FP32/BF16 startup weights required')
    for name, shape in shapes.items():
        value = weights[name]
        if not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.dtype != dtype or tuple(value.shape) != shape:
            raise ValueError('CPU startup tensor shape/dtype differs: ' + name)
        # One-time startup validation only. Never executed by a tensor graph.
        for start in range(0, value.shape[0], 64):
            if not bool(torch.isfinite(value[start:start + 64]).all()):
                raise ValueError('Nonfinite startup weight: ' + name)
    return dtype


def _explicit_device(device, torch):
    chosen = torch.device(device)
    if chosen.type not in ('cpu', 'cuda') or (chosen.type == 'cuda' and chosen.index is None):
        raise ValueError('Explicit cpu or indexed cuda:N/ROCm device required')
    return chosen


def _metadata(value, shape, dtype, device, torch, name):
    # Tensor metadata is host-resident; no all/item/bool/device scalar read here.
    if not isinstance(value, torch.Tensor) or tuple(value.shape) != tuple(shape) or value.dtype != dtype or value.device != device:
        raise ValueError('Tensor metadata differs: ' + name)


def _norm(value, weight, residual, torch):
    x = value.float()
    saved = None
    if residual is not None:
        x = x + residual.float()
        saved = x.to(value.dtype)
    normalized = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-6)
    return (normalized * weight).to(value.dtype), saved


def _rotary(value, cos, sin, torch):
    first, second = value[..., :64], value[..., 64:]
    return torch.cat((first * cos - second * sin, second * cos + first * sin), -1)


def _conv(hidden, delta, base, previous_allowed, torch):
    blocks = hidden.unflatten(-1, (160, 16))
    coefficients = base.view(1, 2, 160, 16) + delta.unsqueeze(-1)
    result = coefficients[:, 0] * blocks
    shifted = torch.nn.functional.pad(blocks[:-1], (0, 0, 0, 0, 1, 0))
    shifted = torch.where(previous_allowed, shifted, 0)
    return (result + coefficients[:, 1] * shifted).flatten(-2)


@dataclass(frozen=True)
class Layout:
    prefix_tokens: int
    context_rows: int
    block_size: int
    positions: object
    cos: object
    sin: object
    allow_mask: object
    previous_allowed: object


class PrivateContext:
    """Owned caller-bound target-input KV, without native ownership authority."""
    def __init__(self, key, value, start_position):
        self._key, self._value = key, value
        self.start_position = start_position
        self.rows = key.shape[1]

    def export_copies(self):
        return self._key.clone(), self._value.clone()


class QueryLayer:
    """One real-width layer with permanently owned packed QKV and gate/up."""
    @classmethod
    def from_cpu(cls, weights, *, device, batched_attention=False):
        import torch
        if type(batched_attention) is not bool:
            raise TypeError('Explicit Boolean batched_attention required')
        dtype = _check_cpu_weights(weights, LAYER_SHAPES, torch)
        chosen = _explicit_device(device, torch)
        with torch.inference_mode():
            return cls._from_validated_cpu(weights, dtype, chosen, torch, batched_attention)

    @classmethod
    def _from_validated_cpu(cls, weights, dtype, chosen, torch, batched_attention=False):
        obj = cls()
        obj._t, obj.dtype, obj.device = torch, dtype, chosen
        obj._batched_attention = batched_attention
        packed = {}
        skip = {f'self_attn.{x}_proj.weight' for x in ('q', 'k', 'v')} | {'mlp.gate_proj.weight', 'mlp.up_proj.weight'}
        for name, value in weights.items():
            if name not in skip:
                packed[name] = value.to(device=chosen, copy=True)
        packed['qkv'] = torch.cat([weights[f'self_attn.{x}_proj.weight'] for x in ('q', 'k', 'v')]).to(device=chosen, copy=True)
        packed['gate_up'] = torch.cat([weights['mlp.gate_proj.weight'], weights['mlp.up_proj.weight']]).to(device=chosen, copy=True)
        obj._weights = packed
        obj._frequency = 1.0 / (10000. ** (torch.arange(0, 128, 2, device=chosen, dtype=torch.float32) / 128))
        return obj

    def layout(self, *, prefix_tokens, context_rows, block_size):
        if any(type(x) is not int for x in (prefix_tokens, context_rows, block_size)):
            raise TypeError('Exact integer logical layout required')
        if block_size not in (4, 8) or not 0 <= prefix_tokens <= 262144 - block_size or not 0 <= context_rows <= min(2048, prefix_tokens):
            raise ValueError('Block4/8, context<=2048 and in-range prefix required')
        end = prefix_tokens + block_size
        left = max(0, end - 2048)
        if prefix_tokens - context_rows > left:
            raise ValueError('Required visible committed history is missing')
        t = self._t
        with t.inference_mode():
            positions = t.arange(prefix_tokens, end, device=self.device, dtype=t.int64)
            angles = t.einsum('i,j -> ij', positions.float(), self._frequency)
            cos = angles.cos().to(self.dtype)[:, None, :]
            sin = angles.sin().to(self.dtype)[:, None, :]
            key_positions = t.arange(prefix_tokens - context_rows, end, device=self.device, dtype=t.int64)
            mask = ((key_positions >= left) & (key_positions < end))[None, :].expand(block_size, -1)
            previous = (t.arange(block_size, device=self.device) >= 1).view(-1, 1, 1)
            return Layout(prefix_tokens, context_rows, block_size, positions, cos, sin, mask, previous)

    def _prepare_conv(self, hidden, prefix, layout):
        t, w = self._t, self._weights
        coefficients = t.nn.functional.linear(hidden, w[prefix + '.kernel_projection.weight']).reshape(-1, 2, 2, 160)
        prepared = _conv(hidden, coefficients[:, 0], w[prefix + '.base_kernel'][0], layout.previous_allowed, t)
        return prepared, coefficients[:, 1]

    def _finish_conv(self, hidden, coefficients, prefix, layout):
        return _conv(hidden, coefficients, self._weights[prefix + '.base_kernel'][1], layout.previous_allowed, self._t)

    def _attention(self, hidden, key, value, layout):
        t, w, rows = self._t, self._weights, layout.block_size
        qkv = t.nn.functional.linear(hidden, w['qkv'])
        q, k, v = qkv.split((4096, 1024, 1024), dim=-1)
        q, _ = _norm(q.reshape(rows, 32, 128), w['self_attn.q_norm.weight'], None, t)
        k, _ = _norm(k.reshape(rows, 8, 128), w['self_attn.k_norm.weight'], None, t)
        q = _rotary(q, layout.cos, layout.sin, t)
        k = _rotary(k, layout.cos, layout.sin, t)
        keys = t.cat((key, k), dim=0).movedim(0, 1)
        values = t.cat((value, v.reshape(rows, 8, 128)), dim=0).movedim(0, 1)
        query = q.movedim(0, 1)
        if self._batched_attention:
            # Explicit candidate: all query rows have the same block-end
            # window, so one noncausal SDPA call realizes the same visibility.
            # Different GPU SDPA kernels/reductions remain Root-qualified.
            result = t.nn.functional.scaled_dot_product_attention(
                query.unsqueeze(0), keys.unsqueeze(0), values.unsqueeze(0),
                attn_mask=layout.allow_mask, enable_gqa=True, scale=128 ** -.5, is_causal=False)
            output = result.squeeze(0).movedim(1, 0)
            return t.nn.functional.linear(output.flatten(-2), w['self_attn.o_proj.weight'])
        output = t.empty_like(q)
        # The exact frozen CPU source path is one-query SDPA, noncausal and
        # every row sees the same window ending at the entire block end.
        # Fixed4/8 Python unrolling enqueues tensors only; no host scalar sync.
        for row in range(rows):
            result = t.nn.functional.scaled_dot_product_attention(
                query[:, row:row + 1].unsqueeze(0), keys.unsqueeze(0), values.unsqueeze(0),
                attn_mask=layout.allow_mask[row:row + 1], enable_gqa=True, scale=128 ** -.5, is_causal=False)
            output[row:row + 1] = result.squeeze(0).movedim(1, 0)
        return t.nn.functional.linear(output.flatten(-2), w['self_attn.o_proj.weight'])

    def forward(self, hidden, residual, context_key, context_value, layout):
        t, w = self._t, self._weights
        if type(layout) is not Layout:
            raise TypeError('Owned logical Layout required')
        rows = layout.block_size
        _metadata(hidden, (rows, 2560), self.dtype, self.device, t, 'hidden')
        _metadata(context_key, (layout.context_rows, 8, 128), self.dtype, self.device, t, 'context key')
        _metadata(context_value, context_key.shape, self.dtype, self.device, t, 'context value')
        if residual is not None:
            _metadata(residual, hidden.shape, self.dtype, self.device, t, 'residual')
        with t.inference_mode():
            if residual is None:
                residual = hidden
                hidden, _ = _norm(hidden, w['input_layernorm.weight'], None, t)
            else:
                hidden, residual = _norm(hidden, w['input_layernorm.weight'], residual, t)
            hidden, coefficients = self._prepare_conv(hidden, 'attention_conv', layout)
            hidden = self._attention(hidden, context_key, context_value, layout)
            hidden = self._finish_conv(hidden, coefficients, 'attention_conv', layout)
            hidden, residual = _norm(hidden, w['post_attention_layernorm.weight'], residual, t)
            hidden, coefficients = self._prepare_conv(hidden, 'mlp_conv', layout)
            gate_up = t.nn.functional.linear(hidden, w['gate_up'])
            hidden = t.nn.functional.silu(gate_up[..., :7680]) * gate_up[..., 7680:]
            hidden = t.nn.functional.linear(hidden, w['mlp.down_proj.weight'])
            hidden = self._finish_conv(hidden, coefficients, 'mlp_conv', layout)
            return hidden, residual


class QueryBackbone:
    """Persistent five-layer body and final residual RMS; private query KV only."""
    @classmethod
    def from_cpu(cls, weights, *, device, batched_attention=False):
        import torch
        if type(batched_attention) is not bool:
            raise TypeError('Explicit Boolean batched_attention required')
        shapes = {f'layers.{i}.{name}': shape for i in range(5) for name, shape in LAYER_SHAPES.items()}
        shapes['norm.weight'] = (2560,)
        dtype = _check_cpu_weights(weights, shapes, torch)
        chosen = _explicit_device(device, torch)
        with torch.inference_mode():
            layers = tuple(QueryLayer._from_validated_cpu({name: weights[f'layers.{i}.{name}'] for name in LAYER_SHAPES}, dtype, chosen, torch, batched_attention) for i in range(5))
            return cls._from_owned(layers, weights['norm.weight'].to(device=chosen, copy=True))

    @classmethod
    def from_owned_layers(cls, layers, final_norm_cpu):
        """Compose five already-owned layers; useful for explicit CPU fixtures.

        Sharing an owned layer deliberately shares its immutable packed storage;
        this is not a mechanism to load unowned model tensors into the graph.
        """
        if type(layers) not in (tuple, list) or len(layers) != 5 or any(type(x) is not QueryLayer for x in layers):
            raise ValueError('Five already-owned QueryLayer objects required')
        first = layers[0]
        if any(x.device != first.device or x.dtype != first.dtype for x in layers):
            raise ValueError('All owned layers must share device/dtype')
        _check_cpu_weights({'norm.weight': final_norm_cpu}, {'norm.weight': (2560,)}, first._t)
        if final_norm_cpu.dtype != first.dtype:
            raise ValueError('Final norm dtype differs')
        with first._t.inference_mode():
            return cls._from_owned(tuple(layers), final_norm_cpu.to(device=first.device, copy=True))

    @classmethod
    def _from_owned(cls, layers, norm):
        obj = cls()
        obj._layers, obj._norm = layers, norm
        obj._t, obj.dtype, obj.device = layers[0]._t, layers[0].dtype, layers[0].device
        return obj

    def bind_context(self, key, value, *, start_position):
        if type(start_position) is not int or not 0 <= start_position <= 262144:
            raise ValueError('Exact absolute context start required')
        if not isinstance(key, self._t.Tensor) or key.ndim != 4 or key.shape[0] != 5 or key.shape[1] > 2048:
            raise ValueError('Five-layer context[5,0..2048,8,128] required')
        if start_position + key.shape[1] > 262144:
            raise ValueError('Context extends beyond model capacity')
        _metadata(key, (5, key.shape[1], 8, 128), self.dtype, self.device, self._t, 'context key')
        _metadata(value, key.shape, self.dtype, self.device, self._t, 'context value')
        with self._t.inference_mode():
            return PrivateContext(key.clone(), value.clone(), start_position)

    def forward(self, input_embeds, context, *, prefix_tokens):
        if type(context) is not PrivateContext or type(prefix_tokens) is not int or context.start_position + context.rows != prefix_tokens:
            raise ValueError('Private context must end immediately before anchor')
        if not isinstance(input_embeds, self._t.Tensor) or input_embeds.ndim != 2:
            raise TypeError('Caller-owned anchor/mask embeddings required')
        layout = self._layers[0].layout(prefix_tokens=prefix_tokens, context_rows=context.rows, block_size=input_embeds.shape[0])
        hidden, residual = input_embeds, None
        with self._t.inference_mode():
            for index, layer in enumerate(self._layers):
                hidden, residual = layer.forward(hidden, residual, context._key[index], context._value[index], layout)
            hidden, _ = _norm(hidden, self._norm, residual, self._t)
            return hidden
