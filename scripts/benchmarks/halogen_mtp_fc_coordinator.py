"""Pure state foundation for one owned count1-D paired FC shadow epoch.

The root supplies current process identity and already verified asset/receipt
hashes. These bytes do not prove process freshness, liveness, model payload
identity, native reset interception, transport, parity or provider placement.
All pointers are opaque integers. There is no file, device, provider or network
I/O here. A candidate callback and its deadline belong to the external owner.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import struct
import threading
from types import MappingProxyType

if __package__:
    from . import halogen_mtp_fc_wire as wire
else:
    import halogen_mtp_fc_wire as wire


OBSERVATION = struct.Struct("<8sII16sIIQQQiiiiiiIIQQQQQQQQQQ120s120siiiI32s")
ARMED = struct.Struct("<8sII16s16sQ32s32s")
OBSERVATION_BYTES, OBSERVATION_DIGEST_OFFSET, ARMED_BYTES = 464, 432, 120
OBSERVATION_MAGIC, ARMED_MAGIC = b"HGNFCO01", b"HGNFCA01"
KNOWN_HEAD_RETURNS = frozenset((0x17dcc08, 0x17dcd54, 0x17dcf49, 0x17de236))
UINT64_MAX, INT32_MAX = (1 << 64) - 1, (1 << 31) - 1
QUALIFICATIONS = MappingProxyType(dict(full_d_qualified=False, full_head_qualified=False,
                                     native_parity_qualified=False, npu_qualified=False,
                                     acceptance_qualified=False, transport_qualified=False,
                                     performance_qualified=False))
ProjectionPair = wire.ProjectionPair
if OBSERVATION.size != OBSERVATION_BYTES or ARMED.size != ARMED_BYTES:
    raise RuntimeError("FC discovery/armed wire extent differs")


def _bytes(value, size, label, nonzero=False):
    if type(value) is not bytes or len(value) != size or (nonzero and not any(value)):
        raise ValueError(label + " requires exact immutable bytes")
    return value


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label + " differs from its fixed integer contract")


def _span(pointer, size):
    return 0 < pointer <= UINT64_MAX - size


@dataclass(frozen=True)
class Observation:
    run_nonce: bytes
    pid: int
    starttime: int
    head_return_rva: int
    model_pointer: int
    discovery_sequence: int
    count: int
    position: int
    token: int
    slot: int
    outer_position_before: int
    wire: int
    initialized_guard: int
    tokens_host_pointer: int
    e_norm_pointer: int
    e_projection_pointer: int
    h_norm_pointer: int
    h_projection_pointer: int
    seed_pointer: int
    e_descriptor_pointer: int
    h_descriptor_pointer: int
    e_raw_weight_pointer: int
    h_raw_weight_pointer: int
    e_descriptor: bytes
    h_descriptor: bytes
    original_head_result: int
    original_head_errno: int
    outer_position_after: int

    def __post_init__(self):
        _bytes(self.run_nonce, 16, "observation nonce", True)
        _integer(self.pid, 1, (1 << 32) - 1, "process PID")
        _integer(self.starttime, 1, UINT64_MAX, "process starttime")
        if type(self.head_return_rva) is not int or self.head_return_rva not in KNOWN_HEAD_RETURNS:
            raise ValueError("unknown native head return")
        if self.discovery_sequence != 0 or type(self.discovery_sequence) is not int:
            raise ValueError("discovery sequence must be zero")
        if self.count != 1 or type(self.count) is not int or self.wire != 68 or type(self.wire) is not int:
            raise ValueError("discovery requires count1 wire D")
        _integer(self.initialized_guard, 1, 255, "initialized wire guard")
        for name in ("position", "token", "slot", "outer_position_before", "outer_position_after",
                     "original_head_result"):
            _integer(getattr(self, name), 0, INT32_MAX, name)
        _integer(self.original_head_errno, -(1 << 31), INT32_MAX, "native errno")
        for name in ("model_pointer", "tokens_host_pointer", "e_norm_pointer", "e_projection_pointer",
                     "h_norm_pointer", "h_projection_pointer", "seed_pointer", "e_descriptor_pointer",
                     "h_descriptor_pointer", "e_raw_weight_pointer", "h_raw_weight_pointer"):
            _integer(getattr(self, name), 1, UINT64_MAX, name)
        if (not _span(self.model_pointer, 0xb10) or not _span(self.tokens_host_pointer, 4) or
                self.e_descriptor_pointer != self.model_pointer + 0x908 or
                self.h_descriptor_pointer != self.model_pointer + 0x980):
            raise ValueError("discovery host pointer layout differs")
        for descriptor, weight in ((self.e_descriptor, self.e_raw_weight_pointer),
                                   (self.h_descriptor, self.h_raw_weight_pointer)):
            _bytes(descriptor, 120, "native descriptor")
            if (struct.unpack_from("<Q", descriptor, 0)[0] or
                    struct.unpack_from("<Q", descriptor, 0x30)[0] or
                    struct.unpack_from("<Q", descriptor, 0x10)[0] != weight or
                    not _span(weight, 6963200) or weight & 15):
                raise ValueError("discovery normal raw-Q8 descriptor differs")
        spans = ((self.e_norm_pointer, wire.E_BYTES), (self.e_projection_pointer, wire.E_BYTES),
                 (self.h_norm_pointer, wire.H_BYTES), (self.h_projection_pointer, wire.H_BYTES),
                 (self.seed_pointer, wire.H_BYTES))
        for index, (pointer, size) in enumerate(spans):
            if not _span(pointer, size):
                raise ValueError("discovery tensor span overflows")
            for prior, prior_size in spans[:index]:
                if pointer < prior + prior_size and prior < pointer + size:
                    raise ValueError("discovery tensor spans overlap")


def encode_observation(observation):
    """Offline fixture encoder; never substitute a fixture for native discovery."""
    if type(observation) is not Observation:
        raise ValueError("observation requires the immutable native record type")
    payload = OBSERVATION.pack(
        OBSERVATION_MAGIC, 1, OBSERVATION_BYTES, observation.run_nonce, observation.pid, 0,
        observation.starttime, observation.head_return_rva, observation.model_pointer,
        observation.discovery_sequence, observation.count, observation.position, observation.token,
        observation.slot, observation.outer_position_before, observation.wire, observation.initialized_guard,
        observation.tokens_host_pointer, observation.e_norm_pointer, observation.e_projection_pointer,
        observation.h_norm_pointer, observation.h_projection_pointer, observation.seed_pointer,
        observation.e_descriptor_pointer, observation.h_descriptor_pointer,
        observation.e_raw_weight_pointer, observation.h_raw_weight_pointer,
        observation.e_descriptor, observation.h_descriptor, observation.original_head_result,
        observation.original_head_errno, observation.outer_position_after, 0, bytes(32))[:432]
    return payload + hashlib.sha256(payload).digest()


def decode_observation(packet, expected_run_nonce, expected_pid, expected_starttime):
    """Validate discovery against root-attested current process/run identity."""
    _bytes(packet, OBSERVATION_BYTES, "observation packet")
    _bytes(expected_run_nonce, 16, "expected run nonce", True)
    _integer(expected_pid, 1, (1 << 32) - 1, "expected PID")
    _integer(expected_starttime, 1, UINT64_MAX, "expected starttime")
    fields = OBSERVATION.unpack(packet)
    if (fields[:3] != (OBSERVATION_MAGIC, 1, OBSERVATION_BYTES) or fields[5] or fields[-2] or
            not hmac.compare_digest(hashlib.sha256(packet[:432]).digest(), fields[-1])):
        raise ValueError("native observation framing/digest differs")
    observation = Observation(fields[3], fields[4], *fields[6:-2])
    if (observation.run_nonce != expected_run_nonce or observation.pid != expected_pid or
            observation.starttime != expected_starttime):
        raise ValueError("observation differs from current owned process/run")
    return observation


@dataclass(frozen=True)
class ArmedIdentity:
    run_nonce: bytes
    epoch: bytes
    model_pointer: int
    model_binding: bytes
    graph_binding: bytes

    def __post_init__(self):
        for name in ("run_nonce", "epoch"):
            _bytes(getattr(self, name), 16, name, True)
        _integer(self.model_pointer, 1, UINT64_MAX, "armed model pointer")
        for name in ("model_binding", "graph_binding"):
            _bytes(getattr(self, name), 32, name, True)


def encode_armed(armed):
    if type(armed) is not ArmedIdentity:
        raise ValueError("arm requires immutable ArmedIdentity")
    return ARMED.pack(ARMED_MAGIC, 1, 0, armed.run_nonce, armed.epoch, armed.model_pointer,
                      armed.model_binding, armed.graph_binding)


def decode_armed(packet):
    _bytes(packet, ARMED_BYTES, "armed packet")
    magic, version, reserved, *identity = ARMED.unpack(packet)
    if magic != ARMED_MAGIC or version != 1 or reserved:
        raise ValueError("armed framing differs")
    return ArmedIdentity(*identity)


def validate_armed(observation, packet):
    if type(observation) is not Observation:
        raise ValueError("arm admission requires immutable native discovery")
    armed = decode_armed(packet)
    if armed.run_nonce != observation.run_nonce or armed.model_pointer != observation.model_pointer:
        raise ValueError("arm differs from native discovery")
    return armed


def _entries(values):
    if not isinstance(values, Mapping) or not values:
        raise ValueError("asset/receipt hashes require a nonempty named mapping")
    entries = []
    for name, digest in values.items():
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", name):
            raise ValueError("canonical entry name differs")
        if type(digest) is str and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            digest = bytes.fromhex(digest)
        entries.append((name, _bytes(digest, 32, "asset/receipt SHA256", True)))
    return tuple(sorted(entries))


@dataclass(frozen=True)
class CanonicalBinding:
    """Snapshot of caller-verified exact hashes; hashes alone confer no qualification."""
    domain: str
    assets: tuple
    receipts: tuple

    def __post_init__(self):
        if type(self.domain) is not str or self.domain not in ("model", "graph"):
            raise ValueError("binding domain must be model or graph")
        for entries in (self.assets, self.receipts):
            if type(entries) is not tuple or not entries:
                raise ValueError("canonical entries require a nonempty immutable tuple")
            names = []
            for entry in entries:
                if type(entry) is not tuple or len(entry) != 2:
                    raise ValueError("canonical entry requires a name and exact SHA256")
                name, digest = entry
                if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", name):
                    raise ValueError("canonical entry name differs")
                _bytes(digest, 32, "canonical SHA256", True)
                names.append(name)
            if names != sorted(set(names)):
                raise ValueError("canonical entries must have sorted unique names")

    @classmethod
    def from_hashes(cls, domain, *, assets, receipts):
        return cls(domain, _entries(assets), _entries(receipts))

    @property
    def canonical_bytes(self):
        value = dict(schema="halogen-mtp-fc-binding-v1", domain=self.domain,
                     assets=[dict(name=name, sha256=digest.hex()) for name, digest in self.assets],
                     receipts=[dict(name=name, sha256=digest.hex()) for name, digest in self.receipts])
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    @property
    def digest(self):
        return hashlib.sha256(self.canonical_bytes).digest()


class ShadowCoordinator:
    """One immutable arm, four ordered requests, a permanent failure latch.

    A new process/epoch requires a new externally admitted instance. Receipt
    hashes are retained in canonical bindings but are never treated as provider,
    parity, transport or speed qualification. No true qualification flags exist.
    """
    def __init__(self, observation, *, epoch, model_assets, graph_assets):
        if type(observation) is not Observation:
            raise ValueError("coordinator requires immutable native discovery")
        if (type(model_assets) is not CanonicalBinding or model_assets.domain != "model" or
                type(graph_assets) is not CanonicalBinding or graph_assets.domain != "graph"):
            raise ValueError("coordinator requires separate canonical model/graph bindings")
        self._observation, self._model_assets, self._graph_assets = observation, model_assets, graph_assets
        self._armed = ArmedIdentity(observation.run_nonce, epoch, observation.model_pointer,
                                    model_assets.digest, graph_assets.digest)
        self._lock = threading.RLock()
        self._consumed, self._failure, self._in_progress = [], None, False

    @property
    def observation(self):
        return self._observation

    @property
    def armed(self):
        return self._armed

    @property
    def armed_packet(self):
        return encode_armed(self._armed)

    @property
    def bindings(self):
        return self._model_assets, self._graph_assets

    @property
    def qualifications(self):
        return QUALIFICATIONS

    @property
    def consumed_requests(self):
        with self._lock:
            return tuple(self._consumed)

    @property
    def failure_reason(self):
        with self._lock:
            return self._failure

    def abort(self, reason="external-owner-abort"):
        """Latch an external timeout/transport/lifecycle failure, without I/O."""
        if type(reason) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", reason):
            raise ValueError("failure reason requires a bounded identifier")
        with self._lock:
            if self._failure is None:
                self._failure = reason

    def respond(self, packet, candidate, *, expected_pid, expected_starttime):
        """Burn a validated sequence before callback; return one complete paired packet.

        The caller must freshly verify PID/starttime via the owned relay. The
        callback must return ProjectionPair and enforce its own deadline; a
        timeout/exception latches failure and cannot retry these native inputs.
        """
        with self._lock:
            if self._failure is not None:
                raise ValueError("coordinator failure is latched: " + self._failure)
            try:
                if self._in_progress or not callable(candidate):
                    raise ValueError("concurrent/reentrant request or missing candidate")
                _integer(expected_pid, 1, (1 << 32) - 1, "current PID")
                _integer(expected_starttime, 1, UINT64_MAX, "current starttime")
                if (expected_pid != self._observation.pid or expected_starttime != self._observation.starttime):
                    raise ValueError("current process identity differs from native discovery")
                request = wire.decode_request(packet)
                identity, armed = request.identity, self._armed
                if (identity.sequence != len(self._consumed) or
                        identity.run_nonce != armed.run_nonce or identity.epoch != armed.epoch or
                        identity.model_pointer != armed.model_pointer or
                        identity.model_binding != armed.model_binding or identity.graph_binding != armed.graph_binding):
                    raise ValueError("request differs from armed epoch or next unused sequence")
                self._consumed.append((identity.sequence, request.request_binding))
                self._in_progress = True
            except BaseException:
                self.abort("request-admission-failed")
                raise
        try:
            pair = candidate(request)
            if type(pair) is not ProjectionPair:
                raise ValueError("candidate must return one immutable finite ProjectionPair")
            response = wire.make_response(packet, pair.e_projection, pair.h_projection,
                                          expected_identity=identity)
            wire.validate_response(packet, response, expected_identity=identity)
            with self._lock:
                if self._failure is not None:
                    raise ValueError("coordinator failed while candidate was in progress")
                return response
        except BaseException:
            self.abort("candidate-failed")
            raise
        finally:
            with self._lock:
                self._in_progress = False
