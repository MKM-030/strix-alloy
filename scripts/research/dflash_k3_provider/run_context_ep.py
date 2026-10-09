"""Explicit root-owned one-row EP probe; imports no numerical runtime at import.

Requires a previously frozen CPU BF16 fixture and local EP library. No driver,
provider acquisition, catalog ensure_ready call, model download or serving hook.
Execute only as a child of root's existing exclusive hardware/memory guard.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import time


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(args):
    destination = Path(args.output).resolve()
    if destination.exists():
        raise FileExistsError("A new explicit result path is required")
    receipt_path, fixture_path = Path(args.export_receipt).resolve(), Path(args.fixture).resolve()
    receipt, fixture = (json.loads(p.read_text(encoding="utf-8")) for p in (receipt_path, fixture_path))
    graph = next(g for g in receipt["graphs"] if g["precision"] == args.precision)
    model_path = Path(graph["path"])
    weights_path = Path(receipt["external_weights_path"])
    if digest(model_path) != graph["sha256"] or digest(weights_path) != receipt["external_weights_sha256"]:
        raise ValueError("Frozen graph/external weights changed")
    if receipt["checkpoint_sha256"] != "35a23c17c248ff2e3296e6b78882b6d955af3092498fb7b6c48be1af4bfa971a":
        raise ValueError("Wrong pinned context source")
    if (fixture.get("rows") != 1 or fixture.get("retained_rows_only") is not True
            or fixture.get("input_scope") not in {"synthetic_component_only", "actual_committed_native_rows"}
            or not fixture.get("source_CPU_oracle") or fixture.get("checkpoint_sha256") != receipt["checkpoint_sha256"]):
        raise ValueError("Explicit retained-R1 and source CPU oracle fixture required")
    library = Path(args.ep_library).resolve(strict=True)
    if digest(library) != args.ep_library_sha256:
        raise ValueError("Root-pinned local EP library changed")
    report = {"schema": "dflash_context_r1_root_EP_probe.v1", "enabled": False,
        "graph": graph, "export_receipt_sha256": digest(receipt_path), "fixture_sha256": digest(fixture_path),
        "fixture_source_CPU_oracle": fixture["source_CPU_oracle"], "input_scope": fixture["input_scope"],
        "precision": args.precision, "runner_sha256": digest(__file__),
        "provider_library": str(library), "provider_library_sha256": args.ep_library_sha256,
        "provider_directory_DLL_sha256": {p.name: digest(p) for p in sorted(library.parent.glob("*.dll"))},
        "cpu_fallback_allowed": args.allow_cpu_fallback, "calls": [], "executed_node_providers": [],
        "NPU_only_node_attribution": False, "source_accuracy_qualified": False,
        "native_transport_measured": False, "serving_throughput_qualified": False,
        "timing_scope": "fresh_owned_host_feature/cos/sin_copy_or_exact_BF16_widen;ORT_binding;dispatch;output_fence;finite_read;owned_host_KV_return_copy;excludes_native_tap/D2H/IPC/GPU_H2D",
        "measurement_completed": False}
    bootstrap_shutdown = dll_directory = ort = session = None
    binding = owners = options = devices = output_owner = finite_owner = None
    registered = False
    try:
        import numpy as np

        def widen(raw):
            return (raw.astype(np.uint32) << 16).view(np.float32)

        def raw_fixture(name, shape):
            row = fixture["tensors"][name]
            path = fixture_path.parent / row["path"]
            if row["shape"] != list(shape) or row["dtype"] != "BF16" or digest(path) != row["sha256"]:
                raise ValueError("Frozen fixture changed: " + name)
            raw = np.fromfile(path, dtype="<u2")
            if raw.size != int(np.prod(shape)):
                raise ValueError("Wrong raw BF16 fixture size")
            raw = raw.reshape(shape)
            if not np.isfinite(widen(raw)).all():
                raise ValueError("Nonfinite selected source fixture")
            return raw

        raw_inputs = {name: raw_fixture(name, shape) for name, shape in
            (("target_features", (1, 12800)), ("cos", (1, 256)), ("sin", (1, 256)))}
        expected = widen(raw_fixture("context_kv", (5, 2, 2, 1, 256))).astype(np.float64)
        # Existing local WinML bootstrap, explicit local EP only. Never acquire.
        from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
        bootstrap_shutdown = initialize()
        dll_directory = os.add_dll_directory(str(library.parent))
        import onnxruntime as ort
        ort.register_execution_provider_library("VitisAIExecutionProvider", str(library))
        registered = True
        devices = [device for device in ort.get_ep_devices()
            if device.ep_name == "VitisAIExecutionProvider" and str(device.device.type).endswith(".NPU")]
        if len(devices) != 1:
            raise RuntimeError("Expected exactly one local VitisAI NPU device")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(destination.with_suffix(""))
        if not args.allow_cpu_fallback:
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        options.add_provider_for_devices(devices, {"cache_dir": str(destination.parent / "context-r1-vitisai-cache"),
            "cache_key": digest(model_path) + args.ep_library_sha256, "enable_cache_file_io_in_mem": "0"})
        started = time.perf_counter_ns()
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False)
        session.disable_fallback()
        report.update(ort_version=ort.__version__, session_providers=session.get_providers(),
            session_initialization_ns=time.perf_counter_ns() - started)
        for index in range(4):
            started = time.perf_counter_ns()
            native = args.precision == "bf16_native"
            feeds = {name: raw.copy() if native else widen(raw) for name, raw in raw_inputs.items()}
            output = np.empty((5, 2, 2, 1, 256), dtype=np.uint16 if native else np.float32)
            finite = np.empty((), dtype=np.bool_)
            binding = session.io_binding()
            owners = []
            for name, value in feeds.items():
                owner = (ort.OrtValue.ortvalue_from_numpy_with_onnx_type(value, 16)
                         if native else ort.OrtValue.ortvalue_from_numpy(value))
                owners.append(owner)
                binding.bind_ortvalue_input(name, owner)
            output_owner = (ort.OrtValue.ortvalue_from_numpy_with_onnx_type(output, 16)
                            if native else ort.OrtValue.ortvalue_from_numpy(output))
            finite_owner = ort.OrtValue.ortvalue_from_numpy(finite)
            owners.extend((output_owner, finite_owner))
            binding.bind_ortvalue_output("context_kv", output_owner)
            binding.bind_ortvalue_output("all_finite", finite_owner)
            binding.synchronize_inputs()
            session.run_with_iobinding(binding)
            binding.synchronize_outputs()
            healthy = bool(finite.item())
            returned = output.copy()
            finished = time.perf_counter_ns()
            actual = widen(returned) if native else returned
            values = actual.astype(np.float64)
            error = np.abs(values - expected)
            nonzero = expected != 0
            numerical_finite = bool(np.isfinite(values).all())
            record = {"call_index": index, "excluded_warmup": index == 0,
                "host_input_to_owned_KV_return_ns": finished - started, "graph_all_finite": healthy,
                "host_outputs_all_finite": bool(np.isfinite(actual).all()),
                "CPU_owner_error": {"max_absolute_error": float(error.max()) if numerical_finite else None,
                    "max_relative_error_nonzero_reference": float((error[nonzero] / np.abs(expected[nonzero])).max()) if numerical_finite and nonzero.any() else None,
                    "exact_element_count": int((values == expected).sum()), "element_count": int(expected.size),
                    "zero_reference_nonzero_actual_count": int(((expected == 0) & (values != 0)).sum())},
                "all_FLOAT_output_values_exactly_widened_BF16": None if native else bool((returned.view(np.uint32) & 0xffff == 0).all())}
            report["calls"].append(record)
            returned_path = destination.parent / f"{destination.stem}.call{index}.kv.{args.precision}.bin"
            returned_path.write_bytes(returned.tobytes())
            record.update(returned_KV_path=str(returned_path), returned_KV_sha256=digest(returned_path))
        profile = Path(session.end_profiling())
        events = json.loads(profile.read_text(encoding="utf-8"))
        nodes = [event for event in events if event.get("cat") == "Node" and event.get("args", {}).get("provider")]
        providers = sorted({event["args"]["provider"] for event in nodes})
        report.update(profile_path=str(profile), profile_sha256=digest(profile),
            executed_node_providers=providers, executed_node_event_count=len(nodes),
            NPU_only_node_attribution=bool(nodes) and providers == ["VitisAIExecutionProvider"],
            placement_limit="ORT EP attribution does not prove every operation runs on physical NPU; preserve compiler partition/context logs",
            measurement_completed=True)
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        if session is not None:
            try:
                report["partial_profile"] = session.end_profiling()
            except Exception as profile_exc:
                report["profile_error"] = str(profile_exc)
    finally:
        binding = owners = output_owner = finite_owner = session = options = devices = None
        gc.collect()
        if registered:
            try:
                ort.unregister_execution_provider_library("VitisAIExecutionProvider")
            except Exception as exc:
                report["unregister_error"] = str(exc)
        if dll_directory is not None:
            try:
                dll_directory.close()
            except Exception as exc:
                report["dll_close_error"] = str(exc)
        if bootstrap_shutdown is not None:
            try:
                bootstrap_shutdown()
            except Exception as exc:
                report["bootstrap_shutdown_error"] = str(exc)
        destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "measurement_completed": report["measurement_completed"],
        "error": report.get("error"), "NPU_only_node_attribution": report["NPU_only_node_attribution"]}))
    return 0 if report["measurement_completed"] and all(r["graph_all_finite"] and r["host_outputs_all_finite"] for r in report["calls"]) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-root-owned", action="store_true", required=True)
    parser.add_argument("--export-receipt", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--precision", choices=("bf16_native", "float_roundtrip"), default="bf16_native")
    parser.add_argument("--ep-library", required=True)
    parser.add_argument("--ep-library-sha256", required=True)
    parser.add_argument("--allow-cpu-fallback", action="store_true")
    parser.add_argument("--output", required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
