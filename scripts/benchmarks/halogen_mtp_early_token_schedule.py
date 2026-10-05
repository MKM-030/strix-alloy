"""Pure host-token schedule for a future early embedding producer.

This implements the token shift in the retained Halogen 0.16.2 target/replay
source. It has no file I/O, device pointers, threads, provider imports, tensor
payloads or native hook. The caller supplies already copied host IDs and one
immutable model generation. A schedule is neither a live producer nor arithmetic
admission. Claimed ready token IDs are only planning inputs: this module cannot
prove that an upload completed or authorize skipping an original FC.
"""
from dataclasses import dataclass


TOKEN_COUNT = 248320
MAX_ROWS = 8192
MAX_POSITION = (1 << 31) - 1


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(name + " is outside its bounded integer contract")
    return value


def _generation(value):
    if not isinstance(value, bytes) or len(value) != 16 or not any(value):
        raise ValueError("a nonzero immutable 16-byte model generation is required")
    return value


def _tokens(value):
    # Avoid consuming an unbounded iterable or retaining mutable host storage.
    if not isinstance(value, (tuple, list)) or not 1 <= len(value) <= MAX_ROWS:
        raise ValueError("a bounded nonempty copied host-token tuple/list is required")
    return tuple(_integer(token, 0, TOKEN_COUNT - 1, "token") for token in value)


@dataclass(frozen=True)
class EarlyTokenPlan:
    generation: bytes
    sequence: int
    path: str
    start_position: int
    input_tokens: tuple
    next_token: int

    def __post_init__(self):
        _generation(self.generation)
        _integer(self.sequence, 0, (1 << 63) - 1, "sequence")
        _integer(self.start_position, 0, MAX_POSITION, "start position")
        if type(self.input_tokens) is not tuple:
            raise ValueError("the retained token snapshot must be immutable")
        _tokens(self.input_tokens)
        if self.start_position + len(self.input_tokens) > MAX_POSITION:
            raise ValueError("position plus count exceeds the native int32 contract")
        if self.path not in ("automatic", "verification"):
            raise ValueError("only automatic-target or verification schedules are supported")
        _integer(self.next_token, -1, TOKEN_COUNT - 1, "known next token or -1")
        if self.path == "verification" and self.next_token != -1:
            raise ValueError("verification correction remains unknown until target completion")

    @property
    def known_shifted_tokens(self):
        """All possible matched draft rows; append the known chunk-next row."""
        prefix = self.input_tokens[1:]
        return prefix + (self.next_token,) if self.next_token >= 0 else prefix

    @property
    def producer_tokens(self):
        """Stable deduplicated token requests; the projection is token-dependent."""
        return tuple(dict.fromkeys(self.known_shifted_tokens))

    @property
    def sampled_tail_unknown(self):
        return self.next_token < 0


def plan_automatic(*, generation, sequence, input_tokens, start_position, next_token=-1):
    """Snapshot Target entry RSI/EDX, pre-call position, and known ECX.

    At RVA0x17de1a9..0x17de1c7 the native head receives input_tokens[1:]
    followed by ECX's saved next token, or a target prediction when ECX is
    negative. The caller must separately check all automatic-replay gates.
    All negative native ECX values mean unknown, represented here as -1.
    """
    _integer(next_token, -(1 << 31), TOKEN_COUNT - 1, "native ECX")
    return EarlyTokenPlan(_generation(generation), sequence, "automatic", start_position,
                          _tokens(input_tokens), max(-1, next_token))


def plan_verification(*, generation, sequence, input_tokens, start_position):
    """Snapshot [current,draft1,...] before Target verification.

    Verification sets model[0] bit0 and suppresses automatic head replay.
    The later accepted-prefix head has [matched drafts...,correction].
    Preparing known drafts does not predict acceptance or the correction.
    """
    return EarlyTokenPlan(_generation(generation), sequence, "verification", start_position,
                          _tokens(input_tokens), -1)


def reconcile_head(plan, *, generation, sequence, head_tokens, head_position,
                   claimed_ready_tokens=()):
    """Check the actual late head shift and return potential row coverage.

    The host adapter must call this only for the automatic head at return
    RVA0x17de236 or accepted-prefix replay at return RVA0x17dcd54. Other
    bootstrap/wrapper callers cannot consume a plan implicitly. Ready IDs
    must come from its own same-generation publication state; membership
    here proves no device event, payload or numerical property.
    """
    if not isinstance(plan, EarlyTokenPlan):
        raise ValueError("EarlyTokenPlan required")
    if _generation(generation) != plan.generation or sequence != plan.sequence:
        raise ValueError("late head differs from the exact model generation/sequence")
    _integer(sequence, 0, (1 << 63) - 1, "sequence")
    _integer(head_position, 0, MAX_POSITION, "head position")
    actual = _tokens(head_tokens)
    if head_position != plan.start_position:
        raise ValueError("late head position differs from the target base")
    if plan.path == "automatic":
        if len(actual) != len(plan.input_tokens):
            raise ValueError("automatic replay count differs from target count")
        if actual[:-1] != plan.input_tokens[1:]:
            raise ValueError("automatic replay's shifted prefix differs")
        if plan.next_token >= 0 and actual[-1] != plan.next_token:
            raise ValueError("known chunk-next token differs at the late head")
    else:
        if len(actual) > len(plan.input_tokens):
            raise ValueError("accepted-prefix replay exceeds verified target count")
        if actual[:-1] != plan.input_tokens[1:len(actual)]:
            raise ValueError("accepted-prefix replay's matched draft prefix differs")
    if not isinstance(claimed_ready_tokens, (tuple, list)) or len(claimed_ready_tokens) > MAX_ROWS:
        raise ValueError("bounded claimed-ready token IDs required")
    ready = frozenset(_integer(token, 0, TOKEN_COUNT - 1, "claimed ready token")
                      for token in claimed_ready_tokens)
    # Only this early plan's requested IDs count. An unrelated preexisting
    # cache hit belongs to a separate mechanism and cannot be credited here.
    planned_ready = ready.intersection(plan.producer_tokens)
    covered = tuple(i for i, token in enumerate(actual) if token in planned_ready)
    fallback = tuple(i for i, token in enumerate(actual) if token not in planned_ready)
    return dict(path=plan.path, sequence=plan.sequence, head_position=head_position,
                count=len(actual), tokens=actual, requested_tokens=plan.producer_tokens,
                sampled_tail_unknown_at_entry=plan.sampled_tail_unknown,
                claimed_ready_row_indices=covered, uncovered_row_indices=fallback,
                all_rows_claimed_ready=not fallback,
                existing_M1_cache_shape=len(actual) == 1,
                batch_FC_skip_requires_separate_qualification=len(actual) > 1,
                native_FC_skip_admitted=False, live_upload_proved=False,
                arithmetic_qualified=False, npu_executed=False, speed_claim=False)
