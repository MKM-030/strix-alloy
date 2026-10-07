"""Fresh VitisAI embedding output -> staged WSL original GPU gather consumer.

Import and offline helpers use only the standard library. Root alone launches
run() in an owned normal-lifecycle window with an outer deadline/job guardian.
The returned NPU BF16 bytes are preserved without arithmetic, tolerance changes
or native substitution. GPU gather reads those exact newly produced bytes.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import queue
import statistics
import subprocess
import threading
import time
import uuid


HERE = Path(__file__).resolve().parent
SCHEMA = "halogen-npu-wsl-staged-handoff.v1"
PROVIDER = "VitisAIExecutionProvider"
ROWS, WARMUPS, ROW_BYTES = 12, 4, 5120
MODEL_SHA = "562a5de0f53aa8d271fca4ba239e8ded2def734f760680ef546dd94c7fcfeb07"
CPU_GATE_SHA = "f25400937c473fedc126d3e3d4d6d422229f4a0cd218e5ef34cd0798faa3c6aa"
NPU_GATE_SHA = "6f4bb9fe244d0c5b2ebaa5af8627bc037c27d5b6b93fab1b32b2a9596c66b444"
ENGINE_SHA = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"
CODE_SHA = "45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83"
GATHER = "_ZN7halogen12_GLOBAL__N_114k_embed_gatherEPKtPKiPt"
TOLERANCE = {"rtol": .03, "atol": .003}
GPU_IMAGE = "ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a"
GPU_IMAGE_HIP = "/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libamdhip64.so.7"
GPU_IMAGE_HIP_SHA = "6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5"
DXG_SHA = "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6"


def validate_container(info, cid, name, identity, image_id):
    if (info.get("Id") != cid or info.get("Name") != "/" + name or info.get("Image") != image_id or
            info.get("Config", {}).get("Image") != GPU_IMAGE or
            info.get("Config", {}).get("Labels", {}).get("strix-alloy.npu-wsl-handoff") != identity or
            info.get("Config", {}).get("Entrypoint") != ["/candidate/consumer"]):
        raise ValueError("owned container UUID/name/label/image/entrypoint identity differs")
    return info


class OwnedGpuContainer:
    """Existing pinned image only; bounded candidate files, no model mounts."""
    def __init__(self, args, directory):
        self.args, self.directory = args, directory
        self.identity = uuid.uuid4().hex
        self.name = "hgn-npu-wsl-" + self.identity
        self.cid, self.image_id, self.removed, self.create_attempted = None, None, False, False
        image = json.loads(self.docker("image", "inspect", GPU_IMAGE))[0]
        self.image_id = image["Id"]
        bridge = subprocess.run(self.wsl_prefix() + ["sha256sum", args.gpu_dxg_library], check=True,
                                timeout=20, capture_output=True, text=True).stdout.split()[0]
        if bridge != DXG_SHA or args.hip_library != GPU_IMAGE_HIP or args.hip_sha256 != GPU_IMAGE_HIP_SHA:
            raise ValueError("previously qualified pinned image HIP and DXG bridge required")
        backend = HERE.parents[1] / "backends/halogen-wsl2-0.16.2"
        mounts = {"/candidate/consumer": args.gpu_consumer, "/candidate/engine": args.engine,
                  "/candidate/code.hsaco": args.hsaco, "/usr/lib/libdxcore.so": "/usr/lib/wsl/lib/libdxcore.so",
                  "/usr/lib/librocdxg.so": args.gpu_dxg_library,
                  "/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib/librocroller.so.1":
                      wsl_path(backend / ".local/librocroller-compat.so.1")}
        command = ["create", "--pull=never", "--interactive", "--name", self.name, "--network=none", "--restart=no", "--read-only",
                   "--device=/dev/dxg", "--memory=2g", "--memory-swap=2g", "--pids-limit=128", "--ipc=private",
                   "--shm-size=64m", "--ulimit=core=0:0", "--ulimit=memlock=-1:-1",
                   "--security-opt=seccomp=unconfined", "--security-opt=label=disable", "--tmpfs=/tmp:rw,size=64m",
                   "--label=strix-alloy.npu-wsl-handoff=" + self.identity]
        for destination, source in sorted(mounts.items()):
            command += ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
        command += ["--mount", "type=bind,src=" + wsl_path(directory) + ",dst=/handoff",
                    "--env=HSA_ENABLE_DXG_DETECTION=1", "--env=HSA_ENABLE_SDMA=1", "--env=HALOGEN_LQ8_WAVE=1",
                    "--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1",
                    "--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
                    "--entrypoint=/candidate/consumer", GPU_IMAGE, "/candidate/engine", "/candidate/code.hsaco",
                    args.hip_library, args.hip_sha256, "/handoff", "--init-barrier"]
        self.plan = {"schema": SCHEMA, "identity": self.identity, "name": self.name, "image": GPU_IMAGE,
                     "image_id": self.image_id, "mounts": mounts, "models_mounted": False, "create_command": command}
        publish_json(directory / "gpu-container-plan.json", self.plan)
        try:
            self.create_attempted = True
            self.cid = self.docker(*command).strip()
            if len(self.cid) != 64 or any(c not in "0123456789abcdef" for c in self.cid):
                raise ValueError("exact Docker container ID required")
            self.verify()
            publish_json(directory / "gpu-container-created.json", {**self.plan, "container_id": self.cid})
        except BaseException:
            self.cleanup()
            raise

    def wsl_prefix(self):
        return ["wsl.exe", "--distribution", self.args.wsl_distro, "--exec"]

    def docker(self, *arguments):
        return subprocess.run(self.wsl_prefix() + ["docker", *arguments], check=True, timeout=30,
                              capture_output=True, text=True).stdout

    def verify(self):
        return validate_container(json.loads(self.docker("inspect", self.cid))[0], self.cid, self.name, self.identity, self.image_id)

    def attest_starting(self, starting):
        before = time.perf_counter_ns()
        state = self.verify()
        host_pid = state["State"]["Pid"]
        if not state["State"]["Running"] or type(host_pid) is not int or host_pid <= 0 or starting["native_pid"] != 1:
            raise ValueError("direct consumer PID1 and running owned container required")
        # Root-owned read-only /proc helper, initial WSL PID namespace. Bind its
        # stat birth, boot and executable to the C-emitted inner PID via NSpid.
        code = ("import os,json,sys; p=int(sys.argv[1]); s=open('/proc/%d/stat'%p).read().rsplit(')',1)[1].split(); "
                "status=open('/proc/%d/status'%p).read(); n=[x for x in status.splitlines() if x.startswith('NSpid:')][0]; "
                "print(json.dumps(dict(initial_namespace_pid=p,starttime_ticks=int(s[19]),"
                "boot_id=open('/proc/sys/kernel/random/boot_id').read().strip(),"
                "executable=os.readlink('/proc/%d/exe'%p),task_name=open('/proc/%d/comm'%p).read().strip(),"
                "namespace_pids=[int(x) for x in n.split()[1:]])))")
        command = ["wsl.exe", "--distribution", self.args.wsl_distro, "--user", "root", "--exec", "python3", "-c", code, str(host_pid)]
        record = json.loads(subprocess.run(command, check=True, timeout=15, capture_output=True, text=True).stdout)
        after = time.perf_counter_ns()
        if (record["namespace_pids"][0] != host_pid or record["namespace_pids"][-1] != starting["native_pid"] or
                record["starttime_ticks"] != starting["native_starttime_ticks"] or record["executable"] != "/candidate/consumer"):
            raise ValueError("exact initial-namespace consumer birth/executable/NSpid attestation differs")
        return {"schema": SCHEMA, "container_id": self.cid, "container_name": self.name, "label_uuid": self.identity,
                "image": GPU_IMAGE, "image_id": self.image_id, "docker_state": state["State"], **record,
                "inner_native_pid": starting["native_pid"], "inner_native_starttime_ticks": starting["native_starttime_ticks"],
                "windows_QPC_before_ns": before, "windows_QPC_after_ns": after, "windows_utc_ns": time.time_ns(),
                "linux_task_evidence": {"initial_namespace_tid": host_pid, "start_ticks": record["starttime_ticks"],
                                        "boot_id": record["boot_id"], "executable": record["executable"]},
                "process_id_in_vm_candidate": host_pid, "process_name_in_vm_candidate": record["task_name"],
                "vm_guid_source": "root must bind the observed Dxg bridge VM GUID; no VM identity inferred here",
                "GPU_context_not_yet_initialized": True}

    def cleanup(self, require_success=False):
        if self.removed:
            return self.terminal
        if not self.cid and self.create_attempted:
            found = self.docker("ps", "-aq", "--no-trunc", "--filter", "name=^/" + self.name + "$",
                                "--filter", "label=strix-alloy.npu-wsl-handoff=" + self.identity).split()
            if not found:
                return {"container_created": False, "container_removed": False}
            if len(found) != 1:
                raise RuntimeError("ambiguous exact owned container recovery")
            self.cid = found[0]
        if not self.cid:
            return {"container_created": False, "container_removed": False}
        info = self.verify()
        if info["State"]["Running"]:
            if require_success:
                raise RuntimeError("GPU consumer container remained running after terminal ack")
            self.docker("stop", "-t", "0", self.cid)
        info = self.verify()
        state = info["State"]
        if state["Running"] or state["Pid"] != 0 or require_success and (state["ExitCode"] != 0 or state["OOMKilled"]):
            raise RuntimeError("owned GPU container terminal state invalid")
        self.terminal = {"schema": SCHEMA, "container_id": self.cid, "container_name": self.name,
                         "identity": self.identity, "state": state, "container_removed": False}
        self.docker("rm", self.cid)
        self.removed = True
        self.terminal["container_removed"] = True
        publish_json(self.directory / "gpu-container-terminal.json", self.terminal)
        return self.terminal


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def require_sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("independent lowercase SHA256 required")
    return value


def wsl_path(path):
    value = PureWindowsPath(str(path))
    if not value.is_absolute() or len(value.drive) != 2 or value.drive[1] != ":":
        raise ValueError("drive-absolute Windows shared-directory path required")
    return "/mnt/" + value.drive[0].lower() + "/" + "/".join(value.parts[1:])


def publish_bytes(path, payload):
    """Fsync byte payload before publish; consumer cannot open partial files."""
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    if path.exists():
        raise FileExistsError("publication already exists")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # This writer owns the fresh run directory. os.rename also refuses an
    # existing destination on the intended Windows producer platform.
    if path.exists():
        raise FileExistsError("publication target appeared during write")
    os.rename(temporary, path)
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "fsync_completed_before_rename": True, "directory_durability_proven": False}


def publish_json(path, value):
    return publish_bytes(path, (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def validate_ack(ack, sequence, payload, ready):
    expected = hashlib.sha256(payload).hexdigest()
    fixed = {"kind": "row", "sequence": sequence, "passed": True,
             "input_sha256": expected, "output_sha256": expected,
             "input_bytes": ROW_BYTES, "output_bytes": ROW_BYTES, "h2d_bytes": 2 * ROW_BYTES,
             "d2h_bytes": ROW_BYTES, "copies": 3, "kernel_launches": 1,
             "completion_waits": 1, "exact_bytes": True, "output_file": f"row-{sequence:03d}-gpu.u16",
             "native_pid": ready["native_pid"], "native_starttime_ticks": ready["native_starttime_ticks"]}
    if len(payload) != ROW_BYTES or any(type(ack.get(k)) is not type(v) or ack.get(k) != v for k, v in fixed.items()):
        raise ValueError("GPU ack sequence, process, exact bytes, copies or completion differs")
    for name in ("gpu_kernel_event_ms", "load_hash_ms", "h2d_and_poison_ms", "enqueue_wait_host_ms",
                 "readback_ms", "consumer_total_ms", "monotonic_start_ms"):
        value = ack.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("bounded finite GPU timing required: " + name)
    return ack


class Consumer:
    def __init__(self, args, directory):
        self.args, self.lines, self.process, self.ready = args, queue.Queue(), None, None
        self.container = None
        self.init_barrier_wait_ms = 0.0
        self.stderr = (directory / "gpu-stderr.txt").open("xb")
        self.log = (directory / "gpu-stdout.jsonl").open("x", encoding="utf-8")
        try:
            if args.gpu_container:
                self.container = OwnedGpuContainer(args, directory)
                command = self.container.wsl_prefix() + ["docker", "start", "-ai", self.container.cid]
            else:
                command = ["wsl.exe", "--distribution", args.wsl_distro, "--exec", args.gpu_consumer,
                           args.engine, args.hsaco, args.hip_library, args.hip_sha256, wsl_path(directory)]
            self.execution_qpc_before_ns = time.perf_counter_ns()
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.stderr, text=True, encoding="utf-8", bufsize=1)
            # Windows TextIOWrapper otherwise translates LF into CRLF. The
            # persistent Linux consumer's init/quit protocol requires exact LF.
            self.process.stdin.reconfigure(newline="\n")
            self.reader = threading.Thread(target=self._read, daemon=True, name="handoff-GPU-output")
            self.reader.start()
            self.starting = self.receive(args.gpu_setup_timeout_s)
            if (self.starting.get("kind") != "starting" or self.starting.get("GPU_context_not_yet_initialized") is not True or
                    any(type(self.starting.get(k)) is not int or self.starting[k] <= 0 for k in
                        ("native_pid", "native_starttime_ticks", "clock_ticks_per_second"))):
                raise ValueError("GPU process identity before first context initialization required")
            self.ready = self.starting  # cancellation can bind Linux PID during HIP setup
            if self.container is not None:
                self.container_starting = self.container.attest_starting(self.starting)
                self.container_starting["execution_qpc_before_ns"] = self.execution_qpc_before_ns
                self.container_starting["qpc_frequency"] = 1_000_000_000
                publish_json(directory / "gpu-initial-namespace.json", self.container_starting)
                if args.gpu_init_barrier:
                    release = directory / "gpu-init-release.json"
                    publish_json(directory / "gpu-init-ready.json", self.container_starting)
                    barrier_started = time.perf_counter_ns()
                    deadline = time.monotonic() + args.barrier_timeout_s
                    while not release.exists():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("root GPU initialization release deadline expired")
                        time.sleep(.05)
                    value = json.loads(release.read_text(encoding="utf-8-sig"))
                    if (value.get("schema") != SCHEMA or value.get("container_id") != self.container.cid or
                            value.get("initial_namespace_pid") != self.container_starting["initial_namespace_pid"] or value.get("release") is not True):
                        raise ValueError("GPU init release must bind the exact owned initial-namespace consumer")
                    self.init_barrier_wait_ms = (time.perf_counter_ns()-barrier_started)/1e6
                self.process.stdin.write("init\n")
                self.process.stdin.flush()
            self.ready = self.receive(args.gpu_setup_timeout_s)
            if (self.ready.get("kind") != "ready" or self.ready.get("schema") != "halogen-npu-wsl-gpu-consumer.v1" or
                    self.ready.get("engine_sha256") != ENGINE_SHA or self.ready.get("codeobject_sha256") != CODE_SHA or
                    self.ready.get("hip_sha256") != args.hip_sha256 or self.ready.get("kernel") != GATHER or
                    self.ready.get("table_bytes") != ROW_BYTES or self.ready.get("destination_bytes") != ROW_BYTES or
                    self.ready.get("setup_token_h2d_bytes") != 4 or self.ready.get("gpu_arch") != "gfx1151" or
                    any(self.ready.get(k) != self.starting[k] for k in ("native_pid", "native_starttime_ticks", "clock_ticks_per_second")) or
                    any(type(self.ready.get(k)) is not int or self.ready[k] <= 0 for k in
                        ("native_pid", "native_starttime_ticks", "clock_ticks_per_second"))):
                raise ValueError("exact persistent GPU consumer ready identity/ABI required")
        except BaseException as exc:
            cleanup_errors = self.abort()
            if cleanup_errors:
                raise RuntimeError(str(exc) + "; cleanup: " + "; ".join(cleanup_errors)) from exc
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                self.log.write(line)
                self.log.flush()
                if len(line) > 8192:
                    raise ValueError("GPU reply exceeded bounded record")
                self.lines.put(json.loads(line))
        except BaseException as exc:
            self.lines.put(exc)
        finally:
            self.lines.put(EOFError("GPU consumer output ended"))

    def receive(self, seconds):
        try:
            value = self.lines.get(timeout=seconds)
        except queue.Empty as exc:
            raise TimeoutError("owned GPU consumer response deadline expired") from exc
        if isinstance(value, BaseException):
            raise value
        if type(value) is not dict:
            raise ValueError("JSON GPU reply object required")
        return value

    def request(self, sequence, payload, seconds):
        self.process.stdin.write(f"{sequence} {hashlib.sha256(payload).hexdigest()}\n")
        self.process.stdin.flush()
        return validate_ack(self.receive(seconds), sequence, payload, self.ready)

    def close(self):
        self.process.stdin.write("quit\n")
        self.process.stdin.flush()
        closed = self.receive(10)
        if (closed.get("kind") != "closed" or closed.get("passed") is not True or
                closed.get("consumed_rows") != ROWS or closed.get("launches") != ROWS or
                closed.get("copies") != 1 + 3 * ROWS or closed.get("cleanup_errors") != 0 or
                closed.get("allocations") != 3 or closed.get("frees") != 3 or
                closed.get("module_loads") != 1 or closed.get("module_unloads") != 1):
            raise ValueError("GPU complete-row and checked teardown evidence required")
        if self.process.wait(timeout=10) != 0:
            raise RuntimeError("GPU consumer exited unsuccessfully")
        execution_qpc_after_ns = time.perf_counter_ns()
        self.process.stdin.close()
        self.process.stdout.close()
        self.reader.join(2)
        if self.reader.is_alive():
            raise RuntimeError("GPU output reader did not stop")
        if self.container is not None:
            closed["initial_namespace_execution_interval"] = {**self.container_starting,
                "execution_qpc_after_ns": execution_qpc_after_ns,
                "process_exited_zero": True}
            publish_json(self.container.directory / "gpu-initial-namespace-terminal.json", closed["initial_namespace_execution_interval"])
            closed["container_terminal"] = self.container.cleanup(require_success=True)
        self.log.close()
        self.stderr.close()
        return closed

    def abort(self):
        errors = []
        if self.container is not None:
            try:
                self.container.cleanup()
            except BaseException as exc:
                errors.append("owned container stop/removal: " + str(exc))
        if self.process is not None and self.process.poll() is None:
            # Linux PID identity comes from the process before hardware calls.
            # An outer root-owned guardian is required for startup before READY.
            identity = getattr(self, "starting", None)
            if self.container is not None:
                pass  # cancellation uses the verified exact container, never a namespace-local PID on the host
            elif identity and type(identity.get("native_pid")) is int and type(identity.get("native_starttime_ticks")) is int:
                code = ("import os,signal,sys; p=int(sys.argv[1]); wanted=int(sys.argv[2]); "
                        "fd=os.pidfd_open(p,0); s=open('/proc/%d/stat'%p).read().rsplit(')',1)[1].split(); "
                        "assert int(s[19])==wanted; "
                        "assert os.path.realpath('/proc/%d/exe'%p)==os.path.realpath(sys.argv[3]); "
                        "s=open('/proc/%d/stat'%p).read().rsplit(')',1)[1].split(); assert int(s[19])==wanted; "
                        "signal.pidfd_send_signal(fd,signal.SIGKILL); os.close(fd)")
                try:
                    subprocess.run(["wsl.exe", "--distribution", self.args.wsl_distro, "--exec", "python3", "-c", code,
                                    str(identity["native_pid"]), str(identity["native_starttime_ticks"]), self.args.gpu_consumer],
                                   check=True, timeout=10, capture_output=True)
                except BaseException as exc:
                    errors.append("owned Linux cancellation: " + str(exc))
            else:
                errors.append("GPU startup failed before READY; outer root-owned guardian must confirm Linux cancellation")
            self.process.kill()
            try:
                self.process.wait(timeout=10)
            except BaseException as exc:
                errors.append("WSL child stop: " + str(exc))
        if self.process is not None:
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
        if hasattr(self, "reader"):
            self.reader.join(2)
            if self.reader.is_alive():
                errors.append("GPU output reader did not stop")
        self.log.close()
        self.stderr.close()
        return errors


def npu_call(session, feeds, ort, seconds, guard):
    options, expired = ort.RunOptions(), threading.Event()
    def cancel():
        expired.set()
        options.terminate = True
    timer = threading.Timer(seconds, cancel)
    timer.daemon = True
    guard.check()
    timer.start()
    started = time.perf_counter_ns()
    try:
        output = session.run(["e_projection"], feeds, options)[0]
        finished = time.perf_counter_ns()
        guard.check()
        if expired.is_set() or finished - started > seconds * 1e9:
            raise TimeoutError("NPU response deadline expired")
        return output, (finished - started) / 1e6
    finally:
        timer.cancel()
        timer.join(2)
        if timer.is_alive():
            raise RuntimeError("NPU deadline timer did not stop")


def bf16_payload(actual, np):
    if (type(actual) is not np.ndarray or actual.dtype != np.float32 or actual.shape != (1, 2560) or
            not np.isfinite(actual).all() or ((actual.view(np.uint32) & np.uint32(0xffff)) != 0).any()):
        raise ValueError("finite exact BF16-lattice NPU FLOAT row required")
    return (actual.view(np.uint32) >> np.uint32(16)).astype("<u2").tobytes(order="C")


def verify_linux_binary(args):
    row = subprocess.run(["wsl.exe", "--distribution", args.wsl_distro, "--exec", "sha256sum", args.gpu_consumer],
                         check=True, timeout=20, capture_output=True, text=True)
    if row.stdout.split()[0] != args.gpu_consumer_sha256:
        raise ValueError("independently pinned GPU binary differs")


def wait_gpu_release(args, directory, facts, guard):
    release = directory / "gpu-release.json"
    marker = {"schema": SCHEMA, "stage": "npu-prepared-before-first-WSL-GPU-process",
              "windows_pid": os.getpid(), "utc_ns": time.time_ns(), "windows_perf_counter_ns": time.perf_counter_ns(),
              "release_file": str(release), "gpu_start_barrier": args.gpu_start_barrier, **facts}
    publish_json(directory / "npu-prepared.json", marker)
    print(json.dumps({"stage": marker["stage"], "marker": str(directory / "npu-prepared.json"),
                      "release_file": str(release), "barrier_enabled": args.gpu_start_barrier}), flush=True)
    marker["barrier_wait_ms"] = 0.0
    if args.gpu_start_barrier:
        barrier_started = time.perf_counter_ns()
        deadline = time.monotonic() + args.barrier_timeout_s
        while not release.exists():
            guard.check()
            if time.monotonic() >= deadline:
                raise TimeoutError("root GPU start barrier deadline expired")
            time.sleep(.05)
        if release.stat().st_size > 4096:
            raise ValueError("bounded root GPU release required")
        value = json.loads(release.read_text(encoding="utf-8-sig"))
        if value.get("schema") != SCHEMA or value.get("windows_pid") != os.getpid() or value.get("release") is not True:
            raise ValueError("root GPU release must bind this Windows producer PID")
        marker["release"] = value
        marker["barrier_wait_ms"] = (time.perf_counter_ns()-barrier_started)/1e6
    return marker


def wait_gpu_rows_release(args, directory, consumer, guard, completed=False):
    stage = "gpu-rows-complete" if completed else "gpu-rows-ready"
    release = directory / ("gpu-cleanup-release.json" if completed else "gpu-rows-release.json")
    marker = {"schema": SCHEMA, "stage": stage, "windows_pid": os.getpid(),
              "utc_ns": time.time_ns(), "windows_perf_counter_ns": time.perf_counter_ns(),
              "release_file": str(release), "gpu_rows_barrier": args.gpu_rows_barrier,
              "barrier_timeout_seconds": args.barrier_timeout_s,
              "rows_completed": ROWS if completed else 0,
              "native_pid": consumer.ready["native_pid"],
              "native_starttime_ticks": consumer.ready["native_starttime_ticks"],
              "GPU_context_live": True, "barrier_wait_ms": 0.0}
    if consumer.container is not None:
        marker.update(container_id=consumer.container.cid,
                      initial_namespace_pid=consumer.container_starting["initial_namespace_pid"])
    publish_json(directory / (stage + ".json"), marker)
    print(json.dumps({"stage": stage, "marker": str(directory / (stage + ".json")),
                      "release_file": str(release), "barrier_enabled": args.gpu_rows_barrier}), flush=True)
    if args.gpu_rows_barrier:
        barrier_started = time.perf_counter_ns()
        deadline = time.monotonic() + args.barrier_timeout_s
        while not release.exists():
            guard.check()
            if consumer.process.poll() is not None:
                raise RuntimeError("owned GPU consumer exited during root rows barrier")
            if time.monotonic() >= deadline:
                raise TimeoutError("root " + stage + " release deadline expired")
            time.sleep(.05)
        if release.stat().st_size > 4096:
            raise ValueError("bounded root GPU rows release required")
        value = json.loads(release.read_text(encoding="utf-8-sig"))
        if (type(value) is not dict or value.get("schema") != SCHEMA or
                type(value.get("windows_pid")) is not int or value["windows_pid"] != os.getpid() or
                value.get("release") is not True):
            raise ValueError("root GPU rows release must bind this Windows producer PID")
        marker.update(release=value, release_received_perf_counter_ns=time.perf_counter_ns(),
                      barrier_wait_ms=(time.perf_counter_ns()-barrier_started)/1e6)
    return marker


def run(args):
    execution_started = time.perf_counter_ns()
    directory = args.output_directory.resolve()
    directory.mkdir(exist_ok=False)
    result = {"schema": SCHEMA, "passed": False, "component": "embedding-projection-to-original-GPU-gather",
              "source_sha256": digest(__file__), "gpu_source_sha256": digest(HERE / "halogen_npu_wsl_handoff_gpu_v1.c"),
              "windows_pid": os.getpid(), "started_utc_ns": time.time_ns(), "calls": [], "warmups": [],
              "npu_tolerance": TOLERANCE, "tolerance_adjustment": False, "arithmetic_fitting": False,
              "live_output_swap": False, "full_D_qualified": False, "hidden_qualified": False,
              "full_head_qualified": False, "acceptance_qualified": False, "overlap_qualified": False,
              "performance_qualified": False, "native_word_parity_qualified": False, "zero_copy": False,
              "outer_owned_job_guard_required": True, "row_deadline_seconds": args.row_timeout_s,
              "gpu_rows_barrier": args.gpu_rows_barrier, "barrier_timeout_seconds": args.barrier_timeout_s,
              "timing_scope": "prepared-input copies -> fresh NPU session.run -> BF16 pack/validation -> fsync/rename "
                              "publication -> pipe request -> WSL file read/hash -> HIP H2D/poison -> original GPU gather "
                              "event wait -> D2H/fsync output -> Windows exact readback; cold setup and barrier waits reported separately; "
                              "row/rows-interval/execution-minus-barrier timings exclude root release waits"}
    session = ort = runtime_handle = dll = guard = consumer = None
    registered = profile_finished = False
    errors = []
    try:
        if any(os.environ.get(k) != "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
            raise ValueError("BLAS/OpenMP thread environment must equal 1 before Python starts")
        import halogen_npu_early_embedding_probe as probe
        graph = probe.graph
        shared, native, runtime, bounded = probe.helpers()
        if graph.digest(graph.__file__) != args.transformer_sha256 or probe.TOLERANCES["npu"] != TOLERANCE:
            raise ValueError("sealed embedding transformer and original tolerance required")
        guard = runtime.ReserveGuard()
        guard.start()
        import numpy as np
        candidate, original = graph.verify_graph(args.model, args.projection_receipt, args.projection_receipt_sha256)
        if candidate["model_sha256"] != MODEL_SHA:
            raise ValueError("previously screened embedding-only model required")
        feeds, oracles, binding, oracle_files = probe.references(args, original, bounded, native, np)
        feed_hashes, diagnostics = {}, {}
        for label, value in feeds.items():
            feed, facts = probe.prepared(value, np)
            feed_hashes[label], diagnostics[label] = {k: shared.array_hash(v) for k, v in feed.items()}, facts
        result.update({k: candidate[k] for k in ("model", "model_sha256", "data", "data_sha256", "data_bytes",
                      "transformer_sha256", "weight_lineage", "immutable_files", "arithmetic")})
        result.update(dependency_sha256=runtime.dependencies(), probe_dependency_sha256={**probe.SEALED_HELPERS,
                      Path(graph.__file__).name: args.transformer_sha256}, projection_receipt_sha256=args.projection_receipt_sha256,
                      fc_fixtures_sha256=args.fc_fixtures_sha256, native_fc_replay_sha256=args.native_fc_replay_sha256,
                      oracle_binding=binding, normalized_input_sets={k: shared.array_hash(v) for k, v in feeds.items()},
                      runtime_input_sets=feed_hashes, input_split_diagnostics=diagnostics,
                      weight_split_diagnostics=candidate["weight_diagnostics"],
                      required_hardware_partition_outputs=candidate["metadata"]["required_hardware_partition_outputs"])
        current = dict(result, source_sha256=graph.digest(probe.__file__))
        if args.cpu_gate_sha256 != CPU_GATE_SHA or args.npu_gate_sha256 != NPU_GATE_SHA:
            raise ValueError("unchanged independently frozen successful CPU/NPU component receipts required")
        result["cpu_gate"] = probe.cpu_gate(args, current, oracles, bounded, shared, native, runtime, np)
        previous = bounded(args.npu_gate, args.npu_gate_sha256, 4 << 20)
        if (previous.get("schema") != probe.SCHEMA or previous.get("provider") != "npu" or
                previous.get("passed") is not True or previous.get("tolerance") != TOLERANCE or
                previous.get("error") is not None or previous.get("cleanup_errors") or previous.get("reserve_guard_error") or
                any(previous.get(k) != current[k] for k in probe.IDENTITY_KEYS)):
            raise ValueError("previous successful same-model NPU accuracy receipt required")
        previous_profile = bounded(Path(previous["profile"]), previous["profile_sha256"], 16 << 20)
        previous_context = bounded(Path(previous["context"]), previous["context_sha256"], 2 << 20)
        proof = runtime.context_proof(previous_context, result["required_hardware_partition_outputs"],
                                      previous["cache_key"], previous["provider_library"])
        # Prior probe adds its descriptive scope; compare every evidential field.
        proof["scope"] = previous["context_proof"].get("scope")
        if (runtime.profile_proof(previous_profile, "npu") != previous["profile_proof"] or
                previous["profile_proof"].get("passed") is not True or proof != previous["context_proof"] or not proof["passed"]):
            raise ValueError("recomputed prior hardware/context/profile provenance differs")
        admitted_hashes = {}
        for index, call in enumerate(previous["calls"]):
            label = "A" if index % 2 == 0 else "B"
            row = call["outputs"]["e_projection"]
            old = shared.retained_output(row, (1, 2560), np)
            metric = native.comparison(old, oracles[label], (1, 2560), TOLERANCE, np)
            if (not metric["passed"] or metric != row["native_comparison"] or not call["passed"] or
                    shared.array_hash(old) != admitted_hashes.setdefault(label, row["output_sha256"])):
                raise ValueError("retained prior NPU output accuracy/stability differs")
        if len(previous["calls"]) != ROWS or admitted_hashes.get("A") == admitted_hashes.get("B"):
            raise ValueError("balanced distinct prior NPU A/B component outputs required")
        result["previous_npu_accuracy"] = {"path": str(args.npu_gate), "sha256": args.npu_gate_sha256,
                                           "profile_sha256": previous["profile_sha256"], "context_sha256": previous["context_sha256"],
                                           "float_output_sha256": admitted_hashes}
        verify_linux_binary(args)
        from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
        from winui3.microsoft.windows.ai.machinelearning import ExecutionProviderCatalog
        runtime_handle = initialize()
        catalog_rows = []
        for provider in ExecutionProviderCatalog.get_default().find_all_providers():
            if provider.name != PROVIDER:
                continue
            row = {"name": provider.name, "ready_state": int(provider.ready_state),
                   "ready_state_name": provider.ready_state.name}
            try:
                row["library_path"] = provider.library_path
            except Exception as exc:
                row["library_path_error"] = type(exc).__name__ + ": " + str(exc)
            catalog_rows.append(row)
        result.update(winml_catalog_observation=catalog_rows,
                      provider_selection="previous-receipt-pinned-installed-and-copied-complete-inventory",
                      catalog_readiness_used_as_execution_proof=False, ensure_ready_called=False,
                      provider_acquisition_allowed=False, catalog_library=previous["catalog_library"])
        from halogen_npu_expert_onnx import verified_provider_copy
        # WinML READY is process-local broker preparation: in a fresh process
        # the installed EP can report NOT_READY with an empty library_path.
        # Avoid ensure_ready_async (which can acquire packages). The successful
        # frozen NPU receipt pins the already installed source path and every
        # byte in its copied DLL inventory. Register that complete unchanged
        # copy directly through ORT's existing EP-library API. Fresh actual NPU
        # device/context/profile/output proofs below decide hardware execution.
        chosen, inventory = verified_provider_copy(previous["catalog_library"], args.ep_dir)
        if inventory != previous["provider_copy_files"] or digest(chosen) != previous["provider_library_sha256"]:
            raise ValueError("unchanged complete provider inventory required")
        dll = os.add_dll_directory(str(chosen.parent))
        import onnxruntime as ort
        if ort.__version__ != "1.25.2" or np.__version__ != "2.5.3":
            raise ValueError("frozen ORT/NumPy versions required")
        ort.register_execution_provider_library(PROVIDER, str(chosen))
        registered = True
        devices = [d for d in ort.get_ep_devices() if d.ep_name == PROVIDER and str(d.device.type).endswith(".NPU")]
        if len(devices) != 1:
            raise RuntimeError("exactly one actual VitisAI NPU device required")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.enable_profiling = True
        options.profile_file_prefix = str(directory / "npu-profile")
        cache = directory / "vitisai-cache"
        cache.mkdir()
        cache_key = hashlib.sha256((result["model_sha256"] + ":" + result["data_sha256"] + ":" +
                                  digest(chosen) + ":ORT_DISABLE_ALL").encode()).hexdigest()
        options.add_provider_for_devices(devices, {"cache_dir": str(cache), "cache_key": cache_key, "enable_cache_file_io_in_mem": "0"})
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        guard.check(admission=True)
        started = time.perf_counter_ns()
        session = ort.InferenceSession(result["model"], sess_options=options, enable_fallback=False)
        session.disable_fallback()
        result.update(initialization_ms=(time.perf_counter_ns()-started)/1e6, session_creations=1,
                      provider_library=str(chosen), provider_library_sha256=digest(chosen), provider_copy_files=inventory,
                      cache_key=cache_key, cpu_fallback_disabled=True, ort_version=ort.__version__, numpy_version=np.__version__)
        if ([(v.name, tuple(v.shape), v.type) for v in session.get_inputs()] !=
                [(k, v, "tensor(float)") for k, v in graph.INPUT_SHAPES.items()] or
                [(v.name, tuple(v.shape), v.type) for v in session.get_outputs()] != [("e_projection", (1, 2560), "tensor(float)")]):
            raise ValueError("exact count1 embedding-only session ABI required")
        context = cache / cache_key / "context.json"
        context_sha = digest(context)
        context_proof = runtime.context_proof(bounded(context, context_sha, 2 << 20),
                                             result["required_hardware_partition_outputs"], cache_key, chosen)
        if not context_proof["passed"]:
            raise RuntimeError("fresh full embedding VAIML hardware/STX partition coverage required")
        result.update(context=str(context), context_sha256=context_sha, context_proof=context_proof)
        for index in range(WARMUPS):
            label = "A" if index % 2 == 0 else "B"
            prepared, facts = probe.prepared(feeds[label], np)
            actual, elapsed = npu_call(session, prepared, ort, 30, guard)
            payload = bf16_payload(actual, np)
            metric = native.comparison(actual, oracles[label], (1, 2560), TOLERANCE, np)
            if not metric["passed"] or shared.array_hash(actual) != admitted_hashes[label] or facts != diagnostics[label]:
                raise ValueError("fresh warmup output differs from admitted NPU accuracy")
            result["warmups"].append({"index": index, "input_set": label, "session_run_ms": elapsed,
                                      "float_sha256": shared.array_hash(actual), "bf16_sha256": hashlib.sha256(payload).hexdigest(),
                                      "native_GPU_comparison": metric})
        result["gpu_start_marker"] = wait_gpu_release(args, directory,
            {"model_sha256": result["model_sha256"], "context_sha256": context_sha, "context_proof": context_proof,
             "warmups_completed": WARMUPS}, guard)
        gpu_started = time.perf_counter_ns()
        consumer = Consumer(args, directory)
        result.update(gpu_starting=consumer.starting, gpu_ready=consumer.ready, gpu_launch_to_ready_ms=(time.perf_counter_ns()-gpu_started)/1e6,
                      gpu_consumer=args.gpu_consumer, gpu_consumer_sha256=args.gpu_consumer_sha256,
                      gpu_init_barrier_wait_ms=consumer.init_barrier_wait_ms)
        if consumer.container is not None:
            result["gpu_initial_namespace"] = consumer.container_starting
        result["gpu_rows_ready_marker"] = wait_gpu_rows_release(args, directory, consumer, guard)
        rows_started = time.perf_counter_ns()
        for sequence in range(ROWS):
            guard.check()
            label = "A" if sequence % 2 == 0 else "B"
            row_started = time.perf_counter_ns()
            prepared, facts = probe.prepared(feeds[label], np)
            feed = {k: np.array(v, dtype=np.float32, order="C", copy=True) for k, v in prepared.items()}
            copied = time.perf_counter_ns()
            actual, npu_ms = npu_call(session, feed, ort, args.row_timeout_s, guard)
            returned = time.perf_counter_ns()
            payload = bf16_payload(actual, np)
            fp32_payload = actual.tobytes(order="C")
            metric = native.comparison(actual, oracles[label], (1, 2560), TOLERANCE, np)
            if (not metric["passed"] or hashlib.sha256(fp32_payload).hexdigest() != admitted_hashes[label] or
                    {k: shared.array_hash(v) for k, v in feed.items()} != feed_hashes[label] or facts != diagnostics[label]):
                raise ValueError("fresh NPU output/input identity or unchanged native screening failed")
            publish_bytes(directory / f"row-{sequence:03d}-npu.f32", fp32_payload)
            binary = publish_bytes(directory / f"row-{sequence:03d}-npu.u16", payload)
            packed = time.perf_counter_ns()
            publication = {"schema": SCHEMA, "sequence": sequence, "input_set": label,
                           "producer": "fresh-session.run/VitisAIExecutionProvider", "producer_windows_pid": os.getpid(),
                           "returned_perf_counter_ns": returned, "publication_perf_counter_ns": packed,
                           "utc_ns": time.time_ns(), "model_sha256": MODEL_SHA,
                           "float_output_sha256": hashlib.sha256(fp32_payload).hexdigest(), "bf16_output": binary,
                           "input_sha256": feed_hashes[label], "native_GPU_comparison": metric,
                           "native_GPU_oracle_used_as_producer": False, "BF16_conversion": "exact high16 of BF16-lattice FLOAT; no rounding"}
            publish_json(directory / f"row-{sequence:03d}-npu.json", publication)
            published = time.perf_counter_ns()
            remaining = args.row_timeout_s - (published-row_started)/1e9
            if remaining <= 0:
                raise TimeoutError("handoff deadline expired before GPU publication request")
            ack = consumer.request(sequence, payload, remaining)
            acknowledged = time.perf_counter_ns()
            readback = (directory / ack["output_file"]).read_bytes()
            if readback != payload:
                raise ValueError("Windows GPU readback differs from newly produced NPU bytes")
            done = time.perf_counter_ns()
            if done-row_started > args.row_timeout_s*1e9:
                raise TimeoutError("NPU-publication-GPU-readback deadline expired")
            result["calls"].append({"sequence": sequence, "input_set": label, "passed": True,
                "producer": "fresh-session.run/VitisAIExecutionProvider", "float_output_sha256": admitted_hashes[label],
                "npu_BF16_sha256": binary["sha256"], "native_GPU_comparison": metric, "publication": publication,
                "gpu_ack": ack, "windows_readback_bytes": len(readback), "windows_readback_sha256": hashlib.sha256(readback).hexdigest(),
                "deadline_passed": True, "row_started_perf_counter_ns": row_started, "row_completed_perf_counter_ns": done,
                "prepare_copy_ms": (copied-row_started)/1e6, "npu_session_run_ms": npu_ms,
                "NPU_return_pack_validate_publish_binary_ms": (packed-returned)/1e6,
                "manifest_publish_ms": (published-packed)/1e6, "publication_to_GPU_ack_ms": (acknowledged-published)/1e6,
                "Windows_readback_verify_ms": (done-acknowledged)/1e6, "full_staged_handoff_ms": (done-row_started)/1e6})
            guard.check()
        rows_completed = time.perf_counter_ns()
        result.update(gpu_rows_interval_started_perf_counter_ns=rows_started,
                      gpu_rows_interval_completed_perf_counter_ns=rows_completed,
                      gpu_rows_interval_ms=(rows_completed-rows_started)/1e6)
        result["gpu_rows_complete_marker"] = wait_gpu_rows_release(args, directory, consumer, guard, completed=True)
        result["gpu_closed"] = consumer.close()
        consumer = None
        profile = Path(session.end_profiling())
        profile_finished = True
        profile_sha = digest(profile)
        proof = runtime.profile_proof(bounded(profile, profile_sha, 16 << 20), "npu")
        if not proof["passed"] or proof["node_events"] != WARMUPS + ROWS:
            raise RuntimeError("fresh exclusive VitisAI execution profile must cover every warmup and handoff call")
        result.update(profile=str(profile), profile_sha256=profile_sha, profile_proof=proof)
        frozen = {Path(row["path"]): row["sha256"] for row in result["immutable_files"] + oracle_files}
        frozen.update({Path(__file__): result["source_sha256"], HERE / "halogen_npu_wsl_handoff_gpu_v1.c": result["gpu_source_sha256"],
                       args.projection_receipt: args.projection_receipt_sha256, args.fc_fixtures: args.fc_fixtures_sha256,
                       args.native_fc_replay: args.native_fc_replay_sha256, args.cpu_gate: args.cpu_gate_sha256,
                       args.npu_gate: args.npu_gate_sha256, context: context_sha, profile: profile_sha})
        if any(digest(path) != wanted for path, wanted in frozen.items()) or runtime.dependencies() != result["dependency_sha256"]:
            raise RuntimeError("immutable model/input/reference/provenance/source changed")
        verify_linux_binary(args)
        hashes = {label: {row["npu_BF16_sha256"] for row in result["calls"] if row["input_set"] == label} for label in ("A", "B")}
        if any(len(values) != 1 for values in hashes.values()) or hashes["A"] == hashes["B"]:
            raise ValueError("both producer and GPU consumer must distinguish stable alternating A/B output bytes")
        result.update(passed=True, npu_component_accuracy_passed=True, real_NPU_to_WSL_GPU_handoff_passed=True,
                      fresh_hardware_context_profile_passed=True, exact_NPU_bytes_GPU_consumed=True,
                      alternating_NPU_outputs_GPU_readback_distinguished=True,
                      timing_observations={name: {"mean": statistics.fmean(row[name] for row in result["calls"]),
                                                "min": min(row[name] for row in result["calls"]),
                                                "max": max(row[name] for row in result["calls"])}
                                           for name in ("npu_session_run_ms", "publication_to_GPU_ack_ms", "full_staged_handoff_ms")})
    except BaseException as exc:
        result.update(passed=False, error=type(exc).__name__ + ": " + str(exc))
    finally:
        if consumer is not None:
            errors.extend(consumer.abort())
        if session is not None and not profile_finished:
            try:
                partial = Path(session.end_profiling())
                result.update(partial_profile=str(partial), partial_profile_sha256=digest(partial))
            except BaseException as exc:
                errors.append("partial NPU profile close: " + str(exc))
        session = None
        gc.collect()
        for name, active, action in (("provider_unregistered", registered, lambda: ort.unregister_execution_provider_library(PROVIDER)),
                                     ("dll_directory_closed", dll is not None, lambda: dll.close()),
                                     ("bootstrap_shutdown", runtime_handle is not None, lambda: runtime_handle())):
            try:
                if active:
                    action()
                    result[name] = True
            except BaseException as exc:
                errors.append(name + ": " + str(exc))
        if guard is not None:
            guard.stop()
            result.update(reserve_samples=guard.samples, reserve_guard_error=guard.error)
            if guard.error:
                errors.append("reserve guard: " + guard.error)
        barrier_wait_ms = (result.get("gpu_start_marker", {}).get("barrier_wait_ms", 0.0) +
                           result.get("gpu_init_barrier_wait_ms", 0.0) +
                           sum(result.get(name, {}).get("barrier_wait_ms", 0.0) for name in
                               ("gpu_rows_ready_marker", "gpu_rows_complete_marker")))
        execution_total_ms = (time.perf_counter_ns()-execution_started)/1e6
        result.update(cleanup_errors=errors, completed_utc_ns=time.time_ns(),
                      completed_root_barrier_wait_ms=barrier_wait_ms,
                      execution_total_ms_including_barrier_waits=execution_total_ms)
        if errors:
            result["passed"] = False
        if result["passed"]:
            result["execution_total_ms_excluding_barrier_waits"] = execution_total_ms-barrier_wait_ms
        publish_json(directory / "handoff.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "projection-receipt", "fc-fixtures", "native-fc-replay", "cpu-gate", "npu-gate", "ep-dir", "output-directory"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("projection-receipt-sha256", "transformer-sha256", "fc-fixtures-sha256", "native-fc-replay-sha256",
                 "cpu-gate-sha256", "npu-gate-sha256", "gpu-consumer-sha256", "hip-sha256"):
        parser.add_argument("--" + name, type=require_sha, required=True)
    for name in ("wsl-distro", "gpu-consumer", "engine", "hsaco", "hip-library"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--gpu-start-barrier", action="store_true")
    parser.add_argument("--gpu-container", action="store_true", help="use previously qualified existing pinned image and DXG mounts")
    parser.add_argument("--gpu-dxg-library", help="independently qualified WSL bridge source path")
    parser.add_argument("--gpu-init-barrier", action="store_true", help="hold container consumer before HIP initialization for root attribution")
    parser.add_argument("--gpu-rows-barrier", action="store_true", help="hold rows after context setup and cleanup after complete rows for a fixed counter epoch")
    parser.add_argument("--barrier-timeout-s", type=float, default=120)
    parser.add_argument("--gpu-setup-timeout-s", type=float, default=60)
    parser.add_argument("--row-timeout-s", type=float, default=2)
    args = parser.parse_args(argv)
    if any(not math.isfinite(v) or not 0 < v <= maximum for v, maximum in
           ((args.barrier_timeout_s, 600), (args.gpu_setup_timeout_s, 120), (args.row_timeout_s, 10))):
        parser.error("finite bounded barrier/setup/standalone-row deadlines required")
    if any(not getattr(args, name).startswith("/") for name in ("gpu_consumer", "engine", "hsaco", "hip_library")):
        parser.error("GPU binary/engine/HSACO/HIP must be absolute Linux paths")
    if args.gpu_container and (not args.gpu_dxg_library or not args.gpu_dxg_library.startswith("/")):
        parser.error("owned pinned-image consumer requires --gpu-dxg-library absolute bridge path")
    if args.gpu_init_barrier and not args.gpu_container:
        parser.error("GPU initialization attribution barrier requires owned container mode")
    result = run(args)
    print(json.dumps({k: result.get(k) for k in ("passed", "error", "real_NPU_to_WSL_GPU_handoff_passed", "timing_observations", "cleanup_errors")}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
