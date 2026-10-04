"""Resident Linux container relay for root-owned paired-FC shadow windows.

The future owned launcher stages this and its pinned pure codec dependencies
inside the SAME fresh container as the native shim. Binary stdin/stdout cross
Windows/WSL/docker pipes; /tmp packets never cross a shared mount. No engine,
provider or child process is launched here. Do not attach it to a user server.
Hardware/transport/parity/acceptance/performance qualification remains pending.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import stat
import sys
import time


PREFIX = "alloy-mtp-fc-quality-"
ENGINE_SHA256 = "ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("independently supplied lowercase SHA256 required")
    return value


def _stat_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def verify_source(path, wanted):
    _sha(wanted)
    before = os.lstat(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        initial = os.fstat(descriptor)
        if (_stat_identity(before) != _stat_identity(initial) or not stat.S_ISREG(initial.st_mode)
                or initial.st_nlink != 1 or not 1 <= initial.st_size <= 262144):
            raise ValueError("staged source identity/extent differs")
        content = os.read(descriptor, initial.st_size + 1)
        if (len(content) != initial.st_size or hashlib.sha256(content).hexdigest() != wanted
                or _stat_identity(initial) != _stat_identity(os.fstat(descriptor))
                or _stat_identity(initial) != _stat_identity(os.lstat(path))):
            raise ValueError("staged source bytes/identity differ")
    finally:
        os.close(descriptor)


def process_start(pid):
    with open(f"/proc/{pid}/stat", "rb", buffering=0) as stream:
        data = stream.read(4097)
    if not data or len(data) > 4096 or b") " not in data:
        raise ValueError("bounded engine process stat required")
    beginning, fields = data.rsplit(b") ", 1)
    if not beginning.startswith(str(pid).encode("ascii") + b" ("):
        raise ValueError("engine process PID differs")
    fields = fields.split()
    if len(fields) < 20 or fields[0] in (b"Z", b"X", b"x"):
        raise ProcessLookupError("engine process is terminal")
    start = int(fields[19])  # Field22; fields start at field3 after comm.
    if start <= 0:
        raise ValueError("nonzero engine process starttime required")
    return start


class ProcessGuard:
    def __init__(self, pid, starttime, lifetime):
        self.pid, self.starttime = pid, starttime
        self.deadline = time.monotonic() + lifetime

    def __call__(self):
        if time.monotonic() >= self.deadline:
            raise TimeoutError("bounded relay lifetime expired")
        if process_start(self.pid) != self.starttime:
            raise ProcessLookupError("engine PID was reused")

    def verify_engine(self):
        self()
        # /proc/<owned-pid>/exe is intentionally followed; engine identity is
        # checked on both sides. It is never an arbitrary packet-provided path.
        with open(f"/proc/{self.pid}/exe", "rb", buffering=0) as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or initial.st_size != 26052768:
                raise ValueError("owned engine ELF extent differs")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != ENGINE_SHA256 or _stat_identity(initial) != _stat_identity(os.fstat(stream.fileno())):
                raise ValueError("owned engine ELF differs")
        self()


class DeadlinePipe:
    def __init__(self, descriptor, guard):
        self.descriptor, self.guard = descriptor, guard
        os.set_blocking(descriptor, False)

    def read(self, count):
        while True:
            self.guard()
            if not select.select([self.descriptor], [], [], .01)[0]:
                continue
            try:
                return os.read(self.descriptor, count)
            except BlockingIOError:
                continue

    def write(self, payload):
        while True:
            self.guard()
            if not select.select([], [self.descriptor], [], .01)[1]:
                continue
            try:
                return os.write(self.descriptor, payload)
            except BlockingIOError:
                continue

    def flush(self):
        self.guard()


class PacketDirectory:
    def __init__(self, path, uid):
        if not re.fullmatch(r"/tmp/alloy-mtp-fc-quality-[0-9a-f]{32}", path):
            raise ValueError("fresh constructor-owned container directory required")
        self.basename, self.uid = Path(path).name, uid
        self.parent = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.descriptor = -1
        try:
            self.descriptor = os.open(self.basename, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                      dir_fd=self.parent)
            initial = os.fstat(self.descriptor)
            if initial.st_uid != uid or initial.st_mode & 0o777 != 0o700:
                raise ValueError("constructor-owned directory owner/mode differs")
            self.identity = (initial.st_dev, initial.st_ino)
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        handle = os.fstat(self.descriptor)
        path = os.stat(self.basename, dir_fd=self.parent, follow_symlinks=False)
        for value in (handle, path):
            if (not stat.S_ISDIR(value.st_mode) or value.st_uid != self.uid
                    or value.st_mode & 0o777 != 0o700 or (value.st_dev, value.st_ino) != self.identity):
                raise ValueError("constructor-owned directory changed")

    def read(self, name, size):
        if not re.fullmatch(r"observed\.bin|armed|records\.jsonl|00[0-3]-request\.bin", name):
            raise ValueError("fixed native packet filename required")
        self.check()
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=self.descriptor)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(descriptor)
            if name == "records.jsonl" and size is None:
                if not 1 <= before.st_size <= 32768:
                    raise ValueError("native discovery log extent differs")
                size = before.st_size
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != self.uid or before.st_nlink != 1
                    or before.st_mode & 0o777 != 0o600 or before.st_size != size):
                raise ValueError("native packet owner/mode/extent differs")
            pieces, offset = [], 0
            while offset < size:
                piece = os.pread(descriptor, size - offset, offset)
                if not piece:
                    raise EOFError("native packet ended before its fixed extent")
                pieces.append(piece)
                offset += len(piece)
            after = os.fstat(descriptor)
            path = os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
            if _stat_identity(before) != _stat_identity(after) or _stat_identity(after) != _stat_identity(path):
                if name == "records.jsonl":
                    # The native writer publishes its bounded discovery line
                    # before the arming rendezvous. Retry an active append.
                    return None
                raise ValueError("native packet identity changed while reading")
            self.check()
            return b"".join(pieces)
        finally:
            os.close(descriptor)

    def publish(self, name, content):
        if not re.fullmatch(r"armed|00[0-3]-response\.bin", name) or not isinstance(content, bytes):
            raise ValueError("fixed paired reply publication required")
        self.check()
        temporary = "relay-" + name + ".partial"
        descriptor = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                             0o600, dir_fd=self.descriptor)
        published = False
        try:
            initial = os.fstat(descriptor)
            if (not stat.S_ISREG(initial.st_mode) or initial.st_uid != self.uid or initial.st_nlink != 1
                    or initial.st_mode & 0o777 != 0o600 or initial.st_size != 0):
                raise ValueError("reply staging owner/mode differs")
            remainder = memoryview(content)
            while remainder:
                count = os.write(descriptor, remainder)
                if count <= 0:
                    raise OSError("reply staging made no progress")
                remainder = remainder[count:]
            os.fsync(descriptor)
            staged = os.fstat(descriptor)
            staged_path = os.stat(temporary, dir_fd=self.descriptor, follow_symlinks=False)
            if (staged.st_size != len(content) or staged.st_dev != initial.st_dev or staged.st_ino != initial.st_ino
                    or staged.st_uid != self.uid or staged.st_mode & 0o777 != 0o600 or staged.st_nlink != 1
                    or _stat_identity(staged) != _stat_identity(staged_path)
                    or os.pread(descriptor, len(content) + 1, 0) != content
                    or _stat_identity(staged) != _stat_identity(os.fstat(descriptor))):
                raise ValueError("paired reply staging bytes/identity changed")
            self.check()
            # link/unlink would expose transient nlink2 for armed, which the
            # native shim correctly rejects. Linux NOREPLACE rename keeps1.
            libc = ctypes.CDLL(None, use_errno=True)
            rename = libc.renameat2
            rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
            rename.restype = ctypes.c_int
            if rename(self.descriptor, temporary.encode("ascii"), self.descriptor, name.encode("ascii"), 1):
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code))
            published = True
            os.fsync(self.descriptor)
            final = os.fstat(descriptor)
            final_path = os.stat(name, dir_fd=self.descriptor, follow_symlinks=False)
            if (_stat_identity(final) != _stat_identity(final_path)
                    or final.st_dev != initial.st_dev or final.st_ino != initial.st_ino
                    or final.st_size != len(content) or final.st_uid != self.uid
                    or final.st_mode & 0o777 != 0o600 or final.st_nlink != 1
                    or os.pread(descriptor, len(content) + 1, 0) != content
                    or _stat_identity(final) != _stat_identity(os.fstat(descriptor))
                    or _stat_identity(final) != _stat_identity(os.stat(name, dir_fd=self.descriptor,
                                                                       follow_symlinks=False))):
                raise ValueError("published paired reply bytes/identity changed")
            self.check()
        finally:
            if descriptor != -1:
                os.close(descriptor)
            if not published:
                try:
                    os.unlink(temporary, dir_fd=self.descriptor)
                except FileNotFoundError:
                    pass

    def close(self):
        for name in ("descriptor", "parent"):
            descriptor = getattr(self, name, -1)
            if descriptor != -1:
                os.close(descriptor)
                setattr(self, name, -1)


def run(args):
    if sys.platform != "linux" or platform.machine() != "x86_64" or os.geteuid() != args.uid:
        raise ValueError("same-uid Linux x86-64 container relay required")
    here = Path(__file__).absolute().parent
    for name, wanted in ((Path(__file__).name, args.self_sha256),
                         ("halogen_mtp_fc_transport.py", args.transport_sha256),
                         ("halogen_mtp_fc_coordinator.py", args.coordinator_sha256),
                         ("halogen_mtp_fc_wire.py", args.wire_sha256)):
        verify_source(here / name, wanted)
    import halogen_mtp_fc_transport as transport
    import halogen_mtp_fc_coordinator as coordinator
    import halogen_mtp_fc_wire as wire
    guard = ProcessGuard(args.engine_pid, args.engine_starttime, args.lifetime_seconds)
    guard.verify_engine()
    packets = PacketDirectory(args.directory, args.uid)
    reader, writer = DeadlinePipe(0, guard), DeadlinePipe(1, guard)
    try:
        nonce = bytes.fromhex(Path(args.directory).name[len(PREFIX):])
        while True:
            guard()
            observation_packet = packets.read("observed.bin", coordinator.OBSERVATION_BYTES)
            if observation_packet is not None:
                break
            time.sleep(.002)
        observation = coordinator.decode_observation(observation_packet, expected_run_nonce=nonce,
                                                    expected_pid=args.engine_pid,
                                                    expected_starttime=args.engine_starttime)
        while True:
            guard()
            record_packet = packets.read("records.jsonl", None)
            if record_packet is not None and record_packet.endswith(b"\n"):
                records = [json.loads(line) for line in record_packet.splitlines()]
                if any(row.get("discovery") is True and
                       (row.get("error") is not None or row.get("outcome") != "native_discovery_published")
                       for row in records):
                    raise ValueError("native discovery already ended before this arming handshake")
                matches = [row for row in records if row.get("discovery") is True
                           and row.get("outcome") == "native_discovery_published"]
                if len(matches) > 1:
                    raise ValueError("discovery receipt was repeated")
                if matches:
                    row = matches[0]
                    required = {"sequence": 0, "completed": True, "error": None,
                                "position": observation.position, "outer_position": observation.outer_position_before,
                                "slot": observation.slot, "token": observation.token,
                                "model": hex(observation.model_pointer), "head_result": observation.original_head_result,
                                "head_errno": observation.original_head_errno,
                                "e_calls": 1, "h_calls": 1, "original_e_calls": 1, "original_h_calls": 1,
                                "e_launches": 1, "h_launches": 1, "e_launch_ok": 1, "h_launch_ok": 1,
                                "captured": False, "response_ready": False, "candidate_published": False,
                                "native_restored": False, "sync_attempts": 0, "copy_attempts": 0,
                                "restore_attempts": 0, "overlaps": 0}
                    if any(type(row.get(key)) is not type(value) or row.get(key) != value
                           for key, value in required.items()):
                        raise ValueError("native discovery receipt counters/identity differ")
                    break
            time.sleep(.001)
        transport.write_frame(writer, transport.HELLO, 0, observation_packet)
        kind, sequence, arm = transport.read_frame(reader)
        if kind != transport.ARM or sequence != 0:
            raise ValueError("armed frame required after fresh observation")
        admitted = coordinator.validate_armed(observation, arm)
        guard()
        if packets.read("observed.bin", coordinator.OBSERVATION_BYTES) != observation_packet:
            raise ValueError("native discovery record changed before arming")
        packets.publish("armed", arm)
        for sequence in range(4):
            while True:
                guard()
                if (packets.read("armed", coordinator.ARMED_BYTES) != arm
                        or packets.read("observed.bin", coordinator.OBSERVATION_BYTES) != observation_packet):
                    raise ValueError("discovery/armed epoch changed during relay")
                request = packets.read(f"{sequence:03d}-request.bin", wire.REQUEST_BYTES)
                if request is not None:
                    break
                time.sleep(.001)
            fields = wire.decode_request(request)
            # validate_armed returns immutable opaque identity bindings.
            if (fields.identity.sequence != sequence or fields.identity.run_nonce != admitted.run_nonce
                    or fields.identity.epoch != admitted.epoch
                    or fields.identity.model_pointer != admitted.model_pointer
                    or fields.identity.model_binding != admitted.model_binding
                    or fields.identity.graph_binding != admitted.graph_binding):
                raise ValueError("native request differs from admitted fresh epoch")
            transport.write_frame(writer, transport.REQUEST, sequence, request)
            kind, returned_sequence, response = transport.read_frame(reader)
            if kind != transport.RESPONSE or returned_sequence != sequence:
                raise ValueError("paired response frame required for consumed sequence")
            wire.validate_response(request, response, expected_identity=fields.identity)
            guard()
            if (packets.read("armed", coordinator.ARMED_BYTES) != arm
                    or packets.read("observed.bin", coordinator.OBSERVATION_BYTES) != observation_packet):
                raise ValueError("discovery/armed epoch changed before paired reply")
            packets.publish(f"{sequence:03d}-response.bin", response)
        transport.write_frame(writer, transport.DONE, 0, b'{"requests":4,"transport_qualified":false}')
    finally:
        packets.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--engine-pid", type=int, required=True)
    parser.add_argument("--engine-starttime", type=int, required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--lifetime-seconds", type=int, default=45)
    for name in ("self", "transport", "coordinator", "wire"):
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args()
    if not 1 <= args.engine_pid <= (1 << 31) - 1 or args.engine_starttime <= 0 or args.uid < 0:
        parser.error("valid fresh process and same-uid identity required")
    if not 1 <= args.lifetime_seconds <= 45:
        parser.error("relay lifetime must be bounded to at most45seconds")
    try:
        run(args)
    except Exception as error:
        # stderr is kept separate from binary stdout by the owned launcher.
        print(type(error).__name__ + ": " + str(error), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
