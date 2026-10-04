"""Separate original-ORT normalized-input FC suffix hardware gate.

Root alone executes assets/providers under the outer owned-job 22/18-GiB
guard and must check serving state first. Exact normalized words are bound to
the retained original ORT boundary diagnostic; final seeds use the unchanged
original ORT oracle/tolerances. Native Q8 rounds decoded FC weights to BF16;
the unchanged FP32 matrices here do not establish that native arithmetic.
Whole-row RMS is outside this segment; no CPU fallback or full-D claim.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
LEGACY_SHA256 = "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3"
BASELINE_HELPER_SHA256 = "43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
BOUNDARY_SHA256 = "68ab8fe6124a01e63ef970df9804b2eb90333b3606742b03ade294db46d4802b"
REFERENCE_MODE = "original-ORT-normalized-cut"
WARMUPS, REPS = 4, 8
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
SHAPES = {"e_norm": (1, 2560), "h_norm": (1, 10240)}
TRANSFORMER = HERE / "halogen_npu_v2_d_projection_graph.py"


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


def normalized_inputs(args, baseline_helpers, np):
    if args.boundary_diagnostic_sha256 != BOUNDARY_SHA256:
        raise ValueError("sealed original ORT boundary diagnostic required")
    boundary = baseline_helpers.bounded_json(args.boundary_diagnostic, BOUNDARY_SHA256, 1 << 20)
    if boundary.get("original_model_sha256") != baseline_helpers.MODEL_SHA256 or len(boundary.get("rows", [])) != 2:
        raise ValueError("original ORT normalized-boundary lineage differs")
    feeds, bindings = {}, {}
    for index, label in enumerate(("A", "B")):
        row = boundary["rows"][index]
        if row.get("label") != label or row["differences"]["seed"]["actual_hash"] != baseline_helpers.ORT_SEED_SHA256[label]:
            raise ValueError("boundary normalized inputs and original retained seed oracle differ")
        feeds[label], bindings[label] = {}, {}
        for name, shape in SHAPES.items():
            attribute = name[0] + "_norm_" + label.lower()
            path = getattr(args, attribute + "_u16").resolve(strict=True)
            expected = getattr(args, attribute + "_sha256")
            before = path.stat()
            length = shape[-1] * 2
            if not stat.S_ISREG(before.st_mode) or before.st_size != length:
                raise ValueError("normalized input requires exact regular BF16 extent: " + name)
            with path.open("rb") as stream:
                raw = stream.read(length + 1)
            after = path.stat()
            fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
            if len(raw) != length or hashlib.sha256(raw).hexdigest() != expected or any(getattr(before, field) != getattr(after, field) for field in fields):
                raise ValueError("normalized input hash/identity differs")
            value = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16).view(np.float32).reshape(shape)
            floating_hash = hashlib.sha256(value.tobytes(order="C")).hexdigest()
            if not np.isfinite(value).all() or floating_hash != row["differences"][name]["actual_hash"]:
                raise ValueError("normalized words must exactly match original ORT boundary: " + label + "/" + name)
            feeds[label][name] = value
            bindings[label][name] = dict(path=str(path), sha256=expected, bytes=length, shape=list(shape),
                                         float_array_sha256=floating_hash, lineage="retained original CPU-ORT whole-row D normalization")
    return feeds, bindings


def cpu_gate(args, result, baseline_helpers):
    gate = baseline_helpers.bounded_json(args.cpu_gate, args.cpu_gate_sha256, 16 << 20)
    keys = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "projection_receipt_sha256",
            "transformer_sha256", "baseline_sha256", "boundary_diagnostic_sha256", "normalized_input_binding",
            "original_fixture_binding", "original_runtime_input_sets", "runtime_input_sets",
            "dependency_sha256", "probe_dependency_sha256", "graph_reference_sha256", "required_hardware_partition_outputs")
    required = dict(schema="halogen_v2_count1_D_projection_probe.v1", provider="cpu", passed=True,
                    graph_fidelity_screen_passed=True, output_replay_stability_passed=True, alternating_inputs_changed=True,
                    tolerance=TOLERANCES["cpu"], session_creations=1, warmup_count=WARMUPS, repetitions=REPS,
                    normalization_in_npu_segment=False, native_fc_weight_rounding_modeled=False,
                    native_bit_parity_qualified=False, full_d_claim=False, full_mtp_claim=False,
                    acceptance_claim=False, generic_speed_promotion=False)
    calls = gate.get("calls", [])
    if (any(gate.get(key) != result[key] for key in keys) or any(gate.get(key) != value for key, value in required.items()) or
            gate.get("error") or gate.get("cleanup_errors") or gate.get("reserve_guard_error") or
            gate.get("profile_proof", {}).get("passed") is not True or
            gate["profile_proof"].get("executed_node_providers") != ["CPUExecutionProvider"] or len(calls) != WARMUPS + REPS):
        raise ValueError("same-source successful original-ORT cut CPU gate required before NPU initialization")
    for index, row in enumerate(calls):
        if (row.get("call_index") != index or row.get("input_set") != ("A" if index % 2 == 0 else "B") or
                row.get("warmup") != (index < WARMUPS) or row.get("passed") is not True or row.get("output_stability_passed") is not True):
            raise ValueError("all twelve balanced CPU suffix calls must pass")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256)


def run(args):
    report = args.report.resolve()
    if report.exists() or not report.parent.is_dir():
        raise FileExistsError("exclusive report in existing directory required")
    lock_path = report.with_name(report.name + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema="halogen_v2_count1_D_projection_probe.v1", source_sha256=digest(__file__),
                  reference_mode=REFERENCE_MODE, provider=args.provider, passed=False, wire_mode="D", count=1,
                  tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True, calls=[], session_creations=0,
                  warmup_count=WARMUPS, repetitions=REPS, graph_fidelity_screen_passed=False,
                  output_replay_stability_passed=False, alternating_inputs_changed=False,
                  normalization_in_npu_segment=False, native_fc_weight_rounding_modeled=False,
                  native_bit_parity_qualified=False, full_d_claim=False, full_mtp_claim=False, acceptance_claim=False,
                  generic_speed_promotion=False, outer_owned_job_guard_required=True, root_serving_state_check_required=True,
                  admission_gib=22, reserve_gib=18, baseline_sha256=args.baseline_sha256,
                  boundary_diagnostic_sha256=args.boundary_diagnostic_sha256,
                  scope="separate original ORT normalized-input FC suffix; unchanged decoded FP32 matrices; no native Q8/full D claim",
                  timing_scope="candidate suffix host calls and normalized input copies; excluded normalization/host-GPU transfers/full head")
    session = options = runtime = dll_directory = devices = guard = ort = helpers = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        sealed = {HERE / "halogen_npu_v2_d_prepare_probe.py": LEGACY_SHA256,
                  HERE / "halogen_npu_v2_d_graph_probe.py": BASELINE_HELPER_SHA256,
                  HERE / "halogen_npu_v2_d_prepare.py": BUILDER_SHA256}
        if any(digest(path) != expected for path, expected in sealed.items()):
            raise ValueError("sealed original helper/builder source differs")
        sys.path.insert(0, str(HERE))
        import halogen_npu_v2_d_prepare_probe as helpers
        import halogen_npu_v2_d_graph_probe as baseline_helpers
        if helpers.TOLERANCES != TOLERANCES or baseline_helpers.TOLERANCES != TOLERANCES:
            raise ValueError("original frozen tolerance values differ")
        guard = helpers.ReserveGuard()
        guard.start()
        result["dependency_sha256"] = helpers.dependencies()
        transformer_hash = digest(TRANSFORMER)
        result["probe_dependency_sha256"] = {path.name: expected for path, expected in sealed.items()}
        result["probe_dependency_sha256"][TRANSFORMER.name] = transformer_hash
        import numpy as np
        import halogen_npu_v2_d_prepare as builder
        import halogen_npu_v2_d_projection_graph as transformer
        model_path, receipt_path = args.model.resolve(strict=True), args.projection_receipt.resolve(strict=True)
        candidate, original = transformer.verify_projection(model_path, receipt_path, args.projection_receipt_sha256)
        if candidate["transformer_sha256"] != transformer_hash or candidate["weight_lineage"] != "original-decoded-FP32":
            raise ValueError("this original-ORT cut gate requires the original decoded-FP32 lineage; BF16-rounded weights require their separate native oracle gate")
        original_feeds, original_binding = helpers.fixtures(args, builder, np)
        references, numpy_references, original_hashes, baseline_proof = baseline_helpers.baseline(args, original, original_feeds, original_binding, helpers, np)
        feeds, normalized_binding = normalized_inputs(args, baseline_helpers, np)
        result.update(model=str(model_path), model_sha256=candidate["model_sha256"], data=candidate["data"],
                      data_sha256=candidate["data_sha256"], data_bytes=candidate["data_bytes"],
                      projection_receipt=str(receipt_path), projection_receipt_sha256=args.projection_receipt_sha256,
                      transformer_sha256=transformer_hash, source_model=candidate["source_model"],
                      weight_lineage=candidate["weight_lineage"],
                      source_model_sha256=candidate["source_model_sha256"], source_build_receipt=candidate["source_build_receipt"],
                      source_build_receipt_sha256=candidate["source_build_receipt_sha256"],
                      original_fixture_binding=original_binding, original_runtime_input_sets=original_hashes,
                      normalized_input_binding=normalized_binding, baseline_proof=baseline_proof,
                      runtime_input_sets={label: {name: baseline_helpers.array_hash(value) for name, value in feed.items()} for label, feed in feeds.items()},
                      graph_reference_sha256=baseline_helpers.ORT_SEED_SHA256,
                      independent_numpy_reference_sha256=baseline_helpers.NUMPY_SEED_SHA256,
                      independent_numpy_screen_is_informational=True,
                      required_hardware_partition_outputs=candidate["metadata"]["required_hardware_partition_outputs"],
                      arithmetic=candidate["arithmetic"])
        if args.provider == "npu":
            result["cpu_gate"] = cpu_gate(args, result, baseline_helpers)
        candidate = original = original_feeds = None
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
        options.profile_file_prefix = str(report.with_suffix(""))
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog = Path(ep.library_path).resolve(strict=True)
            chosen, verified = verified_provider_copy(catalog, args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            result.update(catalog_library=str(catalog), provider_library=str(chosen), provider_library_sha256=digest(chosen), provider_copy_files=verified)
            ort.register_execution_provider_library(ep.name, str(chosen))
            registered = True
            devices = [device for device in ort.get_ep_devices() if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected exactly one VitisAI NPU device")
            cache = report.parent / "vitisai-cache"
            cache.mkdir(exist_ok=False)
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" + result["provider_library_sha256"]).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        result["session_creations"] += 1
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False) if args.provider == "npu" else ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False)
        session.disable_fallback()
        if [value.name for value in session.get_inputs()] != list(SHAPES) or [value.name for value in session.get_outputs()] != ["seed"]:
            raise RuntimeError("exact normalized-input/seed-output cut required")
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            if not context_path.is_file() or not 0 < context_path.stat().st_size <= 2 << 20:
                raise RuntimeError("fresh bounded compiler context unavailable")
            proof = helpers.context_proof(json.loads(context_path.read_text(encoding="utf-8")), result["required_hardware_partition_outputs"], cache_key, chosen)
            result.update(context=str(context_path), context_sha256=digest(context_path), context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("every dynamic original suffix value requires strict hw/stx placement")
        import time
        stable_hashes = {}
        for index in range(WARMUPS + REPS):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied = time.perf_counter_ns()
            actual = session.run(["seed"], feed)[0]
            finished = time.perf_counter_ns()
            comparison = helpers.comparison(actual, references[label], TOLERANCES[args.provider], np)
            independent = helpers.comparison(actual, numpy_references[label], TOLERANCES["cpu"], np)
            output_hash = baseline_helpers.array_hash(actual)
            stable = label not in stable_hashes or stable_hashes[label] == output_hash
            stable_hashes.setdefault(label, output_hash)
            result["calls"].append(dict(call_index=index, warmup=index < WARMUPS, input_set=label,
                                        host_call_ms=(finished - started) / 1e6, prepare_and_copy_ms=(copied - started) / 1e6,
                                        session_run_ms=(finished - copied) / 1e6, output_sha256=output_hash,
                                        actual_shape=list(actual.shape), actual_dtype=str(actual.dtype),
                                        actual_output=actual.tolist() if np.isfinite(actual).all() else None,
                                        actual_output_words_u32=actual.view(np.uint32).tolist() if actual.dtype == np.float32 else None,
                                        graph_comparison=comparison, independent_numpy_comparison=independent,
                                        output_stability_passed=stable, passed=comparison["passed"] and stable))
            feed = actual = None
            guard.check()
        profile = Path(session.end_profiling())
        profile_finished = True
        proof = helpers.profile_proof(json.loads(profile.read_text(encoding="utf-8")), args.provider)
        result.update(profile=str(profile), profile_sha256=digest(profile), profile_proof=proof)
        if not proof["passed"]:
            raise RuntimeError("profile does not prove every node used requested provider")
        frozen = {**sealed, TRANSFORMER: transformer_hash, Path(__file__): result["source_sha256"], model_path: result["model_sha256"],
                  Path(result["data"]): result["data_sha256"], receipt_path: args.projection_receipt_sha256,
                  args.baseline: args.baseline_sha256, args.boundary_diagnostic: BOUNDARY_SHA256,
                  Path(result["source_model"]): result["source_model_sha256"], Path(result["source_build_receipt"]): result["source_build_receipt_sha256"]}
        for row in original_binding["A"].values():
            frozen[Path(row["path"])] = row["sha256"]
        for bindings in normalized_binding.values():
            for row in bindings.values():
                frozen[Path(row["path"])] = row["sha256"]
        if args.provider == "npu":
            frozen[args.cpu_gate] = args.cpu_gate_sha256
        if any(digest(path) != expected for path, expected in frozen.items()) or helpers.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen source/model/data/oracle/input/gate changed during replay")
        result["graph_fidelity_screen_passed"] = all(row["graph_comparison"]["passed"] for row in result["calls"])
        result["output_replay_stability_passed"] = all(row["output_stability_passed"] for row in result["calls"])
        result["alternating_inputs_changed"] = stable_hashes["A"] != stable_hashes["B"]
        result["independent_numpy_screen_passed"] = all(row["independent_numpy_comparison"]["passed"] for row in result["calls"])
        if not all(result[key] for key in ("graph_fidelity_screen_passed", "output_replay_stability_passed", "alternating_inputs_changed")):
            raise RuntimeError("original ORT cut seed gate failed; all returned outputs retained")
        times = sorted(row["host_call_ms"] for row in result["calls"] if not row["warmup"])
        result.update(passed=True, candidate_suffix_host_mean_ms=sum(times) / len(times), candidate_suffix_host_min_ms=min(times),
                      candidate_suffix_host_p95_ms=times[math.ceil(.95 * len(times)) - 1],
                      exact_original_seed_bit_parity=all(row["graph_comparison"]["exact_fp32_bit_mismatches"] == 0 for row in result["calls"]))
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
            if guard.error:
                cleanup_errors.append("reserve guard: " + guard.error)
        if cleanup_errors:
            result.update(passed=False, graph_fidelity_screen_passed=False, cleanup_errors=cleanup_errors)
        try:
            with report.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            lock.close()
            lock_path.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "projection-receipt", "baseline", "boundary-diagnostic", "e-u16", "h-u16", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    hash_names = ["projection-receipt-sha256", "baseline-sha256", "boundary-diagnostic-sha256", "e-sha256", "h-sha256"]
    for branch in ("e", "h"):
        for label in ("a", "b"):
            parser.add_argument("--" + branch + "-norm-" + label + "-u16", type=Path, required=True)
            hash_names.append(branch + "-norm-" + label + "-sha256")
    for name in hash_names:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-mode", choices=(REFERENCE_MODE,), required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--cpu-gate", type=Path)
    parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for name in hash_names:
        sha(getattr(args, name.replace("-", "_")))
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None:
            parser.error("NPU requires --ep-dir and independently hashed same-source --cpu-gate")
        sha(args.cpu_gate_sha256)
    elif args.ep_dir is not None or args.cpu_gate is not None or args.cpu_gate_sha256 is not None:
        parser.error("CPU must omit provider-copy and CPU-gate arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "error", "provider", "session_creations", "graph_fidelity_screen_passed", "native_bit_parity_qualified")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
