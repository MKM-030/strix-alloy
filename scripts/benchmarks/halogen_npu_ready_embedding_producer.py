"""Root-owned offline count1 projection rows for the ready-embedding codec.

CPU writes a receipt only. NPU requires that same-row successful CPU receipt
and exports finite little-endian BF16 rows after provider cleanup. The frozen
GPU capture supplies the original FC oracle and normalized-input provenance.
No graph rewrite, batch, engine lifecycle, upload, overlap or speed admission.
Run only inside root's bounded owned-job/deadline and idle-engine guard.
"""
import argparse
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
import struct
import sys


HERE = Path(__file__).resolve().parent
SCHEMA = "halogen0162.ready-embedding-producer.v1"
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
WIDTH, ROW_BYTES, MAX_ROWS, REPEATS = 2560, 5120, 64, 2
MODEL_SHA = "562a5de0f53aa8d271fca4ba239e8ded2def734f760680ef546dd94c7fcfeb07"
MODEL_RECEIPT_SHA = "5ce966af3b6fcb92b54dcd75d99650411e09dedc5310af040221ac399f930a77"
DATA_SHA = "61ccb018d6855f1d189c39a22554bfaf82f1a31e95a7cd8b745042f7798b906f"
PROMPT_TOKENS_SHA = "dc1b73cc84046ca0fe0ed09520540eed9c06e2682fbd23eeff7077209f7ee31b"
SELECTED_TOKENS = (13, 279, 321, 264, 271, 364, 539, 314, 82, 17942, 14367, 18213,
    15530, 852, 29123, 888, 2902, 30592, 1396, 2235, 948, 11388, 16657, 18197,
    70676, 1332, 5459, 3162, 4009, 66814, 3609, 19719, 34667, 883, 1990, 3055,
    7112, 9506, 11012, 13759, 43287, 998, 2748, 4370, 43299, 22700, 2957,
    28552, 31958, 5904, 17061, 24562, 33002, 62857, 4477, 6092, 27786, 1345,
    1754, 30864, 32469, 1698, 3807, 82051)
HELPERS = {
    "halogen_npu_early_embedding_graph.py": "8b6d30944dce5028eab068646f43031e809b376f32e669d69ba0461d804f0338",
    "halogen_npu_early_embedding_probe.py": "73438c84a0ad931813d53c7051f333f939adb463a1238666e024505920d12e69",
    "halogen_mtp_early_token_producer.py": "56ebe190cdbdc47a50b6c6930172cb6cf274f04995276100c4c8537325ee1da5",
    "halogen_mtp_early_token_native_rms_producer.py": "1c15e38755af53f107c40863f17251197118c404e6ead6aa470d911b06e5caa6",
    "halogen0162_embedding_rms_cpu_tree_portable.py": "4ed6f25305c0ef714a85af2977a094b936b433d0912b781dbc46fab7e2e8f02a",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def capture(path, expected, limit, exact=None):
    """Read one pinned regular file and reject replacement during the read."""
    path = Path(path).resolve(strict=True)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
        raise ValueError("bounded regular input required: " + str(path))
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    end = path.lstat()
    keys = ("st_size", "st_dev", "st_ino", "st_mtime_ns")
    identity = lambda item: tuple(getattr(item, key) for key in keys)
    if (not identity(before) == identity(opened) == identity(after) == identity(end) or
            before.st_ctime_ns != end.st_ctime_ns or opened.st_ctime_ns != after.st_ctime_ns or
            len(raw) != before.st_size or exact is not None and len(raw) != exact or sha(raw) != expected):
        raise ValueError("input extent/hash/identity changed: " + str(path))
    return raw


def json_input(path, expected, limit=2 << 20):
    return json.loads(capture(path, expected, limit))


def sealed_modules(args):
    helper_dir = Path(getattr(args, "sealed_helper_dir", HERE)).resolve(strict=True)
    for name, expected in HELPERS.items():
        capture(helper_dir / name, expected, 2 << 20)
    capture(HERE / "halogen0162_ready_embedding_rows.py", args.codec_sha256, 2 << 20)
    sys.path.insert(0, str(helper_dir))
    graph = importlib.import_module("halogen_npu_early_embedding_graph")
    probe = importlib.import_module("halogen_npu_early_embedding_probe")
    original = importlib.import_module("halogen_mtp_early_token_producer")
    codec = importlib.import_module("halogen0162_ready_embedding_rows")
    for module in (graph, probe, original):
        if Path(module.__file__).resolve().parent != helper_dir:
            raise ValueError("helper import origin differs")
    if Path(codec.__file__).resolve().parent != HERE:
        raise ValueError("codec import origin differs")
    if args.transformer_sha256 != HELPERS["halogen_npu_early_embedding_graph.py"] or probe.TOLERANCES != TOLERANCES:
        raise ValueError("sealed graph source/original tolerance differs")
    shared, native, runtime, bounded = probe.helpers()
    return graph, original, codec, shared, native, runtime, bounded


def widen(raw, np):
    return (np.frombuffer(raw, dtype="<u2").astype("<u4") << 16).view("<f4").reshape(1, WIDTH)


def bf16_bytes(actual, np):
    if actual.dtype != np.float32 or actual.shape != (1, WIDTH) or not np.isfinite(actual).all():
        raise ValueError("finite count1 FLOAT projection required")
    words = np.ascontiguousarray(actual).view(np.uint32)
    if np.any(words & 0xffff):
        raise ValueError("projection must already be exactly BF16; further rounding forbidden")
    return (words >> 16).astype("<u2").tobytes(order="C")


def row_inputs(args, graph, original, codec, np):
    complete = json_input(args.rms_complete, args.rms_complete_sha256)
    plan = json_input(args.rms_plan, args.rms_plan_sha256)
    provenance = json_input(args.provenance, args.provenance_sha256)
    gpu_raw = capture(args.gpu_ready_artifact, args.gpu_ready_artifact_sha256, codec.MAX_BYTES)
    gpu = codec.decode(gpu_raw)
    codec.hex_bytes(args.generation_hex, 16)
    codec.hex_bytes(args.model_binding_hex, 32)
    if (gpu["origin"] != 1 or gpu["generation"] != args.generation_hex or
            gpu["model_binding"] != args.model_binding_hex or
            provenance.get("gpu_capture_provenance") != gpu["provenance"]):
        raise ValueError("original GPU origin/generation/model/provenance binding differs")
    if provenance.get("selection") != dict(policy="top64-prompt-frequency-id-ascending-ties",
            prompt_tokens_sha256=PROMPT_TOKENS_SHA, tokens=list(SELECTED_TOKENS)):
        raise ValueError("prior frozen natural8K prompt-only selection required")
    required = dict(schema="halogen0162.early-token-native-rms-candidates.v1", completed=True,
                    adapter_sha256=HELPERS["halogen_mtp_early_token_native_rms_producer.py"],
                    original_producer_sha256=HELPERS["halogen_mtp_early_token_producer.py"],
                    portable_RMS_sha256=HELPERS["halogen0162_embedding_rms_cpu_tree_portable.py"],
                    original_plan_sha256=args.rms_plan_sha256, cpu_tolerance=TOLERANCES["cpu"],
                    npu_tolerance=TOLERANCES["npu"])
    if any(complete.get(key) != value for key, value in required.items()):
        raise ValueError("sealed native-RMS producer completion differs")
    plan_required = dict(schema="halogen0162.early-token-producer-plan.v1",
                         producer_sha256=HELPERS["halogen_mtp_early_token_producer.py"],
                         checkpoint_sha256_lineage=original.CHECKPOINT_SHA,
                         checkpoint_native_identity=original.NATIVE_IDENTITY,
                         embedding_entry=original.EMBEDDING_ENTRY, gamma_entry=original.GAMMA_ENTRY,
                         source_pins=original.SOURCE_PINS, receipt_pins=original.RECEIPT_PINS,
                         cpu_tolerance=TOLERANCES["cpu"], npu_tolerance=TOLERANCES["npu"])
    if (any(plan.get(key) != value for key, value in plan_required.items()) or
            complete.get("candidate_tokens") != plan.get("producer_tokens") or
            complete.get("schedule") != plan.get("schedule") or
            complete.get("generation_hex") != args.generation_hex):
        raise ValueError("native table/gamma/descriptor/schedule lineage differs")
    tokens = plan["producer_tokens"]
    if (not isinstance(tokens, list) or not 1 <= len(tokens) <= MAX_ROWS or len(set(tokens)) != len(tokens) or
            any(type(token) is not int or token not in SELECTED_TOKENS for token in tokens)):
        raise ValueError("bounded distinct producer token IDs required")
    rows = complete["rows"]
    if len(rows) != len(tokens) or [row.get("token") for row in rows] != tokens:
        raise ValueError("producer row order/token binding differs")
    files = {item["file"]: item for item in complete["files"]}
    root = args.rms_complete.resolve().parent
    immutable = []
    def payload(name, exact, expected=None):
        item = files[name]
        if Path(name).name != name or item["bytes"] != exact or expected is not None and item["sha256"] != expected:
            raise ValueError("producer file binding differs")
        path = root / name
        raw = capture(path, item["sha256"], exact, exact)
        immutable.append(dict(path=str(path), sha256=item["sha256"], bytes=exact))
        return raw
    if payload("tokens.i32", 4 * len(tokens)) != struct.pack("<" + "i" * len(tokens), *tokens):
        raise ValueError("packed token IDs differ")
    payload("raw-gamma.u16", ROW_BYTES, original.GAMMA_SHA)
    payload("selected-rows.q4c", 64 + len(tokens) * 1440)
    normalized = provenance.get("normalized_rows")
    if not isinstance(normalized, list):
        raise ValueError("GPU capture provenance requires normalized_rows token/hash bindings")
    bindings = {}
    for item in normalized:
        token = item["token"]
        if type(token) is not int or token in bindings:
            raise ValueError("duplicate/invalid normalized-input provenance")
        bindings[token] = item
    oracles = dict(gpu["rows"])
    selected = []
    for index, row in enumerate(rows):
        if row.get("index") != index:
            raise ValueError("producer index differs")
        token = row["token"]
        if token not in oracles:
            continue
        norm_raw = payload(f"{index:03d}-token{token}-norm.u16", ROW_BYTES, row["norm_BF16_sha256"])
        codec.words(norm_raw)
        bound = bindings.get(token, {})
        if (bound.get("norm_BF16_sha256") != sha(norm_raw) or
                bound.get("projection_sha256") != sha(oracles[token])):
            raise ValueError("GPU projection must bind the identical native normalized token row")
        norm = widen(norm_raw, np)
        feed, facts = graph.prepare_input(norm, np)
        if (set(feed) != {"e_high", "e_low"} or sum(value.nbytes for value in feed.values()) != 20480 or
                any(value.dtype != np.float32 or value.shape != (1, WIDTH) or not np.isfinite(value).all() for value in feed.values()) or
                facts["e"]["high_idempotence_verified"] is not True or
                facts["e"]["high_requantization_bit_mismatches"] != 0 or
                facts["e"]["stable_high"]["converged"] is not True):
            raise ValueError("finite bit-exact count1 stable input split required")
        selected.append(dict(token=token, norm=norm, oracle=widen(oracles[token], np),
                             norm_sha256=sha(norm_raw), oracle_sha256=sha(oracles[token]),
                             runtime_input_sets={key: sha(value.tobytes(order="C")) for key, value in feed.items()},
                             input_split_diagnostics=facts))
    if not selected:
        raise ValueError("no frozen selected token was observed in the original GPU capture")
    return selected, immutable, dict(checkpoint_sha256_lineage=original.CHECKPOINT_SHA,
        checkpoint_native_identity=original.NATIVE_IDENTITY, embedding_entry=original.EMBEDDING_ENTRY,
        gamma_entry=original.GAMMA_ENTRY, gamma_sha256=original.GAMMA_SHA,
        gpu_capture_provenance=gpu["provenance"], upstream_provenance=provenance,
        selected_tokens=tokens, observed_selected_tokens=[row["token"] for row in selected])


def cpu_receipt(args, identity, rows, codec, native, runtime, bounded, np):
    gate = json_input(args.cpu_receipt, args.cpu_receipt_sha256, 16 << 20)
    required = dict(schema=SCHEMA, provider="cpu", passed=True, completed=True, phase_identity=identity,
                    tolerance=TOLERANCES["cpu"], tolerance_frozen_before_session=True,
                    ort_graph_optimization_level="ORT_DISABLE_ALL", session_creations=1,
                    repeats=REPEATS, cleanup_errors=[], reserve_guard_error=None)
    if any(gate.get(key) != value for key, value in required.items()):
        raise ValueError("same-source/model/normalized-row successful CPU receipt required")
    proof = runtime.profile_proof(bounded(Path(gate["profile"]), gate["profile_sha256"], 16 << 20), "cpu")
    calls = gate.get("calls", [])
    if proof != gate.get("profile_proof") or not proof["passed"] or proof["node_events"] != 9 * len(rows) * REPEATS:
        raise ValueError("completed exclusive CPU profile required")
    retained = gate.get("rows", [])
    if [item.get("token") for item in retained] != [row["token"] for row in rows] or len(calls) != len(rows) * REPEATS:
        raise ValueError("CPU rows/call extent differs")
    for index, (row, item) in enumerate(zip(rows, retained)):
        words = item["projection_words_u16"]
        if len(words) != WIDTH or any(type(word) is not int or not 0 <= word <= 65535 for word in words):
            raise ValueError("retained CPU BF16 words differ")
        raw = struct.pack("<2560H", *words)
        codec.words(raw)
        actual = widen(raw, np)
        metric = native.comparison(actual, row["oracle"], (1, WIDTH), TOLERANCES["cpu"], np)
        float_sha = sha(actual.tobytes(order="C"))
        if (not metric["passed"] or metric != item["native_comparison"] or sha(raw) != item["projection_sha256"] or
                item.get("output_sha256") != float_sha or item.get("norm_sha256") != row["norm_sha256"] or
                item.get("oracle_sha256") != row["oracle_sha256"]):
            raise ValueError("retained CPU native comparison/hash differs")
        for repeat in range(REPEATS):
            call = calls[repeat * len(rows) + index]
            if (call.get("token") != row["token"] or call.get("repeat") != repeat or call.get("passed") is not True or
                    call.get("projection_sha256") != item["projection_sha256"] or call.get("output_sha256") != float_sha or
                    call.get("native_comparison") != metric):
                raise ValueError("every CPU row/repeat must pass with stable output")
    return dict(path=str(args.cpu_receipt.resolve()), sha256=args.cpu_receipt_sha256,
                profile=gate["profile"], profile_sha256=gate["profile_sha256"])


def write_new(directory, name, raw):
    with (directory / name).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(file=name, bytes=len(raw), sha256=sha(raw))


def run(args):
    if not args.out.is_absolute() or not args.out.parent.is_dir():
        raise ValueError("absolute fresh output directory under existing parent required")
    args.out.mkdir(mode=0o700, parents=False, exist_ok=False)
    result = dict(schema=SCHEMA, provider=args.provider, passed=False, completed=False, error=None,
                  source_sha256=args.source_sha256, tolerance=TOLERANCES[args.provider],
                  tolerance_frozen_before_session=True, ort_graph_optimization_level="ORT_DISABLE_ALL",
                  repeats=REPEATS, session_creations=0, rows=[], calls=[], cleanup_errors=[],
                  reserve_guard_error=None, count=1, batch_supported=False, live_artifact_admitted=False,
                  root_owned_idle_window_required=True, outer_owned_deadline_required=True,
                  admission_gib=22, reserve_gib=18, overlap_admitted=False, speed_claim=False)
    session = options = runtime_handle = dll_directory = guard = ort = devices = None
    registered = profile_finished = False
    outputs, immutable, modules, phase_identity = {}, [], None, None
    try:
        capture(Path(__file__), args.source_sha256, 2 << 20)
        if any(os.environ.get(key) != "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("BLAS/OpenMP thread variables must be1 before Python starts")
        modules = sealed_modules(args)
        graph, original, codec, shared, native, runtime, bounded = modules
        guard = runtime.ReserveGuard()
        guard.start()
        import numpy as np
        import onnxruntime as ort
        if np.__version__ != "2.5.3" or ort.__version__ != "1.25.2":
            raise ValueError("frozen NumPy2.5.3/ORT1.25.2 required")
        candidate, _ = graph.verify_graph(args.model, args.projection_receipt, args.projection_receipt_sha256)
        if (candidate["model_sha256"] != MODEL_SHA or candidate["data_sha256"] != DATA_SHA or
                args.projection_receipt_sha256 != MODEL_RECEIPT_SHA):
            raise ValueError("preserved embedding graph/model/external weight pins required")
        rows, immutable, lineage = row_inputs(args, graph, original, codec, np)
        dependencies = runtime.dependencies()
        phase_identity = dict(source_sha256=args.source_sha256, codec_sha256=args.codec_sha256,
            sealed_helper_directory=str(Path(graph.__file__).resolve().parent),
            helper_sha256={**HELPERS, **dependencies}, model_sha256=MODEL_SHA, data_sha256=DATA_SHA,
            projection_receipt_sha256=MODEL_RECEIPT_SHA, transformer_sha256=args.transformer_sha256,
            rms_complete_sha256=args.rms_complete_sha256, rms_plan_sha256=args.rms_plan_sha256,
            gpu_ready_artifact_sha256=args.gpu_ready_artifact_sha256, provenance_sha256=args.provenance_sha256,
            generation=args.generation_hex, model_binding=args.model_binding_hex, lineage=lineage,
            arithmetic=candidate["arithmetic"], weight_lineage=candidate["weight_lineage"],
            weight_diagnostics=candidate["weight_diagnostics"], data_bytes=candidate["data_bytes"],
            ort_version=ort.__version__, numpy_version=np.__version__,
            normalized_rows=[{key: row[key] for key in ("token", "norm_sha256", "oracle_sha256", "runtime_input_sets", "input_split_diagnostics")} for row in rows])
        result["phase_identity"] = phase_identity
        if args.provider == "npu":
            result["cpu_receipt"] = cpu_receipt(args, phase_identity, rows, codec, native, runtime, bounded, np)
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog, ExecutionProviderReadyState
            runtime_handle = initialize()
            ep = next(ep for ep in ExecutionProviderCatalog.get_default().find_all_providers() if ep.name == "VitisAIExecutionProvider")
            if ep.ready_state == ExecutionProviderReadyState.NOT_PRESENT:
                raise RuntimeError("VitisAI absent; acquisition disabled")
            ready = ep.ensure_ready_async().get()
            guard.check()
            if int(ready.status) != 1:
                raise RuntimeError("VitisAI readiness failed: " + ready.diagnostic_text)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(args.out / "projection-profile")
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            chosen, verified = verified_provider_copy(Path(ep.library_path).resolve(strict=True), args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            ort.register_execution_provider_library(ep.name, str(chosen))
            registered = True
            devices = [device for device in ort.get_ep_devices() if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("exactly one VitisAI NPU device required")
            cache = args.out / "vitisai-cache"
            cache.mkdir(exist_ok=False)
            cache_key = sha((MODEL_SHA + ":" + DATA_SHA + ":" + graph.digest(chosen) + ":ORT_DISABLE_ALL").encode())
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(provider_library=str(chosen), provider_library_sha256=graph.digest(chosen),
                          provider_copy_files=verified, cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        result["session_creations"] = 1
        session = ort.InferenceSession(str(args.model), sess_options=options, enable_fallback=False,
                                       **({} if args.provider == "npu" else {"providers": ["CPUExecutionProvider"]}))
        session.disable_fallback()
        if [item.name for item in session.get_inputs()] != ["e_high", "e_low"] or [item.name for item in session.get_outputs()] != ["e_projection"]:
            raise RuntimeError("exact count1 embedding session ABI required")
        result["session_providers"] = session.get_providers()
        if args.provider == "npu":
            context = cache / cache_key / "context.json"
            context_sha = graph.digest(context)
            proof = runtime.context_proof(bounded(context, context_sha, 2 << 20), candidate["metadata"]["required_hardware_partition_outputs"], cache_key, chosen)
            result.update(context=str(context), context_sha256=context_sha, context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("all9 embedding values require exclusive hardware/STX placement")
        for repeat in range(REPEATS):
            for row in rows:
                guard.check()
                feed, facts = graph.prepare_input(row["norm"], np)
                feed = {key: np.array(value, dtype=np.float32, order="C", copy=True) for key, value in feed.items()}
                hashes = {key: shared.array_hash(value) for key, value in feed.items()}
                if hashes != row["runtime_input_sets"] or facts != row["input_split_diagnostics"]:
                    raise RuntimeError("normalized input/split changed")
                actual = session.run(["e_projection"], feed)[0]
                raw = bf16_bytes(actual, np)
                metric = native.comparison(actual, row["oracle"], (1, WIDTH), TOLERANCES[args.provider], np)
                if not metric["passed"] or outputs.setdefault(row["token"], raw) != raw:
                    raise RuntimeError("original native projection tolerance/repeat gate failed")
                result["calls"].append(dict(token=row["token"], repeat=repeat, passed=True,
                    projection_sha256=sha(raw), output_sha256=shared.array_hash(actual), native_comparison=metric))
                if repeat == 0:
                    result["rows"].append(dict(token=row["token"], norm_sha256=row["norm_sha256"],
                        oracle_sha256=row["oracle_sha256"], projection_sha256=sha(raw),
                        output_sha256=shared.array_hash(actual), projection_words_u16=list(struct.unpack("<2560H", raw)),
                        native_comparison=metric))
        profile = Path(session.end_profiling())
        profile_finished = True
        profile_sha = graph.digest(profile)
        proof = runtime.profile_proof(bounded(profile, profile_sha, 16 << 20), args.provider)
        result.update(profile=str(profile), profile_sha256=profile_sha, profile_proof=proof)
        if (not proof["passed"] or proof["node_events"] < len(result["calls"]) or
                args.provider == "cpu" and proof["node_events"] != 9 * len(result["calls"])):
            raise RuntimeError("every count1 call requires exclusive requested-provider profile")
        immutable.extend(candidate["immutable_files"])
        immutable.extend([dict(path=str(path.resolve()), sha256=expected) for path, expected in (
            (args.rms_complete, args.rms_complete_sha256), (args.rms_plan, args.rms_plan_sha256),
            (args.gpu_ready_artifact, args.gpu_ready_artifact_sha256), (args.provenance, args.provenance_sha256),
            (args.projection_receipt, args.projection_receipt_sha256), (Path(__file__), args.source_sha256),
            (HERE / "halogen0162_ready_embedding_rows.py", args.codec_sha256))])
        if args.provider == "npu":
            immutable.extend([dict(path=result["cpu_receipt"]["path"], sha256=args.cpu_receipt_sha256),
                              dict(path=result["cpu_receipt"]["profile"], sha256=result["cpu_receipt"]["profile_sha256"]),
                              dict(path=str(context), sha256=context_sha)])
        if any(graph.digest(item["path"]) != item["sha256"] for item in immutable) or runtime.dependencies() != dependencies:
            raise RuntimeError("immutable source/model/data/row/oracle/CPU evidence changed")
        sealed_modules(args)
        result["completed"] = True
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if session is not None and not profile_finished:
            try:
                partial = Path(session.end_profiling())
                result.update(partial_profile=str(partial), partial_profile_sha256=sha(partial.read_bytes()))
            except Exception as exc:
                result["cleanup_errors"].append("partial profile: " + str(exc))
        session = options = devices = None
        gc.collect()
        for name, active, action in (("provider_unregistered", registered, lambda: ort.unregister_execution_provider_library("VitisAIExecutionProvider")),
                                    ("dll_directory_closed", dll_directory is not None, lambda: dll_directory.close()),
                                    ("bootstrap_shutdown", runtime_handle is not None, lambda: runtime_handle())):
            try:
                if active:
                    action()
                    result[name] = True
            except Exception as exc:
                result["cleanup_errors"].append(name + ": " + str(exc))
        if guard is not None:
            guard.stop()
            result.update(reserve_samples=guard.samples, reserve_guard_error=guard.error)
            if guard.error:
                result["cleanup_errors"].append("reserve guard: " + guard.error)
    result["passed"] = result["completed"] and result["error"] is None and not result["cleanup_errors"]
    if result["passed"] and args.provider == "npu":
        try:
            provenance = dict(schema="halogen0162.ready-embedding-provenance.v1", phase_identity=phase_identity,
                              provider="npu", tolerance=TOLERANCES["npu"], profile_sha256=result["profile_sha256"],
                              context_sha256=result["context_sha256"], context_proof=result["context_proof"],
                              provider_library_sha256=result["provider_library_sha256"], cache_key=result["cache_key"],
                              provider_copy_files=result["provider_copy_files"], cpu_receipt=result["cpu_receipt"],
                              projections=[{key: row[key] for key in ("token", "norm_sha256", "oracle_sha256", "projection_sha256", "output_sha256", "native_comparison")} for row in result["rows"]])
            provenance_file = write_new(args.out, "provenance.json", canonical(provenance))
            records = []
            for row in result["rows"]:
                item = write_new(args.out, f"token{row['token']}-e_projection.u16", outputs[row["token"]])
                records.append(dict(token=row["token"], file=item["file"], sha256=item["sha256"]))
            manifest = dict(schema="halogen_ready_embedding_rows.v1", origin=2, generation=args.generation_hex,
                            model_binding=args.model_binding_hex, provenance=provenance_file["sha256"], rows=records)
            manifest_file = write_new(args.out, "ready-rows.json", canonical(manifest))
            result.update(manifest=str(args.out / "ready-rows.json"), manifest_sha256=manifest_file["sha256"],
                          provenance=str(args.out / "provenance.json"), provenance_sha256=provenance_file["sha256"])
        except Exception as exc:
            result.update(passed=False, completed=False, error=type(exc).__name__ + ": " + str(exc))
    if not result["passed"]:
        result["completed"] = False
    write_new(args.out, "complete.json", canonical(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    for name in ("rms-complete", "rms-plan", "gpu-ready-artifact", "model", "projection-receipt", "provenance", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-sha256", "codec-sha256", "rms-complete-sha256", "rms-plan-sha256",
                 "gpu-ready-artifact-sha256", "projection-receipt-sha256", "transformer-sha256", "provenance-sha256",
                 "generation-hex", "model-binding-hex"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--sealed-helper-dir", type=Path, default=HERE,
                        help="original pinned helper folder matching existing graph receipt paths")
    parser.add_argument("--cpu-receipt", type=Path)
    parser.add_argument("--cpu-receipt-sha256")
    args = parser.parse_args(argv)
    if args.provider == "npu":
        if args.ep_dir is None or args.cpu_receipt is None or args.cpu_receipt_sha256 is None:
            parser.error("NPU requires verified provider directory and same-row successful CPU receipt")
    elif any(value is not None for value in (args.ep_dir, args.cpu_receipt, args.cpu_receipt_sha256)):
        parser.error("CPU must omit provider/CPU-receipt arguments")
    result = run(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "completed", "error", "provider", "manifest", "manifest_sha256")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
