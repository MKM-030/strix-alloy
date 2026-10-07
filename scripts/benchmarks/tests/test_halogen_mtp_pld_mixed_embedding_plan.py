"""Offline split/identity tests; no native hooks, tensors, or device calls."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import halogen_mtp_pld_mixed_embedding_plan as mixed
except ModuleNotFoundError as error:
    if error.name != "halogen_mtp_pld_mixed_embedding_plan":
        raise
    mixed = None


def identity(**changes):
    values = dict(request_nonce=b"r" * 16, model_generation=b"m" * 16,
                  source_epoch=b"e" * 32, round_id=7)
    values.update(changes)
    return mixed.RoundIdentity(**values)


def producer(tokens=(10, 21, 22, 23), **changes):
    values = dict(identity=identity(), input_tokens=tokens, base_position=100,
                  native_proposal_allowance=3, verifier_caller_rva=0x172D61D)
    values.update(changes)
    return mixed.plan_pld_round(**values)


def publication(plan, **changes):
    values = dict(identity=plan.identity, proposal_tokens=plan.proposal_tokens,
                  device_event_complete=True, exclusive_slab_lease=True,
                  producer_writes_closed=True, slab_rows=4)
    values.update(changes)
    return mixed.ClaimedPublication(**values)


def replay(plan, head_tokens=(21, 22, 90), **changes):
    values = dict(identity=plan.identity, head_tokens=head_tokens, head_position=100,
                  head_caller_rva=0x17DCD54, wire="D",
                  publication=publication(plan), enable_offline_split=True)
    values.update(changes)
    return mixed.plan_mixed_replay(plan, **values)


class MixedEmbeddingPlanTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(mixed, "the offline mixed-row planner is not implemented")

    # A removed default-off guard would incorrectly schedule native work removal.
    def test_default_off_preserves_complete_native_branch(self):
        plan = producer()
        result = mixed.plan_mixed_replay(
            plan, identity=plan.identity, head_tokens=(21, 22, 90),
            head_position=100, head_caller_rva=0x17DCD54, wire="D",
            publication=publication(plan))
        self.assertEqual(result.mode, "native")
        self.assertEqual(result.native_embedding_count, 3)
        self.assertEqual(result.native_fc_m, 3)
        self.assertEqual(result.removed_embedding_rows, 0)
        self.assertEqual(result.hidden_fc_m, 12)
        self.assertEqual(result.seed_count, 3)
        self.assertEqual(result.seed_embedding_source, "native_model_b00")
        self.assertFalse(result.seed_arg0_rewrite)

    # Incorrect prefix length, byte stride, or head-count reduction corrupts replay.
    def test_every_bounded_acceptance_split_keeps_full_hidden_seed_count(self):
        plan = producer()
        cases = [((21, 90), 1, 2, 4, 5120, 8),
                 ((21, 22, 90), 2, 3, 8, 10240, 12),
                 ((21, 22, 23, 90), 3, 4, 12, 15360, 16)]
        for tokens, prefix, count, token_offset, row_offset, hidden_m in cases:
            with self.subTest(tokens=tokens):
                result = replay(plan, tokens)
                self.assertEqual(result.mode, "mixed")
                self.assertEqual(result.prepared_prefix_tokens, tokens[:-1])
                self.assertEqual(result.native_embedding_tokens, (90,))
                self.assertEqual(result.removed_embedding_rows, prefix)
                self.assertEqual(result.native_token_offset_bytes, token_offset)
                self.assertEqual(result.native_input_offset_bytes, row_offset)
                self.assertEqual(result.native_fc_output_offset_bytes, row_offset)
                self.assertEqual(result.native_embedding_count, 1)
                self.assertEqual(result.native_fc_m, 1)
                self.assertEqual(result.head_count, count)
                self.assertEqual(result.hidden_fc_m, hidden_m)
                self.assertEqual(result.seed_count, count)
                self.assertEqual(result.layer48_count, count)
                self.assertEqual(result.seed_embedding_source, "private_round_slab")
                self.assertTrue(result.seed_arg0_rewrite)
                self.assertFalse(result.rebind_model_b00)
                self.assertFalse(result.native_skip_admitted)
                self.assertFalse(result.device_execution_proved)
                self.assertFalse(result.speed_claim)

    # Treating k=1 as a ready prefix would consume an unknown correction.
    def test_first_mismatch_has_no_prepared_prefix(self):
        result = replay(producer(), (90,))
        self.assertEqual(result.mode, "native")
        self.assertEqual(result.removed_embedding_rows, 0)
        self.assertEqual(result.native_embedding_tokens, (90,))
        self.assertEqual(result.hidden_fc_m, 4)
        self.assertEqual(result.seed_count, 1)

    # Deduplication or retaining mutable caller storage changes slab row order.
    def test_proposal_snapshot_preserves_duplicates_and_correction_stays_native(self):
        tokens = [10, 21, 21, 23]
        plan = producer(tokens)
        tokens[1] = 99
        self.assertEqual(plan.proposal_tokens, (21, 21, 23))
        result = replay(plan, (21, 21, 21))
        self.assertEqual(result.prepared_prefix_tokens, (21, 21))
        self.assertEqual(result.native_embedding_tokens, (21,))
        self.assertEqual(result.native_fc_m, 1)
        self.assertEqual(result.native_fc_output_offset_bytes, 10240)

    # Ignoring any lifetime/round/prefix seam can attach another round's slab.
    def test_stale_round_or_wrong_replay_metadata_falls_back_before_removal(self):
        plan = producer()
        changes = [dict(identity=identity(request_nonce=b"s" * 16)),
                   dict(identity=identity(model_generation=b"n" * 16)),
                   dict(identity=identity(source_epoch=b"f" * 32)),
                   dict(identity=identity(round_id=8)),
                   dict(head_position=101), dict(head_caller_rva=0x17DCF49),
                   dict(wire="A"), dict(head_tokens=(21, 99, 90)),
                   dict(head_tokens=(21, 22, 23, 24, 90))]
        for change in changes:
            with self.subTest(change=change):
                if len(change.get("head_tokens", ())) > 4:
                    with self.assertRaises(ValueError):
                        replay(plan, **change)
                    continue
                result = replay(plan, **change)
                self.assertEqual(result.mode, "native")
                self.assertEqual(result.removed_embedding_rows, 0)
                self.assertEqual(result.native_fc_m, 3)
                self.assertEqual(result.hidden_fc_m, 12)
                self.assertEqual(result.seed_count, 3)
                self.assertFalse(result.seed_arg0_rewrite)

    # Trusting a pending, writable, unordered, or wrong-epoch publication is unsafe.
    def test_unusable_publication_preserves_whole_native_branch(self):
        plan = producer()
        claims = [None, publication(plan, device_event_complete=False),
                  publication(plan, exclusive_slab_lease=False),
                  publication(plan, producer_writes_closed=False),
                  publication(plan, proposal_tokens=(22, 21, 23)),
                  publication(plan, identity=identity(round_id=8)),
                  publication(plan, slab_rows=3)]
        for claim in claims:
            with self.subTest(claim=claim):
                result = replay(plan, publication=claim)
                self.assertEqual(result.mode, "native")
                self.assertEqual(result.native_embedding_count, 3)
                self.assertEqual(result.native_fc_m, 3)
                self.assertEqual(result.removed_embedding_rows, 0)

    # An out-of-reservation producer snapshot could grow native verification work.
    def test_producer_rejects_invalid_bounds_and_non_pld_caller(self):
        cases = [dict(tokens=(10,)), dict(tokens=(10, 21, 22, 23, 24)),
                 dict(tokens=(10, -1)), dict(tokens=(10, 248320)),
                 dict(tokens=(10, True)), dict(native_proposal_allowance=2),
                 dict(native_proposal_allowance=True), dict(base_position=0),
                 dict(base_position=(1 << 31) - 2),
                 dict(verifier_caller_rva=0x173B6FB)]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                producer(**changes)

    # bool IDs, zero epochs, and mutable identity blobs must not bind a round.
    def test_identity_rejects_malformed_lifetime_metadata(self):
        for changes in [dict(request_nonce=b"\0" * 16),
                        dict(model_generation=bytearray(b"m" * 16)),
                        dict(source_epoch=b"e" * 31), dict(round_id=True),
                        dict(round_id=0)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                identity(**changes)
        with self.assertRaises(ValueError):
            replay(producer(), enable_offline_split=1)
        with self.assertRaises(ValueError):
            publication(producer(), device_event_complete=1)

    # A valid-looking forged plan must not bypass the producer's bound checks.
    def test_immutable_plan_revalidates_replaced_fields(self):
        plan = producer()
        for changes in [dict(proposal_tokens=(21, 22, 23, 24)),
                        dict(proposal_tokens=[21, 22, 23]),
                        dict(native_proposal_allowance=2)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(plan, **changes)


if __name__ == "__main__":
    unittest.main()
