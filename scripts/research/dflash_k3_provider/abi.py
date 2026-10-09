"""Tensor-only preparation ABI; no runtime import or serving activation."""
from dataclasses import dataclass

K, HIDDEN, FUSION, LAYERS, KV_HEADS, HEAD_DIM, VOCAB = 3, 2560, 12800, 5, 2, 256, 248320
MASK_ID = 248077
NATIVE_HC_INDEXES = (4, 16, 24, 36, 44)
TRAINED_TAP_IDS = (3, 15, 23, 35, 43)
DEFAULT_CAPACITY = 16640


@dataclass(frozen=True)
class OwnerStamp:
    session_hex: str
    pending_ticket: int
    lease_generation: int
    cache_generation: int
    model_identity: str
    slot: int
    wire_id: int
    request_birth: str = ""
    holder_identity: int = 0
    model_address: int = 0
    request_address: int = 0
    total_prefill: int = 0

    def __post_init__(self):
        if len(self.session_hex) != 32 or any(c not in "0123456789abcdef" for c in self.session_hex):
            raise ValueError("Session must be the exact16-byte session identifier")
        if not self.model_identity or any(type(x) is not int or x < 0 for x in
            (self.pending_ticket, self.lease_generation, self.cache_generation, self.slot, self.wire_id,
             self.holder_identity, self.model_address, self.request_address, self.total_prefill)):
            raise ValueError("Complete native ownership fields are required")

    def transfer_to_birth(self, other):
        if not isinstance(other, OwnerStamp) or not other.request_birth or self.request_birth:
            raise ValueError("Transfer must bind an untransferred pending owner to an actual birth")
        if any(getattr(self, name) != getattr(other, name) for name in
            ("session_hex", "pending_ticket", "lease_generation", "cache_generation", "model_identity", "slot", "wire_id",
             "holder_identity", "model_address", "total_prefill")):
            raise ValueError("Request birth cannot change pending ownership generations")
        return other


def selected_rows(*, current_id, proposal_ids, verifier_ids, verifier_positions,
                  position, accepted_prefix):
    """Metadata-only selector. Caller slices BEFORE finite checks/projection."""
    expected = (current_id,) + tuple(proposal_ids)
    if len(expected) != 4 or tuple(verifier_ids) != expected:
        raise ValueError("Verifier inputs must be exact current plus this proposal")
    if any(type(i) is not int or not 0 <= i < MASK_ID for i in expected):
        raise ValueError("Reserved raw head IDs cannot be offered to the target")
    if tuple(verifier_positions) != tuple(range(position, position + 4)):
        raise ValueError("Verifier input positions do not match the proposal frontier")
    if type(accepted_prefix) is not int or not 0 <= accepted_prefix <= K:
        raise ValueError("Only the authoritative target accepted-prefix selector is admitted")
    return slice(0, accepted_prefix + 1)


def resource_plan(capacity=DEFAULT_CAPACITY):
    if type(capacity) is not int or not 1 <= capacity <= 262140:
        raise ValueError("Bound capacity explicitly within target position range")
    return {
        "enabled": False, "native_integration_complete": False,
        "capacity": capacity, "context_kv_shape": [5, 2, 2, capacity, 256],
        "context_kv_bf16_bytes": capacity * 10240,
        "target_feature_bytes_per_row": 25600,
        "maximum_verifier_feature_bytes": 102400,
        "full_original_head_bf16_bytes": VOCAB * HIDDEN * 2,
        "drafter_payload_bf16_bytes": 996213760,
        "resident_parameter_bytes": 996213760 + VOCAB * HIDDEN * 2,
        "full_head_macs_per_round": K * VOCAB * HIDDEN,
        "context_projection_macs_per_retained_row": 12800 * 2560 + 5 * 2 * 512 * 2560,
        "query_attention_score_bf16_bytes_per_layer": 24 * K * (capacity + K) * 2,
        "repeated_K_and_V_materialization_bytes_per_layer": 2 * 24 * (capacity + K) * 256 * 2,
        "grouped2d_K_and_V_bytes_per_layer": 2 * 2 * (capacity + K) * 256 * 2,
        "head_chunk_rows": 8192,
        "head_chunk_bf16_bytes": 8192 * HIDDEN * 2,
        "backbone_output_shape": [3, HIDDEN],
        "head_raw_output_shape": [3],
        "rope": "full256_NeoX_split_half;theta1e7;cos_sin_F32_then_BF16",
        "persistent_rows": "accepted_processed_target_inputs_only",
        "ephemeral_query_kv": "never_returned_or_committed",
        "full_vocab_domain": "all248320_rows;raw_ids_unsuppressed;offerable_only0..248076",
    }
