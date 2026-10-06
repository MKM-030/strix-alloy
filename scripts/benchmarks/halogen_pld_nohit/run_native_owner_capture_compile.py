"""Compile only the frozen native owner adapter; no harness or serving entry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "server"))

SOURCE_PINS = {
    "native_owner_capture.h": "649c202063f572a574622ea133b67822c02c78312686b24de8d57c268dfcf87f",
    "native_owner_capture.cpp": "e7e1ce7399e41a9327530b1b635caae6fe14a458516d7c6836948008ef6cfcdf",
    "native_capture_layout.h": "e7ce7302eb98cfa09a2c7ee2b1747e8c2a88d4311de0dfbdf10a5a03ab7eee1a",
    "native_outcome_handoff.h": "5d4a42ad70edb14ae30f6c3043db4d889565031ef449de4ede9d6ce74536f835",
    "native_frame_relay.h": "f6aaf827d5187a3eb47bda94bf9f19d6eae29664251ede96c29b7d84e9c74cbe",
    "seam_contract.h": "caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2",
    "NATIVE_OWNER_CAPTURE.md": "63df9530b2be1c5c6b508c84ab5549b8068a3b99aa1e5c14e197af7f69ce13cc",
    "NATIVE_OWNER_CAPTURE_REVIEW.md": "6ac5a97953b9f426f0675dac3dae300db78e2b699af25eb6dae93df0b605af4c",
}
HELPER_PINS = {
    REPO / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    REPO / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path: Path) -> str:
    resolved = path.resolve()
    if resolved.drive.upper() != "C:":
        raise ValueError("This local launcher only maps the known C workspace")
    return "/mnt/c/" + resolved.as_posix()[3:]


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    if os.name != "nt":
        raise RuntimeError("Local Windows ownership is required")
    expected_pins = {HERE / name: value for name, value in SOURCE_PINS.items()}
    expected_pins.update(HELPER_PINS)
    for path, expected in expected_pins.items():
        if digest(path) != expected:
            raise RuntimeError("Frozen source/helper changed: " + str(path))
    launcher = Path(r"C:\Windows\System32\wsl.exe")
    pins = dict(expected_pins)
    pins[Path(__file__).resolve()] = digest(Path(__file__).resolve())
    pins[launcher] = digest(launcher)
    from host_frames import frame
    from winjob import OwnedProcess

    work = HERE / "_artifacts" / (
        time.strftime("%Y%m%d-%H%M%S") + "-native-owner-compile-" + uuid.uuid4().hex[:8])
    work.mkdir(parents=True, exist_ok=False)
    work = work.resolve()
    if not work.is_relative_to(HERE / "_artifacts"):
        raise RuntimeError("Compile artifact path escaped the owned directory")
    object_file = work / "native-owner-capture.o"
    stack_usage = work / "native-owner-capture.su"
    result = dict(
        work=str(work), source_pins={str(k): v for k, v in pins.items()},
        stages=[], errors=[], minimum_memory=None, maximum_sample_gap_seconds=0.0,
        initial_reserve_bytes=22 * 1024**3, continuous_reserve_bytes=18 * 1024**3,
        compile_only=True, compile_passed=False, compiler_executed=False,
        wsl_executed=False, native_entry_executed=False, harness_executed=False,
        native_engine_loaded=False, server_changed=False, GPU_NPU_executed=False,
        serving_gain_qualified=False, cpu_capture_cost=None, GPU_NPU_readiness=None,
        device_placement=None, prefill_tps=None, decode_tps=None,
        native_acceptance=None, serving_gain=None,
        ownership_scope="Retained Windows jobs/handles plus finite Linux timeout process group; no escaping-descendant or external-cancellation closure proof",
        verification_scope="Compilation of native_owner_capture.cpp only; no link, callback, native capture, lifetime/prefix proof or runtime qualification")
    pending = []

    def verify():
        for path, expected in pins.items():
            if digest(path) != expected:
                raise RuntimeError("Frozen input changed: " + str(path))

    def sample(floor_gib: int):
        observed = frame()
        if result["minimum_memory"] is None:
            result["minimum_memory"] = dict(observed)
        else:
            for key in ("available_bytes", "commit_headroom_bytes"):
                result["minimum_memory"][key] = min(result["minimum_memory"][key], observed[key])
        if min(observed["available_bytes"], observed["commit_headroom_bytes"]) < floor_gib * 1024**3:
            raise RuntimeError("Physical/commit reserve below " + str(floor_gib) + " GiB")

    def run(label: str, argv: list[str], seconds: int):
        verify()
        sample(22)
        command = [str(launcher), "-d", "Ubuntu-24.04", "-u", "revn",
            "--cd", linux(work), "--exec", "/usr/bin/timeout", "--signal=TERM",
            "--kill-after=2s", str(seconds) + "s", "/usr/bin/env",
            "-u", "LD_PRELOAD", "-u", "LD_LIBRARY_PATH", "-u", "LIBRARY_PATH",
            "-u", "CPATH", "-u", "CPLUS_INCLUDE_PATH", "-u", "C_INCLUDE_PATH",
            "-u", "GCC_EXEC_PREFIX", "-u", "COMPILER_PATH", *argv]
        row = dict(label=label, command=command, exit_code=None, owned_job_closed=False)
        result["stages"].append(row)
        child = None
        started = time.monotonic()
        try:
            environment = dict(os.environ)
            environment.update(TEMP=str(work), TMP=str(work))
            for key in tuple(environment):
                if key.upper() in ("WSLENV", "LD_PRELOAD", "LD_LIBRARY_PATH"):
                    del environment[key]
            child = OwnedProcess(command, cwd=work, env=environment,
                stdout_path=work / (label + ".stdout.txt"),
                stderr_path=work / (label + ".stderr.txt"))
            row["identity"] = child.identity
            sample(22)
            child.verify_live_identity()
            child.resume()
            row["windows_child_resumed"] = True
            result["wsl_executed"] = True
            if label == "compile":
                result["compiler_executed"] = True
            last = time.monotonic()
            while True:
                sample(18)
                now = time.monotonic()
                result["maximum_sample_gap_seconds"] = max(result["maximum_sample_gap_seconds"], now - last)
                last = now
                if child.wait(250):
                    sample(18)
                    result["maximum_sample_gap_seconds"] = max(
                        result["maximum_sample_gap_seconds"], time.monotonic() - last)
                    row["exit_code"] = child.exit_code()
                    break
                if now - started > seconds + 10:
                    raise TimeoutError("Finite compile stage did not report termination")
            if row["exit_code"] != 0:
                raise RuntimeError(label + " failed: " + str(row["exit_code"]))
        except BaseException as error:
            if child is None:
                child = getattr(error, "owner", None)
                if child is not None:
                    row["identity"] = child.identity
            raise
        finally:
            if child is not None:
                try:
                    child.close()
                    row["owned_job_closed"] = True
                except BaseException:
                    pending.append((child, row))
                    raise
            row["elapsed_seconds"] = time.monotonic() - started
        verify()

    try:
        run("tool-hashes", ["/usr/bin/sha256sum", "/usr/bin/g++",
            "/usr/bin/timeout", "/usr/bin/env"], 5)
        run("compile", ["/usr/bin/g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
            "-fno-exceptions", "-fno-rtti", "-fstack-usage", "-c",
            linux(HERE / "native_owner_capture.cpp"), "-o", linux(object_file)], 45)
        result["object"] = dict(path=str(object_file), sha256=digest(object_file))
        result["stack_usage"] = dict(path=str(stack_usage), sha256=digest(stack_usage))
        result["compile_passed"] = True
    except BaseException as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    for child, row in pending:
        try:
            child.close()
            row["owned_job_closed"] = True
        except BaseException as error:
            result["errors"].append("Owned cleanup unconfirmed: " + str(error))
    result["all_owned_jobs_closed"] = bool(result["stages"]) and all(
        row["owned_job_closed"] for row in result["stages"])
    result["all_owned_jobs_closed_scope"] = "Retained Windows jobs/handles only"
    result["passed"] = result["compile_passed"] and result["all_owned_jobs_closed"] and not result["errors"]
    receipt = work / "result.json"
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(result=str(receipt), passed=result["passed"], errors=result["errors"])))
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
