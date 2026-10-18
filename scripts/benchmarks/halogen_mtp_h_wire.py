"""Pure input-only H codec. Imports no hardware and performs no I/O.

The owner supplies live identity/epoch guards, consume-once sequencing and
bounded resident transport. Digests bind bytes; they do not authenticate peers
or qualify the arithmetic, consumer, Windows/WSL transport, or performance.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct
from types import MappingProxyType

HEADER = struct.Struct("<8sIIiiiIiiiI16s16sQQ32s32s32s32s")
HELLO_HEADER = struct.Struct("<8sIIQ16s16s32s32s32sII")
FRAME_HEADER = struct.Struct("<8sIIQ32s")
HEADER_BYTES, HELLO_BYTES, FRAME_BYTES = 224, 160, 56
H_BYTES, REQUEST_BYTES, RESPONSE_BYTES = 20480, 20704, 20736
REQUEST_BINDING_OFFSET = 192
VERSION, COUNT, WIRE_D, MAX_CALLS = 1, 1, 68, 64
REQUEST_MAGIC, RESPONSE_MAGIC = b"HGNHCPQ1", b"HGNHCPR1"
HELLO_MAGIC, READY_MAGIC, FRAME_MAGIC = b"HGNHHEL1", b"HGNHACK1", b"HGNHFRM1"
HELLO, READY, REQUEST, RESPONSE = 1, 2, 3, 4
FRAME_SIZES = MappingProxyType({HELLO: HELLO_BYTES, READY: HELLO_BYTES,
                               REQUEST: REQUEST_BYTES, RESPONSE: RESPONSE_BYTES})
ENGINE_SHA256 = bytes.fromhex("ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b")
QUALIFICATIONS = MappingProxyType(dict(transport_qualified=False, full_head_qualified=False,
    arithmetic_qualified=False, npu_qualified=False, native_parity_qualified=False,
    acceptance_qualified=False, performance_qualified=False, native_reset_interception_qualified=False))
if (HEADER.size, HELLO_HEADER.size, FRAME_HEADER.size) != (224, 160, 56):
    raise RuntimeError("H-only ABI layout differs")


def _bytes(value, size, name, nonzero=False):
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError(name + " requires exact immutable bytes")
    if nonzero and not any(value):
        raise ValueError(name + " must be nonzero")
    return value


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " is outside its fixed integer contract")


def _finite(payload, name):
    _bytes(payload, H_BYTES, name)
    if any(word & 0x7f80 == 0x7f80 for (word,) in struct.iter_unpack("<H", payload)):
        raise ValueError(name + " contains nonfinite BF16 words")


@dataclass(frozen=True)
class HSession:
    process_id: int
    run_nonce: bytes
    epoch: bytes
    model_binding: bytes
    graph_binding: bytes

    def __post_init__(self):
        _integer(self.process_id, 1, (1 << 31) - 1, "process id")
        for name, size in (("run_nonce", 16), ("epoch", 16), ("model_binding", 32), ("graph_binding", 32)):
            _bytes(getattr(self, name), size, name, True)


@dataclass(frozen=True)
class HIdentity:
    sequence: int
    position: int
    slot: int
    token: int
    outer_position: int
    process_id: int
    run_nonce: bytes
    epoch: bytes
    model_pointer: int
    model_binding: bytes
    graph_binding: bytes

    def __post_init__(self):
        _integer(self.sequence, 0, MAX_CALLS - 1, "sequence")
        for name in ("position", "slot", "token", "outer_position"):
            _integer(getattr(self, name), 0, (1 << 31) - 1, name)
        _integer(self.model_pointer, 1, (1 << 64) - 1, "opaque model pointer")
        self.session()

    def session(self):
        return HSession(self.process_id, self.run_nonce, self.epoch, self.model_binding, self.graph_binding)


@dataclass(frozen=True)
class HRequest:
    identity: HIdentity
    h_norm: bytes
    input_binding: bytes
    request_binding: bytes


def _identity(value):
    if not isinstance(value, HIdentity):
        raise ValueError("HIdentity required")
    value.__post_init__()


def _session(value):
    if not isinstance(value, HSession):
        raise ValueError("HSession required")
    value.__post_init__()


def _header(magic, identity, input_binding, request_binding):
    _identity(identity)
    _bytes(input_binding, 32, "input binding")
    _bytes(request_binding, 32, "request binding")
    return HEADER.pack(magic, VERSION, H_BYTES, identity.sequence, identity.position, identity.slot,
        0, COUNT, identity.token, identity.outer_position, WIRE_D, identity.run_nonce,
        identity.epoch, identity.model_pointer, identity.process_id, identity.model_binding,
        identity.graph_binding, input_binding, request_binding)


def encode_request(identity, h_norm):
    _finite(h_norm, "hidden norm")
    input_binding = hashlib.sha256(h_norm).digest()
    prefix = _header(REQUEST_MAGIC, identity, input_binding, bytes(32))[:REQUEST_BINDING_OFFSET]
    return prefix + hashlib.sha256(prefix + h_norm).digest() + h_norm


def decode_request(packet, *, expected_identity=None, expected_session=None):
    _bytes(packet, REQUEST_BYTES, "H request")
    (magic, version, size, sequence, position, slot, reserved, count, token, outer_position,
     wire, nonce, epoch, model, process_id, model_binding, graph_binding,
     input_binding, request_binding) = HEADER.unpack_from(packet)
    if (magic, version, size, reserved, count, wire) != (REQUEST_MAGIC, VERSION, H_BYTES, 0, COUNT, WIRE_D):
        raise ValueError("request header differs from H-only count1-D contract")
    identity = HIdentity(sequence, position, slot, token, outer_position, process_id, nonce,
                         epoch, model, model_binding, graph_binding)
    if expected_identity is not None:
        _identity(expected_identity)
        if identity != expected_identity:
            raise ValueError("request identity differs from owned identity")
    if expected_session is not None:
        _session(expected_session)
        if identity.session() != expected_session:
            raise ValueError("request identity differs from owned session")
    body = packet[HEADER_BYTES:]
    if not hmac.compare_digest(hashlib.sha256(packet[:REQUEST_BINDING_OFFSET] + body).digest(), request_binding):
        raise ValueError("request binding digest differs")
    if not hmac.compare_digest(hashlib.sha256(body).digest(), input_binding):
        raise ValueError("normalized input binding digest differs")
    _finite(body, "hidden norm")
    return HRequest(identity, body, input_binding, request_binding)


def make_response(request, h_projection, *, expected_identity=None, expected_session=None):
    fields = decode_request(request, expected_identity=expected_identity, expected_session=expected_session)
    _finite(h_projection, "hidden projection")
    payload = _header(RESPONSE_MAGIC, fields.identity, fields.input_binding, fields.request_binding) + h_projection
    return payload + hashlib.sha256(payload).digest()


def validate_response(request, response, *, expected_identity=None, expected_session=None):
    fields = decode_request(request, expected_identity=expected_identity, expected_session=expected_session)
    _bytes(response, RESPONSE_BYTES, "H response")
    expected = _header(RESPONSE_MAGIC, fields.identity, fields.input_binding, fields.request_binding)
    if not hmac.compare_digest(response[:HEADER_BYTES], expected):
        raise ValueError("response identity/binding echo differs")
    if not hmac.compare_digest(hashlib.sha256(response[:-32]).digest(), response[-32:]):
        raise ValueError("response digest differs")
    body = response[HEADER_BYTES:-32]
    _finite(body, "hidden projection")
    return body


def encode_hello(session):
    _session(session)
    return HELLO_HEADER.pack(HELLO_MAGIC, VERSION, MAX_CALLS, session.process_id, session.run_nonce,
                            session.epoch, session.model_binding, session.graph_binding,
                            ENGINE_SHA256, H_BYTES, WIRE_D)


def decode_hello(hello, *, expected_session=None):
    _bytes(hello, HELLO_BYTES, "hello")
    magic, version, budget, pid, nonce, epoch, model, graph, engine, size, wire = HELLO_HEADER.unpack(hello)
    if (magic, version, budget, engine, size, wire) != (HELLO_MAGIC, VERSION, MAX_CALLS, ENGINE_SHA256, H_BYTES, WIRE_D):
        raise ValueError("hello contract differs")
    session = HSession(pid, nonce, epoch, model, graph)
    if expected_session is not None:
        _session(expected_session)
        if session != expected_session:
            raise ValueError("hello differs from owned session")
    return session


def make_ready(hello, *, expected_session=None):
    decode_hello(hello, expected_session=expected_session)
    return READY_MAGIC + hello[8:]


def validate_ready(hello, ready, *, expected_session=None):
    expected = make_ready(hello, expected_session=expected_session)
    _bytes(ready, HELLO_BYTES, "ready")
    if not hmac.compare_digest(ready, expected):
        raise ValueError("ready differs from complete owned hello")


def _frame_fields(kind, sequence):
    _integer(kind, HELLO, RESPONSE, "frame kind")
    _integer(sequence, 0, 0 if kind in (HELLO, READY) else MAX_CALLS - 1, "frame sequence")


def _packet_sequence(kind, sequence, payload):
    if kind in (REQUEST, RESPONSE) and struct.unpack_from("<i", payload, 16)[0] != sequence:
        raise ValueError("packet sequence differs from frame sequence")


def encode_frame(kind, sequence, payload):
    _frame_fields(kind, sequence)
    _bytes(payload, FRAME_SIZES[kind], "frame payload")
    _packet_sequence(kind, sequence, payload)
    return FRAME_HEADER.pack(FRAME_MAGIC, kind, len(payload), sequence, hashlib.sha256(payload).digest()) + payload


def decode_frame(frame, *, expected_kind, expected_sequence):
    _frame_fields(expected_kind, expected_sequence)
    _bytes(frame, FRAME_BYTES + FRAME_SIZES[expected_kind], "frame")
    magic, kind, size, sequence, digest = FRAME_HEADER.unpack_from(frame)
    if (magic, kind, size, sequence) != (FRAME_MAGIC, expected_kind, FRAME_SIZES[expected_kind], expected_sequence):
        raise ValueError("frame header/sequence differs")
    payload = frame[FRAME_BYTES:]
    if not hmac.compare_digest(hashlib.sha256(payload).digest(), digest):
        raise ValueError("frame payload digest differs")
    _packet_sequence(kind, sequence, payload)
    return payload
