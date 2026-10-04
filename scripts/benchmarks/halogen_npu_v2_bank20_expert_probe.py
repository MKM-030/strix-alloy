"""Bounded real-v2 20-expert constant bank, runtime Gather, original eight ops.

Only experts 0-19 are decoded. The graph takes x, ten int64 expert IDs and
routing coefficients; immutable FP32 bank weights live in external data.
CPU references/fixtures are hash-bound to the completed dynamic-v2 receipt.
NPU execution requires a root-reviewed exclusive process-owner memory guard.
Gather placement and Gather-to-MatMul prepacking remain unproven.
"""
import argparse
import ctypes
from ctypes import wintypes
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
DYNAMIC_SHA256 = "b8578423352d33bb8c9bebc0e591a2d599d388e401886d6afb654f53b10e045c"
PROVIDER_HELPER_SHA256 = "900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722"
REFERENCE_RECEIPT = Path(r"C:\AI\halogen-mtp-npu\v2-dynamic-guarded-20261004\cpu.json")
REFERENCE_RECEIPT_SHA256 = "def9bc80ac3cf5f25542a8a110101ad11a91fa0116fe5fd00877c8676f323142"
if hashlib.sha256((SOURCE_DIR / "halogen_npu_v2_dynamic_expert_probe.py").read_bytes()).hexdigest() != DYNAMIC_SHA256:
    raise ValueError("frozen dynamic-v2 helper changed")
sys.path.insert(0, str(SOURCE_DIR))
import halogen_npu_v2_dynamic_expert_probe as dynamic
from halogen_npu_v2_sparse import reserve, WIDTH, INTERMEDIATE, TOP_K, WEIGHTS_BYTES_PER_SET

BANK_COUNT = 20
BANK_BYTES = 2 * WEIGHTS_BYTES_PER_SET
GATE_BANK_BYTES = BANK_COUNT * WIDTH * 2 * INTERMEDIATE * 4
FEED_BYTES = WIDTH * 4 + TOP_K * 8 + TOP_K * 4
WEIGHT_LIMIT = 1 << 30
EXPLICIT_BUILD_WEIGHT_PEAK = BANK_BYTES + TOP_K * WIDTH * 2 * INTERMEDIATE * 4


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def process_memory():
    current_process = ctypes.windll.kernel32.GetCurrentProcess
    current_process.restype = wintypes.HANDLE
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    query.restype = wintypes.BOOL
    result = ProcessMemory()
    result.cb = ctypes.sizeof(result)
    if not query(current_process(), ctypes.byref(result), result.cb):
        raise ctypes.WinError()
    return {"private_bytes": result.PrivateUsage, "peak_private_bytes": result.PeakPagefileUsage,
            "working_set_bytes": result.WorkingSetSize, "peak_working_set_bytes": result.PeakWorkingSetSize}


def dependencies():
    result = dynamic.verify_dependencies()
    actual = dynamic.digest(SOURCE_DIR / "halogen_npu_v2_dynamic_expert_probe.py")
    if actual != DYNAMIC_SHA256:
        raise ValueError("frozen dynamic-v2 helper changed")
    provider_helper = dynamic.digest(SOURCE_DIR / "halogen_npu_expert_onnx.py")
    if provider_helper != PROVIDER_HELPER_SHA256:
        raise ValueError("frozen provider-copy helper changed")
    return dict(result, **{"halogen_npu_v2_dynamic_expert_probe.py": actual,
                           "halogen_npu_expert_onnx.py": provider_helper})


def external_tensor(name, shape, location, offset, length):
    tensor = TensorProto(name=name, data_type=TensorProto.FLOAT, dims=shape, data_location=TensorProto.EXTERNAL)
    for key, value in (("location", location), ("offset", str(offset)), ("length", str(length))):
        entry = tensor.external_data.add()
        entry.key, entry.value = key, value
    return tensor


def build_graph(location):
    dependencies()
    original = dynamic.build_graph()
    gathers = [helper.make_node("Gather", ["bank_gate_up", "expert_ids"], ["W_gate_up"], axis=0),
               helper.make_node("Gather", ["bank_down", "expert_ids"], ["W_down"], axis=0)]
    bank = [external_tensor("bank_gate_up", [BANK_COUNT, WIDTH, 2 * INTERMEDIATE], location, 0, GATE_BANK_BYTES),
            external_tensor("bank_down", [BANK_COUNT, INTERMEDIATE, WIDTH], location, GATE_BANK_BYTES, BANK_BYTES - GATE_BANK_BYTES)]
    inputs = [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, WIDTH]),
              helper.make_tensor_value_info("expert_ids", TensorProto.INT64, [TOP_K]),
              helper.make_tensor_value_info("routing_weights", TensorProto.FLOAT, [TOP_K, 1, 1])]
    graph = helper.make_graph(gathers + list(original.graph.node), "v2_bank20_gather_selected_experts", inputs,
                              list(original.graph.output), bank + list(original.graph.initializer),
                              value_info=[helper.make_tensor_value_info("W_gate_up", TensorProto.FLOAT, [TOP_K, WIDTH, 2 * INTERMEDIATE]),
                                          helper.make_tensor_value_info("W_down", TensorProto.FLOAT, [TOP_K, INTERMEDIATE, WIDTH])])
    model = helper.make_model(graph, producer_name="strix-alloy-v2-bank20-expert-probe",
                              opset_imports=list(original.opset_import))
    model.ir_version = original.ir_version
    helper.set_model_props(model, {"scope": "real v2 experts 0-19 only; synthetic x/router; not live Halogen or full MTP",
                                  "expert_weights": "FP32 external constant bank; axis-0 Gather by runtime int64 expert IDs",
                                  "reference": "frozen dynamic-v2 independent FP32 references and tolerances",
                                  "dynamic_helper_sha256": DYNAMIC_SHA256,
                                  "prepacking": "Gather-to-MatMul fusion/prepacking unproven"})
    if [node.SerializeToString() for node in model.graph.node[2:]] != [node.SerializeToString() for node in original.graph.node]:
        raise ValueError("original eight operator serializations changed")
    return model


def fixtures(metadata_path, integrity_path, machine_path):
    if dynamic.digest(REFERENCE_RECEIPT) != REFERENCE_RECEIPT_SHA256:
        raise ValueError("frozen independent reference receipt changed")
    frozen = json.loads(REFERENCE_RECEIPT.read_text(encoding="utf-8"))
    feeds, binding = dynamic.fixtures(metadata_path, integrity_path, machine_path)
    started = time.perf_counter_ns()
    recomputed = {label: dynamic.reference(dynamic.prepare(feed)) for label, feed in feeds.items()}
    reference_ms = (time.perf_counter_ns() - started) / 1e6
    expected = {label: np.asarray(frozen["reference_outputs"][label], dtype=np.float32) for label in ("A", "B")}
    reference_drift = {}
    for label, feed in feeds.items():
        if {name: dynamic.array_digest(value) for name, value in feed.items()} != frozen["decoded_input_sets"][label]:
            raise ValueError("decoded fixture differs from frozen receipt: " + label)
        if dynamic.array_digest(expected[label]) != frozen["reference_sha256"][label]:
            raise ValueError("saved frozen reference array hash differs: " + label)
        reference_matches = np.isclose(recomputed[label], expected[label], **dynamic.CPU_TOLERANCE)
        reference_drift[label] = {"recomputed_sha256": dynamic.array_digest(recomputed[label]),
                                  "frozen_sha256": frozen["reference_sha256"][label],
                                  "max_abs_difference": float(np.max(np.abs(recomputed[label] - expected[label]))),
                                  "passes_unchanged_cpu_tolerance": bool(reference_matches.all()),
                                  "mismatched_elements": int(np.sum(~reference_matches))}
        if not reference_matches.all():
            raise ValueError("independent expression differs from frozen arrays at CPU tolerance: " + label)
    runtime_feeds = {label: {"x": feed["x"], "expert_ids": np.arange(first, first + TOP_K, dtype=np.int64),
                             "routing_weights": feed["routing_weights"]}
                     for label, first, feed in [("A", 0, feeds["A"]), ("B", 10, feeds["B"])]}
    return feeds, runtime_feeds, expected, binding, reference_ms, frozen, reference_drift


def memory_summary(samples, baseline):
    current = process_memory()
    return {"minimum_available_gib": min(row["available_bytes"] for row in samples) / 1024**3,
            "minimum_commit_headroom_gib": min(row["commit_headroom_bytes"] for row in samples) / 1024**3,
            "reserve_samples": samples, "process_memory_baseline": baseline, "process_memory_final": current,
            "peak_private_increase_bytes": max(0, current["peak_private_bytes"] - baseline["private_bytes"]),
            "peak_working_set_increase_bytes": max(0, current["peak_working_set_bytes"] - baseline["working_set_bytes"])}


def build(model_path, metadata_path, integrity_path, machine_path):
    data_path = model_path.with_name(model_path.name + ".data")
    receipt_path = model_path.with_suffix(".build.json")
    if any(path.exists() for path in (model_path, data_path, receipt_path)):
        raise FileExistsError("bank model/data/build receipt exists; overwrite refused")
    samples, baseline = [], process_memory()
    reserve(samples, WEIGHT_LIMIT)
    feeds, runtime_feeds, expected, binding, reference_ms, frozen, reference_drift = fixtures(metadata_path, integrity_path, machine_path)
    copy_ms = write_ms = 0.0
    blocks = []
    with data_path.open("xb") as output:
        for name in ("W_gate_up", "W_down"):
            for label in ("A", "B"):
                reserve(samples, feeds[label][name].nbytes)
                started = time.perf_counter_ns()
                block = np.ascontiguousarray(dynamic.prepare(feeds[label])[name])
                copied_at = time.perf_counter_ns()
                block_hash = hashlib.sha256(memoryview(block)).hexdigest()
                if block_hash != frozen["runtime_input_sets"][label][name]:
                    raise ValueError("constant block differs from frozen runtime-layout weights")
                offset = output.tell()
                write_started = time.perf_counter_ns()
                written = output.write(memoryview(block))
                finished = time.perf_counter_ns()
                if written != block.nbytes:
                    raise IOError("short external-data write")
                copy_ms += (copied_at - started) / 1e6
                write_ms += (finished - write_started) / 1e6
                blocks.append({"input_set": label, "tensor": name, "offset": offset, "bytes": block.nbytes, "sha256": block_hash})
                block = None
    feeds = None
    gc.collect()
    if data_path.stat().st_size != BANK_BYTES or EXPLICIT_BUILD_WEIGHT_PEAK >= WEIGHT_LIMIT:
        raise ValueError("constant bank size or explicit weight peak differs")
    reserve(samples)
    started = time.perf_counter_ns()
    model = build_graph(data_path.name)
    with model_path.open("xb") as output:
        output.write(model.SerializeToString())
    onnx.checker.check_model(str(model_path))
    model_write_check_ms = (time.perf_counter_ns() - started) / 1e6
    started = time.perf_counter_ns()
    data_hash = dynamic.digest(data_path)
    data_hash_ms = (time.perf_counter_ns() - started) / 1e6
    result = {"schema": 1, "passed": True, "scope": __doc__, "source_sha256": dynamic.digest(__file__),
              "blas_thread_environment": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
              "model": str(model_path.resolve()), "model_sha256": dynamic.digest(model_path), "model_bytes": model_path.stat().st_size,
              "external_data": str(data_path.resolve()), "external_data_sha256": data_hash, "external_data_bytes": BANK_BYTES,
              "operators": [node.op_type for node in model.graph.node], "original_eight_operators_verified": True,
              "bank_experts": list(range(BANK_COUNT)), "source_binding": binding, "bank_blocks": blocks,
              "reference_receipt_sha256": REFERENCE_RECEIPT_SHA256, "reference_preparation_ms": reference_ms,
              "reference_recomputation_drift": reference_drift,
              "reference_sha256": {label: dynamic.array_digest(value) for label, value in expected.items()},
              "runtime_input_shapes": {name: list(value.shape) for name, value in runtime_feeds["A"].items()},
              "runtime_input_sets": {label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in runtime_feeds.items()},
              "dependency_sha256": dependencies(), "weight_tensor_limit_bytes": WEIGHT_LIMIT,
              "explicit_build_weight_peak_bytes": EXPLICIT_BUILD_WEIGHT_PEAK,
              "constant_layout_copy_ms": copy_ms, "external_data_write_ms": write_ms,
              "model_write_check_ms": model_write_check_ms, "external_data_hash_ms": data_hash_ms,
              "gather_to_matmul_prepacking": "unproven"}
    result.update(memory_summary(samples, baseline))
    if result["peak_private_increase_bytes"] >= WEIGHT_LIMIT:
        result.update(passed=False, error="CPU build private-memory increase exceeded conservative 1 GiB cap")
    with receipt_path.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    return result


def run(model_path, provider, repetitions, report_path, metadata_path, integrity_path, machine_path, ep_dir=None):
    if report_path.exists():
        raise FileExistsError("report exists; overwrite refused")
    if (provider == "npu") != (ep_dir is not None):
        raise ValueError("NPU requires verified provider copy; CPU must omit --ep-dir")
    samples, baseline = [], process_memory()
    result = {"schema": 1, "scope": __doc__, "passed": False, "provider_requested": provider,
              "blas_thread_environment": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
              "source_sha256": dynamic.digest(__file__), "seed": 2026100402, "calls": [],
              "cpu_fallback_allowed": provider == "cpu", "session_creations": 0,
              "warmup_count": 4, "repetitions": repetitions, "feed_bytes_per_call": FEED_BYTES, "weights_bytes_per_call": 0,
              "constant_bank_bytes": BANK_BYTES, "weight_tensor_limit_bytes": WEIGHT_LIMIT,
              "timing_scope": "fresh contiguous x/int64 expert IDs/routing copies + session.run transfer/execution/output; "
                              "sparse decoding, references, constant-bank construction/verification, load/compilation, retention and hashing excluded",
              "numerical_gate_passed": False, "timing_qualified": False, "gather_to_matmul_prepacking": "unproven"}
    runtime = session = options = devices = dll_directory = ort = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        reserve(samples, WEIGHT_LIMIT)
        data_path = model_path.with_name(model_path.name + ".data")
        build_path = model_path.with_suffix(".build.json")
        build_receipt = json.loads(build_path.read_text(encoding="utf-8"))
        if not build_receipt["passed"] or build_receipt["source_sha256"] != result["source_sha256"]:
            raise ValueError("bank build failed or source differs from frozen build")
        started = time.perf_counter_ns()
        model = onnx.load(str(model_path), load_external_data=False)
        if model.SerializeToString() != build_graph(data_path.name).SerializeToString():
            raise ValueError("model differs from two Gathers plus frozen eight-op contract")
        result.update(model_sha256=dynamic.digest(model_path), external_data_sha256=dynamic.digest(data_path),
                      build_receipt_sha256=dynamic.digest(build_path), dependency_sha256=dependencies(),
                      candidate_graph_operators=len(model.graph.node), original_eight_operators_verified=True)
        if result["model_sha256"] != build_receipt["model_sha256"] or result["external_data_sha256"] != build_receipt["external_data_sha256"] or data_path.stat().st_size != BANK_BYTES:
            raise ValueError("frozen constant model/data identity differs")
        result["constant_model_verification_ms"] = (time.perf_counter_ns() - started) / 1e6
        feeds, runtime_feeds, expected, binding, reference_ms, frozen, reference_drift = fixtures(metadata_path, integrity_path, machine_path)
        tolerance = dynamic.NPU_TOLERANCE if provider == "npu" else dynamic.CPU_TOLERANCE
        if np.allclose(expected["A"], expected["B"], **tolerance):
            raise ValueError("fixtures cannot distinguish changed IDs/x/routing")
        for label, other in (("A", "B"), ("B", "A")):
            for name in ("x", "expert_ids", "routing_weights"):
                replacement = {name: feeds[other][name]} if name != "expert_ids" else {
                    "W_gate_up": feeds[other]["W_gate_up"], "W_down": feeds[other]["W_down"]}
                stale = dynamic.reference(dynamic.prepare(dict(feeds[label], **replacement)))
                if np.allclose(stale, expected[label], **tolerance):
                    raise ValueError("fixture cannot detect stale runtime input: " + label + "/" + name)
        result.update(source_binding=binding, reference_preparation_ms=reference_ms, tolerance=tolerance,
                      reference_receipt_sha256=REFERENCE_RECEIPT_SHA256,
                      reference_recomputation_drift=reference_drift,
                      reference_sha256={label: dynamic.array_digest(value) for label, value in expected.items()},
                      reference_outputs={label: value.tolist() for label, value in expected.items()},
                      runtime_input_shapes={name: list(value.shape) for name, value in runtime_feeds["A"].items()},
                      runtime_input_sets={label: {name: dynamic.array_digest(value) for name, value in feed.items()} for label, feed in runtime_feeds.items()},
                      stale_x_ids_routing_detectable=True)
        if any(sum(value.nbytes for value in feed.values()) != FEED_BYTES for feed in runtime_feeds.values()):
            raise ValueError("runtime feed geometry differs")
        feeds = replacement = stale = frozen = None
        gc.collect()
        reserve(samples, WEIGHT_LIMIT)
        result["process_memory_before_session"] = process_memory()
        result["reference_weights_released_before_session"] = True
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
                          placement_scope="strict ORT Node attribution; Gather/internal placement and prepacking unqualified")
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
        started = time.perf_counter_ns()
        result["session_creations"] += 1
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False) if provider == "npu" else ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(), initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        reserve(samples)
        for index in range(repetitions + 4):
            label = "A" if index % 2 == 0 else "B"
            reserve(samples, FEED_BYTES)
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=value.dtype, order="C", copy=True) for name, value in runtime_feeds[label].items()}
            copied_at = time.perf_counter_ns()
            actual = session.run(None, feed)[0]
            finished = time.perf_counter_ns()
            row = {"call_index": index, "warmup": index < 4, "input_set": label,
                   "host_call_ms": (finished - started) / 1e6, "prepare_and_copy_ms": (copied_at - started) / 1e6,
                   "session_run_ms": (finished - copied_at) / 1e6, "output_sha256": dynamic.array_digest(actual),
                   "actual_shape": list(actual.shape), "actual_output": actual.tolist(), "passed": False}
            result["calls"].append(row)
            feed = None
            reserve(samples)
            if actual.shape != expected[label].shape:
                row["error"] = "output shape differs from frozen reference"
                continue
            matches = np.isclose(actual, expected[label], **tolerance)
            row.update(passed=bool(matches.all()), max_abs_error=float(np.max(np.abs(actual - expected[label]))),
                       mismatched_elements=int(np.sum(~matches)), output_elements=int(actual.size))
        profile = Path(session.end_profiling())
        profile_finished = True
        nodes = [event for event in json.loads(profile.read_text(encoding="utf-8")) if event.get("cat") == "Node"]
        providers = sorted({event.get("args", {}).get("provider", "<missing>") for event in nodes})
        result.update(profile=str(profile), profile_sha256=dynamic.digest(profile), node_events=len(nodes), executed_node_providers=providers)
        expected_provider = "VitisAIExecutionProvider" if provider == "npu" else "CPUExecutionProvider"
        if not nodes or providers != [expected_provider]:
            raise RuntimeError("profile does not prove every Node executed by requested provider")
        result["numerical_gate_passed"] = len(result["calls"]) == repetitions + 4 and all(row["passed"] for row in result["calls"])
        if result["numerical_gate_passed"]:
            measured = [row for row in result["calls"] if not row["warmup"]]
            timings = [row["host_call_ms"] for row in measured]
            result.update(passed=True, timing_qualified=True, mean_host_call_ms=statistics.fmean(timings),
                          mean_prepare_and_copy_ms=statistics.fmean(row["prepare_and_copy_ms"] for row in measured),
                          mean_session_run_ms=statistics.fmean(row["session_run_ms"] for row in measured),
                          median_host_call_ms=statistics.median(timings), min_host_call_ms=min(timings),
                          p95_host_call_ms=sorted(timings)[int(np.ceil(.95 * len(timings))) - 1])
        else:
            result["error"] = "numerical gate failed; every returned A/B array retained"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                result["partial_profile"] = str(session.end_profiling())
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
            result.update(memory_summary(samples, baseline))
            if provider == "cpu" and result["peak_private_increase_bytes"] >= WEIGHT_LIMIT:
                result.update(passed=False, timing_qualified=False, error="CPU private-memory increase exceeded conservative 1 GiB cap")
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
    if args.build:
        if args.model or args.report or args.ep_dir or args.provider != "cpu":
            parser.error("--build cannot be mixed with replay arguments")
        result = build(args.build, args.metadata, args.integrity, args.machine)
    else:
        if not args.model or not args.report or args.reps != 8:
            parser.error("replay needs --model, --report and --reps 8")
        result = run(args.model, args.provider, args.reps, args.report, args.metadata, args.integrity, args.machine, args.ep_dir)
    print(json.dumps({key: value for key, value in result.items() if key not in (
        "calls", "reference_outputs", "provider_copy_files", "source_binding", "reserve_samples")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
