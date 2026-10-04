"""Small isolated ROCR component probe; root owns every hardware window.

Run only inside the pinned, read-only image under an outer retained process,
deadline and 18 GiB host physical/commit reserve guard. This file creates no
containers, downloads, model sessions or host processes. Stock/candidate differ
only in the read-only HSA-library mount. It measures a fixed original RMS replay
and async-loop idle CPU; these are component results, not token-rate claims.
The compare subcommand is entirely offline.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import statistics
import stat
import struct
import sys
import threading
import time


IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
BASE = Path("/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib")
HIP_SHA = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
STOCK_HSA_SHA = "1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5"
BRIDGE_SHA = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
FIXTURES_SHA = "cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246"
GAMMA_SHA = "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"
KERNEL = b"_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii"
WIDTH, TENSOR_BYTES, WARMUP, REPEATS, IDLE_SECONDS = 2560, 5120, 8, 64, 10
EXPECTED_ENV = {
    "HSA_ENABLE_DXG_DETECTION": "1", "HSA_ENABLE_SDMA": "1",
    "HALOGEN_LQ8_WAVE": "1", "HSA_DISABLE_COREDUMP_ON_EXCEPTION": "1",
    "LD_LIBRARY_PATH": "/usr/lib:" + str(BASE) + ":/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(path, expected, exact_bytes=None, maximum=64 << 20):
    path = Path(path)
    require(path.is_absolute(), "absolute file path required")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum and
                (exact_bytes is None or before.st_size == exact_bytes), "file extent differs: " + str(path))
        raw = b""
        while len(raw) < before.st_size:
            part = os.read(fd, min(1 << 20, before.st_size - len(raw)))
            require(bool(part), "short read: " + str(path))
            raw += part
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        ident = lambda value: tuple(getattr(value, key) for key in fields)
        require(ident(before) == ident(after) == ident(path.lstat()), "file changed: " + str(path))
        actual = digest(raw)
        require(actual == expected, "SHA256 differs: " + str(path))
        return raw, dict(path=str(path), sha256=actual, bytes=len(raw))
    finally:
        os.close(fd)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def api(library, name, arguments, result=C.c_int):
    function = getattr(library, name)
    function.argtypes, function.restype = arguments, result
    return function


def ok(status, label):
    require(status == 0, label + " failed: " + str(status))


def mapped_bindings(expected):
    """Verify actual mapped paths, not only the proposed LD_LIBRARY_PATH."""
    lines = Path("/proc/self/maps").read_text().splitlines()
    mapped = {line.split(maxsplit=5)[5] for line in lines if len(line.split(maxsplit=5)) == 6}
    result = {}
    for key, (name, wanted_sha) in expected.items():
        paths = {Path(value).resolve(strict=True) for value in mapped
                 if value.startswith("/") and Path(value).name.startswith(name)}
        require(len(paths) == 1, "expected one mapped " + key + " library")
        path = next(iter(paths))
        _, result[key] = capture(path, wanted_sha)
    return result


def cpu_snapshot():
    result = {}
    for directory in Path("/proc/self/task").iterdir():
        try:
            raw = (directory / "stat").read_text()
            end = raw.rfind(")")
            tail = raw[end + 2:].split()
            result[directory.name] = dict(name=raw[raw.find("(") + 1:end], state=tail[0],
                utime=int(tail[11]), stime=int(tail[12]), start_ticks=int(tail[19]),
                wchan=(directory / "wchan").read_text().strip())
        except FileNotFoundError:
            continue
    return result


def idle_bracket(label):
    before = cpu_snapshot()
    cpu0, wall0 = time.process_time_ns(), time.monotonic_ns()
    time.sleep(IDLE_SECONDS)
    wall1, cpu1 = time.monotonic_ns(), time.process_time_ns()
    after = cpu_snapshot()
    elapsed = (wall1 - wall0) / 1e9
    ticks = os.sysconf("SC_CLK_TCK")
    rows = []
    for tid, last in after.items():
        first = before.get(tid)
        if first is not None and first["start_ticks"] == last["start_ticks"]:
            seconds = (last["utime"] + last["stime"] - first["utime"] - first["stime"]) / ticks
            rows.append(dict(tid=int(tid), name=last["name"], cpu_seconds=seconds,
                mean_cpu_cores=seconds / elapsed, state_before=first["state"],
                state_after=last["state"], wchan_before=first["wchan"], wchan_after=last["wchan"]))
    return dict(label=label, requested_seconds=IDLE_SECONDS, elapsed_seconds=elapsed,
        process_cpu_seconds=(cpu1 - cpu0) / 1e9, mean_process_cpu_cores=(cpu1 - cpu0) / 1e9 / elapsed,
        threads=sorted(rows, key=lambda row: row["cpu_seconds"], reverse=True),
        born_tids=sorted(set(after) - set(before)), gone_tids=sorted(set(before) - set(after)))


class Signal(C.Structure):
    _fields_ = [("handle", C.c_uint64)]


def probe(args):
    require(os.name == "posix" and Path("/proc/self/maps").is_file(), "Linux pinned image required")
    require(args.outer_owned_gpu_guard, "root-owned GPU/deadline/host-reserve guard acknowledgment required")
    if args.variant == "stock":
        require(args.hsa_sha256 == STOCK_HSA_SHA, "stock runtime SHA differs")
    require(len(args.hsa_sha256) == 64 and set(args.hsa_sha256) <= set("0123456789abcdef"), "invalid runtime SHA")
    require(all(os.environ.get(key) == value for key, value in EXPECTED_ENV.items()), "fixed environment differs")
    require(os.environ.get("HSA_WAIT_ANY_DEBUG") in (None, "0"), "default AsyncEventsLoop path required")
    require(os.environ.get("HSA_ENABLE_INTERRUPT") in (None, "1"), "default interrupt setting required")
    output = Path(args.output)
    require(output.is_absolute() and output.is_dir() and not any(output.iterdir()), "fresh empty /result required")
    report = dict(schema="halogen.rocr-poll-backoff-component.v1", variant=args.variant,
        image=IMAGE, passed=False, scope="fixed original RMS + async idle CPU; no model/token-rate/acceptance claim",
        environment={**EXPECTED_ENV, "HSA_WAIT_ANY_DEBUG": os.environ.get("HSA_WAIT_ANY_DEBUG"),
                     "HSA_ENABLE_INTERRUPT": os.environ.get("HSA_ENABLE_INTERRUPT")},
        warmup_per_fixture=WARMUP, repeats_per_fixture=REPEATS, tensor_bytes=TENSOR_BYTES,
        width=WIDTH, groups=1, grid=[1, 1, 1], block=[256, 1, 1], shared_bytes=0,
        input_output_alias=True, kernel_symbol=KERNEL.decode(), bindings={}, idle=[], timings=[], cleanup_errors=[])
    hip = hsa = None
    module, tensor, gamma_device = C.c_void_p(), C.c_void_p(), C.c_void_p()
    signal, callback = Signal(), None
    hsa_owned = False
    handler_registered = False
    callback_done = threading.Event()
    callback_values = []
    callback_times_ns = []
    try:
        files = {
            "source": (Path(__file__).absolute(), args.source_sha256, None),
            "engine": (Path("/candidate/flash_serve"), ENGINE_SHA, 26052768),
            "codeobject": (Path("/candidate/engine-gfx1151.hsaco"), CODE_SHA, 17704408),
            "fixtures": (Path("/fixtures/fixtures.json"), FIXTURES_SHA, None),
            "gamma": (Path("/fixtures/raw-gamma.u16"), GAMMA_SHA, TENSOR_BYTES),
            "hip": ((BASE / "libamdhip64.so.7").resolve(strict=True), HIP_SHA, None),
            "hsa": ((BASE / "libhsa-runtime64.so.1").resolve(strict=True), args.hsa_sha256, None),
            "bridge": (Path("/usr/lib/librocdxg.so"), BRIDGE_SHA, None),
        }
        captured = {}
        for key, (path, wanted, size) in files.items():
            captured[key], report["bindings"][key] = capture(path, wanted, size)
        require(captured["engine"][331776:331776 + 17704408] == captured["codeobject"], "original embedded codeobject differs")
        fixtures = json.loads(captured["fixtures"])
        require([row["label"] for row in fixtures["rows"]] == ["A", "B"], "frozen A/B fixture contract differs")
        inputs = {}
        for row in fixtures["rows"]:
            label = row["label"]
            item = row["files"][label + "-input.u16"]
            require(item["file"] == label + "-input.u16" and item["bytes"] == TENSOR_BYTES, "fixture extent/name differs")
            inputs[label], report["bindings"][label + "_input"] = capture(Path("/fixtures") / item["file"], item["sha256"], TENSOR_BYTES)
        hsa = C.CDLL(report["bindings"]["hsa"]["path"], mode=os.RTLD_NOW | os.RTLD_GLOBAL)
        hip = C.CDLL(report["bindings"]["hip"]["path"], mode=os.RTLD_NOW | os.RTLD_GLOBAL)
        init = api(hip, "hipInit", [C.c_uint])
        count_devices = api(hip, "hipGetDeviceCount", [C.POINTER(C.c_int)])
        set_device = api(hip, "hipSetDevice", [C.c_int])
        alloc = api(hip, "hipMalloc", [C.POINTER(C.c_void_p), C.c_size_t])
        free = api(hip, "hipFree", [C.c_void_p])
        copy = api(hip, "hipMemcpy", [C.c_void_p, C.c_void_p, C.c_size_t, C.c_int])
        synchronize = api(hip, "hipDeviceSynchronize", [])
        load_module = api(hip, "hipModuleLoadData", [C.POINTER(C.c_void_p), C.c_void_p])
        get_function = api(hip, "hipModuleGetFunction", [C.POINTER(C.c_void_p), C.c_void_p, C.c_char_p])
        launch = api(hip, "hipModuleLaunchKernel", [C.c_void_p] + [C.c_uint] * 7 + [C.c_void_p, C.POINTER(C.c_void_p), C.c_void_p])
        unload = api(hip, "hipModuleUnload", [C.c_void_p])
        runtime_version = api(hip, "hipRuntimeGetVersion", [C.POINTER(C.c_int)])
        ok(init(0), "hipInit")
        count = C.c_int()
        ok(count_devices(C.byref(count)), "hipGetDeviceCount")
        require(count.value == 1, "exactly one GPU required")
        ok(set_device(0), "hipSetDevice")
        version = C.c_int()
        ok(runtime_version(C.byref(version)), "hipRuntimeGetVersion")
        code = C.create_string_buffer(captured["codeobject"])
        ok(load_module(C.byref(module), code), "hipModuleLoadData")
        function = C.c_void_p()
        ok(get_function(C.byref(function), module, KERNEL), "hipModuleGetFunction")
        ok(alloc(C.byref(tensor), TENSOR_BYTES), "hipMalloc tensor")
        ok(alloc(C.byref(gamma_device), TENSOR_BYTES), "hipMalloc gamma")
        gamma = C.create_string_buffer(captured["gamma"])
        ok(copy(gamma_device, gamma, TENSOR_BYTES, 1), "raw gamma H2D")
        report["gpu_context"] = dict(initialized=True, device_count=count.value, device_index=0, hip_runtime_version=version.value)
        expected = {"hip": ("libamdhip64.so", HIP_SHA), "hsa": ("libhsa-runtime64.so", args.hsa_sha256), "bridge": ("librocdxg.so", BRIDGE_SHA)}
        report["mapped_before"] = mapped_bindings(expected)
        width, groups = C.c_int32(WIDTH), C.c_int32(1)
        kernel_args = (C.c_void_p * 5)(C.cast(C.byref(tensor), C.c_void_p), C.cast(C.byref(gamma_device), C.c_void_p),
            C.cast(C.byref(tensor), C.c_void_p), C.cast(C.byref(width), C.c_void_p), C.cast(C.byref(groups), C.c_void_p))
        for label in ("A", "B"):
            host_input, host_output = C.create_string_buffer(inputs[label]), C.create_string_buffer(TENSOR_BYTES)
            observed, samples = None, []
            for iteration in range(WARMUP + REPEATS):
                ok(copy(tensor, host_input, TENSOR_BYTES, 1), "frozen input H2D")
                start = time.perf_counter_ns()
                ok(launch(function, 1, 1, 1, 256, 1, 1, 0, None, kernel_args, None), "original RMS launch")
                ok(synchronize(), "original RMS synchronization")
                elapsed = time.perf_counter_ns() - start
                ok(copy(host_output, tensor, TENSOR_BYTES, 2), "RMS result D2H")
                raw = host_output.raw
                require(all((word & 0x7f80) != 0x7f80 for word in struct.unpack("<2560H", raw)), "nonfinite RMS result")
                if observed is None:
                    observed = raw
                require(raw == observed, "fixed replay changed its BF16 output")
                if iteration >= WARMUP:
                    samples.append(elapsed / 1000)
            name = label + "-embedding-rms-u16.bin"
            with (output / name).open("xb") as stream:
                stream.write(observed)
            report["timings"].append(dict(label=label, output_file=name, output_sha256=digest(observed),
                exact_repeat_parity=True, wall_launch_synchronize_us=samples, median_us=statistics.median(samples),
                p95_us=sorted(samples)[int(.95 * (len(samples) - 1))]))
        time.sleep(.25)
        report["idle"].append(idle_bracket("gpu_context_after_fixed_replay"))
        ok(api(hsa, "hsa_init", [])(), "hsa_init owned reference")
        hsa_owned = True
        handler_type = C.CFUNCTYPE(C.c_bool, C.c_int64, C.c_void_p)

        def on_signal(value, ignored):
            callback_times_ns.append(time.perf_counter_ns())
            callback_values.append(int(value))
            callback_done.set()
            return False

        callback = handler_type(on_signal)
        # IPC=2 permits CPU consumption and guarantees DefaultSignal/BusyWaitSignal
        # at this SDK source pin. This is an explicit diagnostic, not engine IPC.
        create_signal = api(hsa, "hsa_amd_signal_create", [C.c_int64, C.c_uint32, C.c_void_p, C.c_uint64, C.POINTER(Signal)])
        register_handler = api(hsa, "hsa_amd_signal_async_handler", [Signal, C.c_int, C.c_int64, handler_type, C.c_void_p])
        ok(create_signal(1, 0, None, 2, C.byref(signal)), "hsa_amd_signal_create IPC")
        value_pointer = C.POINTER(C.c_int64)()
        get_value_pointer = api(hsa, "hsa_amd_signal_value_pointer", [Signal, C.POINTER(C.POINTER(C.c_int64))])
        ok(get_value_pointer(signal, C.byref(value_pointer)), "BusyWaitSignal public type check")
        require(bool(value_pointer), "BusyWaitSignal public type check returned null")
        ok(register_handler(signal, 0, 0, callback, None), "pending EQ0 async handler")
        handler_registered = True
        time.sleep(.25)
        require(not callback_values, "pending signal fired before completion")
        report["idle"].append(idle_bracket("one_pending_ipc_async_signal_diagnostic"))
        require(not callback_values, "pending signal fired during idle bracket")
        start = time.perf_counter_ns()
        api(hsa, "hsa_signal_store_screlease", [Signal, C.c_int64], None)(signal, 0)
        require(callback_done.wait(2), "async callback did not complete")
        report["async_signal"] = dict(initial_value=1, condition="EQ0", attributes=2,
            callback_values=list(callback_values), python_observed_wake_us=(callback_times_ns[0] - start) / 1000,
            busy_wait_public_type_check=True, signal_value_pointer_dereferenced=False,
            same_process_ipc_signal_diagnostic=True,
            polling_path_deliberately_exercised=True, latency_is_single_observation=True)
        require(callback_values == [0], "unexpected async callback value/count")
        report["mapped_after"] = mapped_bindings(expected)
        require(report["mapped_after"] == report["mapped_before"], "loaded runtime identities changed")
        for key, (path, wanted, size) in files.items():
            capture(path, wanted, size)
        report["passed"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        actions = []
        if hsa is not None and signal.handle:
            if handler_registered and not callback_done.is_set():
                try:
                    api(hsa, "hsa_signal_store_screlease", [Signal, C.c_int64], None)(signal, 0)
                    require(callback_done.wait(2), "cleanup async callback did not complete")
                except Exception as error:
                    report["cleanup_errors"].append(str(error))
            actions.append(("hsa_signal_destroy", lambda: api(hsa, "hsa_signal_destroy", [Signal])(signal)))
        if hip is not None:
            if tensor.value:
                actions.append(("hipFree tensor", lambda: api(hip, "hipFree", [C.c_void_p])(tensor)))
            if gamma_device.value:
                actions.append(("hipFree gamma", lambda: api(hip, "hipFree", [C.c_void_p])(gamma_device)))
            if module.value:
                actions.append(("hipModuleUnload", lambda: api(hip, "hipModuleUnload", [C.c_void_p])(module)))
        if hsa_owned:
            actions.append(("hsa_shut_down owned reference", lambda: api(hsa, "hsa_shut_down", [])()))
        for label, action in actions:
            try:
                ok(action(), label)
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        report["passed"] = report["passed"] and not report["cleanup_errors"]
        try:
            write_json(output / "probe.json", report)
        except Exception as error:
            report["passed"] = False
            report["report_write_error"] = type(error).__name__ + ": " + str(error)
            print(json.dumps(report), file=sys.stderr, flush=True)
    print(json.dumps(dict(passed=report["passed"], variant=args.variant, error=report.get("error"),
        cleanup_errors=report["cleanup_errors"], report_write_error=report.get("report_write_error"), output=str(output))))
    return 0 if report["passed"] else 1


def compare(args):
    reports = [json.loads(Path(path).read_text()) for path in (args.stock, args.candidate)]
    stock, candidate = reports
    require(stock.get("variant") in ("stock", "source_stock") and candidate.get("variant") == "candidate" and
            all(row.get("passed") for row in reports), "two passed baseline/candidate reports required")
    for key in ("schema", "image", "environment", "warmup_per_fixture", "repeats_per_fixture", "tensor_bytes", "kernel_symbol", "width", "groups", "grid", "block", "shared_bytes", "input_output_alias"):
        require(stock[key] == candidate[key], "comparison configuration differs: " + key)
    for key in ("source", "engine", "codeobject", "fixtures", "gamma", "hip", "bridge", "A_input", "B_input"):
        require(stock["bindings"][key] == candidate["bindings"][key], "comparison input differs: " + key)
    baseline_sha = stock["bindings"]["hsa"]["sha256"]
    if stock["variant"] == "stock":
        require(baseline_sha == STOCK_HSA_SHA, "installed stock provenance differs")
    require(candidate["bindings"]["hsa"]["sha256"] != baseline_sha, "candidate runtime is unchanged baseline")
    rows = []
    for baseline, changed in zip(stock["timings"], candidate["timings"]):
        require(baseline["label"] == changed["label"], "fixture order differs")
        require(baseline["output_sha256"] == changed["output_sha256"], "stock/candidate BF16 parity differs")
        for root, row in zip((Path(args.stock).parent, Path(args.candidate).parent), (baseline, changed)):
            raw = (root / row["output_file"]).read_bytes()
            require(len(raw) == TENSOR_BYTES and digest(raw) == row["output_sha256"], "retained output binding differs")
        rows.append(dict(label=baseline["label"], exact_bf16_parity=True,
            stock_median_us=baseline["median_us"], candidate_median_us=changed["median_us"],
            candidate_over_stock=changed["median_us"] / baseline["median_us"],
            stock_p95_us=baseline["p95_us"], candidate_p95_us=changed["p95_us"]))
    idle = []
    for baseline, changed in zip(stock["idle"], candidate["idle"]):
        require(baseline["label"] == changed["label"] and baseline["requested_seconds"] == changed["requested_seconds"], "idle bracket differs")
        idle.append(dict(label=baseline["label"], stock_mean_cpu_cores=baseline["mean_process_cpu_cores"],
            candidate_mean_cpu_cores=changed["mean_process_cpu_cores"]))
    result = dict(schema="halogen.rocr-poll-backoff-component-comparison.v1", exact_bf16_parity=True,
        baseline_variant=stock["variant"],
        comparison_scope=("source-built unpatched control versus source-built candidate; matching outer build metadata required"
                          if stock["variant"] == "source_stock" else "installed stock versus whole candidate build; patch effect not isolated"),
        runtime_sha256=dict(stock=baseline_sha, candidate=candidate["bindings"]["hsa"]["sha256"]),
        timings=rows, idle=idle, single_python_observed_wake_us=dict(stock=stock["async_signal"]["python_observed_wake_us"],
            candidate=candidate["async_signal"]["python_observed_wake_us"]),
        component_only=True, token_rate_claim=False, acceptance_claim=False, adoption_decision_required=True)
    write_json(args.output, result)
    print(json.dumps(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("probe")
    run.add_argument("--variant", choices=("stock", "source_stock", "candidate"), required=True)
    run.add_argument("--source-sha256", required=True)
    run.add_argument("--hsa-sha256", required=True)
    run.add_argument("--output", default="/result")
    run.add_argument("--outer-owned-gpu-guard", action="store_true")
    check = commands.add_parser("compare")
    check.add_argument("--stock", required=True)
    check.add_argument("--candidate", required=True)
    check.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    return probe(args) if args.command == "probe" else compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
