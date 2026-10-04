"""Standalone paired native FC bounded stable-high correction diagnostic.

Only the root runs this builder or loads model payloads. The frozen original
native candidate, decoded weights, normalized BF16 inputs and GPU oracles are
preserved. A uniformly iterated generic eb8 split must reach a bit-exact
fixed point in at most eight stability iterations, or fail. Residuals are
computed against the unchanged original operands. Four MatMuls and their
fixed addition order retain the original final BF16 RNE/FLOAT boundaries.
This is neither a live responder nor an admission or speed claim.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
NATIVE_HELPER = HERE / "halogen_npu_v2_d_native_projection_graph.py"
NATIVE_HELPER_SHA256 = "8b4d6b9fab064cb556637398796412cb1ccdd555d56193e20fbc2c57285e0c66"
PROJECTION_HELPER = HERE / "halogen_npu_v2_d_projection_graph.py"
PROJECTION_HELPER_SHA256 = "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd"
BUILDER = HERE / "halogen_npu_v2_d_prepare.py"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
SPLIT_SOURCE = HERE / "halogen_npu_precision_split_probe.py"
SPLIT_SOURCE_SHA256 = "012f496c94e52f06ed2b530a58fbc35781ef7795f44715b16f13d75285a68412"
ORIGINAL_SPLIT_HELPER = HERE / "halogen_npu_v2_d_native_projection_split_graph.py"
ORIGINAL_SPLIT_HELPER_SHA256 = "7954af5205d9e21907e600207707a01355a3a5b75909c4f30a7a4aa2993d4526"
NATIVE_MODEL_SHA256 = "9672f9b98b8b0b0efc10fadb30d0668ee9af25200681fe9b2e421dec97821291"
NATIVE_RECEIPT_SHA256 = "10b953f75bc7ba23195f8d5616ef6b46bb5a017bf91666ad7e96fb58a58284a6"
SOURCE_MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
SOURCE_BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
SOURCE_DATA_SHA256 = "a220218d57d4eb9c5cd7231bd696c394a226da5a529fb51cb8c8cbe5e7be379f"
SOURCE_DATA_BYTES = 52_480_000
WIDTH = 2560
MATRIX_BYTES = WIDTH * WIDTH * 4
DATA_BYTES = 4 * MATRIX_BYTES
INPUT_SHAPES = {"e_high": (1, WIDTH), "e_low": (1, WIDTH),
                "h_high": (4, WIDTH), "h_low": (4, WIDTH)}
OUTPUT_SHAPES = {"e_projection": (1, WIDTH), "h_projection": (4, WIDTH)}
INITIALIZER_NAMES = ("W_embedding_high", "W_embedding_low", "W_hidden_high", "W_hidden_low")
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
MAX_HIGH_ITERATIONS = 8
BASE_SPLIT_RULE = "BF16 RNE then K-axis eb8 BFP16, half-away mantissa rounding, signed carry (negative -128 allowed)"
SPLIT_RULE = ("bounded stable-high fixed point of Q=" + BASE_SPLIT_RULE +
              "; start high=Q(original), repeat Q(high) uniformly until bit-exact Q(high)==high "
              "within 8 stability iterations, otherwise fail; low=original-stable_high, original unchanged")
ARITHMETIC = ("original decoded FP32 weights BF16 RNE then generic high/residual split; "
              "high iterated uniformly to verified bounded bit-exact Q fixed point; residual against unchanged original; "
              "normalized original BF16-widened inputs split freshly per call; "
              "HH+HL then +LH then +LL via FLOAT MatMul/Add; original final projection BF16 RNE then FLOAT; "
              "RMS and seed-add excluded; internal NPU rounding and native accumulation parity unqualified")
FALSE_CLAIMS = ("hardware_placement_qualified", "native_q8_parity_qualified", "native_graph_parity_qualified",
                "native_q8_affine_fma_decoder_qualified", "native_accumulation_parity_qualified", "full_d_claim",
                "full_mtp_claim", "acceptance_claim", "speed_promotion", "live_integration_qualified")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def array_digest(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def sealed_native():
    for path, expected in ((NATIVE_HELPER, NATIVE_HELPER_SHA256), (PROJECTION_HELPER, PROJECTION_HELPER_SHA256),
                           (BUILDER, BUILDER_SHA256), (SPLIT_SOURCE, SPLIT_SOURCE_SHA256),
                           (ORIGINAL_SPLIT_HELPER, ORIGINAL_SPLIT_HELPER_SHA256)):
        if digest(path) != expected:
            raise ValueError("frozen source identity differs: " + path.name)
    import halogen_npu_v2_d_native_projection_graph as native
    import halogen_npu_v2_d_prepare as builder
    if Path(native.__file__).resolve() != NATIVE_HELPER or Path(builder.__file__).resolve() != BUILDER:
        raise ValueError("explicit frozen native/builder import origin differs")
    return native, builder


def bf16_rne(value, np):
    value = np.array(value, dtype=np.float32, copy=True, order="C")
    if not np.isfinite(value).all():
        raise ValueError("split operands must be finite")
    bits = value.view(np.uint32)
    rounded = bits + np.uint32(0x7fff) + ((bits >> 16) & np.uint32(1))
    result = (rounded & np.uint32(0xffff0000)).view(np.float32)
    if not np.isfinite(result).all():
        raise ValueError("BF16 RNE overflow refused")
    return result


def bfp16_high(value, axis, np):
    """Exactly the documented one-pass rule; no fixed-point/value fitting.

    Formula lineage is frozen halogen_npu_precision_split_probe.bfp16_high.
    Quark source: https://github.com/amd/Quark/blob/1b229f781a1974cc742884e42d8eefc1eebb4f0a/quark/onnx/operators/custom_ops/src/bfp/cpu/bfp_kernel.cc
    """
    bf = bf16_rne(value, np)
    moved = np.moveaxis(bf, axis, -1).copy()
    shape = moved.shape
    if not shape[-1] or shape[-1] % 8:
        raise ValueError("complete K-axis eb8 groups required")
    blocks = moved.reshape(*shape[:-1], shape[-1] // 8, 8)
    exponents = ((blocks.view(np.uint32) & np.uint32(0x7f800000)) >> 23).max(-1, keepdims=True)
    step = np.exp2(exponents.astype(np.int32) - 127 - 6).astype(np.float32)
    if not np.isfinite(step).all() or np.any(step <= 0):
        raise ValueError("finite positive representable BFP group scale required")

    def mantissa_round(operand):
        return np.sign(operand) * np.floor(np.abs(operand) + np.float32(.5))

    rounded = mantissa_round(blocks / step)
    carry = np.any((rounded >= 128) | (rounded < -128), axis=-1, keepdims=True)
    step = step * np.where(carry, np.float32(2), np.float32(1))
    high = np.ascontiguousarray(np.moveaxis((mantissa_round(blocks / step) * step).reshape(shape), -1, axis))
    if not np.isfinite(high).all():
        raise ValueError("nonfinite BFP high refused")
    return high


def stable_bfp16_high(value, axis, np):
    """Uniform bounded iteration, with no oracle or per-value adjustment."""
    high = bfp16_high(value, axis, np)
    initial = high.copy()
    initial_hash = array_digest(initial)
    history = []
    for iteration in range(1, MAX_HIGH_ITERATIONS + 1):
        candidate = bfp16_high(high, axis, np)
        bit_mismatches = int(np.count_nonzero(candidate.view(np.uint32) != high.view(np.uint32)))
        numeric_mismatches = int(np.count_nonzero(candidate != high))
        history.append(dict(iteration=iteration, bit_mismatches=bit_mismatches,
                            numeric_mismatches=numeric_mismatches,
                            max_abs_change=float(np.max(np.abs(candidate - high))),
                            input_high_sha256=array_digest(high), output_high_sha256=array_digest(candidate)))
        if bit_mismatches == 0:
            return high, dict(max_iterations=MAX_HIGH_ITERATIONS, iterations=iteration,
                              quantization_calls=1 + iteration, converged=True,
                              initial_high_sha256=initial_hash,
                              initial_to_stable_bit_mismatches=int(np.count_nonzero(initial.view(np.uint32) != high.view(np.uint32))),
                              initial_to_stable_numeric_mismatches=int(np.count_nonzero(initial != high)),
                              initial_to_stable_max_abs_change=float(np.max(np.abs(initial - high))), history=history)
        high = candidate
    raise ValueError("generic stable-high split did not converge bit-exactly within fixed 8-iteration bound")


def split_operand(value, axis, np):
    """Split already BF16-widened values, retaining numerical diagnostics."""
    original = np.array(value, dtype=np.float32, copy=True, order="C")
    if (not np.isfinite(original).all() or
            np.any(original.view(np.uint32) & np.uint32(0xffff))):
        raise ValueError("original operand must be finite exact BF16-widened FLOAT")
    high, stability = stable_bfp16_high(original, axis, np)
    low = np.subtract(original, high, dtype=np.float32)
    if not np.isfinite(low).all():
        raise ValueError("nonfinite residual refused")
    reconstructed = np.add(high, low, dtype=np.float32)
    requantized = bfp16_high(high, axis, np)
    low_bf16 = bf16_rne(low, np)
    reconstruction_bits = reconstructed.view(np.uint32) != original.view(np.uint32)
    requantized_bits = requantized.view(np.uint32) != high.view(np.uint32)
    low_bf16_bits = low_bf16.view(np.uint32) != low.view(np.uint32)
    if np.any(requantized_bits):
        raise ValueError("stable-high fixed-point verification failed")
    diagnostics = dict(rule=SPLIT_RULE, shape=list(original.shape), K_axis=axis, eb_size=8,
                       elements=int(original.size), original_sha256=array_digest(original),
                       high_sha256=array_digest(high), low_sha256=array_digest(low),
                       reconstructed_sha256=array_digest(reconstructed),
                       reconstruction_bit_mismatches=int(np.count_nonzero(reconstruction_bits)),
                       reconstruction_numeric_mismatches=int(np.count_nonzero(reconstructed != original)),
                       reconstruction_max_abs_error=float(np.max(np.abs(reconstructed - original))),
                       high_requantized_sha256=array_digest(requantized),
                       high_requantization_bit_mismatches=int(np.count_nonzero(requantized_bits)),
                       high_requantization_numeric_mismatches=int(np.count_nonzero(requantized != high)),
                       high_requantization_max_abs_change=float(np.max(np.abs(requantized - high))),
                       high_idempotence_assumed=False, high_idempotence_verified=True, stable_high=stability,
                       final_high_verification_quantization_calls=1,
                       low_BF16_bit_mismatches=int(np.count_nonzero(low_bf16_bits)),
                       low_BF16_max_abs_change=float(np.max(np.abs(low_bf16 - low))),
                       low_nonzero_elements=int(np.count_nonzero(low)), low_max_abs=float(np.max(np.abs(low))),
                       original_max_abs=float(np.max(np.abs(original))), finite=True,
                       numerical_admission_claim=False, per_value_correction=False)
    # The generic high fixed point is necessary for this candidate; unchanged
    # actual CPU/NPU output gates remain independently necessary for accuracy.
    return high, low, diagnostics


def prepare_inputs(e_norm, h_norm, np):
    if tuple(e_norm.shape) != (1, WIDTH) or tuple(h_norm.shape) != (1, 4 * WIDTH):
        raise ValueError("original normalized e/h input shapes required")
    if e_norm.dtype != np.dtype("float32") or h_norm.dtype != np.dtype("float32"):
        raise ValueError("original normalized FLOAT inputs required")
    feeds, diagnostics = {}, {}
    for branch, value in (("e", e_norm), ("h", h_norm.reshape(4, WIDTH))):
        high, low, facts = split_operand(value, -1, np)
        feeds[branch + "_high"] = high
        feeds[branch + "_low"] = low
        diagnostics[branch] = facts
    if any(tuple(feeds[name].shape) != shape for name, shape in INPUT_SHAPES.items()):
        raise ValueError("split input geometry differs")
    return feeds, diagnostics


def create_graph(data_location, source_hash):
    """Fixed external descriptors; no initializer payload materialization."""
    import onnx
    from onnx import TensorProto, helper
    if not data_location or Path(data_location).name != data_location:
        raise ValueError("derived external data must be a sibling filename")
    sha(source_hash)
    initializers = []
    for index, name in enumerate(INITIALIZER_NAMES):
        tensor = TensorProto(name=name, data_type=TensorProto.FLOAT, dims=[WIDTH, WIDTH],
                             data_location=TensorProto.EXTERNAL)
        for key, value in (("location", data_location), ("offset", str(index * MATRIX_BYTES)), ("length", str(MATRIX_BYTES))):
            field = tensor.external_data.add()
            field.key, field.value = key, value
        initializers.append(tensor)
    nodes = []
    for branch, weight in (("e", "W_embedding"), ("h", "W_hidden")):
        for suffix, x_part, w_part in (("hh", "high", "high"), ("hl", "high", "low"),
                                      ("lh", "low", "high"), ("ll", "low", "low")):
            output = branch + "_" + suffix
            nodes.append(helper.make_node("MatMul", [branch + "_" + x_part, weight + "_" + w_part], [output], name=output))
        for first, second, output in ((branch + "_hh", branch + "_hl", branch + "_sum_h"),
                                      (branch + "_sum_h", branch + "_lh", branch + "_sum_h_lh"),
                                      (branch + "_sum_h_lh", branch + "_ll", branch + "_projection_fp32")):
            nodes.append(helper.make_node("Add", [first, second], [output], name=output))
        nodes.append(helper.make_node("Cast", [branch + "_projection_fp32"], [branch + "_projection_bf16"],
                                      name=branch + "_projection_bf16", to=TensorProto.BFLOAT16))
        nodes.append(helper.make_node("Cast", [branch + "_projection_bf16"], [branch + "_projection"],
                                      name=branch + "_projection", to=TensorProto.FLOAT))
    graph = helper.make_graph(nodes, "halogen_v2_count1_D_native_projection_stable_split",
                              [helper.make_tensor_value_info(name, TensorProto.FLOAT, shape) for name, shape in INPUT_SHAPES.items()],
                              [helper.make_tensor_value_info(name, TensorProto.FLOAT, shape) for name, shape in OUTPUT_SHAPES.items()], initializers)
    model = helper.make_model(graph, producer_name="strix-alloy-native-projection-stable-split-diagnostic",
                              opset_imports=[helper.make_opsetid("", 21)])
    model.ir_version = 13
    helper.set_model_props(model, dict(transformer_sha256=source_hash, native_helper_sha256=NATIVE_HELPER_SHA256,
                                      split_source_sha256=SPLIT_SOURCE_SHA256, source_model_sha256=SOURCE_MODEL_SHA256,
                                      original_split_helper_sha256=ORIGINAL_SPLIT_HELPER_SHA256,
                                      source_build_receipt_sha256=SOURCE_BUILD_SHA256, arithmetic=ARITHMETIC,
                                      weight_lineage=WEIGHT_LINEAGE, split_rule=SPLIT_RULE,
                                      max_high_iterations=str(MAX_HIGH_ITERATIONS),
                                      scope="standalone paired FC correction diagnostic; no live admission/acceptance/speed claim"))
    return model


def metadata(model):
    return dict(input_shapes={key: list(value) for key, value in INPUT_SHAPES.items()},
                output_shapes={key: list(value) for key, value in OUTPUT_SHAPES.items()},
                output_names=list(OUTPUT_SHAPES),
                nodes=[dict(name=node.name, op_type=node.op_type, inputs=list(node.input), outputs=list(node.output)) for node in model.graph.node],
                operator_counts=dict(Counter(node.op_type for node in model.graph.node)),
                required_hardware_partition_outputs=sorted(name for node in model.graph.node for name in node.output),
                constant_foldable_node_outputs=[], normalization_in_segment=False, seed_add_in_segment=False,
                original_projection_BF16_RNE_boundaries_preserved=True, addition_order="((HH+HL)+LH)+LL",
                internal_NPU_FLOAT_execution_assumed=False, weight_lineage=WEIGHT_LINEAGE)


def immutable_files(native_result, build, native_model, native_receipt, builder):
    paths = {Path(__file__).resolve(): digest(__file__), NATIVE_HELPER: NATIVE_HELPER_SHA256,
             PROJECTION_HELPER: PROJECTION_HELPER_SHA256, BUILDER: BUILDER_SHA256, SPLIT_SOURCE: SPLIT_SOURCE_SHA256,
             ORIGINAL_SPLIT_HELPER: ORIGINAL_SPLIT_HELPER_SHA256,
             native_model: NATIVE_MODEL_SHA256, native_receipt: NATIVE_RECEIPT_SHA256,
             Path(native_result["source_model"]): SOURCE_MODEL_SHA256,
             Path(native_result["source_build_receipt"]): SOURCE_BUILD_SHA256,
             Path(build["data"]): SOURCE_DATA_SHA256,
             Path(build["assets_receipt"]): build["assets_receipt_sha256"],
             Path(builder.STATIC_AUDIT): builder.STATIC_AUDIT_SHA256}
    assets = builder.small_json(build["assets_receipt"], build["assets_receipt_sha256"])
    paths[Path(assets["prepared_plan"])] = assets["prepared_plan_sha256"]
    paths[Path(assets["data"])] = assets["data_sha256"]
    paths.update({HERE / name: expected for name, expected in builder.READER_SHA256.items()})
    result = [dict(path=str(path.resolve(strict=True)), sha256=sha(expected)) for path, expected in paths.items()]
    result.sort(key=lambda row: row["path"])
    recheck_files(result)
    return result


def recheck_files(files):
    if not isinstance(files, list) or not files or len(files) > 64:
        raise ValueError("bounded immutable file inventory required")
    seen = set()
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise ValueError("exact immutable path/SHA256 fields required")
        path = Path(row["path"]).resolve(strict=True)
        if str(path) != row["path"] or str(path) in seen or digest(path) != sha(row["sha256"]):
            raise ValueError("immutable file identity differs: " + str(path))
        seen.add(str(path))


def parent_binding(native_model, native_receipt, receipt_sha256):
    if receipt_sha256 != NATIVE_RECEIPT_SHA256 or digest(native_model) != NATIVE_MODEL_SHA256:
        raise ValueError("exact original native projection candidate/receipt required")
    native, builder = sealed_native()
    result, build = native.verify_native_projection(native_model, native_receipt, receipt_sha256)
    if (result["source_model_sha256"] != SOURCE_MODEL_SHA256 or result["source_build_receipt_sha256"] != SOURCE_BUILD_SHA256 or
            build["data_sha256"] != SOURCE_DATA_SHA256 or build["data_bytes"] != SOURCE_DATA_BYTES):
        raise ValueError("exact original source-build/data lineage required")
    return result, build, builder


def transform(native_model, native_receipt, receipt_sha256, output):
    import numpy as np
    import onnx
    native_model, native_receipt = Path(native_model).resolve(strict=True), Path(native_receipt).resolve(strict=True)
    output = Path(output).resolve()
    data, report, partial, lock = (Path(str(output) + suffix) for suffix in (".data", ".json", ".partial", ".lock"))
    if output.parent != native_model.parent:
        raise ValueError("split candidate must stay beside frozen original native candidate")
    if any(path.exists() for path in (output, data, report, partial, lock)):
        raise FileExistsError("existing split graph/data/receipt/partial/lock refused")
    with lock.open("x", encoding="utf-8"):
        source_hash = digest(__file__)
        parent, build, builder = parent_binding(native_model, native_receipt, sha(receipt_sha256))
        inventory = immutable_files(parent, build, native_model, native_receipt, builder)
        source = onnx.load(str(native_model), load_external_data=False)
        initializers = {value.name: value for value in source.graph.initializer}
        weight_diagnostics = {}
        with data.open("xb") as stream:
            for name in ("W_embedding", "W_hidden"):
                tensor = initializers[name]
                fields = {entry.key: entry.value for entry in tensor.external_data}
                expected_offset = 0 if name == "W_embedding" else MATRIX_BYTES
                if (tensor.data_type != onnx.TensorProto.FLOAT or list(tensor.dims) != [WIDTH, WIDTH] or
                        tensor.data_location != onnx.TensorProto.EXTERNAL or
                        fields != dict(location=Path(build["data"]).name, offset=str(expected_offset), length=str(MATRIX_BYTES))):
                    raise ValueError("exact original external FC descriptors required")
                original = np.memmap(build["data"], mode="r", dtype="<f4", offset=expected_offset, shape=(WIDTH, WIDTH))
                rounded = bf16_rne(original, np)
                high, low, facts = split_operand(rounded, -2, np)
                facts["decoded_original_sha256"] = array_digest(original)
                facts["decoded_to_BF16_bit_changes"] = int(np.count_nonzero(original.view(np.uint32) != rounded.view(np.uint32)))
                weight_diagnostics[name] = facts
                for operand in (high, low):
                    payload = memoryview(np.ascontiguousarray(operand, dtype="<f4")).cast("B")
                    if stream.write(payload) != MATRIX_BYTES:
                        raise OSError("incomplete derived weight write")
                    del payload
                del original, rounded, high, low
            stream.flush()
            os.fsync(stream.fileno())
        if data.stat().st_size != DATA_BYTES:
            raise ValueError("derived four-matrix data extent differs")
        candidate = create_graph(data.name, source_hash)
        with partial.open("xb") as stream:
            stream.write(candidate.SerializeToString())
            stream.flush()
            os.fsync(stream.fileno())
        onnx.checker.check_model(str(partial))
        sealed_native()
        recheck_files(inventory)
        if digest(__file__) != source_hash:
            raise ValueError("split transformer changed during build")
        # Windows rename refuses overwrite; the exclusive lock/initial guards
        # also protect the paired publication. Originals are never written.
        os.rename(partial, output)
        inventory.extend([dict(path=str(output), sha256=digest(output)), dict(path=str(data), sha256=digest(data))])
        inventory.sort(key=lambda row: row["path"])
        result = dict(schema="halogen_v2_count1_D_native_projection_stable_split_graph.v1", wire_mode="D", count=1,
                      diagnostic_only=True, integration_admission=False, acceleration_claim=False, halogen_output_swap=False,
                      arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE, transformer_sha256=source_hash,
                      native_helper_sha256=NATIVE_HELPER_SHA256, projection_helper_sha256=PROJECTION_HELPER_SHA256,
                      builder_sha256=BUILDER_SHA256, split_source_sha256=SPLIT_SOURCE_SHA256,
                      original_split_helper=str(ORIGINAL_SPLIT_HELPER), original_split_helper_sha256=ORIGINAL_SPLIT_HELPER_SHA256,
                      source_native_projection=str(native_model), source_native_projection_sha256=NATIVE_MODEL_SHA256,
                      native_projection_receipt=str(native_receipt), native_projection_receipt_sha256=NATIVE_RECEIPT_SHA256,
                      source_model=parent["source_model"], source_model_sha256=SOURCE_MODEL_SHA256,
                      source_build_receipt=parent["source_build_receipt"], source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                      source_data=build["data"], source_data_sha256=SOURCE_DATA_SHA256, source_data_bytes=SOURCE_DATA_BYTES,
                      assets_receipt=build["assets_receipt"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      model=str(output), model_sha256=digest(output), data=str(data), data_sha256=digest(data), data_bytes=DATA_BYTES,
                      derived_data_exclusive=True, original_external_data_unchanged=True,
                      normalization_in_segment=False, seed_add_in_segment=False,
                      split_diagnostics=dict(rule=SPLIT_RULE, input_K_axis=-1, weight_K_axis=-2,
                                             high_idempotence_assumed=False, per_value_correction=False,
                                             stable_high_fixed_point_required=True, max_high_iterations=MAX_HIGH_ITERATIONS,
                                             iteration_condition="bit-exact Q(high)==high", bounded_nonconvergence_is_failure=True,
                                             weight_preparation_is_static=True, input_preparation_timed_every_call=True),
                      weight_diagnostics=weight_diagnostics, metadata=metadata(candidate), immutable_files=inventory,
                      **{key: False for key in FALSE_CLAIMS})
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        recheck_files(inventory)
    lock.unlink()
    return result


def verify_split(model_path, receipt_path, receipt_sha256):
    import onnx
    model_path, receipt_path = Path(model_path).resolve(strict=True), Path(receipt_path).resolve(strict=True)
    native, _ = sealed_native()
    result = native.sealed_helper().receipt(receipt_path, sha(receipt_sha256))
    data_path = Path(str(model_path) + ".data")
    source_hash = digest(__file__)
    required = dict(schema="halogen_v2_count1_D_native_projection_stable_split_graph.v1", wire_mode="D", count=1,
                    diagnostic_only=True, integration_admission=False, acceleration_claim=False, halogen_output_swap=False,
                    arithmetic=ARITHMETIC, weight_lineage=WEIGHT_LINEAGE, transformer_sha256=source_hash,
                    native_helper_sha256=NATIVE_HELPER_SHA256, projection_helper_sha256=PROJECTION_HELPER_SHA256,
                    builder_sha256=BUILDER_SHA256, split_source_sha256=SPLIT_SOURCE_SHA256,
                    original_split_helper=str(ORIGINAL_SPLIT_HELPER), original_split_helper_sha256=ORIGINAL_SPLIT_HELPER_SHA256,
                    source_native_projection_sha256=NATIVE_MODEL_SHA256, native_projection_receipt_sha256=NATIVE_RECEIPT_SHA256,
                    source_model_sha256=SOURCE_MODEL_SHA256, source_build_receipt_sha256=SOURCE_BUILD_SHA256,
                    source_data_sha256=SOURCE_DATA_SHA256, source_data_bytes=SOURCE_DATA_BYTES,
                    model=str(model_path), data=str(data_path), data_bytes=DATA_BYTES,
                    derived_data_exclusive=True, original_external_data_unchanged=True,
                    normalization_in_segment=False, seed_add_in_segment=False, **{key: False for key in FALSE_CLAIMS})
    if (receipt_path != Path(str(model_path) + ".json") or any(result.get(key) != value for key, value in required.items()) or
            data_path.stat().st_size != DATA_BYTES or digest(data_path) != sha(result["data_sha256"]) or
            digest(model_path) != sha(result["model_sha256"])):
        raise ValueError("split graph/data/receipt contract differs")
    if any(Path(str(model_path) + suffix).exists() for suffix in (".partial", ".lock")):
        raise ValueError("split writer partial/lock present")
    source_native = Path(result["source_native_projection"]).resolve(strict=True)
    source_receipt = Path(result["native_projection_receipt"]).resolve(strict=True)
    if source_native.parent != model_path.parent:
        raise ValueError("split/native candidate folders differ")
    parent, build, builder = parent_binding(source_native, source_receipt, result["native_projection_receipt_sha256"])
    for key, expected in (("source_model", parent["source_model"]), ("source_build_receipt", parent["source_build_receipt"]),
                          ("source_data", build["data"]), ("assets_receipt", build["assets_receipt"]),
                          ("assets_receipt_sha256", build["assets_receipt_sha256"])):
        if result.get(key) != expected:
            raise ValueError("unchanged original source-build binding differs: " + key)
    expected = create_graph(data_path.name, source_hash)
    actual = onnx.load(str(model_path), load_external_data=False)
    if actual.SerializeToString() != expected.SerializeToString() or result.get("metadata") != metadata(expected):
        raise ValueError("fixed split graph/parser proof differs")
    expected_split = dict(rule=SPLIT_RULE, input_K_axis=-1, weight_K_axis=-2, high_idempotence_assumed=False,
                          stable_high_fixed_point_required=True, max_high_iterations=MAX_HIGH_ITERATIONS,
                          iteration_condition="bit-exact Q(high)==high", bounded_nonconvergence_is_failure=True,
                          per_value_correction=False, weight_preparation_is_static=True, input_preparation_timed_every_call=True)
    if result.get("split_diagnostics") != expected_split or set(result.get("weight_diagnostics", {})) != {"W_embedding", "W_hidden"}:
        raise ValueError("documented generic split diagnostics required")
    for facts in result["weight_diagnostics"].values():
        if (facts.get("rule") != SPLIT_RULE or facts.get("shape") != [WIDTH, WIDTH] or facts.get("K_axis") != -2 or
                facts.get("eb_size") != 8 or facts.get("elements") != WIDTH * WIDTH or facts.get("finite") is not True or
                any(facts.get(key) is not False for key in ("high_idempotence_assumed", "numerical_admission_claim", "per_value_correction"))):
            raise ValueError("static weight split facts differ")
        stability = facts.get("stable_high", {})
        iterations = stability.get("iterations")
        history = stability.get("history")
        if (facts.get("high_idempotence_verified") is not True or
                facts.get("final_high_verification_quantization_calls") != 1 or
                facts.get("high_requantization_bit_mismatches") != 0 or facts.get("high_requantization_numeric_mismatches") != 0 or
                facts.get("high_requantization_max_abs_change") != 0.0 or
                stability.get("max_iterations") != MAX_HIGH_ITERATIONS or stability.get("converged") is not True or
                type(iterations) is not int or not 1 <= iterations <= MAX_HIGH_ITERATIONS or
                stability.get("quantization_calls") != iterations + 1 or not isinstance(history, list) or len(history) != iterations):
            raise ValueError("bounded verified static high fixed-point facts required")
        previous = sha(stability["initial_high_sha256"])
        for index, row in enumerate(history, 1):
            current = sha(row["output_high_sha256"])
            if (row.get("iteration") != index or sha(row["input_high_sha256"]) != previous or
                    type(row.get("bit_mismatches")) is not int or type(row.get("numeric_mismatches")) is not int or
                    not 0 <= row["numeric_mismatches"] <= row["bit_mismatches"] <= WIDTH * WIDTH or
                    type(row.get("max_abs_change")) not in (int, float) or
                    not math.isfinite(row["max_abs_change"]) or row["max_abs_change"] < 0 or
                    (row["bit_mismatches"] == 0) != (current == previous) or
                    (index < iterations and row["bit_mismatches"] == 0) or
                    (index == iterations and (row["bit_mismatches"] != 0 or row["numeric_mismatches"] != 0 or row["max_abs_change"] != 0.0))):
                raise ValueError("uniform stable-high iteration history differs")
            previous = current
        if previous != facts["high_sha256"] or previous != facts["high_requantized_sha256"]:
            raise ValueError("verified high fixed-point hash binding differs")
        for key in ("original_sha256", "high_sha256", "low_sha256", "reconstructed_sha256", "high_requantized_sha256", "decoded_original_sha256"):
            sha(facts[key])
    expected_inventory = immutable_files(parent, build, source_native, source_receipt, builder)
    expected_inventory.extend([dict(path=str(model_path), sha256=result["model_sha256"]),
                               dict(path=str(data_path), sha256=result["data_sha256"])])
    expected_inventory.sort(key=lambda row: row["path"])
    if result.get("immutable_files") != expected_inventory:
        raise ValueError("complete immutable source/candidate inventory differs")
    recheck_files(expected_inventory)
    sealed_native()
    if digest(receipt_path) != receipt_sha256 or digest(__file__) != source_hash:
        raise ValueError("split receipt/transformer changed during verification")
    # This is the original source-build dictionary, not a derived split build;
    # the unchanged native probe uses its assets receipt to bind GPU oracles.
    return result, build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-native-projection", type=Path, required=True)
    parser.add_argument("--native-projection-receipt", type=Path, required=True)
    parser.add_argument("--native-projection-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    args = parser.parse_args(argv)
    result = transform(args.source_native_projection, args.native_projection_receipt,
                       sha(args.native_projection_receipt_sha256), args.output)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
