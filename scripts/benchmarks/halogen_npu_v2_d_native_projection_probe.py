"""Original GPU Q8 FC oracle for a separate BF16-weight projection candidate.

Root alone runs assets/providers in an exclusive guarded window after checking
the user-owned server. Both FC outputs are screened before seed addition;
seed-add, embedding RMS, complete D/head/acceptance and speed stay unqualified.
Original decoded FP32 matrices receive explicit BF16 RNE before MatMul. Any
native affine-FMA decoding or accumulation mismatch must fail the frozen gate.
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
PROJECTION_HELPER_SHA256 = "8cabd689422ef07e0d48684e7b2fae8a6d1d71571b17605619f796a33f0b11bd"
TRANSFORMER_SHA256 = "8b4d6b9fab064cb556637398796412cb1ccdd555d56193e20fbc2c57285e0c66"
FC_FIXTURES_SHA256 = "ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA256 = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
WEIGHT_SHA256 = {"e": "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d",
                 "h": "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f"}
WEIGHT_LINEAGE = "BF16-rounded-original-decoded-FP32"
REFERENCE_MODE = "original-GPU-Q8-FC-before-seed-add"
WARMUPS, REPS = 4, 8
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
INPUT_SHAPES = {"e": (1, 2560), "h": (1, 10240)}
OUTPUT_SHAPES = {"e_projection": (1, 2560), "h_projection": (4, 2560)}
TRANSFORMER = HERE / "halogen_npu_v2_d_native_projection_graph.py"


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


def array_hash(value):
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def words(path, expected, shape, np):
    sha(expected)
    path = Path(path).resolve(strict=True)
    before = path.stat()
    count = math.prod(shape)
    if not stat.S_ISREG(before.st_mode) or before.st_size != count * 2 or count > 10240:
        raise ValueError("bounded normalized-input/FC-output BF16 extent differs")
    with path.open("rb") as stream:
        raw = stream.read(count * 2 + 1)
    after = path.stat()
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    if len(raw) != count * 2 or hashlib.sha256(raw).hexdigest() != expected or any(getattr(before, name) != getattr(after, name) for name in fields):
        raise ValueError("BF16 input/reference hash or identity differs")
    value = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16).view(np.float32).reshape(shape)
    if not np.isfinite(value).all():
        raise ValueError("BF16 inputs/references must be finite")
    return value, dict(path=str(path), sha256=expected, bytes=len(raw), shape=list(shape), float_array_sha256=array_hash(value))


def references(args, original, bounded, np):
    if args.fc_fixtures_sha256 != FC_FIXTURES_SHA256:
        raise ValueError("sealed root FC fixture manifest required")
    fixture = bounded(args.fc_fixtures, FC_FIXTURES_SHA256, 1 << 20)
    native = bounded(args.native_fc_replay, args.native_fc_replay_sha256, 32768)
    if (fixture.get("schema") != 1 or fixture.get("arithmetic_fitting") is not False or
            fixture.get("tolerance_adjustment") is not False or fixture.get("native_hidden_rms_inputs") is not True or
            fixture.get("native_embedding_rms_inputs") is not False or
            fixture.get("source_identity_before") != fixture.get("source_identity_after") or
            fixture.get("source_identity_before") != fixture.get("source", {}).get("native_identity") or
            fixture["source"]["checkpoint_sha256"] != "71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687" or
            fixture["pins"].get(str(Path(original["assets_receipt"]))) != original["assets_receipt_sha256"]):
        raise ValueError("raw Q8 fixtures and original decoded external matrices have different lineage")
    required = dict(schema="halogen0162.original-q8-fc-kernel-replay.v1", passed=True,
                    engine_sha256=ENGINE_SHA256, codeobject_sha256=CODE_SHA256,
                    codeobject_engine_offset=331776, codeobject_bytes=17704408,
                    K=2560, N=2560, grid=[160, 1, 1], block=[256, 1, 1], shared_bytes=0, default_stream=True,
                    static_lds_bytes=0, wave_size=32, kernarg_bytes=40, kernarg_alignment=8, hidden_arguments=False,
                    user_argument_offsets=[0, 8, 16, 24, 32], user_argument_types=["u8*", "u16*", "u16*", "i64", "i64"],
                    q8_group_size=64, weight_row_bytes=2720, weight_bytes=6963200, raw_weights_copied_unchanged=True,
                    native_arithmetic="affine dequant FMA; decoded-weight BF16 RNE; packed BF16 dot2 FP32 accumulation/reduction; output BF16 RNE",
                    embedding_rms_qualified=False, full_D_parity_qualified=False, seed_add_implemented=False,
                    full_head_qualified=False, acceptance_claim=False, speed_claim=False, tolerance_adjustment=False,
                    arithmetic_fitting=False, logical_calls=4, launch_attempts=4, launches_ok=4, synchronizations_ok=4,
                    copies_ok=14, allocations_ok=4, free_ok=4, module_loads=1, module_unloads=1,
                    cleanup_errors=0, file_close_errors=0, immutable_files_rechecked=True, output_files_written=4,
                    error="", error_code=0)
    kernels = [dict(branch="embedding", symbol="_ZN7halogen12_GLOBAL__N_16k_lq8wILi1ELi16ELi1EEEvPKhPKtPtll",
                    host_identity_rva="0x18d6690", registration_rva="0x184b596", gpu_entry_rva="0x2d1200", descriptor_rva="0x1fa340", M=1),
               dict(branch="hidden", symbol="_ZN7halogen12_GLOBAL__N_16k_lq8wILi4ELi16ELi1EEEvPKhPKtPtll",
                    host_identity_rva="0x18d66f0", registration_rva="0x184b7be", gpu_entry_rva="0x2d7800", descriptor_rva="0x1fa640", M=4)]
    if (any(native.get(key) != value for key, value in required.items()) or native.get("kernels") != kernels or
            native.get("halogen_lq8_wave") not in ("1", "unset-native-default1") or len(native.get("fixtures", [])) != 4):
        raise ValueError("successful fixed original Q8 M1/M4 GPU oracle required")
    sha(native["runtime_sha256"])
    feeds, oracles, information, binding, files = {}, {}, {}, {}, []
    raw_weight_binding = {}
    for branch, full in (("e", "embedding"), ("h", "hidden")):
        weight = fixture["raw_weights"][branch]
        entry = weight["entry"]
        if (weight["bytes"] != 6963200 or weight["sha256"] != WEIGHT_SHA256[branch] or
                native["raw_weight_sha256"][full] != WEIGHT_SHA256[branch] or
                weight.get("decoded_matches_frozen_external_data") is not True or
                (entry["store"], entry["variant"], entry["rank"], entry["dims"], entry["size"]) != (7, 0, 2, [2560, 2560], 6963200) or
                entry["name"] != "mtp.fc_" + full + ".weight"):
            raise ValueError("unchanged raw Q8 matrix geometry/hash differs")
        raw_path = args.fc_fixtures.parent / weight["file"]
        if raw_path.name != branch + "-weight.q8g64" or digest(raw_path) != WEIGHT_SHA256[branch]:
            raise ValueError("sealed original raw Q8 matrix file differs")
        raw_weight_binding[branch] = dict(path=str(raw_path.resolve()), sha256=weight["sha256"], bytes=weight["bytes"], entry=entry,
                                          decoded_matches_frozen_external_data=True)
        files.append(raw_weight_binding[branch])
    for label_index, label in enumerate(("A", "B")):
        feeds[label], oracles[label], information[label], binding[label] = {}, {}, {}, {}
        for branch_index, (branch, full) in enumerate((("e", "embedding"), ("h", "hidden"))):
            row = fixture["inputs"][label][branch]
            shape = INPUT_SHAPES[branch]
            if row["shape"] != list(shape) or row["bytes"] != math.prod(shape) * 2 or row["file"] != label + "-" + branch + "-norm.u16":
                raise ValueError("fixed normalized A/B input shape/name differs")
            value, input_binding = words(args.fc_fixtures.parent / row["file"], row["sha256"], shape, np)
            input_binding["preparation_provenance"] = row["source"]
            feeds[label][branch + "_norm"] = value
            files.append(input_binding)
            native_row = native["fixtures"][label_index * 2 + branch_index]
            output_name = label + "-" + full + "-fc-u16.bin"
            streams = 1 if branch == "e" else 4
            expected_row = dict(id=label + "-" + full, input_sha256=row["sha256"], output_file=output_name,
                                input_bytes=row["bytes"], output_bytes=row["bytes"], streams=streams,
                                vectors_completed=streams, output_copied=True, completed=True, nonfinite_output=0)
            if any(native_row.get(key) != expected for key, expected in expected_row.items()):
                raise ValueError("native FC output does not bind the exact normalized input")
            output_shape = OUTPUT_SHAPES[branch + "_projection"]
            oracle, native_binding = words(args.native_fc_replay.parent / output_name, native_row["output_sha256"], output_shape, np)
            oracles[label][branch + "_projection"] = oracle
            files.append(native_binding)
            information[label][branch + "_projection"], informational_binding = {}, {}
            old = fixture["references"][label][branch]
            for name, item in (("original_decoded_FP32_numpy", old["bf16"]),
                               ("BF16_weight_numpy", old["bf16_weight_reference"]["bf16"])):
                if item["bytes"] != math.prod(output_shape) * 2 or Path(item["file"]).name != item["file"]:
                    raise ValueError("separate NumPy FC reference extent/name differs")
                ref, bound = words(args.fc_fixtures.parent / item["file"], item["sha256"], output_shape, np)
                information[label][branch + "_projection"][name] = ref
                informational_binding[name] = bound
                files.append(bound)
            binding[label][branch + "_projection"] = dict(input=input_binding, native_GPU=native_binding, informational=informational_binding)
    proof = dict(fixture_path=str(args.fc_fixtures.resolve()), fixture_sha256=FC_FIXTURES_SHA256,
                 native_replay_path=str(args.native_fc_replay.resolve()), native_replay_sha256=args.native_fc_replay_sha256,
                 raw_weights=raw_weight_binding, normalized_inputs_and_projection_references=binding,
                 native_hidden_rms_inputs=True, native_embedding_rms_inputs=False,
                 scope="original GPU Q8 FC outputs only on explicit normalized A/B inputs; embedding RMS and seed-add unqualified")
    return feeds, oracles, information, proof, files


def comparison(actual, expected, shape, tolerance, np):
    if actual.dtype != np.float32 or actual.shape != shape or expected.shape != shape or not np.isfinite(actual).all():
        return dict(passed=False, shape_dtype_or_finiteness_error=True)
    bits, wanted = actual.view(np.uint32), expected.view(np.uint32)
    close = np.isclose(actual, expected, **tolerance)
    lattice = int(((bits & 0xffff) != 0).sum())
    return dict(passed=bool(close.all()) and lattice == 0, tolerance=tolerance,
                exact_BF16_word_mismatches=int((bits != wanted).sum()), max_abs_error=float(np.max(np.abs(actual - expected))),
                mismatched_elements=int((~close).sum()), elements=int(actual.size), non_BF16_lattice_elements=lattice)


def cpu_gate(args, result, bounded):
    gate = bounded(args.cpu_gate, args.cpu_gate_sha256, 16 << 20)
    keys = ("source_sha256", "reference_mode", "model_sha256", "data_sha256", "projection_receipt_sha256",
            "transformer_sha256", "weight_lineage", "fc_fixtures_sha256", "native_fc_replay_sha256", "oracle_binding",
            "runtime_input_sets", "dependency_sha256", "probe_dependency_sha256", "required_hardware_partition_outputs")
    required = dict(schema="halogen_v2_count1_D_native_projection_probe.v1", provider="cpu", passed=True,
                    native_FC_screen_passed=True, output_replay_stability_passed=True, alternating_inputs_changed=True,
                    tolerance=TOLERANCES["cpu"], session_creations=1, warmup_count=WARMUPS, repetitions=REPS,
                    native_bit_parity_qualified=False, seed_add_implemented=False, embedding_rms_qualified=False,
                    full_d_claim=False, full_mtp_claim=False, acceptance_claim=False, generic_speed_promotion=False)
    calls = gate.get("calls", [])
    if (any(gate.get(key) != result[key] for key in keys) or any(gate.get(key) != value for key, value in required.items()) or
            gate.get("error") or gate.get("cleanup_errors") or gate.get("reserve_guard_error") or
            gate.get("profile_proof", {}).get("passed") is not True or
            gate["profile_proof"].get("executed_node_providers") != ["CPUExecutionProvider"] or len(calls) != WARMUPS + REPS):
        raise ValueError("same-source successful native-FC CPU gate required before NPU initialization")
    for index, row in enumerate(calls):
        if (row.get("call_index") != index or row.get("input_set") != ("A" if index % 2 == 0 else "B") or
                row.get("warmup") != (index < WARMUPS) or row.get("passed") is not True or
                row.get("output_stability_passed") is not True or set(row.get("outputs", {})) != set(OUTPUT_SHAPES) or
                any(value.get("native_comparison", {}).get("passed") is not True for value in row["outputs"].values())):
            raise ValueError("both FC outputs on every balanced CPU call must pass")
    return dict(path=str(args.cpu_gate.resolve()), sha256=args.cpu_gate_sha256)


def run(args):
    report = args.report.resolve()
    if report.exists() or not report.parent.is_dir():
        raise FileExistsError("exclusive report in existing directory required")
    lock_path = report.with_name(report.name + ".lock")
    lock = lock_path.open("x", encoding="utf-8")
    result = dict(schema="halogen_v2_count1_D_native_projection_probe.v1", source_sha256=digest(__file__),
                  reference_mode=REFERENCE_MODE, provider=args.provider, passed=False, wire_mode="D", count=1,
                  weight_lineage=WEIGHT_LINEAGE, tolerance=TOLERANCES[args.provider], tolerance_frozen_before_session=True,
                  calls=[], session_creations=0, warmup_count=WARMUPS, repetitions=REPS, native_FC_screen_passed=False,
                  output_replay_stability_passed=False, alternating_inputs_changed=False,
                  native_bit_parity_qualified=False, seed_add_implemented=False, embedding_rms_qualified=False,
                  full_d_claim=False, full_mtp_claim=False, acceptance_claim=False, generic_speed_promotion=False,
                  normalization_in_npu_segment=False, native_q8_affine_fma_decoder_proved=False,
                  outer_owned_job_guard_required=True, root_exclusive_serving_state_check_required=True,
                  admission_gib=22, reserve_gib=18, fc_fixtures_sha256=args.fc_fixtures_sha256,
                  native_fc_replay_sha256=args.native_fc_replay_sha256,
                  scope="separate BF16-rounded decoded-weight FC candidate against original GPU Q8 FC outputs before seed-add",
                  timing_scope="candidate two-output FC host calls/copies; normalization/seed-add/native head/transfer integration excluded")
    session = options = runtime = dll_directory = devices = guard = ort = helpers = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        if any(os.environ.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("set BLAS/OpenMP thread variables to1 before Python starts")
        sealed = {HERE / "halogen_npu_v2_d_prepare_probe.py": LEGACY_SHA256,
                  HERE / "halogen_npu_v2_d_graph_probe.py": BASELINE_HELPER_SHA256,
                  HERE / "halogen_npu_v2_d_prepare.py": BUILDER_SHA256,
                  HERE / "halogen_npu_v2_d_projection_graph.py": PROJECTION_HELPER_SHA256,
                  TRANSFORMER: TRANSFORMER_SHA256}
        if any(digest(path) != expected for path, expected in sealed.items()):
            raise ValueError("sealed original/projection helper source differs")
        sys.path.insert(0, str(HERE))
        import halogen_npu_v2_d_prepare_probe as helpers
        import halogen_npu_v2_d_graph_probe as baseline_helpers
        if helpers.TOLERANCES != TOLERANCES or baseline_helpers.TOLERANCES != TOLERANCES:
            raise ValueError("original frozen tolerances differ")
        guard = helpers.ReserveGuard()
        guard.start()
        result["dependency_sha256"] = helpers.dependencies()
        transformer_hash = TRANSFORMER_SHA256
        result["probe_dependency_sha256"] = {path.name: expected for path, expected in sealed.items()}
        result["probe_dependency_sha256"][TRANSFORMER.name] = transformer_hash
        import numpy as np
        import halogen_npu_v2_d_native_projection_graph as transformer
        model_path, receipt_path = args.model.resolve(strict=True), args.projection_receipt.resolve(strict=True)
        candidate, original = transformer.verify_native_projection(model_path, receipt_path, args.projection_receipt_sha256)
        if candidate["transformer_sha256"] != transformer_hash or candidate["weight_lineage"] != WEIGHT_LINEAGE or candidate["metadata"]["output_names"] != list(OUTPUT_SHAPES):
            raise ValueError("reviewed native-oriented weight/output contract differs")
        feeds, oracles, information, oracle_binding, oracle_files = references(args, original, baseline_helpers.bounded_json, np)
        result.update(model=str(model_path), model_sha256=candidate["model_sha256"], data=candidate["data"],
                      data_sha256=candidate["data_sha256"], data_bytes=candidate["data_bytes"],
                      projection_receipt=str(receipt_path), projection_receipt_sha256=args.projection_receipt_sha256,
                      transformer_sha256=transformer_hash, source_model=candidate["source_model"],
                      source_model_sha256=candidate["source_model_sha256"], source_build_receipt=candidate["source_build_receipt"],
                      source_build_receipt_sha256=candidate["source_build_receipt_sha256"], oracle_binding=oracle_binding,
                      runtime_input_sets={label: {name: array_hash(value) for name, value in feed.items()} for label, feed in feeds.items()},
                      required_hardware_partition_outputs=candidate["metadata"]["required_hardware_partition_outputs"],
                      arithmetic=candidate["arithmetic"], independent_numpy_comparisons_are_informational=True)
        if args.provider == "npu":
            result["cpu_gate"] = cpu_gate(args, result, baseline_helpers.bounded_json)
        candidate = original = None
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
        if [value.name for value in session.get_inputs()] != ["e_norm", "h_norm"] or [value.name for value in session.get_outputs()] != list(OUTPUT_SHAPES):
            raise RuntimeError("exact normalized-input/two-FC-output cut required")
        result.update(ort_version=ort.__version__, numpy_version=np.__version__, session_providers=session.get_providers())
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            if not context_path.is_file() or not 0 < context_path.stat().st_size <= 2 << 20:
                raise RuntimeError("fresh bounded compiler context unavailable")
            proof = helpers.context_proof(json.loads(context_path.read_text(encoding="utf-8")), result["required_hardware_partition_outputs"], cache_key, chosen)
            proof["scope"] = "every dynamic FC candidate value including projection BF16 casts in hw/stx partitions; RMS and seed-add absent; internal kernel offload not independently observed"
            result.update(context=str(context_path), context_sha256=digest(context_path), context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("every dynamic two-output FC value requires strict hw/stx placement")
        import time
        stable_hashes = {}
        for index in range(WARMUPS + REPS):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied = time.perf_counter_ns()
            actual = dict(zip(OUTPUT_SHAPES, session.run(list(OUTPUT_SHAPES), feed), strict=True))
            finished = time.perf_counter_ns()
            rows = {}
            for name, value in actual.items():
                native_comparison = comparison(value, oracles[label][name], OUTPUT_SHAPES[name], TOLERANCES[args.provider], np)
                rows[name] = dict(actual_shape=list(value.shape), actual_dtype=str(value.dtype), output_sha256=array_hash(value),
                                  actual_output=value.tolist() if np.isfinite(value).all() else None,
                                  actual_output_words_u32=value.view(np.uint32).tolist() if value.dtype == np.float32 else None,
                                  native_comparison=native_comparison,
                                  independent_numpy_comparisons={mode: comparison(value, expected, OUTPUT_SHAPES[name], TOLERANCES["cpu"], np) for mode, expected in information[label][name].items()})
            current_hashes = {name: value["output_sha256"] for name, value in rows.items()}
            stable = label not in stable_hashes or current_hashes == stable_hashes[label]
            stable_hashes.setdefault(label, current_hashes)
            result["calls"].append(dict(call_index=index, warmup=index < WARMUPS, input_set=label,
                                        host_call_ms=(finished - started) / 1e6, prepare_and_copy_ms=(copied - started) / 1e6,
                                        session_run_ms=(finished - copied) / 1e6, outputs=rows, output_stability_passed=stable,
                                        passed=stable and all(row["native_comparison"]["passed"] for row in rows.values())))
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
                  args.fc_fixtures: FC_FIXTURES_SHA256, args.native_fc_replay: args.native_fc_replay_sha256,
                  Path(result["source_model"]): result["source_model_sha256"], Path(result["source_build_receipt"]): result["source_build_receipt_sha256"]}
        for row in oracle_files:
            frozen[Path(row["path"])] = row["sha256"]
        if args.provider == "npu":
            frozen[args.cpu_gate] = args.cpu_gate_sha256
        if any(digest(path) != expected for path, expected in frozen.items()) or helpers.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("frozen source/model/data/native-oracle/fixture/gate changed during replay")
        result["native_FC_screen_passed"] = all(value["native_comparison"]["passed"] for row in result["calls"] for value in row["outputs"].values())
        result["output_replay_stability_passed"] = all(row["output_stability_passed"] for row in result["calls"])
        result["alternating_input_output_checks"] = {name: stable_hashes["A"][name] != stable_hashes["B"][name] for name in OUTPUT_SHAPES}
        result["alternating_inputs_changed"] = all(result["alternating_input_output_checks"].values())
        if not all(result[key] for key in ("native_FC_screen_passed", "output_replay_stability_passed", "alternating_inputs_changed")):
            raise RuntimeError("frozen original GPU FC gate failed; both returned projections retained")
        times = sorted(row["host_call_ms"] for row in result["calls"] if not row["warmup"])
        result.update(passed=True, candidate_FC_host_mean_ms=sum(times) / len(times), candidate_FC_host_min_ms=min(times),
                      candidate_FC_host_p95_ms=times[math.ceil(.95 * len(times)) - 1],
                      exact_native_FC_word_parity_on_frozen_inputs=all(value["native_comparison"]["exact_BF16_word_mismatches"] == 0 for row in result["calls"] for value in row["outputs"].values()))
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
            result.update(passed=False, native_FC_screen_passed=False, cleanup_errors=cleanup_errors)
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
    for name in ("projection-receipt-sha256", "fc-fixtures-sha256", "native-fc-replay-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reference-mode", choices=(REFERENCE_MODE,), required=True)
    parser.add_argument("--wire-mode", choices=("D",), required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--cpu-gate", type=Path)
    parser.add_argument("--cpu-gate-sha256")
    args = parser.parse_args(argv)
    for value in (args.projection_receipt_sha256, args.fc_fixtures_sha256, args.native_fc_replay_sha256):
        sha(value)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_gate is None or args.cpu_gate_sha256 is None:
            parser.error("NPU requires --ep-dir and independently hashed same-source --cpu-gate")
        sha(args.cpu_gate_sha256)
    elif args.ep_dir is not None or args.cpu_gate is not None or args.cpu_gate_sha256 is not None:
        parser.error("CPU must omit provider-copy and CPU-gate arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "error", "provider", "session_creations", "native_FC_screen_passed", "native_bit_parity_qualified")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
