"""Root-owned real expert0 FC admission through ordinary DD C++ APIs.

No ONNX/provider registration, binary modification, checkpoint read or model
benchmark. A parent OwnedProcess guard enforces exclusive hardware admission,
22/18 GiB reserves, the fixed configuration and a bounded child lifetime.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time


class Receipt(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "schema", "size", "stage", "fc_index", "calls_completed", "output_valid",
        "logical_k", "logical_n", "kernel_k", "kernel_n")]
    _fields_ += [(name, ctypes.c_uint64) for name in (
        "packed_bytes", "input_bo_bytes", "output_bo_bytes")]
    _fields_ += [(name, ctypes.c_int64) for name in (
        "qpc_frequency", "qpc_start", "qpc_end")]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def module_path(name):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    handle = kernel.GetModuleHandleW(name)
    if not handle:
        return None
    output = ctypes.create_unicode_buffer(32768)
    require(kernel.GetModuleFileNameW(handle, output, len(output)), "Loaded module path unavailable")
    return str(Path(output.value).resolve(strict=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-owned-admission", action="store_true")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-config-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(args.root_owned_admission and os.name == "nt", "Root-owned Windows child required")
    require(sha(args.config) == args.expected_config_sha256, "Pinned configuration changed")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    require(sha(Path(__file__)) == config["probe_sha256"], "Pinned child source changed")
    require(sha(sys.executable) == config["python_sha256"], "Pinned interpreter changed")
    require(not args.report.exists() and args.report.parent.is_dir(), "Fresh report required")
    require(ctypes.sizeof(Receipt) == 88 and Receipt.qpc_frequency.offset == 64, "Receipt ABI changed")
    for path, expected in config["file_pins"].items():
        require(sha(path) == expected, "Pinned dependency changed: " + path)
    expected_fixtures = [(0, 2560, 1280, 4198400), (1, 640, 2560, 1597440)]
    require([(fc["index"], fc["k"], fc["n"], fc["bytes"]) for fc in config["fixtures"]]
            == expected_fixtures, "Fixed FC fixture geometry differs")
    for fc in config["fixtures"]:
        require(Path(fc["path"]).stat().st_size == fc["bytes"], "Fixed FC fixture extent differs")
    require(config.get("tolerance") == {"rtol": .03, "atol": .003}, "Frozen arithmetic tolerance changed")
    preparation_path = Path(config["real_preparation_report"])
    require(sha(preparation_path) == config["real_preparation_sha256"], "Pinned real preparation changed")
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    require(preparation.get("passed") is True and preparation.get("expert") == 0
            and preparation.get("completed_experts") == 1
            and preparation.get("schema") == "halogen_real_expert_fc_preparation_v1", "Qualified expert0 fixture receipt required")
    require(config["fixtures"] == preparation["fixtures"], "Real fixture configuration differs from sealed preparation")
    for path, expected in preparation["file_pins"].items():
        require(config["file_pins"].get(path) == expected and sha(path) == expected, "Real fixture pin differs: " + path)
    import numpy as np

    def saved(path, dtype, elements):
        value = np.load(path, allow_pickle=False)
        require(value.dtype == np.dtype(dtype) and value.shape == (elements,) and value.flags.c_contiguous,
                "Exact saved reference/input geometry required")
        require(np.isfinite(value).all(), "Finite saved input/reference required")
        return value

    def metrics(actual, expected):
        a, b = actual.astype(np.float64), expected.astype(np.float64)
        error = a - b
        permitted = .003 + .03 * np.abs(b)
        denominator = float(np.square(b).sum())
        return dict(max_abs_error=float(np.abs(error).max()),
                    rmse=float(np.sqrt(np.square(error).mean())),
                    relative_l2_error=float(np.sqrt(np.square(error).sum() / denominator)) if denominator else 0.0,
                    violating_elements=int(np.count_nonzero(np.abs(error) > permitted)),
                    tolerance={"rtol": .03, "atol": .003},
                    passed=bool(np.isfinite(a).all() and np.all(np.abs(error) <= permitted)))

    result = dict(schema=1, passed=False, stage="validated", scope="real approximate v2 layer48 expert0 FC arithmetic only",
                  full_mtp_proven=False, acceptance_qualified=False, speed_gain_established=False,
                  expert=0, approximate_quantization=True, router_semantics_verified=False, activation_semantics_verified=False,
                  calls=[], contexts=[], native_fault_counters=None, cleanup_errors=[])
    directories = []
    library = collector = None
    armed = False
    native_fault = False
    handle = ctypes.c_void_p()

    def checkpoint(stage):
        result["stage"] = stage
        print("DD_OWNED_STAGE " + stage, flush=True)

    def check_loaded():
        observed = {}
        for name, expected in config["expected_loaded_modules"].items():
            observed[name] = module_path(name)
            require(observed[name] and Path(observed[name]) == Path(expected).resolve(strict=True),
                    "Unexpected loaded module: " + name)
        for name, expected in config["optional_loaded_modules"].items():
            observed[name] = module_path(name)
            require(observed[name] is None or Path(observed[name]) == Path(expected).resolve(strict=True),
                    "Unexpected optional loaded module: " + name)
        result["loaded_modules"] = observed

    def invoke_native(function, *values):
        nonlocal native_fault
        try:
            return function(*values)
        except OSError:
            native_fault = True
            result["native_call_faulted"] = True
            raise

    def release_handle():
        nonlocal handle
        detached = ctypes.c_void_p(handle.value)
        handle = ctypes.c_void_p()
        invoke_native(library.halogen_dd_owned_fc_destroy, detached)

    try:
        for directory in config["dll_directories"]:
            directories.append(os.add_dll_directory(directory))
        collector = ctypes.CDLL(config["collector_library"])
        collector.start_capture.argtypes = [ctypes.c_wchar_p]
        collector.start_capture.restype = ctypes.c_uint32
        collector.refresh_capture.argtypes = []
        collector.refresh_capture.restype = ctypes.c_uint32
        collector.stop_capture.argtypes = []
        collector.stop_capture.restype = ctypes.c_uint32
        require(collector.start_capture(str(args.report.parent / "native-fault.jsonl")) == 0,
                "Fault collector arm failed")
        armed = True
        checkpoint("load_public_client")
        library = ctypes.CDLL(config["native_library"])
        create = library.halogen_dd_owned_fc_create
        create.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64,
                           ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(Receipt),
                           ctypes.c_void_p, ctypes.c_uint32]
        create.restype = ctypes.c_int
        run = library.halogen_dd_owned_fc_run
        run.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(Receipt),
                        ctypes.c_void_p, ctypes.c_uint32]
        run.restype = ctypes.c_int
        destroy = library.halogen_dd_owned_fc_destroy
        destroy.argtypes = [ctypes.c_void_p]
        destroy.restype = None
        check_loaded()
        for fc in config["fixtures"]:
            require(fc["index"] in (0, 1), "Unexpected FC fixture")
            packed = ctypes.create_string_buffer(Path(fc["path"]).read_bytes())
            require(len(packed.raw) - 1 == fc["bytes"], "Packed FC extent differs")
            receipt, error = Receipt(), ctypes.create_string_buffer(4096)
            require(collector.refresh_capture() == 0, "Pre-create module refresh failed")
            checkpoint("fc" + str(fc["index"]) + "_create")
            started = time.perf_counter_ns()
            code = invoke_native(create, fc["index"], packed, fc["bytes"], ctypes.byref(handle),
                          ctypes.byref(receipt), error, len(error))
            row = dict(fc_index=fc["index"], create_code=code,
                       create_host_ms=(time.perf_counter_ns() - started) / 1e6,
                       create_receipt={name: getattr(receipt, name) for name, _ in Receipt._fields_},
                       create_error=error.value.decode("utf-8", errors="replace"))
            result["contexts"].append(row)
            require(code == 0 and handle.value and receipt.schema == 1 and receipt.size == 88,
                    "Public FC creation failed: " + row["create_error"])
            check_loaded()
            for call in range(2):
                require(fc.get("expert") == 0 and fc.get("synthetic") is False and len(fc["cases"]) == 2,
                        "Exactly two real expert0 cases required")
                case = fc["cases"][call]
                require(case["call"] == call, "Fixed call order differs")
                input_array = saved(case["input_path"], "<u2", fc["k"])
                affine_reference = saved(case["affine_reference_path"], "<f4", fc["n"])
                decoded_reference = saved(case["decoded_reference_path"], "<f4", fc["n"])
                require(np.any(affine_reference != 0), "Nonzero real arithmetic reference required")
                input_words = (ctypes.c_uint16 * fc["k"]).from_buffer_copy(input_array.tobytes())
                output = (ctypes.c_uint16 * fc["n"])(*([0x7fc1] * fc["n"]))
                require(collector.refresh_capture() == 0, "Pre-call module refresh failed")
                checkpoint("fc" + str(fc["index"]) + "_call" + str(call))
                try:
                    code = invoke_native(run, handle, input_words, fc["k"], output, fc["n"],
                               ctypes.byref(receipt), error, len(error))
                finally:
                    raw = bytes(output)
                    raw_path = args.report.parent / f"fc{fc['index']}.call{call}.output-bf16.bin"
                    with raw_path.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    result.setdefault("raw_outputs", []).append(dict(fc_index=fc["index"], call=call,
                        path=str(raw_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                        native_call_faulted=native_fault))
                native = {name: getattr(receipt, name) for name, _ in Receipt._fields_}
                actual = (np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16).view(np.float32)
                finite = bool(np.isfinite(actual).all())
                affine_comparison = metrics(actual, affine_reference) if finite else {"passed": False, "nonfinite_elements": int(np.count_nonzero(~np.isfinite(actual)))}
                decoded_comparison = metrics(actual, decoded_reference) if finite else {"passed": False}
                execution_ok = (code == 0 and receipt.stage == 4 and receipt.output_valid == 1
                                and receipt.calls_completed == call + 1 and receipt.qpc_frequency > 0
                                and receipt.qpc_end >= receipt.qpc_start)
                valid = execution_ok and affine_comparison["passed"]
                result["calls"].append(dict(fc_index=fc["index"], call=call, passed=valid, execution_ok=execution_ok,
                    receipt=native, error=error.value.decode("utf-8", errors="replace"),
                    output_sha256=hashlib.sha256(raw).hexdigest(), output_path=str(raw_path),
                    affine_reference_comparison=affine_comparison,
                    decoded_true_fp32_comparison=decoded_comparison,
                    approximate_int4_cpu_error=case["approximation_output_error"],
                    row_layout=fc["row_layout"],
                    completed_call_ms=(receipt.qpc_end - receipt.qpc_start) * 1000 / receipt.qpc_frequency
                    if valid else None))
                require(execution_ok, "Public real FC execution receipt failed")
                check_loaded()
            checkpoint("fc" + str(fc["index"]) + "_destroy")
            release_handle()
            row["destroy_returned"] = True
        require(len(result["calls"]) == 4, "Incomplete real expert0 FC admission")
        result["passed"] = all(row["passed"] for row in result["calls"])
        if not result["passed"]:
            result.update(error="Public real FC failed frozen affine arithmetic tolerance",
                          failed_at_stage="arithmetic_comparison")
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["failed_at_stage"] = result["stage"]
    finally:
        if handle.value and library is not None and not native_fault:
            try:
                release_handle()
                result["error_path_destroy_returned"] = True
            except Exception as exc:
                result["cleanup_errors"].append("destroy: " + str(exc))
        if native_fault:
            result["dd_cleanup_skipped_after_native_fault"] = True
        if library is not None:
            try:
                check_loaded()
            except Exception as exc:
                result["cleanup_errors"].append("loaded module verification: " + str(exc))
        if armed:
            try:
                require(collector.stop_capture() == 0, "Fault collector stop failed")
                result["collector_stopped"] = True
            except Exception as exc:
                result["cleanup_errors"].append("collector: " + str(exc))
        for directory in reversed(directories):
            directory.close()
        if result["cleanup_errors"]:
            result["passed"] = False
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(result, indent=2), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
