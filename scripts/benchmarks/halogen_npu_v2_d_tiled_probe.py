"""Fixed256 tiled count1 D fidelity with distinct retained ORT/native baselines.

Root alone runs real assets/providers under the outer owned-job 22/18-GiB
guard. Seed fidelity uses the original frozen CPU-ORT seeds and unchanged
tolerances. Hidden RMS diagnostics compare separate original ORT, NumPy and
standalone native word references. Every call retains both partial sums and
both normalized outputs. Changed FP32 reduction order is explicit; there is
no complete-head, acceptance, native graph parity or speed promotion.
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
LEGACY = HERE / "halogen_npu_v2_d_prepare_probe.py"
GRAPH_PROBE = HERE / "halogen_npu_v2_d_graph_probe.py"
TRANSFORMER = HERE / "halogen_npu_v2_d_tiled_graph.py"
LEGACY_SHA256 = "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3"
GRAPH_PROBE_SHA256 = "43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f"
BUILDER_SHA256 = "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544"
TRANSFORMER_SHA256 = "52f8bb4f9546135d1d85c5786468cf65ade68cdeda1cd16ffd7efc276ce56485"
RMS_FIXTURES_SHA256 = "1b0c66d46406598028d573353a6e24f42e54527e69a3cf022bf0ffa4284e15a6"
NATIVE_RMS_REPLAY_SHA256 = "4fecd22ab29a9f6d27139eb3b9c313cd7dd5229c406c84f406e8dfd6bbeed9ec"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
REFERENCE_MODE = "original-ORT-seed-and-distinct-RMS-words"
WARMUPS, REPS = 4, 8
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
OUTPUT_SHAPES = {"seed": (1, 4, 2560), "e_partial_sums": (1, 10, 1),
                 "h_partial_sums": (1, 40, 1), "e_norm": (1, 2560), "h_norm": (1, 10240)}
MAX_GATE_BYTES = 32 << 20


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for payload in iter(lambda: stream.read(1 << 20), b""):
            value.update(payload)
    return value.hexdigest()


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def array_hash(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def read_words(path, expected, np):
    sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != 20480:
        raise ValueError("retained hidden RMS words require exactly20480 regular bytes")
    with path.open("rb") as stream:
        raw = stream.read(20481)
    after = path.stat()
    attrs = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if (len(raw) != 20480 or hashlib.sha256(raw).hexdigest() != expected or
            any(getattr(before, name) != getattr(after, name) for name in attrs)):
        raise ValueError("retained hidden RMS word hash/identity differs")
    words = np.frombuffer(raw, dtype="<u2").copy().reshape(1, 10240)
    value = (words.astype(np.uint32) << 16).view(np.float32)
    if not np.isfinite(value).all():
        raise ValueError("retained hidden RMS reference must be finite")
    return value, dict(path=str(path), sha256=expected, bytes=len(raw))


def rms_references(args, feeds, baseline_helpers, np):
    if args.rms_fixtures_sha256 != RMS_FIXTURES_SHA256 or args.native_rms_replay_sha256 != NATIVE_RMS_REPLAY_SHA256:
        raise ValueError("frozen root RMS fixture/native receipts required")
    fixtures = baseline_helpers.bounded_json(args.rms_fixtures, args.rms_fixtures_sha256, 2 << 20)
    native = baseline_helpers.bounded_json(args.native_rms_replay, args.native_rms_replay_sha256, 16384)
    required = dict(schema="halogen0162.hidden-rms-original-kernel-replay.v1", passed=True,
                    engine_sha256=ENGINE_SHA256, codeobject_sha256=CODE_SHA256,
                    kernel_symbol="_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii",
                    width=10240, groups=1, tensor_bytes=20480, grid=[1, 1, 1], block=[256, 1, 1],
                    shared_bytes=0, default_stream=True, codeobject_engine_offset=331776,
                    launch_attempts=2, launches_ok=2, synchronizations_ok=2, copies_ok=8,
                    allocations_ok=3, free_ok=3, module_loads=1, module_unloads=1, cleanup_errors=0, error="")
    if any(native.get(key) != value for key, value in required.items()):
        raise ValueError("retained successful original native RMS receipt differs")
    if fixtures.get("schema") != 1 or len(fixtures.get("rows", [])) != 2 or len(native.get("fixtures", [])) != 2:
        raise ValueError("exact A/B RMS reference bindings required")
    references, files = {}, []
    proof = dict(fixtures_path=str(args.rms_fixtures.resolve()), fixtures_sha256=args.rms_fixtures_sha256,
                 native_replay_path=str(args.native_rms_replay.resolve()), native_replay_sha256=args.native_rms_replay_sha256,
                 scope="distinct original ORT, independent NumPy and original standalone native h_norm words; e_norm has no retained word oracle",
                 rows=[])
    for index, label in enumerate(("A", "B")):
        row, native_row = fixtures["rows"][index], native["fixtures"][index]
        input_words = (feeds[label]["h"].view(np.uint32) >> 16).astype("<u2")
        input_sha = array_hash(input_words)
        if (row.get("label") != label or native_row.get("id") != label or
                row["files"][label + "-input.u16"]["sha256"] != input_sha or
                native_row.get("input_sha256") != input_sha or
                native_row.get("raw_gamma_sha256") != fixtures["gamma"]["sha256"] or
                native_row.get("completed") is not True or native_row.get("nonfinite_output") != 0):
            raise ValueError("native/ORT/NumPy RMS input or raw gamma binding differs")
        references[label], rows = {}, {}
        for oracle in ("ort", "numpy"):
            name = label + "-" + oracle + "-rms.u16"
            binding = row["files"][name]
            if binding["bytes"] != 20480:
                raise ValueError("original RMS reference extent differs")
            value, bound = read_words(args.rms_fixtures.parent / name, binding["sha256"], np)
            references[label][oracle] = value
            rows[oracle] = bound
            files.append(bound)
        value, bound = read_words(args.native_rms_replay.parent / (label + "-hidden-rms-u16.bin"), native_row["output_sha256"], np)
        references[label]["native"] = value
        rows["native"] = bound
        files.append(bound)
        if not np.array_equal(value.view(np.uint32), references[label]["numpy"].view(np.uint32)):
            raise ValueError("frozen two-call native RMS/NumPy word agreement differs")
        proof["rows"].append(dict(label=label, input_sha256=input_sha, references=rows,
                                  native_equals_numpy=True,
                                  native_ort_word_mismatches=int((value.view(np.uint32) != references[label]["ort"].view(np.uint32)).sum())))
    return references, proof, files


def diagnostic(value, shape, bf16, np):
    valid = value.dtype == np.float32 and value.shape == shape and bool(np.isfinite(value).all())
    lattice = int(((value.view(np.uint32) & 0xffff) != 0).sum()) if valid and bf16 else None
    return dict(passed=valid and (not bf16 or lattice == 0), shape=list(value.shape), dtype=str(value.dtype),
                finite=bool(np.isfinite(value).all()), non_bf16_lattice_elements=lattice,
                sha256=array_hash(value), output_words_u32=value.view(np.uint32).tolist() if value.dtype == np.float32 else None,
                output=value.tolist() if np.isfinite(value).all() else None)


def rms_comparison(actual, expected, tolerance, np):
    if actual.dtype != np.float32 or actual.shape != (1, 10240) or not np.isfinite(actual).all():
        return dict(passed=False, shape_dtype_or_finiteness_error=True)
    bits, wanted = actual.view(np.uint32), expected.view(np.uint32)
    close = np.isclose(actual, expected, **tolerance)
    lattice = int(((bits & 0xffff) != 0).sum())
    return dict(passed=bool(close.all()) and lattice == 0, tolerance=tolerance,
                exact_word_mismatches=int((bits != wanted).sum()), max_abs_error=float(np.max(np.abs(actual - expected))),
                mismatched_elements=int((~close).sum()), non_bf16_lattice_elements=lattice)


def verify_cpu_gate(args, result, baseline_helpers):
    gate = baseline_helpers.bounded_json(args.cpu_gate, args.cpu_gate_sha256, MAX_GATE_BYTES)
    keys = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "tiled_receipt_sha256",
            "transformer_sha256", "baseline_sha256", "runtime_input_sets", "fixture_binding", "rms_reference_proof",
            "dependency_sha256", "probe_dependency_sha256", "graph_reference_sha256",
            "required_hardware_partition_outputs", "fp32_reduction_order_changed")
    required = dict(schema="halogen_v2_count1_D_tiled_probe.v1", provider="cpu", passed=True,
                    graph_fidelity_screen_passed=True, diagnostics_passed=True, tolerance=TOLERANCES["cpu"],
                    output_replay_stability_passed=True, alternating_input_outputs_changed=True,
                    session_creations=1, warmup_count=WARMUPS, repetitions=REPS, native_bit_parity_qualified=False,
                    full_mtp_claim=False, acceptance_claim=False, generic_speed_promotion=False)
    calls = gate.get("calls", [])
    if (any(gate.get(key) != result[key] for key in keys) or
            any(gate.get(key) != value for key, value in required.items()) or gate.get("cleanup_errors") or
            gate.get("reserve_guard_error") or gate.get("error") or
            gate.get("profile_proof", {}).get("passed") is not True or
            gate["profile_proof"].get("executed_node_providers") != ["CPUExecutionProvider"] or
            len(calls) != WARMUPS + REPS):
        raise ValueError("same-source successful tiled CPU gate required before NPU initialization")
    for index, row in enumerate(calls):
        if (row.get("call_index") != index or row.get("input_set") != ("A" if index % 2 == 0 else "B") or
                row.get("warmup") != (index < WARMUPS) or row.get("passed") is not True or
                row.get("output_stability_passed") is not True or
                set(row.get("outputs", {})) != set(OUTPUT_SHAPES) or
                any(value.get("passed") is not True for value in row["outputs"].values())):
            raise ValueError("successful CPU seed and every observable tiled diagnostic required")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256, source_sha256=result["source_sha256"])


def run(args):
    report_path = args.report.resolve()
    if report_path.exists() or not report_path.parent.is_dir():
        raise FileExistsError("report must be exclusive in an existing output directory")
    lock_path = report_path.with_name(report_path.name + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema="halogen_v2_count1_D_tiled_probe.v1", source_sha256=digest(__file__),
                  reference_mode=REFERENCE_MODE, passed=False, provider=args.provider, wire_mode="D", count=1,
                  tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True,
                  warmup_count=WARMUPS, repetitions=REPS, calls=[], session_creations=0,
                  graph_fidelity_screen_passed=False, diagnostics_passed=False,
                  output_replay_stability_passed=False, alternating_input_outputs_changed=False,
                  fp32_reduction_order_changed=True, compiler_fusion_avoidance_qualified=False,
                  native_bit_parity_qualified=False, full_mtp_claim=False, acceptance_claim=False,
                  generic_speed_promotion=False, cpu_fallback_allowed=args.provider == "cpu",
                  baseline_sha256=args.baseline_sha256, outer_owned_job_guard_required=True,
                  admission_gib=22, reserve_gib=18,
                  scope="fixed256 tiled whole-row D candidate; original ORT seed fidelity; distinct ORT/NumPy/native h_norm diagnostics",
                  timing_scope="candidate graph host calls including five observable outputs; no full-head/native/NPU speed promotion")
    session = options = runtime = dll_directory = devices = guard = ort = helpers = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        sealed = {LEGACY: LEGACY_SHA256, GRAPH_PROBE: GRAPH_PROBE_SHA256, TRANSFORMER: TRANSFORMER_SHA256,
                  HERE / "halogen_npu_v2_d_prepare.py": BUILDER_SHA256}
        if any(digest(path) != expected for path, expected in sealed.items()):
            raise ValueError("sealed original orchestration/baseline/builder differs")
        sys.path.insert(0, str(HERE))
        import halogen_npu_v2_d_prepare_probe as helpers
        import halogen_npu_v2_d_graph_probe as baseline_helpers
        if helpers.TOLERANCES != TOLERANCES or baseline_helpers.TOLERANCES != TOLERANCES:
            raise ValueError("original frozen tolerances differ")
        guard = helpers.ReserveGuard()
        guard.start()
        result["dependency_sha256"] = helpers.dependencies()
        transformer_hash = TRANSFORMER_SHA256
        result["probe_dependency_sha256"] = {str(path.name): expected for path, expected in sealed.items()}
        result["probe_dependency_sha256"][TRANSFORMER.name] = transformer_hash
        import numpy as np
        import halogen_npu_v2_d_prepare as builder
        import halogen_npu_v2_d_tiled_graph as transformer
        model_path = args.model.resolve(strict=True)
        tiled_path = args.tiled_receipt.resolve(strict=True)
        tiled, original = transformer.verify_tiled(model_path, tiled_path, args.tiled_receipt_sha256)
        if tiled["transformer_sha256"] != transformer_hash or tiled["metadata"]["output_names"] != list(OUTPUT_SHAPES):
            raise ValueError("reviewed transformer/output contract differs")
        result.update(model=str(model_path), model_sha256=tiled["model_sha256"], data=tiled["data"],
                      data_sha256=tiled["data_sha256"], data_bytes=tiled["data_bytes"],
                      tiled_receipt=str(tiled_path), tiled_receipt_sha256=args.tiled_receipt_sha256,
                      transformer_sha256=transformer_hash, builder_sha256=BUILDER_SHA256,
                      source_model=tiled["source_model"], source_model_sha256=tiled["source_model_sha256"],
                      source_build_receipt=tiled["source_build_receipt"], source_build_receipt_sha256=tiled["source_build_receipt_sha256"],
                      assets_receipt_sha256=tiled["assets_receipt_sha256"], arithmetic=tiled["arithmetic"],
                      required_hardware_partition_outputs=tiled["metadata"]["required_hardware_partition_outputs"],
                      constant_foldable_node_outputs=tiled["metadata"]["constant_foldable_node_outputs"],
                      whole_row_rms=tiled["metadata"]["whole_row_rms"])
        feeds, fixture_binding = helpers.fixtures(args, builder, np)
        references, numpy_references, input_hashes, baseline_proof = baseline_helpers.baseline(args, original, feeds, fixture_binding, helpers, np)
        rms_refs, rms_proof, rms_files = rms_references(args, feeds, baseline_helpers, np)
        result.update(fixture_binding=fixture_binding, runtime_input_sets=input_hashes,
                      baseline_proof=baseline_proof, graph_reference_sha256=baseline_helpers.ORT_SEED_SHA256,
                      independent_numpy_reference_sha256=baseline_helpers.NUMPY_SEED_SHA256,
                      independent_numpy_screen_is_informational=True, rms_reference_proof=rms_proof,
                      rms_comparisons_are_informational=True, e_norm_word_reference_available=False)
        if args.provider == "npu":
            result["cpu_gate"] = verify_cpu_gate(args, result, baseline_helpers)
        tiled = original = None
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
        if [value.name for value in session.get_outputs()] != list(OUTPUT_SHAPES):
            raise RuntimeError("all five observable tiled outputs required")
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            if not context_path.is_file() or not 0 < context_path.stat().st_size <= 2 << 20:
                raise RuntimeError("fresh bounded compiler context unavailable")
            context = json.loads(context_path.read_text(encoding="utf-8"))
            proof = helpers.context_proof(context, result["required_hardware_partition_outputs"], cache_key, chosen)
            result.update(context=str(context_path), context_sha256=digest(context_path), context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("every dynamic tiled value placement unproven by strict hardware context")
        import time
        stable_hashes = {}
        for index in range(WARMUPS + REPS):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied = time.perf_counter_ns()
            outputs = dict(zip(OUTPUT_SHAPES, session.run(list(OUTPUT_SHAPES), feed), strict=True))
            finished = time.perf_counter_ns()
            diagnostics = {name: diagnostic(value, OUTPUT_SHAPES[name], name in ("seed", "e_norm", "h_norm"), np) for name, value in outputs.items()}
            current_hashes = {name: value["sha256"] for name, value in diagnostics.items()}
            stable = label not in stable_hashes or current_hashes == stable_hashes[label]
            if label not in stable_hashes:
                stable_hashes[label] = current_hashes
            graph_comparison = helpers.comparison(outputs["seed"], references[label], TOLERANCES[args.provider], np)
            independent = helpers.comparison(outputs["seed"], numpy_references[label], TOLERANCES["cpu"], np)
            rms = {oracle: rms_comparison(outputs["h_norm"], expected, TOLERANCES[args.provider], np) for oracle, expected in rms_refs[label].items()}
            result["calls"].append(dict(call_index=index, warmup=index < WARMUPS, input_set=label,
                                        host_call_ms=(finished - started) / 1e6, prepare_and_copy_ms=(copied - started) / 1e6,
                                        session_run_ms=(finished - copied) / 1e6, outputs=diagnostics,
                                        graph_comparison=graph_comparison, independent_numpy_comparison=independent,
                                        hidden_rms_comparisons=rms, output_stability_passed=stable,
                                        passed=graph_comparison["passed"] and stable and all(value["passed"] for value in diagnostics.values())))
            feed = outputs = None
            guard.check()
        profile = Path(session.end_profiling())
        profile_finished = True
        proof = helpers.profile_proof(json.loads(profile.read_text(encoding="utf-8")), args.provider)
        result.update(profile=str(profile), profile_sha256=digest(profile), profile_proof=proof)
        if not proof["passed"]:
            raise RuntimeError("profile does not prove every node used the requested provider")
        frozen = {**sealed, TRANSFORMER: transformer_hash, Path(__file__): result["source_sha256"],
                  model_path: result["model_sha256"], Path(result["data"]): result["data_sha256"],
                  tiled_path: args.tiled_receipt_sha256, args.baseline: args.baseline_sha256,
                  args.rms_fixtures: args.rms_fixtures_sha256, args.native_rms_replay: args.native_rms_replay_sha256,
                  Path(result["source_model"]): result["source_model_sha256"],
                  Path(result["source_build_receipt"]): result["source_build_receipt_sha256"]}
        for row in fixture_binding["A"].values():
            frozen[Path(row["path"])] = row["sha256"]
        for row in rms_files:
            frozen[Path(row["path"])] = row["sha256"]
        if args.provider == "npu":
            frozen[args.cpu_gate] = args.cpu_gate_sha256
        if any(digest(path) != expected for path, expected in frozen.items()) or helpers.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen source/graph/data/reference/gate changed during replay")
        result["graph_fidelity_screen_passed"] = all(row["graph_comparison"]["passed"] for row in result["calls"])
        result["diagnostics_passed"] = all(value["passed"] for row in result["calls"] for value in row["outputs"].values())
        result["output_replay_stability_passed"] = all(row["output_stability_passed"] for row in result["calls"])
        result["alternating_input_output_checks"] = {name: stable_hashes["A"][name] != stable_hashes["B"][name] for name in OUTPUT_SHAPES}
        result["alternating_input_outputs_changed"] = all(result["alternating_input_output_checks"].values())
        result["independent_numpy_screen_passed"] = all(row["independent_numpy_comparison"]["passed"] for row in result["calls"])
        if not all(result[key] for key in ("graph_fidelity_screen_passed", "diagnostics_passed",
                                          "output_replay_stability_passed", "alternating_input_outputs_changed")):
            raise RuntimeError("frozen original ORT seed/tiled diagnostic screen failed; every returned output retained")
        times = sorted(row["host_call_ms"] for row in result["calls"] if not row["warmup"])
        result.update(passed=True, candidate_graph_host_mean_ms=sum(times) / len(times),
                      candidate_graph_host_min_ms=min(times), candidate_graph_host_p95_ms=times[math.ceil(.95 * len(times)) - 1],
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
            if guard.samples:
                result.update(minimum_available_gib=min(row["available_bytes"] for row in guard.samples) / helpers.GIB,
                              minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in guard.samples) / helpers.GIB)
            if guard.error:
                cleanup_errors.append("reserve guard: " + guard.error)
        if cleanup_errors:
            result.update(passed=False, graph_fidelity_screen_passed=False, diagnostics_passed=False, cleanup_errors=cleanup_errors)
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
    for name in ("model", "tiled-receipt", "baseline", "e-u16", "h-u16", "rms-fixtures", "native-rms-replay", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("tiled-receipt-sha256", "baseline-sha256", "e-sha256", "h-sha256", "rms-fixtures-sha256", "native-rms-replay-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-mode", choices=(REFERENCE_MODE,), required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--cpu-gate", type=Path)
    parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for value in (args.tiled_receipt_sha256, args.baseline_sha256, args.e_sha256, args.h_sha256,
                  args.rms_fixtures_sha256, args.native_rms_replay_sha256):
        sha(value)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None:
            parser.error("NPU requires --ep-dir and independently hashed --cpu-gate")
        sha(args.cpu_gate_sha256)
    elif args.ep_dir is not None or args.cpu_gate is not None or args.cpu_gate_sha256 is not None:
        parser.error("CPU must omit provider-copy and CPU-gate arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "error", "provider", "session_creations",
                                                     "graph_fidelity_screen_passed", "diagnostics_passed",
                                                     "native_bit_parity_qualified", "candidate_graph_host_mean_ms")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
