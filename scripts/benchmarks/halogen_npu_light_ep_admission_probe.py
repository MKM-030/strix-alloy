"""Root-only strict Ryzen AI Light EP admission of the frozen tiny graph.

This tests an alternative EP, not VitisAI or another BF16 Gather geometry.
The exact retained eight-op FP32 graph and seeded A/B runtime weights are
reused. No checkpoint, model download, driver update, quantization or custom
QMoE schema is involved. A pass covers only ORT attribution and tiny dynamic
inputs, not internal kernel placement, full MTP, residency or a speed gain.
Root must launch through its exclusive owned-process/memory/deadline guard.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

SELF = Path(__file__).resolve()
ROOT = SELF.parents[2]
LIGHT = "RyzenAILightExecutionProvider"
PACKAGE = Path(r"C:\Program Files\WindowsApps\MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0_x64__8wekyb3d8bbwe")
LIBRARY = PACKAGE / "ExecutionProvider/onnxruntime_providers_ryzenai.dll"
LIBRARY_SHA256 = "ccc3bd0c2a8f519f9cd5fb112491785918810819f80c804302f717d2a93456ec"
MANIFEST_SHA256 = "0a1e15844043769d095bc70a808bbdff9d30c389182b61ddb7d61a7b6a8809a3"
MODEL = Path(r"C:\AI\halogen-mtp-npu\parameter-inputs-20261004\tiny-input-matrices.onnx")
MODEL_SHA256 = "4190ad34d24b563d0f8ca6a6ed8ef02ed96c475c99bec794719fe8f8c1e29036"
CPU_RECEIPT = MODEL.parent / "cpu.json"
CPU_RECEIPT_SHA256 = "2a674030aa90eec083c5eec084b9834ad57cc05c89e21146167131098ad01968"
DEPENDENCIES = {
    "scripts/benchmarks/halogen_npu_parameter_probe.py": "ddd476b25f6e434b03390fb0974d54f157fcd26492417641a5ed9cc38fa15a1c",
    "scripts/benchmarks/halogen_npu_expert_onnx.py": "900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722",
    "scripts/benchmarks/hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
}
NPU_TOLERANCE = {"rtol": .03, "atol": .003}
STRICT_TOLERANCE = {"rtol": 3e-5, "atol": 3e-6}
TENSOR_LIMIT = 8 << 20


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def verify_sources():
    actual = {name: digest(ROOT / name) for name in DEPENDENCIES}
    require(actual == DEPENDENCIES, "Frozen helper source changed")
    require(digest(MODEL) == MODEL_SHA256 and MODEL.stat().st_size == 710, "Retained tiny graph changed")
    require(digest(CPU_RECEIPT) == CPU_RECEIPT_SHA256, "Retained exact A/B fixture receipt changed")
    require(digest(PACKAGE / "AppxManifest.xml") == MANIFEST_SHA256, "Installed package manifest changed")
    require(digest(LIBRARY) == LIBRARY_SHA256 and LIBRARY.stat().st_size == 4368688, "Installed Light EP changed")
    return actual


def run(args):
    require(not args.report.exists() and args.report.parent.is_dir(), "Report must be a fresh file in an existing owned directory")
    result = dict(schema=1, passed=False, scope="tiny synthetic dynamic-weight graph; strict Light EP admission only",
                  source_sha256=digest(SELF), provider_requested=LIGHT, model_sha256=MODEL_SHA256,
                  cpu_fallback_allowed=False, automatic_acquisition_allowed=False, calls=[], session_creations=0,
                  stage="source_validation", provider_options={}, tolerance=NPU_TOLERANCE,
                  tensor_limit_bytes=TENSOR_LIMIT, full_mtp_support_proven=False, internal_placement_proven=False,
                  weight_residency_proven=False, speed_gain_established=False,
                  timing_scope="fresh contiguous host input copies plus session.run; graph initialization/reference/validation excluded")
    runtime = session = options = devices = dll_directory = ort = None
    registered = profile_finished = False
    memory_samples, cleanup_errors = [], []
    try:
        require(all(os.environ.get(name) == "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")),
                "Set all three BLAS/OpenMP thread variables to 1 before Python starts")
        result["dependency_sha256"] = verify_sources()
        sys.path.insert(0, str(ROOT / "server"))
        from host_frames import frame

        def reserve(phase, minimum_gib=18):
            current = frame()
            memory_samples.append(dict(phase=phase, **current))
            require(min(current["available_bytes"], current["commit_headroom_bytes"]) >= minimum_gib * 1024**3,
                    "Physical/commit reserve below " + str(minimum_gib) + " GiB")

        reserve("admission", 22)
        import numpy as np
        import onnx
        import halogen_npu_parameter_probe as tiny
        from halogen_npu_expert_onnx import verified_provider_copy
        require(onnx.load(str(MODEL)).SerializeToString() == tiny.build_graph().SerializeToString(),
                "Model differs from frozen eight-op graph")
        receipt = json.loads(CPU_RECEIPT.read_text(encoding="utf-8"))
        feeds = tiny.fixtures()
        array_hash = lambda value: hashlib.sha256(value.tobytes()).hexdigest()
        require({label: {name: array_hash(value) for name, value in feed.items()} for label, feed in feeds.items()} == receipt["input_sets"],
                "A/B input bytes differ from the original retained CPU receipt")
        expected = {label: tiny.reference(feed) for label, feed in feeds.items()}
        require({label: array_hash(value) for label, value in expected.items()} == receipt["reference_sha256"],
                "Independent references differ from the original retained CPU receipt")
        require(not np.allclose(expected["A"], expected["B"], **NPU_TOLERANCE), "A/B fixtures cannot detect stale data")
        for label, other in (("A", "B"), ("B", "A")):
            for name in feeds[label]:
                stale = tiny.reference(dict(feeds[label], **{name: feeds[other][name]}))
                require(not np.allclose(expected[label], stale, **NPU_TOLERANCE), "Fixture cannot detect stale input: " + label + "/" + name)
        tensor_bytes = sum(value.nbytes for feed in feeds.values() for value in feed.values())
        require(tensor_bytes + 2 * tiny.INPUT_BYTES + sum(value.nbytes for value in expected.values()) < TENSOR_LIMIT,
                "Explicit fixture/copy allocation budget exceeded")
        result.update(input_sets=receipt["input_sets"], reference_sha256=receipt["reference_sha256"],
                      fixture_tensor_bytes=tensor_bytes, feed_bytes_per_call=tiny.INPUT_BYTES,
                      input_shapes={name: list(value.shape) for name, value in feeds["A"].items()})
        chosen_library, verified_files = verified_provider_copy(LIBRARY, args.ep_dir)
        require(digest(chosen_library) == LIBRARY_SHA256, "Verified copy is not the pinned Light library")
        result.update(provider_library=str(chosen_library), provider_library_sha256=LIBRARY_SHA256,
                      provider_copy_files=verified_files)
        reserve("before_registration")
        result["stage"] = "provider_registration"
        from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
        runtime = initialize()
        dll_directory = os.add_dll_directory(str(chosen_library.parent))
        import onnxruntime as ort
        result["ort_version"] = ort.__version__
        ort.register_execution_provider_library(LIGHT, str(chosen_library))
        registered = True
        result["stage"] = "npu_device_selection"
        all_devices = ort.get_ep_devices()
        result["advertised_ep_devices"] = [dict(ep_name=d.ep_name, device_type=str(d.device.type)) for d in all_devices]
        devices = [d for d in all_devices if d.ep_name == LIGHT and d.device.type == ort.OrtHardwareDeviceType.NPU]
        all_devices = None
        require(len(devices) == 1, "Expected exactly one pinned Light EP NPU device")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(args.report.with_suffix(""))
        options.add_provider_for_devices(devices, {})
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        reserve("before_session")
        result["stage"] = "strict_session_admission"
        result["session_creations"] += 1
        started = time.perf_counter_ns()
        session = ort.InferenceSession(str(MODEL), sess_options=options, enable_fallback=False)
        session.disable_fallback()
        result.update(session_providers=session.get_providers(), initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        reserve("after_session")
        result["stage"] = "alternating_replay"
        for index in range(args.reps + 2):
            label = "A" if index % 2 == 0 else "B"
            reserve("before_call_" + str(index))
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied_at = time.perf_counter_ns()
            actual = session.run(None, feed)[0]
            finished_at = time.perf_counter_ns()
            row = dict(call_index=index, warmup=index < 2, input_set=label, actual_shape=list(actual.shape),
                       actual_dtype=str(actual.dtype), actual_output=actual.tolist(), output_sha256=array_hash(actual),
                       host_call_ms=(finished_at - started) / 1e6, prepare_and_copy_ms=(copied_at - started) / 1e6,
                       session_run_ms=(finished_at - copied_at) / 1e6, passed=False)
            result["calls"].append(row)
            require(actual.shape == expected[label].shape and actual.dtype == np.float32, "Returned output geometry/dtype differs")
            row.update(passed=bool(np.allclose(actual, expected[label], **NPU_TOLERANCE)),
                       strict_fp32_passed=bool(np.allclose(actual, expected[label], **STRICT_TOLERANCE)),
                       max_abs_error=float(np.max(np.abs(actual - expected[label]))))
            feed = actual = None
            reserve("after_call_" + str(index))
        result["stage"] = "profile_attribution"
        profile = Path(session.end_profiling())
        profile_finished = True
        nodes = [e for e in json.loads(profile.read_text(encoding="utf-8")) if e.get("cat") == "Node"]
        executed = sorted({e.get("args", {}).get("provider", "<missing>") for e in nodes})
        result.update(profile=str(profile), profile_sha256=digest(profile), node_events=len(nodes), executed_node_providers=executed)
        require(nodes and executed == [LIGHT], "Profile does not prove exclusive Light ORT Node attribution")
        result["numerical_gate_passed"] = all(row["passed"] for row in result["calls"])
        require(result["numerical_gate_passed"], "Tiny dynamic-input numerical gate failed")
        result.update(passed=True, stage="tiny_admission_passed")
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
                ort.unregister_execution_provider_library(LIGHT)
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
        result["reserve_samples"] = memory_samples
        if memory_samples:
            result.update(minimum_available_gib=min(r["available_bytes"] for r in memory_samples) / 1024**3,
                          minimum_commit_headroom_gib=min(r["commit_headroom_bytes"] for r in memory_samples) / 1024**3)
        if cleanup_errors:
            result.update(passed=False, cleanup_errors=cleanup_errors)
        with args.report.open("x", encoding="utf-8") as output:
            json.dump(json_safe(result), output, indent=2, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-owned-admission", action="store_true", required=True)
    parser.add_argument("--expected-probe-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ep-dir", type=Path, required=True)
    parser.add_argument("--reps", type=int, default=2)
    args = parser.parse_args()
    require(digest(SELF) == args.expected_probe_sha256, "Root-reviewed probe source changed")
    require(args.reps in (2, 4), "Admission allows exactly 2 or 4 measured calls")
    result = run(args)
    print(json.dumps(json_safe({key: value for key, value in result.items() if key not in ("calls", "provider_copy_files", "reserve_samples")}), indent=2, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
