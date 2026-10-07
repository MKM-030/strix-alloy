"""Default-off, offline PLD embedding-prefix/native-correction contract.

Only copied host token IDs and caller-supplied identity/readiness claims enter
this module. It performs no I/O, native hook, pointer access, device operation,
provider execution, or timing measurement. An enabled split is an arithmetic
schedule for future qualification; it never admits a live native work skip.
"""
from dataclasses import dataclass


TOKEN_COUNT = 248320
MAX_PROPOSALS = 3
MAX_REPLAY_ROWS = 4
MAX_POSITION = (1 << 31) - 1
ROW_BYTES = 5120
SLAB_BYTES = MAX_REPLAY_ROWS * ROW_BYTES
PLD_VERIFIER_RETURN_RVA = 0x172D61D
ACCEPTED_HEAD_RETURN_RVA = 0x17DCD54


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " is outside its bounded integer contract")
    return value


def _blob(value, size, name):
    if type(value) is not bytes or len(value) != size or not any(value):
        raise ValueError(name + " requires immutable nonzero bytes of the exact extent")


def _boolean(value, name):
    if type(value) is not bool:
        raise ValueError(name + " requires a boolean")


def _tokens(value, minimum, maximum):
    if type(value) not in (tuple, list) or not minimum <= len(value) <= maximum:
        raise ValueError("copied token snapshot exceeds the bounded row contract")
    return tuple(_integer(token, 0, TOKEN_COUNT - 1, "token") for token in value)


@dataclass(frozen=True)
class RoundIdentity:
    """Opaque metadata supplied by the future owner, not a lifetime proof."""

    request_nonce: bytes
    model_generation: bytes
    source_epoch: bytes
    round_id: int

    def __post_init__(self):
        _blob(self.request_nonce, 16, "request nonce")
        _blob(self.model_generation, 16, "model generation")
        _blob(self.source_epoch, 32, "table/gamma/weight source epoch")
        _integer(self.round_id, 1, (1 << 63) - 1, "one-shot round ID")


@dataclass(frozen=True)
class PldProducerPlan:
    identity: RoundIdentity
    base_position: int
    current_token: int
    proposal_tokens: tuple
    native_proposal_allowance: int

    def __post_init__(self):
        if type(self.identity) is not RoundIdentity:
            raise ValueError("RoundIdentity required")
        _integer(self.base_position, 1, MAX_POSITION, "verification base position")
        _integer(self.current_token, 0, TOKEN_COUNT - 1, "current token")
        if type(self.proposal_tokens) is not tuple:
            raise ValueError("proposal rows require an immutable ordered snapshot")
        _tokens(self.proposal_tokens, 1, MAX_PROPOSALS)
        _integer(self.native_proposal_allowance, 1, MAX_PROPOSALS, "native allowance")
        if len(self.proposal_tokens) > self.native_proposal_allowance:
            raise ValueError("proposal count exceeds the actual native allowance")
        if self.base_position + len(self.proposal_tokens) + 1 > MAX_POSITION:
            raise ValueError("verification end position exceeds the native int32 contract")


@dataclass(frozen=True)
class ClaimedPublication:
    """Metadata-only claim for ordered rows and a four-row exclusive slab.

    True flags cannot prove an event, allocation, arithmetic result, or lease.
    The future native owner must establish those facts before using this plan.
    """

    identity: RoundIdentity
    proposal_tokens: tuple
    device_event_complete: bool
    exclusive_slab_lease: bool
    producer_writes_closed: bool
    slab_rows: int

    def __post_init__(self):
        if type(self.identity) is not RoundIdentity:
            raise ValueError("RoundIdentity required")
        if type(self.proposal_tokens) is not tuple:
            raise ValueError("published row order must be an immutable snapshot")
        _tokens(self.proposal_tokens, 1, MAX_PROPOSALS)
        _boolean(self.device_event_complete, "event-complete claim")
        _boolean(self.exclusive_slab_lease, "exclusive-lease claim")
        _boolean(self.producer_writes_closed, "producer-writes-closed claim")
        _integer(self.slab_rows, 1, MAX_REPLAY_ROWS, "claimed slab row extent")


@dataclass(frozen=True)
class MixedReplayPlan:
    mode: str
    reason: str
    head_tokens: tuple
    prepared_prefix_tokens: tuple
    native_embedding_tokens: tuple
    native_token_offset_bytes: int
    native_input_offset_bytes: int
    native_fc_output_offset_bytes: int

    @property
    def head_count(self):
        return len(self.head_tokens)

    @property
    def native_embedding_count(self):
        return len(self.native_embedding_tokens)

    @property
    def native_fc_m(self):
        return self.native_embedding_count

    @property
    def removed_embedding_rows(self):
        return len(self.prepared_prefix_tokens)

    @property
    def hidden_fc_m(self):
        return 4 * self.head_count

    @property
    def seed_count(self):
        return self.head_count

    @property
    def layer48_count(self):
        return self.head_count

    @property
    def seed_embedding_source(self):
        return "private_round_slab" if self.mode == "mixed" else "native_model_b00"

    @property
    def seed_arg0_rewrite(self):
        return self.mode == "mixed"

    # These are deliberately independent of the caller's metadata claims.
    rebind_model_b00 = False
    native_skip_admitted = False
    device_execution_proved = False
    speed_claim = False


def plan_pld_round(*, identity, input_tokens, base_position,
                   native_proposal_allowance, verifier_caller_rva):
    """Copy [current,drafts...] at verifier entry before forwarding stock once.

    Only the native PLD call at 0x172d618/return 0x172d61d is in this first
    contract. Its constraints and opening-token gate have already run. Ordered
    proposal rows are not deduplicated: slab row i must correspond to draft i.
    """
    if _integer(verifier_caller_rva, 0, (1 << 64) - 1, "verifier caller") != PLD_VERIFIER_RETURN_RVA:
        raise ValueError("the producer is confined to the native PLD verifier caller")
    copied = _tokens(input_tokens, 2, MAX_REPLAY_ROWS)
    return PldProducerPlan(identity, base_position, copied[0], copied[1:],
                           native_proposal_allowance)


def plan_mixed_replay(plan, *, identity, head_tokens, head_position,
                      head_caller_rva, wire, publication=None,
                      enable_offline_split=False):
    """Plan only a complete prepared prefix plus one native correction.

    Default-off or mismatched/stale/pending metadata returns the whole observed
    native embedding branch. Malformed bounded input raises ValueError before
    returning any split. A future adapter must leave stock untouched on either
    rejection. This pure function neither consumes a lease nor prevents a
    second use of a round; the future owner must enforce one-shot ownership.
    """
    if type(plan) is not PldProducerPlan or type(identity) is not RoundIdentity:
        raise ValueError("producer plan and RoundIdentity required")
    _boolean(enable_offline_split, "offline split enable")
    actual = _tokens(head_tokens, 1, MAX_REPLAY_ROWS)
    _integer(head_position, 0, MAX_POSITION, "head position")
    _integer(head_caller_rva, 0, (1 << 64) - 1, "head caller")
    if head_position + len(actual) > MAX_POSITION:
        raise ValueError("replay end position exceeds the native int32 contract")

    def native(reason):
        return MixedReplayPlan("native", reason, actual, (), actual, 0, 0, 0)

    if not enable_offline_split:
        return native("offline-split-disabled")
    if identity != plan.identity:
        return native("stale-round-identity")
    if head_caller_rva != ACCEPTED_HEAD_RETURN_RVA or wire != "D":
        return native("unsupported-replay-caller-or-wire")
    if head_position != plan.base_position or len(actual) > len(plan.proposal_tokens) + 1:
        return native("replay-base-or-count-mismatch")
    prefix = actual[:-1]
    if prefix != plan.proposal_tokens[:len(prefix)]:
        return native("accepted-prefix-mismatch")
    if not prefix:
        return native("count-one-has-only-the-native-correction")
    if type(publication) is not ClaimedPublication:
        return native("no-claimed-publication")
    if (publication.identity != plan.identity or
            publication.proposal_tokens != plan.proposal_tokens or
            publication.slab_rows != MAX_REPLAY_ROWS or
            not publication.device_event_complete or
            not publication.exclusive_slab_lease or
            not publication.producer_writes_closed):
        return native("unusable-claimed-publication")

    accepted = len(prefix)
    row_offset = accepted * ROW_BYTES
    return MixedReplayPlan("mixed", "offline-prefix-native-correction-split", actual,
                           prefix, actual[-1:], accepted * 4, row_offset, row_offset)
