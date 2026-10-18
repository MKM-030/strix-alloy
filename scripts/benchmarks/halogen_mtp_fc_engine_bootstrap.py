"""Attest the exact fresh Linux engine PID before exec, and inspect it afterward.

This is a launch adapter for an owned experimental container, never a way to
attach to a running user server. execv preserves the PID and /proc starttime.
The receipt stays outside the directory exclusively created by the native shim.
Importing the module performs no process, file, model or provider work.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


ENGINE = "/usr/local/bin/flash_serve"
ENGINE_BYTES = 26052768
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
PREFIX = "/tmp/alloy-mtp-fc-launch-"
SCHEMA = "halogen0162.fc-owned-engine-launch.v1"


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _sha(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("independently sealed lowercase SHA256 required")
    return value


def _nonce(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{32}", value) or not any(bytes.fromhex(value)):
        raise ValueError("fresh nonzero run nonce required")
    return value


def _starttime(pid):
    raw = Path(f"/proc/{pid}/stat").read_bytes()
    end = raw.rfind(b") ")
    fields = raw[end + 2:].split() if end >= 0 else ()
    if len(fields) < 20 or fields[0] in (b"Z", b"X", b"x"):
        raise ProcessLookupError("engine identity is absent or terminal")
    ticks = int(fields[19])
    if ticks <= 0:
        raise ValueError("invalid Linux process starttime")
    return ticks


def _file(path, expected, maximum, *, exact=None, follow_proc=False):
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if not follow_proc:
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= maximum
                or exact is not None and before.st_size != exact):
            raise ValueError("sealed regular file extent/identity differs")
        with os.fdopen(os.dup(fd), "rb", buffering=0) as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != _sha(expected) or _identity(before) != _identity(os.fstat(fd)):
            raise ValueError("sealed file hash or identity changed")
        return before
    finally:
        os.close(fd)


def _contract(nonce, plan_sha256, source_sha256):
    if sys.platform != "linux":
        raise OSError("engine launch attestation requires Linux /proc")
    _nonce(nonce)
    _sha(plan_sha256)
    _file(__file__, source_sha256, 262144)
    directory = os.lstat("/tmp")
    if not stat.S_ISDIR(directory.st_mode):
        raise ValueError("plain container-local /tmp required")
    return PREFIX + nonce + ".json"


def launch(nonce, plan_sha256, source_sha256, argv):
    receipt = _contract(nonce, plan_sha256, source_sha256)
    run_id = _nonce(os.environ.get("ALLOY_FC_SERVICE_RUN_ID"))
    expected = [ENGINE, "--ck", "/models/qwen38-flash-next-v2.hgn", "--port", "8730",
                "--bind", "127.0.0.1", "--slots", "1", "--ctx", "262144"]
    # MAX_TOK and KV_POOL come from the pinned service shell. Check every
    # argument as well, rather than accepting a prefix and arbitrary suffix.
    if (argv[:len(expected)] != expected or len(argv) != len(expected) + 4
            or argv[-4] != "--max-tok" or not re.fullmatch("[1-9][0-9]{0,5}", argv[-3])
            or argv[-2:] != ["--kv-pool", "262144"]):
        raise ValueError("fixed owned full-context engine argv differs")
    required = {"HALOGEN_MTP_WIRE": "D", "HALOGEN_MTP_FC_QUALITY": "shadow4-v1",
                "HALOGEN_MTP_FC_QUALITY_DIR": "/tmp/alloy-mtp-fc-quality-" + nonce,
                "HALOGEN_MTP_DEPTH": "2", "HALOGEN_HOST_RESERVE_GIB": "18"}
    if any(os.environ.get(key) != value for key, value in required.items()):
        raise ValueError("owned native shadow environment differs")
    _file(ENGINE, ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES)
    pid = os.getpid()
    value = dict(schema=SCHEMA, nonce=nonce, service_run_id=run_id,
                 plan_sha256=plan_sha256, source_sha256=source_sha256,
                 engine_sha256=ENGINE_SHA256, engine_bytes=ENGINE_BYTES,
                 pid=pid, starttime_ticks=_starttime(pid), uid=os.geteuid(),
                 argv=argv, exec_preserves_identity=True, qualifications=False)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        remaining = memoryview(payload)
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise OSError("launch receipt publication made no progress")
            remaining = remaining[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.execv(ENGINE, argv)


def inspect(nonce, plan_sha256, source_sha256):
    receipt = _contract(nonce, plan_sha256, source_sha256)
    fd = os.open(receipt, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= 4096):
            raise ValueError("bounded private launch receipt required")
        raw = os.read(fd, 4097)
        if len(raw) != before.st_size or _identity(before) != _identity(os.fstat(fd)):
            raise ValueError("launch receipt changed while reading")
    finally:
        os.close(fd)
    value = json.loads(raw)
    required = dict(schema=SCHEMA, nonce=nonce, plan_sha256=plan_sha256,
                    source_sha256=source_sha256, engine_sha256=ENGINE_SHA256,
                    engine_bytes=ENGINE_BYTES, exec_preserves_identity=True, qualifications=False)
    if any(type(value.get(key)) is not type(wanted) or value.get(key) != wanted for key, wanted in required.items()):
        raise ValueError("independent engine launch identity differs")
    _nonce(value.get("service_run_id"))
    pid, ticks, uid = (value.get(key) for key in ("pid", "starttime_ticks", "uid"))
    if (any(type(item) is not int for item in (pid, ticks, uid)) or pid <= 0
            or ticks <= 0 or uid < 0 or before.st_uid != uid or _starttime(pid) != ticks):
        raise ValueError("actual engine process/starttime/owner differs")
    status = Path(f"/proc/{pid}/status").read_text()
    found = re.search(r"^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", status, re.MULTILINE)
    if found is None or any(int(item) != uid for item in found.groups()):
        raise ValueError("actual engine UID differs from launch receipt")
    with open(f"/proc/{pid}/cmdline", "rb") as stream:
        cmdline = stream.read(4097)
    argv = value.get("argv")
    if (not isinstance(argv, list) or not argv or argv[0] != ENGINE
            or any(type(item) is not str or "\0" in item for item in argv)
            or cmdline != b"\0".join(item.encode() for item in argv) + b"\0"):
        raise ValueError("actual post-exec engine argv differs")
    _file(f"/proc/{pid}/exe", ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES, follow_proc=True)
    if _starttime(pid) != ticks:
        raise ProcessLookupError("engine identity changed during inspection")
    return dict(value, receipt_sha256=hashlib.sha256(raw).hexdigest(), inspected_after_exec=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "inspect"))
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    # Split explicitly so positional REMAINDER cannot swallow action-first
    # option tokens. Never accept unknown bootstrap options as engine flags.
    supplied = sys.argv[1:]
    separator = supplied.index("--") if "--" in supplied else len(supplied)
    args = parser.parse_args(supplied[:separator])
    argv = supplied[separator + 1:] if separator < len(supplied) else []
    if args.action == "inspect":
        if argv or separator < len(supplied):
            parser.error("inspection accepts no engine arguments")
        print(json.dumps(inspect(args.nonce, args.plan_sha256, args.source_sha256), sort_keys=True))
    else:
        if separator == len(supplied) or not argv:
            parser.error("launch requires -- followed by the exact engine argv")
        launch(args.nonce, args.plan_sha256, args.source_sha256, argv)


if __name__ == "__main__":
    main()
