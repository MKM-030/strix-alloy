"""Root-owned, offline gfx1151 compilation. Never loads a GPU runtime.

Uses the installed compiler in a finite Windows job. Source, tool, ELF,
disassembly and metadata hashes are retained; emitted arithmetic and runtime
parity must be reviewed separately. This is not an engine installation.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "server"))
from host_frames import frame
from winjob import OwnedProcess

SDK = Path(r"C:\Program Files\AMD\ROCm\7.2")
SOURCE = Path(__file__).with_name("hidden_q8_fused.hip")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    out = args.out_dir or (ROOT / "server/.local/optimization9h-20261004" /
                          ("gpu-hidden-q8-fused-build-" + uuid.uuid4().hex))
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = dict(schema="halogen.gpu-hidden-q8-fused.offline-build.v1",
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  output_directory=str(out), runtime_loaded=False,
                  gpu_executed=False, engine_modified=False, passed=False,
                  stages=[], source_sha256=digest(SOURCE))
    minima = [float("inf"), float("inf")]

    def reserve():
        value = frame()
        minima[0] = min(minima[0], value["available_bytes"])
        minima[1] = min(minima[1], value["commit_headroom_bytes"])
        if min(value["available_bytes"], value["commit_headroom_bytes"]) < 18 * 2**30:
            raise RuntimeError("physical or commit reserve below 18 GiB")

    def stage(name, command, seconds):
        reserve()
        tool = Path(command[0])
        entry = dict(name=name, command=command, tool_sha256=digest(tool),
                     deadline_seconds=seconds, owned_job_closed=False)
        record["stages"].append(entry)
        child = OwnedProcess(command, cwd=ROOT, env=dict(os.environ),
                             stdout_path=out / (name + "-stdout.txt"),
                             stderr_path=out / (name + "-stderr.txt"))
        entry["identity"] = child.identity
        try:
            child.resume()
            deadline = time.monotonic() + seconds
            while not child.wait(250):
                reserve()
                if time.monotonic() > deadline:
                    raise TimeoutError(name + " exceeded deadline")
            entry["exit_code"] = child.exit_code()
            if entry["exit_code"] != 0:
                raise RuntimeError(name + " failed; retained stderr has diagnostics")
        finally:
            child.close()
            entry["owned_job_closed"] = True
        for label in ("stdout", "stderr"):
            entry[label + "_sha256"] = digest(out / (name + "-" + label + ".txt"))

    try:
        stage("compile", [str(SDK / "bin/clang++.exe"), "-x", "hip", "--offload-device-only",
              "--offload-arch=gfx1151", "-mcode-object-version=6", "-O3",
              "-fno-fast-math", "-ffp-contract=off", "--rocm-path=" + str(SDK),
              "--hip-path=" + str(SDK), str(SOURCE), "-o", str(out / "hidden-q8-fused.bundle")], 180)
        bundle = out / "hidden-q8-fused.bundle"
        if bundle.stat().st_size > 1024 * 1024:
            raise RuntimeError("compiler bundle exceeds bounded 1 MiB extent")
        record["bundle_sha256"] = digest(bundle)
        stage("unbundle", [str(SDK / "bin/clang-offload-bundler.exe"), "--type=o",
              "--unbundle", "--targets=hipv4-amdgcn-amd-amdhsa--gfx1151",
              "--input=" + str(bundle), "--output=" + str(out / "hidden-q8-fused.hsaco")], 30)
        code = out / "hidden-q8-fused.hsaco"
        if code.stat().st_size > 1024 * 1024 or code.read_bytes()[:4] != b"\x7fELF":
            raise RuntimeError("bounded raw ELF code object required")
        record["codeobject_sha256"] = digest(code)
        record["codeobject_bytes"] = code.stat().st_size
        stage("metadata", [str(SDK / "bin/llvm-readobj.exe"), "--file-headers",
              "--notes", "--symbols", str(code)], 30)
        stage("disassembly", [str(SDK / "bin/llvm-objdump.exe"), "-d",
              "--mcpu=gfx1151", str(code)], 30)
        if record["source_sha256"] != digest(SOURCE):
            raise RuntimeError("source changed during build")
        reserve()
        record["passed"] = True
    except BaseException as error:
        record["error"] = type(error).__name__ + ": " + str(error)
    finally:
        record["minimum_physical_bytes"] = minima[0] if minima[0] != float("inf") else None
        record["minimum_commit_headroom_bytes"] = minima[1] if minima[1] != float("inf") else None
        record["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"passed": record["passed"], "receipt": str(out / "build.json"),
                      "error": record.get("error")}))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
