"""Fresh NPU BF16 rows -> bounded binary pipe -> unchanged original GPU gather.

V1/V2 remain frozen. Root alone runs hardware; imports/offline helpers are stdlib.
Kernel PID/TGID comes from a private socket probe in the consumer before HIP.
The timed exchange contains no row artifact writes or DrvFS row reads.
"""
import importlib.util
import struct
import sys

from pathlib import Path
_base_path = Path(__file__).with_name("halogen_npu_wsl_handoff_v1.py")
_spec = importlib.util.spec_from_file_location("handoff_frozen_v1", _base_path)
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)
for _name in ("argparse", "gc", "hashlib", "json", "math", "os", "queue", "statistics", "subprocess", "threading", "time", "uuid",
              "HERE", "SCHEMA", "PROVIDER", "ROWS", "WARMUPS", "ROW_BYTES", "MODEL_SHA", "CPU_GATE_SHA", "NPU_GATE_SHA",
              "ENGINE_SHA", "CODE_SHA", "GATHER", "TOLERANCE", "GPU_IMAGE", "GPU_IMAGE_HIP", "GPU_IMAGE_HIP_SHA", "DXG_SHA",
              "digest", "validate_container", "wsl_path", "publish_bytes", "publish_json", "require_sha", "npu_call", "bf16_payload",
              "verify_linux_binary", "wait_gpu_release", "wait_gpu_rows_release"):
    globals()[_name] = getattr(v1, _name)

V1_SHA = "ab001904b908dd723a0b001df6e88c0445058e9952f84d6dc5407c59763f6500"
PIPE_SCHEMA = "halogen-npu-wsl-binary-pipe.v3"
MAGIC = b"HGNPIPE3"
MAX_META_BYTES = 4096


def validate_kernel_identity(frame):
    value = frame.get("kernel_identity")
    if type(value) is not dict:
        raise ValueError("observed own-socket kernel identity required")
    integers = ("kernel_pid", "kernel_tgid", "namespace_pid", "namespace_tid",
                "proc_pid_namespace_inode", "native_starttime_ticks")
    chain = value.get("namespace_pids")
    boot = value.get("boot_id")
    try:
        valid_boot = type(boot) is str and str(uuid.UUID(boot)) == boot
    except (ValueError, AttributeError):
        valid_boot = False
    if (any(type(value.get(key)) is not int or value[key] <= 0 for key in integers) or
            value["kernel_pid"] > 0x7fffffff or value["kernel_pid"] != value["kernel_tgid"] or
            type(frame.get("native_pid")) is not int or type(frame.get("native_starttime_ticks")) is not int or
            value["namespace_pid"] != frame["native_pid"] or value["namespace_tid"] != frame["native_pid"] or
            value["native_starttime_ticks"] != frame["native_starttime_ticks"] or
            type(chain) is not list or not 1 <= len(chain) <= 32 or
            any(type(pid) is not int or not 0 < pid <= 0x7fffffff for pid in chain) or chain[-1] != frame["native_pid"] or
            not valid_boot or value.get("scope") != "own-socket-only" or
            value.get("probe_fds_closed") is not True or value.get("persistent_kernel_attachment") is not False):
        raise ValueError("closed own-socket main-thread kernel/namespace/birth/boot evidence required")
    return value


def require_same_kernel_identity(frame, ready):
    value = validate_kernel_identity({**ready, "kernel_identity": frame.get("kernel_identity")})
    if value != validate_kernel_identity(ready):
        raise ValueError("persistent consumer kernel identity changed")
    return value


def _exact(stream, count):
    value = bytearray()
    while len(value) < count:
        part = stream.read(count-len(value))
        if not part:
            raise EOFError("truncated bounded GPU pipe frame")
        value.extend(part)
    return bytes(value)


def _metadata(value):
    if type(value) is not dict or value.get("schema") != PIPE_SCHEMA or type(value.get("kind")) is not str:
        raise ValueError("binary pipe schema/kind object required")
    return value


def read_frame(stream):
    prefix = _exact(stream, 16)
    header_bytes, payload_bytes = struct.unpack(">II", prefix[8:])
    if prefix[:8] != MAGIC or not 0 < header_bytes <= MAX_META_BYTES or payload_bytes not in (0, ROW_BYTES):
        raise ValueError("bounded binary pipe envelope required")
    metadata = _metadata(json.loads(_exact(stream, header_bytes).decode("utf-8")))
    return metadata, _exact(stream, payload_bytes)


def write_frame(stream, metadata, payload=b""):
    _metadata(metadata)
    if type(payload) is not bytes or len(payload) not in (0, ROW_BYTES):
        raise ValueError("exact binary pipe row length required")
    header = json.dumps(metadata, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if not 0 < len(header) <= MAX_META_BYTES:
        raise ValueError("bounded binary pipe metadata required")
    frame = MAGIC + struct.pack(">II", len(header), len(payload)) + header + payload
    sent = 0
    while sent < len(frame):
        count = stream.write(frame[sent:])
        if type(count) is not int or count <= 0:
            raise OSError("binary pipe write did not progress")
        sent += count
    stream.flush()


def validate_pipe_ack(ack, readback, sequence, payload, ready, model_binding):
    require_same_kernel_identity(ack, ready)
    if (type(ack) is not dict or ack.get("schema") != PIPE_SCHEMA or ack.get("transport") != "binary-pipe" or
            ack.get("model_binding") != require_sha(model_binding) or type(readback) is not bytes or readback != payload or
            len(readback) != ROW_BYTES or hashlib.sha256(readback).hexdigest() != ack.get("output_sha256")):
        raise ValueError("binary GPU readback/hash/model binding differs")
    v1.validate_ack({**ack, "output_file": f"row-{sequence:03d}-gpu.u16"}, sequence, payload, ready)
    return ack


class OwnedGpuContainer(v1.OwnedGpuContainer):
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
                   "--cap-add=BPF", "--security-opt=seccomp=unconfined", "--security-opt=label=disable", "--tmpfs=/tmp:rw,size=64m",
                   "--label=strix-alloy.npu-wsl-handoff=" + self.identity]
        for destination, source in sorted(mounts.items()):
            command += ["--mount", "type=bind,src=" + source + ",dst=" + destination + ",readonly"]
        command += ["--mount", "type=bind,src=" + wsl_path(directory) + ",dst=/handoff",
                    "--env=HSA_ENABLE_DXG_DETECTION=1", "--env=HSA_ENABLE_SDMA=1", "--env=HALOGEN_LQ8_WAVE=1",
                    "--env=HSA_DISABLE_COREDUMP_ON_EXCEPTION=1",
                    "--env=LD_LIBRARY_PATH=/usr/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib:/usr/local/lib/python3.12/site-packages/_rocm_sdk_libraries/lib",
                    "--entrypoint=/candidate/consumer", GPU_IMAGE, "/candidate/engine", "/candidate/code.hsaco",
                    args.hip_library, args.hip_sha256, "/handoff", "--init-barrier", "--pipe-rows", args.model_binding]
        self.plan = {"schema": SCHEMA, "identity": self.identity, "name": self.name, "image": GPU_IMAGE,
                     "image_id": self.image_id, "mounts": mounts, "models_mounted": False, "create_command": command, "model_binding": args.model_binding}
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



    def attest_starting(self, starting):
        kernel = validate_kernel_identity(starting)
        before = time.perf_counter_ns()
        state = self.verify()
        docker_pid = state["State"]["Pid"]
        if not state["State"]["Running"] or type(docker_pid) is not int or docker_pid <= 0 or starting["native_pid"] != 1:
            raise ValueError("running direct consumer PID1 required")
        # --system procfs also omits the initial kernel namespace. Bind its
        # observed chain to the consumer's direct kernel observation; do not
        # infer an initial namespace PID from this procfs view.
        code = r'''set -eu
bb=/usr/sbin/busybox
matches=$($bb awk -v outer="$1" -v inner="$2" '$1=="NSpid:" && NF>=3 && $(NF-1)==outer && $NF==inner {x=FILENAME;sub("/proc/","",x);sub("/status","",x);print x}' /proc/[0-9]*/status 2>/dev/null || true)
set -- $matches
[ "$#" -eq 1 ]
p=$1
printf 'PID\t%s\n' "$p"
printf 'NSPID\t'; $bb awk '$1=="NSpid:" {for(i=2;i<=NF;i++) printf "%s%s",$i,(i==NF?"\n":" ")}' /proc/$p/status
printf 'START\t'; $bb awk '{sub(/.*\) /,"");split($0,a," ");print a[20]}' /proc/$p/stat
printf 'BOOT\t'; $bb cat /proc/sys/kernel/random/boot_id
printf 'EXE\t'; $bb readlink /proc/$p/exe
printf 'SHA\t'; $bb sha256sum /proc/$p/exe
printf 'CGROUP\t'; $bb tr '\n' '|' </proc/$p/cgroup; printf '\n'
printf 'NAME\t'; $bb cat /proc/$p/comm
printf 'PID_NS_INODE\t'; $bb stat -Lc '%i' /proc/$p/ns/pid
for f in /proc/$p/task/[0-9]*/status; do
 t=${f%/status}; t=${t##*/}
 printf 'TASK\t%s\t' "$t"
 $bb awk '$1=="NSpid:" {for(i=2;i<=NF;i++) printf "%s%s",$i,(i==NF?"\t":" ")}' "$f"
 $bb awk '{sub(/.*\) /,"");split($0,a," ");printf "%s\t",a[20]}' /proc/$p/task/$t/stat
 $bb cat /proc/$p/task/$t/comm
done
printf 'START_AFTER\t'; $bb awk '{sub(/.*\) /,"");split($0,a," ");print a[20]}' /proc/$p/stat
'''
        command = ["wsl.exe", "--system", "--user", "root", "--exec", "/usr/sbin/busybox", "sh", "-c", code,
                   "vm-root-attestation", str(docker_pid), str(starting["native_pid"])]
        raw = subprocess.run(command, check=True, timeout=15, capture_output=True, text=True).stdout
        if len(raw.encode("utf-8")) > 65536:
            raise ValueError("bounded VM-root task evidence required")
        values, tasks = {}, []
        for line in raw.splitlines():
            fields = line.split("\t")
            if fields[0] == "TASK" and len(fields) == 5:
                tasks.append({"system_proc_tid": int(fields[1]),
                              "namespace_pids": [int(value) for value in fields[2].split()],
                              "start_ticks": int(fields[3]), "task_name": fields[4]})
            elif len(fields) == 2 and fields[0] not in values:
                values[fields[0]] = fields[1]
            else:
                raise ValueError("VM-root evidence format differs")
        pid, chain, birth = int(values["PID"]), [int(value) for value in values["NSPID"].split()], int(values["START"])
        if (len(chain) < 3 or chain[0] != pid or chain[-2:] != [docker_pid, starting["native_pid"]] or
                birth != starting["native_starttime_ticks"] or int(values["START_AFTER"]) != birth or
                values["BOOT"] != kernel["boot_id"] or int(values["PID_NS_INODE"]) != kernel["proc_pid_namespace_inode"] or
                len(chain) < len(kernel["namespace_pids"]) or chain[-len(kernel["namespace_pids"]):] != kernel["namespace_pids"] or
                values["EXE"] != "/candidate/consumer" or values["SHA"].split()[0] != self.args.gpu_consumer_sha256 or
                self.cid not in values["CGROUP"] or not 1 <= len(tasks) <= 128 or
                not any(task["system_proc_tid"] == pid and task["namespace_pids"] == chain and
                        task["start_ticks"] == birth for task in tasks) or
                any(not task["namespace_pids"] or task["namespace_pids"][0] != task["system_proc_tid"] for task in tasks)):
            raise ValueError("VM-root namespace/birth/executable/hash/container/task evidence differs")
        after = time.perf_counter_ns()
        return {"schema": SCHEMA, "scope": "own-socket-kernel-PID-plus-WSL-system-proc", "container_id": self.cid,
                "container_name": self.name, "label_uuid": self.identity, "image": GPU_IMAGE, "image_id": self.image_id,
                "docker_state": state["State"], "docker_host_namespace_pid": docker_pid,
                "initial_namespace_pid": kernel["kernel_tgid"], "kernel_pid": kernel["kernel_pid"],
                "kernel_tgid": kernel["kernel_tgid"], "kernel_identity": kernel,
                "system_proc_pid": pid, "system_proc_namespace_pids": chain,
                "namespace_pids": chain, "namespace_pids_scope": "WSL-system-proc-mount", "starttime_ticks": birth,
                "boot_id": values["BOOT"], "executable": values["EXE"], "executable_sha256": values["SHA"].split()[0],
                "cgroup": values["CGROUP"], "task_name": values["NAME"], "tasks": tasks,
                "inner_native_pid": starting["native_pid"], "inner_native_starttime_ticks": starting["native_starttime_ticks"],
                "windows_QPC_before_ns": before, "windows_QPC_after_ns": after, "windows_utc_ns": time.time_ns(),
                "linux_task_evidence": {"initial_namespace_tid": kernel["kernel_pid"], "start_ticks": birth,
                                        "boot_id": values["BOOT"], "executable": values["EXE"],
                                        "kernel_tgid": kernel["kernel_tgid"], "source": "consumer-own-socket-before-HIP"},
                "process_id_in_vm_candidate": kernel["kernel_pid"], "process_name_in_vm_candidate": values["NAME"],
                "vm_guid_source": "root must bind observed Dxg VM GUID", "GPU_context_not_yet_initialized": True}


class Consumer(v1.Consumer):
    def __init__(self, args, directory):
        self.args, self.lines, self.process, self.ready = args, queue.Queue(maxsize=18), None, None
        self.container = None
        self.receipts = []
        self.init_barrier_wait_ms = 0.0
        self.stderr = (directory / "gpu-stderr.txt").open("xb")
        self.log = (directory / "gpu-stdout.jsonl").open("x", encoding="utf-8")
        try:
            if args.gpu_container:
                self.container = OwnedGpuContainer(args, directory)
                command = self.container.wsl_prefix() + ["docker", "start", "-ai", self.container.cid]
            else:
                command = ["wsl.exe", "--distribution", args.wsl_distro, "--exec", args.gpu_consumer,
                           args.engine, args.hsaco, args.hip_library, args.hip_sha256, wsl_path(directory), "--pipe-rows", args.model_binding]
            self.execution_qpc_before_ns = time.perf_counter_ns()
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.stderr, text=False, bufsize=0)
            self.reader = threading.Thread(target=self._read, daemon=True, name="handoff-GPU-output")
            self.reader.start()
            self.starting = self.receive(args.gpu_setup_timeout_s)
            if (self.starting.get("model_binding") != args.model_binding or self.starting.get("transport") != "binary-pipe" or
                    self.starting.get("kind") != "starting" or self.starting.get("GPU_context_not_yet_initialized") is not True or
                    any(type(self.starting.get(k)) is not int or self.starting[k] <= 0 for k in
                        ("native_pid", "native_starttime_ticks", "clock_ticks_per_second"))):
                raise ValueError("GPU process identity before first context initialization required")
            validate_kernel_identity(self.starting)
            self.ready = self.starting  # cancellation can bind Linux PID during HIP setup
            if self.container is not None:
                self.container_starting = self.container.attest_starting(self.starting)
                self.container_starting["execution_qpc_before_ns"] = self.execution_qpc_before_ns
                self.container_starting["qpc_frequency"] = 1_000_000_000
                publish_json(directory / "gpu-initial-namespace.json", self.container_starting)
                publish_json(directory / "gpu-vm-root-before-hip.json", self.container_starting)
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
                self.control("init")
            self.ready = self.receive(args.gpu_setup_timeout_s)
            require_same_kernel_identity(self.ready, self.starting)
            if (self.ready.get("model_binding") != args.model_binding or self.ready.get("transport") != "binary-pipe" or
                    self.ready.get("kind") != "ready" or self.ready.get("schema") != PIPE_SCHEMA or
                    self.ready.get("engine_sha256") != ENGINE_SHA or self.ready.get("codeobject_sha256") != CODE_SHA or
                    self.ready.get("hip_sha256") != args.hip_sha256 or self.ready.get("kernel") != GATHER or
                    self.ready.get("table_bytes") != ROW_BYTES or self.ready.get("destination_bytes") != ROW_BYTES or
                    self.ready.get("setup_token_h2d_bytes") != 4 or self.ready.get("gpu_arch") != "gfx1151" or
                    any(self.ready.get(k) != self.starting[k] for k in ("native_pid", "native_starttime_ticks", "clock_ticks_per_second")) or
                    any(type(self.ready.get(k)) is not int or self.ready[k] <= 0 for k in
                        ("native_pid", "native_starttime_ticks", "clock_ticks_per_second"))):
                raise ValueError("exact persistent GPU consumer ready identity/ABI required")
            if self.container is not None:
                self.container_ready = self.container.attest_starting(self.starting)
                self.container_ready["GPU_context_not_yet_initialized"] = False
                self.container_ready["GPU_context_ready"] = True
                if (self.container_ready["initial_namespace_pid"] != self.container_starting["initial_namespace_pid"] or
                        self.container_ready["boot_id"] != self.container_starting["boot_id"] or
                        self.container_ready["namespace_pids"] != self.container_starting["namespace_pids"]):
                    raise ValueError("VM-root consumer identity changed across HIP initialization")
                publish_json(directory / "gpu-vm-root-after-hip.json", self.container_ready)
        except BaseException as exc:
            cleanup_errors = self.abort()
            if cleanup_errors:
                raise RuntimeError(str(exc) + "; cleanup: " + "; ".join(cleanup_errors)) from exc
            raise

    def control(self, kind):
        write_frame(self.process.stdin, {"schema": PIPE_SCHEMA, "kind": kind, "model_binding": self.args.model_binding})

    def _read(self):
        try:
            while True:
                metadata, payload = read_frame(self.process.stdout)
                if len(self.receipts) >= ROWS+3:
                    raise ValueError("GPU reply count exceeded bounded protocol")
                self.receipts.append(metadata)
                self.lines.put((metadata, payload), timeout=1)
        except BaseException as exc:
            self.lines.put(exc, timeout=1)
        finally:
            self.lines.put(EOFError("GPU consumer output ended"), timeout=1)

    def _receive_frame(self, seconds):
        try:
            value = self.lines.get(timeout=seconds)
        except queue.Empty as exc:
            raise TimeoutError("owned GPU binary response deadline expired") from exc
        if isinstance(value, BaseException):
            raise value
        return value

    def receive(self, seconds):
        metadata, payload = self._receive_frame(seconds)
        if payload:
            raise ValueError("GPU control frame unexpectedly contains row bytes")
        return metadata

    def request(self, sequence, payload, seconds):
        write_frame(self.process.stdin, {"schema": PIPE_SCHEMA, "kind": "row", "sequence": sequence,
                    "model_binding": self.args.model_binding, "input_sha256": hashlib.sha256(payload).hexdigest(),
                    "input_bytes": ROW_BYTES}, payload)
        ack, readback = self._receive_frame(seconds)
        validate_pipe_ack(ack, readback, sequence, payload, self.ready, self.args.model_binding)
        return ack, readback

    def _flush_diagnostics(self):
        if not self.log.closed:
            for metadata in self.receipts:
                self.log.write(json.dumps(metadata, allow_nan=False)+"\n")
            self.log.flush()

    def close(self):
        self.control("quit")
        closed = self.receive(10)
        require_same_kernel_identity(closed, self.ready)
        if (closed.get("schema") != PIPE_SCHEMA or closed.get("model_binding") != self.args.model_binding or
                closed.get("transport") != "binary-pipe" or closed.get("kind") != "closed" or closed.get("passed") is not True or
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
        self._flush_diagnostics()
        self.log.close()
        self.stderr.close()
        return closed

    def abort(self):
        errors = []
        try:
            self._flush_diagnostics()
        except BaseException as exc:
            errors.append("deferred GPU metadata: "+str(exc))
        return errors+super().abort()


def record_artifacts(directory, retained, result):
    total = 0.0
    for sequence, fp32, payload, readback, publication in retained:
        if publication.get("diagnostic_artifacts_recorded"):
            continue
        started = time.perf_counter_ns()
        publication["float_artifact"] = publish_bytes(directory / f"row-{sequence:03d}-npu.f32", fp32)
        publication["bf16_artifact"] = publish_bytes(directory / f"row-{sequence:03d}-npu.u16", payload)
        publication["gpu_readback_artifact"] = publish_bytes(directory / f"row-{sequence:03d}-gpu.u16", readback)
        publication["diagnostic_artifacts_outside_timed_exchange"] = True
        publication["diagnostic_artifacts_recorded"] = True
        publish_json(directory / f"row-{sequence:03d}-npu.json", publication)
        elapsed = (time.perf_counter_ns()-started)/1e6
        result["calls"][sequence]["artifact_record_ms"] = elapsed
        total += elapsed
    result["artifact_record_total_ms"] = result.get("artifact_record_total_ms", 0.0)+total


def run(args):
    if digest(_base_path) != V1_SHA:
        raise ValueError("frozen v1 validation source differs")
    execution_started = time.perf_counter_ns()
    directory = args.output_directory.resolve()
    directory.mkdir(exist_ok=False)
    result = {"schema": SCHEMA, "passed": False, "component": "embedding-projection-to-original-GPU-gather", "transport": "binary-pipe.v3",
              "v1_validation_source_sha256": V1_SHA,
              "source_sha256": digest(__file__), "gpu_source_sha256": digest(HERE / "halogen_npu_wsl_handoff_gpu_v3.c"),
              "kernel_pid_helper_source_sha256": digest(HERE / "halogen_kernel_pid_self.c"),
              "kernel_pid_helper_header_sha256": digest(HERE / "halogen_kernel_pid_self.h"),
              "windows_pid": os.getpid(), "started_utc_ns": time.time_ns(), "calls": [], "warmups": [],
              "npu_tolerance": TOLERANCE, "tolerance_adjustment": False, "arithmetic_fitting": False,
              "live_output_swap": False, "full_D_qualified": False, "hidden_qualified": False,
              "full_head_qualified": False, "acceptance_qualified": False, "overlap_qualified": False,
              "performance_qualified": False, "native_word_parity_qualified": False, "zero_copy": False,
              "outer_owned_job_guard_required": True, "row_deadline_seconds": args.row_timeout_s,
              "gpu_rows_barrier": args.gpu_rows_barrier, "barrier_timeout_seconds": args.barrier_timeout_s,
              "timing_scope": "prepared-input copies -> fresh NPU session.run -> exact BF16 pack/validation -> binary pipe "
                              "frame -> SHA/binding check -> HIP H2D/poison -> original gather/event wait -> D2H -> "
                              "binary readback/hash/byte validation; all row artifacts after exchange and cleanup barrier; "
                              "cold setup and root barriers separate; no engine throughput claim"}
    session = ort = runtime_handle = dll = guard = consumer = None
    registered = profile_finished = False
    errors, retained = [], []
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
        args.model_binding = hashlib.sha256((result["model_sha256"]+":"+result["data_sha256"]+":"+
                                             context_sha+":"+digest(chosen)).encode("ascii")).hexdigest()
        result["pipe_model_binding"] = args.model_binding
        consumer = Consumer(args, directory)
        result.update(gpu_starting=consumer.starting, gpu_ready=consumer.ready, gpu_launch_to_ready_ms=(time.perf_counter_ns()-gpu_started)/1e6,
                      gpu_consumer=args.gpu_consumer, gpu_consumer_sha256=args.gpu_consumer_sha256,
                      gpu_init_barrier_wait_ms=consumer.init_barrier_wait_ms)
        if consumer.container is not None:
            result["gpu_initial_namespace"] = consumer.container_starting
            result["gpu_vm_root_after_hip"] = consumer.container_ready
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
            binary = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                      "transport": "binary-pipe", "model_binding": args.model_binding}
            packed = time.perf_counter_ns()
            publication = {"schema": SCHEMA, "sequence": sequence, "input_set": label,
                           "producer": "fresh-session.run/VitisAIExecutionProvider", "producer_windows_pid": os.getpid(),
                           "returned_perf_counter_ns": returned, "frame_prepared_perf_counter_ns": packed, "model_binding": args.model_binding,
                           "utc_ns": time.time_ns(), "model_sha256": MODEL_SHA,
                           "float_output_sha256": hashlib.sha256(fp32_payload).hexdigest(), "bf16_output": binary,
                           "input_sha256": feed_hashes[label], "native_GPU_comparison": metric,
                           "native_GPU_oracle_used_as_producer": False, "BF16_conversion": "exact high16 of BF16-lattice FLOAT; no rounding"}
            published = time.perf_counter_ns()
            remaining = args.row_timeout_s - (published-row_started)/1e9
            if remaining <= 0:
                raise TimeoutError("handoff deadline expired before GPU publication request")
            ack, readback = consumer.request(sequence, payload, remaining)
            acknowledged = time.perf_counter_ns()
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
                "NPU_return_pack_validate_ms": (packed-returned)/1e6,
                "pipe_exchange_ms": (acknowledged-published)/1e6, "publication_to_GPU_ack_ms": (acknowledged-published)/1e6,
                "production_to_validated_GPU_readback_ms": (done-returned)/1e6,
                "Windows_readback_verify_ms": (done-acknowledged)/1e6, "full_staged_handoff_ms": (done-row_started)/1e6})
            retained.append((sequence, fp32_payload, payload, readback, publication))
            guard.check()
        rows_completed = time.perf_counter_ns()
        result.update(gpu_rows_interval_started_perf_counter_ns=rows_started,
                      gpu_rows_interval_completed_perf_counter_ns=rows_completed,
                      gpu_rows_interval_ms=(rows_completed-rows_started)/1e6)
        result["gpu_rows_complete_marker"] = wait_gpu_rows_release(args, directory, consumer, guard, completed=True)
        result["gpu_closed"] = consumer.close()
        consumer = None
        record_artifacts(directory, retained, result)
        profile = Path(session.end_profiling())
        profile_finished = True
        profile_sha = digest(profile)
        proof = runtime.profile_proof(bounded(profile, profile_sha, 16 << 20), "npu")
        if not proof["passed"] or proof["node_events"] != WARMUPS + ROWS:
            raise RuntimeError("fresh exclusive VitisAI execution profile must cover every warmup and handoff call")
        result.update(profile=str(profile), profile_sha256=profile_sha, profile_proof=proof)
        frozen = {Path(row["path"]): row["sha256"] for row in result["immutable_files"] + oracle_files}
        frozen.update({_base_path: V1_SHA, Path(__file__): result["source_sha256"], HERE / "halogen_npu_wsl_handoff_gpu_v3.c": result["gpu_source_sha256"],
                       HERE / "halogen_kernel_pid_self.c": result["kernel_pid_helper_source_sha256"],
                       HERE / "halogen_kernel_pid_self.h": result["kernel_pid_helper_header_sha256"],
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
                                           for name in ("npu_session_run_ms", "pipe_exchange_ms", "production_to_validated_GPU_readback_ms", "full_staged_handoff_ms", "artifact_record_ms")})
    except BaseException as exc:
        result.update(passed=False, error=type(exc).__name__ + ": " + str(exc))
    finally:
        if consumer is not None:
            errors.extend(consumer.abort())
        try:
            record_artifacts(directory, retained, result)
        except BaseException as exc:
            errors.append("deferred row diagnostics: "+str(exc))
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
