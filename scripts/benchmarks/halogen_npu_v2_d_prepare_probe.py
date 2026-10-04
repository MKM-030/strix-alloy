"""Receipt-bound count1 D preparation replay; root alone owns hardware launch.

One captured BF16 embedding/residual pair and one deterministic distinct BF16
pair exercise e/h independently. This qualifies only approximate graph
arithmetic and strict ORT/VAIML attribution, never native parity or full MTP.
Launch inside the root's bounded owned-job guard: the continuous local reserve
monitor records breaches, while the outer guard must interrupt blocked native
initialization or execution. No provider acquisition, graph rewrites or retries.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import stat
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
WIDTH, HIDDEN, GIB = 2560, 10240, 1024**3
TOLERANCES = {"cpu": {"rtol": .002, "atol": .0002}, "npu": {"rtol": .03, "atol": .003}}
PINNED_HELPERS = {
    "scripts/benchmarks/halogen_npu_expert_onnx.py": "900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722",
    "scripts/benchmarks/hgn_q4c_slice.py": "fe0dd1b9974f95bed02f37dddde1ee7c286f3f69d491548008d4a94ea703fdce",
    "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def require_sha(value):
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("expected lowercase SHA-256")
    return value


def dependencies():
    actual = {name: digest(ROOT / name) for name in PINNED_HELPERS}
    if actual != PINNED_HELPERS:
        raise ValueError("frozen provider-copy or memory helper changed")
    actual["scripts/benchmarks/halogen_npu_v2_d_prepare.py"] = digest(Path(__file__).with_name("halogen_npu_v2_d_prepare.py"))
    return actual


def profile_proof(events, provider):
    nodes = [event for event in events if event.get("cat") == "Node"]
    observed = sorted({event.get("args", {}).get("provider", "<missing>") for event in nodes})
    expected = "VitisAIExecutionProvider" if provider == "npu" else "CPUExecutionProvider"
    return {"passed": bool(nodes) and observed == [expected], "node_events": len(nodes),
            "executed_node_providers": observed,
            "node_event_ops": sorted({event.get("args", {}).get("op_name", "<missing>") for event in nodes})}


def context_proof(context, required_outputs, cache_key, library):
    config = context.get("config", {})
    options = config.get("sessionOptions", {})
    defs = context.get("metaDef", [])
    hardware = bool(defs) and all(row.get("device") == "VAIML" and
        row.get("vaimlParam", {}).get("deviceName") == "stx" and
        row.get("vaimlParam", {}).get("runnerType") == "hw" for row in defs)
    covered = {name for row in defs for name in row.get("nodes", [])}
    missing = sorted(set(required_outputs) - covered)
    fallback = config.get("ort_session_config", {}).get("session.disable_cpu_ep_fallback") == "1"
    key_matches = config.get("cacheKey") == cache_key and options.get("cache_key") == cache_key
    normalize = lambda path: os.path.normcase(os.path.abspath(path))
    library_matches = normalize(str(options.get("library_path", ""))) == normalize(str(library))
    partition_pass = any(row.get("name") == "vaiml_partition" and
        row.get("vaimlConfig", {}).get("device") == "stx" for row in config.get("passes", []))
    return {"passed": hardware and not missing and fallback and key_matches and library_matches and partition_pass,
            "hardware_partitions_only": hardware, "missing_required_outputs": missing,
            "cpu_fallback_disabled_in_context": fallback, "cache_key_matches": key_matches,
            "provider_library_matches": library_matches, "stx_partition_pass": partition_pass,
            "partitions": [{"id": row.get("id"), "device": row.get("device"),
                            "nodes": row.get("nodes", []), "inputs": row.get("inputs", []),
                            "outputs": row.get("outputs", []), "constantInitializers": row.get("constantInitializers", []),
                            "vaimlParam": row.get("vaimlParam", {})} for row in defs],
            "config_passes": config.get("passes", []),
            "scope": "retained VAIML hw/stx partition names cover every original dynamic D value including norm, arithmetic, reshape and BF16 casts; internal kernel offload is not independently observed"}


class ReserveGuard:
    def __init__(self):
        sys.path.insert(0, str(ROOT / "server"))
        from host_frames import frame
        self.frame = frame
        self.samples, self.error = [], None
        self.done, self.ready = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self.watch, name="D-probe-reserve", daemon=True)

    def sample(self, minimum):
        row = {"time": time.time(), **self.frame()}
        self.samples.append(row)
        if min(row["available_bytes"], row["commit_headroom_bytes"]) < minimum * GIB:
            raise RuntimeError(f"physical/commit headroom below {minimum} GiB")
        return row

    def watch(self):
        try:
            while not self.done.is_set():
                self.sample(18)
                self.ready.set()
                self.done.wait(.1)
        except BaseException as exc:
            self.error = type(exc).__name__ + ": " + str(exc)
            self.ready.set()

    def start(self):
        self.sample(22)
        self.thread.start()
        if not self.ready.wait(2):
            raise RuntimeError("continuous reserve monitor did not start")
        self.check()

    def check(self, admission=False):
        if self.error:
            raise RuntimeError("continuous reserve breached: " + self.error)
        self.sample(22 if admission else 18)
        if self.error:
            raise RuntimeError("continuous reserve breached: " + self.error)

    def stop(self):
        self.done.set()
        if self.thread.is_alive():
            self.thread.join(2)
        if self.thread.is_alive():
            self.error = self.error or "reserve monitor did not stop"


def fixtures(args, builder, np):
    captured, bindings = {}, {}
    for name, path, expected, width in (("e", args.e_u16, args.e_sha256, WIDTH), ("h", args.h_u16, args.h_sha256, HIDDEN)):
        path = path.resolve(strict=True)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != width * 2:
            raise ValueError("captured raw BF16 must be a regular file of the exact extent: " + name)
        before = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        with path.open("rb") as stream:
            payload = stream.read(width * 2 + 1)
        if len(payload) != width * 2 or hashlib.sha256(payload).hexdigest() != require_sha(expected):
            raise ValueError("captured raw BF16 size/hash differs: " + name)
        value = builder.widen_bf16(np.frombuffer(payload, dtype="<u2")).reshape(1, width).copy()
        info = path.stat()
        after = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if not np.isfinite(value).all() or after != before:
            raise ValueError("captured BF16 input nonfinite or changed: " + name)
        captured[name] = value
        bindings[name] = {"path": str(path), "sha256": expected, "bytes": len(payload), "shape": [1, width],
                          "interpretation": "little-endian raw BF16 u16, exactly widened to FLOAT; no rerounding"}
    rng = np.random.default_rng(20261004)
    synthetic = {name: builder.bf16_rne(rng.normal(0, .5, value.shape).astype(np.float32)) for name, value in captured.items()}
    if any(np.array_equal(captured[name], synthetic[name]) for name in captured):
        raise ValueError("controlled feed must change both e and h")
    return {"A": captured, "B": synthetic}, {"A": bindings, "B": {"scope": "controlled distinct synthetic BF16 feed", "seed": 20261004}}


def comparison(actual, expected, tolerance, np):
    if actual.dtype != np.float32 or actual.shape != (1, 4, WIDTH) or expected.shape != actual.shape or not np.isfinite(actual).all():
        return {"passed": False, "shape_dtype_or_finiteness_error": True, "non_bf16_lattice_elements": None}
    close = np.isclose(actual, expected, **tolerance)
    bits, expected_bits = actual.view(np.uint32), expected.view(np.uint32)
    lattice_mismatches = int(((bits & np.uint32(0xffff)) != 0).sum())
    return {"passed": bool(close.all()) and lattice_mismatches == 0, "tolerance": tolerance,
            "max_abs_error": float(np.max(np.abs(actual - expected))),
            "mismatched_elements": int((~close).sum()), "elements": int(actual.size),
            "exact_fp32_bit_mismatches": int((bits != expected_bits).sum()),
            "bf16_word_mismatches": int(((bits >> 16) != (expected_bits >> 16)).sum()),
            "non_bf16_lattice_elements": lattice_mismatches}


def replay(args):
    report = args.report.resolve()
    if report.exists() or not report.parent.is_dir():
        raise FileExistsError("report must be an exclusive new file in an existing output directory")
    lock = report.with_name(report.name + ".lock").open("x", encoding="utf-8")
    result = {"schema": "halogen_v2_count1_D_probe.v1", "passed": False, "provider": args.provider,
              "wire_mode": "D", "count": 1, "source_sha256": digest(__file__), "dependency_sha256": {},
              "tolerance": TOLERANCES[args.provider], "tolerance_frozen_before_session": True,
              "warmup_count": args.warmup, "repetitions": args.reps, "calls": [], "session_creations": 0,
              "cpu_fallback_allowed": args.provider == "cpu", "numerical_gate_passed": False, "timing_qualified": False,
              "native_bit_parity_qualified": False, "full_mtp_claim": False, "acceptance_claim": False,
              "admission_gib": 22, "reserve_gib": 18, "guard_interval_seconds": .1,
              "outer_owned_job_guard_required": True,
              "timing_scope": "fresh contiguous e/h copies and session.run transfer/execution/output; references/build/verification/load/compile/gates/output retention excluded"}
    runtime = session = options = devices = dll_directory = ort = guard = None
    registered = profile_finished = False
    cleanup_errors = []
    try:
        threads = {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}
        if any(value != "1" for value in threads.values()):
            raise ValueError("set BLAS/OpenMP thread variables to 1 before Python starts")
        result["blas_thread_environment"] = threads
        guard = ReserveGuard()
        guard.start()
        result["dependency_sha256"] = dependencies()
        import numpy as np
        import onnx
        import halogen_npu_v2_d_prepare as builder
        model = args.model.resolve(strict=True)
        build_path = args.build_receipt.resolve(strict=True)
        build, weights = builder.verify_model(model, build_path, require_sha(args.build_receipt_sha256), "D")
        result.update(build_receipt=str(build_path), build_receipt_sha256=args.build_receipt_sha256,
                      model=str(model), model_sha256=build["model_sha256"], data=str(build["data"]),
                      data_sha256=build["data_sha256"], data_bytes=build["data_bytes"],
                      assets_receipt=build["assets_receipt"], assets_receipt_sha256=build["assets_receipt_sha256"],
                      builder_sha256=build["builder_sha256"], arithmetic=build["arithmetic"])
        feeds, binding = fixtures(args, builder, np)
        references = {label: builder.reference(feed["e"], feed["h"], weights, "D") for label, feed in feeds.items()}
        result.update(fixture_binding=binding,
                      runtime_input_sets={label: {name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in feed.items()} for label, feed in feeds.items()},
                      reference_outputs={label: value.tolist() for label, value in references.items()},
                      reference_sha256={label: hashlib.sha256(value.tobytes()).hexdigest() for label, value in references.items()})
        stale_checks = []
        for label, other in (("A", "B"), ("B", "A")):
            for name in ("e", "h"):
                guard.check()
                stale_feed = dict(feeds[label], **{name: feeds[other][name]})
                stale = builder.reference(stale_feed["e"], stale_feed["h"], weights, "D")
                row = comparison(stale, references[label], result["tolerance"], np)
                stale_checks.append({"input_set": label, "stale_input": name, "replacement_set": other,
                                     "comparison": row, "distinguished": not row["passed"]})
        result["stale_runtime_input_checks"] = stale_checks
        if not all(row["distinguished"] for row in stale_checks):
            raise ValueError("fixed A/B references cannot distinguish every stale e/h at the frozen tolerance")
        graph = onnx.load(str(model), load_external_data=False)
        matmul_outputs = {name for node in graph.graph.node if node.op_type == "MatMul" for name in node.output}
        dynamic_values = {value.name for value in graph.graph.input}
        required_outputs, constant_outputs = set(), set()
        for node in graph.graph.node:
            if any(name in dynamic_values for name in node.input):
                dynamic_values.update(node.output)
                required_outputs.update(node.output)
            else:
                constant_outputs.update(node.output)
        if len(matmul_outputs) != 2 or "seed" not in required_outputs or not matmul_outputs <= required_outputs:
            raise ValueError("D graph must contain two independently covered projections and seed")
        result["required_hardware_partition_outputs"] = sorted(required_outputs)
        result["constant_foldable_node_outputs"] = sorted(constant_outputs)
        result["context_origin_alias_policy"] = "each dynamic original output name must be present; missing compiler alias/origin mapping leaves complete D placement and timing unproven"
        weights = build = graph = stale = stale_feed = None
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
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(report.with_suffix(""))
        if args.provider == "npu":
            from halogen_npu_expert_onnx import verified_provider_copy
            catalog = Path(ep.library_path).resolve(strict=True)
            chosen, verified = verified_provider_copy(catalog, args.ep_dir)
            dll_directory = os.add_dll_directory(str(chosen.parent))
            result.update(catalog_library=str(catalog), provider_library=str(chosen),
                          provider_library_sha256=digest(chosen), provider_copy_files=verified,
                          execution_provider_allowlist=["VitisAIExecutionProvider"])
            ort.register_execution_provider_library(ep.name, str(chosen))
            registered = True
            devices = [device for device in ort.get_ep_devices() if device.ep_name == ep.name and str(device.device.type).endswith(".NPU")]
            if len(devices) != 1:
                raise RuntimeError("expected one VitisAI NPU device")
            cache = report.parent / "vitisai-cache"
            cache.mkdir(exist_ok=False)
            cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" + result["provider_library_sha256"]).encode()).hexdigest()
            options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
            options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
            result.update(cache_key=cache_key, session_disable_cpu_ep_fallback="1")
        guard.check(admission=True)
        result["session_creations"] += 1
        started = time.perf_counter_ns()
        session = ort.InferenceSession(str(model), sess_options=options, enable_fallback=False) if args.provider == "npu" else ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        session.disable_fallback()
        result.update(ort_version=ort.__version__, session_providers=session.get_providers(), initialization_ms=(time.perf_counter_ns() - started) / 1e6)
        guard.check()
        if args.provider == "npu":
            context_path = cache / cache_key / "context.json"
            if not context_path.is_file() or context_path.stat().st_size > 2 << 20:
                raise RuntimeError("fresh bounded compiler context unavailable")
            context = json.loads(context_path.read_text(encoding="utf-8"))
            proof = context_proof(context, required_outputs, cache_key, chosen)
            result.update(context=str(context_path), context_sha256=digest(context_path), context_proof=proof)
            if not proof["passed"]:
                raise RuntimeError("complete D placement unproven: compiler context lacks original dynamic norm/arithmetic/reshape/BF16 boundary coverage or matching hardware/fallback identity")
        for index in range(args.warmup + args.reps):
            guard.check()
            label = "A" if index % 2 == 0 else "B"
            started = time.perf_counter_ns()
            feed = {name: np.array(value, dtype=np.float32, order="C", copy=True) for name, value in feeds[label].items()}
            copied = time.perf_counter_ns()
            outputs = session.run(["seed"], feed)
            finished = time.perf_counter_ns()
            actual = outputs[0]
            row = {"call_index": index, "warmup": index < args.warmup, "input_set": label,
                   "host_call_ms": (finished - started) / 1e6, "prepare_and_copy_ms": (copied - started) / 1e6,
                   "session_run_ms": (finished - copied) / 1e6,
                   "actual_output": actual.tolist() if np.isfinite(actual).all() else None,
                   "actual_output_words_u32": actual.view(np.uint32).tolist() if actual.dtype == np.float32 else None,
                   "unexpected_dtype_raw_hex": actual.tobytes().hex() if actual.dtype != np.float32 else None,
                   "output_sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
                   "actual_shape": list(actual.shape), "actual_dtype": str(actual.dtype)}
            result["calls"].append(row)
            row["comparison"] = comparison(actual, references[label], result["tolerance"], np)
            row["passed"] = row["comparison"]["passed"] and row["comparison"]["non_bf16_lattice_elements"] == 0
            feed = actual = outputs = None
            guard.check()
        profile = Path(session.end_profiling())
        profile_finished = True
        proof = profile_proof(json.loads(profile.read_text(encoding="utf-8")), args.provider)
        result.update(profile=str(profile), profile_sha256=digest(profile), profile_proof=proof)
        if not proof["passed"]:
            raise RuntimeError("profile does not prove every Node executed by the requested provider")
        if dependencies() != result["dependency_sha256"] or digest(__file__) != result["source_sha256"]:
            raise RuntimeError("replay source changed")
        for path, expected in ((model, result["model_sha256"]), (result["data"], result["data_sha256"]), (build_path, args.build_receipt_sha256)):
            if digest(path) != expected:
                raise RuntimeError("frozen graph/data/build receipt changed")
        for row in binding["A"].values():
            if digest(row["path"]) != row["sha256"]:
                raise RuntimeError("captured feed changed during replay")
        result["numerical_gate_passed"] = all(row["passed"] for row in result["calls"])
        if not result["numerical_gate_passed"]:
            raise RuntimeError("frozen arithmetic screening failed; all returned outputs retained")
        measured = [row for row in result["calls"] if not row["warmup"]]
        times = sorted(row["host_call_ms"] for row in measured)
        result.update(passed=True, timing_qualified=True, mean_host_call_ms=statistics.fmean(times),
                      median_host_call_ms=statistics.median(times), min_host_call_ms=min(times),
                      p95_host_call_ms=times[math.ceil(.95 * len(times)) - 1],
                      mean_session_run_ms=statistics.fmean(row["session_run_ms"] for row in measured),
                      mean_prepare_and_copy_ms=statistics.fmean(row["prepare_and_copy_ms"] for row in measured),
                      exact_reference_bit_parity=all(row["comparison"]["exact_fp32_bit_mismatches"] == 0 for row in result["calls"]))
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
                result.update(minimum_available_gib=min(row["available_bytes"] for row in guard.samples) / GIB,
                              minimum_commit_headroom_gib=min(row["commit_headroom_bytes"] for row in guard.samples) / GIB)
            if guard.error:
                cleanup_errors.append("reserve guard: " + guard.error)
        if cleanup_errors:
            result.update(passed=False, timing_qualified=False, cleanup_errors=cleanup_errors)
        try:
            with report.open("x", encoding="utf-8") as output:
                json.dump(result, output, indent=2, allow_nan=False)
        finally:
            lock.close()
            report.with_name(report.name + ".lock").unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "build-receipt", "e-u16", "h-u16", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("build-receipt-sha256", "e-sha256", "h-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--provider", choices=("cpu", "npu"), required=True)
    parser.add_argument("--ep-dir", type=Path)
    parser.add_argument("--warmup", type=int, default=4)
    parser.add_argument("--reps", type=int, default=8)
    args = parser.parse_args()
    if not 2 <= args.warmup <= 4 or args.warmup % 2 or not 2 <= args.reps <= 16 or args.reps % 2:
        parser.error("use 2/4 warmups and 2..16 even measured repetitions for balanced A/B")
    if (args.provider == "npu") != (args.ep_dir is not None):
        parser.error("NPU requires --ep-dir; CPU must omit it")
    result = replay(args)
    print(json.dumps({key: result.get(key) for key in ("passed", "error", "provider", "session_creations", "numerical_gate_passed", "timing_qualified", "mean_host_call_ms", "native_bit_parity_qualified")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
