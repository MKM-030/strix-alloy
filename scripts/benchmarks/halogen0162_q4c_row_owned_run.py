"""ROOT-only one-window original Q4C row oracle; no model is mounted or run.

A fresh frozen JSON config supplies the independently hashed compiled binary,
native export directory/receipt, and current original server identity. Review
source and actual ownership before executing. Preserve the ready/idle server;
stop/remove only the exact UUID-owned CID. Failed or unresolved cleanup evidence
is retained and an unresolved ownership latch prevents another window.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "server/.local/optimization9h-20261004"
BACKEND = ROOT / "backends/halogen-wsl2-0.16.2"
PATTERN = ROOT / "scripts/benchmarks/halogen_rocr_poll_backoff_owned_run.py"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
COLLEAGUE_CID = "3aaf75d78637c1d01f55b857d1871e8d7f90dfcf2df3993294ae9665779e18de"
CONTROLLER = dict(pid=24904, creation_time_100ns=134356415115894861,
    run_id="370cc96915474e509d12e7329b44f0e7", context=262144, port=8840,
    executable=r"C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe",
    profile_sha256="39faa5d1c98289be76d76a396aafd6ae4fe44cba673e61354a8d63f4540b3de7")
HEALTH = dict(completed=4, cancelled=0)
ENGINE = BACKEND / ".local/flash_serve"
HSACO = WORK / "mtp-route-static-20261004/engine-gfx1151.hsaco"
PLAN = WORK / "q4c-row-plan-fixed-41c4cc84e1b74dec81c61ef344d594d8.json"
HARNESS = ROOT / "scripts/benchmarks/halogen0162_q4c_row_oracle.c"
SCAFFOLD = ROOT / "scripts/benchmarks/halogen0162_embedding_rms_replay.c"
PLAN_SHA = "5814aced81640b368bddbb3b66143abd7974f226012d162bb1c47a48149494bf"
HARNESS_SHA = "f09f3d1e54adcf08c809ca175f8cb59a76b346df585887fe784fad0432de5d95"
SCAFFOLD_SHA = "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
HIP_PATH = "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"
HIP_SHA = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
PACK_SHA = "846e0416dee1d61ec954039f22e249d13254555a9a55a37e95f03f410a64a368"
REFERENCE_SHA = "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374"
BINARY_SHA = "05d5290aecc7ba149b0643a6f384ab4b0465d1b11e11d550bd66177a9bb10c69"
DXG = "/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocdxg.so.1"
LABEL = "alloy.q4c-row-owner"
ROCROLLER = BACKEND / ".local/librocroller-compat.so.1"
PIN_EXTENTS = {ROCROLLER: 465578929}
PINS = {
    PATTERN: "bd2945ae634248e63ce2b008c2cbbdc17ac1af7f47a3a97082c8d36a41955c4f",
    ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    ROOT / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c",
    HARNESS: HARNESS_SHA, SCAFFOLD: SCAFFOLD_SHA, PLAN: PLAN_SHA,
    ENGINE: ENGINE_SHA, HSACO: CODE_SHA,
    ROCROLLER: "9e35bc339b10da3ab2c6f7afbed0d4a1bb5bb2608bf8e3bb43031cfe654c1975",
    BACKEND / ".local/machine.json": "4afd3a90d13222c3f3460425c48f315c5959a29c2b7ade78a82791c8552fe527",
    Path(r"\\wsl.localhost\Ubuntu-24.04" + DXG.replace("/", "\\")):
        "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def capture(path, expected=None, maximum=64 << 20, extent=None):
    path = Path(path)
    require(path.is_absolute(), "absolute input path required")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum
            and (extent is None or before.st_size == extent), "bounded regular file required: " + str(path))
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_birthtime_ns")
    identity = lambda value: tuple(getattr(value, key, None) for key in fields)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    last = path.lstat()
    require(identity(before) == identity(opened) == identity(after) == identity(last)
            and before.st_ctime_ns == last.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns
            and len(raw) == before.st_size, "input identity changed: " + str(path))
    actual = hashlib.sha256(raw).hexdigest()
    require(expected is None or actual == expected, "input SHA differs: " + str(path))
    return raw, actual


def verify_pin(path, expected, maximum=512 << 20, extent=None):
    """Verify a bounded regular pin without retaining its complete contents."""
    path = Path(path)
    require(path.is_absolute(), "absolute input path required")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum
            and (extent is None or before.st_size == extent), "bounded regular pin required: " + str(path))
    fields = ("st_size", "st_dev", "st_ino", "st_mtime_ns", "st_birthtime_ns")
    identity = lambda value: tuple(getattr(value, key, None) for key in fields)
    digest, read_bytes = hashlib.sha256(), 0
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        while read_bytes < before.st_size:
            block = stream.read(min(1 << 20, before.st_size - read_bytes))
            if not block:
                break
            read_bytes += len(block)
            digest.update(block)
        after = os.fstat(stream.fileno())
    last = path.lstat()
    require(identity(before) == identity(opened) == identity(after) == identity(last)
            and before.st_ctime_ns == last.st_ctime_ns and opened.st_ctime_ns == after.st_ctime_ns
            and read_bytes == before.st_size, "pin identity changed: " + str(path))
    require(digest.hexdigest() == expected, "input SHA differs: " + str(path))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "lowercase SHA256 required")
    return value


def native_unc(value, prefix):
    require(isinstance(value, str) and re.fullmatch(prefix + r"[0-9a-f]{32}", value), "exact native owned artifact path required")
    return Path(r"\\wsl.localhost\Ubuntu-24.04" + value.replace("/", "\\"))


def linux_path(path):
    value = Path(path).resolve().as_posix()
    require(re.match(r"^[A-Za-z]:/", value), "absolute Windows path required")
    require("," not in value and "\n" not in value, "mount source contains delimiter")
    return "/mnt/" + value[0].lower() + value[2:]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("health redirect rejected")


def run(args):
    require(os.name == "nt" and args.root_runtime_reviewed, "ROOT Windows runtime/ownership review acknowledgment required")
    config_path = Path(args.config)
    source_path = Path(__file__).absolute()
    raw, _ = capture(config_path, sha(args.config_sha256), 65536)
    config = json.loads(raw)
    require(config.get("schema") == "halogen0162.q4c-row-owned-config.v1" and config.get("image") == IMAGE
            and config.get("colleague_cid") == COLLEAGUE_CID and config.get("controller") == CONTROLLER
            and config.get("health") == HEALTH, "frozen original-server identity/config differs")
    binary = config["binary"]
    require(binary["sha256"] == BINARY_SHA, "reviewed compiled binary SHA differs")
    binary_unc = native_unc(binary["native_path"], "/home/revn/halogen-re/q4c-row-oracle-")
    exported = config["export"]
    export_unc = native_unc(exported["native_directory"], "/home/revn/halogen-re/q4c-selected-export-")
    receipt_sha = sha(exported["receipt_sha256"])
    pins = {**PINS, config_path: args.config_sha256, source_path: sha(args.source_sha256),
            binary_unc: BINARY_SHA, export_unc / "export.json": receipt_sha}
    for path, wanted in pins.items():
        verify_pin(path, wanted, extent=PIN_EXTENTS.get(path))
    machine = json.loads(capture(BACKEND / ".local/machine.json", PINS[BACKEND / ".local/machine.json"], 65536)[0])
    require(machine["image"] == IMAGE and machine["dxg"] == DXG
            and machine["distro"] == "Ubuntu-24.04" and machine["user"] == "revn",
            "installed original DXG/distro/user binding differs")
    plan = json.loads(capture(PLAN, PLAN_SHA, 2 << 20)[0])
    receipt = json.loads(capture(export_unc / "export.json", receipt_sha, 2 << 20)[0])
    require(plan["schema"] == "halogen0162.q4c-row-oracle-plan.v1" and plan["harness_sha256"] == HARNESS_SHA
            and plan["included_scaffold_sha256"] == SCAFFOLD_SHA and plan["engine_sha256"] == ENGINE_SHA
            and plan["codeobject_sha256"] == CODE_SHA and plan["token"] == 14367
            and plan["native_pack"]["bytes"] == 1504 and plan["reference"]["bytes"] == 5120
            and plan["reference"]["sha256"] == REFERENCE_SHA and plan["gather"]["private_table_bytes"] == 73564160,
            "sealed Q4C plan differs")
    require(receipt["schema"] == "halogen0162.q4c-row-oracle-export.v1" and receipt["passed"] is True
            and receipt["plan_sha256"] == PLAN_SHA and receipt["harness_sha256"] == HARNESS_SHA
            and receipt["included_scaffold_sha256"] == SCAFFOLD_SHA
            and receipt["native_identity_before"] == receipt["native_identity_after"] == plan["checkpoint_native_identity"]
            and receipt["source_ranges"] == plan["source_ranges"]
            and receipt["checkpoint_payload_bytes_read"] == 1504 and receipt["reference_payload_bytes_read"] == 5120
            and receipt["CPU_decoding_executed"] is False and receipt["GPU_executed"] is False
            and receipt["native_pack"] == {"file": "native-row.q4c", "bytes": 1504, "sha256": PACK_SHA}
            and receipt["cpu_reference"] == {"file": "cpu-reference.u16", "bytes": 5120, "sha256": REFERENCE_SHA},
            "sealed export lineage/extent differs")
    payloads = {export_unc / "native-row.q4c": (PACK_SHA, 1504),
                export_unc / "cpu-reference.u16": (REFERENCE_SHA, 5120)}

    def recheck():
        for path, wanted in pins.items():
            verify_pin(path, wanted, extent=PIN_EXTENTS.get(path))
        for path, (wanted, extent) in payloads.items():
            capture(path, wanted, extent, extent)

    recheck()
    spec = importlib.util.spec_from_file_location("q4c_reviewed_ownership_pattern", PATTERN)
    pattern = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pattern)
    ControllerIdentity = pattern.ControllerIdentity
    sys.path.insert(0, str(ROOT / "server"))
    from host_frames import frame
    from winjob import OwnedProcess
    wsl = Path(os.environ["WINDIR"]) / "System32/wsl.exe"
    require(wsl.is_absolute() and wsl.is_file(), "absolute Windows WSL executable required")
    wsl_docker = [str(wsl), "-d", "Ubuntu-24.04", "-u", "revn", "--exec", "docker"]

    def docker(*values, timeout=10):
        completed = subprocess.run([*wsl_docker, *values], capture_output=True, text=True,
            timeout=timeout, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        require(len(completed.stdout) <= 2 << 20 and len(completed.stderr) <= 2 << 20, "docker output ceiling exceeded")
        return completed.stdout.strip()

    def inspect(cid):
        rows = json.loads(docker("inspect", cid))
        require(len(rows) == 1 and rows[0]["Id"] == cid, "exact container inspect required")
        return rows[0]

    token = (BACKEND / ".local/api-token.txt").read_text(encoding="ascii").strip()
    require(token, "colleague health authorization unavailable")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    tag = uuid.uuid4().hex
    out = WORK / ("q4c-row-owned-" + tag)
    out.mkdir()
    result = dict(schema="halogen0162.q4c-row-owned.v1", passed=False, contaminated=False,
        errors=[], source_sha256=args.source_sha256, config_sha256=args.config_sha256,
        image=IMAGE, binary_sha256=BINARY_SHA, export_receipt_sha256=receipt_sha,
        models_mounted=False, root_runtime_reviewed=True, colleague_preserved=False)
    window = dict(container_id=None, container_name="alloy-q4c-row-" + tag, ownership_label=tag,
        passed=False, container_removed=False, job_closed=False, create_attempted=False,
        create_identity_recovered=False, cleanup_pending=False, errors=[])
    result["window"] = window
    current = {"cid": None}
    controller = owner = None
    stop, ready_memory, ready_health = threading.Event(), threading.Event(), threading.Event()
    cleanup_lock = threading.RLock()
    problems, samples = [], []
    latch_path = WORK / "q4c-row-owned.lock"
    latch_bytes = (json.dumps(dict(schema="halogen0162.q4c-row-owned-lock.v1", tag=tag,
        out=str(out), source_sha256=args.source_sha256, config_sha256=args.config_sha256), sort_keys=True) + "\n").encode()
    latch_owned = latch_acquired = False

    def owned_info(cid):
        require(re.fullmatch(r"[0-9a-f]{64}", cid) and cid != COLLEAGUE_CID, "owned CID required")
        info = inspect(cid)
        require(info["Name"] == "/" + window["container_name"] and info["Config"]["Image"] == IMAGE
                and (info["Config"].get("Labels") or {}).get(LABEL) == tag,
                "own CID/name/image/label identity differs")
        return info

    def fail(message):
        problems.append(message)
        result["contaminated"] = True
        with cleanup_lock:
            if current["cid"]:
                try:
                    if owned_info(current["cid"])["State"]["Running"]:
                        docker("stop", "-t", "0", current["cid"], timeout=20)
                except BaseException as error:
                    problems.append("guard own-CID stop: " + str(error))

    def reserve(floor):
        controller.verify()
        with (ROOT / "server/.local/current.json").open("rb") as stream:
            raw = stream.read((1 << 20) + 1)
        require(len(raw) <= 1 << 20, "controller-state ceiling exceeded")
        state = json.loads(raw.decode("utf-8-sig"))
        require(state.get("run_id") == CONTROLLER["run_id"] and state.get("pid") == CONTROLLER["pid"]
                and state.get("phase") == "ready" and state.get("active_requests") == 0
                and state.get("context") == CONTROLLER["context"] and state.get("port") == CONTROLLER["port"]
                and state.get("profile_sha256") == CONTROLLER["profile_sha256"]
                and 0 <= time.time() - state.get("heartbeat", 0) <= 10,
                "colleague identity/readiness/idle heartbeat changed")
        sample = {"epoch": time.time(), **frame()}
        samples.append(sample)
        require(min(sample["available_bytes"], sample["commit_headroom_bytes"]) >= floor * 2**30,
                "host physical/commit reserve below " + str(floor) + "GiB")
        return {**sample, "run_id": state["run_id"], "pid": state["pid"],
                "heartbeat": state["heartbeat"], "active_requests": 0}

    def health():
        request = urllib.request.Request("http://127.0.0.1:8840/health", headers={"Authorization": "Bearer " + token})
        with opener.open(request, timeout=2) as response:
            raw = response.read((1 << 20) + 1)
            require(response.status == 200 and len(raw) <= 1 << 20, "colleague health response unavailable")
        value = json.loads(raw)
        require(value.get("status") == "ok" and value.get("active_requests") == 0 and value.get("draining") is False
                and value.get("completed") == HEALTH["completed"] and value.get("cancelled") == HEALTH["cancelled"]
                and value.get("context") == CONTROLLER["context"] and value.get("checkpoint") == "v2"
                and value.get("backend") == "halogen-v2", "colleague health/request counters changed")
        return {"epoch": time.time(), "health": value}

    def watch(name, event, function):
        try:
            with (out / name).open("x", encoding="utf-8") as stream:
                deadline = time.monotonic() + 180
                for _ in range(1024):
                    if stop.is_set():
                        return
                    require(time.monotonic() < deadline, "continuous-guard deadline exceeded")
                    stream.write(json.dumps(function(), allow_nan=False) + "\n")
                    stream.flush()
                    event.set()
                    stop.wait(.25)
                raise RuntimeError("continuous-guard sample ceiling exceeded")
        except BaseException as error:
            event.set()
            fail(name + ": " + type(error).__name__ + ": " + str(error))

    monitors = [threading.Thread(target=watch, args=("memory-state.jsonl", ready_memory, lambda: reserve(18)), daemon=True),
                threading.Thread(target=watch, args=("health.jsonl", ready_health, health), daemon=True)]

    def admission():
        require(not problems and all(monitor.is_alive() for monitor in monitors), "continuous guard unavailable")
        reserve(22)
        health()
        require(not problems, "continuous guard failed during admission")
        info = inspect(COLLEAGUE_CID)
        require(info["Config"]["Image"] == IMAGE and info["State"]["Running"] is True,
                "original colleague container image/CID differs")
        require(set(docker("ps", "-q", "--no-trunc").split()) == {COLLEAGUE_CID},
                "unexpected active container; Q4C window deferred")

    def cleanup_window():
        with cleanup_lock:
            try:
                if window["create_attempted"] and not current["cid"]:
                    found = docker("ps", "-aq", "--no-trunc", "--filter", "name=^/" + window["container_name"] + "$",
                                   "--filter", "label=" + LABEL + "=" + tag, timeout=20).split()
                    require(len(found) == 1, "ambiguous create outcome remains unproven; ownership latch retained")
                    current["cid"] = found[0]
                    owned_info(found[0])
                    window.update(container_id=found[0], create_identity_recovered=True)
                if current["cid"]:
                    info = owned_info(current["cid"])
                    if info["State"]["Running"]:
                        docker("stop", "-t", "0", current["cid"], timeout=20)
                    info = owned_info(current["cid"])
                    require(not info["State"]["Running"] and info["State"]["Pid"] == 0, "own container remained live")
                    window["terminal_container_state"] = info["State"]
                    removed = current["cid"]
                    docker("rm", removed, timeout=20)
                    require(removed not in docker("ps", "-aq", "--no-trunc").split(), "removed own CID remains listed")
                    window["container_removed"] = True
                    current["cid"] = None
            except BaseException as error:
                window["errors"].append("own CID cleanup: " + str(error))
            try:
                if owner:
                    owner.close(timeout_ms=5000)
                    window["job_closed"] = bool(owner._closed)
            except BaseException as error:
                window["errors"].append("own job cleanup: " + str(error))
            window["cleanup_pending"] = (window["create_attempted"] and not window["container_removed"]
                                         or owner is not None and not window["job_closed"])

    try:
        with latch_path.open("xb") as stream:
            latch_owned = latch_acquired = True
            stream.write(latch_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        controller = ControllerIdentity(CONTROLLER)
        write(out / "config.json", config)
        reserve(22)
        health()
        for monitor in monitors:
            monitor.start()
        require(ready_memory.wait(2) and ready_health.wait(2) and not problems, "continuous guard failed before create")
        admission()
        native = out / "result"
        native.mkdir()
        mounts = {
            "/candidate/q4c-row-oracle": binary["native_path"],
            "/candidate/flash_serve": linux_path(ENGINE),
            "/candidate/engine-gfx1151.hsaco": linux_path(HSACO),
            "/fixtures/native-row.q4c": exported["native_directory"] + "/native-row.q4c",
            "/fixtures/cpu-reference.u16": exported["native_directory"] + "/cpu-reference.u16",
            "/usr/lib/libdxcore.so": "/usr/lib/wsl/lib/libdxcore.so",
            "/usr/lib/librocdxg.so": DXG,
            "/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1": linux_path(BACKEND / ".local/librocroller-compat.so.1"),
        }
        argv = ["create", "--name", window["container_name"], "--label", LABEL + "=" + tag,
            "--network=none", "--restart=no", "--read-only", "--device=/dev/dxg", "--memory=2g", "--memory-swap=2g",
            "--pids-limit=128", "--ipc=private", "--shm-size=64m", "--ulimit=core=0:0", "--ulimit=memlock=-1:-1",
            "--security-opt=seccomp=unconfined", "--security-opt=label=disable", "--tmpfs=/tmp:rw,size=64m"]
        for destination, source in sorted(mounts.items()):
            argv += ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
        argv += ["--mount", "type=bind,src=" + linux_path(native) + ",dst=/result",
            "--env=HSA_ENABLE_DXG_DETECTION=1", "--env=HSA_ENABLE_SDMA=1", "--env=HALOGEN_LQ8_WAVE=1",
            "--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1",
            "--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
            "--entrypoint=/usr/bin/timeout", IMAGE, "--signal=TERM", "--kill-after=5s", "60s",
            "/candidate/q4c-row-oracle", "/candidate/flash_serve", "/candidate/engine-gfx1151.hsaco", HIP_PATH, HIP_SHA,
            "/fixtures/native-row.q4c", PACK_SHA, "/fixtures/cpu-reference.u16", "/result/replay"]
        write(out / "plan.json", dict(argv=argv, mounts=mounts, models_mounted=False, private_table_bytes=73564160,
            admission_gib=22, reserve_gib=18, inner_deadline_seconds=60, outer_deadline_seconds=80))
        recheck()
        admission()
        window["create_attempted"] = True
        created = docker(*argv, timeout=20)
        require(re.fullmatch(r"[0-9a-f]{64}", created), "created CID invalid")
        current["cid"] = created
        window["container_id"] = created
        info = owned_info(created)
        require(not info["State"]["Running"], "own container unexpectedly started")
        admission()
        try:
            owner = OwnedProcess([*wsl_docker, "start", "-a", created], cwd=ROOT, env=dict(os.environ),
                stdout_path=out / "stdout.txt", stderr_path=out / "stderr.txt")
        except BaseException as error:
            owner = getattr(error, "owner", None)
            if owner:
                window["process_identity"] = owner.identity
            raise
        window["process_identity"] = owner.identity
        write(out / "retained-process.json", window)
        owner.verify_live_identity()
        with cleanup_lock:
            admission()
            require(not problems, "guard failed before owned process resume")
            owner.resume()
        print(json.dumps(dict(out=str(out), cid=created, process=owner.identity)), flush=True)
        deadline = time.monotonic() + 80
        while owner.exit_code() is None:
            require(not problems, "Q4C guard rejected window: " + "; ".join(problems))
            require(time.monotonic() <= deadline, "owned Q4C outer deadline exceeded")
            stop.wait(.1)
        window["exit_code"] = owner.exit_code()
        info = owned_info(created)
        window["terminal_container_state"] = info["State"]
        require(window["exit_code"] == 0 and not info["State"]["Running"] and info["State"]["Pid"] == 0
                and info["State"]["ExitCode"] == 0 and info["State"]["OOMKilled"] is False
                and info["State"]["Error"] == "", "owned Q4C component failed")
        reserve(18)
        health()
        replay_path = native / "replay/replay.json"
        replay_raw, replay_sha = capture(replay_path, maximum=1 << 20)
        replay = json.loads(replay_raw)
        require(replay["schema"] == "halogen0162.q4c-selected-row-original-kernel-oracle.v1"
                and replay["passed"] is True and replay["engine_sha256"] == ENGINE_SHA
                and replay["codeobject_sha256"] == CODE_SHA and replay["runtime_sha256"] == HIP_SHA
                and replay["included_scaffold_sha256"] == SCAFFOLD_SHA and replay["native_pack_sha256"] == PACK_SHA
                and replay["reference_sha256"] == REFERENCE_SHA and replay["cleanup_errors"] == 0
                and replay["file_close_errors"] == 0 and replay["immutable_files_rechecked"] is True
                and replay["selected_window_hashes_verified"] is True and replay["output_files_written"] == 4,
                "Q4C replay identity/cleanup receipt differs")
        names = {"vector-converted.u16", "vector-gathered.u16", "scalar-converted.u16", "scalar-gathered.u16"}
        converters = replay["converters"]
        require(len(converters) == 2 and {row["mode"] for row in converters} ==
                {"default-aligned-v8u2-optional-codebook-false", "scalar"}, "exact converter pair required")
        recorded = set()
        for row in converters:
            require(row["completed"] is True and row["converted_copied"] is True and row["gathered_copied"] is True
                    and row["converter_reference_mismatches"] == row["gather_converter_mismatches"] ==
                    row["gather_reference_mismatches"] == row["nonfinite_words"] == 0, "exact Q4C numerical gate differs")
            for kind in ("converted", "gathered"):
                name = row[kind + "_file"]
                require(name in names and name not in recorded, "Q4C output file identity differs")
                recorded.add(name)
                capture(native / "replay" / name, REFERENCE_SHA, 5120, 5120)
                require(row[kind + "_sha256"] == REFERENCE_SHA, "output receipt hash differs")
        require(recorded == names, "Q4C output set incomplete")
        recheck()
        window["replay_receipt_sha256"] = replay_sha
        window["passed"] = True
    except BaseException as error:
        window["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        cleanup_window()
        if controller:
            try:
                reserve(18)
                health()
                require(not problems, "continuous guard rejected original-server preservation")
                result["colleague_preserved"] = True
            except BaseException as error:
                result["errors"].append("final colleague check: " + str(error))
        stop.set()
        for monitor in monitors:
            if monitor.is_alive():
                monitor.join(25)
        result["monitor_stopped"] = not any(monitor.is_alive() for monitor in monitors)
        result["controller_handle_closed"] = controller is None
        if controller and result["monitor_stopped"]:
            try:
                controller.close()
                result["controller_handle_closed"] = True
            except BaseException as error:
                result["errors"].append("controller handle close: " + str(error))
        try:
            if latch_owned and result["monitor_stopped"] and result["controller_handle_closed"] and not window["cleanup_pending"]:
                require(capture(latch_path, maximum=65536)[0] == latch_bytes, "ownership latch identity changed")
                latch_path.unlink()
                latch_owned = False
        except BaseException as error:
            result["errors"].append("ownership latch close: " + str(error))
        result["ownership_latch_acquired"] = latch_acquired
        result["ownership_latch_released"] = latch_acquired and not latch_owned
        result["errors"].extend(problems)
        result["colleague_preserved"] = result["colleague_preserved"] and not problems
        result["minimum_physical_gib"] = min((row["available_bytes"] / 2**30 for row in samples), default=None)
        result["minimum_commit_gib"] = min((row["commit_headroom_bytes"] / 2**30 for row in samples), default=None)
        result["cleanup_pending"] = (window["cleanup_pending"] or not result["monitor_stopped"]
            or not result["controller_handle_closed"] or latch_owned)
        window["passed"] = window["passed"] and not window["errors"] and not result["errors"] and not result["cleanup_pending"]
        result["passed"] = window["passed"]
        write(out / "result.json", result)
        print(json.dumps(dict(out=str(out), passed=result["passed"], contaminated=result["contaminated"],
            errors=result["errors"] + window["errors"], cleanup_pending=result["cleanup_pending"])), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--root-runtime-reviewed", action="store_true")
    raise SystemExit(run(parser.parse_args()))
