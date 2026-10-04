"""Full-width runtime expert probe using bounded real v2 q4c selected weights.

Original eight operators; selected sets 0-9 and 10-19; unchanged FP32 numerical
reference and tolerances. Timed calls include weight transpose/view preparation,
fresh contiguous copies of every runtime input and session.run. One-time sparse
source read/decode and reference preparation are reported separately. NPU launch
requires a root-owned guarded exclusive window.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np
import onnx
from onnx import TensorProto, helper

import halogen_npu_parameter_probe as original
from halogen_npu_v2_sparse import read_sets, reserve, WIDTH, INTERMEDIATE, TOP_K, WEIGHTS_BYTES_PER_SET


INPUT_BYTES = WEIGHTS_BYTES_PER_SET + WIDTH * 4 + TOP_K * 4
TENSOR_LIMIT = 1 << 30
DEPENDENCIES = {
    "halogen_npu_parameter_probe.py": "ddd476b25f6e434b03390fb0974d54f157fcd26492417641a5ed9cc38fa15a1c",
    "halogen_npu_v2_sparse.py": "345f18778deeac5ade76c69f26f6bd2296741a55130d33a9caa0f6506f7e5c79",
    "halogen_npu_mtp_metadata.py": "25e25cf244e1da93d1fefa510ec0c95aefafb29d7fd8d0098237fb55adec0455",
    "hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
}
NPU_TOLERANCE = {"rtol": .03, "atol": .003}
CPU_TOLERANCE = {"rtol": 3e-5, "atol": 3e-6}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def array_digest(value):
    return hashlib.sha256(value.tobytes()).hexdigest()


def verify_dependencies():
    root = Path(__file__).resolve().parent
    actual = {name: digest(root / name) for name in DEPENDENCIES}
    if actual != DEPENDENCIES:
        raise ValueError("frozen original/split dependency source changed")
    return actual


def build_graph():
    verify_dependencies()
    baseline = original.build_graph()
    inputs = [helper.make_tensor_value_info(name, TensorProto.FLOAT, shape) for name, shape in
              [("x", [1, WIDTH]), ("W_gate_up", [TOP_K, WIDTH, 2 * INTERMEDIATE]),
               ("W_down", [TOP_K, INTERMEDIATE, WIDTH]), ("routing_weights", [TOP_K, 1, 1])]]
    graph = helper.make_graph(list(baseline.graph.node), "v2_fullwidth_dynamic_selected_experts", inputs,
                              [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, WIDTH])],
                              list(baseline.graph.initializer))
    model = helper.make_model(graph, producer_name="strix-alloy-v2-dynamic-expert-probe",
                              opset_imports=list(baseline.opset_import))
    model.ir_version = baseline.ir_version
    helper.set_model_props(model, {
        "scope": "real v2 selected q4c weights; full-width eight-op expert subgraph; no live Halogen/MTP",
        "expert_weights": "runtime inputs; selected sets 0-9 and 10-19; no expert initializers",
        "reference": "independent original per-expert FP32 expression; tolerance unchanged",
        "operator_source_sha256": DEPENDENCIES["halogen_npu_parameter_probe.py"],
    })
    if [node.SerializeToString() for node in model.graph.node] != [node.SerializeToString() for node in baseline.graph.node]:
        raise ValueError("frozen original eight operators changed")
    onnx.checker.check_model(model)
    return model


def fixtures(metadata_path, integrity_path, machine_path):
    sets, binding = read_sets(metadata_path, integrity_path, machine_path)
    rng = np.random.default_rng(2026100402)
    feeds = {}
    for label, scale in [("A", .2), ("B", .35)]:
        coefficients = np.arange(1, TOP_K + 1, dtype=np.float32)
        if label == "B":
            coefficients = coefficients[::-1].copy()
        feeds[label] = {"x": rng.normal(0, scale, (1, WIDTH)).astype(np.float32),
                        "W_gate_up": sets[label]["gate_up"], "W_down": sets[label]["down"],
                        "routing_weights": (coefficients / 55).reshape(TOP_K, 1, 1)}
    return feeds, binding


def prepare(feed):
    return {"x": feed["x"], "W_gate_up": feed["W_gate_up"].transpose(0, 2, 1),
            "W_down": feed["W_down"].transpose(0, 2, 1), "routing_weights": feed["routing_weights"]}


def reference(feed):
    """Same independent per-expert FP32 expression as the frozen original."""
    output = np.zeros((1, WIDTH), dtype=np.float32)
    for expert in range(TOP_K):
        projected = feed["x"] @ feed["W_gate_up"][expert]
        gate, up = projected[:, :INTERMEDIATE], projected[:, INTERMEDIATE:]
        activated = gate / (1 + np.exp(-gate))
        contribution = (activated * up) @ feed["W_down"][expert]
        output += float(feed["routing_weights"][expert, 0, 0]) * contribution
    return output


def run(model_path, provider, repetitions, report_path, metadata_path, integrity_path, machine_path, ep_dir=None):
    if report_path.exists():
        raise FileExistsError("report exists; overwrite refused")
    if (provider == "npu") != (ep_dir is not None):
        raise ValueError("NPU requires verified provider copy; CPU must omit --ep-dir")
    result = {"schema": 1, "scope": "real v2 q4c full-width runtime expert graph; original eight ops; not live Halogen or full MTP",
              "passed": False, "provider_requested": provider, "seed": 2026100402,
              "model_sha256": digest(model_path), "cpu_fallback_allowed": provider == "cpu",
              "session_creations": 0, "tensor_limit_bytes": TENSOR_LIMIT,
              "feed_bytes_per_call": INPUT_BYTES, "weights_bytes_per_call": WEIGHTS_BYTES_PER_SET,
              "decoded_weight_sets": {"A": list(range(10)), "B": list(range(10, 20))},
              "warmup_count": 4, "repetitions": repetitions,
              "timing_scope": "weight transpose/view preparation + fresh contiguous copies of all runtime inputs + session.run input transfer/execution/output; "
                              "one-time sparse read/decode, FP32 reference preparation, compilation, validation, array retention and hashing excluded",
              "calls": [], "numerical_gate_passed": False, "timing_qualified": False}
    memory_samples = []
    runtime = session = options = devices = dll_directory = ort = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        model = onnx.load(str(model_path))
        if model.SerializeToString() != build_graph().SerializeToString():
            raise ValueError("model differs from frozen full-width v2 eight-op contract")
        feeds, source_binding = fixtures(metadata_path, integrity_path, machine_path)
        result["source_binding"] = source_binding
        if any(sum(value.nbytes for value in feed.values()) != INPUT_BYTES for feed in feeds.values()):
            raise ValueError("fixture input geometry differs")
        reserve(memory_samples)
        reference_started = time.perf_counter_ns()
        expected = {label: reference(prepare(feed)) for label, feed in feeds.items()}
        result["reference_preparation_ms"] = (time.perf_counter_ns() - reference_started) / 1e6
        tensor_bytes = sum(value.nbytes for feed in feeds.values() for value in feed.values())
        tensor_bytes += sum(value.nbytes for value in expected.values())
        runtime_views = {label: prepare(feed) for label, feed in feeds.items()}
        if tensor_bytes >= TENSOR_LIMIT:
            raise ValueError("fixture tensor limit exceeded")
        tolerance = NPU_TOLERANCE if provider == "npu" else CPU_TOLERANCE
        if np.allclose(expected["A"], expected["B"], **tolerance):
            raise ValueError("fixtures cannot distinguish alternating input sets")
        for label, other in (("A", "B"), ("B", "A")):
            for name in ("x", "W_gate_up", "W_down", "routing_weights"):
                stale = reference(prepare(dict(feeds[label], **{name: feeds[other][name]})))
                if np.allclose(stale, expected[label], **tolerance):
                    raise ValueError("fixture cannot detect stale input: " + label + "/" + name)
        reserve(memory_samples, INPUT_BYTES)
        result.update(tolerance=tolerance, fixture_tensor_bytes=tensor_bytes,
                      dependency_sha256=verify_dependencies(), candidate_graph_operators=len(model.graph.node),
                      original_eight_operators_verified=True,
                      decoded_input_shapes={name: list(value.shape) for name, value in feeds["A"].items()},
                      runtime_input_shapes={name: list(value.shape) for name, value in runtime_views["A"].items()},
                      decoded_input_sets={label: {name: array_digest(value) for name, value in feed.items()}
                                          for label, feed in feeds.items()},
                      runtime_input_sets={label: {name: array_digest(value) for name, value in feed.items()}
                                          for label, feed in runtime_views.items()},
                      reference_sha256={label: array_digest(value) for label, value in expected.items()},
                      reference_outputs={label: value.tolist() for label, value in expected.items()},
                      reference_separation_max_abs=float(np.max(np.abs(expected["A"] - expected["B"]))))
        runtime_views = None
        if provider == "npu":
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers()
                      if ep.name == "VitisAIExecutionProvider")
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
                          provider_library_sha256=digest(chosen_library), provider_copy_files=verified_files,
                          placement_scope="strict ORT Node EP attribution; internal placement needs compiler context")
            ort.register_execution_provider_library(ep.name, str(chosen_library))
            registered = True
            devices = [device for device in ort.get_ep_devices()
                       if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected one VitisAI NPU device")
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["provider_library_sha256"]).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(report_path.parent / "vitisai-cache"),
                                                       "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result["cache_key"] = cache_key
        started = time.perf_counter_ns()
        result["session_creations"] += 1
        if provider == "npu":
            session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False)
        else:
            session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(),
                      initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        for index in range(repetitions + 4):
            label = "A" if index % 2 == 0 else "B"
            reserve(memory_samples, INPUT_BYTES)
            started = time.perf_counter_ns()
            prepared = prepare(feeds[label])
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True)
                    for name, value in prepared.items()}
            copied_at = time.perf_counter_ns()
            actual = session.run(None, feed)[0]
            finished_at = time.perf_counter_ns()
            elapsed_ms = (finished_at - started) / 1e6
            # Keep the full result before any gate. A failing A/B call must not
            # discard its output or prevent collecting the other input set.
            row = {"call_index": index, "warmup": index < 4, "input_set": label,
                   "host_call_ms": elapsed_ms, "prepare_and_copy_ms": (copied_at - started) / 1e6,
                   "session_run_ms": (finished_at - copied_at) / 1e6, "output_sha256": array_digest(actual),
                   "actual_shape": list(actual.shape), "actual_output": actual.tolist(), "passed": False}
            result["calls"].append(row)
            prepared = feed = None
            reserve(memory_samples)
            if actual.shape != expected[label].shape:
                row["error"] = "output shape differs from reference"
                continue
            error = np.abs(actual - expected[label])
            matches = np.isclose(actual, expected[label], **tolerance)
            row.update(passed=bool(matches.all()), max_abs_error=float(error.max()),
                       mismatched_elements=int(np.sum(~matches)), output_elements=int(actual.size))
        profile = Path(session.end_profiling())
        profile_finished = True
        events = json.loads(profile.read_text(encoding="utf-8"))
        nodes = [event for event in events if event.get("cat") == "Node"]
        providers = sorted({event.get("args", {}).get("provider", "<missing>") for event in nodes})
        result.update(profile=str(profile), profile_sha256=digest(profile), node_events=len(nodes),
                      executed_node_providers=providers)
        if provider == "npu" and (not nodes or providers != ["VitisAIExecutionProvider"]):
            raise RuntimeError("profile does not prove every Node executed by VitisAI")
        result["numerical_gate_passed"] = all(row["passed"] for row in result["calls"])
        if result["numerical_gate_passed"]:
            timings = [row["host_call_ms"] for row in result["calls"] if not row["warmup"]]
            result.update(passed=True, timing_qualified=True, mean_host_call_ms=statistics.fmean(timings),
                          median_host_call_ms=statistics.median(timings), min_host_call_ms=min(timings),
                          p95_host_call_ms=sorted(timings)[int(np.ceil(.95 * len(timings))) - 1])
        else:
            result["error"] = "numerical gate failed; all returned A/B arrays retained"
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
        if memory_samples:
            result.update(minimum_available_gib=min(row["available_bytes"] for row in memory_samples) / 1024**3,
                          minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in memory_samples) / 1024**3,
                          reserve_samples=memory_samples)
        if cleanup_errors:
            result.update(passed=False, timing_qualified=False, cleanup_errors=cleanup_errors)
        with report_path.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, help="exclusive new ONNX path; CPU-only graph creation")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--provider", choices=("cpu", "npu"), default="cpu")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--metadata", type=Path, default=Path(r"C:\AI\halogen-mtp-npu\v2-metadata-20261004\mtp-metadata.json"))
    parser.add_argument("--integrity", type=Path, default=Path(r"C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.16.2\.local\v2-integrity.json"))
    parser.add_argument("--machine", type=Path, default=Path(r"C:\Projects\strix-alloy-clean\backends\halogen-wsl2-0.16.2\.local\machine.json"))
    parser.add_argument("--reps", type=int, default=8)
    args = parser.parse_args()
    if args.build:
        if args.model or args.report or args.ep_dir or args.provider != "cpu":
            parser.error("--build cannot be mixed with replay arguments")
        model = build_graph()
        with args.build.open("xb") as output:
            output.write(model.SerializeToString())
        print(json.dumps({"model": str(args.build.resolve()), "model_sha256": digest(args.build),
                          "bytes": args.build.stat().st_size, "operators": [node.op_type for node in model.graph.node],
                          "dependency_sha256": verify_dependencies(), "original_eight_operators_verified": True}))
        return 0
    if not args.model or not args.report or not 2 <= args.reps <= 8 or args.reps % 2:
        parser.error("replay needs --model, --report and even 2..8 --reps")
    result = run(args.model, args.provider, args.reps, args.report, args.metadata, args.integrity, args.machine, args.ep_dir)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("calls", "reference_outputs", "provider_copy_files", "source_binding", "reserve_samples")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
