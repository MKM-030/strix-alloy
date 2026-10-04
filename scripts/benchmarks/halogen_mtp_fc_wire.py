"""Pure paired count1-D FC packet codec; no devices, pointers or file I/O.

Identity pointers are opaque uint64 values and are never dereferenced. An
armed coordinator supplies expected_identity and owns live epoch/model checks,
consume-once sequencing, transport and all runtime qualification. This codec
does not create candidate arithmetic or a persistent responder.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct
from types import MappingProxyType


HEADER = struct.Struct("<8sIIiiiIiiiI16s16sQQ32s32s32s32s")
HEADER_BYTES = 224
REQUEST_MAGIC, RESPONSE_MAGIC = b"HGNFCPQ1", b"HGNFCPR1"
VERSION, COUNT, WIRE_D, MAX_CALLS = 1, 1, 68, 4
E_BYTES, H_BYTES = 5120, 20480
INPUT_BYTES = OUTPUT_BYTES = 25600
REQUEST_BODY_BYTES, RESPONSE_BODY_BYTES = 51200, 25600
REQUEST_BINDING_OFFSET, RESPONSE_DIGEST_BYTES = 192, 32
REQUEST_BYTES, RESPONSE_BYTES = 51424, 25856
QUALIFICATIONS = MappingProxyType(dict(full_d_qualified=False, full_head_qualified=False,
                                     npu_qualified=False, native_parity_qualified=False,
                                     acceptance_qualified=False, performance_qualified=False))
if HEADER.size != HEADER_BYTES:
    raise RuntimeError("paired FC header layout must be exactly 224 bytes")


def _bytes(value, size, name, nonzero=False):
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError(name + " requires exact immutable bytes")
    if nonzero and not any(value):
        raise ValueError(name + " must be nonzero")
    return value


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " is outside its fixed integer contract")


def _finite_bf16(payload, size, name):
    _bytes(payload, size, name)
    if any((word & 0x7f80) == 0x7f80 for (word,) in struct.iter_unpack("<H", payload)):
        raise ValueError(name + " contains nonfinite BF16 words")


@dataclass(frozen=True)
class FcIdentity:
    sequence: int
    position: int
    slot: int
    token: int
    outer_position: int
    run_nonce: bytes
    epoch: bytes
    model_pointer: int
    model_binding: bytes
    graph_binding: bytes

    def __post_init__(self):
        _validate_identity(self)


def _validate_identity(value):
    if not isinstance(value, FcIdentity):
        raise ValueError("FcIdentity required")
    _integer(value.sequence, 0, MAX_CALLS - 1, "sequence")
    for name in ("position", "slot", "token", "outer_position"):
        _integer(getattr(value, name), 0, (1 << 31) - 1, name)
    _integer(value.model_pointer, 1, (1 << 64) - 1, "opaque model pointer")
    _bytes(value.run_nonce, 16, "run nonce", nonzero=True)
    _bytes(value.epoch, 16, "model/reset epoch", nonzero=True)
    _bytes(value.model_binding, 32, "model binding", nonzero=True)
    _bytes(value.graph_binding, 32, "graph binding", nonzero=True)


@dataclass(frozen=True)
class ProjectionPair:
    e_projection: bytes
    h_projection: bytes

    def __post_init__(self):
        _finite_bf16(self.e_projection, E_BYTES, "embedding projection")
        _finite_bf16(self.h_projection, H_BYTES, "hidden projection")


@dataclass(frozen=True)
class FcRequest:
    identity: FcIdentity
    e_norm: bytes
    h_norm: bytes
    native_projections: ProjectionPair
    input_binding: bytes
    request_binding: bytes


def _header(magic, body_bytes, identity, input_binding, request_binding):
    _validate_identity(identity)
    _bytes(input_binding, 32, "input binding")
    _bytes(request_binding, 32, "request binding")
    return HEADER.pack(magic, VERSION, body_bytes, identity.sequence, identity.position,
                       identity.slot, 0, COUNT, identity.token, identity.outer_position, WIRE_D,
                       identity.run_nonce, identity.epoch, identity.model_pointer, 0,
                       identity.model_binding, identity.graph_binding, input_binding, request_binding)


def encode_request(identity, e_norm, h_norm, native_e_projection, native_h_projection):
    """Return the fixed 224-byte header followed by all four BF16 arrays."""
    _validate_identity(identity)
    _finite_bf16(e_norm, E_BYTES, "embedding norm")
    _finite_bf16(h_norm, H_BYTES, "hidden norm")
    pair = ProjectionPair(native_e_projection, native_h_projection)
    inputs = e_norm + h_norm
    body = inputs + pair.e_projection + pair.h_projection
    input_binding = hashlib.sha256(inputs).digest()
    prefix = _header(REQUEST_MAGIC, REQUEST_BODY_BYTES, identity, input_binding, bytes(32))[:REQUEST_BINDING_OFFSET]
    request_binding = hashlib.sha256(prefix + body).digest()
    return prefix + request_binding + body


def decode_request(packet, *, expected_identity=None):
    """Validate structure/digests; optionally require the armed exact identity."""
    _bytes(packet, REQUEST_BYTES, "request packet")
    (magic, version, size, sequence, position, slot, reserved32, count, token,
     outer_position, wire, run_nonce, epoch, model_pointer, reserved64,
     model_binding, graph_binding, input_binding, request_binding) = HEADER.unpack_from(packet)
    if (magic != REQUEST_MAGIC or version != VERSION or size != REQUEST_BODY_BYTES or
            reserved32 != 0 or reserved64 != 0 or count != COUNT or wire != WIRE_D):
        raise ValueError("request header differs from paired count1-D contract")
    identity = FcIdentity(sequence, position, slot, token, outer_position, run_nonce, epoch,
                          model_pointer, model_binding, graph_binding)
    if expected_identity is not None:
        _validate_identity(expected_identity)
        if identity != expected_identity:
            raise ValueError("request identity differs from armed coordinator")
    body = packet[HEADER_BYTES:]
    if not hmac.compare_digest(hashlib.sha256(packet[:REQUEST_BINDING_OFFSET] + body).digest(), request_binding):
        raise ValueError("request binding digest differs")
    if not hmac.compare_digest(hashlib.sha256(body[:INPUT_BYTES]).digest(), input_binding):
        raise ValueError("normalized input binding digest differs")
    e_norm, h_norm = body[:E_BYTES], body[E_BYTES:INPUT_BYTES]
    _finite_bf16(e_norm, E_BYTES, "embedding norm")
    _finite_bf16(h_norm, H_BYTES, "hidden norm")
    pair = ProjectionPair(body[INPUT_BYTES:INPUT_BYTES + E_BYTES], body[INPUT_BYTES + E_BYTES:])
    return FcRequest(identity, e_norm, h_norm, pair, input_binding, request_binding)


def make_response(request, e_projection, h_projection, *, expected_identity=None):
    """Return both finite candidates with full identity echo and final SHA256."""
    fields = decode_request(request, expected_identity=expected_identity)
    pair = ProjectionPair(e_projection, h_projection)
    header = _header(RESPONSE_MAGIC, RESPONSE_BODY_BYTES, fields.identity,
                     fields.input_binding, fields.request_binding)
    payload = header + pair.e_projection + pair.h_projection
    return payload + hashlib.sha256(payload).digest()


def validate_response(request, response, *, expected_identity=None):
    """Validate every echoed field and both outputs before returning either."""
    fields = decode_request(request, expected_identity=expected_identity)
    _bytes(response, RESPONSE_BYTES, "paired response packet")
    expected = _header(RESPONSE_MAGIC, RESPONSE_BODY_BYTES, fields.identity,
                       fields.input_binding, fields.request_binding)
    if not hmac.compare_digest(response[:HEADER_BYTES], expected):
        raise ValueError("response identity/binding echo differs from request")
    if not hmac.compare_digest(hashlib.sha256(response[:-RESPONSE_DIGEST_BYTES]).digest(), response[-RESPONSE_DIGEST_BYTES:]):
        raise ValueError("paired response digest differs")
    body = response[HEADER_BYTES:-RESPONSE_DIGEST_BYTES]
    return ProjectionPair(body[:E_BYTES], body[E_BYTES:])
