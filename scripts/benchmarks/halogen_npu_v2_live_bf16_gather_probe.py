"""Approximate BF16 constant Gather candidate for two captured real v2 routes.

Only the <=20-expert union of the first two distinct ordered live routes is
decoded. Captured BF16 x is widened exactly; captured IDs and FP32 coefficients
retain their order. Host-derived int64 bank indices map those IDs to the bounded
constant bank. Two BF16 Gathers and two FP32 Casts precede the frozen eight ops.
CPU graph semantics use an independent BF16-rounded-weight reference at the
unchanged strict CPU tolerance. Original decoded FP32 references use the
separately labelled existing NPU approximation tolerance; their strict mismatch
is also retained. This is the routed-expert subgraph, not complete MLP/MTP or
speculative acceptance. NPU launch requires the root's exclusive guarded window.
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
EXPLICIT_BUILD_WEIGHT_PEAK = 8 * EXPERT_FP32_BYTES
FEED_BYTES = WIDTH * 4 + TOP_K * 8 + TOP_K * 4
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


def capture_fixtures():
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


def source_entries(metadata_path, integrity_path, machine_path):
    if dynamic.digest(metadata_path) != sparse.METADATA_SHA256:
        raise ValueError("pinned metadata receipt differs")
    expected = json.loads(metadata_path.read_text(encoding="utf-8"))["sources"]["v2"]
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    machine = json.loads(machine_path.read_text(encoding="utf-8"))
    if integrity["sha256"] != sparse.CHECKPOINT_SHA256 or integrity["identity"]["size"] != 66687678432:
        raise ValueError("pinned full v2 integrity receipt differs")
    source = machine["models"] + "/qwen38-flash-next-v2.hgn"
    unc = Path("\\\\wsl.localhost\\" + machine["distro"] + source.replace("/", "\\"))
    if str(unc) != expected["path"]:
        raise ValueError("machine source differs from pinned metadata path")
    native_before = sparse.native_identity(machine, source)
    if native_before != integrity["identity"]:
        raise ValueError("native v2 identity differs from complete integrity receipt")
    actual = sparse.metadata(unc)
    if any(actual[key] != expected[key] for key in ("identity", "file_size", "version", "tensor_count", "header_sha256", "table_sha256", "entries")):
        raise ValueError("v2 header/tensor table differs from pinned metadata")
    entries = {entry["name"]: entry for entry in actual["entries"]}
    gate = entries["mtp.layers.0.mlp.experts.gate_up_proj.weight"]
    down = entries["mtp.layers.0.mlp.experts.down_proj.weight"]
    if (gate["dims"], down["dims"]) != ([512, 1280, 2560], [512, 2560, 640]):
        raise ValueError("v2 expert geometry differs")
    if any((entry["store"], entry["variant"]) != (5, 2) for entry in (gate, down)):
        raise ValueError("v2 experts require frozen q4c variant-2 decoder")
    return unc, gate, down, machine, source, native_before, {
        "checkpoint_source": source, "checkpoint_unc": str(unc), "checkpoint_sha256": sparse.CHECKPOINT_SHA256,
        "integrity_receipt_sha256": dynamic.digest(integrity_path), "machine_sha256": dynamic.digest(machine_path),
        "native_identity_before": native_before, "metadata_receipt_sha256": dynamic.digest(metadata_path),
        "v2_header_sha256": actual["header_sha256"], "v2_table_sha256": actual["table_sha256"],
        "metadata_bytes_read": actual["metadata_bytes_read"], "selected_source_ranges": []}


def contribution(x, gate_up, down):
    projected = x @ gate_up
    gate, up = projected[:, :INTERMEDIATE], projected[:, INTERMEDIATE:]
    activated = gate / (1 + np.exp(-gate))
    return (activated * up) @ down


def ordered_reference(contributions, coefficients):
    result = np.zeros((1, WIDTH), dtype=np.float32)
    for position in range(TOP_K):
        result += float(coefficients[position, 0, 0]) * contributions[position]
    return result


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
    prefix = [helper.make_node("Gather", ["bank_gate_up_bf16", "bank_indices"], ["selected_gate_up_bf16"], axis=0),
              helper.make_node("Gather", ["bank_down_bf16", "bank_indices"], ["selected_down_bf16"], axis=0),
              helper.make_node("Cast", ["selected_gate_up_bf16"], ["W_gate_up"], to=TensorProto.FLOAT),
              helper.make_node("Cast", ["selected_down_bf16"], ["W_down"], to=TensorProto.FLOAT)]
    tensors = [external_tensor("bank_gate_up_bf16", [count, WIDTH, 2 * INTERMEDIATE], location, 0, gate_bytes),
               external_tensor("bank_down_bf16", [count, INTERMEDIATE, WIDTH], location, gate_bytes, count * EXPERT_BF16_BYTES - gate_bytes)]
    inputs = [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, WIDTH]),
              helper.make_tensor_value_info("bank_indices", TensorProto.INT64, [TOP_K]),
              helper.make_tensor_value_info("routing_weights", TensorProto.FLOAT, [TOP_K, 1, 1])]
    infos = [helper.make_tensor_value_info(name, dtype, shape) for name, dtype, shape in (
        ("selected_gate_up_bf16", TensorProto.BFLOAT16, [TOP_K, WIDTH, 2 * INTERMEDIATE]),
        ("selected_down_bf16", TensorProto.BFLOAT16, [TOP_K, INTERMEDIATE, WIDTH]),
        ("W_gate_up", TensorProto.FLOAT, [TOP_K, WIDTH, 2 * INTERMEDIATE]),
        ("W_down", TensorProto.FLOAT, [TOP_K, INTERMEDIATE, WIDTH]))]
    graph = helper.make_graph(prefix + list(original.graph.node), "v2_live_bf16_gather_routed_experts", inputs,
                              list(original.graph.output), tensors + list(original.graph.initializer), value_info=infos)
    model = helper.make_model(graph, producer_name="strix-alloy-v2-live-bf16-gather-probe", opset_imports=list(original.opset_import))
    model.ir_version = original.ir_version
    helper.set_model_props(model, {"scope": "two captured real live v2 routes; approximate BF16 routed-expert subgraph only; no complete MLP/MTP/acceptance",
                                  "precision": "BF16 nearest/even constant weights; exact BF16 input widening; FP32 arithmetic/output",
                                  "bank_global_expert_ids": json.dumps(bank_ids),
                                  "runtime_indices": "host-derived sorted-union bank positions; captured global ID order and coefficient pairing preserved",
                                  "original_eight_source_sha256": dynamic.DEPENDENCIES["halogen_npu_parameter_probe.py"],
                                  "gather_to_matmul_prepacking": "unproven"})
    if [node.SerializeToString() for node in model.graph.node[4:]] != [node.SerializeToString() for node in original.graph.node]:
        raise ValueError("original eight operator serializations changed")
    return model


def build(model_path, metadata_path, integrity_path, machine_path):
    data_path = model_path.with_name(model_path.name + ".data")
    receipt_path = model_path.with_suffix(".build.json")
    if any(path.exists() for path in (model_path, data_path, receipt_path)):
        raise FileExistsError("new model/data/build receipt exists; overwrite refused")
    samples, baseline = [], bank.process_memory()
    threads = check_threads()
    deps = dependencies()
    sparse.reserve(samples, WEIGHT_LIMIT)
    started = time.perf_counter_ns()
    feeds, bank_ids, capture_binding = capture_fixtures()
    unc, gate_entry, down_entry, machine, source, native_before, source_binding = source_entries(metadata_path, integrity_path, machine_path)
    routes = {label: capture_binding["fixtures"][label]["original_global_expert_ids"] for label in ("A", "B")}
    # Store only output contributions, then add in captured route order. Sorted
    # sparse decode order must never change the reference's FP32 reduction order.
    contributions = {precision: {x_label: {route_label: np.zeros((TOP_K, 1, WIDTH), dtype=np.float32)
                     for route_label in ("A", "B")} for x_label in ("A", "B")} for precision in ("original_fp32", "bf16")}
    blocks, conversion = [], []
    count = len(bank_ids)
    gate_bytes = count * WIDTH * 2 * INTERMEDIATE * 2
    write_ms = reference_ms = 0.0
    with unc.open("rb") as stream, data_path.open("xb") as output:
        for bank_index, expert_id in enumerate(bank_ids):
            sparse.reserve(samples, EXPLICIT_BUILD_WEIGHT_PEAK)
            gate, record = sparse.expert(stream, gate_entry, expert_id, 2 * INTERMEDIATE)
            source_binding["selected_source_ranges"].append(record)
            down, record = sparse.expert(stream, down_entry, expert_id, WIDTH)
            source_binding["selected_source_ranges"].append(record)
            gate_storage, down_storage = bf16_rne_storage(gate), bf16_rne_storage(down)
            rounded_gate, rounded_down = widen_bf16(gate_storage), widen_bf16(down_storage)
            for name, original, storage, widened, offset in (
                ("gate_up", gate, gate_storage, rounded_gate, bank_index * WIDTH * 2 * INTERMEDIATE * 2),
                ("down", down, down_storage, rounded_down, gate_bytes + bank_index * INTERMEDIATE * WIDTH * 2)):
                block = np.ascontiguousarray(storage.T)
                written_at = time.perf_counter_ns()
                output.seek(offset)
                if output.write(memoryview(block)) != block.nbytes:
                    raise IOError("short BF16 external-data write")
                write_ms += (time.perf_counter_ns() - written_at) / 1e6
                blocks.append({"expert_id": expert_id, "bank_index": bank_index, "tensor": name, "offset": offset,
                               "bytes": block.nbytes, "bf16_storage_sha256": dynamic.array_digest(block)})
                exact = original.view(np.uint32) == widened.view(np.uint32)
                conversion.append({"expert_id": expert_id, "tensor": name, "elements": int(original.size),
                                   "changed_elements": int(np.sum(~exact)), "max_abs_difference": float(np.max(np.abs(original - widened))),
                                   "decoded_fp32_sha256": dynamic.array_digest(original), "bf16_widened_sha256": dynamic.array_digest(widened)})
                block = exact = original = storage = widened = None
            reference_at = time.perf_counter_ns()
            for x_label in ("A", "B"):
                original_result = contribution(feeds[x_label]["x"], gate.T, down.T)
                bf16_result = contribution(feeds[x_label]["x"], rounded_gate.T, rounded_down.T)
                for route_label in ("A", "B"):
                    if expert_id in routes[route_label]:
                        position = routes[route_label].index(expert_id)
                        contributions["original_fp32"][x_label][route_label][position] = original_result
                        contributions["bf16"][x_label][route_label][position] = bf16_result
            reference_ms += (time.perf_counter_ns() - reference_at) / 1e6
            gate = down = gate_storage = down_storage = rounded_gate = rounded_down = original_result = bf16_result = None
            sparse.reserve(samples)
    native_after = sparse.native_identity(machine, source)
    if native_after != native_before:
        raise ValueError("native v2 checkpoint changed during bounded sparse decode")
    source_binding.update(native_identity_after=native_after,
                          source_bytes_read=sum(row["bytes"] for entry in source_binding["selected_source_ranges"] for row in entry["ranges"]),
                          decoded_expert_count=count, decoded_fp32_bytes=count * EXPERT_FP32_BYTES,
                          checkpoint_whole_file_rehashed=False)
    references = {precision: {label: ordered_reference(contributions[precision][label][label], feeds[label]["routing_weights"])
                             for label in ("A", "B")} for precision in ("original_fp32", "bf16")}
    stale = {}
    for label, other in (("A", "B"), ("B", "A")):
        alternatives = {"x": ordered_reference(contributions["bf16"][other][label], feeds[label]["routing_weights"]),
                        "bank_indices": ordered_reference(contributions["bf16"][label][other], feeds[label]["routing_weights"]),
                        "routing_weights": ordered_reference(contributions["bf16"][label][label], feeds[other]["routing_weights"])}
        stale[label] = {name: {"strict_bf16_reference": comparison(value, references["bf16"][label], dynamic.CPU_TOLERANCE),
                              "approx_bf16_reference": comparison(value, references["bf16"][label], dynamic.NPU_TOLERANCE)}
                        for name, value in alternatives.items()}
    if any(row["strict_bf16_reference"]["passed"] or row["approx_bf16_reference"]["passed"] for label in stale.values() for row in label.values()):
        raise ValueError("live fixtures cannot detect every stale runtime input at both labelled tolerances")
    contributions = alternatives = None
    gc.collect()
    bank_bytes = count * EXPERT_BF16_BYTES
    if data_path.stat().st_size != bank_bytes or EXPLICIT_BUILD_WEIGHT_PEAK >= WEIGHT_LIMIT:
        raise ValueError("BF16 bank bytes or explicit build weight peak differs")
    model = build_graph(data_path.name, bank_ids)
    with model_path.open("xb") as output:
        output.write(model.SerializeToString())
    onnx.checker.check_model(str(model_path))
    result = {"schema": 1, "passed": True, "scope": __doc__, "source_sha256": dynamic.digest(__file__),
              "blas_thread_environment": threads, "dependency_sha256": deps,
              "model": str(model_path.resolve()), "model_sha256": dynamic.digest(model_path), "model_bytes": model_path.stat().st_size,
              "external_data": str(data_path.resolve()), "external_data_sha256": dynamic.digest(data_path), "external_data_bytes": bank_bytes,
              "operators": [node.op_type for node in model.graph.node], "original_eight_operators_verified": True,
              "bank_experts": bank_ids, "bank_blocks": blocks, "weight_conversion": conversion,
              "rounding": "BF16 RNE: bits += 0x7fff + ((bits>>16)&1); storage=(bits>>16).astype('<u2'); reference widening uint32(storage)<<16",
              "changed_weight_elements": sum(row["changed_elements"] for row in conversion),
              "total_weight_elements": sum(row["elements"] for row in conversion),
              "capture_binding": capture_binding, "source_binding": source_binding,
              "reference_expression": "independent per-expert FP32 x@weight, gate/(1+exp(-gate)), mul, @down; ordered FP32 coefficient accumulation",
              "reference_outputs": {precision: {label: value.tolist() for label, value in rows.items()} for precision, rows in references.items()},
              "reference_sha256": {precision: {label: dynamic.array_digest(value) for label, value in rows.items()} for precision, rows in references.items()},
              "bf16_reference_against_original": {label: {"strict_original": comparison(references["bf16"][label], references["original_fp32"][label], dynamic.CPU_TOLERANCE),
                                                        "approx_original": comparison(references["bf16"][label], references["original_fp32"][label], dynamic.NPU_TOLERANCE)} for label in ("A", "B")},
              "stale_runtime_input_checks": stale, "reference_preparation_ms": reference_ms, "external_data_write_ms": write_ms,
              "runtime_input_shapes": {name: list(value.shape) for name, value in feeds["A"].items()},
              "runtime_input_sets": {label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in feeds.items()},
              "weight_tensor_limit_bytes": WEIGHT_LIMIT, "explicit_build_weight_peak_bytes": EXPLICIT_BUILD_WEIGHT_PEAK,
              "build_ms": (time.perf_counter_ns() - started) / 1e6, "gather_to_matmul_prepacking": "unproven"}
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
              "timing_scope": "fresh contiguous x/host-derived int64 bank-index/coefficient copies + session.run transfer/execution/output; "
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
        feeds, bank_ids, capture_binding = capture_fixtures()
        if capture_binding != frozen["capture_binding"] or bank_ids != frozen["bank_experts"]:
            raise ValueError("captured live fixture binding differs from build")
        model = onnx.load(str(model_path), load_external_data=False)
        if model.SerializeToString() != build_graph(data_path.name, bank_ids).SerializeToString():
            raise ValueError("model differs from two BF16 Gathers/two FP32 Casts/frozen eight ops")
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
    parser.add_argument("--build", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--provider", choices=("cpu", "npu"), default="cpu")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--reps", type=int, default=8)
    parser.add_argument("--metadata", type=Path, default=Path(r"C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json"))
    parser.add_argument("--integrity", type=Path, default=Path(r"C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.16.2\.local\v2-integrity.json"))
    parser.add_argument("--machine", type=Path, default=Path(r"C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.16.2\.local\machine.json"))
    args = parser.parse_args()
    if args.reps != 8:
        parser.error("candidate replay requires four warmups and eight measured calls")
    if args.build:
        if args.model or args.report or args.ep_dir or args.provider != "cpu":
            parser.error("--build cannot be mixed with replay arguments")
        result = build(args.build, args.metadata, args.integrity, args.machine)
    else:
        if not args.model or not args.report:
            parser.error("replay requires --model and --report")
        result = run(args.model, args.provider, args.report, args.ep_dir)
    excluded = {"calls", "reference_outputs", "bank_blocks", "weight_conversion", "capture_binding", "source_binding", "reserve_samples", "provider_copy_files"}
    print(json.dumps({key: value for key, value in result.items() if key not in excluded}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
