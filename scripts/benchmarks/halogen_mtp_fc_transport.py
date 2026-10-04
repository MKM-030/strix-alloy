"""Fixed paired-FC frames for a resident Windows/WSL/container pipe.

No processes, listeners, providers or shared-mount files are opened on import.
The root-owned launcher must supply pipes belonging to its fresh owned engine
window and enforce job/deadline/reserve cleanup. This protocol does not qualify
transport latency, native arithmetic, NPU placement, acceptance or throughput.
"""
import hashlib
import hmac
import struct


FRAME = struct.Struct("<8sIIQ32s")
PREFIX = struct.Struct("<8sIIQ")
MAGIC = b"HGFCBR01"
HELLO, ARM, REQUEST, RESPONSE, DONE, ERROR = range(1, 7)
SIZES = {HELLO: 464, ARM: 120, REQUEST: 51424, RESPONSE: 25856}
MAX_STATUS_BYTES = 4096
MAX_SEQUENCE = 3


def _contract(kind, sequence, size):
    if type(kind) is not int or kind not in (*SIZES, DONE, ERROR):
        raise ValueError("unknown FC transport frame kind")
    if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
        raise ValueError("FC transport sequence outside bounded epoch")
    if kind in (HELLO, ARM, DONE, ERROR) and sequence != 0:
        raise ValueError("control frames require sequence0")
    if kind in SIZES:
        if size != SIZES[kind]:
            raise ValueError("FC transport payload extent differs")
    elif not 1 <= size <= MAX_STATUS_BYTES:
        raise ValueError("bounded nonempty status payload required")


def encode_frame(kind, sequence, payload):
    if not isinstance(payload, bytes):
        raise ValueError("immutable transport payload required")
    _contract(kind, sequence, len(payload))
    prefix = PREFIX.pack(MAGIC, kind, len(payload), sequence)
    return prefix + hashlib.sha256(prefix + payload).digest() + payload


def _read_exact(reader, size):
    pieces, remaining = [], size
    while remaining:
        piece = reader.read(remaining)
        if not isinstance(piece, bytes) or not piece or len(piece) > remaining:
            raise EOFError("FC transport ended within a fixed frame")
        pieces.append(piece)
        remaining -= len(piece)
    return b"".join(pieces)


def read_frame(reader):
    header = _read_exact(reader, FRAME.size)
    magic, kind, size, sequence, digest = FRAME.unpack(header)
    if magic != MAGIC:
        raise ValueError("FC transport magic differs")
    # Validate extent before requesting any payload allocation/read.
    _contract(kind, sequence, size)
    payload = _read_exact(reader, size)
    if not hmac.compare_digest(hashlib.sha256(header[:PREFIX.size] + payload).digest(), digest):
        raise ValueError("FC transport digest differs")
    return kind, sequence, payload


def write_frame(writer, kind, sequence, payload):
    packet = encode_frame(kind, sequence, payload)
    remaining = memoryview(packet)
    while remaining:
        count = writer.write(remaining)
        if type(count) is not int or not 0 < count <= len(remaining):
            raise OSError("FC transport write made no bounded progress")
        remaining = remaining[count:]
    writer.flush()


def bridge_loop(reader, writer, *, expected_observation, armed_packet,
                coordinator, compute_pair, live_guard):
    """Serve four packets through already-owned resident relay pipes.

    live_guard must check the actual owned process, reserve and deadline and
    return its attested (container_pid, starttime_ticks); its exceptions abort
    this epoch. Pipes' blocking I/O must have an outer owned
    job deadline. compute_pair may be an explicitly selected native echo for
    transport qualification, or a separately screened persistent provider.
    This function never turns a callback or echo into NPU/speed qualification.
    """
    live_guard()
    kind, sequence, observation = read_frame(reader)
    if (kind, sequence, observation) != (HELLO, 0, expected_observation):
        raise ValueError("relay observation differs from admitted fresh engine")
    live_guard()
    write_frame(writer, ARM, 0, armed_packet)
    completed = 0
    while True:
        live_guard()
        kind, sequence, payload = read_frame(reader)
        if kind == ERROR:
            raise RuntimeError("container relay failed: " + payload.decode("utf-8", errors="replace"))
        if kind == DONE:
            if completed != 4:
                raise ValueError("relay ended before the exact bounded epoch")
            live_guard()
            return {"requests": completed, "relay_status": payload.decode("utf-8", errors="strict"),
                    "transport_qualified": False, "npu_qualified": False,
                    "acceptance_qualified": False, "performance_qualified": False}
        if kind != REQUEST or sequence != completed or completed >= 4:
            raise ValueError("relay request sequence differs from admitted epoch")
        process = live_guard()
        if (not isinstance(process, tuple) or len(process) != 2
                or any(type(value) is not int or value <= 0 for value in process)):
            raise ValueError("live process PID/starttime attestation required")
        # The coordinator burns the sequence BEFORE invoking the callback.
        response = coordinator.respond(payload, compute_pair,
                                       expected_pid=process[0], expected_starttime=process[1])
        live_guard()
        write_frame(writer, RESPONSE, sequence, response)
        completed += 1
