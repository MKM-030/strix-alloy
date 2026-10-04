"""Isolated synthetic first GEMM; diagnostic only, not Halogen or full MTP.

One session alternates frozen tiny A/B x and runtime W_gate_up. Every returned
array is retained before evaluating the numerical gate. NPU execution requires
a root-reviewed external guard and an exclusive hardware window.
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

from halogen_npu_parameter_probe import fixtures


INPUT_BYTES = 164096
TENSOR_LIMIT = 64 << 20
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


def build_graph():
    graph = helper.make_graph(
        [helper.make_node("MatMul", ["x", "W_gate_up"], ["gu"])],
        "tiny_first_gemm_runtime_weights",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 64]),
         helper.make_tensor_value_info("W_gate_up", TensorProto.FLOAT, [10, 64, 64])],
        [helper.make_tensor_value_info("gu", TensorProto.FLOAT, [10, 1, 64])])
    model = helper.make_model(graph, producer_name="strix-alloy-first-gemm-precision-probe",
                              opset_imports=[helper.make_opsetid("", 21)])
    model.ir_version = 13
    helper.set_model_props(model, {"scope": "one synthetic first GEMM; no Halogen state or full MTP",
                                   "expert_weights": "runtime input; no expert initializers"})
    onnx.checker.check_model(model)
    return model


def reference(feed):
    """Independent per-expert FP32 NumPy projection, not batched ONNX replay."""
    return np.stack([feed["x"] @ feed["W_gate_up"][expert] for expert in range(10)])


def run(model_path, provider, repetitions, report_path, ep_dir=None):
    if report_path.exists():
        raise FileExistsError("report exists; overwrite refused")
    if (provider == "npu") != (ep_dir is not None):
        raise ValueError("NPU requires verified provider copy; CPU must omit --ep-dir")
    result = {"schema": 1, "scope": "isolated synthetic first GEMM; not Halogen, routing or full MTP",
              "passed": False, "provider_requested": provider, "seed": 2026100402,
              "model_sha256": digest(model_path), "cpu_fallback_allowed": provider == "cpu",
              "session_creations": 0, "tensor_limit_bytes": TENSOR_LIMIT,
              "feed_bytes_per_call": INPUT_BYTES, "warmup_count": 4, "repetitions": repetitions,
              "timing_scope": "fresh contiguous host copies + session.run input transfer/execution/output; "
                              "compilation, validation, array retention and hashing excluded",
              "calls": [], "numerical_gate_passed": False, "timing_qualified": False}
    runtime = session = options = devices = dll_directory = ort = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        model = onnx.load(str(model_path))
        if model.SerializeToString() != build_graph().SerializeToString():
            raise ValueError("model differs from frozen isolated first GEMM contract")
        feeds = {label: {name: feed[name] for name in ("x", "W_gate_up")}
                 for label, feed in fixtures().items()}
        if any(sum(value.nbytes for value in feed.values()) != INPUT_BYTES for feed in feeds.values()):
            raise ValueError("fixture input geometry differs")
        expected = {label: reference(feed) for label, feed in feeds.items()}
        tensor_bytes = sum(value.nbytes for feed in feeds.values() for value in feed.values())
        tensor_bytes += sum(value.nbytes for value in expected.values())
        if tensor_bytes >= TENSOR_LIMIT:
            raise ValueError("fixture tensor limit exceeded")
        tolerance = NPU_TOLERANCE if provider == "npu" else CPU_TOLERANCE
        if np.allclose(expected["A"], expected["B"], **tolerance):
            raise ValueError("fixtures cannot distinguish alternating input sets")
        for label, other in (("A", "B"), ("B", "A")):
            for name in ("x", "W_gate_up"):
                stale = reference(dict(feeds[label], **{name: feeds[other][name]}))
                if np.allclose(stale, expected[label], **tolerance):
                    raise ValueError("fixture cannot detect stale input: " + label + "/" + name)
        result.update(tolerance=tolerance, fixture_tensor_bytes=tensor_bytes,
                      input_sets={label: {name: array_digest(value) for name, value in feed.items()}
                                  for label, feed in feeds.items()},
                      reference_sha256={label: array_digest(value) for label, value in expected.items()},
                      reference_outputs={label: value.tolist() for label, value in expected.items()},
                      reference_separation_max_abs=float(np.max(np.abs(expected["A"] - expected["B"]))))
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
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True)
                    for name, value in feeds[label].items()}
            actual = session.run(None, feed)[0]
            elapsed_ms = (time.perf_counter_ns() - started) / 1e6
            # Keep the full result before any gate. A failing A/B call must not
            # discard its output or prevent collecting the other input set.
            row = {"call_index": index, "warmup": index < 4, "input_set": label,
                   "host_call_ms": elapsed_ms, "output_sha256": array_digest(actual),
                   "actual_shape": list(actual.shape), "actual_output": actual.tolist(), "passed": False}
            result["calls"].append(row)
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
    parser.add_argument("--reps", type=int, default=8)
    args = parser.parse_args()
    if args.build:
        if args.model or args.report or args.ep_dir or args.provider != "cpu":
            parser.error("--build cannot be mixed with replay arguments")
        model = build_graph()
        with args.build.open("xb") as output:
            output.write(model.SerializeToString())
        print(json.dumps({"model": str(args.build.resolve()), "model_sha256": digest(args.build),
                          "bytes": args.build.stat().st_size, "operators": ["MatMul"]}))
        return 0
    if not args.model or not args.report or not 2 <= args.reps <= 8 or args.reps % 2:
        parser.error("replay needs --model, --report and even 2..8 --reps")
    result = run(args.model, args.provider, args.reps, args.report, args.ep_dir)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("calls", "reference_outputs", "provider_copy_files")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
