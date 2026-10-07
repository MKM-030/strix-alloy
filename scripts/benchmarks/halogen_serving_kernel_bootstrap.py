"""Default-off pre-exec identity bridge for one fresh, owned flash_serve task.

The sealed plan contains argv/environment hashes, never their plaintext values.
Launch requires both enabled=true and --activate. Import/check do no native work.
No serving entrypoint uses this module. Linux/native CPU qualification is separate.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import uuid

PLAN_SCHEMA = "halogen.serving-kernel-identity.plan.v1"
RECEIPT_SCHEMA = "halogen.serving-kernel-identity.pre-exec.v1"
ENGINE = "/usr/local/bin/flash_serve"
ENGINE_BYTES = 26052768
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
FROZEN_HEADER_SHA256 = "21c311d0d5dd458bca7f84b611dc734a9db1a4182938841629c98ed8efd718eb"
BPF_MASK = 1 << 39
CAP_KEYS = ("effective", "permitted", "inheritable", "bounding", "ambient")
MAX_JSON_BYTES = 16384
PREFIX = "/tmp/halogen-serving-kernel-"
BINDING_KEYS = ("nonce", "service_run_id", "container_id", "manifest_sha256", "bootstrap_sha256",
                "native_source_sha256", "frozen_header_sha256", "native_helper_sha256", "engine_sha256",
                "engine_bytes", "argv_sha256", "environment_sha256")


class NativeResult(ctypes.Structure):
    _fields_ = [(key, ctypes.c_uint32) for key in ("abi_version", "struct_bytes", "kernel_pid", "kernel_tgid")] + [
        ("namespace_pid", ctypes.c_int64), ("namespace_tid", ctypes.c_int64),
        ("proc_pid_namespace_inode", ctypes.c_uint64)] + [
        (key, ctypes.c_uint32) for key in ("probe_fds_closed", "capability_drop_checked", "failure_stage",
                                         "probe_errno", "drop_errno", "capability_count")] + [
        (prefix + key, ctypes.c_uint64) for prefix in ("before_", "after_") for key in CAP_KEYS]


NATIVE_STRUCT_BYTES = ctypes.sizeof(NativeResult)
if NATIVE_STRUCT_BYTES != 144:
    raise RuntimeError("Unsupported native identity ABI layout")


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, ensure_ascii=True).encode()).hexdigest()


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Sealed lowercase SHA256 required")
    return value


def _nonce(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None or not any(bytes.fromhex(value)):
        raise ValueError("Fresh nonzero nonce required")
    return value


def _masks(value):
    if type(value) is not dict or set(value) != set(CAP_KEYS) or any(
            type(number) is not int or not 0 <= number < 1 << 64 for number in value.values()):
        raise ValueError("Exact bounded capability masks required")
    return value


def validate_plan(plan):
    keys = {"schema", "enabled", "nonce", "service_run_id", "container_id", "manifest_sha256",
            "bootstrap_sha256", "native_source_sha256", "frozen_header_sha256", "native_helper_path",
            "native_helper_sha256", "native_helper_bytes", "engine_sha256", "engine_bytes",
            "argv_sha256", "environment_sha256", "capability_policy"}
    if type(plan) is not dict or set(plan) != keys or plan["schema"] != PLAN_SCHEMA or plan["enabled"] is not True:
        raise ValueError("Explicitly enabled sealed plan required; plaintext fields are not accepted")
    for key in ("nonce", "service_run_id"): _nonce(plan[key])
    for key in keys:
        if key.endswith("sha256") or key == "container_id": _sha(plan[key])
    if (plan["engine_sha256"] != ENGINE_SHA256 or type(plan["engine_bytes"]) is not int or
            plan["engine_bytes"] != ENGINE_BYTES or plan["frozen_header_sha256"] != FROZEN_HEADER_SHA256):
        raise ValueError("Frozen engine/header pins differ")
    helper = plan["native_helper_path"]
    if (type(helper) is not str or not helper.startswith("/candidate/") or "\0" in helper or
            ".." in PurePosixPath(helper).parts or type(plan["native_helper_bytes"]) is not int or
            not 0 < plan["native_helper_bytes"] <= 1024**2):
        raise ValueError("Bounded candidate native helper required")
    policy = plan["capability_policy"]
    if type(policy) is not dict or set(policy) != {"only_added", "baseline_masks", "expected_before_masks"} or policy["only_added"] != "CAP_BPF":
        raise ValueError("Only added CAP_BPF may be removed")
    baseline, before = _masks(policy["baseline_masks"]), _masks(policy["expected_before_masks"])
    if (any(baseline[key] & BPF_MASK or before[key] & ~BPF_MASK != baseline[key] for key in CAP_KEYS) or
            any(not before[key] & BPF_MASK for key in ("effective", "permitted", "bounding")) or
            not before["effective"] & (1 << 8)):
        raise ValueError("Sealed baseline and BPF-only capability delta differ")
    return plan


def _duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _file_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


@contextmanager
def _verified_fd(path, expected_sha, maximum, *, exact=None, follow_proc=False):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if not follow_proc: flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        _check_fd(fd, expected_sha, maximum, exact=exact)
        yield fd
    finally:
        os.close(fd)


def _check_fd(fd, expected_sha, maximum, *, exact=None):
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
            before.st_mode & (stat.S_ISUID | stat.S_ISGID) or not 0 < before.st_size <= maximum or
            exact is not None and before.st_size != exact):
        raise ValueError("Sealed regular file extent differs")
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256(); count = 0
    while count <= maximum:
        block = os.read(fd, min(1024**2, maximum + 1 - count))
        if not block: break
        digest.update(block); count += len(block)
    if (count != before.st_size or digest.hexdigest() != _sha(expected_sha) or
            _file_identity(before) != _file_identity(os.fstat(fd))):
        raise ValueError("Sealed file pin changed")
    os.lseek(fd, 0, os.SEEK_SET)


def load_plan(path, expected_sha):
    with _verified_fd(path, expected_sha, MAX_JSON_BYTES) as fd:
        raw = os.read(fd, MAX_JSON_BYTES + 1)
    return validate_plan(json.loads(raw, object_pairs_hook=_duplicates))


def _require_linux():
    if sys.platform != "linux" or os.execve not in os.supports_fd:
        raise OSError("Linux proc and fd-based exec are required")


def _read_proc(path, maximum):
    with open(path, "rb", buffering=0) as source:
        value = source.read(maximum + 1)
    if len(value) > maximum: raise ValueError("Proc field exceeds its fixed bound")
    return value


def _snapshot(pid=None):
    pid = os.getpid() if pid is None else pid
    root = Path("/proc") / str(pid)
    status = _read_proc(root / "status", 65536).decode("ascii")
    def field(name):
        matches = re.findall(r"^" + name + r":\s+([^\n]+)$", status, re.M)
        if len(matches) != 1: raise ValueError("Required proc status field missing")
        return matches[0].split()
    uid = [int(value) for value in field("Uid")]
    chain = [int(value) for value in field("NSpid")]
    if len(uid) != 4 or len(set(uid)) != 1 or not chain or chain[-1] != pid or len(chain) > 32:
        raise ValueError("Stable proc UID and namespace PID chain required")
    raw = _read_proc(root / "stat", 16384); end = raw.rfind(b") ")
    parts = raw[end + 2:].split() if end >= 0 else ()
    if len(parts) < 20 or parts[0] in (b"Z", b"X", b"x") or int(parts[19]) <= 0:
        raise ProcessLookupError("Live process birth required")
    capabilities = {key: int(field(name)[0], 16) for key, name in zip(CAP_KEYS, ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb"))}
    boot = _read_proc("/proc/sys/kernel/random/boot_id", 64).decode("ascii").strip()
    if str(uuid.UUID(boot)) != boot: raise ValueError("Canonical boot ID required")
    tasks = []
    for entry in (root / "task").iterdir():
        tasks.append(entry.name)
        if len(tasks) > 128 or not entry.name.isdecimal(): raise ValueError("Bounded proc task set required")
    if not tasks: raise ValueError("Live proc task set required")
    cgroup = _read_proc(root / "cgroup", 16384).decode("ascii")
    return dict(pid=pid, uid=uid[0], start_ticks=int(parts[19]), boot_id=boot,
                namespace_inode=(root / "ns/pid").stat().st_ino, namespace_pids=chain,
                task_count=len(tasks), capabilities=_masks(capabilities), cgroup=cgroup)


def _in_container(snapshot, container_id):
    return snapshot.get("container_id") == container_id or re.search(
        r"(?<![0-9a-f])" + container_id + r"(?![0-9a-f])", snapshot.get("cgroup", "")) is not None


def _same_task(before, after):
    return all(before[key] == after[key] for key in ("pid", "uid", "start_ticks", "boot_id", "namespace_inode", "namespace_pids"))


def _observe_native(plan):
    with _verified_fd(plan["native_helper_path"], plan["native_helper_sha256"], 1024**2,
                      exact=plan["native_helper_bytes"]) as fd:
        library = ctypes.CDLL("/proc/self/fd/" + str(fd), mode=os.RTLD_NOW | os.RTLD_LOCAL, use_errno=True)
        _check_fd(fd, plan["native_helper_sha256"], 1024**2, exact=plan["native_helper_bytes"])
        abi = library.halogen_serving_kernel_identity_abi; abi.argtypes = []; abi.restype = ctypes.c_uint32
        size = library.halogen_serving_kernel_identity_size; size.argtypes = []; size.restype = ctypes.c_uint32
        header = library.halogen_serving_kernel_identity_header_sha256; header.argtypes = []; header.restype = ctypes.c_char_p
        if abi() != 1 or size() != NATIVE_STRUCT_BYTES or header() != FROZEN_HEADER_SHA256.encode():
            raise ValueError("Native bridge ABI/header differs")
        observe = library.halogen_serving_observe_and_drop_bpf
        observe.argtypes = [ctypes.POINTER(NativeResult), ctypes.c_uint32, ctypes.c_uint32]
        observe.restype = ctypes.c_int
        result = NativeResult()
        success = observe(ctypes.byref(result), NATIVE_STRUCT_BYTES, 1)
        value = {key: int(getattr(result, key)) for key, _ in NativeResult._fields_ if not key.startswith(("before_", "after_"))}
        value.update(before={key: int(getattr(result, "before_" + key)) for key in CAP_KEYS},
                     after={key: int(getattr(result, "after_" + key)) for key in CAP_KEYS})
        if success != 1: raise RuntimeError("Native identity/cleanup failed")
        _check_fd(fd, plan["native_helper_sha256"], 1024**2, exact=plan["native_helper_bytes"])
        return value


def validate_native(value, plan, before):
    scalar = ("abi_version", "struct_bytes", "kernel_pid", "kernel_tgid", "namespace_pid", "namespace_tid",
              "proc_pid_namespace_inode", "probe_fds_closed", "capability_drop_checked", "failure_stage",
              "probe_errno", "drop_errno", "capability_count")
    if (type(value) is not dict or set(value) != set(scalar) | {"before", "after"} or
            any(type(value.get(key)) is not int for key in scalar) or
            value["abi_version"] != 1 or value["struct_bytes"] != NATIVE_STRUCT_BYTES or
            not 0 < value["kernel_pid"] <= 0x7fffffff or value["kernel_pid"] != value["kernel_tgid"] or
            value["namespace_pid"] != before["pid"] or value["namespace_tid"] != before["pid"] or
            value["proc_pid_namespace_inode"] != before["namespace_inode"] or
            not 40 <= value["capability_count"] <= 64 or
            value["probe_fds_closed"] != 1 or value["capability_drop_checked"] != 1 or
            any(value[key] != 0 for key in ("failure_stage", "probe_errno", "drop_errno")) or
            _masks(value["before"]) != plan["capability_policy"]["expected_before_masks"] or
            _masks(value["after"]) != plan["capability_policy"]["baseline_masks"]):
        raise ValueError("Checked native main-task identity and BPF-only removal required")
    return value


def _publish_fresh(path, value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(payload) > MAX_JSON_BYTES: raise ValueError("Receipt exceeds its fixed bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        pending = memoryview(payload)
        while pending:
            size = os.write(fd, pending)
            if size <= 0: raise OSError("Receipt write made no progress")
            pending = pending[size:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _require_fresh_receipt(path):
    try: os.lstat(path)
    except FileNotFoundError: return
    raise FileExistsError("Receipt nonce has already been used")


def _read_receipt(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1 or stat.S_IMODE(first.st_mode) != 0o600 or not 0 < first.st_size <= MAX_JSON_BYTES:
            raise ValueError("Bounded private receipt required")
        raw = os.read(fd, MAX_JSON_BYTES + 1)
        if len(raw) != first.st_size or _file_identity(first) != _file_identity(os.fstat(fd)):
            raise ValueError("Receipt changed")
    finally: os.close(fd)
    return json.loads(raw, object_pairs_hook=_duplicates), raw, first.st_uid


def _argv_check(argv):
    if (type(argv) is not list or len(argv) != 15 or any(type(item) is not str or "\0" in item or len(item) > 4096 for item in argv) or
            argv[0] != ENGINE or argv[1::2] != ["--ck", "--port", "--bind", "--slots", "--ctx", "--max-tok", "--kv-pool"] or
            not argv[2].startswith("/models/") or ".." in PurePosixPath(argv[2]).parts or argv[6] != "127.0.0.1" or argv[8] != "1" or
            any(re.fullmatch(r"[1-9][0-9]{0,5}", argv[index]) is None for index in (4, 10, 12, 14)) or
            not 1 <= int(argv[4]) <= 65535 or not 4096 <= int(argv[10]) <= 262144 or
            not 1 <= int(argv[12]) <= 262144 or argv[10] != argv[14]):
        raise ValueError("Exact real-serving argv shape differs")


def launch(plan_path, plan_sha256, argv, *, activate=False):
    if activate is not True: raise ValueError("Launch requires explicit activation")
    _require_linux(); plan = load_plan(plan_path, plan_sha256); _argv_check(argv)
    environment = dict(os.environ)
    if digest_json(argv) != plan["argv_sha256"] or digest_json(environment) != plan["environment_sha256"]:
        raise ValueError("Sealed argv/environment digest differs")
    receipt_path = PREFIX + plan["nonce"] + ".json"
    _require_fresh_receipt(receipt_path)
    before = _snapshot()
    if (before["task_count"] != 1 or not _in_container(before, plan["container_id"]) or
            before["capabilities"] != plan["capability_policy"]["expected_before_masks"]):
        raise ValueError("Owned sole task and declared capability state required")
    with _verified_fd(Path(__file__).resolve(), plan["bootstrap_sha256"], 262144) as bootstrap_fd:
        with _verified_fd(ENGINE, ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES) as engine_fd:
            started = time.monotonic_ns()
            native = validate_native(_observe_native(plan), plan, before)
            after = _snapshot()
            if (not _same_task(before, after) or after["task_count"] != 1 or
                    after["capabilities"] != native["after"] or not _in_container(after, plan["container_id"])):
                raise ValueError("Task/birth changed across native identity/cleanup")
            value = {key: plan[key] for key in BINDING_KEYS}
            value.update(schema=RECEIPT_SCHEMA, plan_sha256=_sha(plan_sha256), pid=before["pid"], uid=before["uid"],
                         start_ticks=before["start_ticks"], boot_id=before["boot_id"], namespace_pids=before["namespace_pids"],
                         namespace_pids_scope="bootstrap-proc-mount", kernel_identity=native,
                         only_added_capability_declared="CAP_BPF", exec_preserves_identity=True,
                         stage="pre-exec-intent", post_exec_verified=False, qualifications=False,
                         linux_monotonic_before_ns=started, linux_monotonic_after_ns=time.monotonic_ns())
            _publish_fresh(receipt_path, value)
            _check_fd(bootstrap_fd, plan["bootstrap_sha256"], 262144)
            _check_fd(engine_fd, ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES)
            final = _snapshot()
            if (not _same_task(after, final) or final["task_count"] != 1 or final["capabilities"] != native["after"] or
                    not _in_container(final, plan["container_id"]) or digest_json(dict(os.environ)) != plan["environment_sha256"]):
                raise ValueError("Task/environment changed before exec")
            os.execve(engine_fd, argv, environment)
            raise RuntimeError("Exec unexpectedly returned")


def _check_live_argv(pid, expected_sha):
    command = _read_proc(Path("/proc") / str(pid) / "cmdline", 65536)
    argv = [item.decode() for item in command[:-1].split(b"\0")] if command.endswith(b"\0") else []
    _argv_check(argv)
    if digest_json(argv) != expected_sha: raise ValueError("Post-exec argv differs")


def inspect(plan_path, plan_sha256):
    _require_linux(); plan = load_plan(plan_path, plan_sha256)
    path = PREFIX + plan["nonce"] + ".json"
    value, raw, owner_uid = _read_receipt(path)
    receipt_keys = set(BINDING_KEYS) | {"schema", "plan_sha256", "pid", "uid", "start_ticks", "boot_id", "namespace_pids",
                   "namespace_pids_scope", "kernel_identity", "only_added_capability_declared", "exec_preserves_identity",
                   "stage", "post_exec_verified", "qualifications", "linux_monotonic_before_ns", "linux_monotonic_after_ns"}
    if (type(value) is not dict or set(value) != receipt_keys or any(value.get(key) != plan[key] for key in BINDING_KEYS) or value.get("schema") != RECEIPT_SCHEMA or
            value.get("plan_sha256") != plan_sha256 or value.get("stage") != "pre-exec-intent" or
            value.get("post_exec_verified") is not False or value.get("qualifications") is not False or
            value.get("exec_preserves_identity") is not True or value.get("only_added_capability_declared") != "CAP_BPF" or
            value.get("namespace_pids_scope") != "bootstrap-proc-mount" or
            type(value.get("pid")) is not int or value["pid"] <= 0):
        raise ValueError("Receipt binding differs")
    current = _snapshot(value["pid"])
    if (owner_uid != current["uid"] or any(value.get(key) != current[key] for key in ("pid", "uid", "start_ticks", "boot_id", "namespace_pids")) or
            not _in_container(current, plan["container_id"]) or current["capabilities"] != plan["capability_policy"]["baseline_masks"]):
        raise ValueError("Live engine/birth/BPF state differs")
    validate_native(value["kernel_identity"], plan, current)
    _check_live_argv(value["pid"], plan["argv_sha256"])
    executable = f"/proc/{value['pid']}/exe"
    with _verified_fd(executable, ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES, follow_proc=True):
        final = _snapshot(value["pid"])
        if (not _same_task(current, final) or not _in_container(final, plan["container_id"]) or
                final["capabilities"] != plan["capability_policy"]["baseline_masks"]):
            raise ValueError("Engine identity changed during inspection")
        # Exec itself preserves birth: sample the current image and argv again.
        with _verified_fd(executable, ENGINE_SHA256, ENGINE_BYTES, exact=ENGINE_BYTES, follow_proc=True):
            _check_live_argv(value["pid"], plan["argv_sha256"])
    return dict(value, receipt_sha256=hashlib.sha256(raw).hexdigest(), post_exec_verified=True)


class QuietParser(argparse.ArgumentParser):
    def error(self, message): raise ValueError("Invalid bootstrap options")


def main():
    parser = QuietParser(description=__doc__)
    parser.add_argument("action", choices=("check", "launch", "inspect"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--activate", action="store_true", default=False)
    supplied = sys.argv[1:]; separator = supplied.index("--") if "--" in supplied else len(supplied)
    args = parser.parse_args(supplied[:separator]); argv = supplied[separator + 1:]
    if args.action == "launch":
        launch(args.plan, args.plan_sha256, argv, activate=args.activate)
    elif args.action == "check":
        if argv or args.activate: raise ValueError("Check is inert")
        plan = load_plan(args.plan, args.plan_sha256)
        print(json.dumps(dict(schema=PLAN_SCHEMA, valid=True, launch_activated=False, plan_sha256=args.plan_sha256,
                              capability_delta=plan["capability_policy"]["only_added"])))
    else:
        if argv or args.activate: raise ValueError("Inspection accepts no activation/argv")
        result = inspect(args.plan, args.plan_sha256)
        summary = {key: result[key] for key in ("schema", "pid", "boot_id", "start_ticks", "receipt_sha256", "post_exec_verified")}
        summary.update(kernel_pid=result["kernel_identity"]["kernel_pid"], kernel_tgid=result["kernel_identity"]["kernel_tgid"])
        print(json.dumps(summary))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(json.dumps(dict(passed=False, error_type=type(error).__name__, details_redacted=True)), file=sys.stderr)
        raise SystemExit(1)
