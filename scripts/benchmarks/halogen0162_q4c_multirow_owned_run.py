"""ROOT-only exact64-row original Q4C/RMS accuracy window; no model mounted.

A fresh frozen JSON config supplies the independently hashed compiled binary,
manifest directory/receipt, and current original server identity. Review
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
import struct
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
PRODUCER_PLAN = WORK / "early64-plan-3fc1648d90a1436da89e47213a749bfe.json"
CANDIDATES = WORK / "early64-candidates-40e19242264d414e91a2570f8e964e0e"
HARNESS = ROOT / "scripts/benchmarks/halogen0162_q4c_multirow_oracle.c"
PREPARER = ROOT / "scripts/benchmarks/halogen0162_q4c_multirow_oracle_prepare.py"
PRODUCER = ROOT / "scripts/benchmarks/halogen_mtp_early_token_producer.py"
SCAFFOLD = ROOT / "scripts/benchmarks/halogen0162_embedding_rms_replay.c"
PRODUCER_PLAN_SHA = "cfbf862eaea8c3e3b9e65f7136664fc03bea55cff063dadb6e7ec67b3136f6a7"
HARNESS_SHA = "d1da5ea77fc4ed66f05a1fa03f34aaa1607f8c944a5e0da3b4e8b2a9278cab56"
PREPARER_SHA = "e32c9b4c3612fc25827ead683765160167b84371f6c7241fa3723162da0bcbd9"
PRODUCER_SHA = "56ebe190cdbdc47a50b6c6930172cb6cf274f04995276100c4c8537325ee1da5"
SCAFFOLD_SHA = "7ea99028014f590a0938d5a06790f51ce571948706d851c16bfcb72f694f4fa8"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
HIP_PATH = "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"
HIP_SHA = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
GAMMA_SHA = "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86"
BINARY_SHA = "c159ff52b902ab2ff9b480fe01cd3bb1de5b0e276569722501d5c9214afa90c6"
BACKEND_CONTROLLER = dict(pid=24960, run_id="babc627cdc474863b0aa8b2104297d4c")
DXG = "/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocdxg.so.1"
LABEL = "alloy.q4c-multirow-owner"
ROCROLLER = BACKEND / ".local/librocroller-compat.so.1"
PIN_EXTENTS = {ROCROLLER: 465578929}
PINS = {
    PATTERN: "bd2945ae634248e63ce2b008c2cbbdc17ac1af7f47a3a97082c8d36a41955c4f",
    ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    ROOT / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c",
    HARNESS: HARNESS_SHA, PREPARER: PREPARER_SHA, PRODUCER: PRODUCER_SHA,
    SCAFFOLD: SCAFFOLD_SHA, PRODUCER_PLAN: PRODUCER_PLAN_SHA,
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


def native_unc(value):
    require(isinstance(value, str) and re.fullmatch(r"/home/revn/halogen-re/[a-z0-9][a-z0-9-]{0,127}", value),
            "bounded root-reviewed native binary path required")
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
    require(set(config) == {"schema", "image", "colleague_cid", "controller", "health", "binary", "oracle", "complete_sha256"}
            and config.get("schema") == "halogen0162.q4c-multirow-owned-config.v1" and config.get("image") == IMAGE
            and config.get("colleague_cid") == COLLEAGUE_CID and config.get("controller") == CONTROLLER
            and config.get("health") == HEALTH, "frozen original-server identity/config differs")
    binary = config["binary"]
    require(set(binary) == {"native_path", "sha256"}, "exact reviewed binary config required")
    binary_sha = sha(binary["sha256"])
    require(binary_sha == BINARY_SHA, "root-reviewed exact64 compiled binary SHA differs")
    binary_unc = native_unc(binary["native_path"])
    oracle = config["oracle"]
    require(set(oracle) == {"directory", "plan_sha256", "manifest_sha256"}, "exact oracle manifest config required")
    oracle_directory = Path(oracle["directory"])
    require(oracle_directory.is_absolute() and oracle_directory.resolve().parent == WORK.resolve(),
            "root-reviewed oracle directory must be a direct child of the owned work directory")
    oracle_plan_sha, manifest_sha = sha(oracle["plan_sha256"]), sha(oracle["manifest_sha256"])
    complete_sha = sha(config["complete_sha256"])
    oracle_plan_path, manifest_path = oracle_directory / "oracle-plan.json", oracle_directory / "oracle-manifest.bin"
    pins = {**PINS, config_path: args.config_sha256, source_path: sha(args.source_sha256),
            binary_unc: binary_sha, CANDIDATES / "complete.json": complete_sha,
            oracle_plan_path: oracle_plan_sha, manifest_path: manifest_sha}
    for path, wanted in pins.items():
        verify_pin(path, wanted, extent=PIN_EXTENTS.get(path))
    machine = json.loads(capture(BACKEND / ".local/machine.json", PINS[BACKEND / ".local/machine.json"], 65536)[0])
    require(machine["image"] == IMAGE and machine["dxg"] == DXG
            and machine["distro"] == "Ubuntu-24.04" and machine["user"] == "revn",
            "installed original DXG/distro/user binding differs")
    producer_plan = json.loads(capture(PRODUCER_PLAN, PRODUCER_PLAN_SHA, 2 << 20)[0])
    complete = json.loads(capture(CANDIDATES / "complete.json", complete_sha, 2 << 20)[0])
    plan = json.loads(capture(oracle_plan_path, oracle_plan_sha, 2 << 20)[0])
    tokens = producer_plan["producer_tokens"]
    require(type(tokens) is list and len(tokens) == 64 and len(set(tokens)) == 64
            and all(type(token) is int and 0 <= token < 248320 for token in tokens), "exact64 sealed original token list required")
    require(producer_plan["schema"] == "halogen0162.early-token-producer-plan.v1"
            and producer_plan["producer_sha256"] == PRODUCER_SHA
            and complete["schema"] == "halogen0162.early-token-producer-candidates.v1" and complete["completed"] is True
            and complete["plan_sha256"] == PRODUCER_PLAN_SHA and complete["producer_sha256"] == PRODUCER_SHA
            and complete["candidate_tokens"] == tokens and complete["schedule"] == producer_plan["schedule"]
            and complete["generation_hex"] == producer_plan["schedule"]["generation_hex"]
            and complete["sequence"] == producer_plan["schedule"]["sequence"]
            and complete["checkpoint_payload_bytes_read"] == 194688, "exact64 completed producer binding differs")
    require(plan["schema"] == "halogen0162.q4c-multirow-oracle-plan.v1"
            and plan["preparer_sha256"] == PREPARER_SHA and plan["harness_sha256"] == HARNESS_SHA
            and plan["included_scaffold_sha256"] == SCAFFOLD_SHA and plan["producer_sha256"] == PRODUCER_SHA
            and plan["producer_plan_sha256"] == PRODUCER_PLAN_SHA and plan["complete_sha256"] == complete_sha
            and plan["generation_hex"] == complete["generation_hex"] and plan["sequence"] == complete["sequence"]
            and plan["original_tokens"] == tokens and plan["selected_rows"] == 64 and plan["width"] == 2560
            and plan["pack_bytes"] == 92224 and plan["scale_offset"] == 81984
            and plan["vector_grid"] == [40, 1, 1] and plan["scalar_grid"] == [64, 1, 1]
            and plan["rms_grid"] == [1, 1, 1] and plan["block"] == [256, 1, 1]
            and plan["native_kernel_calls"] == 66 and plan["expected_copies"] == 70
            and plan["device_allocation_bytes"] == 425024 and plan["payload_bytes_read"] == 0,
            "reviewed exact64 oracle plan/ABI differs")
    require(plan["manifest"] == dict(file="oracle-manifest.bin", bytes=8648, sha256=manifest_sha,
            byte_order="little", header_bytes=200, row_record_bytes=132), "sealed binary manifest record differs")
    for value, keys in ((complete, ("FC_weight_payload_read", "hidden_payload_read", "CPU_FC_executed", "native_FC_skip_admitted",
                                   "live_publication_implemented", "npu_executed", "speed_claim")),
                        (plan, ("GPU_executed", "numerical_parity_qualified", "original_full_table_loader_qualified", "live_allocation_qualified",
                                "general_table_parity_qualified", "gather_replayed", "live_generation_binding_proved", "native_FC_skip_admitted",
                                "full_D_parity_qualified", "full_head_qualified", "FC_executed", "npu_executed", "speed_claim",
                                "tolerance_adjustment", "arithmetic_fitting"))):
        require(all(value[key] is False for key in keys), "broader candidate/oracle gate was admitted")
    require(complete["gate_status"] == producer_plan["gate_status"]
            and all(value is False for value in complete["gate_status"].values()), "candidate arithmetic/live gates must remain false")
    files = complete["files"]
    require(type(files) is list and len(files) == 323, "exact64 candidate file list required")
    file_map = {}
    for item in files:
        require(set(item) == {"file", "bytes", "sha256"} and item["file"] not in file_map, "unique exact candidate file records required")
        sha(item["sha256"])
        file_map[item["file"]] = item
    def fixture(name, extent):
        item = file_map[name]
        require(item["file"] == name and type(item["bytes"]) is int and item["bytes"] == extent, "candidate file extent differs")
        return sha(item["sha256"]), extent
    pack_sha, _ = fixture("selected-rows.q4c", 92224)
    tokens_sha, _ = fixture("tokens.i32", 256)
    require(fixture("raw-gamma.u16", 5120)[0] == GAMMA_SHA, "unchanged original raw gamma differs")
    payloads = {CANDIDATES / name: fixture(name, extent) for name, extent in
                (("selected-rows.q4c", 92224), ("tokens.i32", 256), ("raw-gamma.u16", 5120))}
    require(len(complete["rows"]) == 64 and len(complete["observed_source_ranges"]) == len(producer_plan["source_ranges"]),
            "exact64 row/window records required")
    windows = {}
    for actual, planned in zip(complete["observed_source_ranges"], producer_plan["source_ranges"]):
        require(set(actual) == set(planned) | {"observed_sha256"} and {key: actual[key] for key in planned} == planned,
                "observed original source window identity/order differs")
        windows[(actual["kind"], actual["token"])] = sha(actual["observed_sha256"])
    expected_manifest = bytearray(struct.pack("<8sII16sQ", b"HGMROW1\0", 64, 2560,
        bytes.fromhex(complete["generation_hex"]), complete["sequence"]))
    for digest in (complete_sha, PRODUCER_PLAN_SHA, PRODUCER_SHA, pack_sha, tokens_sha):
        expected_manifest.extend(bytes.fromhex(digest))
    for index, token_id in enumerate(tokens):
        row = complete["rows"][index]
        prefix = f"{index:03d}-token{token_id}-"
        raw_name, norm_name = prefix + "raw.u16", prefix + "norm.u16"
        raw_sha, _ = fixture(raw_name, 5120)
        norm_sha, _ = fixture(norm_name, 5120)
        require(row["index"] == index and row["token"] == token_id and row["shape"] == [1, 2560]
                and row["raw_BF16_sha256"] == raw_sha and row["norm_BF16_sha256"] == norm_sha
                and row["arbitrary_row_native_parity_admitted"] is False and row["native_FC_skip_admitted"] is False,
                "candidate raw/normalized reference identity differs")
        payloads[CANDIDATES / raw_name] = (raw_sha, 5120)
        payloads[CANDIDATES / norm_name] = (norm_sha, 5120)
        expected_manifest.extend(struct.pack("<I", token_id))
        for digest in (raw_sha, norm_sha, windows[("codes", token_id)], windows[("scales", token_id)]):
            expected_manifest.extend(bytes.fromhex(digest))
    require(capture(manifest_path, manifest_sha, 8648, 8648)[0] == bytes(expected_manifest),
            "binary manifest differs from exact root-sealed producer request/reference/window metadata")

    def recheck():
        for path, wanted in pins.items():
            verify_pin(path, wanted, extent=PIN_EXTENTS.get(path))
        for path, (wanted, extent) in payloads.items():
            verify_pin(path, wanted, extent, extent)

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
    out = WORK / ("q4c-multirow-owned-" + tag)
    out.mkdir()
    result = dict(schema="halogen0162.q4c-multirow-owned.v1", passed=False, contaminated=False,
        errors=[], source_sha256=args.source_sha256, config_sha256=args.config_sha256,
        image=IMAGE, binary_sha256=binary_sha, complete_sha256=complete_sha, oracle_plan_sha256=oracle_plan_sha,
        manifest_sha256=manifest_sha, exact_original_tokens=tokens, selected_rows=64,
        models_mounted=False, root_runtime_reviewed=True, colleague_preserved=False,
        original_full_table_loader_qualified=False, live_allocation_qualified=False, native_FC_skip_admitted=False,
        live_generation_binding_proved=False, full_D_parity_qualified=False, full_head_qualified=False,
        FC_executed=False, npu_executed=False, speed_claim=False)
    window = dict(container_id=None, container_name="alloy-q4c-multirow-" + tag, ownership_label=tag,
        passed=False, container_removed=False, job_closed=False, create_attempted=False,
        create_identity_recovered=False, cleanup_pending=False, errors=[])
    result["window"] = window
    current = {"cid": None}
    controller = owner = None
    stop, ready_memory, ready_health = threading.Event(), threading.Event(), threading.Event()
    cleanup_lock = threading.RLock()
    problems, samples = [], []
    # Share the original Q4C ownership latch; separate labels never weaken mutual exclusion.
    latch_path = WORK / "q4c-row-owned.lock"
    latch_bytes = (json.dumps(dict(schema="halogen0162.q4c-multirow-owned-lock.v1", tag=tag,
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
        with (BACKEND / ".local/current-service.json").open("rb") as stream:
            backend_raw = stream.read((1 << 20) + 1)
        require(len(backend_raw) <= 1 << 20, "backend-state ceiling exceeded")
        backend_state = json.loads(backend_raw.decode("utf-8-sig"))
        require(backend_state.get("run_id") == BACKEND_CONTROLLER["run_id"]
                and backend_state.get("controller_pid") == BACKEND_CONTROLLER["pid"]
                and backend_state.get("phase") == "ready" and backend_state.get("context") == CONTROLLER["context"]
                and backend_state.get("checkpoint") == "v2" and backend_state.get("container_id") == COLLEAGUE_CID,
                "original backend controller/run/CID/readiness changed")
        heartbeat_path = BACKEND / ".local/services" / BACKEND_CONTROLLER["run_id"] / "controller.json"
        with heartbeat_path.open("rb") as stream:
            backend_heartbeat_raw = stream.read((1 << 20) + 1)
        require(len(backend_heartbeat_raw) <= 1 << 20, "backend-heartbeat ceiling exceeded")
        backend_heartbeat = json.loads(backend_heartbeat_raw)
        require(backend_heartbeat.get("run_id") == BACKEND_CONTROLLER["run_id"]
                and 0 <= time.time() - backend_heartbeat.get("time", 0) <= 10,
                "original backend controller heartbeat changed or stale")
        sample = {"epoch": time.time(), **frame()}
        samples.append(sample)
        require(min(sample["available_bytes"], sample["commit_headroom_bytes"]) >= floor * 2**30,
                "host physical/commit reserve below " + str(floor) + "GiB")
        return {**sample, "run_id": state["run_id"], "pid": state["pid"],
                "heartbeat": state["heartbeat"], "active_requests": 0,
                "backend_run_id": BACKEND_CONTROLLER["run_id"], "backend_pid": BACKEND_CONTROLLER["pid"],
                "backend_heartbeat": backend_heartbeat["time"]}

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
            "/candidate/q4c-multirow-oracle": binary["native_path"],
            "/candidate/halogen0162_q4c_multirow_oracle.c": linux_path(HARNESS),
            "/candidate/halogen0162_embedding_rms_replay.c": linux_path(SCAFFOLD),
            "/candidate/oracle-manifest.bin": linux_path(manifest_path),
            "/candidate/flash_serve": linux_path(ENGINE),
            "/candidate/engine-gfx1151.hsaco": linux_path(HSACO),
            "/fixtures": linux_path(CANDIDATES),
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
            "/candidate/q4c-multirow-oracle", "/candidate/flash_serve", "/candidate/engine-gfx1151.hsaco", HIP_PATH, HIP_SHA,
            "/fixtures", "/candidate/oracle-manifest.bin", manifest_sha, "/result/replay"]
        write(out / "plan.json", dict(argv=argv, mounts=mounts, models_mounted=False, device_allocation_bytes=425024,
            native_kernel_calls=66, selected_rows=64, manifest_sha256=manifest_sha, complete_sha256=complete_sha,
            producer_plan_sha256=PRODUCER_PLAN_SHA, original_tokens=tokens, backend_controller=BACKEND_CONTROLLER,
            original_full_table_loader_qualified=False, live_allocation_qualified=False, native_FC_skip_admitted=False,
            npu_executed=False, speed_claim=False,
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
        expected = dict(schema="halogen0162.q4c-multirow-original-kernel-oracle.v1", passed=True,
            manifest_sha256=manifest_sha, complete_sha256=complete_sha, producer_plan_sha256=PRODUCER_PLAN_SHA,
            producer_sha256=PRODUCER_SHA, generation_hex=complete["generation_hex"], sequence=complete["sequence"],
            selected_rows=64, width=2560, engine_sha256=ENGINE_SHA, codeobject_sha256=CODE_SHA,
            runtime_sha256=HIP_SHA, included_scaffold_sha256=SCAFFOLD_SHA, codeobject_engine_offset=331776,
            codeobject_bytes=17704408, pack_sha256=pack_sha, tokens_sha256=tokens_sha, raw_gamma_sha256=GAMMA_SHA,
            selected_window_hashes_verified=True, pack_bytes=92224, code_offset=64, scale_offset=81984, scale_stride=160,
            vector_kernel="_ZN7halogen12_GLOBAL__N_114k_deq_q4cp_v8uILi2ELb0EEEvPKhPtjjllllNS0_5DeqCbE",
            scalar_kernel="_ZN7halogen12_GLOBAL__N_110k_deq_q4cpEPKhPtlllll",
            rms_kernel="_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii",
            vector_grid=[40,1,1], scalar_grid=[64,1,1], rms_grid=[1,1,1], block=[256,1,1], shared_bytes=0,
            default_stream=True, hidden_ABI_supplied_by_HIP=True, vector_blocks_per_row=320, vector_total_blocks=20480,
            vector_optional_codebook_all_zero=True, rms_groups=1, rms_input_output_alias=True, raw_gamma_copied_unchanged=True,
            device_allocation_bytes=425024, selected_rows_raw_parity_qualified=True, selected_rows_RMS_parity_qualified=True,
            original_full_table_loader_qualified=False, live_allocation_qualified=False, general_table_parity_qualified=False,
            gather_replayed=False, live_generation_binding_proved=False, native_FC_skip_admitted=False,
            full_D_parity_qualified=False, full_head_qualified=False, FC_executed=False, hidden_payload_read=False,
            npu_executed=False, supported_fabric_clock_overlap_qualified=False, concurrent_GPU_NPU_inference_allowed=False,
            acceptance_claim=False, speed_claim=False, tolerance_adjustment=False, arithmetic_fitting=False,
            launch_attempts=66, launches_ok=66, synchronizations_ok=66, copies_ok=70, allocations_ok=3, free_ok=3,
            module_loads=1, module_unloads=1, cleanup_errors=0, file_close_errors=0,
            immutable_files_rechecked=True, output_files_written=3, error="", error_code=0)
        require(all(type(replay.get(key)) is type(value) and replay.get(key) == value for key, value in expected.items()),
                "exact64 original-kernel ABI/identity/arithmetic/cleanup receipt differs")
        output_bytes = {}
        for kind, name in (("vector_raw", "vector-raw.u16"), ("scalar_raw", "scalar-raw.u16"),
                           ("native_norm", "vector-native-norm.u16")):
            require(replay[kind + "_file"] == name and replay[kind + "_bytes"] == 327680,
                    "exact64 native output name/extent differs")
            output_bytes[kind] = capture(native / "replay" / name, sha(replay[kind + "_sha256"]), 327680, 327680)[0]
        require(type(replay["rows"]) is list and len(replay["rows"]) == 64, "all64 native row receipts required")
        for index, token_id in enumerate(tokens):
            row, candidate = replay["rows"][index], complete["rows"][index]
            row_expected = dict(index=index, token=token_id, raw_reference_sha256=candidate["raw_BF16_sha256"],
                norm_reference_sha256=candidate["norm_BF16_sha256"], vector_copied=True, scalar_copied=True, rms_copied=True,
                vector_raw_mismatches=0, scalar_raw_mismatches=0, native_norm_mismatches=0,
                first_vector_raw_index_or_width=2560, first_scalar_raw_index_or_width=2560, first_native_norm_index_or_width=2560,
                vector_raw_nonfinite=0, scalar_raw_nonfinite=0, native_norm_nonfinite=0)
            require(all(type(row.get(key)) is type(value) and row.get(key) == value for key, value in row_expected.items()),
                    "original token/raw/RMS exact-word native row gate differs")
            for kind, reference_sha in (("vector_raw", candidate["raw_BF16_sha256"]),
                                        ("scalar_raw", candidate["raw_BF16_sha256"]),
                                        ("native_norm", candidate["norm_BF16_sha256"])):
                actual_sha = hashlib.sha256(output_bytes[kind][index * 5120:(index + 1) * 5120]).hexdigest()
                require(actual_sha == reference_sha == row[kind + "_sha256"],
                        "independently hashed native output row differs from sealed candidate/reference receipt")
        recheck()
        capture(replay_path, replay_sha, 1 << 20)
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
