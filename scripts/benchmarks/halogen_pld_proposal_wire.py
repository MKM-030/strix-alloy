"""Default-off finite OFFLINE token-proposal codec and stock-preserving selector.

No model, engine, pointer, transport, device, or file access. A caller supplies
the immutable committed-context identity and independent currentness/token-map
truth. Those callbacks do not prove native reset/cancellation synchronization.
Returning a proposal neither injects it nor establishes native acceptance.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct
from threading import Lock
from types import MappingProxyType


MAGIC, VERSION = b"HGNPLDP1", 1
HEADER = struct.Struct("<8sII16s32s32s16s16s32sQQiQI")
HEADER_BYTES, DIGEST_BYTES = 192, 32
MAX_IDS, MAX_WINDOW_TOKENS, MAX_SUCCESSFUL_ROUNDS = 3, 512, 64
INT32_MAX, UINT64_MAX = (1 << 31) - 1, (1 << 64) - 1
MIN_PACKET_BYTES = HEADER_BYTES + 4 + DIGEST_BYTES
MAX_PACKET_BYTES = HEADER_BYTES + 4 * MAX_IDS + DIGEST_BYTES
QUALIFICATIONS = MappingProxyType(dict(
    offline_cpu_only=True, native_injection_qualified=False,
    native_epoch_reset_qualified=False, tokenizer_compatibility_qualified=False,
    npu_predictor_qualified=False, acceptance_qualified=False,
    hit_only=True, no_hit_coverage=False, performance_qualified=False,
))
if HEADER.size != HEADER_BYTES:
    raise RuntimeError("proposal header must occupy exactly 192 bytes")


def _bytes(value, size, name):
    if type(value) is not bytes or len(value) != size or not any(value):
        raise ValueError(name + " requires exact nonzero immutable bytes")
    return value


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " is outside the bounded integer contract")


@dataclass(frozen=True)
class ProposalBinding:
    model_binding: bytes
    tokenizer_binding: bytes
    request_nonce: bytes
    round_id: bytes
    committed_prefix_fingerprint: bytes
    committed_prefix_length: int
    target_position: int
    current_token: int
    window_origin: int

    def __post_init__(self):
        _validate_binding(self)


def _validate_binding(binding):
    if type(binding) is not ProposalBinding:
        raise ValueError("immutable ProposalBinding required")
    for name in ("model_binding", "tokenizer_binding", "committed_prefix_fingerprint"):
        _bytes(getattr(binding, name), 32, name)
    for name in ("request_nonce", "round_id"):
        _bytes(getattr(binding, name), 16, name)
    _integer(binding.committed_prefix_length, 1, UINT64_MAX, "committed prefix length")
    _integer(binding.target_position, 1, UINT64_MAX, "target position")
    _integer(binding.current_token, 0, INT32_MAX, "current token")
    _integer(binding.window_origin, 0, binding.committed_prefix_length - 1, "window origin")
    _integer(binding.committed_prefix_length - binding.window_origin,
             1, MAX_WINDOW_TOKENS, "committed context window length")


def _ids(ids, limit=INT32_MAX + 1):
    if type(ids) is not tuple or not 1 <= len(ids) <= MAX_IDS:
        raise ValueError("proposal requires one to three immutable int32 IDs")
    for token in ids:
        _integer(token, 0, limit - 1, "proposal token ID")
    return ids


@dataclass(frozen=True)
class Proposal:
    binding: ProposalBinding
    ids: tuple
    key_id: bytes


def encode_proposal(binding, ids, *, key_id, integrity_key):
    """Build one authenticated, bounded frame from already-independent IDs."""
    _validate_binding(binding)
    _ids(ids)
    _bytes(key_id, 16, "integrity key ID")
    _bytes(integrity_key, 32, "integrity key")
    header = HEADER.pack(
        MAGIC, VERSION, len(ids), key_id,
        binding.model_binding, binding.tokenizer_binding,
        binding.request_nonce, binding.round_id, binding.committed_prefix_fingerprint,
        binding.committed_prefix_length, binding.target_position, binding.current_token,
        binding.window_origin, binding.committed_prefix_length - binding.window_origin,
    )
    frame = header + struct.pack("<" + "i" * len(ids), *ids)
    return frame + hmac.new(integrity_key, frame, hashlib.sha256).digest()


def decode_proposal(packet, *, trusted_keys, token_id_limit):
    """Authenticate/validate a whole frame; never truncate an overlong proposal."""
    _integer(token_id_limit, 1, INT32_MAX + 1, "token ID limit")
    if type(packet) is not bytes or not MIN_PACKET_BYTES <= len(packet) <= MAX_PACKET_BYTES:
        raise ValueError("malformed bounded proposal frame")
    (magic, version, count, key_id, model, tokenizer, nonce, round_id,
     fingerprint, prefix_length, position, token, origin, window_count) = HEADER.unpack_from(packet)
    if magic != MAGIC or version != VERSION or not 1 <= count <= MAX_IDS:
        raise ValueError("proposal header/count differs from contract")
    if len(packet) != HEADER_BYTES + count * 4 + DIGEST_BYTES:
        raise ValueError("proposal frame length differs from count")
    try:
        key = trusted_keys[key_id]
    except (KeyError, TypeError):
        raise ValueError("unknown integrity key ID") from None
    _bytes(key_id, 16, "integrity key ID")
    _bytes(key, 32, "trusted integrity key")
    digest = hmac.new(key, packet[:-DIGEST_BYTES], hashlib.sha256).digest()
    if not hmac.compare_digest(digest, packet[-DIGEST_BYTES:]):
        raise ValueError("proposal integrity mismatch")
    binding = ProposalBinding(model, tokenizer, nonce, round_id, fingerprint,
                              prefix_length, position, token, origin)
    if window_count != prefix_length - origin:
        raise ValueError("proposal window count differs from committed binding")
    ids = tuple(value for (value,) in struct.iter_unpack(
        "<i", packet[HEADER_BYTES:-DIGEST_BYTES]))
    _ids(ids, token_id_limit)
    return Proposal(binding, ids, key_id)


@dataclass(frozen=True)
class SelectionContext:
    """Caller-owned native-hit snapshot; stock IDs remain an immutable tuple."""
    binding: ProposalBinding
    stock_ids: tuple
    native_allowance: int
    constraints_present: bool = False

    def __post_init__(self):
        _validate_binding(self.binding)
        if type(self.stock_ids) is not tuple:
            raise ValueError("stock IDs require the original immutable tuple")
        for token in self.stock_ids:
            _integer(token, 0, INT32_MAX, "stock token ID")
        _integer(self.native_allowance, 0, INT32_MAX, "native allowance")
        if type(self.constraints_present) is not bool:
            raise ValueError("constraint presence must be explicit bool")


@dataclass(frozen=True)
class Selection:
    ids: tuple
    used_proposal: bool
    reason: str


class ProposalSelector:
    """Own only copied trust pins and at most max_rounds consumed round keys.

    context_is_current(context) must answer from authoritative committed state,
    not packet fields, target predictions, or a manufactured opening-token hit.
    token_is_defined(ID) must answer from the trusted tokenizer's defined IDs.
    Callbacks run before the local one-shot commit; caller serialization/reset
    ownership remains external and is not proved by this offline local lock.
    """
    def __init__(self, *, trusted_model_binding, trusted_tokenizer_binding,
                 trusted_keys, token_id_limit, token_is_defined=None,
                 enabled=False, max_rounds=4):
        self._model = _bytes(trusted_model_binding, 32, "trusted model binding")
        self._tokenizer = _bytes(trusted_tokenizer_binding, 32, "trusted tokenizer binding")
        _integer(token_id_limit, 1, INT32_MAX + 1, "token ID limit")
        _integer(max_rounds, 1, MAX_SUCCESSFUL_ROUNDS, "successful round limit")
        if type(enabled) is not bool:
            raise ValueError("enabled must be explicit bool")
        if token_is_defined is not None and not callable(token_is_defined):
            raise ValueError("token definition predicate must be callable")
        keys = dict(trusted_keys)
        if not 1 <= len(keys) <= MAX_SUCCESSFUL_ROUNDS:
            raise ValueError("one to 64 trusted integrity keys required")
        for key_id, key in keys.items():
            _bytes(key_id, 16, "trusted integrity key ID")
            _bytes(key, 32, "trusted integrity key")
        self._keys = MappingProxyType(keys)
        self._token_id_limit = token_id_limit
        self._token_is_defined = token_is_defined
        self._enabled = enabled
        self._max_rounds = max_rounds
        self._consumed = set()
        self._lock = Lock()

    def select(self, packet, *, current, context_is_current=None):
        """Return original stock tuple on every decline; consume only success."""
        if type(current) is not SelectionContext:
            raise ValueError("immutable SelectionContext required")
        stock = current.stock_ids
        fallback = lambda reason: Selection(stock, False, reason)
        if not self._enabled:
            return fallback("disabled")
        if current.constraints_present:
            return fallback("constraints-present")
        cap = min(len(stock), MAX_IDS, current.native_allowance)
        if cap <= 0:
            return fallback("no-native-hit-allowance")
        if (current.binding.model_binding != self._model or
                current.binding.tokenizer_binding != self._tokenizer):
            return fallback("untrusted-current-bindings")
        try:
            proposal = decode_proposal(packet, trusted_keys=self._keys,
                                       token_id_limit=self._token_id_limit)
        except ValueError as error:
            return fallback(str(error))
        if proposal.binding != current.binding:
            return fallback("stale-or-mismatched-binding")
        if len(proposal.ids) > cap:
            return fallback("proposal-exceeds-native-stock-cap")
        if self._token_is_defined is None or not callable(context_is_current):
            return fallback("caller-truth-unavailable")
        try:
            if (current.binding.current_token >= self._token_id_limit or
                    self._token_is_defined(current.binding.current_token) is not True or
                    any(self._token_is_defined(token) is not True for token in proposal.ids)):
                return fallback("undefined-token-ID")
            if context_is_current(current) is not True:
                return fallback("caller-context-stale")
        except Exception:
            return fallback("caller-truth-unavailable")
        round_key = (current.binding.request_nonce, current.binding.round_id)
        with self._lock:
            if round_key in self._consumed:
                return fallback("round-already-used")
            if len(self._consumed) >= self._max_rounds:
                return fallback("finite-round-budget-exhausted")
            self._consumed.add(round_key)
        return Selection(proposal.ids, True, "proposal-selected")
