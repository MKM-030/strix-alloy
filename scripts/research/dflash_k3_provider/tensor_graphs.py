"""Default-off pure tensor context/backbone/head components.

No PyTorch import, model load, accelerator initialization or inference at import.
The factory is an explicit preparation operation for the root-owned runtime.
It does not modify the CPU reference and has no native callback/serving hook.
"""
from dataclasses import dataclass

from abi import HEAD_DIM, HIDDEN, K, KV_HEADS, LAYERS, VOCAB, resource_plan


@dataclass(frozen=True)
class TensorGraphs:
    context: object
    backbone: object
    head: object
    capacity: int


def make_tensor_graphs(torch, *, weights, full_head, capacity, compute_dtype="bf16",
                       attention_mode="repeat", head_mode="chunked"):
    """Bind ONLY actual strict-loaded weights/head; caller chooses device later.

    This factory never chooses a GPU/NPU. Root must first use the published
    strict loader and immutable TargetBinding; weights/head remain private.
    Context [5,KV-kind2,KV-head2,capacity,256] has one accepted prefix. Padded
    slots are masked/zeroed. Cos/sin come from full-head default NeoX RoPE.
    """
    resource_plan(capacity)
    if compute_dtype not in {"bf16", "float32"}:
        raise ValueError("Explicit BF16 source math or FP32 approximation is required")
    if attention_mode not in {"repeat", "grouped2d"} or head_mode not in {"chunked", "full_bf16"}:
        raise ValueError("Explicit preparation variant must be named")
    if head_mode == "full_bf16" and compute_dtype != "bf16":
        raise ValueError("Single full-head candidate forbids full FP32 head expansion")
    dtype = {"bf16": torch.bfloat16, "float32": torch.float32}[compute_dtype]
    # Registration references these prepared tensors; the three modules do not
    # clone whole learned matrices or invent/random-initialize any parameter.
    prepared = {n: t.detach().to(dtype=dtype) for n, t in weights.items()}

    class Math(torch.nn.Module):
        def __init__(self, names):
            super().__init__()
            self._keys = {}
            for i, name in enumerate(names):
                self._keys[name] = f"w{i}"
                self.register_buffer(f"w{i}", prepared[name])

        def weight(self, name):
            return getattr(self, self._keys[name])

        def linear(self, x, name):
            return torch.nn.functional.linear(x, self.weight(name))

        def rms(self, x, name):
            value = x.float()
            squared = value.pow(2)
            variance = squared.mean(-1, keepdim=True) + 1e-6
            inverse = torch.rsqrt(variance)
            normalized = value * inverse
            output = self.weight(name) * normalized.to(x.dtype)
            finite = (torch.isfinite(x).all() & torch.isfinite(squared).all()
                & torch.isfinite(variance).all() & torch.isfinite(inverse).all()
                & torch.isfinite(normalized).all() & torch.isfinite(output).all())
            return output, finite

        def rope(self, x, cos, sin):
            rotated = torch.cat((-x[..., 128:], x[..., :128]), dim=-1)
            return x * cos[None, None] + rotated * sin[None, None]

    context_names = ["fc.weight", "hidden_norm.weight"]
    for i in range(5):
        context_names += [f"layers.{i}.self_attn.{n}.weight" for n in ("k_proj", "v_proj", "k_norm")]

    class ContextProjector(Math):
        def __init__(self):
            super().__init__(context_names)

        def forward(self, selected_target_features, cos, sin):
            # Host must slice accepted input rows and reject nonfinite selected
            # rows BEFORE dispatch. Output validity additionally prevents commit.
            rows = selected_target_features.shape[0]
            fused, finite = self.rms(self.linear(selected_target_features[None], "fc.weight"), "hidden_norm.weight")
            result = []
            finite = finite & torch.isfinite(selected_target_features).all()
            for i in range(5):
                p = f"layers.{i}.self_attn."
                key = self.linear(fused, p + "k_proj.weight").reshape(1, rows, 2, 256)
                key, key_finite = self.rms(key, p + "k_norm.weight")
                key = key.transpose(1, 2)
                key = self.rope(key, cos, sin)
                value = self.linear(fused, p + "v_proj.weight").reshape(1, rows, 2, 256).transpose(1, 2)
                finite = finite & key_finite & torch.isfinite(key).all() & torch.isfinite(value).all()
                result.append(torch.stack((key[0], value[0]), dim=0))
            return torch.stack(result, dim=0), finite

    class DraftBackbone(Math):
        def __init__(self):
            super().__init__([n for n in prepared if n not in {"fc.weight", "hidden_norm.weight"}])
            self.register_buffer("context_index", torch.arange(capacity, dtype=torch.long, device="cpu"))

        def forward(self, committed_context_kv, context_length, query_embeddings, cos, sin):
            hidden = query_embeddings[None]
            valid = self.context_index < context_length
            finite = torch.isfinite(hidden).all()
            for i in range(5):
                p = f"layers.{i}."
                residual = hidden
                x, norm_finite = self.rms(hidden, p + "input_layernorm.weight")
                finite = finite & norm_finite
                a = p + "self_attn."
                query = self.linear(x, a + "q_proj.weight").reshape(1, 3, 24, 256)
                query, q_finite = self.rms(query, a + "q_norm.weight")
                query = query.transpose(1, 2)
                key = self.linear(x, a + "k_proj.weight").reshape(1, 3, 2, 256)
                key, k_finite = self.rms(key, a + "k_norm.weight")
                key = key.transpose(1, 2)
                value = self.linear(x, a + "v_proj.weight").reshape(1, 3, 2, 256).transpose(1, 2)
                query, key = self.rope(query, cos, sin), self.rope(key, cos, sin)
                finite = (finite & q_finite & k_finite & torch.isfinite(query).all()
                    & torch.isfinite(key).all() & torch.isfinite(value).all())
                ctx_k = torch.where(valid[None, None, :, None], committed_context_kv[i, 0][None], 0)
                ctx_v = torch.where(valid[None, None, :, None], committed_context_kv[i, 1][None], 0)
                finite = finite & torch.isfinite(ctx_k).all() & torch.isfinite(ctx_v).all()
                key, value = torch.cat((ctx_k, key), dim=2), torch.cat((ctx_v, value), dim=2)
                length = capacity + 3
                all_valid = torch.cat((valid, torch.ones(3, dtype=torch.bool, device=valid.device)), dim=0)
                if attention_mode == "grouped2d":
                    outputs = []
                    for kv_head in range(2):
                        # Strict 2D GEMM, not broadcast BMM. Each KV matrix is
                        # used directly by its12 Q heads; no repeated KV exists.
                        q2 = query[0, kv_head * 12:(kv_head + 1) * 12].reshape(36, 256)
                        k2, v2 = key[0, kv_head], value[0, kv_head]
                        score = torch.matmul(q2, k2.transpose(0, 1)) * (256 ** -0.5)
                        finite = finite & torch.isfinite(score).all()
                        score = score.masked_fill(~all_valid[None], float("-inf"))
                        probability = torch.nn.functional.softmax(score, dim=-1, dtype=torch.float32).to(query.dtype)
                        group_output = torch.matmul(probability, v2)
                        finite = finite & torch.isfinite(probability).all() & torch.isfinite(group_output).all()
                        outputs.append(group_output.reshape(12, 3, 256))
                    output = torch.cat(outputs, dim=0)[None].transpose(1, 2).contiguous().reshape(1, 3, 6144)
                else:
                    key = key[:, :, None].expand(1, 2, 12, length, 256).reshape(1, 24, length, 256)
                    value = value[:, :, None].expand(1, 2, 12, length, 256).reshape(1, 24, length, 256)
                    score = torch.matmul(query, key.transpose(2, 3)) * (256 ** -0.5)
                    # Check scores before intentional mask -inf sentinels.
                    finite = finite & torch.isfinite(score).all()
                    score = score.masked_fill(~all_valid[None, None, None], float("-inf"))
                    probability = torch.nn.functional.softmax(score, dim=-1, dtype=torch.float32).to(query.dtype)
                    output = torch.matmul(probability, value).transpose(1, 2).contiguous().reshape(1, 3, 6144)
                    finite = finite & torch.isfinite(probability).all()
                projection = self.linear(output, a + "o_proj.weight")
                finite = (finite & torch.isfinite(output).all()
                    & torch.isfinite(projection).all())
                hidden = residual + projection
                finite = finite & torch.isfinite(hidden).all()
                residual = hidden
                x, norm_finite = self.rms(hidden, p + "post_attention_layernorm.weight")
                gate_input = self.linear(x, p + "mlp.gate_proj.weight")
                gate = torch.nn.functional.silu(gate_input)
                up = self.linear(x, p + "mlp.up_proj.weight")
                product = gate * up
                down = self.linear(product, p + "mlp.down_proj.weight")
                finite = (finite & norm_finite & torch.isfinite(gate_input).all()
                    & torch.isfinite(gate).all() & torch.isfinite(up).all()
                    & torch.isfinite(product).all() & torch.isfinite(down).all())
                hidden = residual + down
                finite = finite & torch.isfinite(hidden).all()
            hidden, norm_finite = self.rms(hidden, "norm.weight")
            return hidden[0], finite & norm_finite

    class FullHeadTopIds(torch.nn.Module):
        def __init__(self):
            super().__init__()
            # Keep actual full head in BF16, even for FP32 backbone arithmetic.
            self.register_buffer("full_head", full_head.detach())

        def forward(self, hidden):
            finite = torch.isfinite(hidden).all()
            best_values, best_ids = None, None
            pieces = []
            for start in range(0, VOCAB, 8192):
                logits = torch.nn.functional.linear(hidden, self.full_head[start:start + 8192].to(hidden.dtype))
                finite = finite & torch.isfinite(logits).all()
                pieces.append(logits)
                values, ids = logits.max(dim=-1)
                ids = ids + start
                if best_values is None:
                    best_values, best_ids = values, ids
                else:
                    better = values > best_values
                    best_values = torch.where(better, values, best_values)
                    best_ids = torch.where(better, ids, best_ids)
            # Strict > preserves lowest-ID ties across chunks, as full argmax.
            # IDs must be discarded if finite=False. No native publication here.
            return best_ids, finite, torch.cat(pieces, dim=-1)

    head = FullHeadTopIds() if head_mode == "chunked" else make_full_head_bf16(torch, full_head)
    return TensorGraphs(ContextProjector(), DraftBackbone(), head, capacity)


def make_full_head_bf16(torch, full_head):
    """Default-off one-GEMM head; shares the exact existing BF16 head storage."""
    class FullHeadBF16(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("full_head", full_head)

        def forward(self, hidden):
            if hidden.dtype != torch.bfloat16 or self.full_head.dtype != torch.bfloat16:
                raise ValueError("Single-GEMM alternative admits BF16 only; no full FP32 temporary")
            logits = torch.nn.functional.linear(hidden, self.full_head)
            finite = torch.isfinite(hidden).all() & torch.isfinite(logits).all()
            return logits.argmax(dim=-1), finite, logits

    return FullHeadBF16()
