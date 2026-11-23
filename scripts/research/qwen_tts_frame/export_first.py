"""Export the CPU reference for the first acoustic step as static ONNX."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from .frame import FramePredictor
from .weights import MODEL_PATH, TALKER_CODEC_EMBEDDING, FrameWeights, load_weights


class _Graph:
    def __init__(self):
        self.nodes = []
        self.initializers = []

    def constant(self, name, value, dtype=None):
        self.initializers.append(numpy_helper.from_array(np.asarray(value, dtype=dtype), name=name))
        return name

    def apply(self, op, *inputs, **attrs):
        output = f"{op.lower()}_{len(self.nodes)}"
        self.nodes.append(helper.make_node(op, list(inputs), [output], name=output, **attrs))
        return output


def build_first_model(weights: FrameWeights, *, host_embedding: bool = False) -> onnx.ModelProto:
    """Build a batch-1, two-token F32 graph that returns c1 logits before sampling."""
    reference = FramePredictor(weights)
    arch = reference.arch
    graph = _Graph()
    op = graph.apply
    const = graph.constant
    if not host_embedding:
        token_axis = const("token_axis", [0], np.int64)
    last_token = const("last_token", 1, np.int64)
    half = arch.head_dim // 2
    left_columns = const("rope_left_columns", np.arange(half, dtype=np.int64))
    right_columns = const("rope_right_columns", np.arange(half, arch.head_dim, dtype=np.int64))
    cos = const("rope_cos", reference.cos[:, :2])
    sin = const("rope_sin", reference.sin[:, :2])
    eps = const("rms_epsilon", reference.eps)
    query_shape = const("query_shape", [2, arch.num_attention_heads, arch.head_dim], np.int64)
    kv_shape = const("kv_shape", [2, arch.num_key_value_heads, arch.head_dim], np.int64)
    attention_shape = const("attention_shape", [2, arch.num_attention_heads * arch.head_dim], np.int64)
    kv_head_ids = const("kv_head_ids", reference.kv_head_ids, np.int64)
    attention_scale = const("attention_scale", reference.scale)
    causal_mask = const("causal_mask", [[0, -np.inf], [0, 0]], np.float32)
    lower = const("silu_lower", -80, np.float32)
    upper = const("silu_upper", 80, np.float32)
    one = const("one", 1, np.float32)

    def rms(values, weight_name):
        mean_square = op("ReduceMean", op("Mul", values, values), axes=[-1], keepdims=1)
        denominator = op("Sqrt", op("Add", mean_square, eps))
        return op("Mul", op("Div", values, denominator), const(weight_name, weights.tensors[weight_name]))

    def dense(values, weight_name):
        matrix = const(f"{weight_name}.transposed", weights.tensors[weight_name].T)
        return op("MatMul", values, matrix)

    def rope(values):
        left = op("Gather", values, left_columns, axis=-1)
        right = op("Gather", values, right_columns, axis=-1)
        rotated_left = op("Sub", op("Mul", left, cos), op("Mul", right, sin))
        rotated_right = op("Add", op("Mul", right, cos), op("Mul", left, sin))
        return op("Concat", rotated_left, rotated_right, axis=-1)

    if host_embedding:
        inputs = [helper.make_tensor_value_info("token_rows", TensorProto.FLOAT,
                                                [2, arch.talker_hidden_size])]
        hidden = "token_rows"
    else:
        inputs = [
            helper.make_tensor_value_info("hidden", TensorProto.FLOAT, [arch.talker_hidden_size]),
            helper.make_tensor_value_info("c0", TensorProto.INT64, []),
        ]
        embedding = const(TALKER_CODEC_EMBEDDING, weights.tensors[TALKER_CODEC_EMBEDDING])
        c0_embedding = op("Gather", embedding, "c0", axis=0)
        hidden = op("Concat", op("Unsqueeze", "hidden", token_axis), op("Unsqueeze", c0_embedding, token_axis), axis=0)
    for layer in range(arch.num_hidden_layers):
        prefix = f"code_pred.blk.{layer}."
        norm = rms(hidden, prefix + "attn_norm.weight")
        query = op("Reshape", dense(norm, prefix + "attn_q.weight"), query_shape)
        key = op("Reshape", dense(norm, prefix + "attn_k.weight"), kv_shape)
        value = op("Reshape", dense(norm, prefix + "attn_v.weight"), kv_shape)
        query = rope(op("Transpose", rms(query, prefix + "attn_q_norm.weight"), perm=[1, 0, 2]))
        key = rope(op("Transpose", rms(key, prefix + "attn_k_norm.weight"), perm=[1, 0, 2]))
        key = op("Gather", key, kv_head_ids, axis=0)
        value = op("Gather", op("Transpose", value, perm=[1, 0, 2]), kv_head_ids, axis=0)
        scores = op("MatMul", query, op("Transpose", key, perm=[0, 2, 1]))
        scores = op("Add", op("Mul", scores, attention_scale), causal_mask)
        attended = op("MatMul", op("Softmax", scores, axis=-1), value)
        attended = op("Reshape", op("Transpose", attended, perm=[1, 0, 2]), attention_shape)
        hidden = op("Add", hidden, dense(attended, prefix + "attn_output.weight"))

        norm = rms(hidden, prefix + "ffn_norm.weight")
        gate = dense(norm, prefix + "ffn_gate.weight")
        up = dense(norm, prefix + "ffn_up.weight")
        exp = op("Exp", op("Neg", op("Clip", gate, lower, upper)))
        silu = op("Div", gate, op("Add", one, exp))
        hidden = op("Add", hidden, dense(op("Mul", silu, up), prefix + "ffn_down.weight"))

    normalized = rms(op("Gather", hidden, last_token, axis=0), "code_pred.output_norm.weight")
    logits = dense(normalized, "code_pred.lm_head.0.weight")
    graph.nodes.append(helper.make_node("Identity", [logits], ["c1_logits"], name="c1_logits"))
    first_step = helper.make_graph(
        graph.nodes,
        "qwen3_tts_first_acoustic_step_f32",
        inputs,
        [helper.make_tensor_value_info("c1_logits", TensorProto.FLOAT, [arch.vocab_size])],
        initializer=graph.initializers,
    )
    return helper.make_model(
        first_step,
        opset_imports=[helper.make_opsetid("", 17)],
        ir_version=8,
        producer_name="strix-alloy",
        doc_string="Two-token CodePredictor F32 reference for c1. Sampling is external.",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gguf", type=Path, default=MODEL_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-embedding", action="store_true",
                        help="Accept F32 token_rows containing the Talker hidden row and exact c0 embedding row")
    args = parser.parse_args(argv)
    model = build_first_model(load_weights(args.gguf), host_embedding=args.host_embedding)
    onnx.save_model(model, args.output)


if __name__ == "__main__":
    main()
