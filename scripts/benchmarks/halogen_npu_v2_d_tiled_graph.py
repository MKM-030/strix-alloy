"""Immutable fixed-256 whole-row RMS candidate for count1 D preparation.

Root alone builds/verifies with real graph/assets. Each RMS squares packed
[1,tiles,256] input, reduces features then tiles, and multiplies by FP32
1/width. The whole width remains2560/10240; gamma/epsilon/product order and
BF16 boundaries are preserved. FP32 reduction order changes explicitly.

Partial sums are observable graph outputs to preserve the two-stage reduction
boundary. Norm outputs are diagnostics. Avoiding the compiler's large
SinglePassRMSNorm lowering remains an actual compile gate, not a source claim.
No provider/native parity/head/acceptance/speed promotion is supplied here.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


HERE = Path(__file__).resolve().parent
BUILDER = HERE / "halogen_npu_v2_d_prepare.py"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
SOURCE_MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
SOURCE_BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
TILE_WIDTH = 256
WIDTHS = {"e": 2560, "h": 10240}
OUTPUT_NAMES = ["seed", "e_partial_sums", "h_partial_sums", "e_norm", "h_norm"]
ARITHMETIC = "FP32 square; fixed256 feature ReduceSum then tile ReduceSum; FP32 reciprocal-width multiplication; reduction order changed; native parity unqualified"
MAX_JSON_BYTES = 2 << 20


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def read_receipt(path, expected):
    sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not 0 < before.st_size <= MAX_JSON_BYTES:
        raise ValueError("tiled receipt exceeds bounded size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    after = path.stat()
    attrs = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if (len(raw) > MAX_JSON_BYTES or hashlib.sha256(raw).hexdigest() != expected or
            any(getattr(before, name) != getattr(after, name) for name in attrs)):
        raise ValueError("tiled receipt hash/identity differs")
    return json.loads(raw)


def create_tiled(source):
    """Pure protobuf transform; no model/weight/provider I/O."""
    if [value.name for value in source.graph.output] != ["seed"]:
        raise ValueError("source must be the frozen seed-only D graph")
    model = deepcopy(source)
    nodes = []
    for original in model.graph.node:
        if original.name in ("e_square", "h_square"):
            continue
        if original.name in ("e_mean", "h_mean"):
            branch = original.name[0]
            width = WIDTHS[branch]
            if original.op_type != "ReduceMean" or list(original.input) != [branch + "_square", "norm_axis"]:
                raise ValueError("source RMS node contract differs")
            def add(op, inputs, output, **attrs):
                nodes.append(helper.make_node(op, inputs, [output], name=output, **attrs))
            add("Reshape", [branch, branch + "_tile_shape"], branch + "_tiles")
            add("Mul", [branch + "_tiles", branch + "_tiles"], branch + "_tiled_square")
            add("ReduceSum", [branch + "_tiled_square", "tile_feature_axis"], branch + "_partial_sums", keepdims=1)
            add("ReduceSum", [branch + "_partial_sums", "tile_group_axis"], branch + "_row_sum_3d", keepdims=1)
            add("Reshape", [branch + "_row_sum_3d", "rms_scalar_shape"], branch + "_row_sum")
            add("Mul", [branch + "_row_sum", branch + "_inv_width"], branch + "_mean")
        else:
            nodes.append(deepcopy(original))
    if len(nodes) != len(source.graph.node) + 8:
        raise ValueError("exact two RMS replacements required")
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    for branch, width in WIDTHS.items():
        model.graph.initializer.extend([
            numpy_helper.from_array(np.array([1, width // TILE_WIDTH, TILE_WIDTH], dtype=np.int64), branch + "_tile_shape"),
            numpy_helper.from_array(np.array([np.float32(1.0 / width)], dtype=np.float32), branch + "_inv_width"),
        ])
    model.graph.initializer.extend([
        numpy_helper.from_array(np.array([2], dtype=np.int64), "tile_feature_axis"),
        numpy_helper.from_array(np.array([1], dtype=np.int64), "tile_group_axis"),
        numpy_helper.from_array(np.array([1, 1], dtype=np.int64), "rms_scalar_shape"),
    ])
    model.graph.output.extend([
        helper.make_tensor_value_info("e_partial_sums", TensorProto.FLOAT, [1, 10, 1]),
        helper.make_tensor_value_info("h_partial_sums", TensorProto.FLOAT, [1, 40, 1]),
        helper.make_tensor_value_info("e_norm", TensorProto.FLOAT, [1, 2560]),
        helper.make_tensor_value_info("h_norm", TensorProto.FLOAT, [1, 10240]),
    ])
    props = {entry.key: entry.value for entry in model.metadata_props}
    props.update(source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                 transformer_sha256=digest(__file__), rms_tile_width=str(TILE_WIDTH), arithmetic=ARITHMETIC,
                 output_scope="seed plus observable partial sums and normalized BF16-widened diagnostics; host cost includes extra outputs",
                 scope="standalone tiled D graph candidate; changed FP32 reduction order; no native/full-head/acceptance/speed promotion")
    helper.set_model_props(model, props)
    return model


def source_binding(source_model, source_build_receipt, source_build_sha256):
    if source_build_sha256 != SOURCE_BUILD_SHA256 or digest(BUILDER) != BUILDER_SHA256:
        raise ValueError("frozen original builder/build receipt identity differs")
    import halogen_npu_v2_d_prepare as builder
    source_model = Path(source_model).resolve(strict=True)
    if digest(source_model) != SOURCE_MODEL_SHA256:
        raise ValueError("frozen original D graph identity differs")
    build, weights = builder.verify_model(source_model, source_build_receipt, source_build_sha256, "D")
    weights = None
    model = onnx.load(str(source_model), load_external_data=False)
    return build, model


def output_metadata(model):
    dynamic = {value.name for value in model.graph.input}
    required, constant = set(), set()
    for node in model.graph.node:
        if any(name in dynamic for name in node.input):
            dynamic.update(node.output)
            required.update(node.output)
        else:
            constant.update(node.output)
    return dict(output_names=[value.name for value in model.graph.output],
                nodes=[dict(name=node.name, op_type=node.op_type, inputs=list(node.input), outputs=list(node.output)) for node in model.graph.node],
                operator_counts=dict(Counter(node.op_type for node in model.graph.node)),
                required_hardware_partition_outputs=sorted(required), constant_foldable_node_outputs=sorted(constant),
                whole_row_rms={branch: dict(width=width, tile_width=TILE_WIDTH, tiles=width // TILE_WIDTH,
                square_shape=[1, width // TILE_WIDTH, TILE_WIDTH], feature_reduction_axis=2,
                partial_sums_shape=[1, width // TILE_WIDTH, 1], tile_reduction_axis=1,
                scalar_mean_shape=[1, 1], normalization_groups=1) for branch, width in WIDTHS.items()})


def transform(source_model, source_build_receipt, source_build_sha256, output):
    source_model = Path(source_model).resolve(strict=True)
    output = Path(output).resolve()
    receipt_path, partial, lock_path = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent:
        raise ValueError("new graph must remain beside immutable original external data; no copy/requantization")
    if any(path.exists() for path in (output, receipt_path, partial, lock_path)):
        raise FileExistsError("existing tiled graph/receipt/partial/lock refused")
    with lock_path.open("x", encoding="utf-8"):
        build, source = source_binding(source_model, source_build_receipt, source_build_sha256)
        candidate = create_tiled(source)
        original_external = [value.SerializeToString() for value in source.graph.initializer if value.data_location == TensorProto.EXTERNAL]
        candidate_external = [value.SerializeToString() for value in candidate.graph.initializer if value.data_location == TensorProto.EXTERNAL]
        if original_external != candidate_external:
            raise ValueError("original immutable external initializers changed")
        with partial.open("xb") as stream:
            stream.write(candidate.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        if digest(source_model) != SOURCE_MODEL_SHA256 or digest(build["data"]) != build["data_sha256"]:
            raise ValueError("original graph/data changed during transform")
        os.rename(partial, output)
        receipt = dict(schema="halogen_v2_count1_D_tiled_graph.v1", wire_mode="D", count=1, tile_width=TILE_WIDTH,
                       arithmetic=ARITHMETIC, fp32_reduction_order_changed=True, compiler_fusion_avoidance_qualified=False,
                       native_parity_qualified=False, full_mtp_claim=False, acceptance_claim=False, speed_promotion=False,
                       transformer_sha256=digest(__file__), builder_sha256=BUILDER_SHA256,
                       source_model=str(source_model), source_model_sha256=SOURCE_MODEL_SHA256,
                       source_build_receipt=str(Path(source_build_receipt).resolve()), source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                       model=str(output), model_sha256=digest(output), data=build["data"], data_sha256=build["data_sha256"],
                       data_bytes=build["data_bytes"], assets_receipt_sha256=build["assets_receipt_sha256"],
                       no_asset_copy_or_requantization=True, metadata=output_metadata(candidate))
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    lock_path.unlink()
    return receipt


def verify_tiled(model_path, receipt_path, receipt_sha256):
    model_path = Path(model_path).resolve(strict=True)
    receipt_path = Path(receipt_path).resolve(strict=True)
    receipt = read_receipt(receipt_path, receipt_sha256)
    if (receipt_path != Path(str(model_path) + ".json") or receipt.get("schema") != "halogen_v2_count1_D_tiled_graph.v1" or
            receipt.get("wire_mode") != "D" or receipt.get("count") != 1 or receipt.get("tile_width") != TILE_WIDTH or
            receipt.get("arithmetic") != ARITHMETIC or receipt.get("transformer_sha256") != digest(__file__) or
            receipt.get("builder_sha256") != BUILDER_SHA256 or receipt.get("model") != str(model_path) or
            digest(model_path) != receipt["model_sha256"] or receipt.get("source_model_sha256") != SOURCE_MODEL_SHA256 or
            receipt.get("source_build_receipt_sha256") != SOURCE_BUILD_SHA256 or
            receipt.get("fp32_reduction_order_changed") is not True or receipt.get("no_asset_copy_or_requantization") is not True or
            any(receipt.get(key) is not False for key in ("compiler_fusion_avoidance_qualified", "native_parity_qualified",
                                                        "full_mtp_claim", "acceptance_claim", "speed_promotion"))):
        raise ValueError("tiled source/model/receipt contract differs")
    source_path = Path(receipt["source_model"]).resolve(strict=True)
    if source_path.parent != model_path.parent:
        raise ValueError("tiled/source graph external-data folder differs")
    build, source = source_binding(source_path, receipt["source_build_receipt"], receipt["source_build_receipt_sha256"])
    if any(receipt[key] != build[key] for key in ("data", "data_sha256", "data_bytes", "assets_receipt_sha256")):
        raise ValueError("immutable original external data binding differs")
    actual = onnx.load(str(model_path), load_external_data=False)
    expected = create_tiled(source)
    if actual.SerializeToString() != expected.SerializeToString() or receipt["metadata"] != output_metadata(expected):
        raise ValueError("exact fixed256 two-stage RMS graph/parser metadata proof differs")
    if digest(receipt_path) != receipt_sha256:
        raise ValueError("tiled receipt changed during verification")
    return receipt, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--source-build-receipt", type=Path, required=True)
    parser.add_argument("--source-build-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    result = transform(args.source_model, args.source_build_receipt, sha(args.source_build_receipt_sha256), args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
