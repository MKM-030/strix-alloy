"""Root-only count1 embedding component CPU/NPU diagnostic for an early producer.

Same native GPU oracle, stable split and BF16 boundary; CPU .002/.0002 must
pass before NPU .03/.003. No hidden inputs/compute, late-cut batch, producer,
publication, live swap or speed admission. Root coordinates an idle existing
server and owned deadline/reserve guard. Concurrent GPU inference is forbidden;
safe supported fabric control is a separate prerequisite before any overlap.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import sys
import time

import halogen_npu_early_embedding_graph as graph


HERE = Path(__file__).resolve().parent
SCHEMA = "halogen_v2_count1_early_embedding_projection_probe.v1"
REFERENCE_MODE = "original-GPU-Q8-FC-before-seed-add"
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
WARMUPS, REPS, FEED_BYTES = 4, 8, 20480
FIXTURE_SHA256 = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
NATIVE_REPLAY_SHA256 = "2fb0f6a198581156e430301064acef3e41d10a99e0a0cd06ab5ae9a16b8ed5fb"
SEALED_HELPERS = {
    "halogen_npu_v2_d_native_projection_stable_split_graph.py": graph.STABLE_HELPER_SHA256,
    "halogen_npu_v2_d_native_projection_stable_split_probe.py": "2ba71370edddd8d772111a16a985a90e02396066e6d88d04686acccbfa6b2558",
    "halogen_npu_v2_d_native_projection_probe.py": "7d1f51fd254389906c66b3ce44117fbe889b38b73861d192e4965893f6b0d9b0",
    "halogen_npu_v2_d_prepare_probe.py": "f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3",
    "halogen_npu_v2_d_graph_probe.py": "43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f",
}
IDENTITY_KEYS = ("source_sha256", "transformer_sha256", "model_sha256", "data_sha256", "data_bytes",
                 "projection_receipt_sha256", "weight_lineage", "dependency_sha256", "probe_dependency_sha256",
                 "fc_fixtures_sha256", "native_fc_replay_sha256", "oracle_binding", "normalized_input_sets",
                 "runtime_input_sets", "input_split_diagnostics", "weight_split_diagnostics",
                 "required_hardware_partition_outputs", "immutable_files", "arithmetic")
CPU_REQUIRED = dict(schema=SCHEMA, provider="cpu", component_mode=graph.COMPONENT_MODE, count=1,
                    passed=True, cpu_passed=True, diagnostic_completed=True,
                    native_embedding_FC_screen_passed=True, output_replay_stability_passed=True,
                    alternating_inputs_changed=True, tolerance=TOLERANCES["cpu"], tolerance_frozen_before_session=True,
                    ort_graph_optimization_level="ORT_DISABLE_ALL", warmup_count=WARMUPS, repetitions=REPS,
                    session_creations=1, reference_mode=REFERENCE_MODE, **graph.CLAIMS)


def cpu_receipt_header(gate, current):
    if (any(gate.get(k) != v for k, v in CPU_REQUIRED.items()) or
            any(gate.get(k) != current[k] for k in IDENTITY_KEYS) or gate.get("error") is not None or
            gate.get("cleanup_errors") or gate.get("reserve_guard_error")):
        raise ValueError("same-source successful strict embedding-only CPU gate required before NPU")


def helpers():
    for name, expected in SEALED_HELPERS.items():
        if graph.digest(HERE / name) != expected:
            raise ValueError("sealed helper differs: " + name)
    import halogen_npu_v2_d_native_projection_stable_split_probe as shared
    import halogen_npu_v2_d_native_projection_probe as native
    import halogen_npu_v2_d_prepare_probe as runtime
    import halogen_npu_v2_d_graph_probe as bounded
    for module in (shared, native, runtime, bounded):
        if module.TOLERANCES != TOLERANCES or Path(module.__file__).resolve().parent != HERE:
            raise ValueError("sealed original tolerances/import origin differ")
    return shared, native, runtime, bounded.bounded_json


def references(args, original, bounded, native, np):
    """Read embedding rows only; paired receipt metadata supplies sealed lineage."""
    if args.fc_fixtures_sha256 != FIXTURE_SHA256 or args.native_fc_replay_sha256 != NATIVE_REPLAY_SHA256:
        raise ValueError("unchanged independently sealed original fixtures/oracle required")
    fixture = bounded(args.fc_fixtures, FIXTURE_SHA256, 1 << 20)
    replay = bounded(args.native_fc_replay, NATIVE_REPLAY_SHA256, 32768)
    weight = fixture["raw_weights"]["e"]
    if (fixture.get("schema") != 1 or fixture.get("arithmetic_fitting") is not False or
            fixture.get("tolerance_adjustment") is not False or
            fixture["pins"].get(str(Path(original["assets_receipt"]))) != original["assets_receipt_sha256"] or
            fixture["source_identity_before"] != fixture["source_identity_after"] or
            fixture["source_identity_before"] != fixture["source"]["native_identity"] or
            replay.get("passed") is not True or replay["engine_sha256"] != native.ENGINE_SHA256 or
            replay["codeobject_sha256"] != native.CODE_SHA256 or
            weight["sha256"] != native.WEIGHT_SHA256["e"] or
            replay["raw_weight_sha256"]["embedding"] != weight["sha256"] or
            weight["decoded_matches_frozen_external_data"] is not True):
        raise ValueError("sealed native embedding FC and stable weight lineage differ")
    feeds, oracles, bindings, files = {}, {}, {}, []
    for index, label in enumerate(("A", "B")):
        row = fixture["inputs"][label]["e"]
        observed = replay["fixtures"][index * 2]
        output = label + "-embedding-fc-u16.bin"
        required = dict(id=label + "-embedding", input_sha256=row["sha256"], input_bytes=5120,
                        output_bytes=5120, output_file=output, streams=1, vectors_completed=1,
                        completed=True, output_copied=True, nonfinite_output=0)
        if (row["shape"] != [1, 2560] or row["bytes"] != 5120 or row["file"] != label + "-e-norm.u16" or
                any(observed.get(k) != v for k, v in required.items())):
            raise ValueError("native embedding oracle must bind exact normalized row")
        feed, input_binding = native.words(args.fc_fixtures.parent / row["file"], row["sha256"], (1, 2560), np)
        oracle, output_binding = native.words(args.native_fc_replay.parent / output,
                                             observed["output_sha256"], (1, 2560), np)
        input_binding["preparation_provenance"] = row["source"]
        feeds[label], oracles[label] = feed, oracle
        bindings[label] = dict(input=input_binding, native_GPU=output_binding)
        files.extend((input_binding, output_binding))
    proof = dict(fixture_sha256=FIXTURE_SHA256, native_replay_sha256=NATIVE_REPLAY_SHA256,
                 raw_embedding_weight_sha256=weight["sha256"], normalized_embedding_and_native_FC=bindings,
                 scope="embedding FC only on frozen A/B normalized rows; no hidden payload read or producer admission")
    return feeds, oracles, proof, files


def prepared(value, np):
    feed, facts = graph.prepare_input(value, np)
    stable = facts["e"]["stable_high"]
    if (set(feed) != set(graph.INPUT_SHAPES) or sum(v.nbytes for v in feed.values()) != FEED_BYTES or
            any(v.dtype != np.float32 or v.shape != graph.INPUT_SHAPES[k] or not np.isfinite(v).all() for k, v in feed.items()) or
            facts["e"]["high_idempotence_verified"] is not True or facts["e"]["high_requantization_bit_mismatches"] != 0 or
            stable["max_iterations"] != 8 or stable["converged"] is not True):
        raise ValueError("finite count1 bit-exact stable-high input split required")
    return feed, facts


def cpu_gate(args, current, oracles, bounded, shared, native, runtime, np):
    gate = bounded(args.cpu_gate, args.cpu_gate_sha256, 4 << 20)
    cpu_receipt_header(gate, current)
    profile = bounded(Path(gate["profile"]), gate["profile_sha256"], 16 << 20)
    proof = runtime.profile_proof(profile, "cpu")
    calls, stable = gate.get("calls", []), {}
    if proof != gate.get("profile_proof") or not proof["passed"] or proof["node_events"] != 9 * (WARMUPS + REPS) or len(calls) != WARMUPS + REPS:
        raise ValueError("completed embedding-only CPU profile/calls required")
    for index, call in enumerate(calls):
        label = "A" if index % 2 == 0 else "B"
        if (call.get("call_index") != index or call.get("input_set") != label or call.get("warmup") != (index < WARMUPS) or
                call.get("passed") is not True or call.get("output_stability_passed") is not True or
                call.get("runtime_input_sets") != current["runtime_input_sets"][label] or
                call.get("input_split_diagnostics") != current["input_split_diagnostics"][label] or
                set(call.get("outputs", {})) != {"e_projection"}):
            raise ValueError("every balanced same-input embedding CPU call must pass")
        row = call["outputs"]["e_projection"]
        actual = shared.retained_output(row, (1, 2560), np)
        metric = native.comparison(actual, oracles[label], (1, 2560), TOLERANCES["cpu"], np)
        if not metric["passed"] or metric != row["native_comparison"] or row["output_sha256"] != stable.setdefault(label, row["output_sha256"]):
            raise ValueError("retained embedding CPU numerical/repeat proof differs")
    changed = {"e_projection": stable["A"] != stable["B"]}
    if (not changed["e_projection"] or gate["alternating_input_output_checks"] != changed or
            gate["timing_observations"] != shared.timing_observations(calls)):
        raise ValueError("CPU changed-input/timing evidence differs")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256,
                profile=gate["profile"], profile_sha256=gate["profile_sha256"], cpu_passed=True)


def run(args):
    report = args.report.resolve()
    if report.exists() or not report.parent.is_dir():
        raise FileExistsError("exclusive report in existing directory required")
    lock_path = Path(str(report) + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema=SCHEMA, provider=args.provider, component_mode=graph.COMPONENT_MODE, count=1,
                  source_sha256=graph.digest(__file__), passed=False, cpu_passed=None, diagnostic_completed=False, error=None,
                  reference_mode=REFERENCE_MODE, tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True,
                  ort_graph_optimization_level="ORT_DISABLE_ALL", calls=[], warmup_count=WARMUPS, repetitions=REPS,
                  session_creations=0, feed_bytes_per_call=FEED_BYTES, native_embedding_FC_screen_passed=False,
                  output_replay_stability_passed=False, alternating_inputs_changed=False, timing_qualified=False,
                  native_bit_parity_qualified=False, embedding_rms_executed_by_this_probe=False,
                  producer_lineage_qualified_by_this_probe=False, shared_data_contains_unused_hidden_weights=True,
                  outer_owned_job_guard_required=True, admission_gib=22, reserve_gib=18,
                  timing_scope="count1 stable input preparation/diagnostic hashes + fresh copies + session.run; "
                               "excludes producer/gather/RMS, compilation, post-validation, live transport and GPU scheduling",
                  **graph.CLAIMS)
    session = options = runtime_handle = dll_directory = guard = ort = devices = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(k) != "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        if graph.digest(graph.__file__) != graph.sha(args.transformer_sha256):
            raise ValueError("embedding transformer source differs")
        shared, native, runtime, bounded = helpers()
        guard = runtime.ReserveGuard(); guard.start()
        result.update(dependency_sha256=runtime.dependencies(),
                      probe_dependency_sha256={**SEALED_HELPERS, Path(graph.__file__).name: args.transformer_sha256})
        import numpy as np
        candidate, original = graph.verify_graph(args.model, args.projection_receipt, args.projection_receipt_sha256)
        feeds, oracles, binding, oracle_files = references(args, original, bounded, native, np)
        feed_hashes, diagnostics = {}, {}
        for label, value in feeds.items():
            feed, facts = prepared(value, np)
            feed_hashes[label], diagnostics[label] = {k: shared.array_hash(v) for k, v in feed.items()}, facts
        feed = None
        result.update({k: candidate[k] for k in ("model", "model_sha256", "data", "data_sha256", "data_bytes",
                      "transformer_sha256", "weight_lineage", "immutable_files", "arithmetic")})
        result.update(projection_receipt_sha256=args.projection_receipt_sha256,
                      fc_fixtures_sha256=args.fc_fixtures_sha256, native_fc_replay_sha256=args.native_fc_replay_sha256,
                      oracle_binding=binding, normalized_input_sets={k: shared.array_hash(v) for k, v in feeds.items()},
                      runtime_input_sets=feed_hashes, input_split_diagnostics=diagnostics,
                      weight_split_diagnostics=candidate["weight_diagnostics"],
                      required_hardware_partition_outputs=candidate["metadata"]["required_hardware_partition_outputs"])
        if args.provider == "npu":
            result["cpu_gate"] = cpu_gate(args, result, oracles, bounded, shared, native, runtime, np)
            result["cpu_passed"] = True
        original = candidate = None
        gc.collect()
        if args.provider == "npu":
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime_handle = initialize()
            ep = next(e for e in ExecutionProviderCatalog.get_default().find_all_providers() if e.name == "VitisAIExecutionProvider")
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError("VitisAI absent; acquisition disabled")
            ready = ep.ensure_ready_async().get(); guard.check()
            if int(ready.status) != 1:
                raise RuntimeError("VitisAI readiness failed: " + ready.diagnostic_text)
        import onnxruntime as ort
        if ort.__version__ != "1.25.2" or np.__version__ != "2.5.3":
            raise ValueError("frozen ORT/NumPy versions differ")
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report.with_suffix(""))
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            chosen, verified = verified_provider_copy(Path(ep.library_path).resolve(strict=True), args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            ort.register_execution_provider_library(ep.name, str(chosen)); registered = True
            devices = [d for d in ort.get_ep_devices() if d.ep_name == ep.name and str(d.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("exactly one VitisAI NPU device required")
            cache = report.parent / "vitisai-cache"; cache.mkdir(exist_ok=False)
            import hashlib
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" +
                                        graph.digest(chosen) + ":ORT_DISABLE_ALL").encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(catalog_library=str(Path(ep.library_path).resolve(strict=True)),
                          provider_library=str(chosen), provider_library_sha256=graph.digest(chosen),
                          provider_copy_files=verified, cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        started = time.perf_counter_ns(); result["session_creations"] += 1
        session = ort.InferenceSession(result["model"], sess_options=options, enable_fallback=False,
                                       **({} if args.provider == "npu" else {"providers": ["CPUExecutionProvider"]}))
        result["initialization_ms"] = (time.perf_counter_ns() - started) / 1e6
        session.disable_fallback()
        if [v.name for v in session.get_inputs()] != list(graph.INPUT_SHAPES) or [v.name for v in session.get_outputs()] != ["e_projection"]:
            raise RuntimeError("exact embedding-only session ABI required")
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        if args.provider == "npu":
            context = cache / cache_key / "context.json"; context_sha = graph.digest(context)
            proof = runtime.context_proof(bounded(context, context_sha, 2 << 20), result["required_hardware_partition_outputs"], cache_key, chosen)
            proof["scope"] = "all9 count1 embedding partials/sums and BF16/FLOAT casts; hidden/RMS/seed-add absent"
            result.update(context=str(context), context_sha256=context_sha, context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("all9 embedding values require exclusive hardware/STX placement")
        stable = {}
        for index in range(WARMUPS + REPS):
            guard.check(); label = "A" if index % 2 == 0 else "B"; started = time.perf_counter_ns()
            prepared_feed, facts = prepared(feeds[label], np)
            feed = {k: np.array(v, dtype=np.float32, order="C", copy=True) for k, v in prepared_feed.items()}
            copied = time.perf_counter_ns(); actual = session.run(["e_projection"], feed)[0]; finished = time.perf_counter_ns()
            hashes = {k: shared.array_hash(v) for k, v in feed.items()}
            if hashes != feed_hashes[label] or facts != diagnostics[label]:
                raise RuntimeError("per-call embedding split identity changed")
            metric = native.comparison(actual, oracles[label], (1, 2560), TOLERANCES[args.provider], np)
            output_hash = shared.array_hash(actual); repeated = output_hash == stable.setdefault(label, output_hash)
            row = dict(actual_shape=list(actual.shape), actual_dtype=str(actual.dtype), output_sha256=output_hash,
                       actual_output=actual.tolist() if np.isfinite(actual).all() else None,
                       actual_output_words_u32=actual.view(np.uint32).tolist() if actual.dtype == np.float32 else None,
                       native_comparison=metric)
            result["calls"].append(dict(call_index=index, input_set=label, warmup=index < WARMUPS,
                  host_call_ms=(finished-started)/1e6, prepare_and_copy_ms=(copied-started)/1e6,
                  session_run_ms=(finished-copied)/1e6, runtime_input_sets=hashes, input_split_diagnostics=facts,
                  outputs={"e_projection": row}, output_stability_passed=repeated, passed=repeated and metric["passed"]))
            actual = feed = prepared_feed = None
        profile = Path(session.end_profiling()); profile_finished = True; profile_sha = graph.digest(profile)
        proof = runtime.profile_proof(bounded(profile, profile_sha, 16 << 20), args.provider)
        result.update(profile=str(profile), profile_sha256=profile_sha, profile_proof=proof,
                      timing_observations=shared.timing_observations(result["calls"]))
        if not proof["passed"]:
            raise RuntimeError("profile must prove exclusive requested provider execution")
        frozen = {HERE/name: pin for name, pin in SEALED_HELPERS.items()}
        frozen.update({Path(graph.__file__): args.transformer_sha256, Path(__file__): result["source_sha256"],
                       args.projection_receipt: args.projection_receipt_sha256, args.fc_fixtures: FIXTURE_SHA256,
                       args.native_fc_replay: NATIVE_REPLAY_SHA256, profile: profile_sha})
        frozen.update({Path(r["path"]): r["sha256"] for r in result["immutable_files"] + oracle_files})
        if args.provider == "npu":
            frozen.update({args.cpu_gate: args.cpu_gate_sha256, Path(result["cpu_gate"]["profile"]): result["cpu_gate"]["profile_sha256"], context: context_sha})
        if any(graph.digest(p) != pin for p, pin in frozen.items()) or runtime.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen embedding source/model/data/oracle/CPU evidence changed")
        result["native_embedding_FC_screen_passed"] = all(c["outputs"]["e_projection"]["native_comparison"]["passed"] for c in result["calls"])
        result["output_replay_stability_passed"] = all(c["output_stability_passed"] for c in result["calls"])
        result["alternating_input_output_checks"] = {"e_projection": stable["A"] != stable["B"]}
        result["alternating_inputs_changed"] = stable["A"] != stable["B"]
        result["diagnostic_completed"] = True
        result["exact_native_embedding_FC_word_parity_on_frozen_inputs"] = all(
            c["outputs"]["e_projection"]["native_comparison"].get("exact_BF16_word_mismatches") == 0 for c in result["calls"])
        result["passed"] = all(result[k] for k in ("native_embedding_FC_screen_passed", "output_replay_stability_passed", "alternating_inputs_changed"))
        if args.provider == "cpu": result["cpu_passed"] = result["passed"]
        if not result["passed"]: raise RuntimeError("unchanged original native embedding FC gate failed; outputs retained")
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                partial = Path(session.end_profiling())
                result.update(partial_profile=str(partial), partial_profile_sha256=graph.digest(partial))
            except Exception as exc: cleanup_errors.append("partial profile: " + str(exc))
        session = options = devices = None; gc.collect()
        for name, active, action in (("provider_unregistered", registered, lambda: ort.unregister_execution_provider_library("VitisAIExecutionProvider")),
                                    ("dll_directory_closed", dll_directory is not None, lambda: dll_directory.close()),
                                    ("bootstrap_shutdown", runtime_handle is not None, lambda: runtime_handle())):
            try:
                if active:
                    action(); result[name] = True
            except Exception as exc: cleanup_errors.append(name + ": " + str(exc))
        if guard is not None:
            guard.stop(); result.update(reserve_samples=guard.samples, reserve_guard_error=guard.error)
            if guard.error: cleanup_errors.append("reserve guard: " + guard.error)
        if cleanup_errors: result.update(passed=False, diagnostic_completed=False, cleanup_errors=cleanup_errors)
        try:
            with report.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2, allow_nan=False); stream.flush(); os.fsync(stream.fileno())
        finally: lock.close(); lock_path.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "projection-receipt", "fc-fixtures", "native-fc-replay", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("projection-receipt-sha256", "transformer-sha256", "fc-fixtures-sha256", "native-fc-replay-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path); parser.add_argument("--cpu-gate", type=Path); parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for value in (args.projection_receipt_sha256, args.transformer_sha256, args.fc_fixtures_sha256, args.native_fc_replay_sha256): graph.sha(value)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None: parser.error("NPU requires verified provider directory and independently sealed successful CPU gate")
        graph.sha(args.cpu_gate_sha256)
    elif any(v is not None for v in (args.ep_dir, args.cpu_gate, args.cpu_gate_sha256)): parser.error("CPU must omit NPU/CPU-gate arguments")
    result = run(args)
    print(json.dumps({k: result.get(k) for k in ("passed", "cpu_passed", "diagnostic_completed", "error", "provider", "timing_observations")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
