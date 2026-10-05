"""Default-off, synchronous raw-ID proposer transactions; no native policy.

The injected engine alone implements clear_context(), prefill(tuple[int, ...])
and forward(int), returning indexable raw logits. No engine/runtime is imported.
An optional append path retains only consumed drafts proven authoritative, with
clear/rebuild for rejection or window shifts. There is no checkpoint rollback.
The caller supplies truthful native bindings and verifies outcomes independently.
Local serialization is not proof
of native cancellation/reset ownership, acceptance, or performance.
"""
from dataclasses import dataclass, field, replace
import math
from threading import Lock
from typing import Protocol, Sequence

try:
    from .halogen_pld_proposal_wire import (
        ProposalBinding, encode_proposal, MAX_IDS, MAX_WINDOW_TOKENS,
        MAX_SUCCESSFUL_ROUNDS, INT32_MAX,
    )
except ImportError:
    from halogen_pld_proposal_wire import (
        ProposalBinding, encode_proposal, MAX_IDS, MAX_WINDOW_TOKENS,
        MAX_SUCCESSFUL_ROUNDS, INT32_MAX,
    )


SHARED_ID_COUNT = 248070
MAX_HEAD_ROWS = 248320


class RawIdEngine(Protocol):
    def clear_context(self) -> None: ...
    def prefill(self, ids: tuple[int, ...]) -> Sequence[float]: ...
    def forward(self, token: int) -> Sequence[float]: ...


@dataclass(frozen=True)
class CommittedState:
    binding: ProposalBinding
    ids: tuple
    logits: tuple = field(repr=False)


@dataclass(frozen=True)
class PendingProposal:
    binding: ProposalBinding
    ids: tuple
    packet: bytes
    logits: tuple = field(repr=False)


@dataclass(frozen=True)
class AuthoritativeOutcome:
    """Caller-reported accepted draft prefix and optional correction/bonus.

    Constructing this object does not establish target authority. apply() also
    requires the independent outcome_is_authoritative(outcome, next_binding)
    callback to return exactly True. None permits an EOS/empty-output outcome.
    """
    binding: ProposalBinding
    accepted_ids: tuple
    correction_or_bonus: int | None

    def __post_init__(self):
        if type(self.binding) is not ProposalBinding:
            raise ValueError("immutable proposal binding required")
        if type(self.accepted_ids) is not tuple or len(self.accepted_ids) > MAX_IDS:
            raise ValueError("accepted IDs require a bounded immutable tuple")
        for token in self.accepted_ids:
            _token(token, INT32_MAX + 1)
        if self.correction_or_bonus is not None:
            _token(self.correction_or_bonus, INT32_MAX + 1)


def _token(token, limit=SHARED_ID_COUNT):
    if type(token) is not int or not 0 <= token < limit:
        raise ValueError("unsupported raw token ID")


def _owned_logits(raw):
    if not SHARED_ID_COUNT <= len(raw) <= MAX_HEAD_ROWS:
        raise ValueError("raw logits do not cover the bounded shared vocabulary")
    # Own only supported rows. Undefined/additional head rows cannot be sampled.
    values = tuple(float(raw[index]) for index in range(SHARED_ID_COUNT))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite raw logits")
    return values


class TransactionCoordinator:
    """One pending round, <=512 committed IDs, <=3 independent greedy drafts.

    Native hit/count/constraint/opening-head/stop policy belongs to the caller
    and the existing selector. It must choose max_drafts within native limits.
    Callbacks must not re-enter this coordinator. Fresh caller-supplied request
    nonces are mandatory; at most 64 requests and 64 rounds/request are retained
    per coordinator. A new coordinator is needed after that finite budget.
    Prefix fingerprints, IDs before the retained window, and initial native
    target-position semantics are caller truth; subsequent positions, window
    origins, and current IDs are checked here. Engines need capacity for 512
    committed IDs plus two speculative forward inputs; authoritative results
    contain up to four IDs, then rebase to 512 before clear/prefill.
    Start below the 512-token cap to permit growth before a window rebase.
    Python logits copies/argmax are reference behavior, not a speed claim.
    """
    def __init__(self, engine: RawIdEngine, *, model_binding, tokenizer_binding,
                 key_id, integrity_key, enabled=False,
                 append_when_authoritative=False):
        if type(enabled) is not bool or type(append_when_authoritative) is not bool:
            raise ValueError("enabled/append flags must be explicit bool")
        for value, size in ((model_binding, 32), (tokenizer_binding, 32),
                            (key_id, 16), (integrity_key, 32)):
            if type(value) is not bytes or len(value) != size or not any(value):
                raise ValueError("exact nonzero immutable binding/key bytes required")
        if any(not callable(getattr(engine, name, None))
               for name in ("clear_context", "prefill", "forward")):
            raise ValueError("raw-ID engine interface required")
        self._engine, self._enabled = engine, enabled
        self._append_when_authoritative = append_when_authoritative
        self._model, self._tokenizer = model_binding, tokenizer_binding
        self._key_id, self._key = key_id, integrity_key
        self._state = self._pending = None
        self._nonces, self._rounds = set(), set()
        self._lock = Lock()

    @property
    def state(self):
        with self._lock:
            return self._state  # Frozen IDs and owned immutable logits.

    def _binding(self, binding):
        if (type(binding) is not ProposalBinding or
                binding.model_binding != self._model or
                binding.tokenizer_binding != self._tokenizer):
            raise ValueError("untrusted proposal binding")

    def _window(self, binding, ids):
        self._binding(binding)
        if (type(ids) is not tuple or not 1 <= len(ids) <= MAX_WINDOW_TOKENS or
                len(ids) != binding.committed_prefix_length - binding.window_origin or
                ids[-1] != binding.current_token):
            raise ValueError("committed window differs from its binding/current ID")
        for token in ids:
            _token(token)

    def _retire(self):
        self._state = self._pending = None

    def _rebuild(self, binding, ids):
        self._retire()
        try:
            self._engine.clear_context()
            logits = _owned_logits(self._engine.prefill(ids))
        except Exception:
            self._retire()
            raise
        self._state = CommittedState(binding, ids, logits)

    def reset(self, binding, committed_ids):
        """Retire the old round and initialize a supported window with a new nonce."""
        with self._lock:
            if not self._enabled:
                return False
            # A failed request initialization must never leave an old feed live.
            self._retire()
            self._binding(binding)
            if (binding.request_nonce in self._nonces or
                    len(self._nonces) >= MAX_SUCCESSFUL_ROUNDS):
                raise ValueError("fresh request nonce / finite request budget required")
            self._nonces.add(binding.request_nonce)
            self._rounds.clear()
            self._window(binding, committed_ids)
            self._rebuild(binding, committed_ids)
            return True

    def invalidate(self):
        """Retire a cancelled/replaced request; never restore a stale engine snapshot."""
        with self._lock:
            self._retire()

    def propose(self, binding, *, max_drafts=MAX_IDS):
        """Predict from private committed logits, then authenticate a wire packet."""
        with self._lock:
            if not self._enabled or self._state is None:
                return None
            self._binding(binding)
            if (self._pending is not None or
                    replace(binding, round_id=self._state.binding.round_id) != self._state.binding):
                raise ValueError("pending round or stale committed binding")
            if type(max_drafts) is not int or not 1 <= max_drafts <= MAX_IDS:
                raise ValueError("one to three draft IDs required")
            if binding.round_id in self._rounds or len(self._rounds) >= MAX_SUCCESSFUL_ROUNDS:
                raise ValueError("round replay / finite round budget exhausted")
            self._rounds.add(binding.round_id)
            ids, logits = [], self._state.logits
            try:
                for index in range(max_drafts):
                    # Stable lowest-ID tie break. No target logits enter this path.
                    token = max(range(SHARED_ID_COUNT), key=logits.__getitem__)
                    ids.append(token)
                    if index + 1 < max_drafts:
                        logits = _owned_logits(self._engine.forward(token))
                ids = tuple(ids)
                packet = encode_proposal(binding, ids, key_id=self._key_id,
                                         integrity_key=self._key)
            except Exception:
                self._retire()
                raise
            # The final predicted ID has not been consumed by the engine.
            self._pending = PendingProposal(binding, ids, packet, logits)
            return self._pending

    def apply(self, outcome, next_binding, *, outcome_is_authoritative=None):
        """Synchronize accepted prefix plus correction/bonus; discard rejected state.

        The authority callback must validate both outcome and next fingerprint
        against the caller's actual committed target state. False/unavailable
        authority leaves the pending round intact. Unsupported authoritative IDs
        retire this feed, leaving native target output/policy to its caller.
        """
        with self._lock:
            if not self._enabled or self._state is None:
                return False
            if (type(outcome) is not AuthoritativeOutcome or self._pending is None or
                    outcome.binding != self._pending.binding):
                raise ValueError("no matching pending authoritative outcome")
            self._binding(next_binding)
            accepted = outcome.accepted_ids
            if accepted != self._pending.ids[:len(accepted)]:
                raise ValueError("accepted IDs differ from the proposed prefix")
            if not callable(outcome_is_authoritative):
                return False
            try:
                if outcome_is_authoritative(outcome, next_binding) is not True:
                    return False
            except Exception:
                return False
            outputs = accepted + (() if outcome.correction_or_bonus is None
                                  else (outcome.correction_or_bonus,))
            if any(token >= SHARED_ID_COUNT for token in outputs):
                self._retire()
                return False
            previous = self._state.binding
            ids = (self._state.ids + outputs)[-MAX_WINDOW_TOKENS:]
            length = previous.committed_prefix_length + len(outputs)
            if (next_binding.request_nonce != previous.request_nonce or
                    next_binding.round_id in self._rounds or
                    next_binding.committed_prefix_length != length or
                    next_binding.window_origin != length - len(ids) or
                    next_binding.target_position != previous.target_position + len(outputs) or
                    next_binding.current_token != ids[-1] or
                    (not outputs and next_binding.committed_prefix_fingerprint !=
                     previous.committed_prefix_fingerprint)):
                raise ValueError("next binding differs from authoritative advancement")
            self._window(next_binding, ids)
            consumed = len(self._pending.ids) - 1
            if (self._append_when_authoritative and len(accepted) >= consumed and
                    next_binding.window_origin == previous.window_origin):
                # Every already-consumed draft is now authoritative. Only feed
                # new output beyond that prefix; no rollback/snapshot is used.
                logits = self._pending.logits
                self._retire()
                try:
                    for token in outputs[consumed:]:
                        logits = _owned_logits(self._engine.forward(token))
                except Exception:
                    self._retire()
                    raise
                self._state = CommittedState(next_binding, ids, logits)
            else:
                self._rebuild(next_binding, ids)
            return True
