"""Bounded Linux CPU frame-relay qualifier; no engine, GPU or NPU access."""
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path: Path) -> str:
    resolved = path.resolve()
    if resolved.drive.upper() != "C:":
        raise ValueError("This local launcher only maps the known C workspace")
    return "/mnt/c/" + resolved.as_posix()[3:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-receipt", type=Path)
    parser.add_argument("--receipt-sha256")
    args = parser.parse_args()
    if bool(args.execute_receipt) != bool(args.receipt_sha256):
        parser.error("Execution requires both frozen build receipt and its hash")
    if os.name != "nt":
        raise RuntimeError("Local Windows ownership is required")
    helpers = {
        REPO / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
        REPO / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c",
    }
    sources = [HERE / name for name in (
        "native_frame_relay.h", "native_frame_relay.S", "native_frame_config.cpp",
        "native_frame_harness.cpp", "native_frame_harness.S")]
    pins = {path: digest(path) for path in [*sources, Path(__file__).resolve(), *helpers]}
    for path, expected in helpers.items():
        if pins[path] != expected:
            raise RuntimeError("Reviewed ownership or memory helper changed")
    from host_frames import frame
    from winjob import OwnedProcess
    work = HERE / "_artifacts" / (time.strftime("%Y%m%d-%H%M%S") + "-native-frame-" + uuid.uuid4().hex[:8])
    work.mkdir(parents=True, exist_ok=False)
    executable = work / "native-frame-harness"
    result = dict(work=str(work), source_pins={str(k): v for k, v in pins.items()},
        stages=[], errors=[], minimum_memory=None, maximum_sample_gap_seconds=0.0,
        linux_cpu_only=True, native_engine_loaded=False, server_changed=False,
        GPU_NPU_executed=False, serving_gain_qualified=False,
        harness_launch_requested=False, harness_executed=None,
        ownership_scope="Windows jobs/handles plus finite Linux timeout process group; no escaping-descendant or external-cancellation closure proof")
    pending = []

    def verify():
        for path, expected in pins.items():
            if digest(path) != expected:
                raise RuntimeError("Frozen source changed: " + str(path))

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
        # Linux timeout bounds its child and the same process group. Escaping
        # descendants/monitor death/external WSL cancellation are not covered;
        # this reviewed CPU harness/compiler has no such intended behavior.
        command = [r"C:\Windows\System32\wsl.exe", "-d", "Ubuntu-24.04", "-u", "revn",
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
            if label == "harness":
                result["harness_launch_requested"] = True
            last = time.monotonic()
            while True:
                sample(18)
                now = time.monotonic()
                result["maximum_sample_gap_seconds"] = max(result["maximum_sample_gap_seconds"], now - last)
                last = now
                if child.wait(250):
                    sample(18)
                    result["maximum_sample_gap_seconds"] = max(result["maximum_sample_gap_seconds"], time.monotonic() - last)
                    row["exit_code"] = child.exit_code()
                    break
                if now - started > seconds + 10:
                    raise TimeoutError("Finite Linux stage did not report termination")
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
        if args.execute_receipt:
            prior_path = args.execute_receipt.resolve(strict=True)
            if not prior_path.is_relative_to(HERE / "_artifacts") or digest(prior_path) != args.receipt_sha256:
                raise ValueError("Reviewed build receipt path/hash mismatch")
            prior = json.loads(prior_path.read_bytes())
            if not prior.get("build_passed") or not prior.get("passed") or prior.get("harness_executed"):
                raise ValueError("A completed, unexecuted build is required")
            if prior["source_pins"] != result["source_pins"] or not prior["all_owned_jobs_closed"]:
                raise ValueError("Frozen build source or job receipt mismatch")
            executable = Path(prior["executable"]["path"]).resolve(strict=True)
            if not executable.is_relative_to(HERE / "_artifacts") or digest(executable) != prior["executable"]["sha256"]:
                raise ValueError("Reviewed executable path/hash mismatch")
            result["reviewed_build"] = dict(path=str(prior_path), sha256=args.receipt_sha256)
            result["executable"] = prior["executable"]
            run("harness", [linux(executable)], 10)
            result["harness_executed"] = True
        else:
            run("tool-hashes", ["/usr/bin/sha256sum", "/usr/bin/g++", "/usr/bin/timeout",
                "/usr/bin/env", "/usr/bin/objdump", "/usr/bin/readelf"], 5)
            run("compile", ["/usr/bin/g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fno-exceptions", "-fno-rtti", "-fno-omit-frame-pointer", "-fstack-usage",
                "-fcf-protection=full", "-pthread", *[linux(p) for p in sources[1:]],
                "-Wl,-z,relro,-z,now", "-o", linux(executable)], 45)
            result["executable"] = dict(path=str(executable), sha256=digest(executable))
            run("instructions", ["/usr/bin/objdump", "-d", "-w", "-Mintel", linux(executable)], 5)
            run("frames", ["/usr/bin/readelf", "--debug-dump=frames", "--wide", linux(executable)], 5)
            run("elf", ["/usr/bin/readelf", "-h", "-l", "-s", "-d", "-n", "--wide", linux(executable)], 5)
            result["build_passed"] = True
            result["harness_executed"] = False
    except BaseException as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    for child, row in pending:
        try:
            child.close()
            row["owned_job_closed"] = True
        except BaseException as error:
            result["errors"].append("Owned cleanup unconfirmed: " + str(error))
    result["all_owned_jobs_closed"] = bool(result["stages"]) and all(r["owned_job_closed"] for r in result["stages"])
    result["all_owned_jobs_closed_scope"] = "Retained Windows jobs/handles only"
    result["passed"] = not result["errors"]
    receipt = work / "result.json"
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(result=str(receipt), passed=result["passed"], errors=result["errors"])))
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
