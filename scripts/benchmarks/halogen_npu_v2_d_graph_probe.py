"""Count1 D cross-EP graph fidelity against frozen retained CPU-ORT seed words.

This is a new, explicit ORT-graph-output screening mode. The original failed
NumPy-oracle runner, outputs and tolerances remain unchanged. Its independent
NumPy comparisons are retained as information, not silently replaced. No
native arithmetic parity, complete head, acceptance or generic speed claim.

Root alone launches under the outer owned-job 22/18-GiB guard. Helpers from the
sealed original runner are imported explicitly; its reference function is not
monkeypatched. NPU initialization requires an independently hashed successful
CPU graph-fidelity receipt from this exact new source and the same bindings.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
LEGACY = HERE / "halogen_npu_v2_d_prepare_probe.py"
LEGACY_SHA256 = "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
MODEL_SHA256 = "3dd6940b38d788643b709837959d36ab16d1b926e548121b6f6efcc554147518"
BUILD_SHA256 = "06bba1a8bb9658047ce12292becf7bbee9d639498a345aaf3019af4540bcfd99"
REFERENCE_MODE = "ORT-graph-output"
SHAPE = (1, 4, 2560)
WARMUPS, REPS = 4, 8
MAX_BASELINE_BYTES, MAX_GATE_BYTES = 16 << 20, 16 << 20
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
# Independently retained boundary diagnostic confirms these final seed hashes.
ORT_SEED_SHA256 = {"A": "4fadb4e59e61b3d1ed75d9279f4c5b017b36f23d277ad7f6d6fb411d81c34bec",
                   "B": "1728c475732e0ed8b265627de771771a294ff1d87194bf3d41d25c16a9a47787"}
NUMPY_SEED_SHA256 = {"A": "6117e5ef852418cd1a710730a12c048106e984809310426c3c44f23938dffffc",
                     "B": "bc4cbd071cc1f241d7be5c927df45162bcbe3cfc2b47183e7911ab46b4b58a9e"}


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


def bounded_json(path, expected, limit):
    sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not 0 < before.st_size <= limit:
        raise ValueError("bounded receipt size exceeded")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    after = path.stat()
    attrs = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if (len(raw) > limit or hashlib.sha256(raw).hexdigest() != expected or
            any(getattr(before, name) != getattr(after, name) for name in attrs)):
        raise ValueError("receipt hash/identity differs")
    return json.loads(raw)


def array_hash(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def seed_array(value, np, raw_words=False):
    result = np.asarray(value, dtype="<u4" if raw_words else np.float32)
    if result.shape != SHAPE:
        raise ValueError("retained seed must have exact count1 shape")
    result = np.ascontiguousarray(result)
    if raw_words:
        result = result.view("<f4")
    if not np.isfinite(result).all() or np.any(result.view(np.uint32) & 0xffff):
        raise ValueError("retained seed must be finite and exactly BF16-widened FLOAT")
    return result


def baseline(args, build, feeds, bindings, helpers, np):
    old = bounded_json(args.baseline, args.baseline_sha256, MAX_BASELINE_BYTES)
    required = dict(schema="halogen_v2_count1_D_probe.v1", provider="cpu", wire_mode="D", count=1,
                    source_sha256=LEGACY_SHA256, builder_sha256=BUILDER_SHA256, model_sha256=MODEL_SHA256,
                    build_receipt_sha256=BUILD_SHA256, tolerance=TOLERANCES["cpu"], session_creations=1,
                    warmup_count=WARMUPS, repetitions=REPS, passed=False, numerical_gate_passed=False,
                    timing_qualified=False, native_bit_parity_qualified=False, ort_version="1.25.2")
    if any(old.get(key) != value for key, value in required.items()):
        raise ValueError("original failed CPU baseline contract differs")
    if (old.get("data_sha256") != build["data_sha256"] or old.get("data_bytes") != build["data_bytes"] or
            old.get("assets_receipt_sha256") != build["assets_receipt_sha256"] or
            old.get("dependency_sha256") != helpers.dependencies() or old.get("fixture_binding") != bindings or
            old.get("cleanup_errors") or old.get("reserve_guard_error") or
            old.get("error") != "RuntimeError: frozen arithmetic screening failed; all returned outputs retained" or
            old.get("profile_proof", {}).get("passed") is not True or
            old["profile_proof"].get("executed_node_providers") != ["CPUExecutionProvider"]):
        raise ValueError("baseline graph/data/feed/profile/cleanup/source proof differs")
    input_hashes = {label: {name: array_hash(value) for name, value in feed.items()} for label, feed in feeds.items()}
    if old.get("runtime_input_sets") != input_hashes:
        raise ValueError("baseline A/B feed hashes differ")
    calls = old.get("calls", [])
    if len(calls) != WARMUPS + REPS:
        raise ValueError("baseline requires exactly12 balanced retained calls")
    expected, independent = {}, {}
    for index, row in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        if (row.get("call_index") != index or row.get("input_set") != label or
                row.get("warmup") != (index < WARMUPS) or row.get("actual_shape") != list(SHAPE) or
                row.get("actual_dtype") != "float32"):
            raise ValueError("baseline retained call identity/shape differs")
        value = seed_array(row["actual_output_words_u32"], np, raw_words=True)
        reported_float = seed_array(row["actual_output"], np)
        if (array_hash(value) != row["output_sha256"] or array_hash(value) != ORT_SEED_SHA256[label] or
                not np.array_equal(value.view(np.uint32), reported_float.view(np.uint32))):
            raise ValueError("retained CPU seed word/float/hash representations differ")
        if label in expected and not np.array_equal(value.view(np.uint32), expected[label].view(np.uint32)):
            raise ValueError("baseline CPU output is not stable for every A/B call")
        expected[label] = value
    for label in ("A", "B"):
        value = seed_array(old["reference_outputs"][label], np)
        if array_hash(value) != old["reference_sha256"][label] or array_hash(value) != NUMPY_SEED_SHA256[label]:
            raise ValueError("independent retained NumPy seed binding differs")
        independent[label] = value
    return expected, independent, input_hashes, dict(
        path=str(args.baseline.resolve()), sha256=args.baseline_sha256, source_sha256=LEGACY_SHA256,
        legacy_passed=False, legacy_numerical_gate_passed=False, legacy_error=old["error"],
        stable_calls=len(calls), seed_sha256=ORT_SEED_SHA256, independent_numpy_sha256=NUMPY_SEED_SHA256,
        ort_version=old["ort_version"],
        original_tolerance=TOLERANCES["cpu"], original_call_comparisons=[row["comparison"] for row in calls],
        original_stale_input_checks=old.get("stale_runtime_input_checks", []))


def verify_cpu_gate(args, bindings, source_hash):
    gate = bounded_json(args.cpu_gate, args.cpu_gate_sha256, MAX_GATE_BYTES)
    required = dict(schema="halogen_v2_count1_D_graph_probe.v1", reference_mode=REFERENCE_MODE,
                    source_sha256=source_hash, provider="cpu", passed=True,
                    graph_fidelity_screen_passed=True, tolerance=TOLERANCES["cpu"],
                    model_sha256=bindings["model_sha256"], data_sha256=bindings["data_sha256"],
                    build_receipt_sha256=bindings["build_receipt_sha256"], baseline_sha256=bindings["baseline_sha256"],
                    runtime_input_sets=bindings["runtime_input_sets"], graph_reference_sha256=ORT_SEED_SHA256,
                    dependency_sha256=bindings["dependency_sha256"], builder_sha256=BUILDER_SHA256,
                    assets_receipt_sha256=bindings["assets_receipt_sha256"], fixture_binding=bindings["fixture_binding"],
                    session_creations=1, warmup_count=WARMUPS, repetitions=REPS,
                    native_bit_parity_qualified=False, full_mtp_claim=False, acceptance_claim=False)
    if (any(gate.get(key) != value for key, value in required.items()) or gate.get("cleanup_errors") or
            gate.get("reserve_guard_error") or gate.get("error") or
            gate.get("profile_proof", {}).get("passed") is not True or
            gate["profile_proof"].get("executed_node_providers") != ["CPUExecutionProvider"] or
            len(gate.get("calls", [])) != WARMUPS + REPS or not all(row.get("passed") is True for row in gate["calls"])):
        raise ValueError("same-source successful CPU graph-fidelity gate required before NPU initialization")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256,
                source_sha256=source_hash, graph_fidelity_screen_passed=True)


def run(args):
    report_path = args.report.resolve()
    if report_path.exists() or not report_path.parent.is_dir():
        raise FileExistsError("report must be exclusive in an existing output directory")
    lock_path = report_path.with_name(report_path.name + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema="halogen_v2_count1_D_graph_probe.v1", reference_mode=REFERENCE_MODE,
                  source_sha256=digest(__file__), passed=False, provider=args.provider, wire_mode="D", count=1,
                  scope="cross-EP execution of fixed count1 D graph against frozen CPU-ORT outputs; independent NumPy failure preserved",
                  tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True,
                  warmup_count=WARMUPS, repetitions=REPS, calls=[], session_creations=0,
                  graph_fidelity_screen_passed=False, cpu_fallback_allowed=args.provider == "cpu",
                  native_bit_parity_qualified=False, full_mtp_claim=False, acceptance_claim=False,
                  generic_speed_promotion=False, baseline_sha256=args.baseline_sha256,
                  outer_owned_job_guard_required=True, admission_gib=22, reserve_gib=18,
                  timing_scope="candidate graph host calls only; measured calls retained after graph-fidelity gate; no native/full-head speed qualification")
    session = options = runtime = dll_directory = devices = guard = ort = helpers = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        if digest(LEGACY) != LEGACY_SHA256 or digest(HERE / "halogen_npu_v2_d_prepare.py") != BUILDER_SHA256:
            raise ValueError("sealed original orchestration/builder source differs")
        sys.path.insert(0, str(HERE))
        import halogen_npu_v2_d_prepare_probe as helpers
        if helpers.TOLERANCES != TOLERANCES:
            raise ValueError("original frozen tolerance values differ")
        guard = helpers.ReserveGuard()
        guard.start()
        result["dependency_sha256"] = helpers.dependencies()
        result["orchestration_source_sha256"] = LEGACY_SHA256
        import numpy as np
        import onnx
        import halogen_npu_v2_d_prepare as builder
        model_path = args.model.resolve(strict=True)
        build_path = args.build_receipt.resolve(strict=True)
        if args.build_receipt_sha256 != BUILD_SHA256:
            raise ValueError("frozen original build receipt SHA256 required")
        build, weights = builder.verify_model(model_path, build_path, args.build_receipt_sha256, "D")
        if build["model_sha256"] != MODEL_SHA256:
            raise ValueError("fixed original D graph identity differs")
        result.update(model=str(model_path), model_sha256=build["model_sha256"], data=build["data"],
                      data_sha256=build["data_sha256"], data_bytes=build["data_bytes"],
                      build_receipt=str(build_path), build_receipt_sha256=args.build_receipt_sha256,
                      assets_receipt=build["assets_receipt"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      builder_sha256=BUILDER_SHA256, arithmetic=build["arithmetic"])
        feeds, fixture_binding = helpers.fixtures(args, builder, np)
        references, numpy_references, input_hashes, baseline_proof = baseline(args, build, feeds, fixture_binding, helpers, np)
        result.update(fixture_binding=fixture_binding, runtime_input_sets=input_hashes,
                      baseline_proof=baseline_proof, graph_reference_sha256=ORT_SEED_SHA256,
                      independent_numpy_reference_sha256=NUMPY_SEED_SHA256,
                      independent_numpy_screen_is_informational=True)
        if args.provider == "npu":
            result["cpu_gate"] = verify_cpu_gate(args, result, result["source_sha256"])
        graph = onnx.load(str(model_path), load_external_data=False)
        dynamic = {value.name for value in graph.graph.input}
        required_outputs, constant_outputs = set(), set()
        matmul_outputs = {name for node in graph.graph.node if node.op_type == "MatMul" for name in node.output}
        for node in graph.graph.node:
            if any(name in dynamic for name in node.input):
                dynamic.update(node.output)
                required_outputs.update(node.output)
            else:
                constant_outputs.update(node.output)
        if len(matmul_outputs) != 2 or "seed" not in required_outputs or not matmul_outputs <= required_outputs:
            raise ValueError("fixed D graph dynamic projection/seed contract differs")
        result.update(required_hardware_partition_outputs=sorted(required_outputs),
                      constant_foldable_node_outputs=sorted(constant_outputs))
        weights = build = graph = None
        gc.collect()
        result["reference_weights_released_before_session"] = True
        if args.provider == "npu":
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers() if ep.name == "VitisAIExecutionProvider")
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError("VitisAI absent; acquisition disabled")
            ready = ep.ensure_ready_async().get()
            guard.check()
            if int(ready.status) != 1:
                raise RuntimeError("VitisAI readiness failed: " + ready.diagnostic_text)
        import onnxruntime as ort
        if ort.__version__ != "1.25.2" or np.__version__ != "2.5.3":
            raise ValueError("frozen CPU-ORT/NumPy runtime version differs")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report_path.with_suffix(""))
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog = Path(ep.library_path).resolve(strict=True)
            chosen, verified = verified_provider_copy(catalog, args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            result.update(catalog_library=str(catalog), provider_library=str(chosen),
                          provider_library_sha256=digest(chosen), provider_copy_files=verified)
            ort.register_execution_provider_library(ep.name, str(chosen))
            registered = True
            devices = [device for device in ort.get_ep_devices() if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected exactly one VitisAI NPU device")
            cache = report_path.parent / "vitisai-cache"
            cache.mkdir(exist_ok=False)
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" + result["provider_library_sha256"]).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        result["session_creations"] += 1
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False) if args.provider == "npu" else ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False)
        session.disable_fallback()
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            if not context_path.is_file() or not 0 < context_path.stat().st_size <= 2 << 20:
                raise RuntimeError("fresh bounded compiler context unavailable")
            context = json.loads(context_path.read_text(encoding="utf-8"))
            proof = helpers.context_proof(context, required_outputs, cache_key, chosen)
            result.update(context=str(context_path), context_sha256=digest(context_path), context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("complete D graph placement unproven by strict hardware context")
        import time
        for index in range(WARMUPS + REPS):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied = time.perf_counter_ns()
            actual = session.run(["seed"], feed)[0]
            finished = time.perf_counter_ns()
            graph_comparison = helpers.comparison(actual, references[label], TOLERANCES[args.provider], np)
            independent_comparison = helpers.comparison(actual, numpy_references[label], TOLERANCES["cpu"], np)
            row = dict(call_index=index, warmup=index < WARMUPS, input_set=label,
                       host_call_ms=(finished - started) / 1e6, prepare_and_copy_ms=(copied - started) / 1e6,
                       session_run_ms=(finished - copied) / 1e6, output_sha256=array_hash(actual),
                       actual_shape=list(actual.shape), actual_dtype=str(actual.dtype),
                       actual_output=actual.tolist() if np.isfinite(actual).all() else None,
                       actual_output_words_u32=actual.view(np.uint32).tolist() if actual.dtype == np.float32 else None,
                       graph_comparison=graph_comparison, independent_numpy_comparison=independent_comparison,
                       passed=graph_comparison["passed"])
            result["calls"].append(row)
            feed = actual = None
            guard.check()
        profile = Path(session.end_profiling())
        profile_finished = True
        proof = helpers.profile_proof(json.loads(profile.read_text(encoding="utf-8")), args.provider)
        result.update(profile=str(profile), profile_sha256=digest(profile), profile_proof=proof)
        if not proof["passed"]:
            raise RuntimeError("profile does not prove all nodes used the requested provider")
        for path, expected in ((LEGACY, LEGACY_SHA256), (Path(__file__), result["source_sha256"]),
                               (model_path, result["model_sha256"]), (result["data"], result["data_sha256"]),
                               (build_path, args.build_receipt_sha256), (args.baseline, args.baseline_sha256)):
            if digest(path) != expected:
                raise RuntimeError("frozen source/model/data/baseline changed during replay")
        if helpers.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen original helper dependencies changed")
        for row in fixture_binding["A"].values():
            if digest(row["path"]) != row["sha256"]:
                raise RuntimeError("captured feed changed during replay")
        if args.provider == "npu" and digest(args.cpu_gate) != args.cpu_gate_sha256:
            raise RuntimeError("CPU graph-fidelity gate changed during replay")
        result["graph_fidelity_screen_passed"] = all(row["passed"] for row in result["calls"])
        result["independent_numpy_screen_passed"] = all(row["independent_numpy_comparison"]["passed"] for row in result["calls"])
        if not result["graph_fidelity_screen_passed"]:
            raise RuntimeError("frozen ORT-graph-output fidelity screen failed; all returned outputs retained")
        measured = [row for row in result["calls"] if not row["warmup"]]
        times = sorted(row["host_call_ms"] for row in measured)
        result.update(passed=True, candidate_graph_host_mean_ms=sum(times) / len(times),
                      candidate_graph_host_min_ms=min(times), candidate_graph_host_p95_ms=times[math.ceil(.95 * len(times)) - 1],
                      exact_graph_reference_bit_parity=all(row["graph_comparison"]["exact_fp32_bit_mismatches"] == 0 for row in result["calls"]))
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                profile = Path(session.end_profiling())
                result.update(partial_profile=str(profile), partial_profile_sha256=digest(profile))
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
        if guard is not None:
            guard.stop()
            result.update(reserve_samples=guard.samples, reserve_guard_error=guard.error)
            if guard.samples:
                result.update(minimum_available_gib=min(row["available_bytes"] for row in guard.samples) / helpers.GIB,
                              minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in guard.samples) / helpers.GIB)
            if guard.error:
                cleanup_errors.append("reserve guard: " + guard.error)
        if cleanup_errors:
            result.update(passed=False, graph_fidelity_screen_passed=False, cleanup_errors=cleanup_errors)
        try:
            with report_path.open("x", encoding="utf-8") as output:
                json.dump(result, output, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
        finally:
            lock.close()
            lock_path.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "build-receipt", "baseline", "e-u16", "h-u16", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("build-receipt-sha256", "baseline-sha256", "e-sha256", "h-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-mode", choices=(REFERENCE_MODE,), required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--cpu-gate", type=Path)
    parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for value in (args.build_receipt_sha256, args.baseline_sha256, args.e_sha256, args.h_sha256):
        sha(value)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None:
            parser.error("NPU requires --ep-dir and independently hashed --cpu-gate")
        sha(args.cpu_gate_sha256)
    elif args.ep_dir is not None or args.cpu_gate is not None or args.cpu_gate_sha256 is not None:
        parser.error("CPU must omit provider-copy and CPU-gate arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "error", "provider", "reference_mode", "session_creations",
                                                     "graph_fidelity_screen_passed", "independent_numpy_screen_passed",
                                                     "native_bit_parity_qualified", "candidate_graph_host_mean_ms")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
