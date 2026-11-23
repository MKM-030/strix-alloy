"""Export the complete batch-one acoustic CodePredictor frame as static ONNX."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper

from .export_first import _Graph
from .frame import FramePredictor
from .weights import MODEL_PATH, FrameWeights, load_weights


def build_frame_model(weights: FrameWeights, *, steps: int = 15,
                      expose_logits: bool = False) -> onnx.ModelProto:
    """Build a static FP32 frame with cache state private to one invocation."""
    from .sampler import emit_sample

    reference = FramePredictor(weights)
    arch = reference.arch
    if type(steps) is not int or not 1 <= steps <= min(15, arch.num_acoustic_codebooks):
        raise ValueError('Acoustic frame must contain 1 to 15 supported steps')

    graph = _Graph()
    op = graph.apply
    const = graph.constant
    token_axis = const('token_axis', [0], np.int64)
    step_ids = [const(f'index.{index}', index, np.int64) for index in range(steps + 1)]
    half = arch.head_dim // 2
    left_columns = const('rope_left_columns', np.arange(half, dtype=np.int64))
    right_columns = const('rope_right_columns', np.arange(half, arch.head_dim, dtype=np.int64))
    cos_table = const('rope_cos', reference.cos[:, :steps + 1])
    sin_table = const('rope_sin', reference.sin[:, :steps + 1])
    initial_positions = const('initial_positions', [0, 1], np.int64)
    eps = const('rms_epsilon', reference.eps)
    causal_mask = const('causal_mask', [[0, -np.inf], [0, 0]], np.float32)
    kv_head_ids = const('kv_head_ids', reference.kv_head_ids, np.int64)
    scale = const('attention_scale', reference.scale)
    lower = const('silu_lower', -80, np.float32)
    upper = const('silu_upper', 80, np.float32)
    one = const('one', 1, np.float32)

    shapes = {}
    for tokens in ((2, 1) if steps > 1 else (2,)):
        shapes[tokens] = (
            const(f'query_shape.{tokens}', [tokens, arch.num_attention_heads, arch.head_dim], np.int64),
            const(f'kv_shape.{tokens}', [tokens, arch.num_key_value_heads, arch.head_dim], np.int64),
            const(f'attention_shape.{tokens}', [tokens, arch.num_attention_heads * arch.head_dim], np.int64),
        )

    added_weights = set()

    def weight(name, *, transpose=False):
        key = f'{name}.transposed' if transpose else name
        if key not in added_weights:
            values = weights.tensors[name]
            const(key, values.T if transpose else values, np.float32)
            added_weights.add(key)
        return key

    def rms(values, name):
        mean = op('ReduceMean', op('Mul', values, values), axes=[-1], keepdims=1)
        denominator = op('Sqrt', op('Add', mean, eps))
        return op('Mul', op('Div', values, denominator), weight(name))

    def dense(values, name):
        return op('MatMul', values, weight(name, transpose=True))

    def rope(values, cos, sin):
        left = op('Gather', values, left_columns, axis=-1)
        right = op('Gather', values, right_columns, axis=-1)
        rotated_left = op('Sub', op('Mul', left, cos), op('Mul', right, sin))
        rotated_right = op('Add', op('Mul', right, cos), op('Mul', left, sin))
        return op('Concat', rotated_left, rotated_right, axis=-1)

    values = 'token_rows'
    cache = []
    cache_types = []
    code_rows = []
    logits_rows = []
    valid = None
    for step in range(steps):
        tokens = 2 if step == 0 else 1
        query_shape, kv_shape, attention_shape = shapes[tokens]
        # Position 0 is the Talker hidden row, position 1 is the c0 embedding.
        positions = initial_positions if step == 0 else op('Unsqueeze', step_ids[step + 1], token_axis)
        cos = op('Gather', cos_table, positions, axis=1)
        sin = op('Gather', sin_table, positions, axis=1)

        for layer in range(arch.num_hidden_layers):
            prefix = f'code_pred.blk.{layer}.'
            norm = rms(values, prefix + 'attn_norm.weight')
            query = op('Reshape', dense(norm, prefix + 'attn_q.weight'), query_shape)
            key = op('Reshape', dense(norm, prefix + 'attn_k.weight'), kv_shape)
            value = op('Reshape', dense(norm, prefix + 'attn_v.weight'), kv_shape)
            query = rope(op('Transpose', rms(query, prefix + 'attn_q_norm.weight'), perm=[1, 0, 2]), cos, sin)
            key = rope(op('Transpose', rms(key, prefix + 'attn_k_norm.weight'), perm=[1, 0, 2]), cos, sin)
            value = op('Transpose', value, perm=[1, 0, 2])
            if step == 0:
                cache.append((key, value))
            else:
                previous_key, previous_value = cache[layer]
                key = op('Concat', previous_key, key, axis=1)
                value = op('Concat', previous_value, value, axis=1)
                cache[layer] = (key, value)
            cache_shape = [arch.num_key_value_heads, step + 2, arch.head_dim]
            cache_types.extend(helper.make_tensor_value_info(tensor, TensorProto.FLOAT, cache_shape)
                               for tensor in (key, value))

            grouped_key = op('Gather', key, kv_head_ids, axis=0)
            grouped_value = op('Gather', value, kv_head_ids, axis=0)
            scores = op('MatMul', query, op('Transpose', grouped_key, perm=[0, 2, 1]))
            scores = op('Mul', scores, scale)
            if step == 0:
                scores = op('Add', scores, causal_mask)
            attended = op('MatMul', op('Softmax', scores, axis=-1), grouped_value)
            attended = op('Reshape', op('Transpose', attended, perm=[1, 0, 2]), attention_shape)
            values = op('Add', values, dense(attended, prefix + 'attn_output.weight'))

            norm = rms(values, prefix + 'ffn_norm.weight')
            gate = dense(norm, prefix + 'ffn_gate.weight')
            up = dense(norm, prefix + 'ffn_up.weight')
            exp = op('Exp', op('Neg', op('Clip', gate, lower, upper)))
            silu = op('Div', gate, op('Add', one, exp))
            values = op('Add', values, dense(op('Mul', silu, up), prefix + 'ffn_down.weight'))

        last = op('Gather', values, step_ids[tokens - 1], axis=0)
        logits = dense(rms(last, 'code_pred.output_norm.weight'), f'code_pred.lm_head.{step}.weight')
        if expose_logits:
            logits_rows.append(op('Unsqueeze', logits, token_axis))
        uniform = op('Gather', 'uniforms', step_ids[step], axis=0)
        code, step_valid = emit_sample(graph, logits, 'temperature', uniform)
        code_rows.append(op('Unsqueeze', code, token_axis))
        valid = step_valid if valid is None else op('And', valid, step_valid)
        if step + 1 < steps:
            embedding = weight(f'code_pred.codec_embd.{step}.weight')
            values = op('Gather', embedding, code_rows[-1], axis=0)

    def output(name, source, dtype, shape):
        graph.nodes.append(helper.make_node('Identity', [source], [name], name=name))
        return helper.make_tensor_value_info(name, dtype, shape)

    outputs = [
        output('acoustic_ids', op('Concat', *code_rows, axis=0), TensorProto.INT64, [steps]),
        output('sampler_valid', valid, TensorProto.BOOL, []),
    ]
    if expose_logits:
        outputs.append(output('acoustic_logits', op('Concat', *logits_rows, axis=0),
                              TensorProto.FLOAT, [steps, arch.vocab_size]))
    model_graph = helper.make_graph(
        graph.nodes, 'qwen3_tts_acoustic_frame_f32',
        [
            helper.make_tensor_value_info('token_rows', TensorProto.FLOAT, [2, arch.talker_hidden_size]),
            helper.make_tensor_value_info('temperature', TensorProto.FLOAT, []),
            helper.make_tensor_value_info('uniforms', TensorProto.FLOAT, [steps]),
        ],
        outputs, initializer=graph.initializers, value_info=cache_types,
    )
    return helper.make_model(
        model_graph, opset_imports=[helper.make_opsetid('', 17)], ir_version=8,
        producer_name='strix-alloy',
        doc_string='Static FP32 CodePredictor frame with host-provided semantic embedding and sampler draws.',
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gguf', type=Path, default=MODEL_PATH)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, choices=range(1, 16), default=15)
    parser.add_argument('--expose-logits', action='store_true')
    args = parser.parse_args(argv)
    model = build_frame_model(load_weights(args.gguf), steps=args.steps, expose_logits=args.expose_logits)
    onnx.save_model(model, args.output)


if __name__ == '__main__':
    main()
