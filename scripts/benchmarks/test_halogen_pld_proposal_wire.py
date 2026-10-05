"""Three finite synthetic CPU tests; no runtime/model/engine imports."""
from dataclasses import replace
import hashlib
import hmac
import struct
import unittest

import halogen_pld_proposal_wire as wire


KEY_ID, KEY = b"K" * 16, b"S" * 32
MODEL, TOKENIZER = b"M" * 32, b"T" * 32


class ProposalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.binding = wire.ProposalBinding(
            model_binding=MODEL, tokenizer_binding=TOKENIZER,
            request_nonce=b"N" * 16, round_id=b"R" * 16,
            committed_prefix_fingerprint=hashlib.sha256(b"committed CPU fixture").digest(),
            committed_prefix_length=20, target_position=19,
            current_token=7, window_origin=0,
        )
        self.stock = (101, 102, 103, 104)
        self.current = wire.SelectionContext(self.binding, self.stock, 3)

    def selector(self, *, enabled=True):
        return wire.ProposalSelector(
            trusted_model_binding=MODEL, trusted_tokenizer_binding=TOKENIZER,
            trusted_keys={KEY_ID: KEY}, token_id_limit=1000,
            token_is_defined=lambda token: token < 900,
            enabled=enabled, max_rounds=1,
        )

    def packet(self, ids=(11, 12, 13), binding=None, key_id=KEY_ID):
        return wire.encode_proposal(binding or self.binding, ids,
                                    key_id=key_id, integrity_key=KEY)

    def test_fresh_candidate_is_selected_once_without_changing_stock(self):
        # Missing one-shot consumption would select this replay a second time.
        selector = self.selector()
        packet = self.packet()
        result = selector.select(packet, current=self.current,
                                 context_is_current=lambda context: context == self.current)
        self.assertTrue(result.used_proposal)
        self.assertEqual(result.ids, (11, 12, 13))
        self.assertEqual(self.stock, (101, 102, 103, 104))
        replay = selector.select(packet, current=self.current,
                                 context_is_current=lambda _: True)
        self.assertFalse(replay.used_proposal)
        self.assertIs(replay.ids, self.stock)
        later = replace(self.binding, round_id=b"2" * 16)
        exhausted = selector.select(self.packet(binding=later),
                                    current=replace(self.current, binding=later),
                                    context_is_current=lambda _: True)
        self.assertIs(exhausted.ids, self.stock)

    def test_stale_or_tampered_bindings_preserve_stock_and_valid_round(self):
        # An invalid reply must not poison the still-valid one-shot round.
        selector = self.selector()
        packet = self.packet()
        tampered = bytearray(packet)
        tampered[192] ^= 1  # Authenticated token body, not a Python object mutation.
        rejected = (
            bytes(tampered),
            self.packet(binding=replace(self.binding, request_nonce=b"X" * 16)),
            self.packet(binding=replace(self.binding, tokenizer_binding=b"X" * 32)),
            self.packet(key_id=b"?" * 16),
        )
        for reply in rejected:
            with self.subTest(reply=reply[:32].hex()):
                result = selector.select(reply, current=self.current,
                                         context_is_current=lambda _: True)
                self.assertFalse(result.used_proposal)
                self.assertIs(result.ids, self.stock)
        stale = selector.select(packet, current=self.current,
                                context_is_current=lambda _: False)
        self.assertIs(stale.ids, self.stock)
        self.assertTrue(selector.select(packet, current=self.current,
                                        context_is_current=lambda _: True).used_proposal)

    def test_bounds_and_constraints_fall_back_without_expanding_native_count(self):
        # Ignoring any native/stock/three-ID cap or constraints would replace stock.
        selector = self.selector()
        bounded = replace(self.current, native_allowance=2)
        packet = self.packet()
        count_four = bytearray(packet[:-32])
        struct.pack_into("<I", count_four, 12, 4)
        count_four.extend(struct.pack("<i", 14))
        count_four = bytes(count_four) + hmac.new(KEY, count_four, hashlib.sha256).digest()
        cases = (
            (packet, bounded),
            (self.packet((11, 1000)), bounded),
            (self.packet((11, 999)), bounded),  # Within head range, absent from tokenizer.
            (count_four, self.current),
            (packet + b"extra", self.current),
            (packet, replace(self.current, constraints_present=True)),
            (packet, replace(self.current, native_allowance=0)),
            (packet, replace(self.current, stock_ids=())),
        )
        for reply, current in cases:
            with self.subTest(count=len(current.stock_ids), allowance=current.native_allowance):
                result = selector.select(reply, current=current,
                                         context_is_current=lambda _: True)
                self.assertFalse(result.used_proposal)
                self.assertIs(result.ids, current.stock_ids)
        disabled = wire.ProposalSelector(
            trusted_model_binding=MODEL, trusted_tokenizer_binding=TOKENIZER,
            trusted_keys={KEY_ID: KEY}, token_id_limit=1000,
        )
        self.assertIs(disabled.select(packet, current=self.current,
                                      context_is_current=lambda _: True).ids, self.stock)
        stock_bounded = replace(bounded, stock_ids=(101,))
        self.assertIs(selector.select(self.packet((11, 12)), current=stock_bounded,
                                      context_is_current=lambda _: True).ids, stock_bounded.stock_ids)
        used = selector.select(self.packet((11, 12)), current=bounded,
                               context_is_current=lambda _: True)
        self.assertTrue(used.used_proposal)
        self.assertEqual(used.ids, (11, 12))
        self.assertLessEqual(len(used.ids), len(bounded.stock_ids))


if __name__ == "__main__":
    unittest.main()
