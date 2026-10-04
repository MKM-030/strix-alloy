"""Rank-two row Gather BF16 candidate for two captured real v2 routes.

The reviewed 16-expert BF16 bank bytes and independent saved references are
reused without checkpoint decode. Bank tensors flatten only their first two
axes: [16*2560,1280] and [16*640,2560]. Host derives ordered row indices, two
axis-zero Gathers feed explicit Reshapes, then two FP32 Casts and the frozen
eight expert operators. Embedding-style row dimensions are an admission
hypothesis, not established provider support. Captured BF16 x is widened
exactly; captured expert and coefficient order is preserved. Strict BF16
semantics and original FP32 approximation gates remain separately labelled.
This is a routed-expert subgraph, not complete MLP/MTP or acceptance. Only the
root may launch NPU through its exclusive memory/owned-process guard.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import onnx
from onnx import TensorProto, helper

SOURCE_DIR = Path(r"C:\Projects\strix-alloy-clean\scripts\benchmarks")
FROZEN = {
    "halogen_npu_v2_live_bf16_gather_probe.py": "6d665ec8d88df6cc177c8c0747329714183825ed80f23e87a347701d91d9d53d",
    "halogen_npu_v2_bank20_expert_probe.py": "ae1372da176af3e473c78533d45906ae08c31380cdf15d0999b91da41b7b9210",
    "halogen_npu_v2_dynamic_expert_probe.py": "b8578423352d33bb8c9bebc0e591a2d599d388e401886d6afb654f53b10e045c",
}
for _name, _expected in FROZEN.items():
    if hashlib.sha256((SOURCE_DIR / _name).read_bytes()).hexdigest() != _expected:
        raise ValueError("frozen helper changed: " + _name)
sys.path.insert(0, str(SOURCE_DIR))
import halogen_npu_v2_bank20_expert_probe as bank
import halogen_npu_v2_sparse as sparse

dynamic = bank.dynamic
WIDTH, INTERMEDIATE, TOP_K = sparse.WIDTH, sparse.INTERMEDIATE, sparse.TOP_K
WEIGHT_LIMIT = 1 << 30
EXPERT_FP32_BYTES = WIDTH * 3 * INTERMEDIATE * 4
EXPERT_BF16_BYTES = EXPERT_FP32_BYTES // 2
EXPLICIT_BUILD_WEIGHT_PEAK = 1 << 20
FEED_BYTES = WIDTH * 4 + TOP_K * (WIDTH + INTERMEDIATE) * 8 + TOP_K * 4
REVIEWED_DIR = Path(r"C:\AI\halogen-mtp-npu\v2-live-bf16-gather-offline-20261004")
REVIEWED_RECEIPT = REVIEWED_DIR / "v2-live-bf16-gather-top10.build.json"
REVIEWED_RECEIPT_SHA256 = "28bc4f16814efb0b4007937e4bde429a6d2eb6320745935362d427bdf57d9d21"
REVIEWED_MODEL_SHA256 = "fc238448ba77fcc63cf109e762ecf0c9361cb9b028bb756feafa71741eaf66ff"
REVIEWED_DATA_SHA256 = "bf47a0989cbbb038d57c7daf22bfb06b887e5c6052e4cdaa6d5c584e8777b8fa"
REVIEWED_DATA_BYTES = 157286400
CAPTURE = Path(r"C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\mtp-route-capture-353f04fbb6cf42cb8a4f9030aa4eafc9")
CAPTURE_PINS = {
    "trace-pairs.json": "e902cb16b5f0867698c3f32ac79451aea23d70de86d65672056a424c8feaf9c1",
    "trace-inventory.json": "de3870c74610ae64002f03f442435d47f23b98b3c6e4c0ff280f27223cc389a7",
    "plan.json": "54c65122cbd09ef8fe004d9413f2664feb97b3dba2c2bf740225a52f77bcb77d",
    "terminal.json": "87299df5514df3fee80cbbccdf91731be55d71522cb626de7bea26e0e8dc3365",
    "result.json": "f471ff109a158fb5a06b858edebdc67fa1e6ef80c2baffadf872086febd1812c",
    "trace/trace.jsonl": "1ad70b65be966ac4fe34c0bbec646a9fbf2e0996785e6c25a2e949757afa00ba",
}


def dependencies():
    actual = bank.dependencies()
    for name, expected in FROZEN.items():
        actual[name] = dynamic.digest(SOURCE_DIR / name)
        if actual[name] != expected:
            raise ValueError("frozen helper changed: " + name)
    return actual


def check_threads():
    settings = {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}
    if any(value != "1" for value in settings.values()):
        raise ValueError("set all three BLAS/OpenMP thread variables to 1 before Python starts")
    return settings


def widen_bf16(raw):
    return (np.asarray(raw, dtype="<u2").astype(np.uint32) << np.uint32(16)).view(np.float32)


def bf16_rne_storage(value):
    if not np.isfinite(value).all():
        raise ValueError("BF16 conversion requires finite decoded FP32 weights")
    bits = np.array(value, dtype=np.float32, order="C", copy=True).view(np.uint32)
    bits += np.uint32(0x7fff) + ((bits >> 16) & np.uint32(1))
    storage = (bits >> np.uint32(16)).astype("<u2")
    if not np.isfinite(widen_bf16(storage)).all():
        raise ValueError("BF16 conversion produced nonfinite weights")
    return storage


def route_mapping(routes):
    bank_ids = sorted({int(expert_id) for route in routes for expert_id in route})
    if not 1 <= len(bank_ids) <= 20 or any(not 0 <= value < 512 for value in bank_ids):
        raise ValueError("bounded route union must contain <=20 valid global expert IDs")
    mapping = {expert_id: index for index, expert_id in enumerate(bank_ids)}
    indices = [np.asarray([mapping[int(value)] for value in route], dtype=np.int64) for route in routes]
    for route, mapped in zip(routes, indices):
        if not np.array_equal(np.asarray(bank_ids)[mapped], route):
            raise ValueError("global ID to bank-index mapping changed route order")
    return bank_ids, indices


def capture_parent_fixtures():
    actual_pins = {name: dynamic.digest(CAPTURE / name) for name in CAPTURE_PINS}
    if actual_pins != CAPTURE_PINS:
        raise ValueError("frozen live-capture manifest/source binding changed")
    terminal = json.loads((CAPTURE / "terminal.json").read_text(encoding="utf-8"))
    if terminal["state"]["phase"] != "stopped" or terminal["process_exit"] != 0 or not terminal["cleanup_proven"]:
        raise ValueError("live capture is not proven stopped and cleaned up")
    manifest = json.loads((CAPTURE / "trace-pairs.json").read_text(encoding="utf-8"))
    if manifest["calls"] != len(manifest["pairs"]):
        raise ValueError("capture pair count differs")
    routes, selected, feeds, bindings = [], [], {}, {}
    for pair in manifest["pairs"]:
        index = pair["index"]
        if index != pair["entry"]["index"] or index != pair["exit"]["index"] or pair["entry"]["layer"] != 48 or pair["entry"]["count"] != 1:
            raise ValueError("captured route pairing/geometry differs")
        def read_payload(suffix, size):
            name = f"{index:03d}-{suffix}.bin"
            payload = (CAPTURE / "trace" / name).read_bytes()
            binding = pair["payloads"][name]
            if len(payload) != size or binding != {"bytes": size, "sha256": hashlib.sha256(payload).hexdigest()}:
                raise ValueError("captured payload differs: " + name)
            return payload, dict(path=str(CAPTURE / "trace" / name), **binding)
        ids_payload, ids_binding = read_payload("exit-expert-ids-i32", TOP_K * 4)
        ids = np.frombuffer(ids_payload, dtype="<i4").copy()
        if len(set(ids.tolist())) != TOP_K or np.any((ids < 0) | (ids >= 512)):
            raise ValueError("captured route requires ten distinct valid expert IDs")
        if any(np.array_equal(ids, route) for route in routes):
            continue
        x_payload, x_binding = read_payload("entry-mlp-input-u16", WIDTH * 2)
        coefficient_payload, coefficient_binding = read_payload("exit-coefficients-f32", TOP_K * 4)
        _, complete_output_binding = read_payload("exit-complete-mlp-output-u16", WIDTH * 2)
        x = widen_bf16(np.frombuffer(x_payload, dtype="<u2")).reshape(1, WIDTH)
        coefficients = np.frombuffer(coefficient_payload, dtype="<f4").copy().reshape(TOP_K, 1, 1)
        if not np.isfinite(x).all() or not np.isfinite(coefficients).all():
            raise ValueError("nonfinite captured x or coefficients")
        label = "A" if not routes else "B"
        routes.append(ids)
        selected.append(index)
        feeds[label] = {"x": x, "routing_weights": coefficients}
        bindings[label] = {"capture_index": index, "entry": pair["entry"], "exit": pair["exit"],
                           "original_global_expert_ids": ids.tolist(), "original_coefficients": coefficients.reshape(-1).tolist(),
                           "raw_payloads": {"x": x_binding, "expert_ids": ids_binding, "routing_weights": coefficient_binding,
                                            "complete_mlp_output_provenance_only": complete_output_binding}}
        if len(routes) == 2:
            break
    if len(routes) != 2 or selected != [0, 1]:
        raise ValueError("first two distinct pinned live routes differ from capture calls 0/1")
    bank_ids, indices = route_mapping(routes)
    for label, mapped in zip(("A", "B"), indices):
        feeds[label]["bank_indices"] = mapped
        bindings[label]["host_derived_bank_indices"] = mapped.tolist()
        bindings[label]["runtime_sha256"] = {name: dynamic.array_digest(value) for name, value in feeds[label].items()}
    return feeds, bank_ids, {"capture_directory": str(CAPTURE), "manifest_sha256": actual_pins,
                             "selection": "first two distinct ordered recorded top10 routes; calls 0/1",
                             "x_interpretation": "little-endian raw u16 BF16; uint32(u16)<<16 viewed as FP32; no input rerounding",
                             "mapping": "host maps original global expert IDs to sorted union bank; original order and coefficient pairing preserved",
                             "global_to_bank_index": {str(value): index for index, value in enumerate(bank_ids)},
                             "fixtures": bindings, "complete_mlp_output_used_as_reference": False}


def capture_fixtures():
    feeds, bank_ids, binding = capture_parent_fixtures()
    for label, feed in feeds.items():
        indices = feed.pop("bank_indices")
        gate_rows = (indices[:, None] * WIDTH + np.arange(WIDTH, dtype=np.int64)[None, :]).reshape(-1)
        down_rows = (indices[:, None] * INTERMEDIATE + np.arange(INTERMEDIATE, dtype=np.int64)[None, :]).reshape(-1)
        for rows, height in ((gate_rows, WIDTH), (down_rows, INTERMEDIATE)):
            shaped = rows.reshape(TOP_K, height)
            if not np.array_equal(shaped // height, np.broadcast_to(indices[:, None], shaped.shape)) or not np.array_equal(shaped % height, np.broadcast_to(np.arange(height), shaped.shape)):
                raise ValueError("row indices changed captured route or tensor row order")
            if rows.min() < 0 or rows.max() >= len(bank_ids) * height:
                raise ValueError("row indices outside exact constant bank")
        feed.update(gate_up_row_indices=gate_rows, down_row_indices=down_rows)
        binding["fixtures"][label]["host_derived_row_indices"] = {
            name: {"shape": list(value.shape), "sha256": dynamic.array_digest(value), "first": int(value[0]), "last": int(value[-1])}
            for name, value in feed.items() if name.endswith("row_indices")}
        binding["fixtures"][label]["runtime_sha256"] = {name: dynamic.array_digest(value) for name, value in feed.items()}
    binding["row_mapping"] = "ordered bank_index*height + arange(height); gate_up height=2560, down height=640; flat rows reshape into original top10 order"
    return feeds, bank_ids, binding


def verified_reviewed_build():
    if dynamic.digest(REVIEWED_RECEIPT) != REVIEWED_RECEIPT_SHA256:
        raise ValueError("reviewed independent-reference receipt changed")
    reviewed = json.loads(REVIEWED_RECEIPT.read_text(encoding="utf-8"))
    parent_name = "halogen_npu_v2_live_bf16_gather_probe.py"
    deps = dependencies()
    if not reviewed["passed"] or reviewed["source_sha256"] != FROZEN[parent_name] or reviewed["dependency_sha256"] != {name: value for name, value in deps.items() if name != parent_name}:
        raise ValueError("reviewed parent source/dependency identities differ")
    model_path = REVIEWED_DIR / "v2-live-bf16-gather-top10.onnx"
    data_path = model_path.with_name(model_path.name + ".data")
    if dynamic.digest(model_path) != REVIEWED_MODEL_SHA256 or reviewed["model_sha256"] != REVIEWED_MODEL_SHA256:
        raise ValueError("reviewed model identity differs")
    if dynamic.digest(data_path) != REVIEWED_DATA_SHA256 or reviewed["external_data_sha256"] != REVIEWED_DATA_SHA256 or data_path.stat().st_size != REVIEWED_DATA_BYTES or reviewed["external_data_bytes"] != REVIEWED_DATA_BYTES:
        raise ValueError("reviewed constant bank identity differs")
    parent_feeds, bank_ids, binding = capture_parent_fixtures()
    if len(bank_ids) != 16 or reviewed["bank_experts"] != bank_ids or reviewed["capture_binding"] != binding:
        raise ValueError("reviewed bank or captured route binding differs")
    if reviewed["runtime_input_sets"] != {label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in parent_feeds.items()}:
        raise ValueError("reviewed captured feeds differ")
    references = {precision: {label: np.asarray(value, dtype=np.float32) for label, value in rows.items()} for precision, rows in reviewed["reference_outputs"].items()}
    if {precision: {label: dynamic.array_digest(value) for label, value in rows.items()} for precision, rows in references.items()} != reviewed["reference_sha256"]:
        raise ValueError("saved independent reference array hashes differ")
    if any(row["strict_bf16_reference"]["passed"] or row["approx_bf16_reference"]["passed"] for rows in reviewed["stale_runtime_input_checks"].values() for row in rows.values()):
        raise ValueError("reviewed stale-input discrimination failed")
    return reviewed, data_path, {
        "parent_source": str(SOURCE_DIR / parent_name), "parent_source_sha256": FROZEN[parent_name],
        "receipt": str(REVIEWED_RECEIPT), "receipt_sha256": REVIEWED_RECEIPT_SHA256,
        "model": str(model_path), "model_sha256": REVIEWED_MODEL_SHA256,
        "data": str(data_path), "data_sha256": REVIEWED_DATA_SHA256, "data_bytes": REVIEWED_DATA_BYTES}


def comparison(actual, expected, tolerance):
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        return {"passed": False, "shape_or_finiteness_error": True}
    matches = np.isclose(actual, expected, **tolerance)
    return {"passed": bool(matches.all()), "tolerance": tolerance,
            "max_abs_error": float(np.max(np.abs(actual - expected))),
            "mismatched_elements": int(np.sum(~matches)), "output_elements": int(actual.size)}


def external_tensor(name, shape, location, offset, length):
    tensor = TensorProto(name=name, data_type=TensorProto.BFLOAT16, dims=shape, data_location=TensorProto.EXTERNAL)
    for key, value in (("location", location), ("offset", str(offset)), ("length", str(length))):
        entry = tensor.external_data.add()
        entry.key, entry.value = key, value
    return tensor


def build_graph(location, bank_ids):
    dependencies()
    original = dynamic.build_graph()
    count = len(bank_ids)
    gate_bytes = count * WIDTH * 2 * INTERMEDIATE * 2
    prefix = [helper.make_node("Gather", ["bank_gate_up_rows_bf16", "gate_up_row_indices"], ["selected_gate_up_rows_bf16"], axis=0),
              helper.make_node("Gather", ["bank_down_rows_bf16", "down_row_indices"], ["selected_down_rows_bf16"], axis=0),
              helper.make_node("Reshape", ["selected_gate_up_rows_bf16", "gate_up_shape"], ["selected_gate_up_bf16"]),
              helper.make_node("Reshape", ["selected_down_rows_bf16", "down_shape"], ["selected_down_bf16"]),
              helper.make_node("Cast", ["selected_gate_up_bf16"], ["W_gate_up"], to=TensorProto.FLOAT),
              helper.make_node("Cast", ["selected_down_bf16"], ["W_down"], to=TensorProto.FLOAT)]
    tensors = [external_tensor("bank_gate_up_rows_bf16", [count * WIDTH, 2 * INTERMEDIATE], location, 0, gate_bytes),
               external_tensor("bank_down_rows_bf16", [count * INTERMEDIATE, WIDTH], location, gate_bytes, count * EXPERT_BF16_BYTES - gate_bytes),
               onnx.numpy_helper.from_array(np.array([TOP_K, WIDTH, 2 * INTERMEDIATE], dtype=np.int64), "gate_up_shape"),
               onnx.numpy_helper.from_array(np.array([TOP_K, INTERMEDIATE, WIDTH], dtype=np.int64), "down_shape")]
    inputs = [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, WIDTH]),
              helper.make_tensor_value_info("gate_up_row_indices", TensorProto.INT64, [TOP_K * WIDTH]),
              helper.make_tensor_value_info("down_row_indices", TensorProto.INT64, [TOP_K * INTERMEDIATE]),
              helper.make_tensor_value_info("routing_weights", TensorProto.FLOAT, [TOP_K, 1, 1])]
    infos = [helper.make_tensor_value_info(name, dtype, shape) for name, dtype, shape in (
        ("selected_gate_up_rows_bf16", TensorProto.BFLOAT16, [TOP_K * WIDTH, 2 * INTERMEDIATE]),
        ("selected_down_rows_bf16", TensorProto.BFLOAT16, [TOP_K * INTERMEDIATE, WIDTH]),
        ("selected_gate_up_bf16", TensorProto.BFLOAT16, [TOP_K, WIDTH, 2 * INTERMEDIATE]),
        ("selected_down_bf16", TensorProto.BFLOAT16, [TOP_K, INTERMEDIATE, WIDTH]),
        ("W_gate_up", TensorProto.FLOAT, [TOP_K, WIDTH, 2 * INTERMEDIATE]),
        ("W_down", TensorProto.FLOAT, [TOP_K, INTERMEDIATE, WIDTH]))]
    graph = helper.make_graph(prefix + list(original.graph.node), "v2_live_bf16_row_gather_routed_experts", inputs,
                              list(original.graph.output), tensors + list(original.graph.initializer), value_info=infos)
    model = helper.make_model(graph, producer_name="strix-alloy-v2-live-bf16-row-gather-probe", opset_imports=list(original.opset_import))
    model.ir_version = original.ir_version
    helper.set_model_props(model, {"scope": "two captured real live v2 routes; approximate BF16 routed-expert subgraph only; no complete MLP/MTP/acceptance",
                                  "precision": "reviewed BF16 nearest/even constant weights; exact BF16 input widening; FP32 arithmetic/output",
                                  "bank_global_expert_ids": json.dumps(bank_ids),
                                  "runtime_indices": "host-derived ordered row indices; preserved top10 expert and coefficient order",
                                  "reviewed_parent_source_sha256": FROZEN["halogen_npu_v2_live_bf16_gather_probe.py"],
                                  "original_eight_source_sha256": dynamic.DEPENDENCIES["halogen_npu_parameter_probe.py"],
                                  "gather_to_matmul_prepacking": "unproven", "embedding_style_support": "hypothesis only"})
    if [node.SerializeToString() for node in model.graph.node[6:]] != [node.SerializeToString() for node in original.graph.node]:
        raise ValueError("original eight operator serializations changed")
    return model


def build_from_reviewed(model_path):
    data_path = model_path.with_name(model_path.name + ".data")
    receipt_path = model_path.with_suffix(".build.json")
    if any(path.exists() for path in (model_path, data_path, receipt_path)):
        raise FileExistsError("new model/data/build receipt exists; overwrite refused")
    samples, baseline = [], bank.process_memory()
    threads = check_threads()
    sparse.reserve(samples, WEIGHT_LIMIT)
    started = time.perf_counter_ns()
    reviewed, source_data, reviewed_binding = verified_reviewed_build()
    feeds, bank_ids, capture_binding = capture_fixtures()
    with source_data.open("rb") as source, data_path.open("xb") as output:
        while True:
            sparse.reserve(samples, EXPLICIT_BUILD_WEIGHT_PEAK)
            chunk = source.read(EXPLICIT_BUILD_WEIGHT_PEAK)
            if not chunk:
                break
            if output.write(chunk) != len(chunk):
                raise IOError("short reviewed external-data copy")
    if dynamic.digest(source_data) != REVIEWED_DATA_SHA256 or dynamic.digest(data_path) != REVIEWED_DATA_SHA256 or data_path.stat().st_size != REVIEWED_DATA_BYTES:
        raise ValueError("exact reviewed bank bytes changed during copy")
    model = build_graph(data_path.name, bank_ids)
    with model_path.open("xb") as output:
        output.write(model.SerializeToString())
    onnx.checker.check_model(str(model_path))
    result = dict(reviewed)
    stale = {label: {("paired_row_indices" if name == "bank_indices" else name): row for name, row in rows.items()} for label, rows in reviewed["stale_runtime_input_checks"].items()}
    result.update(schema=1, passed=True, scope=__doc__, source_sha256=dynamic.digest(__file__),
                  blas_thread_environment=threads, dependency_sha256=dependencies(),
                  model=str(model_path.resolve()), model_sha256=dynamic.digest(model_path), model_bytes=model_path.stat().st_size,
                  external_data=str(data_path.resolve()), external_data_sha256=dynamic.digest(data_path), external_data_bytes=REVIEWED_DATA_BYTES,
                  operators=[node.op_type for node in model.graph.node], original_eight_operators_verified=True,
                  bank_experts=bank_ids, capture_binding=capture_binding, reviewed_artifacts=reviewed_binding,
                  checkpoint_decode_performed=False, external_data_layout_changed=False,
                  stale_runtime_input_checks=stale,
                  runtime_input_shapes={name: list(value.shape) for name, value in feeds["A"].items()},
                  runtime_input_sets={label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in feeds.items()},
                  feed_bytes_per_call=FEED_BYTES, weight_tensor_limit_bytes=WEIGHT_LIMIT,
                  explicit_build_weight_peak_bytes=EXPLICIT_BUILD_WEIGHT_PEAK, build_ms=(time.perf_counter_ns() - started) / 1e6,
                  reference_preparation_ms=0.0, reference_reuse="pinned reviewed independent FP32/BF16 arrays; no new expert decode",
                  gather_to_matmul_prepacking="unproven", embedding_style_support="hypothesis only")
    sparse.reserve(samples)
    result.update(bank.memory_summary(samples, baseline))
    if result["peak_private_increase_bytes"] >= WEIGHT_LIMIT:
        result.update(passed=False, error="CPU build private-memory increase exceeded conservative 1 GiB cap")
    with receipt_path.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    return result


def run(model_path, provider, report_path, ep_dir=None):
    if report_path.exists():
        raise FileExistsError("new replay receipt exists; overwrite refused")
    if (provider == "npu") != (ep_dir is not None):
        raise ValueError("NPU requires verified provider copy; CPU must omit --ep-dir")
    samples, baseline = [], bank.process_memory()
    result = {"schema": 1, "scope": __doc__, "passed": False, "provider_requested": provider,
              "source_sha256": dynamic.digest(__file__), "blas_thread_environment": check_threads(),
              "calls": [], "cpu_fallback_allowed": provider == "cpu", "session_creations": 0,
              "warmup_count": 4, "repetitions": 8, "feed_bytes_per_call": FEED_BYTES, "weights_bytes_per_call": 0,
              "weight_tensor_limit_bytes": WEIGHT_LIMIT, "numerical_gate_passed": False, "timing_qualified": False,
              "timing_scope": "fresh contiguous x/host-derived int64 row-index/coefficient copies + session.run transfer/execution/output; "
                              "sparse decode, independent references, constant build/verification, load/compile, output retention/gates/hash excluded",
              "full_mlp_claim": False, "mtp_claim": False, "acceptance_claim": False, "gather_to_matmul_prepacking": "unproven"}
    runtime = session = options = devices = dll_directory = ort = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        sparse.reserve(samples, WEIGHT_LIMIT)
        data_path = model_path.with_name(model_path.name + ".data")
        build_path = model_path.with_suffix(".build.json")
        frozen = json.loads(build_path.read_text(encoding="utf-8"))
        if not frozen["passed"] or frozen["source_sha256"] != result["source_sha256"]:
            raise ValueError("build failed or candidate source changed")
        reviewed, _, reviewed_binding = verified_reviewed_build()
        if frozen["reviewed_artifacts"] != reviewed_binding or frozen["reference_sha256"] != reviewed["reference_sha256"] or frozen["reference_outputs"] != reviewed["reference_outputs"]:
            raise ValueError("new receipt differs from pinned independent parent reference binding")
        reviewed = None
        feeds, bank_ids, capture_binding = capture_fixtures()
        if capture_binding != frozen["capture_binding"] or bank_ids != frozen["bank_experts"]:
            raise ValueError("captured live fixture binding differs from build")
        model = onnx.load(str(model_path), load_external_data=False)
        if model.SerializeToString() != build_graph(data_path.name, bank_ids).SerializeToString():
            raise ValueError("model differs from rank2 BF16 Gathers/two Reshapes/two FP32 Casts/frozen eight ops")
        result.update(model_sha256=dynamic.digest(model_path), external_data_sha256=dynamic.digest(data_path),
                      build_receipt_sha256=dynamic.digest(build_path), dependency_sha256=dependencies(),
                      candidate_graph_operators=len(model.graph.node), original_eight_operators_verified=True,
                      constant_bank_bytes=len(bank_ids) * EXPERT_BF16_BYTES, bank_experts=bank_ids, capture_binding=capture_binding)
        if result["model_sha256"] != frozen["model_sha256"] or result["external_data_sha256"] != frozen["external_data_sha256"] or data_path.stat().st_size != result["constant_bank_bytes"]:
            raise ValueError("frozen candidate model/data differs")
        references = {precision: {label: np.asarray(value, dtype=np.float32) for label, value in rows.items()}
                      for precision, rows in frozen["reference_outputs"].items()}
        if {precision: {label: dynamic.array_digest(value) for label, value in rows.items()} for precision, rows in references.items()} != frozen["reference_sha256"]:
            raise ValueError("saved independent reference arrays differ")
        feed_hashes = {label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in feeds.items()}
        if feed_hashes != frozen["runtime_input_sets"] or any(sum(value.nbytes for value in feed.values()) != FEED_BYTES for feed in feeds.values()):
            raise ValueError("live fixture runtime hashes/bytes differ")
        semantics_tolerance = dynamic.CPU_TOLERANCE if provider == "cpu" else dynamic.NPU_TOLERANCE
        result.update(runtime_input_sets=feed_hashes, runtime_input_shapes=frozen["runtime_input_shapes"],
                      source_binding=frozen["source_binding"], reference_outputs=frozen["reference_outputs"], reference_sha256=frozen["reference_sha256"],
                      reference_expression=frozen["reference_expression"], stale_runtime_input_checks=frozen["stale_runtime_input_checks"],
                      contracts={"bf16_graph_semantics": semantics_tolerance, "original_fp32_approximation": dynamic.NPU_TOLERANCE,
                                 "strict_original_report_only": dynamic.CPU_TOLERANCE},
                      reference_weights_released_before_session=True, process_memory_before_session=bank.process_memory())
        frozen = None
        gc.collect()
        if provider == "npu":
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers() if ep.name == "VitisAIExecutionProvider")
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError("VitisAI absent; acquisition disabled")
            ready = ep.ensure_ready_async().get()
            if int(ready.status) != 1:
                raise RuntimeError("VitisAI readiness failed: " + ready.diagnostic_text)
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report_path.with_suffix(""))
        if provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog_library = Path(ep.library_path).resolve(strict=True)
            chosen_library, verified_files = verified_provider_copy(catalog_library, ep_dir)
            dll_directory = os.add_dll_directory(str(chosen_library.parent))
            result.update(catalog_library=str(catalog_library), provider_library=str(chosen_library),
                          provider_library_sha256=dynamic.digest(chosen_library), provider_copy_files=verified_files,
                          placement_scope="strict ORT Node attribution; internal Gather/Cast placement/prepacking unqualified")
            ort.register_execution_provider_library(ep.name, str(chosen_library))
            registered = True
            devices = [device for device in ort.get_ep_devices() if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected one VitisAI NPU device")
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["external_data_sha256"] + ":" + result["provider_library_sha256"]).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(report_path.parent / "vitisai-cache"), "cache_key": cache_key,
                                                       "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result["cache_key"] = cache_key
        sparse.reserve(samples, WEIGHT_LIMIT)
        started = time.perf_counter_ns()
        result["session_creations"] += 1
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False) if provider == "npu" else ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(), initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        for index in range(12):
            label = "A" if index % 2 == 0 else "B"
            sparse.reserve(samples, FEED_BYTES)
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=value.dtype, order="C", copy=True) for name, value in feeds[label].items()}
            copied_at = time.perf_counter_ns()
            actual = session.run(None, feed)[0]
            finished = time.perf_counter_ns()
            row = {"call_index": index, "warmup": index < 4, "input_set": label,
                   "host_call_ms": (finished - started) / 1e6, "prepare_and_copy_ms": (copied_at - started) / 1e6,
                   "session_run_ms": (finished - copied_at) / 1e6, "output_sha256": dynamic.array_digest(actual),
                   "actual_shape": list(actual.shape), "actual_dtype": str(actual.dtype), "actual_output": actual.tolist(), "passed": False}
            result["calls"].append(row)  # Retain every full output before any numerical gate.
            row.update(bf16_graph_semantics=comparison(actual, references["bf16"][label], semantics_tolerance),
                       strict_bf16_reference=comparison(actual, references["bf16"][label], dynamic.CPU_TOLERANCE),
                       original_fp32_approximation=comparison(actual, references["original_fp32"][label], dynamic.NPU_TOLERANCE),
                       strict_original_report_only=comparison(actual, references["original_fp32"][label], dynamic.CPU_TOLERANCE))
            row["passed"] = actual.dtype == np.float32 and row["bf16_graph_semantics"]["passed"] and row["original_fp32_approximation"]["passed"]
            feed = actual = None
            sparse.reserve(samples)
        if provider == "cpu":
            stale_calls = []
            for label, other in (("A", "B"), ("B", "A")):
                for name in feeds[label]:
                    sparse.reserve(samples, FEED_BYTES)
                    stale_feed = {key: np.array(feeds[other][key] if key == name else value, dtype=value.dtype, order="C", copy=True) for key, value in feeds[label].items()}
                    stale_actual = session.run(None, stale_feed)[0]
                    strict = comparison(stale_actual, references["bf16"][label], dynamic.CPU_TOLERANCE)
                    approx = comparison(stale_actual, references["bf16"][label], dynamic.NPU_TOLERANCE)
                    stale_row = {"input_set": label, "replaced_with": other, "stale_input": name,
                                 "actual_output": stale_actual.tolist(), "output_sha256": dynamic.array_digest(stale_actual),
                                 "strict_bf16_reference": strict, "approx_bf16_reference": approx,
                                 "passed": stale_actual.shape == (1, WIDTH) and np.isfinite(stale_actual).all() and not strict["passed"] and not approx["passed"]}
                    stale_row["passed"] = bool(stale_row["passed"])
                    stale_calls.append(stale_row)
                    stale_feed = stale_actual = None
            result.update(stale_runtime_replay_calls=stale_calls, stale_runtime_replay_passed=len(stale_calls) == 8 and all(row["passed"] for row in stale_calls))
            if not result["stale_runtime_replay_passed"]:
                raise RuntimeError("CPU replay cannot detect each stale row-index/x/coefficient input at both tolerances")
        profile = Path(session.end_profiling())
        profile_finished = True
        nodes = [event for event in json.loads(profile.read_text(encoding="utf-8")) if event.get("cat") == "Node"]
        providers = sorted({event.get("args", {}).get("provider", "<missing>") for event in nodes})
        result.update(profile=str(profile), profile_sha256=dynamic.digest(profile), node_events=len(nodes), executed_node_providers=providers,
                      node_event_ops=sorted({event.get("args", {}).get("op_name", "<missing>") for event in nodes}))
        expected_provider = "VitisAIExecutionProvider" if provider == "npu" else "CPUExecutionProvider"
        if not nodes or providers != [expected_provider]:
            raise RuntimeError("profile does not prove every Node executed by requested provider")
        result.update(bf16_graph_semantics_passed=all(row["bf16_graph_semantics"]["passed"] for row in result["calls"]),
                      original_fp32_approximation_passed=all(row["original_fp32_approximation"]["passed"] for row in result["calls"]),
                      strict_original_all_calls_passed=all(row["strict_original_report_only"]["passed"] for row in result["calls"]))
        result["numerical_gate_passed"] = len(result["calls"]) == 12 and all(row["passed"] for row in result["calls"])
        if result["numerical_gate_passed"]:
            measured = [row for row in result["calls"] if not row["warmup"]]
            times = [row["host_call_ms"] for row in measured]
            result.update(passed=True, timing_qualified=True, mean_host_call_ms=statistics.fmean(times),
                          mean_prepare_and_copy_ms=statistics.fmean(row["prepare_and_copy_ms"] for row in measured),
                          mean_session_run_ms=statistics.fmean(row["session_run_ms"] for row in measured),
                          median_host_call_ms=statistics.median(times), min_host_call_ms=min(times),
                          p95_host_call_ms=sorted(times)[int(np.ceil(.95 * len(times))) - 1])
        else:
            result["error"] = "labelled numerical contract failed; every returned A/B array retained"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                result["partial_profile"] = str(session.end_profiling())
                result["partial_profile_sha256"] = dynamic.digest(result["partial_profile"])
            except Exception as exc:
                result["partial_profile_error"] = type(exc).__name__ + ": " + str(exc)
        session = options = devices = None
        gc.collect()
        if registered:
            try:
                ort.unregister_execution_provider_library("VitisAIExecutionProvider")
                result["provider_unregistered"] = True
            except Exception as exc:
                cleanup_errors.append("provider unregister: " + str(exc))
        if dll_directory is not None:
            try:
                dll_directory.close()
                result["dll_directory_closed"] = True
            except Exception as exc:
                cleanup_errors.append("DLL directory close: " + str(exc))
        if runtime is not None:
            try:
                runtime()
                result["bootstrap_shutdown"] = True
            except Exception as exc:
                cleanup_errors.append("bootstrap shutdown: " + str(exc))
        if samples:
            result.update(bank.memory_summary(samples, baseline))
            if provider == "cpu" and result["peak_private_increase_bytes"] >= WEIGHT_LIMIT:
                result.update(passed=False, timing_qualified=False, error="CPU replay private-memory increase exceeded conservative 1 GiB cap")
        if cleanup_errors:
            result.update(passed=False, timing_qualified=False, cleanup_errors=cleanup_errors)
        with report_path.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-from-reviewed", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--provider", choices=("cpu", "npu"), default="cpu")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--reps", type=int, default=8)
    args = parser.parse_args()
    if args.reps != 8:
        parser.error("candidate replay requires four warmups and eight measured calls")
    if args.build_from_reviewed:
        if args.model or args.report or args.ep_dir or args.provider != "cpu":
            parser.error("--build-from-reviewed cannot be mixed with replay arguments")
        result = build_from_reviewed(args.build_from_reviewed)
    else:
        if not args.model or not args.report:
            parser.error("replay requires --model and --report")
        result = run(args.model, args.provider, args.report, args.ep_dir)
    excluded = {"calls", "reference_outputs", "bank_blocks", "weight_conversion", "capture_binding", "source_binding", "reserve_samples", "provider_copy_files", "stale_runtime_replay_calls"}
    print(json.dumps({key: value for key, value in result.items() if key not in excluded}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
