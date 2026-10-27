"""Bounded synthetic CPU checks for private committed-row KV retention."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MODULE = Path(__file__).with_name('context_ring.py')


class Passive(unittest.TestCase):
    def test_context_ring_exists_and_import_has_no_torch_side_effect(self):
        self.assertTrue(MODULE.is_file(), 'Committed-input context ring is missing')
        code = 'import sys;from scripts.research.dflash2_gpu import context_ring;assert "torch" not in sys.modules'
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless('--run-cpu' in sys.argv and MODULE.is_file(), 'Explicit CPU fixture only')
class RingCPU(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from scripts.research.dflash2_gpu.context_ring import ContextRing, SequenceKey, InputCommit
        from scripts.research.dflash2_gpu.graph import PrivateContext
        torch.set_num_threads(1)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        torch.set_grad_enabled(False)
        cls.t, cls.ContextRing, cls.SequenceKey = torch, ContextRing, SequenceKey
        cls.InputCommit, cls.PrivateContext = InputCommit, PrivateContext

    def setUp(self):
        self.ring = self.ContextRing.allocate(device='cpu', dtype=self.t.bfloat16)
        self.key = self.SequenceKey(b'a' * 32, b'm' * 32, b't' * 32, 1)

    def prepared(self, start, rows, *, dtype=None):
        t = self.t
        line = t.arange(start, start + rows, device='cpu', dtype=t.int64).remainder(97).to(dtype or t.bfloat16)
        key = line.view(1, rows, 1, 1).expand(5, rows, 8, 128)
        return self.PrivateContext(key, -key, start)

    def seed(self, prompt=8192, *, split=None):
        self.ring.begin(self.key, prompt_tokens=prompt)
        start = max(0, prompt - 2048)
        cuts = (prompt - start,) if split is None else split
        for rows in cuts:
            self.ring.append_prompt(self.prepared(start, rows), sequence=self.key,
                                    input_ids=tuple(value % 248077 for value in range(start, start + rows)))
            start += rows

    def assert_context(self, end, round, *, block=4):
        actual = self.ring.context_for(self.key, round=round, anchor_position=end, block_size=block)
        left = max(0, end + block - 2048)
        self.assertEqual((actual.start_position, actual.rows), (left, end - left))
        expected = self.prepared(left, end - left)
        self.t.testing.assert_close(actual._key, expected._key, rtol=0, atol=0)
        self.t.testing.assert_close(actual._value, expected._value, rtol=0, atol=0)
        self.assertEqual(self.ring.input_ids, tuple(value % 248077 for value in range(max(0, end - 2048), end)))
        return actual

    def test_prompt_chunks_and_mirrored_rollover_keep_exact_chronological_source_window(self):
        self.seed(split=(511, 1537))
        old = self.assert_context(8192, 1)
        # Returned context is a view of persistent ring storage, not a full-tail clone.
        self.assertEqual(old._key.untyped_storage().data_ptr(), self.ring._key.untyped_storage().data_ptr())
        end = 8192
        for round, accepted in enumerate((0, 2, 1, 3), 1):
            captured = tuple(range(end, end + 4))
            committed = captured[:accepted + 1]
            receipt = self.InputCommit(self.key, round, end, captured, accepted, committed)
            self.ring.append_committed(self.prepared(end, 4), receipt)
            end += accepted + 1
            self.assert_context(end, round + 1)
            self.assert_context(end, round + 1, block=8)

    def test_only_authoritative_verified_input_prefix_is_kept_never_bonus_or_rejected_rows(self):
        self.seed(prompt=13)
        source = self.prepared(13, 4)
        captured = (13, 14, 15, 16)
        receipt = self.InputCommit(self.key, 1, 13, captured, 1, (13, 14))
        self.ring.append_committed(source, receipt)
        self.assert_context(15, 2)
        source._key.fill_(88)
        self.assert_context(15, 2)  # input storage was copied, never borrowed

    def test_rejects_gap_duplicate_stale_round_mismatched_ids_and_invalid_acceptance(self):
        self.seed(prompt=13)
        cases = (
            self.InputCommit(self.key, 1, 14, (14, 15, 16, 17), 0, (14,)),
            self.InputCommit(self.key, 2, 13, (13, 14, 15, 16), 0, (13,)),
            self.InputCommit(self.key, 1, 13, (13, 14, 15, 16), 1, (13, 99)),
            self.InputCommit(self.key, 1, 13, (13, 14, 15, 16), 4, (13, 14, 15, 16)),
            self.InputCommit(self.key, 1, 13, (13, 14, 15, 16), True, (13, 14)),
        )
        for receipt in cases:
            with self.assertRaises((TypeError, ValueError)):
                self.ring.append_committed(self.prepared(receipt.start_position, 4), receipt)
            self.assert_context(13, 1)
        valid = self.InputCommit(self.key, 1, 13, (13, 14, 15, 16), 0, (13,))
        self.ring.append_committed(self.prepared(13, 4), valid)
        with self.assertRaises(ValueError):
            self.ring.append_committed(self.prepared(13, 4), valid)
        self.assert_context(14, 2)

    def test_incomplete_prompt_wrong_generation_and_reset_retirement_are_rejected(self):
        self.ring.begin(self.key, prompt_tokens=8192)
        self.ring.append_prompt(self.prepared(6144, 17), sequence=self.key, input_ids=tuple(range(6144, 6161)))
        with self.assertRaises(ValueError):
            self.ring.context_for(self.key, round=1, anchor_position=8192, block_size=4)
        self.ring.retire(self.key)
        with self.assertRaises(ValueError):
            self.ring.context_for(self.key, round=1, anchor_position=6161, block_size=4)
        with self.assertRaises(ValueError):
            self.ring.begin(self.key, prompt_tokens=13)
        next_key = self.SequenceKey(b'b' * 32, b'm' * 32, b't' * 32, 2)
        self.ring.begin(next_key, prompt_tokens=0)
        with self.assertRaises(ValueError):
            self.ring.append_prompt(self.prepared(0, 1), sequence=self.key, input_ids=(0,))
        empty = self.ring.context_for(next_key, round=1, anchor_position=0, block_size=4)
        self.assertEqual((empty.start_position, empty.rows), (0, 0))

    def test_absolute_capacity_and_frontier_position_not_canonical_length(self):
        self.seed(prompt=262136)
        self.assert_context(262136, 1, block=8)
        with self.assertRaises(ValueError):
            self.ring.context_for(self.key, round=1, anchor_position=262137, block_size=4)
        receipt = self.InputCommit(self.key, 1, 262136, (20, 21, 22, 23), 3, (20, 21, 22, 23))
        self.ring.append_committed(self.prepared(262136, 4), receipt)
        context = self.ring.context_for(self.key, round=2, anchor_position=262140, block_size=4)
        self.assertEqual(context.start_position + context.rows, 262140)
        with self.assertRaises(ValueError):
            self.ring.context_for(self.key, round=2, anchor_position=262140, block_size=8)

    def test_metadata_and_token_domain_failures_do_not_mutate_valid_state(self):
        self.seed(prompt=13)
        for prepared, ids in ((self.prepared(13, 4, dtype=self.t.float32), (13, 14, 15, 16)),
                              (self.prepared(13, 4), (13, 14, 15, 248077))):
            receipt = self.InputCommit(self.key, 1, 13, ids, 0, (13,))
            with self.assertRaises((TypeError, ValueError)):
                self.ring.append_committed(prepared, receipt)
            self.assert_context(13, 1)

    def test_tensor_path_has_no_scalar_read_or_host_copy(self):
        self.seed(prompt=13)
        prepared = self.prepared(13, 4)
        receipt = self.InputCommit(self.key, 1, 13, (13, 14, 15, 16), 1, (13, 14))
        t = self.t
        names = ('__bool__', 'item', 'cpu', 'tolist', 'numpy')
        originals = {name: getattr(t.Tensor, name) for name in names}
        def forbidden(*args, **kwargs):
            raise AssertionError('Device scalar read or host copy in ring')
        try:
            for name in names:
                setattr(t.Tensor, name, forbidden)
            self.ring.append_committed(prepared, receipt)
            actual = self.ring.context_for(self.key, round=2, anchor_position=15, block_size=4)
        finally:
            for name, value in originals.items():
                setattr(t.Tensor, name, value)
        self.assertEqual(actual.rows, 15)


if __name__ == '__main__':
    unittest.main(argv=[arg for arg in sys.argv if arg != '--run-cpu'])
