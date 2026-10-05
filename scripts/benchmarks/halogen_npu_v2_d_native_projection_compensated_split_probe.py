"""Root-only balanced TwoSum paired-FC diagnostic at unchanged tolerances.

The sealed stable graph/failed CPU receipt remain unchanged. This new sibling
uses identical stable high/residual operands and four MatMuls, changes only
uniform compensated recombination, and retains original BF16 output boundaries.
A same-source successful strict CPU gate is mandatory before NPU initialization.
The IEEE FLOAT TwoSum identity is not assumed for provider BFP arithmetic;
actual placement/profile and unchanged NPU accuracy checks remain required.
No oracle/index-specific correction, live output swap or speed claim exists.
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


HERE = Path(__file__).resolve().parent
NATIVE_PROBE = HERE / "halogen_npu_v2_d_native_projection_probe.py"
NATIVE_PROBE_SHA256 = "7d1f51fd254389906c66b3ce44117fbe889b38b73861d192e4965893f6b0d9b0"
TRANSFORMER = HERE / "halogen_npu_v2_d_native_projection_compensated_split_graph.py"
ORIGINAL_STABLE_PROBE_SHA256 = "2ba71370edddd8d772111a16a985a90e02396066e6d88d04686acccbfa6b2558"
ONE_PASS_PROBE_SHA256 = "a3ed6d88c38126b7636a3f5e233ebfb6787fc935e7f49b5caed52e428ed25c8b"
SEALED_HELPERS = {
    "halogen_npu_v2_d_prepare_probe.py": "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3",
    "halogen_npu_v2_d_graph_probe.py": "43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f",
    "halogen_npu_v2_d_prepare.py": "6334b32fc8a9a5cb792590d0422c0ee1fb532a7c475785f75979962ec80c2544",
    "halogen_npu_v2_d_projection_graph.py": "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd",
    "halogen_npu_v2_d_native_projection_graph.py": "8b4d6b9fab064cb556637398796412cb1ccdd555d56193e20fbc2c57285e0c66",
    NATIVE_PROBE.name: NATIVE_PROBE_SHA256,
    "halogen_npu_v2_d_native_projection_stable_split_graph.py": "94438473e7b1084818515b6c8308b86dc1f24a48cee05fa68e0b1f3c48636566",
    "halogen_npu_v2_d_native_projection_stable_split_probe.py": ORIGINAL_STABLE_PROBE_SHA256,
    "halogen_npu_v2_d_native_projection_split_probe.py": ONE_PASS_PROBE_SHA256,
}
SCHEMA = "halogen_v2_count1_D_native_projection_compensated_split_diagnostic.v1"
REFERENCE_MODE = "original-GPU-Q8-FC-before-seed-add"
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
WARMUPS, REPS = 4, 8
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
INPUT_SHAPES = {"e_high": (1, 2560), "e_low": (1, 2560),
                "h_high": (4, 2560), "h_low": (4, 2560)}
OUTPUT_SHAPES = {"e_projection": (1, 2560), "h_projection": (4, 2560)}
FEED_BYTES = 102400
ORT_OPTIMIZATION = "ORT_DISABLE_ALL"
MAX_HIGH_ITERATIONS = 8
NUMERICAL_ERROR = "RuntimeError: frozen original GPU FC gate failed; both returned projections retained"
IDENTITY_KEYS = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "data_bytes",
                 "projection_receipt_sha256", "transformer_sha256", "weight_lineage",
                 "fc_fixtures_sha256", "native_fc_replay_sha256", "oracle_binding",
                 "normalized_input_sets", "runtime_input_sets", "input_split_diagnostics",
                 "weight_split_diagnostics", "split_algorithm_diagnostics", "dependency_sha256", "probe_dependency_sha256",
                 "required_hardware_partition_outputs", "arithmetic", "immutable_files",
                 "ort_graph_optimization_level", "one_pass_probe_sha256",
                 "stable_high_fixed_point_required", "max_high_iterations",
                 "bounded_nonconvergence_is_failure", "oracle_used_for_operand_preparation",
                 "original_stable_probe_sha256", "recombination", "stable_operands_unchanged",
                 "successful_strict_cpu_gate_required_before_npu")


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def array_hash(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def prepared_inputs(transformer, original, np):
    feed, diagnostics = transformer.prepare_inputs(original["e_norm"], original["h_norm"], np)
    if set(feed) != set(INPUT_SHAPES):
        raise ValueError("exact four-input high/residual ABI required")
    for name, shape in INPUT_SHAPES.items():
        value = feed[name]
        if value.dtype != np.float32 or value.shape != shape or not np.isfinite(value).all():
            raise ValueError("finite FLOAT high/residual geometry differs: " + name)
    if sum(value.nbytes for value in feed.values()) != FEED_BYTES:
        raise ValueError("fixed high/residual input extent differs")
    if set(diagnostics) != {"e", "h"}:
        raise ValueError("stable-high diagnostics require both original branches")
    for facts in diagnostics.values():
        stable = facts.get("stable_high", {})
        if (facts.get("high_idempotence_assumed") is not False or
                facts.get("high_idempotence_verified") is not True or
                facts.get("high_requantization_bit_mismatches") != 0 or
                facts.get("high_requantization_numeric_mismatches") != 0 or
                facts.get("per_value_correction") is not False or
                stable.get("max_iterations") != MAX_HIGH_ITERATIONS or
                stable.get("converged") is not True or
                not isinstance(stable.get("iterations"), int) or
                not 1 <= stable["iterations"] <= MAX_HIGH_ITERATIONS):
            raise ValueError("bounded bit-exact stable-high input proof required")
    return feed, diagnostics


def retained_output(row, shape, np):
    if row.get("actual_shape") != list(shape) or row.get("actual_dtype") != "float32":
        raise ValueError("CPU diagnostic output shape/dtype differs")
    words = np.asarray(row.get("actual_output_words_u32"), dtype="<u4")
    values = np.asarray(row.get("actual_output"), dtype=np.float32)
    if words.shape != shape or values.shape != shape:
        raise ValueError("CPU diagnostic retained output extent differs")
    words, values = np.ascontiguousarray(words), np.ascontiguousarray(values)
    actual = words.view("<f4")
    if (not np.isfinite(actual).all() or np.any(words & 0xffff) or
            not np.array_equal(words, values.view("<u4")) or array_hash(actual) != row.get("output_sha256")):
        raise ValueError("CPU diagnostic word/float/hash/BF16 representations differ")
    return actual


def cpu_diagnostic(args, current, oracles, information, bounded, legacy, helpers, np):
    """Require the completed matched CPU diagnostic to pass before NPU."""
    gate = bounded(args.cpu_gate, args.cpu_gate_sha256, 16 << 20)
    required = dict(schema=SCHEMA, provider="cpu", diagnostic_only=True, diagnostic_completed=True,
                    passed=True, cpu_passed=True, native_FC_screen_passed=True,
                    successful_strict_cpu_gate_required_before_npu=True,
                    integration_admission=False, halogen_output_swap=False, acceleration_claim=False,
                    reference_mode=REFERENCE_MODE, wire_mode="D", count=1,
                    tolerance=TOLERANCES["cpu"], tolerance_frozen_before_session=True,
                    ort_graph_optimization_level=ORT_OPTIMIZATION,
                    one_pass_probe_sha256=ONE_PASS_PROBE_SHA256,
                    stable_high_fixed_point_required=True, max_high_iterations=MAX_HIGH_ITERATIONS,
                    bounded_nonconvergence_is_failure=True, oracle_used_for_operand_preparation=False,
                    session_creations=1, warmup_count=WARMUPS, repetitions=REPS,
                    output_replay_stability_passed=True, alternating_inputs_changed=True,
                    normalization_in_npu_segment=False, seed_add_implemented=False,
                    native_bit_parity_qualified=False, embedding_rms_qualified=False,
                    full_d_claim=False, full_mtp_claim=False, acceptance_claim=False,
                    generic_speed_promotion=False, timing_qualified=False,
                    reference_weights_released_before_session=True)
    if (any(gate.get(key) != value for key, value in required.items()) or
            any(gate.get(key) != current[key] for key in IDENTITY_KEYS) or
            gate.get("cleanup_errors") or gate.get("reserve_guard_error") or
            gate.get("error") is not None):
        raise ValueError("same-candidate completed CPU precision diagnostic required")
    profile = bounded(Path(gate["profile"]), gate["profile_sha256"], 16 << 20)
    proof = helpers.profile_proof(profile, "cpu")
    if proof != gate.get("profile_proof") or not proof["passed"]:
        raise ValueError("CPU diagnostic profile does not prove exclusive CPU execution")
    calls = gate.get("calls", [])
    if len(calls) != WARMUPS + REPS:
        raise ValueError("CPU diagnostic requires exactly12 balanced calls")
    stable, numerical = {}, True
    for index, row in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        if (row.get("call_index") != index or row.get("input_set") != label or
                row.get("warmup") != (index < WARMUPS) or row.get("output_stability_passed") is not True or
                row.get("runtime_input_sets") != current["runtime_input_sets"][label] or
                row.get("input_split_diagnostics") != current["input_split_diagnostics"][label] or
                set(row.get("outputs", {})) != set(OUTPUT_SHAPES)):
            raise ValueError("CPU diagnostic balanced call identity/stability differs")
        row_passed = True
        hashes = {}
        for name, shape in OUTPUT_SHAPES.items():
            record = row["outputs"][name]
            actual = retained_output(record, shape, np)
            metric = legacy.comparison(actual, oracles[label][name], shape, TOLERANCES["cpu"], np)
            informational = {mode: legacy.comparison(actual, expected, shape, TOLERANCES["cpu"], np)
                             for mode, expected in information[label][name].items()}
            if metric != record.get("native_comparison") or informational != record.get("independent_numpy_comparisons"):
                raise ValueError("CPU diagnostic frozen-oracle metrics differ from retained values")
            row_passed = row_passed and metric["passed"]
            hashes[name] = array_hash(actual)
        if row.get("passed") is not row_passed or (label in stable and hashes != stable[label]):
            raise ValueError("CPU diagnostic numerical status or repeat hashes differ")
        stable.setdefault(label, hashes)
        numerical = numerical and row_passed
    changed = {name: stable["A"][name] != stable["B"][name] for name in OUTPUT_SHAPES}
    if (not all(changed.values()) or gate.get("alternating_input_output_checks") != changed or
            gate.get("native_FC_screen_passed") is not numerical or gate.get("passed") is not numerical or
            gate.get("cpu_passed") is not numerical or
            gate.get("error") != (None if numerical else NUMERICAL_ERROR)):
        raise ValueError("CPU diagnostic screen/stability status was not reported faithfully")
    if gate.get("timing_observations") != timing_observations(calls):
        raise ValueError("CPU diagnostic timing summaries differ from retained calls")
    if not numerical:
        raise ValueError("successful unchanged strict CPU gate required before NPU initialization")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256,
                profile=gate["profile"], profile_sha256=gate["profile_sha256"], profile_proof=proof,
                cpu_passed=numerical, completed=True, integration_admission=False,
                numerical_failure_only=not numerical,
                scope="same-source numerical evidence for standalone NPU diagnostic only")


def timing_observations(calls):
    measured = [row for row in calls if not row["warmup"]]
    if len(measured) != REPS:
        raise ValueError("timing observation requires all8 measured calls")
    result = dict(measured_calls=REPS, qualified_for_acceleration=False)
    for name in ("host_call_ms", "prepare_and_copy_ms", "session_run_ms"):
        values = sorted(row[name] for row in measured)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("finite nonnegative observed timing required")
        result[name] = dict(mean=sum(values) / REPS, minimum=values[0], maximum=values[-1],
                            median=(values[REPS // 2 - 1] + values[REPS // 2]) / 2,
                            p95=values[math.ceil(.95 * REPS) - 1])
    return result


def run(args):
    report = args.report.resolve()
    if report.exists() or not report.parent.is_dir():
        raise FileExistsError("exclusive report in existing directory required")
    lock_path = report.with_name(report.name + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema=SCHEMA, source_sha256=digest(__file__), provider=args.provider,
                  diagnostic_only=True, diagnostic_completed=False, integration_admission=False,
                  halogen_output_swap=False, acceleration_claim=False, passed=False, cpu_passed=None,
                  reference_mode=REFERENCE_MODE, wire_mode="D", count=1, weight_lineage=WEIGHT_LINEAGE,
                  tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True,
                  ort_graph_optimization_level=ORT_OPTIMIZATION,
                  one_pass_probe_sha256=ONE_PASS_PROBE_SHA256,
                  original_stable_probe_sha256=ORIGINAL_STABLE_PROBE_SHA256,
                  successful_strict_cpu_gate_required_before_npu=True,
                  stable_high_fixed_point_required=True, max_high_iterations=MAX_HIGH_ITERATIONS,
                  bounded_nonconvergence_is_failure=True, oracle_used_for_operand_preparation=False,
                  calls=[], session_creations=0, warmup_count=WARMUPS, repetitions=REPS,
                  feed_bytes_per_call=FEED_BYTES, native_FC_screen_passed=False,
                  output_replay_stability_passed=False, alternating_inputs_changed=False,
                  native_bit_parity_qualified=False, seed_add_implemented=False,
                  embedding_rms_qualified=False, full_d_claim=False, full_mtp_claim=False,
                  acceptance_claim=False, generic_speed_promotion=False, timing_qualified=False,
                  normalization_in_npu_segment=False, native_q8_affine_fma_decoder_proved=False,
                  outer_owned_job_guard_required=True, root_exclusive_serving_state_check_required=True,
                  admission_gib=22, reserve_gib=18, fc_fixtures_sha256=args.fc_fixtures_sha256,
                  native_fc_replay_sha256=args.native_fc_replay_sha256,
                  scope="one bounded compensated four-term paired-FC diagnostic against unchanged original GPU outputs",
                  timing_scope="dynamic bounded stable-high/residual preparation including reconstruction/requantization diagnostics and "
                               "preparation hashes + "
                               "fresh contiguous copies + session.run; "
                               "compile/post-run validation and hashing/static weight split and live transport excluded")
    session = options = runtime = dll_directory = devices = guard = ort = helpers = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        sealed = {HERE / name: expected for name, expected in SEALED_HELPERS.items()}
        sealed[TRANSFORMER] = sha(args.split_transformer_sha256)
        if any(digest(path) != expected for path, expected in sealed.items()):
            raise ValueError("sealed original/split helper source differs")
        sys.path.insert(0, str(HERE))
        import halogen_npu_v2_d_prepare_probe as helpers
        import halogen_npu_v2_d_graph_probe as baseline_helpers
        import halogen_npu_v2_d_native_projection_probe as legacy
        import halogen_npu_v2_d_native_projection_compensated_split_graph as transformer
        if any(module.TOLERANCES != TOLERANCES for module in (helpers, baseline_helpers, legacy)):
            raise ValueError("original frozen tolerances differ")
        if legacy.REFERENCE_MODE != REFERENCE_MODE or legacy.WEIGHT_LINEAGE != WEIGHT_LINEAGE:
            raise ValueError("original native oracle or weight lineage differs")
        guard = helpers.ReserveGuard()
        guard.start()
        result["dependency_sha256"] = helpers.dependencies()
        result["probe_dependency_sha256"] = {path.name: expected for path, expected in sealed.items()}
        import numpy as np
        model_path = args.model.resolve(strict=True)
        receipt_path = args.projection_receipt.resolve(strict=True)
        candidate, original = transformer.verify_split(model_path, receipt_path, args.projection_receipt_sha256)
        if (candidate["transformer_sha256"] != args.split_transformer_sha256 or
                candidate["weight_lineage"] != WEIGHT_LINEAGE or
                candidate["metadata"]["output_names"] != list(OUTPUT_SHAPES) or
                candidate["metadata"]["input_shapes"] != {name: list(shape) for name, shape in INPUT_SHAPES.items()}):
            raise ValueError("reviewed four-term input/weight/output contract differs")
        if (candidate.get("stable_operands_unchanged") is not True or
                candidate.get("reused_stable_weight_data") is not True or
                candidate.get("recombination") != transformer.RECOMBINATION or
                candidate.get("successful_strict_cpu_gate_required_before_npu") is not True):
            raise ValueError("unchanged stable operands and uniform compensated recombination required")
        algorithm = candidate["split_diagnostics"]
        if (algorithm.get("stable_high_fixed_point_required") is not True or
                algorithm.get("max_high_iterations") != MAX_HIGH_ITERATIONS or
                algorithm.get("iteration_condition") != "bit-exact Q(high)==high" or
                algorithm.get("bounded_nonconvergence_is_failure") is not True or
                algorithm.get("per_value_correction") is not False):
            raise ValueError("reviewed bounded generic stable-high algorithm required")
        immutable = candidate["immutable_files"]
        if not isinstance(immutable, list) or not immutable:
            raise ValueError("split candidate immutable source bindings required")
        for item in immutable:
            if set(item) != {"path", "sha256"} or digest(Path(item["path"])) != sha(item["sha256"]):
                raise ValueError("split candidate immutable source binding differs")
        feeds, oracles, information, oracle_binding, oracle_files = legacy.references(
            args, original, baseline_helpers.bounded_json, np)
        runtime_hashes, input_diagnostics = {}, {}
        for label, original_feed in feeds.items():
            prepared, diagnostics = prepared_inputs(transformer, original_feed, np)
            runtime_hashes[label] = {name: array_hash(value) for name, value in prepared.items()}
            input_diagnostics[label] = diagnostics
        prepared = None
        result.update(model=str(model_path), model_sha256=candidate["model_sha256"], data=candidate["data"],
                      data_sha256=candidate["data_sha256"], data_bytes=candidate["data_bytes"],
                      projection_receipt=str(receipt_path), projection_receipt_sha256=args.projection_receipt_sha256,
                      transformer_sha256=args.split_transformer_sha256, source_model=candidate["source_model"],
                      source_model_sha256=candidate["source_model_sha256"],
                      source_build_receipt=candidate["source_build_receipt"],
                      source_build_receipt_sha256=candidate["source_build_receipt_sha256"],
                      immutable_files=immutable, oracle_binding=oracle_binding,
                      normalized_input_sets={label: {name: array_hash(value) for name, value in feed.items()}
                                             for label, feed in feeds.items()},
                      runtime_input_sets=runtime_hashes, input_split_diagnostics=input_diagnostics,
                      weight_split_diagnostics=candidate["weight_diagnostics"],
                      split_algorithm_diagnostics=candidate["split_diagnostics"],
                      required_hardware_partition_outputs=candidate["metadata"]["required_hardware_partition_outputs"],
                      arithmetic=candidate["arithmetic"], recombination=candidate["recombination"],
                      stable_operands_unchanged=True, independent_numpy_comparisons_are_informational=True)
        if args.provider == "npu":
            result["cpu_gate"] = cpu_diagnostic(args, result, oracles, information, baseline_helpers.bounded_json,
                                                 legacy, helpers, np)
            result["cpu_passed"] = result["cpu_gate"]["cpu_passed"]
        candidate = original = None
        gc.collect()
        result["reference_weights_released_before_session"] = True
        if args.provider == "npu":
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers()
                      if ep.name == "VitisAIExecutionProvider")
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
        # Keep the reviewed MatMul/Add outputs visible to the unchanged
        # hardware coverage gate. Retained default-optimization CPU evidence
        # showed all six residual products absorbed by MatMulAddFusion Gemms.
        # This changes the new diagnostic's session configuration, never its
        # graph, oracle, required output set or original gate helper.
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        if options.graph_optimization_level != ort.GraphOptimizationLevel.ORT_DISABLE_ALL:
            raise RuntimeError("ORT graph optimization disable setting was not retained")
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report.with_suffix(""))
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog = Path(ep.library_path).resolve(strict=True)
            chosen, verified = verified_provider_copy(catalog, args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            result.update(catalog_library=str(catalog), provider_library=str(chosen),
                          provider_library_sha256=digest(chosen), provider_copy_files=verified)
            ort.register_execution_provider_library(ep.name, str(chosen))
            registered = True
            devices = [device for device in ort.get_ep_devices()
                       if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected exactly one VitisAI NPU device")
            cache = report.parent / "vitisai-cache"
            cache.mkdir(exist_ok=False)
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" +
                                        result["provider_library_sha256"] + ":" + ORT_OPTIMIZATION).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key,
                                                       "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        started = time.perf_counter_ns()
        result["session_creations"] += 1
        session = ort.InferenceSession(str(model_path), sess_options=options, enable_fallback=False) if args.provider == "npu" else ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False)
        result["initialization_ms"] = (time.perf_counter_ns() - started) / 1e6
        session.disable_fallback()
        if ([value.name for value in session.get_inputs()] != list(INPUT_SHAPES) or
                [value.name for value in session.get_outputs()] != list(OUTPUT_SHAPES)):
            raise RuntimeError("exact four-input/two-FC-output cut required")
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            context_sha256 = digest(context_path)
            proof = helpers.context_proof(baseline_helpers.bounded_json(context_path, context_sha256, 2 << 20),
                                          result["required_hardware_partition_outputs"], cache_key, chosen)
            proof["scope"] = "all dynamic split partials, compensated Add/Subs and original projection BF16 casts in hw/stx; RMS/seed-add absent"
            result.update(context=str(context_path), context_sha256=context_sha256, context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("every dynamic four-term FC and compensation value requires strict hw/stx placement")
        stable_hashes = {}
        for index in range(WARMUPS + REPS):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            prepared, diagnostics = prepared_inputs(transformer, feeds[label], np)
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in prepared.items()}
            copied = time.perf_counter_ns()
            actual = dict(zip(OUTPUT_SHAPES, session.run(list(OUTPUT_SHAPES), feed), strict=True))
            finished = time.perf_counter_ns()
            current_inputs = {name: array_hash(value) for name, value in feed.items()}
            if current_inputs != runtime_hashes[label] or diagnostics != input_diagnostics[label]:
                raise RuntimeError("per-call generic split inputs or diagnostics changed")
            rows = {}
            for name, value in actual.items():
                native = legacy.comparison(value, oracles[label][name], OUTPUT_SHAPES[name], TOLERANCES[args.provider], np)
                rows[name] = dict(actual_shape=list(value.shape), actual_dtype=str(value.dtype),
                                  output_sha256=array_hash(value),
                                  actual_output=value.tolist() if np.isfinite(value).all() else None,
                                  actual_output_words_u32=value.view(np.uint32).tolist() if value.dtype == np.float32 else None,
                                  native_comparison=native,
                                  independent_numpy_comparisons={mode: legacy.comparison(value, expected, OUTPUT_SHAPES[name],
                                                                                        TOLERANCES["cpu"], np)
                                                                 for mode, expected in information[label][name].items()})
            current_hashes = {name: value["output_sha256"] for name, value in rows.items()}
            stable = label not in stable_hashes or current_hashes == stable_hashes[label]
            stable_hashes.setdefault(label, current_hashes)
            result["calls"].append(dict(call_index=index, warmup=index < WARMUPS, input_set=label,
                                        host_call_ms=(finished - started) / 1e6,
                                        prepare_and_copy_ms=(copied - started) / 1e6,
                                        session_run_ms=(finished - copied) / 1e6, runtime_input_sets=current_inputs,
                                        input_split_diagnostics=diagnostics, outputs=rows,
                                        output_stability_passed=stable,
                                        passed=stable and all(row["native_comparison"]["passed"] for row in rows.values())))
            feed = actual = prepared = None
            guard.check()
        result["timing_observations"] = timing_observations(result["calls"])
        profile = Path(session.end_profiling())
        profile_finished = True
        profile_sha256 = digest(profile)
        proof = helpers.profile_proof(baseline_helpers.bounded_json(profile, profile_sha256, 16 << 20), args.provider)
        result.update(profile=str(profile), profile_sha256=profile_sha256, profile_proof=proof)
        if not proof["passed"]:
            raise RuntimeError("profile does not prove every Node used requested provider")
        frozen = {**sealed, Path(__file__): result["source_sha256"], model_path: result["model_sha256"],
                  Path(result["data"]): result["data_sha256"], receipt_path: args.projection_receipt_sha256,
                  args.fc_fixtures: args.fc_fixtures_sha256, args.native_fc_replay: args.native_fc_replay_sha256,
                  profile: profile_sha256}
        for item in immutable + oracle_files:
            frozen[Path(item["path"])] = item["sha256"]
        if args.provider == "npu":
            frozen[args.cpu_gate] = args.cpu_gate_sha256
            frozen[Path(result["cpu_gate"]["profile"])] = result["cpu_gate"]["profile_sha256"]
            frozen[context_path] = context_sha256
        if any(digest(path) != expected for path, expected in frozen.items()) or helpers.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen source/model/data/native-oracle/fixture/CPU diagnostic changed during replay")
        result["native_FC_screen_passed"] = all(row["native_comparison"]["passed"]
                                                for call in result["calls"] for row in call["outputs"].values())
        result["output_replay_stability_passed"] = all(row["output_stability_passed"] for row in result["calls"])
        result["alternating_input_output_checks"] = {name: stable_hashes["A"][name] != stable_hashes["B"][name]
                                                       for name in OUTPUT_SHAPES}
        result["alternating_inputs_changed"] = all(result["alternating_input_output_checks"].values())
        if not result["output_replay_stability_passed"] or not result["alternating_inputs_changed"]:
            raise RuntimeError("split diagnostic output stability or alternating-input check failed")
        result["diagnostic_completed"] = True
        result["exact_native_FC_word_parity_on_frozen_inputs"] = all(
            row["native_comparison"].get("exact_BF16_word_mismatches") == 0
            for call in result["calls"] for row in call["outputs"].values())
        result["passed"] = result["native_FC_screen_passed"]
        if args.provider == "cpu":
            result["cpu_passed"] = result["passed"]
        if not result["passed"]:
            raise RuntimeError("frozen original GPU FC gate failed; both returned projections retained")
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
            result.update(passed=False, diagnostic_completed=False, cleanup_errors=cleanup_errors)
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
    for name in ("model", "projection-receipt", "fc-fixtures", "native-fc-replay", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("projection-receipt-sha256", "split-transformer-sha256", "fc-fixtures-sha256", "native-fc-replay-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-mode", choices=(REFERENCE_MODE,), required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--cpu-gate", type=Path)
    parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for value in (args.projection_receipt_sha256, args.split_transformer_sha256,
                  args.fc_fixtures_sha256, args.native_fc_replay_sha256):
        sha(value)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None:
            parser.error("NPU diagnostic requires --ep-dir and independently hashed same-source --cpu-gate")
        sha(args.cpu_gate_sha256)
    elif args.ep_dir is not None or args.cpu_gate is not None or args.cpu_gate_sha256 is not None:
        parser.error("CPU must omit provider-copy and CPU diagnostic arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("diagnostic_completed", "passed", "error", "provider",
                                                    "cpu_passed", "integration_admission", "acceleration_claim",
                                                    "session_creations", "native_FC_screen_passed", "timing_observations")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
