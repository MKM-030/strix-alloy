"""Three CPU coordinator transactions with a deterministic fixture engine."""
import hashlib
import unittest

import halogen_pld_proposal_wire as wire
import halogen_pld_transaction as transaction


MODEL, TOKENIZER = b"M" * 32, b"T" * 32
KEY_ID, KEY = b"K" * 16, b"S" * 32


class FixtureEngine:
    """Reusable logits and prefix-dependent predictions; no model runtime."""
    def __init__(self):
        self.ids = []
        self.logits = [0.0] * 248320
        self.rebuilds = 0

    def clear_context(self):
        self.ids.clear()

    def _output(self):
        self.logits[:] = [0.0] * len(self.logits)
        self.logits[sum(self.ids) % 20 + 10] = 2.0
        self.logits[248319] = 100.0  # Undefined head rows must never win.
        return self.logits

    def prefill(self, ids):
        self.ids.extend(ids)
        self.rebuilds += 1
        return self._output()

    def forward(self, token):
        self.ids.append(token)
        return self._output()


def binding(ids, nonce=b"N" * 16, round_id=b"R" * 16, origin=0):
    return wire.ProposalBinding(
        MODEL, TOKENIZER, nonce, round_id,
        hashlib.sha256(repr(ids).encode()).digest(),
        origin + len(ids), origin + len(ids) - 1, ids[-1], origin,
    )


class TransactionTests(unittest.TestCase):
    def coordinator(self, engine, **kwargs):
        return transaction.TransactionCoordinator(
            engine, model_binding=MODEL, tokenizer_binding=TOKENIZER,
            key_id=KEY_ID, integrity_key=KEY, **kwargs,
        )

    def test_zero_partial_all_rebuild_only_authoritative_ids(self):
        # Retaining rejected drafts or shallow logits changes the next prediction.
        cases = (((), 9, (1, 2, 3, 9), 25),
                 ((16,), 7, (1, 2, 3, 16, 7), 19),
                 ((16, 12, 24), 6, (1, 2, 3, 16, 12, 24, 6), 14))
        for accepted, correction, expected, next_id in cases:
            with self.subTest(accepted=accepted):
                engine = FixtureEngine()
                coordinator = self.coordinator(engine, enabled=True)
                initial = binding((1, 2, 3))
                self.assertTrue(coordinator.reset(initial, (1, 2, 3)))
                saved_logits = coordinator.state.logits
                proposal = coordinator.propose(initial, max_drafts=3)
                self.assertEqual(proposal.ids, (16, 12, 24))
                self.assertEqual(saved_logits[16], 2.0)
                decoded = wire.decode_proposal(proposal.packet,
                    trusted_keys={KEY_ID: KEY}, token_id_limit=248070)
                self.assertEqual(decoded.binding, initial)
                self.assertEqual(decoded.ids, (16, 12, 24))
                outcome = transaction.AuthoritativeOutcome(initial, accepted, correction)
                following = binding(expected, round_id=b"2" * 16)
                self.assertFalse(coordinator.apply(outcome, following,
                    outcome_is_authoritative=lambda *_: False))
                self.assertTrue(coordinator.apply(outcome, following,
                    outcome_is_authoritative=lambda *_: True))
                self.assertEqual(coordinator.state.ids, expected)
                self.assertEqual(tuple(engine.ids), expected)
                self.assertEqual(engine.rebuilds, 2)
                self.assertEqual(coordinator.propose(following, max_drafts=1).ids,
                                 (next_id,))

    def test_reset_retires_pending_round_and_rebase_keeps_512_window(self):
        # Accepting an old nonce or retaining 513 tokens corrupts fresh state.
        engine = FixtureEngine()
        coordinator = self.coordinator(engine, enabled=True)
        old = binding((1, 2, 3))
        coordinator.reset(old, (1, 2, 3))
        coordinator.propose(old)
        window = (1,) * 512
        fresh = binding(window, nonce=b"F" * 16)
        coordinator.reset(fresh, window)
        with self.assertRaises(ValueError):
            coordinator.apply(transaction.AuthoritativeOutcome(old, (), 9),
                binding((1, 2, 3, 9)), outcome_is_authoritative=lambda *_: True)
        proposal = coordinator.propose(fresh, max_drafts=1)
        self.assertEqual(proposal.ids, (22,))
        rebased = (1,) * 511 + (8,)
        following = binding(rebased, nonce=b"F" * 16, round_id=b"2" * 16, origin=1)
        coordinator.apply(transaction.AuthoritativeOutcome(fresh, (), 8), following,
                          outcome_is_authoritative=lambda *_: True)
        self.assertEqual(coordinator.state.ids, rebased)
        self.assertEqual(coordinator.state.binding.window_origin, 1)
        self.assertEqual(tuple(engine.ids), rebased)
        with self.assertRaises(ValueError):
            coordinator.reset(old, (1, 2, 3))
        self.assertIsNone(coordinator.state)
        self.assertIsNone(coordinator.propose(following))
        valid = binding((1, 2, 3), nonce=b"G" * 16)
        coordinator.reset(valid, (1, 2, 3))
        coordinator.propose(valid)
        unsupported = binding((1, 2, 248070), nonce=b"U" * 16)
        with self.assertRaises(ValueError):
            coordinator.reset(unsupported, (1, 2, 248070))
        self.assertIsNone(coordinator.state)
        self.assertIsNone(coordinator.propose(valid))

    def test_disabled_and_unsupported_authoritative_token_retire_feed(self):
        # A disabled feed must not touch its engine; unsupported target IDs retire it.
        engine = FixtureEngine()
        disabled = self.coordinator(engine)
        initial = binding((1, 2, 3))
        self.assertFalse(disabled.reset(initial, (1, 2, 3)))
        self.assertIsNone(disabled.propose(initial))
        self.assertEqual(engine.rebuilds, 0)
        coordinator = self.coordinator(engine, enabled=True)
        coordinator.reset(initial, (1, 2, 3))
        coordinator.propose(initial)
        following = binding((1, 2, 3, 248070), round_id=b"2" * 16)
        self.assertFalse(coordinator.apply(
            transaction.AuthoritativeOutcome(initial, (), 248070), following,
            outcome_is_authoritative=lambda *_: True))
        self.assertIsNone(coordinator.state)
        self.assertIsNone(coordinator.propose(following))


if __name__ == "__main__":
    unittest.main()
