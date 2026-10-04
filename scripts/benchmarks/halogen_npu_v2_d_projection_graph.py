"""Exact original count1 D suffix with explicit normalized FLOAT inputs.

Root alone builds/verifies actual models/assets. No RMS node is in this
separate candidate: whole-row normalization has already completed before
the input cut. External FC matrices and every projection/add BF16 boundary
remain unchanged. An explicit second lineage adds decoded-weight BF16 RNE;
native Q8 affine-FMA decoder parity and hardware placement stay unqualified.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import onnx
from onnx import TensorProto, helper


HERE = Path(__file__).resolve().parent
BUILDER = HERE / "halogen_npu_v2_d_prepare.py"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
SOURCE_MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
SOURCE_BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
SUFFIX = ["h_streams", "e_projection_fp32", "h_projection_fp32", "e_projection_bf16",
          "e_projection", "h_projection_bf16", "h_projection", "seed_fp32",
          "seed_bf16_widened_bf16", "seed_bf16_widened", "seed"]
INPUT_SHAPES = {"e_norm": [1, 2560], "h_norm": [1, 10240]}
WEIGHT_LINEAGES = ("original-decoded-FP32", "BF16-rounded-original-decoded-FP32")
ARITHMETIC = {
    WEIGHT_LINEAGES[0]: "original FP32 FC suffix with original projection/add BF16 casts; already normalized BF16-widened inputs; RMS excluded",
    WEIGHT_LINEAGES[1]: "original decoded FP32 weights explicitly rounded BF16 RNE and widened before FC; original projection/add BF16 casts; RMS excluded; native Q8 affine-FMA decoder parity unqualified",
}
FALSE_CLAIMS = ("hardware_placement_qualified", "native_q8_parity_qualified", "full_d_claim",
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


def receipt(path, expected):
    sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not 0 < before.st_size <= 2 << 20:
        raise ValueError("projection receipt exceeds bounded size")
    with path.open("rb") as stream:
        raw = stream.read((2 << 20) + 1)
    after = path.stat()
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if len(raw) > 2 << 20 or hashlib.sha256(raw).hexdigest() != expected or any(getattr(before, name) != getattr(after, name) for name in fields):
        raise ValueError("projection receipt hash/identity differs")
    return json.loads(raw)


def create_projection(source, weight_lineage=WEIGHT_LINEAGES[0]):
    """Copy the exact suffix protobuf nodes; no external data I/O."""
    if [value.name for value in source.graph.output] != ["seed"]:
        raise ValueError("frozen original seed-only graph required")
    first = next(index for index, node in enumerate(source.graph.node) if node.name == "h_streams")
    nodes = list(source.graph.node)[first:]
    if [node.name for node in nodes] != SUFFIX:
        raise ValueError("exact original eleven-node FC/BF16/add suffix required")
    if weight_lineage not in WEIGHT_LINEAGES:
        raise ValueError("explicit supported weight lineage required")
    model = deepcopy(source)
    del model.graph.node[:]
    model.graph.node.extend(deepcopy(nodes))
    if weight_lineage == WEIGHT_LINEAGES[1]:
        casts = []
        for name in ("W_embedding", "W_hidden"):
            casts.extend([helper.make_node("Cast", [name], [name + "_bf16"], name=name + "_bf16", to=TensorProto.BFLOAT16),
                          helper.make_node("Cast", [name + "_bf16"], [name + "_bf16_widened"], name=name + "_bf16_widened", to=TensorProto.FLOAT)])
        for node in model.graph.node:
            if node.op_type == "MatMul":
                node.input[1] = node.input[1] + "_bf16_widened"
        transformed_nodes = [*casts, *model.graph.node]
        del model.graph.node[:]
        model.graph.node.extend(transformed_nodes)
    del model.graph.input[:]
    model.graph.input.extend(helper.make_tensor_value_info(name, TensorProto.FLOAT, shape) for name, shape in INPUT_SHAPES.items())
    initializers = [deepcopy(value) for value in source.graph.initializer if value.name in ("W_embedding", "W_hidden", "stream_shape", "seed_shape")]
    if {value.name for value in initializers} != {"W_embedding", "W_hidden", "stream_shape", "seed_shape"}:
        raise ValueError("original FC and reshape constants required")
    del model.graph.initializer[:]
    model.graph.initializer.extend(initializers)
    props = {entry.key: entry.value for entry in source.metadata_props}
    props.update(source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                 transformer_sha256=digest(__file__), arithmetic=ARITHMETIC[weight_lineage], weight_lineage=weight_lineage,
                 input_cut="already normalized original whole-row e/h BF16 words, exactly widened to FLOAT",
                 scope="separate original FC suffix candidate; RMS outside NPU segment; no full D/native Q8/head/acceptance/speed claim")
    helper.set_model_props(model, props)
    return model


def metadata(model, weight_lineage):
    dynamic = {value.name for value in model.graph.input}
    required, constant = set(), set()
    for node in model.graph.node:
        if any(name in dynamic for name in node.input):
            dynamic.update(node.output)
            required.update(node.output)
        else:
            constant.update(node.output)
    return dict(input_shapes=INPUT_SHAPES, output_names=[value.name for value in model.graph.output],
                nodes=[dict(name=node.name, op_type=node.op_type, inputs=list(node.input), outputs=list(node.output)) for node in model.graph.node],
                operator_counts=dict(Counter(node.op_type for node in model.graph.node)),
                required_hardware_partition_outputs=sorted(required), constant_foldable_node_outputs=sorted(constant),
                normalization_in_segment=False, weight_lineage=weight_lineage,
                suffix_nodes_serialized_unchanged=weight_lineage == WEIGHT_LINEAGES[0],
                native_fc_weight_rounding_modeled=weight_lineage == WEIGHT_LINEAGES[1],
                native_q8_affine_fma_decoder_proved=False)


def source_binding(model_path, build_path, build_sha):
    if build_sha != SOURCE_BUILD_SHA256 or digest(BUILDER) != BUILDER_SHA256 or digest(model_path) != SOURCE_MODEL_SHA256:
        raise ValueError("frozen original builder/model/build identity differs")
    import halogen_npu_v2_d_prepare as builder
    build, weights = builder.verify_model(model_path, build_path, build_sha, "D")
    weights = None
    return build, onnx.load(str(model_path), load_external_data=False)


def transform(source_model, source_build_receipt, source_build_sha256, output, weight_lineage):
    source_model = Path(source_model).resolve(strict=True)
    output = Path(output).resolve()
    report, partial, lock = (Path(str(output) + suffix) for suffix in (".json", ".partial", ".lock"))
    if output.parent != source_model.parent:
        raise ValueError("candidate must stay beside immutable original external data")
    if any(path.exists() for path in (output, report, partial, lock)):
        raise FileExistsError("existing candidate/receipt/partial/lock refused")
    with lock.open("x", encoding="utf-8"):
        build, source = source_binding(source_model, source_build_receipt, source_build_sha256)
        candidate = create_projection(source, weight_lineage)
        with partial.open("xb") as stream:
            stream.write(candidate.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        if digest(source_model) != SOURCE_MODEL_SHA256 or digest(build["data"]) != build["data_sha256"]:
            raise ValueError("original graph/data changed during transform")
        os.rename(partial, output)
        result = dict(schema="halogen_v2_count1_D_projection_graph.v1", wire_mode="D", count=1,
                      arithmetic=ARITHMETIC[weight_lineage], weight_lineage=weight_lineage,
                      transformer_sha256=digest(__file__), builder_sha256=BUILDER_SHA256,
                      source_model=str(source_model), source_model_sha256=SOURCE_MODEL_SHA256,
                      source_build_receipt=str(Path(source_build_receipt).resolve()), source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                      model=str(output), model_sha256=digest(output), data=build["data"], data_sha256=build["data_sha256"],
                      data_bytes=build["data_bytes"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      original_external_data_unchanged=True, no_external_weight_copy=True,
                      metadata=metadata(candidate, weight_lineage), **{key: False for key in FALSE_CLAIMS})
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    lock.unlink()
    return result


def verify_projection(model_path, receipt_path, receipt_sha256):
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    result = receipt(receipt_path, receipt_sha256)
    weight_lineage = result.get("weight_lineage")
    if weight_lineage not in WEIGHT_LINEAGES:
        raise ValueError("explicit recorded weight lineage required")
    required = dict(schema="halogen_v2_count1_D_projection_graph.v1", wire_mode="D", count=1, arithmetic=ARITHMETIC[weight_lineage],
                    transformer_sha256=digest(__file__), builder_sha256=BUILDER_SHA256,
                    source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                    model=str(model_path), original_external_data_unchanged=True, no_external_weight_copy=True,
                    **{key: False for key in FALSE_CLAIMS})
    if receipt_path != Path(str(model_path) + ".json") or any(result.get(key) != value for key, value in required.items()) or digest(model_path) != result["model_sha256"]:
        raise ValueError("projection source/model/receipt contract differs")
    source_path = Path(result["source_model"]).resolve(strict=True)
    if source_path.parent != model_path.parent:
        raise ValueError("source/candidate external-data folder differs")
    build, source = source_binding(source_path, result["source_build_receipt"], result["source_build_receipt_sha256"])
    if any(result[key] != build[key] for key in ("data", "data_sha256", "data_bytes", "assets_receipt_sha256")):
        raise ValueError("original FC external-data binding differs")
    expected = create_projection(source, weight_lineage)
    actual = onnx.load(str(model_path), load_external_data=False)
    if actual.SerializeToString() != expected.SerializeToString() or result["metadata"] != metadata(expected, weight_lineage):
        raise ValueError("exact original suffix/parser proof differs")
    if digest(receipt_path) != receipt_sha256:
        raise ValueError("projection receipt changed during verification")
    return result, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--source-build-receipt", type=Path, required=True)
    parser.add_argument("--source-build-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--weight-lineage", choices=WEIGHT_LINEAGES, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(transform(args.source_model, args.source_build_receipt, sha(args.source_build_receipt_sha256), args.output, args.weight_lineage), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
