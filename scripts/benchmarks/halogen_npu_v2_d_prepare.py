"""Receipt-bound, count1 D preparation graph and ordinary CPU reference.

Inputs e[1,2560] and h[1,10240] are FLOAT values already widened exactly from
BF16 words. The gathered embedding row is an explicit input cut. RMS gamma,
epsilon, multiplication order and BF16 boundaries follow retained native D
source evidence. FP32 MatMul and CPU sqrt/reciprocal are a canonical algebra
reference, not qualified native GEMM/rsq bit arithmetic. No provider or native
engine is imported or initialized here. Actual live wire mode is unobserved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from collections import Counter

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WIDTH, STREAMS = 2560, 4
DATA_BYTES = 52_480_000
MAX_JSON_BYTES, TILE_BYTES = 8 << 20, 8 << 20
CHECKPOINT_SHA256 = "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687"
METADATA_SHA256 = "4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb"
HEADER_SHA256 = "9e522122a6deedf7f966108b1902939d376126f4888c28ec183f3f6460a937c7"
TABLE_SHA256 = "2302900dfe860fd7a689c90bdf1d3fe674d78aa8bf3c166e05000c9d5e5e9ceb"
STATIC_AUDIT = ROOT / "server/.local/optimization9h-20261004/mtp-route-static-20261004/cpu-d-input-static-audit.json"
STATIC_AUDIT_SHA256 = "ece0f957bcd39016cf48398346475b5658a23c20bcdd8fa27319018c2de55be2"
READER_SHA256 = {
    "halogen_npu_v2_head_assets.py": "582e292581cc85b06be9af86e82af5bdc694a6a277cfbc416ae7a11e3343a870",
    "hgn_q8g64_slice.py": "1bb7c274688d77f4d2181866cbebfd170e33031934aaeb32f43b0cdf73a65d23",
    "hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "halogen_npu_v2_sparse.py": "345f18778deeac5ade76c69f26f6bd2296741a55130d33a9caa0f6506f7e5c79",
    "halogen_npu_mtp_metadata.py": "25e25cf244e1da93d1fefa510ec0c95aefafb29d7fd8d0098237fb55adec0455",
    "hgn_ht_slice.py": "4e0c72fdf63d8e1c12ed90c11f9400aa65ee3f531a9157a8257d6ebb899bd3c7",
    "hgn_ht_slice.NOTICE.md": "2888732b9ff5b0c3b1bf69b85055492ee39e5717ce4b02aac74ae25cabb89dc3",
    "hgn_ht_slice.LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
}
# Stable output layout: FC arrays are transposed to [in,out], norms remain raw.
LAYOUT = (
    ("mtp.fc_embedding.weight", "W_embedding", [WIDTH, WIDTH], 0, 26_214_400, (7, 0)),
    ("mtp.fc_hidden.weight", "W_hidden", [WIDTH, WIDTH], 26_214_400, 26_214_400, (7, 0)),
    ("mtp.pre_fc_norm_embedding.weight", "gamma_embedding", [WIDTH], 52_428_800, 10_240, (0, 0)),
    ("mtp.pre_fc_norm_hidden.weight", "gamma_hidden", [STREAMS * WIDTH], 52_439_040, 40_960, (0, 0)),
)
ARITHMETIC = "canonical FP32 RMS/MatMul with explicit BF16 RNE boundaries; native GEMM/rsq parity unqualified"


def require_d(wire_mode):
    if wire_mode != "D":
        raise ValueError("explicit wire_mode=D is required; default is not an observation")


def require_sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def small_json(path, expected_sha256):
    require_sha(expected_sha256)
    path = Path(path).resolve(strict=True)
    if not 0 < path.stat().st_size <= MAX_JSON_BYTES:
        raise ValueError("receipt exceeds bounded JSON size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("receipt SHA256 differs")
    return json.loads(raw)


def identity(path):
    value = Path(path).stat()
    return (value.st_size, value.st_dev, value.st_ino, value.st_mtime_ns, value.st_ctime_ns)


def bf16_rne(value):
    """Round finite FP32 to BF16, nearest with even ties; return widened FP32."""
    value = np.asarray(value, dtype=np.float32)
    if not np.isfinite(value).all():
        raise ValueError("BF16 conversion requires finite FP32")
    bits = np.ascontiguousarray(value).view(np.uint32)
    rounded = (bits + np.uint32(0x7fff) + ((bits >> 16) & 1)) & np.uint32(0xffff0000)
    result = rounded.view(np.float32).reshape(value.shape)
    if not np.isfinite(result).all():
        raise ValueError("BF16 conversion overflow")
    return result


def widen_bf16(words):
    words = np.asarray(words)
    if words.dtype != np.dtype("<u2"):
        raise ValueError("BF16 words must have little-endian uint16 dtype")
    result = (words.astype(np.uint32) << 16).view(np.float32)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite BF16 input")
    return result


def bf16_input(value, shape, label):
    value = np.asarray(value)
    if value.dtype != np.dtype("float32") or list(value.shape) != list(shape):
        raise ValueError(label + " must be count1 FLOAT " + str(shape))
    value = np.ascontiguousarray(value)
    if not np.isfinite(value).all() or np.any(value.view(np.uint32) & 0xffff):
        raise ValueError(label + " must be finite, exactly BF16-widened FLOAT")
    return value


def rms_bf16(value, raw_gamma):
    """One whole-row group; preserves native product order, ordinary FP32 rsqrt."""
    value = np.asarray(value)
    if value.ndim != 2:
        raise ValueError("RMS input must be rank2")
    value = bf16_input(value, value.shape, "RMS input")
    raw_gamma = bf16_input(raw_gamma, [value.shape[-1]], "raw RMS gamma")
    squared = np.multiply(value, value, dtype=np.float32)
    mean = np.mean(squared, axis=-1, keepdims=True, dtype=np.float32)
    epsilon = np.array([0x358637bd], dtype=np.uint32).view(np.float32)[0]
    inverse = np.reciprocal(np.sqrt(mean + epsilon, dtype=np.float32), dtype=np.float32)
    first = np.multiply(value, inverse, dtype=np.float32)
    gamma = np.add(raw_gamma, np.float32(1), dtype=np.float32)
    return bf16_rne(np.multiply(first, gamma, dtype=np.float32))


def reference(e, h, weights, wire_mode):
    require_d(wire_mode)
    e = bf16_input(e, [1, WIDTH], "e")
    h = bf16_input(h, [1, STREAMS * WIDTH], "h")
    for _, name, shape, _, _, _ in LAYOUT:
        if name not in weights or list(weights[name].shape) != shape or weights[name].dtype != np.dtype("float32"):
            raise ValueError("reference weight geometry/dtype differs: " + name)
    normalized_e = rms_bf16(e, weights["gamma_embedding"])
    normalized_h = rms_bf16(h, weights["gamma_hidden"]).reshape(STREAMS, WIDTH)
    projected_e = bf16_rne(normalized_e @ weights["W_embedding"])
    projected_h = bf16_rne(normalized_h @ weights["W_hidden"])
    return bf16_rne(np.add(projected_h, projected_e, dtype=np.float32)).reshape(1, STREAMS, WIDTH)


def verify_assets(receipt_path, receipt_sha256):
    """Read only exporter output/receipts and small frozen source files."""
    receipt_path = Path(receipt_path).resolve(strict=True)
    receipt = small_json(receipt_path, receipt_sha256)
    plan_path = Path(receipt["prepared_plan"]).resolve(strict=True)
    if plan_path.parent != receipt_path.parent:
        raise ValueError("prepared plan must be beside asset receipt")
    plan = small_json(plan_path, receipt["prepared_plan_sha256"])
    source = receipt["source"]
    if (receipt.get("schema") != 1 or source != plan.get("source") or
            source.get("checkpoint_sha256") != CHECKPOINT_SHA256 or
            source.get("header_sha256") != HEADER_SHA256 or source.get("table_sha256") != TABLE_SHA256 or
            source.get("receipt_sha256", {}).get("metadata") != METADATA_SHA256 or
            receipt.get("source_identity_after") != source.get("native_identity") or
            source.get("native_identity", {}).get("size") != 66_687_678_432 or
            receipt.get("reader_sources") != READER_SHA256 or plan.get("reader_sources") != READER_SHA256 or
            receipt.get("data_bytes") != DATA_BYTES or plan.get("output_bytes") != DATA_BYTES or
            receipt.get("dtype") != plan.get("dtype") or not receipt["dtype"].startswith("little-endian FP32; stored row orientation;")):
        raise ValueError("frozen v2 source/decoder lineage differs")
    for name, expected in READER_SHA256.items():
        if digest(HERE / name) != expected:
            raise ValueError("frozen reader source differs: " + name)
    small_json(STATIC_AUDIT, STATIC_AUDIT_SHA256)
    data = Path(receipt["data"]).resolve(strict=True)
    if data.parent != receipt_path.parent or data.stat().st_size != DATA_BYTES:
        raise ValueError("asset data location/extent differs")
    if any(Path(str(data) + suffix).exists() for suffix in (".partial",)):
        raise ValueError("partial asset writer exists")
    prefix = str(data)[:-5] if str(data).endswith(".data") else str(data)
    if Path(prefix + ".lock").exists():
        raise ValueError("asset writer lock exists")
    tensors = receipt["tensors"]
    if len(tensors) != 4 or len(plan["tensors"]) != 4 or {item["name"] for item in tensors} != {item[0] for item in LAYOUT}:
        raise ValueError("exact four complete D tensors required")
    by_name = {item["name"]: item for item in tensors}
    plans = {item["entry"]["name"]: item for item in plan["tensors"]}
    regions = {}
    for source_name, _, shape, _, length, encoding in LAYOUT:
        item, item_plan = by_name[source_name], plans[source_name]
        entry, external = item["source_entry"], item["external_data"]
        rows = shape[0] if len(shape) == 2 else 1
        source_size = rows * (shape[-1] + shape[-1] // 16) if encoding == (7, 0) else shape[-1] * 2
        if (entry != item_plan["entry"] or entry["name"] != source_name or entry["dims"] != shape or
                (entry["store"], entry["variant"]) != encoding or entry["rank"] != len(shape) or entry["size"] != source_size or
                item["row_start"] != 0 or item["rows"] != rows or item["shape"] != shape or
                item_plan["row_start"] != 0 or item_plan["rows"] != rows or item_plan["output_shape"] != shape or
                item["sideplanes"] is not None or item_plan["sideplanes"] is not None or
                item["reference"] != item_plan["reference"] or external["location"] != data.name or
                external["offset"] != item_plan["output_offset"] or external["length"] != length or item_plan["output_bytes"] != length or
                type(external["offset"]) is not int or not 0 <= external["offset"] <= DATA_BYTES - length):
            raise ValueError("D tensor geometry/encoding/extent differs: " + source_name)
        regions[source_name] = external
        next_row = 0
        row_bytes = source_size // rows
        for tile in item_plan["tiles"]:
            count = tile["rows"]
            if (type(count) is not int or not 0 < count <= rows - next_row or
                    tile["row_start"] != next_row or tile["decoded_bytes"] != count * shape[-1] * 4 or
                    tile["output_offset"] != external["offset"] + next_row * shape[-1] * 4 or
                    tile["source_ranges"] != [dict(name=source_name, offset=entry["offset"] + next_row * row_bytes,
                                                   bytes=count * row_bytes)]):
                raise ValueError("D tensor tile row/source coverage differs: " + source_name)
            next_row += count
        if next_row != rows:
            raise ValueError("D tensor tile coverage is incomplete: " + source_name)
    next_byte = 0
    for region in sorted(regions.values(), key=lambda item: item["offset"]):
        if region["offset"] != next_byte:
            raise ValueError("D tensor external-data regions overlap or have gaps")
        next_byte += region["length"]
    if next_byte != DATA_BYTES:
        raise ValueError("D tensor external-data coverage is incomplete")
    planned_tiles = [dict(tensor=item["entry"]["name"], **tile) for item in plan["tensors"] for tile in item["tiles"]]
    actual_tiles = receipt["tiles"]
    if len(planned_tiles) != len(actual_tiles) or not 1 <= len(actual_tiles) <= 4096:
        raise ValueError("asset tile count differs")
    before = identity(data)
    complete, cursor = hashlib.sha256(), 0
    with data.open("rb") as stream:
        for expected, actual in zip(planned_tiles, actual_tiles):
            amount = actual["output_bytes"]
            if (type(amount) is not int or not 0 < amount <= TILE_BYTES or actual["output_offset"] != cursor or
                    any(actual[key] != expected[key] for key in ("tensor", "row_start", "rows", "output_offset")) or
                    amount != expected["decoded_bytes"] or actual["reference"] != by_name[actual["tensor"]]["reference"] or
                    [{key: row[key] for key in ("name", "offset", "bytes")} for row in actual["source_ranges"]] != expected["source_ranges"]):
                raise ValueError("asset tile coverage/lineage differs")
            for row in actual["source_ranges"]:
                require_sha(row["sha256"])
            payload = stream.read(amount)
            if len(payload) != amount or hashlib.sha256(payload).hexdigest() != require_sha(actual["decoded_sha256"]):
                raise ValueError("asset tile SHA256 differs")
            complete.update(payload)
            cursor += amount
        if cursor != DATA_BYTES or stream.read(1) or complete.hexdigest() != require_sha(receipt["data_sha256"]):
            raise ValueError("asset complete data SHA256 differs")
    if identity(data) != before or digest(receipt_path) != receipt_sha256 or digest(plan_path) != receipt["prepared_plan_sha256"]:
        raise ValueError("asset data/receipt changed while verifying")
    return receipt, data, regions


def create_graph(data_location, assets_receipt_sha256):
    require_sha(assets_receipt_sha256)
    if Path(data_location).name != data_location:
        raise ValueError("graph external data must be a sibling filename")
    initializers = []
    for _, name, shape, offset, length, _ in LAYOUT:
        tensor = TensorProto(name=name, data_type=TensorProto.FLOAT, dims=shape,
                             data_location=TensorProto.EXTERNAL)
        for key, value in (("location", data_location), ("offset", str(offset)), ("length", str(length))):
            field = tensor.external_data.add()
            field.key, field.value = key, value
        initializers.append(tensor)
    initializers.extend([
        numpy_helper.from_array(np.array([1], dtype=np.float32), "one"),
        numpy_helper.from_array(np.array([0x358637bd], dtype=np.uint32).view(np.float32), "epsilon"),
        numpy_helper.from_array(np.array([-1], dtype=np.int64), "norm_axis"),
        numpy_helper.from_array(np.array([STREAMS, WIDTH], dtype=np.int64), "stream_shape"),
        numpy_helper.from_array(np.array([1, STREAMS, WIDTH], dtype=np.int64), "seed_shape"),
    ])
    nodes = []
    def node(op, inputs, output, **attrs):
        nodes.append(helper.make_node(op, inputs, [output], name=output, **attrs))
    def round_bf16(value, output):
        node("Cast", [value], output + "_bf16", to=TensorProto.BFLOAT16)
        node("Cast", [output + "_bf16"], output, to=TensorProto.FLOAT)
    for branch in ("e", "h"):
        gamma = "gamma_embedding" if branch == "e" else "gamma_hidden"
        node("Mul", [branch, branch], branch + "_square")
        node("ReduceMean", [branch + "_square", "norm_axis"], branch + "_mean", keepdims=1)
        node("Add", [branch + "_mean", "epsilon"], branch + "_mean_eps")
        node("Sqrt", [branch + "_mean_eps"], branch + "_rms")
        node("Reciprocal", [branch + "_rms"], branch + "_inverse_rms")
        node("Mul", [branch, branch + "_inverse_rms"], branch + "_unit")
        node("Add", [gamma, "one"], branch + "_gamma_plus_one")
        node("Mul", [branch + "_unit", branch + "_gamma_plus_one"], branch + "_norm_fp32")
        round_bf16(branch + "_norm_fp32", branch + "_norm")
    node("Reshape", ["h_norm", "stream_shape"], "h_streams")
    node("MatMul", ["e_norm", "W_embedding"], "e_projection_fp32")
    node("MatMul", ["h_streams", "W_hidden"], "h_projection_fp32")
    round_bf16("e_projection_fp32", "e_projection")
    round_bf16("h_projection_fp32", "h_projection")
    node("Add", ["h_projection", "e_projection"], "seed_fp32")
    round_bf16("seed_fp32", "seed_bf16_widened")
    node("Reshape", ["seed_bf16_widened", "seed_shape"], "seed")
    graph = helper.make_graph(nodes, "halogen_v2_count1_D_preparation",
                              [helper.make_tensor_value_info("e", TensorProto.FLOAT, [1, WIDTH]),
                               helper.make_tensor_value_info("h", TensorProto.FLOAT, [1, STREAMS * WIDTH])],
                              [helper.make_tensor_value_info("seed", TensorProto.FLOAT, [1, STREAMS, WIDTH])], initializers)
    model = helper.make_model(graph, producer_name="strix-alloy-halogen-D-preparation",
                              opset_imports=[helper.make_opsetid("", 21)])
    model.ir_version = 13
    helper.set_model_props(model, {"wire_mode": "D", "count": "1", "assets_receipt_sha256": assets_receipt_sha256,
                                  "static_audit_sha256": STATIC_AUDIT_SHA256, "arithmetic": ARITHMETIC,
                                  "input_cut": "already gathered embedding and residual; exact BF16-widened FLOAT",
                                  "scope": "standalone D preparation; no history/full head/native parity/acceptance claim"})
    return model


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def build(assets_receipt, assets_receipt_sha256, model_path, wire_mode):
    require_d(wire_mode)
    model_path = Path(model_path).resolve()
    data_path, report_path = Path(str(model_path) + ".data"), Path(str(model_path) + ".json")
    partial = Path(str(data_path) + ".partial")
    if any(path.exists() for path in (model_path, data_path, report_path, partial)):
        raise FileExistsError("existing graph/data/receipt/partial refused")
    receipt, source, regions = verify_assets(assets_receipt, assets_receipt_sha256)
    source_before = identity(source)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with partial.open("xb") as stream:
        stream.truncate(DATA_BYTES)
    for source_name, _, shape, offset, _, _ in LAYOUT:
        original = np.memmap(source, mode="r", dtype="<f4", offset=regions[source_name]["offset"], shape=tuple(shape))
        target = np.memmap(partial, mode="r+", dtype="<f4", offset=offset, shape=tuple(shape))
        if len(shape) == 2:
            for start in range(0, WIDTH, 256):
                tile = original[start:start + 256]
                if not np.isfinite(tile).all():
                    raise ValueError("nonfinite FC asset")
                target[:, start:start + 256] = tile.T
        else:
            bf16_input(original, shape, source_name)
            target[:] = original
        target.flush()
        del target, original
    with partial.open("r+b") as stream:
        os.fsync(stream.fileno())
    if identity(source) != source_before or digest(source) != receipt["data_sha256"]:
        raise ValueError("asset source changed during graph packing")
    # Recheck receipt/source seals before publishing any usable graph.
    verify_assets(assets_receipt, assets_receipt_sha256)
    os.rename(partial, data_path)
    model = create_graph(data_path.name, assets_receipt_sha256)
    with model_path.open("xb") as stream:
        stream.write(model.SerializeToString())
        stream.flush()
        os.fsync(stream.fileno())
    onnx.checker.check_model(str(model_path))
    report = dict(schema="halogen_v2_count1_D_prepare.v1", wire_mode="D", count=1, arithmetic=ARITHMETIC,
                  model=str(model_path), model_sha256=digest(model_path), data=str(data_path),
                  data_bytes=DATA_BYTES, data_sha256=digest(data_path),
                  assets_receipt=str(Path(assets_receipt).resolve()), assets_receipt_sha256=assets_receipt_sha256,
                  assets_data_sha256=receipt["data_sha256"], static_audit_sha256=STATIC_AUDIT_SHA256,
                  builder_sha256=digest(__file__), input_shapes={"e": [1, WIDTH], "h": [1, STREAMS * WIDTH]},
                  output_shape=[1, STREAMS, WIDTH], nodes=[dict(name=node.name, op_type=node.op_type,
                  inputs=list(node.input), outputs=list(node.output)) for node in model.graph.node],
                  operator_counts=dict(Counter(node.op_type for node in model.graph.node)),
                  layout=[dict(source=name, graph_name=graph_name, shape=shape,
                  offset=offset, bytes=length) for name, graph_name, shape, offset, length, _ in LAYOUT])
    write_json(report_path, report)
    return report


def verify_model(model_path, build_receipt_path, build_receipt_sha256, wire_mode):
    require_d(wire_mode)
    model_path = Path(model_path).resolve(strict=True)
    report_path = Path(build_receipt_path).resolve(strict=True)
    report = small_json(report_path, build_receipt_sha256)
    data_path = Path(str(model_path) + ".data")
    if (report_path != Path(str(model_path) + ".json") or report.get("schema") != "halogen_v2_count1_D_prepare.v1" or
            report.get("wire_mode") != "D" or report.get("count") != 1 or report.get("arithmetic") != ARITHMETIC or
            report.get("model") != str(model_path) or report.get("data") != str(data_path) or
            report.get("data_bytes") != DATA_BYTES or report.get("builder_sha256") != digest(__file__) or
            report.get("static_audit_sha256") != STATIC_AUDIT_SHA256 or
            data_path.stat().st_size != DATA_BYTES or digest(model_path) != report["model_sha256"] or
            digest(data_path) != report["data_sha256"]):
        raise ValueError("frozen D graph/build/data receipt differs")
    assets, _, _ = verify_assets(report["assets_receipt"], report["assets_receipt_sha256"])
    if assets["data_sha256"] != report["assets_data_sha256"]:
        raise ValueError("graph assets lineage differs")
    actual = onnx.load(str(model_path), load_external_data=False)
    expected = create_graph(data_path.name, report["assets_receipt_sha256"])
    if actual.SerializeToString() != expected.SerializeToString():
        raise ValueError("D model differs from exact graph contract")
    weights = {name: np.memmap(data_path, mode="r", dtype="<f4", offset=offset, shape=tuple(shape))
               for _, name, shape, offset, _, _ in LAYOUT}
    if digest(report_path) != build_receipt_sha256:
        raise ValueError("build receipt changed during verification")
    return report, weights


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--assets-sha256", required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    result = build(args.assets, args.assets_sha256, args.build, args.wire_mode)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
