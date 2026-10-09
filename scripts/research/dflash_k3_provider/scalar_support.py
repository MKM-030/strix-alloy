"""Native-round adapter draft; does not alter the sealed comparison path.

The root must map the exact shared Lane.round and source-stamped DecodeView.
Calls are serialized by the external worker dispatcher; no native transport or
callback is implemented here. Scalar never fabricates a four-input verifier.
"""
from dataclasses import replace
from time import perf_counter_ns

from abi import MASK_ID
from provider import reference_modules


class NativeRoundAdapter:
    def __init__(self, worker):
        self.worker = worker
        self.last_completed_native_round = -1
        self.pending_native_round = None
        self.pending_native_ready = None

    def _round(self, stamp, native_round, position):
        self.worker._owner(stamp)
        if type(native_round) is not int or native_round <= self.last_completed_native_round:
            raise ValueError("Stale native mandatory-Entry round")
        if type(position) is not int or position != len(self.worker.ids):
            raise ValueError("Actual native processed position differs from committed provider prefix")

    def propose(self, *, stamp, native_round, position, current_id, anchor_embedding=None):
        self._round(stamp, native_round, position)
        if self.pending_native_round is not None:
            raise ValueError("Complete actual verifier/scalar outcome before another native Entry")
        # Native Entry IDs and the numerical provider's private Frontier counter
        # are separate. No missed native round is inferred or synthesized.
        internal = self.worker.frontier.round_index
        ready = self.worker.propose(stamp=stamp, round_index=internal,
                                    current_id=current_id, anchor_embedding=anchor_embedding)
        self.pending_native_round = native_round
        self.pending_native_ready = replace(ready, round_index=native_round)
        return self.pending_native_ready

    def apply_verify_commit(self, *, stamp, native_round, position, retained_features,
                            retained_ids, verified_rows, committed_rows,
                            authoritative_next_current, terminal=False):
        self._round(stamp, native_round, position)
        if terminal:
            self.worker.retire()
            self.pending_native_round = self.pending_native_ready = None
            return None
        ready = self.pending_native_ready
        if (ready is None or native_round != self.pending_native_round
                or verified_rows != 4 or type(committed_rows) is not int or not 1 <= committed_rows <= 4):
            raise ValueError("Verify DecodeView must bind this exact offered K3 round and native commit count")
        actual_offered_inputs = (ready.current_id,) + ready.raw_ids
        if tuple(retained_ids) != actual_offered_inputs[:committed_rows]:
            raise ValueError("Copied committed target IDs differ from this offered verifier prefix")
        if tuple(retained_features.shape) != (committed_rows, 12800):
            raise ValueError("Transport only actual committed target rows")
        # The four IDs here are the saved actual offer, not fabricated verifier
        # input rows. The source-stamped Verify view attests verified_rows=4.
        internal = self.worker.pending.round_index
        plan = self.worker.apply_verification(stamp=stamp, round_index=internal,
            verifier_features=retained_features, verifier_ids=actual_offered_inputs,
            verifier_positions=tuple(range(position, position + 4)),
            accepted_prefix=committed_rows - 1, authoritative_bonus_id=authoritative_next_current)
        self.last_completed_native_round = native_round
        self.pending_native_round = self.pending_native_ready = None
        return plan

    def _rebase_frontier(self, next_current):
        contract, _, _ = reference_modules()
        old = self.worker.frontier
        old.retire()  # Obsolete query tickets can no longer finish a commit.
        fresh = contract.Frontier(old.request_nonce, old.epoch)
        fresh.initialize(self.worker.positions)
        fresh.expected_anchor_id = next_current
        self.worker.frontier = fresh
        self.worker.pending = None
        self.worker.last_hidden = self.worker.last_logits = None

    def apply_scalar(self, *, stamp, native_round, position, current_id,
                     current_features, authoritative_next_current, terminal=False):
        self._round(stamp, native_round, position)
        if terminal:
            self.worker.retire()
            self.pending_native_round = self.pending_native_ready = None
            return None
        if (type(current_id) is not int or not 0 <= current_id < MASK_ID
                or type(authoritative_next_current) is not int or not 0 <= authoritative_next_current < MASK_ID):
            raise ValueError("Scalar source must supply actual current and unprocessed next-current IDs")
        if tuple(current_features.shape) != (1, 12800):
            raise ValueError("Scalar supplies exactly one actual processed target row")
        expected = self.worker.frontier.expected_anchor_id
        if expected is not None and current_id != expected:
            raise ValueError("Scalar current differs from the last authoritative next-current")
        if self.pending_native_ready is not None:
            if (native_round < self.pending_native_round
                    or current_id != self.pending_native_ready.current_id
                    or position != self.pending_native_ready.position):
                raise ValueError("Scalar cannot cancel a query for another native frontier")
        if position + 1 > self.worker.capacity:
            self.worker.retire()
            raise ValueError("Scalar context growth exceeds bounded provider capacity")
        try:
            started = perf_counter_ns()
            # Cancel prior numerical query before any scalar context projection.
            self._rebase_frontier(current_id)
            self.pending_native_round = self.pending_native_ready = None
            with self.worker.torch.inference_mode():
                append = self.worker._project(current_features, (position,))
                self.worker.cache[:, :, :, position:position + 1, :].copy_(append)
            self.worker.ids += (current_id,)
            self.worker.positions += (position,)
            self._rebase_frontier(authoritative_next_current)
            self.worker.last_context_update_ns = perf_counter_ns() - started
            self.last_completed_native_round = native_round
            return {"native_round": native_round, "processed_input_count": 1,
                    "next_position": position + 1, "next_current": authoritative_next_current}
        except Exception:
            self.worker.retire()
            raise
