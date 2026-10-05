"""ROOT-only three-window ROCr component launcher; never runs a model.

Execute only after ROOT reviews actual runtime/provider ownership. A frozen
JSON config supplies image, colleague CID, controller identity, health counters,
three regular HSA paths, and the passed static ABI gate path/SHA. The launcher
preserves that ready/idle server and cleans only its UUID-owned CID/job. No
automatic retry, library installation, global setting change, or engine restart.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "server/.local/optimization9h-20261004"
BACKEND = ROOT / "backends/halogen-wsl2-0.16.2"
PROBE = ROOT / "scripts/benchmarks/halogen_rocr_poll_backoff_probe.py"
FIXTURES = WORK / "embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e"
HSACO = WORK / "mtp-route-static-20261004/engine-gfx1151.hsaco"
IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
PROBE_SHA = "9b2f6dd62162cbed8ea51f767e018c787a69ebf03fa6e4cc8b6ef153fdf83f52"
LIBRARY_SHAS = {
    "stock": "1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5",
    "source_stock": "2ba2eafa07cfcedb3754a7708858f2c054bc07c9e4e24fe4820b5340cda95af5",
    "candidate": "cf1f4447cd92330c6a551042eff1ad95de2df4e276c09dfbfe7a252b5fa89434",
}
SUPPORT_SHAS = {
    ROOT / "server/host_frames.py": "417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8",
    ROOT / "server/winjob.py": "3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c",
    BACKEND / "scripts/runner.py": "14bed4dc8e3ef2a4dd1e7ea0393bac0c9e07a97ae8f3358227ac65b5525ffe0d",
    PROBE: PROBE_SHA,
    BACKEND / ".local/flash_serve": "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b",
    HSACO: "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83",
    FIXTURES / "fixtures.json": "cf7ae0ed36d323ae32b6664ed080bc2b3cdd44863878d51719b53ddef9f72246",
    FIXTURES / "raw-gamma.u16": "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86",
}
LABEL = "alloy.rocr-component-owner"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def capture(path, expected=None, maximum=64 << 20):
    path = Path(path)
    require(path.is_absolute(), "absolute input path required")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, "bounded regular file required: " + str(path))
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


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


class ControllerIdentity:
    """Independent read-only retained handle; never owns the colleague process."""
    def __init__(self, expected):
        self.expected, self.handle = expected, None
        api = self.api = C.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ("GetProcessId", [W.HANDLE], W.DWORD),
            ("GetProcessTimes", [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
            ("QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            ("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            ("CloseHandle", [W.HANDLE], W.BOOL),
        ):
            function = getattr(api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = api.OpenProcess(0x1000 | 0x100000, False, expected["pid"])
        require(self.handle, "cannot retain read-only colleague controller handle")
        try:
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        api, handle = self.api, self.handle
        require(handle and api.WaitForSingleObject(handle, 0) == 258, "colleague controller is no longer live")
        times = [W.FILETIME() for _ in range(4)]
        require(api.GetProcessTimes(handle, *(C.byref(value) for value in times)), "controller creation time unavailable")
        image, length = C.create_unicode_buffer(32768), W.DWORD(32768)
        require(api.QueryFullProcessImageNameW(handle, 0, image, C.byref(length)), "controller executable unavailable")
        live = {"pid": int(api.GetProcessId(handle)),
                "creation_time_100ns": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                "executable": image.value}
        require(live["pid"] == self.expected["pid"] and live["creation_time_100ns"] == self.expected["creation_time_100ns"]
                and os.path.normcase(live["executable"]) == os.path.normcase(self.expected["executable"]),
                "colleague controller PID identity differs")
        return live

    def close(self):
        if self.handle:
            require(self.api.CloseHandle(self.handle), "read-only controller handle close failed")
            self.handle = None


def run(args):
    require(os.name == "nt" and args.root_runtime_reviewed, "ROOT Windows runtime/ownership review acknowledgment required")
    capture(Path(__file__).absolute(), args.source_sha256)
    raw, _ = capture(Path(args.config), args.config_sha256, 65536)
    config = json.loads(raw)
    require(config["schema"] == "halogen.rocr-component-owned-config.v1" and config["image"] == IMAGE, "frozen image/config differs")
    require(re.fullmatch(r"[0-9a-f]{64}", config["colleague_cid"]), "exact colleague CID required")
    expected = config["controller"]
    require(re.fullmatch(r"[0-9a-f]{32}", expected["run_id"]) and type(expected["pid"]) is int
            and expected["pid"] > 0 and type(expected["creation_time_100ns"]) is int
            and expected["creation_time_100ns"] > 0 and Path(expected["executable"]).is_absolute()
            and expected["context"] == 262144 and expected["port"] == 8840
            and re.fullmatch(r"[0-9a-f]{64}", expected["profile_sha256"]), "frozen controller identity required")
    require(config["health"] == {"completed": 20, "cancelled": 0}, "expected health counters differ")
    libraries = {variant: Path(config["libraries"][variant]) for variant in LIBRARY_SHAS}
    pins = {**SUPPORT_SHAS, **{libraries[key]: value for key, value in LIBRARY_SHAS.items()},
            Path(args.config): args.config_sha256, Path(__file__).absolute(): args.source_sha256}
    for path, wanted in pins.items():
        capture(path, wanted)
    gate_path, gate_sha = Path(config["abi_gate"]["path"]), config["abi_gate"]["sha256"]
    gate = json.loads(capture(gate_path, gate_sha, 2 << 20)[0])
    require(gate["schema"] == "halogen.rocr-private-static-abi-gate.v1" and gate["passed"] is True
            and gate["errors"] == [] and gate["unresolved_dependency_availability"] == []
            and gate["checks"]["stock_patched_interface_equal"] is True
            and all(gate["checks"][key]["strong_unversioned_import_closure"]["unresolved"] == []
                    for key in ("source_stock", "patched")), "passed static ABI/dependency/import gate required")
    for variant, key in (("stock", "original"), ("source_stock", "source_stock"), ("candidate", "patched")):
        require(gate[key]["sha256"] == LIBRARY_SHAS[variant], "ABI gate library binding differs")
    pins[gate_path] = gate_sha
    sys.path.insert(0, str(ROOT / "server"))
    from host_frames import frame
    from winjob import OwnedProcess
    sys.path.insert(0, str(BACKEND / "scripts"))
    import runner as backend
    backend.configure()
    token = (BACKEND / ".local/api-token.txt").read_text(encoding="ascii").strip()
    require(token, "colleague health authorization unavailable")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), backend.NoRedirect())
    out = WORK / ("alloy-rocr-component-" + uuid.uuid4().hex)
    out.mkdir()
    result = {"schema": "halogen.rocr-component-owned.v1", "passed": False, "contaminated": False,
              "errors": [], "windows": [], "config_sha256": args.config_sha256,
              "source_sha256": args.source_sha256, "probe_sha256": PROBE_SHA, "abi_gate_sha256": gate_sha,
              "image": IMAGE, "root_runtime_reviewed": True, "colleague_preserved": True}
    controller = None
    stop, ready_memory, ready_health = threading.Event(), threading.Event(), threading.Event()
    cleanup_lock = threading.RLock()
    current = {"cid": None, "name": None, "tag": None}
    samples = []
    problems = []

    def owned_info(cid):
        info = backend.inspect(cid)
        require(info["Id"] == cid and info["Name"] == "/" + current["name"]
                and info["Config"]["Image"] == IMAGE
                and (info["Config"].get("Labels") or {}).get(LABEL) == current["tag"], "own CID/name/image/label identity differs")
        return info

    def fail(message):
        problems.append(message)
        result["contaminated"] = True
        with cleanup_lock:
            cid = current["cid"]
            if cid:
                try:
                    if owned_info(cid)["State"]["Running"]:
                        backend.docker("stop", "-t", "0", cid, timeout=20)
                except BaseException as error:
                    problems.append("guard own-CID stop: " + str(error))

    def reserve(floor):
        controller.verify()
        state = json.loads((ROOT / "server/.local/current.json").read_text(encoding="utf-8-sig"))
        require(state.get("run_id") == expected["run_id"] and state.get("pid") == expected["pid"]
                and state.get("phase") == "ready" and state.get("active_requests") == 0
                and state.get("context") == expected["context"] and state.get("port") == expected["port"]
                and state.get("profile_sha256") == expected["profile_sha256"]
                and 0 <= time.time() - state.get("heartbeat", 0) <= 10, "colleague identity/readiness/idle heartbeat changed")
        sample = {"epoch": time.time(), **frame()}
        samples.append(sample)
        require(min(sample["available_bytes"], sample["commit_headroom_bytes"]) >= floor * 2**30, "host physical/commit reserve below " + str(floor) + "GiB")
        return {**sample, "run_id": state["run_id"], "pid": state["pid"], "heartbeat": state["heartbeat"], "active_requests": 0}

    def health():
        request = urllib.request.Request("http://127.0.0.1:8840/health", headers={"Authorization": "Bearer " + token})
        with opener.open(request, timeout=2) as response:
            raw = response.read((1 << 20) + 1)
            require(response.status == 200 and len(raw) <= 1 << 20, "colleague health response unavailable")
        value = json.loads(raw)
        require(value.get("status") == "ok" and value.get("active_requests") == 0 and value.get("draining") is False
                and value.get("completed") == 20 and value.get("cancelled") == 0
                and value.get("context") == 262144, "colleague request started or health/completed counters changed")
        return {"epoch": time.time(), "health": value}

    def watch(name, event, function):
        try:
            with (out / name).open("x", encoding="utf-8") as stream:
                while not stop.is_set():
                    stream.write(json.dumps(function(), allow_nan=False) + "\n")
                    stream.flush()
                    event.set()
                    stop.wait(.25)
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
        info = backend.inspect(config["colleague_cid"])
        require(info["Id"] == config["colleague_cid"] and info["Config"]["Image"] == IMAGE
                and info["State"]["Running"] is True, "expected colleague container image/CID differs")
        require(set(backend.docker("ps", "-q", "--no-trunc", timeout=10).split()) == {config["colleague_cid"]}, "unexpected active container; component window deferred")

    try:
        controller = ControllerIdentity(expected)
        write(out / "config.json", config)
        reserve(22)
        health()
        for monitor in monitors:
            monitor.start()
        require(ready_memory.wait(2) and ready_health.wait(2) and not problems, "continuous guard failed before create")
        for variant, hsa_path in libraries.items():
            admission()
            directory = out / variant
            directory.mkdir()
            native = directory / "result"
            native.mkdir()
            tag = uuid.uuid4().hex
            current.update(cid=None, name="alloy-rocr-component-" + variant + "-" + tag, tag=tag)
            window = {"variant": variant, "hsa_sha256": LIBRARY_SHAS[variant], "container_id": None,
                      "container_name": current["name"], "ownership_label": tag, "passed": False,
                      "container_removed": False, "job_closed": False, "create_attempted": False,
                      "create_identity_recovered": False, "cleanup_pending": False, "errors": []}
            result["windows"].append(window)
            owner = None
            mounts = {"/candidate/probe.py": backend.linux_path(PROBE),
                      "/candidate/flash_serve": backend.linux_path(BACKEND / ".local/flash_serve"),
                      "/candidate/engine-gfx1151.hsaco": backend.linux_path(HSACO),
                      "/fixtures": backend.linux_path(FIXTURES),
                      "/usr/lib/libdxcore.so": "/usr/lib/wsl/lib/libdxcore.so",
                      "/usr/lib/librocdxg.so": backend.MACHINE["dxg"],
                      "/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1": backend.linux_path(BACKEND / ".local/librocroller-compat.so.1"),
                      "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libhsa-runtime64.so.1": backend.linux_path(hsa_path)}
            argv = ["create", "--name", current["name"], "--label", LABEL + "=" + tag,
                    "--network=none", "--restart=no", "--read-only", "--device=/dev/dxg",
                    "--memory=2g", "--memory-swap=2g", "--pids-limit=128", "--ipc=private", "--shm-size=64m",
                    "--ulimit=core=0:0", "--ulimit=memlock=-1:-1", "--security-opt=seccomp=unconfined",
                    "--security-opt=label=disable", "--tmpfs=/tmp:rw,size=64m"]
            for destination, source in sorted(mounts.items()):
                argv += ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
            argv += ["--mount", "type=bind,src=" + backend.linux_path(native) + ",dst=/result",
                     "--env=HSA_ENABLE_DXG_DETECTION=1", "--env=HSA_ENABLE_SDMA=1", "--env=HALOGEN_LQ8_WAVE=1",
                     "--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1",
                     "--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
                     "--entrypoint=timeout", IMAGE, "--signal=TERM", "--kill-after=5s", "60s",
                     "python3", "/candidate/probe.py", "probe", "--variant", variant,
                     "--source-sha256", PROBE_SHA, "--hsa-sha256", LIBRARY_SHAS[variant],
                     "--output", "/result", "--outer-owned-gpu-guard"]
            write(directory / "plan.json", {"argv": argv, "models_mounted": False, "admission_gib": 22, "reserve_gib": 18, "outer_deadline_seconds": 80})
            try:
                admission()
                window["create_attempted"] = True
                created = backend.docker(*argv, timeout=20).strip()
                require(re.fullmatch(r"[0-9a-f]{64}", created), "created CID invalid")
                current["cid"] = created
                window["container_id"] = created
                info = owned_info(created)
                require(not info["State"]["Running"], "own container unexpectedly started")
                admission()
                wsl = Path(os.environ["WINDIR"]) / "System32/wsl.exe"
                try:
                    owner = OwnedProcess([str(wsl), *backend.WSL[1:], "docker", "start", "-a", created],
                                         cwd=ROOT, env=dict(os.environ), stdout_path=directory / "stdout.txt", stderr_path=directory / "stderr.txt")
                except BaseException as error:
                    owner = getattr(error, "owner", None)
                    if owner is not None:
                        window["process_identity"] = owner.identity
                    raise
                window["process_identity"] = owner.identity
                write(directory / "retained-process.json", window)
                owner.verify_live_identity()
                with cleanup_lock:
                    admission()
                    require(not problems, "guard failed before owned process resume")
                    owner.resume()
                print(json.dumps({"out": str(directory), "variant": variant, "cid": created, "process": owner.identity}), flush=True)
                deadline = time.monotonic() + 80
                while owner.exit_code() is None:
                    require(not problems, "component guard rejected window: " + "; ".join(problems))
                    require(time.monotonic() <= deadline, "owned component outer deadline exceeded")
                    stop.wait(.1)
                window["exit_code"] = owner.exit_code()
                info = owned_info(created)
                window["terminal_container_state"] = info["State"]
                require(window["exit_code"] == 0 and not info["State"]["Running"]
                        and info["State"]["ExitCode"] == 0 and not info["State"]["OOMKilled"], "owned component failed")
                reserve(18)
                health()
                probe_raw, probe_sha = capture(native / "probe.json", maximum=1 << 20)
                receipt = json.loads(probe_raw)
                require(receipt["passed"] is True and receipt["variant"] == variant and receipt["cleanup_errors"] == []
                        and receipt["bindings"]["source"]["sha256"] == PROBE_SHA
                        and receipt["bindings"]["hsa"]["sha256"] == LIBRARY_SHAS[variant], "probe identity/cleanup receipt differs")
                window["probe_receipt_sha256"] = probe_sha
                window["passed"] = True
            except BaseException as error:
                window["errors"].append(type(error).__name__ + ": " + str(error))
            finally:
                with cleanup_lock:
                    try:
                        if window["create_attempted"] and not current["cid"]:
                            found = backend.docker("ps", "-aq", "--no-trunc", "--filter", "name=^/" + current["name"] + "$",
                                                   "--filter", "label=" + LABEL + "=" + tag, timeout=20).split()
                            require(len(found) == 1, "ambiguous create outcome remains unproven; no unrelated cleanup")
                            current["cid"] = found[0]
                            owned_info(found[0])
                            window.update(container_id=found[0], create_identity_recovered=True)
                        if current["cid"]:
                            info = owned_info(current["cid"])
                            if info["State"]["Running"]:
                                backend.docker("stop", "-t", "0", current["cid"], timeout=20)
                            info = owned_info(current["cid"])
                            require(not info["State"]["Running"] and info["State"]["Pid"] == 0, "own container remained live")
                            window["terminal_container_state"] = info["State"]
                            backend.docker("rm", current["cid"], timeout=20)
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
                window["cleanup_pending"] = (window["create_attempted"] and not window["container_removed"] or owner is not None and not window["job_closed"])
                window["passed"] = window["passed"] and not window["errors"] and not window["cleanup_pending"] and not problems
                write(directory / "owned-result.json", window)
            require(window["passed"], "window failed; no retry or later variant: " + variant)
        for path, wanted in pins.items():
            capture(path, wanted)
        reserve(18)
        health()
        spec = importlib.util.spec_from_file_location("rocr_component_offline_compare", PROBE)
        comparison = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(comparison)
        for baseline, filename in (("stock", "installed-comparison.json"), ("source_stock", "patch-comparison.json")):
            comparison.compare(argparse.Namespace(stock=str(out / baseline / "result/probe.json"),
                                                 candidate=str(out / "candidate/result/probe.json"), output=str(out / filename)))
        require(not problems, "continuous guard rejected cohort")
        result["passed"] = True
    except BaseException as error:
        result["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        stop.set()
        for monitor in monitors:
            if monitor.is_alive():
                monitor.join(25)
        result["monitor_stopped"] = not any(monitor.is_alive() for monitor in monitors)
        result["errors"].extend(problems)
        result["controller_handle_closed"] = controller is None
        if controller and result["monitor_stopped"]:
            try:
                controller.close()
                result["controller_handle_closed"] = True
            except BaseException as error:
                result["errors"].append(str(error))
        result["minimum_physical_gib"] = min((row["available_bytes"] / 2**30 for row in samples), default=None)
        result["minimum_commit_gib"] = min((row["commit_headroom_bytes"] / 2**30 for row in samples), default=None)
        result["cleanup_pending"] = (not result["monitor_stopped"] or not result["controller_handle_closed"]
                                     or any(row["cleanup_pending"] for row in result["windows"]))
        result["passed"] = result["passed"] and not result["errors"] and not result["cleanup_pending"]
        write(out / "result.json", result)
        print(json.dumps({"out": str(out), "passed": result["passed"], "contaminated": result["contaminated"], "errors": result["errors"]}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--root-runtime-reviewed", action="store_true")
    raise SystemExit(run(parser.parse_args()))
