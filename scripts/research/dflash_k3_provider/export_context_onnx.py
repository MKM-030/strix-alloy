"""Manual fixed-R1 context ONNX export; no torch/ORT, device or inference calls.

All seventeen learned tensors are copied byte-for-byte from the pinned local
BF16 checkpoint into one 91,758,080-byte external-data file. The source file is
never modified. ONNX construction/checking is the only runtime work here.
"""
import argparse
from array import array
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def contract_module():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts/research/dflash_k3_reference"
        if (candidate / "contract.py").is_file():
            sys.path.insert(0, str(candidate))
            import contract
            return contract
    raise RuntimeError("Pinned published standard-library checkpoint contract is required")


def context_weight_names():
    names = ["fc.weight", "hidden_norm.weight"]
    for layer in range(5):
        names.extend(f"layers.{layer}.self_attn.{part}.weight"
                     for part in ("k_proj", "v_proj", "k_norm"))
    return tuple(names)


def copy_weights(manifest, destination):
    """Validate/copy only context weights; no conversion or tensor arithmetic."""
    if sys.byteorder != "little":
        raise RuntimeError("Pinned BF16 external-data bytes require little endian")
    rows, offset = [], 0
    with manifest.path.open("rb") as source, destination.open("xb") as output:
        for name in context_weight_names():
            info = manifest.tensors[name]
            source.seek(manifest.data_offset + info.start)
            remaining, digest = info.end - info.start, hashlib.sha256()
            while remaining:
                chunk = source.read(min(remaining, 4 * 1024 * 1024))
                if not chunk or len(chunk) % 2:
                    raise ValueError("Incomplete BF16 checkpoint payload")
                words = array("H")
                words.frombytes(chunk)
                if any(word & 0x7f80 == 0x7f80 for word in words):
                    raise ValueError("Nonfinite immutable context weight: " + name)
                output.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            length = info.end - info.start
            rows.append({"name": name, "shape": list(info.shape), "dtype": "BF16",
                "source_absolute_offset": manifest.data_offset + info.start,
                "external_offset": offset, "bytes": length,
                "raw_bytes_sha256": digest.hexdigest(), "all_values_finite": True})
            offset += length
    if offset != 91758080 or len(rows) != 17:
        raise AssertionError("Wrong complete context-projector learned inventory")
    return rows


def build_model(onnx, weight_rows, location, precision):
    """No custom op, placeholder matrix, dynamic row or model-wide export."""
    from onnx import TensorProto as T, helper as h
    if precision not in {"bf16_native", "float_roundtrip"}:
        raise ValueError("Unknown explicit precision path")
    native = precision == "bf16_native"
    dtype = T.BFLOAT16 if native else T.FLOAT
    nodes, initializers, checked = [], [], []
    serial = 0

    def op(kind, inputs, label, **attributes):
        nonlocal serial
        serial += 1
        output = f"{label}_{serial}"
        nodes.append(h.make_node(kind, list(inputs), [output], name=output, **attributes))
        return output

    def constant(name, kind, values, shape=None):
        initializers.append(h.make_tensor(name, kind, [len(values)] if shape is None else shape, values))
        return name

    last_axis = constant("last_axis", T.INT64, [-1])
    first_axis = constant("first_axis", T.INT64, [0])
    zero = constant("zero_i64", T.INT64, [0], [])
    epsilon = constant("rms_epsilon", T.FLOAT, [1e-6], [])
    half_start = constant("half_start", T.INT64, [0])
    half_mid = constant("half_mid", T.INT64, [128])
    half_end = constant("half_end", T.INT64, [256])
    key_shape = constant("key_shape", T.INT64, [1, 2, 256])

    def finite(value, label, kind):
        # BF16 is widened solely for validity; IsNaN/IsInf BF16 needs opset20.
        wide = op("Cast", [value], label + "_check_float", to=T.FLOAT) if kind == T.BFLOAT16 else value
        nan = op("IsNaN", [wide], label + "_isnan")
        inf = op("IsInf", [wide], label + "_isinf")
        bad = op("Or", [nan, inf], label + "_invalid")
        integer = op("Cast", [bad], label + "_invalid_i64", to=T.INT64)
        maximum = op("ReduceMax", [integer], label + "_any_invalid", keepdims=0)
        checked.append(op("Greater", [maximum, zero], label + "_bad_scalar"))
        return value

    def round_bf16(value, label):
        narrowed = op("Cast", [value], label + "_BF16", to=T.BFLOAT16)
        finite(narrowed, label + "_BF16", T.BFLOAT16)
        return op("Cast", [narrowed], label + "_exact_widen", to=T.FLOAT)

    weights = {}
    for index, row in enumerate(weight_rows):
        tensor = T()
        tensor.name, tensor.data_type = f"actual_weight_{index}", T.BFLOAT16
        tensor.dims.extend(row["shape"])
        tensor.data_location = T.EXTERNAL
        for key, value in (("location", location), ("offset", row["external_offset"]), ("length", row["bytes"])):
            entry = tensor.external_data.add()
            entry.key, entry.value = key, str(value)
        initializers.append(tensor)
        weights[row["name"]] = tensor.name if native else op("Cast", [tensor.name], f"weight_{index}_float", to=T.FLOAT)

    def linear(value, name, label):
        transposed = op("Transpose", [weights[name]], label + "_weight_T", perm=[1, 0])
        product = finite(op("MatMul", [value, transposed], label + "_matmul"), label + "_matmul", dtype)
        return product if native else round_bf16(product, label + "_linear_round")

    def rms(value, name, label):
        finite(value, label + "_input", dtype)
        wide = op("Cast", [value], label + "_input_float", to=T.FLOAT) if native else value
        square = finite(op("Mul", [wide, wide], label + "_square"), label + "_square", T.FLOAT)
        mean = finite(op("ReduceMean", [square, last_axis], label + "_mean", keepdims=1), label + "_mean", T.FLOAT)
        variance = finite(op("Add", [mean, epsilon], label + "_variance"), label + "_variance", T.FLOAT)
        root = finite(op("Sqrt", [variance], label + "_sqrt"), label + "_sqrt", T.FLOAT)
        inverse = finite(op("Reciprocal", [root], label + "_inverse"), label + "_inverse", T.FLOAT)
        normalized = finite(op("Mul", [wide, inverse], label + "_normalized"), label + "_normalized", T.FLOAT)
        if native:
            normalized = finite(op("Cast", [normalized], label + "_normalized_BF16", to=T.BFLOAT16), label + "_normalized_BF16", T.BFLOAT16)
        else:
            normalized = round_bf16(normalized, label + "_normalized_round")
        scaled = finite(op("Mul", [normalized, weights[name]], label + "_gamma"), label + "_gamma", dtype)
        return scaled if native else round_bf16(scaled, label + "_gamma_round")

    for name in ("target_features", "cos", "sin"):
        finite(name, name, dtype)
    fused = rms(linear("target_features", "fc.weight", "fusion"), "hidden_norm.weight", "hidden_norm")
    layers = []
    for layer in range(5):
        prefix, label = f"layers.{layer}.self_attn.", f"layer_{layer}"
        key = op("Reshape", [linear(fused, prefix + "k_proj.weight", label + "_k"), key_shape], label + "_k_heads")
        key = op("Transpose", [rms(key, prefix + "k_norm.weight", label + "_k_norm")], label + "_k_head_first", perm=[1, 0, 2])
        first = op("Slice", [key, half_start, half_mid, last_axis], label + "_k_first_half")
        second = op("Slice", [key, half_mid, half_end, last_axis], label + "_k_second_half")
        negative = finite(op("Neg", [second], label + "_k_negative"), label + "_k_negative", dtype)
        rotated = op("Concat", [negative, first], label + "_k_rotated", axis=-1)
        a = finite(op("Mul", [key, "cos"], label + "_rope_cos"), label + "_rope_cos", dtype)
        b = finite(op("Mul", [rotated, "sin"], label + "_rope_sin"), label + "_rope_sin", dtype)
        if not native:
            a, b = round_bf16(a, label + "_rope_cos_round"), round_bf16(b, label + "_rope_sin_round")
        key = finite(op("Add", [a, b], label + "_rope_sum"), label + "_rope_sum", dtype)
        if not native:
            key = round_bf16(key, label + "_rope_sum_round")
        value = op("Reshape", [linear(fused, prefix + "v_proj.weight", label + "_v"), key_shape], label + "_v_heads")
        value = op("Transpose", [value], label + "_v_head_first", perm=[1, 0, 2])
        key, value = op("Unsqueeze", [key, first_axis], label + "_key_kind"), op("Unsqueeze", [value, first_axis], label + "_value_kind")
        pair = op("Concat", [key, value], label + "_kv", axis=0)
        layers.append(op("Unsqueeze", [pair, first_axis], label + "_layer"))
    kv = op("Concat", layers, "complete_projected_kv", axis=0)
    finite(kv, "complete_projected_kv", dtype)
    invalid = checked[0]
    for index, check in enumerate(checked[1:]):
        invalid = op("Or", [invalid, check], f"any_invalid_{index}")
    nodes.append(h.make_node("Identity", [kv], ["context_kv"], name="context_kv"))
    nodes.append(h.make_node("Not", [invalid], ["all_finite"], name="all_finite"))
    graph = h.make_graph(nodes, "PinnedDFlashCompleteContextR1_" + precision,
        [h.make_tensor_value_info("target_features", dtype, [1, 12800]),
         h.make_tensor_value_info("cos", dtype, [1, 256]), h.make_tensor_value_info("sin", dtype, [1, 256])],
        [h.make_tensor_value_info("context_kv", dtype, [5, 2, 2, 1, 256]),
         h.make_tensor_value_info("all_finite", T.BOOL, [])], initializer=initializers)
    model = h.make_model(graph, producer_name="manual_pinned_dflash_context_export",
        producer_version="1", opset_imports=[h.make_opsetid("", 18)], ir_version=9)
    model.doc_string = ("Default off, complete context-only R1 projection, actual17 BF16 weights. "
        "Full NeoX cos/sin supplied from the exact source position. Native BF16 or explicit FLOAT/BF16/FLOAT rounding. "
        "Sqrt+Reciprocal decomposition and EP GEMM are numerically unqualified versus source torch.rsqrt/BF16 GEMM. "
        "No quantization, tolerance change, full head, attention, proposal or native activation.")
    return model, len(checked)


def export(args):
    import onnx
    contract = contract_module()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    contract.validate_config(config)
    manifest = contract.inspect_safetensors(args.checkpoint)
    contract.validate_checkpoint_manifest(manifest)
    if contract.sha256_file(manifest.path) != contract.CHECKPOINT_SHA256:
        raise ValueError("Export requires the exact pinned acquired checkpoint")
    destination = Path(args.output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    weights_path = destination / "context_weights.bf16.bin"
    rows = copy_weights(manifest, weights_path)
    precisions = ("bf16_native", "float_roundtrip") if args.precision == "both" else (args.precision,)
    graphs = []
    for precision in precisions:
        model, checks = build_model(onnx, rows, weights_path.name, precision)
        path = destination / f"context_projector_r1_{precision}.onnx"
        path.write_bytes(model.SerializeToString())
        onnx.checker.check_model(str(path), full_check=True)
        graphs.append({"path": str(path), "sha256": contract.sha256_file(path),
            "precision": precision, "operators": dict(sorted(Counter(n.op_type for n in model.graph.node).items())),
            "derived_values_with_finite_checks": checks, "checker_full_check_passed": True,
            "EP_BF16_partition_support": "not_executed_or_qualified", "EP_node_assignment": None,
            "source_CPU_numerical_errors": None, "hardware_execution": False})
    receipt = {"schema": "dflash_complete_context_r1_onnx_export.v1", "enabled": False,
        "checkpoint": str(manifest.path), "checkpoint_sha256": contract.CHECKPOINT_SHA256,
        "config_sha256": contract.sha256_file(args.config), "onnx_version": onnx.__version__,
        "exporter_sha256": contract.sha256_file(__file__), "graphs": graphs, "weights": rows,
        "external_weights_path": str(weights_path), "external_weights_bytes": weights_path.stat().st_size,
        "external_weights_sha256": contract.sha256_file(weights_path), "opset": 18, "ir_version": 9,
        "source_tap_indexes": [4, 16, 24, 36, 44], "rows": 1,
        "BF16_feature_input_bytes": 25600, "BF16_cos_sin_input_bytes": 1024,
        "BF16_KV_output_bytes": 10240, "FLOAT_feature_input_bytes": 51200,
        "FLOAT_cos_sin_input_bytes": 2048, "FLOAT_KV_output_bytes": 20480,
        "source_math_difference": "ONNX Sqrt then Reciprocal in FP32 versus torch.rsqrt; provider GEMM/reduction may differ; every error must be reported with unchanged source accuracy criteria",
        "finite_policy": "slice_actual_retained_rows_before_dispatch; immutable17weights_checked_once; all_inputs_and_derived_arithmetic_checked; false_finite_discards_entire_output",
        "hardware_execution": False, "native_transport_qualified": False,
        "acceptance_qualified": False, "serving_throughput_qualified": False}
    (destination / "export.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"export_receipt": str(destination / "export.json"), "graphs": graphs,
        "external_weights_bytes": receipt["external_weights_bytes"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--precision", choices=("bf16_native", "float_roundtrip", "both"), default="both")
    export(parser.parse_args())


if __name__ == "__main__":
    main()
