"""Native-oriented count1 D algebra candidate; all native parity unqualified.

Root alone builds/verifies actual models/assets under its owned guards. Reuse
the sealed fixed256 whole-row RMS graph and the sealed projection helper's
explicit decoded-weight Cast BF16 RNE then Cast FLOAT boundary. Preserve the
original epsilon, raw-gamma-plus-one/products, norm/projection/seed BF16 casts
and seed-add nodes. Flatten the final seed to [1,10240] without new arithmetic.

Inputs remain supplied raw BF16 embedding/residual exactly widened to FLOAT.
Hidden RMS still covers the whole 10240 row, never four independent groups.
FP32 reduction order changes. CPU sqrt/reciprocal does not model native rsq;
native embedding RMS remains unqualified. FP32 MatMul does not model the
original native DOT2/chunk/lane schedule. Native Q8 decoder/FC/full-D/head,
acceptance, placement, fusion avoidance and speed claims remain false.

This new immutable graph reuses all original external data unchanged. Partial
sums, normalized words and separate projections are observable diagnostics;
their extra output traffic belongs to the candidate's later runtime cost.
"""
import argparse
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
TILED_HELPER = HERE / "halogen_npu_v2_d_tiled_graph.py"
PROJECTION_HELPER = HERE / "halogen_npu_v2_d_projection_graph.py"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
TILED_HELPER_SHA256 = "52f8bb4f9546135d1d85c5786468cf65ade68cdeda1cd16ffd7efc276ce56485"
PROJECTION_HELPER_SHA256 = "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd"
SOURCE_MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
SOURCE_BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
INPUT_SHAPES = {"e": [1, 2560], "h": [1, 10240]}
OUTPUT_SHAPES = {"seed": [1, 10240], "e_partial_sums": [1, 10, 1], "h_partial_sums": [1, 40, 1],
                 "e_norm": [1, 2560], "h_norm": [1, 10240], "e_projection": [1, 2560], "h_projection": [4, 2560]}
WEIGHT_CAST_NAMES = ["W_embedding_bf16", "W_embedding_bf16_widened", "W_hidden_bf16", "W_hidden_bf16_widened"]
SEED_SUFFIX = ["seed_fp32", "seed_bf16_widened_bf16", "seed_bf16_widened", "seed"]
ARITHMETIC = "fixed256 whole-row FP32 RMS two-stage ReduceSum then reciprocal-width multiplication; changed reduction order; original epsilon/sqrt/reciprocal/raw-gamma-plus-one/products and norm BF16 boundary; decoded FP32 FC weights Cast BF16 RNE then Cast FLOAT; FP32 MatMul and original projection BF16 boundary; original seed-add BF16 boundary; final reshape1x10240; native arithmetic parity unqualified"
FALSE_CLAIMS = ("hardware_placement_qualified", "compiler_fusion_avoidance_qualified", "native_arithmetic_qualified",
                "native_graph_parity_qualified", "native_embedding_rms_qualified", "native_hidden_rms_qualified",
                "native_rsq_instruction_modeled", "native_q8_parity_qualified", "native_q8_affine_fma_decoder_qualified",
                "native_fc_dot2_schedule_modeled", "native_accumulation_parity_qualified", "full_d_claim",
                "full_mtp_claim", "acceptance_claim", "speed_promotion")
DEPENDENCY_SHA256 = {BUILDER.name: BUILDER_SHA256, TILED_HELPER.name: TILED_HELPER_SHA256,
                     PROJECTION_HELPER.name: PROJECTION_HELPER_SHA256}


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


def sealed_helpers():
    for path, expected in ((BUILDER, BUILDER_SHA256), (TILED_HELPER, TILED_HELPER_SHA256),
                           (PROJECTION_HELPER, PROJECTION_HELPER_SHA256)):
        if digest(path) != expected:
            raise ValueError("sealed original builder/RMS/projection helper differs")
    import halogen_npu_v2_d_tiled_graph as tiled
    import halogen_npu_v2_d_projection_graph as projection
    if Path(tiled.__file__).resolve() != TILED_HELPER or Path(projection.__file__).resolve() != PROJECTION_HELPER:
        raise ValueError("explicit sealed helper import path differs")
    return tiled, projection


def create_native_graph(source):
    """Compose reviewed protobuf transforms; no model/weight/provider I/O."""
    tiled, projection = sealed_helpers()
    model = tiled.create_tiled(source)
    projected = projection.create_projection(source, WEIGHT_LINEAGE)
    casts = [deepcopy(node) for node in projected.graph.node if node.name in WEIGHT_CAST_NAMES]
    matmuls = {node.name: deepcopy(node) for node in projected.graph.node if node.op_type == "MatMul"}
    if [node.name for node in casts] != WEIGHT_CAST_NAMES or set(matmuls) != {"e_projection_fp32", "h_projection_fp32"}:
        raise ValueError("exact reviewed four weight casts/two projections required")
    nodes = [*casts, *[deepcopy(matmuls.get(node.name, node)) for node in model.graph.node]]
    if len(nodes) != len(source.graph.node) + 12:
        raise ValueError("exact fixed256 RMS plus four weight casts required")
    original_seed = [node.SerializeToString() for node in source.graph.node if node.name in SEED_SUFFIX]
    candidate_seed = [node.SerializeToString() for node in nodes if node.name in SEED_SUFFIX]
    if len(original_seed) != 4 or original_seed != candidate_seed:
        raise ValueError("original seed-add/BF16/reshape nodes changed")
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    if sum(value.name == "seed_shape" for value in model.graph.initializer) != 1:
        raise ValueError("exact original final seed-shape initializer required")
    for index, value in enumerate(model.graph.initializer):
        if value.name == "seed_shape":
            model.graph.initializer[index].CopyFrom(numpy_helper.from_array(np.array([1, 10240], dtype=np.int64), "seed_shape"))
    del model.graph.output[:]
    model.graph.output.extend(helper.make_tensor_value_info(name, TensorProto.FLOAT, shape)
                              for name, shape in OUTPUT_SHAPES.items())
    model.graph.name = "halogen_v2_count1_D_native_algebra_candidate"
    props = {entry.key: entry.value for entry in model.metadata_props}
    props.update(transformer_sha256=digest(__file__), tiled_helper_sha256=TILED_HELPER_SHA256,
                 projection_helper_sha256=PROJECTION_HELPER_SHA256, arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE,
                 input_cut="supplied gathered raw BF16 embedding/residual exactly widened to FLOAT; no native gather qualification",
                 output_scope="flat BF16-widened seed1x10240 plus RMS partials/norms and separate BF16-widened FC projections; extra diagnostic traffic included in candidate cost",
                 scope="standalone count1 D algebra composition; changed RMS reduction and BF16-rounded decoded weights; native RMS/decoder/DOT2/full-D/head/acceptance/placement/speed unqualified")
    helper.set_model_props(model, props)
    return model


def metadata(model):
    tiled, _ = sealed_helpers()
    result = tiled.output_metadata(model)
    result.update(input_shapes=INPUT_SHAPES, output_shapes=OUTPUT_SHAPES, weight_lineage=WEIGHT_LINEAGE,
                  native_fc_weight_rounding_boundary_modeled=True, weights_rounded_by_graph_casts=True,
                  original_seed_add_nodes_serialized_unchanged=True, original_seed_add_bf16_boundary_preserved=True,
                  seed_shape_initializer_changed_to=[1, 10240], seed_flattening_adds_no_arithmetic=True,
                  normalization_in_segment=True, seed_add_in_segment=True, fp32_reduction_order_changed=True,
                  native_embedding_rms_qualified=False, native_rsq_instruction_modeled=False,
                  native_q8_affine_fma_decoder_qualified=False, native_fc_dot2_schedule_modeled=False,
                  native_accumulation_parity_qualified=False, native_arithmetic_qualified=False,
                  qualification_gaps=["native embedding RMS words", "native rsq/FP32 reduction semantics",
                                      "native Q8 affine-FMA decoder parity", "native BF16 DOT2/chunk/XOR-lane accumulation schedule",
                                      "matched native seed arithmetic and full-D runtime", "strict hardware placement"],
                  diagnostic_output_cost_in_scope=True)
    return result


def source_binding(source_model, source_build_receipt, source_build_sha256):
    if source_build_sha256 != SOURCE_BUILD_SHA256 or digest(source_model) != SOURCE_MODEL_SHA256:
        raise ValueError("frozen original model/build identity differs")
    tiled, _ = sealed_helpers()
    return tiled.source_binding(source_model, source_build_receipt, source_build_sha256)


def transform(source_model, source_build_receipt, source_build_sha256, output):
    source_model = Path(source_model).resolve(strict=True)
    output = Path(output).resolve()
    report, partial, lock = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent:
        raise ValueError("new native algebra graph must stay beside immutable original external data")
    if any(path.exists() for path in (output, report, partial, lock)):
        raise FileExistsError("existing native graph/receipt/partial/lock refused")
    with lock.open("x", encoding="utf-8"):
        source_hash = digest(__file__)
        build, source = source_binding(source_model, source_build_receipt, source_build_sha256)
        candidate = create_native_graph(source)
        original_external = [value.SerializeToString() for value in source.graph.initializer if value.data_location == TensorProto.EXTERNAL]
        candidate_external = [value.SerializeToString() for value in candidate.graph.initializer if value.data_location == TensorProto.EXTERNAL]
        if original_external != candidate_external:
            raise ValueError("immutable original FC/raw-gamma external initializer protobufs changed")
        with partial.open("xb") as stream:
            stream.write(candidate.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        sealed_helpers()
        if (digest(__file__) != source_hash or digest(source_model) != SOURCE_MODEL_SHA256 or
                digest(build["data"]) != build["data_sha256"]):
            raise ValueError("sealed transformer/original graph/data changed during composition")
        os.rename(partial, output)
        result = dict(schema="halogen_v2_count1_D_native_graph.v1", wire_mode="D", count=1,
                      arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE, fp32_reduction_order_changed=True,
                      transformer_sha256=source_hash, dependency_sha256=DEPENDENCY_SHA256,
                      builder_sha256=BUILDER_SHA256, tiled_helper_sha256=TILED_HELPER_SHA256,
                      projection_helper_sha256=PROJECTION_HELPER_SHA256,
                      source_model=str(source_model), source_model_sha256=SOURCE_MODEL_SHA256,
                      source_build_receipt=str(Path(source_build_receipt).resolve()), source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                      model=str(output), model_sha256=digest(output), data=build["data"], data_sha256=build["data_sha256"],
                      data_bytes=build["data_bytes"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      original_external_data_unchanged=True, no_external_weight_copy=True, no_asset_requantization=True,
                      input_shapes=INPUT_SHAPES, output_shapes=OUTPUT_SHAPES,
                      metadata=metadata(candidate), **{key: False for key in FALSE_CLAIMS})
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    lock.unlink()
    return result


def verify_native_graph(model_path, receipt_path, receipt_sha256):
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    tiled, _ = sealed_helpers()
    result = tiled.read_receipt(receipt_path, sha(receipt_sha256))
    required = dict(schema="halogen_v2_count1_D_native_graph.v1", wire_mode="D", count=1, arithmetic=ARITHMETIC,
                    weight_lineage=WEIGHT_LINEAGE, transformer_sha256=digest(__file__), dependency_sha256=DEPENDENCY_SHA256,
                    builder_sha256=BUILDER_SHA256, tiled_helper_sha256=TILED_HELPER_SHA256,
                    projection_helper_sha256=PROJECTION_HELPER_SHA256,
                    source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                    model=str(model_path), input_shapes=INPUT_SHAPES, output_shapes=OUTPUT_SHAPES)
    if (receipt_path != Path(str(model_path) + ".json") or any(result.get(key) != value for key, value in required.items()) or
            any(result.get(key) is not False for key in FALSE_CLAIMS) or
            any(result.get(key) is not True for key in ("fp32_reduction_order_changed", "original_external_data_unchanged",
                                                       "no_external_weight_copy", "no_asset_requantization")) or
            digest(model_path) != result["model_sha256"]):
        raise ValueError("native algebra graph source/model/receipt contract differs")
    source_path = Path(result["source_model"]).resolve(strict=True)
    if source_path.parent != model_path.parent:
        raise ValueError("source/candidate external-data folder differs")
    build, source = source_binding(source_path, result["source_build_receipt"], result["source_build_receipt_sha256"])
    if any(result[key] != build[key] for key in ("data", "data_sha256", "data_bytes", "assets_receipt_sha256")):
        raise ValueError("immutable original FC/raw-gamma external-data binding differs")
    expected = create_native_graph(source)
    actual = onnx.load(str(model_path), load_external_data=False)
    if actual.SerializeToString() != expected.SerializeToString() or result["metadata"] != metadata(expected):
        raise ValueError("exact full-D algebra composition/parser metadata proof differs")
    sealed_helpers()
    if digest(receipt_path) != receipt_sha256 or digest(model_path) != result["model_sha256"]:
        raise ValueError("native algebra graph/receipt changed during verification")
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
