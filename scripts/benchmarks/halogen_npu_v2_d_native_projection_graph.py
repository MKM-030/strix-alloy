"""Count1 D projection-only candidate with explicit decoded-weight BF16 RNE.

Root alone builds/verifies real models/assets. The sealed projection helper
supplies the original FC graph with BF16-rounded decoded FP32 weights. This
new graph removes every seed-add/cast/reshape node and exposes the two stored
BF16-widened projections separately. Normalization and seed-add are outside
the segment. Original external FC initializer bytes/data remain unchanged.

The native Q8 affine-FMA decoder and packed BF16 accumulation/reduction remain
unqualified by this FP32 MatMul graph. Actual retained original native FC
outputs must supply the later numerical oracle; no synthetic seed gate or
native graph/full-D/head/acceptance/speed claim is supplied here.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import onnx
from onnx import TensorProto, helper


HERE = Path(__file__).resolve().parent
PROJECTION_HELPER = HERE / "halogen_npu_v2_d_projection_graph.py"
PROJECTION_HELPER_SHA256 = "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd"
BUILDER = HERE / "halogen_npu_v2_d_prepare.py"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
SOURCE_MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
SOURCE_BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
SEED_SUFFIX = ["seed_fp32", "seed_bf16_widened_bf16", "seed_bf16_widened", "seed"]
OUTPUT_SHAPES = {"e_projection": [1, 2560], "h_projection": [4, 2560]}
FC_INITIALIZERS = ("W_embedding", "W_hidden")
ARITHMETIC = "original decoded FP32 weights Cast BF16 RNE then Cast FLOAT; FP32 MatMul; original projection BF16 RNE then FLOAT; RMS and seed-add excluded; native Q8 affine-FMA decoder and accumulation parity unqualified"
FALSE_CLAIMS = ("hardware_placement_qualified", "native_q8_parity_qualified", "native_graph_parity_qualified",
                "native_q8_affine_fma_decoder_qualified", "native_accumulation_parity_qualified", "full_d_claim",
                "full_mtp_claim", "acceptance_claim", "speed_promotion")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for payload in iter(lambda: stream.read(1 << 20), b""):
            value.update(payload)
    return value.hexdigest()


def sealed_helper():
    if digest(PROJECTION_HELPER) != PROJECTION_HELPER_SHA256 or digest(BUILDER) != BUILDER_SHA256:
        raise ValueError("sealed projection helper/original builder identity differs")
    import halogen_npu_v2_d_projection_graph as projection
    if Path(projection.__file__).resolve() != PROJECTION_HELPER:
        raise ValueError("explicit sealed projection helper import path differs")
    return projection


def create_native_projection(source):
    """Transform only protobufs; no model/weight/provider I/O."""
    projection = sealed_helper()
    model = projection.create_projection(source, WEIGHT_LINEAGE)
    if [node.name for node in model.graph.node][-4:] != SEED_SUFFIX:
        raise ValueError("exact original seed suffix required before removal")
    nodes = [deepcopy(node) for node in model.graph.node[:-4]]
    if len(nodes) != 11 or sum(node.op_type == "MatMul" for node in nodes) != 2:
        raise ValueError("exact weight-cast/two-projection graph required")
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    initializers = [deepcopy(value) for value in model.graph.initializer if value.name != "seed_shape"]
    if [value.name for value in initializers] != ["W_embedding", "W_hidden", "stream_shape"]:
        raise ValueError("exact original FC/stream-shape initializers required")
    del model.graph.initializer[:]
    model.graph.initializer.extend(initializers)
    del model.graph.output[:]
    model.graph.output.extend(helper.make_tensor_value_info(name, TensorProto.FLOAT, shape)
                              for name, shape in OUTPUT_SHAPES.items())
    model.graph.name = "halogen_v2_count1_D_native_projection"
    props = {entry.key: entry.value for entry in model.metadata_props}
    props.update(transformer_sha256=digest(__file__), projection_helper_sha256=PROJECTION_HELPER_SHA256,
                 arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE,
                 output_scope="separate original stored e/h projections, exactly BF16-widened FLOAT; no seed output",
                 scope="native-oriented projection-only candidate; RMS/seed-add outside segment; native decoder/accumulation/graph/full-D/head/acceptance/speed unqualified")
    helper.set_model_props(model, props)
    return model


def metadata(model):
    result = sealed_helper().metadata(model, WEIGHT_LINEAGE)
    result.update(output_shapes=OUTPUT_SHAPES, seed_add_in_segment=False,
                  projection_output_boundaries_preserved=True,
                  native_graph_parity_qualified=False, native_accumulation_parity_qualified=False,
                  numerical_oracle="actual retained original native FC outputs on explicitly identical normalized BF16 inputs",
                  projection_helper_sha256=PROJECTION_HELPER_SHA256)
    return result


def source_binding(source_model, source_build_receipt, source_build_sha256):
    if source_build_sha256 != SOURCE_BUILD_SHA256 or digest(source_model) != SOURCE_MODEL_SHA256:
        raise ValueError("frozen original model/build identity differs")
    return sealed_helper().source_binding(source_model, source_build_receipt, source_build_sha256)


def transform(source_model, source_build_receipt, source_build_sha256, output):
    source_model = Path(source_model).resolve(strict=True)
    output = Path(output).resolve()
    report, partial, lock = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent:
        raise ValueError("candidate must stay beside immutable original external data")
    if any(path.exists() for path in (output, report, partial, lock)):
        raise FileExistsError("existing native-projection graph/receipt/partial/lock refused")
    with lock.open("x", encoding="utf-8"):
        source_hash = digest(__file__)
        build, source = source_binding(source_model, source_build_receipt, source_build_sha256)
        candidate = create_native_projection(source)
        original_fc = [value.SerializeToString() for value in source.graph.initializer if value.name in FC_INITIALIZERS]
        actual_fc = [value.SerializeToString() for value in candidate.graph.initializer if value.data_location == TensorProto.EXTERNAL]
        if original_fc != actual_fc:
            raise ValueError("immutable original external FC initializers changed")
        with partial.open("xb") as stream:
            stream.write(candidate.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        sealed_helper()
        if (digest(__file__) != source_hash or digest(source_model) != SOURCE_MODEL_SHA256 or
                digest(build["data"]) != build["data_sha256"]):
            raise ValueError("sealed transformer/original graph/data changed during transform")
        os.rename(partial, output)
        result = dict(schema="halogen_v2_count1_D_native_projection_graph.v1", wire_mode="D", count=1,
                      arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE,
                      transformer_sha256=source_hash, projection_helper_sha256=PROJECTION_HELPER_SHA256,
                      builder_sha256=BUILDER_SHA256, source_model=str(source_model), source_model_sha256=SOURCE_MODEL_SHA256,
                      source_build_receipt=str(Path(source_build_receipt).resolve()), source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                      model=str(output), model_sha256=digest(output), data=build["data"], data_sha256=build["data_sha256"],
                      data_bytes=build["data_bytes"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      original_external_data_unchanged=True, no_external_weight_copy=True,
                      normalization_in_segment=False, seed_add_in_segment=False,
                      metadata=metadata(candidate), **{key: False for key in FALSE_CLAIMS})
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    lock.unlink()
    return result


def verify_native_projection(model_path, receipt_path, receipt_sha256):
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    result = sealed_helper().receipt(receipt_path, sha(receipt_sha256))
    required = dict(schema="halogen_v2_count1_D_native_projection_graph.v1", wire_mode="D", count=1,
                    arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE, transformer_sha256=digest(__file__),
                    projection_helper_sha256=PROJECTION_HELPER_SHA256, builder_sha256=BUILDER_SHA256,
                    source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                    model=str(model_path))
    if (receipt_path != Path(str(model_path) + ".json") or any(result.get(key) != value for key, value in required.items()) or
            any(result.get(key) is not False for key in (*FALSE_CLAIMS, "normalization_in_segment", "seed_add_in_segment")) or
            result.get("original_external_data_unchanged") is not True or result.get("no_external_weight_copy") is not True or
            digest(model_path) != result["model_sha256"]):
        raise ValueError("native-projection source/model/receipt contract differs")
    source_path = Path(result["source_model"]).resolve(strict=True)
    if source_path.parent != model_path.parent:
        raise ValueError("source/candidate external-data folder differs")
    build, source = source_binding(source_path, result["source_build_receipt"], result["source_build_receipt_sha256"])
    if any(result[key] != build[key] for key in ("data", "data_sha256", "data_bytes", "assets_receipt_sha256")):
        raise ValueError("immutable original FC external-data binding differs")
    expected = create_native_projection(source)
    actual = onnx.load(str(model_path), load_external_data=False)
    if actual.SerializeToString() != expected.SerializeToString() or result["metadata"] != metadata(expected):
        raise ValueError("exact projection-only graph/parser metadata proof differs")
    sealed_helper()
    if digest(receipt_path) != receipt_sha256 or digest(model_path) != result["model_sha256"]:
        raise ValueError("native-projection model/receipt changed during verification")
    return result, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--source-build-receipt", type=Path, required=True)
    parser.add_argument("--source-build-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    print(json.dumps(transform(args.source_model, args.source_build_receipt,
                               sha(args.source_build_receipt_sha256), args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
