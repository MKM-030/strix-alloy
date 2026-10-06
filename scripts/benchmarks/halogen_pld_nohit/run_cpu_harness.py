"""Finite Windows host-only build/test with owned children and reserve guards."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
GIB = 1024 ** 3
INITIAL_RESERVE = 22 * GIB
CONTINUOUS_RESERVE = 18 * GIB
VCVARS = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
CL = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load reviewed host-only helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("red", "green"), default="green")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("this bounded launcher requires Windows")
    if digest(REPO / "server" / "winjob.py") != "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c":
        raise RuntimeError("reviewed Windows ownership helper changed")
    if digest(REPO / "server" / "host_frames.py") != "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8":
        raise RuntimeError("reviewed host memory helper changed")
    if digest(VCVARS) != "6b516d8fcf543c14b2d861e1f45661e0029230fe0dc48e86ce78522801822209":
        raise RuntimeError("reviewed MSVC environment setup changed")
    host = load_module("nohit_host_frames", REPO / "server" / "host_frames.py")
    owned = load_module("nohit_winjob", REPO / "server" / "winjob.py")
    work = ROOT / "_artifacts" / (time.strftime("%Y%m%d-%H%M%S") + "-" + args.phase + "-" + uuid.uuid4().hex[:8])
    work.mkdir(parents=True, exist_ok=False)
    work = work.resolve()
    if not work.is_relative_to(ROOT):
        raise RuntimeError("artifact path escaped contract directory")
    result = dict(phase=args.phase, expected_harness_exit=1 if args.phase == "red" else 0,
                  expectation_met=False, host_cpu_harness_executed=False,
                  gpu_npu_executed=False, wsl_executed=False,
                  native_engine_loaded=False, work=str(work), children=[], errors=[],
                  minimum_memory=None, maximum_sample_gap_seconds=0.0,
                  initial_reserve_bytes=INITIAL_RESERVE,
                  continuous_reserve_bytes=CONTINUOUS_RESERVE)
    result["pins"] = [dict(path=str(path), sha256=digest(path)) for path in
        (ROOT / "seam_contract.h", ROOT / "seam_contract.cpp", ROOT / "contract_harness.cpp",
         Path(__file__).resolve(), REPO / "server" / "host_frames.py",
         REPO / "server" / "winjob.py", VCVARS, CL)]
    pending_cleanup = []  # Retain only our own handles if a close needs retry.

    def sample(required: int):
        memory = host.frame()
        if result["minimum_memory"] is None:
            result["minimum_memory"] = dict(memory)
        else:
            for key in ("available_bytes", "commit_headroom_bytes"):
                result["minimum_memory"][key] = min(result["minimum_memory"][key], memory[key])
        if min(memory["available_bytes"], memory["commit_headroom_bytes"]) < required:
            raise RuntimeError("host physical/commit reserve below required threshold")
        return memory

    def run_child(label: str, argv: list[str], deadline_seconds: float):
        sample(INITIAL_RESERVE)
        environment = dict(os.environ)
        environment.update(TEMP=str(work), TMP=str(work))
        # CL/LINK environment options must not inject unrelated includes/libraries.
        for key in tuple(environment):
            if key.upper() in ("CL", "_CL_", "LINK", "_LINK_"):
                del environment[key]
        child_record = dict(label=label, owned_job_closed=False, exit_code=None)
        result["children"].append(child_record)
        child = None
        started = time.monotonic()
        try:
            child = owned.OwnedProcess(argv, cwd=work, env=environment,
                stdout_path=work / (label + ".stdout.txt"),
                stderr_path=work / (label + ".stderr.txt"))
            child_record["identity"] = child.identity
            sample(INITIAL_RESERVE)
            child.resume()
            last_sample = time.monotonic()
            while True:
                sample(CONTINUOUS_RESERVE)
                now = time.monotonic()
                result["maximum_sample_gap_seconds"] = max(result["maximum_sample_gap_seconds"], now - last_sample)
                last_sample = now
                if now - started > deadline_seconds:
                    raise TimeoutError(label + " exceeded finite deadline")
                if child.wait(250):
                    sample(CONTINUOUS_RESERVE)
                    result["maximum_sample_gap_seconds"] = max(
                        result["maximum_sample_gap_seconds"], time.monotonic() - last_sample)
                    child_record["exit_code"] = child.exit_code()
                    return child_record["exit_code"]
        except BaseException as error:
            if child is None:
                child = getattr(error, "owner", None)
                if child is not None:
                    child_record["recovery_owner_attached"] = True
                    child_record["identity"] = child.identity
            raise
        finally:
            if child is not None:
                try:
                    child.close()
                    child_record["owned_job_closed"] = True
                except BaseException:
                    pending_cleanup.append((child, child_record))
                    raise
            child_record["elapsed_seconds"] = time.monotonic() - started

    try:
        executable = work / "nohit-contract.exe"
        compile_args = [str(CL), "/nologo", "/std:c++20", "/W4", "/WX", "/EHsc", "/O2", "/MT",
            str(ROOT / "seam_contract.cpp"), str(ROOT / "contract_harness.cpp"),
            "/Fo" + str(work) + "\\", "/Fe" + str(executable),
            "/Fd" + str(work / "compiler.pdb"), "/link", "/INCREMENTAL:NO"]
        command_file = work / "compile.cmd"
        command_file.write_text("@echo off\ncall \"" + str(VCVARS) + "\" >nul\n"
            "if errorlevel 1 exit /b 2\n" + subprocess.list2cmdline(compile_args) + "\n"
            "exit /b %errorlevel%\n", encoding="utf-8")
        command_shell = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
        code = run_child("compile", [str(command_shell), "/d", "/s", "/c", str(command_file)], 90.0)
        if code != 0:
            raise RuntimeError("host-only compiler failed: " + str(code))
        result["executable"] = dict(path=str(executable), sha256=digest(executable))
        code = run_child("harness", [str(executable)], 10.0)
        result["host_cpu_harness_executed"] = True
        result["harness_exit"] = code
        result["expectation_met"] = code == result["expected_harness_exit"]
        if not result["expectation_met"]:
            result["errors"].append("harness exit differs from expected phase outcome")
    except BaseException as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    for child, child_record in pending_cleanup:
        try:
            child.close()
            child_record["owned_job_closed"] = True
            child_record["cleanup_retry_completed"] = True
        except BaseException as error:
            result["errors"].append("owned child cleanup unconfirmed: " + type(error).__name__)
    result_file = work / "result.json"
    result_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(result=str(result_file), expectation_met=result["expectation_met"],
                          errors=result["errors"])))
    return 0 if result["expectation_met"] and not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
