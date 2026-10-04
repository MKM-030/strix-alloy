"""Exclusive, bounded public-DD admission with durable failure receipts.

This is a synthetic FC diagnostic, not a model-throughput benchmark. The child
has an 8-GiB committed-memory ceiling in addition to host reserve monitoring.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "server/.local/optimization9h-20261004"
sys.path.insert(0, str(ROOT / "server"))
from host_frames import frame
from winjob import OwnedProcess, _ExtendedLimit, _check

MEMORY_KEYS = ("available_bytes", "commit_headroom_bytes")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_reserve(value, gib):
    if min(value[key] for key in MEMORY_KEYS) < gib << 30:
        raise RuntimeError("Required memory reserve: " + str(gib) + " GiB")


def quiet():
    for path in (ROOT / "server/.local/current.json",
                 ROOT / "backends/halogen-wsl2-0.16.2/.local/current-service.json"):
        state = json.loads(path.read_text())
        if state.get("phase") != "stopped" or state.get("active_requests", 0):
            raise RuntimeError("Controller/backend is not terminal and idle")
        if path.name == "current-service.json":
            outcome = state.get("outcome", {})
            if outcome.get("cleanup") is not True or outcome.get("recovery") is not True:
                raise RuntimeError("Backend cleanup and reserve recovery are unconfirmed")
    for port in (8731, 8840):
        with socket.socket() as connection:
            connection.settimeout(.1)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Engine listener remains open")


def cap_child(owner, limit):
    # Experimental diagnostic only: retain KILL_ON_JOB_CLOSE and limit both
    # one process and its job. Apply and read back before resuming the child.
    # https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
    limits = _ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x100 | 0x200
    limits.ProcessMemoryLimit = limits.JobMemoryLimit = limit
    _check(owner._api.SetInformationJobObject(owner._job, 9,
                                             ctypes.byref(limits), ctypes.sizeof(limits)))
    query = owner._api.QueryInformationJobObject
    query.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                      ctypes.c_uint32, ctypes.c_void_p]
    query.restype = ctypes.c_int
    observed = _ExtendedLimit()
    _check(query(owner._job, 9, ctypes.byref(observed), ctypes.sizeof(observed), None))
    if (observed.BasicLimitInformation.LimitFlags & 0x2300 != 0x2300
            or observed.ProcessMemoryLimit != limit or observed.JobMemoryLimit != limit):
        raise RuntimeError("Diagnostic child memory ceiling not confirmed")


def main():
    if len(sys.argv) != 3:
        raise RuntimeError("Pinned configuration and its SHA required")
    config_path = Path(sys.argv[1]).resolve(strict=True)
    config_bytes = config_path.read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != sys.argv[2]:
        raise RuntimeError("Pinned configuration changed")
    config = json.loads(config_bytes)
    if sha(__file__) != config["guard_sha256"]:
        raise RuntimeError("Root-reviewed guard changed")
    for path, expected in config["file_pins"].items():
        if sha(path) != expected:
            raise RuntimeError("Root-reviewed dependency changed: " + path)
    limit = config["process_commit_limit_bytes"]
    if type(limit) is not int or limit != 8 << 30:
        raise RuntimeError("Fixed 8-GiB diagnostic child ceiling required")
    quiet()
    before = frame()
    require_reserve(before, 22)
    out = WORK / ("dd-owned-fc-admission-" + uuid.uuid4().hex)
    out.mkdir()
    (out / "reviewed-config.json").write_bytes(config_bytes)
    environment = dict(os.environ)
    environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    environment["PATH"] = os.pathsep.join(config["dll_directories"]) + os.pathsep + environment.get("PATH", "")
    command = [config["python"], "-B", config["probe"], "--root-owned-admission",
               "--config", str(config_path), "--expected-config-sha256", sys.argv[2],
               "--report", str(out / "admission.json")]
    owner, exit_code = None, None
    errors, memory_recovery = [], []
    minimum = {key: before[key] for key in MEMORY_KEYS}
    after = None
    closed = False
    faults = None
    try:
        owner = OwnedProcess(command, cwd=out, env=environment,
                             stdout_path=out / "stdout.txt", stderr_path=out / "stderr.txt")
        cap_child(owner, limit)
        identity = owner.verify_live_identity()
        (out / "identity.json").write_text(json.dumps(dict(command=command, identity=identity,
            config_path=str(config_path), config_sha256=sys.argv[2], before=before,
            process_commit_limit_bytes=limit), indent=2) + "\n")
        quiet()
        require_reserve(frame(), 22)
        owner.resume()
        print("DD_OWNED_STARTED " + str(out) + " pid=" + str(identity["pid"]), flush=True)
        deadline = time.perf_counter() + 90
        next_quiet = time.perf_counter() + 1
        with (out / "memory.jsonl").open("x") as log:
            while owner.exit_code() is None:
                value = frame()
                for key in minimum:
                    minimum[key] = min(minimum[key], value[key])
                # Preserve the violating frame before checking or raising.
                log.write(json.dumps(dict(epoch=time.time(), **value)) + "\n")
                log.flush()
                require_reserve(value, 22)  # 4 GiB margin above the hard reserve.
                now = time.perf_counter()
                if now > deadline:
                    raise TimeoutError("Public-DD child exceeded 90 seconds")
                if now >= next_quiet:
                    quiet()
                    next_quiet = time.perf_counter() + 1
                owner.wait(50)
        exit_code = owner.exit_code()
        if exit_code != 0:
            raise RuntimeError("Public-DD child exit " + str(exit_code))
        admission = json.loads((out / "admission.json").read_text())
        if not admission["passed"] or len(admission["calls"]) != 4:
            raise RuntimeError("Public-DD synthetic output admission failed")
    except BaseException as exc:
        if owner is None:
            owner = getattr(exc, "owner", None)
        errors.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if owner is not None:
            try:
                owner.close()
                closed = owner._closed
                exit_code = owner.exit_code()
            except BaseException as exc:
                errors.append("cleanup: " + type(exc).__name__ + ": " + str(exc))
        try:
            quiet()
        except BaseException as exc:
            errors.append("idle: " + type(exc).__name__ + ": " + str(exc))
        try:
            deadline = time.perf_counter() + 10
            while True:
                after = frame()
                memory_recovery.append(dict(epoch=time.time(), **after))
                if min(after[key] for key in MEMORY_KEYS) >= 22 << 30:
                    break
                if not closed or time.perf_counter() >= deadline:
                    raise RuntimeError("Post-close 22-GiB admission reserve not recovered")
                time.sleep(.1)
            require_reserve(after, 18)
        except BaseException as exc:
            errors.append("memory: " + type(exc).__name__ + ": " + str(exc))
        try:
            fault_path = out / "native-fault.jsonl"
            faults = [json.loads(line) for line in fault_path.read_text().splitlines() if line.strip()]
            if faults:
                errors.append("Native fault records present")
        except BaseException as exc:
            errors.append("fault receipt: " + type(exc).__name__ + ": " + str(exc))
        # Cleanup or telemetry failures must never suppress the primary result.
        (out / "result.json").write_text(json.dumps(dict(schema=2, passed=not errors and closed,
            errors=errors, exit_code=exit_code, owned_job_closed=closed, minimum=minimum,
            final_memory=after, memory_recovery=memory_recovery,
            process_commit_limit_bytes=limit, monitor_abort_reserve_gib=22,
            hard_reserve_gib=18, fault_record_count=len(faults) if faults is not None else None,
            full_mtp_proven=False, speed_gain_established=False), indent=2) + "\n")
    print("DD_OWNED_FINISHED " + str(out) + " errors=" + str(errors), flush=True)
    return 1 if errors or not closed else 0


if __name__ == "__main__":
    raise SystemExit(main())
