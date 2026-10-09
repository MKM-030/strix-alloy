"""No tensor arithmetic, model execution, or accelerator imports in this suite."""
import importlib
import json
import struct
import tempfile
import unittest
from pathlib import Path


def implementation(test):
    try:
        return importlib.import_module("contract")
    except ModuleNotFoundError:
        test.fail("K3 tensor and frontier contract has not been implemented")


class ContractTests(unittest.TestCase):
    def test_anchor_query_zero_predicts_next_and_mask_is_internal(self):
        c = implementation(self)
        q = c.query_layout(anchor_id=7, anchor_position=23)
        self.assertEqual(q.input_ids, (7, 248077, 248077))
        self.assertEqual(q.query_positions, (23, 24, 25))
        self.assertEqual(q.output_positions, (24, 25, 26))
        with self.assertRaises(ValueError):
            c.query_layout(anchor_id=248077, anchor_position=23)

    def test_verification_keeps_current_plus_accepted_prefix_not_bonus(self):
        c = implementation(self)
        state = c.Frontier("request-A", 2)
        state.initialize(tuple(range(5)))
        q = state.begin(0, 42, 5)
        state.record_proposal(q, (10, 11, 12))
        plan = state.plan_commit(0, (42, 10, 11, 12), (5, 6, 7, 8), 1, 99)
        self.assertEqual(plan.retained_indices, (0, 1))
        self.assertEqual(plan.retained_ids, (42, 10))
        self.assertEqual(plan.next_anchor_position, 7)
        state.finish_commit(plan)
        next_q = state.begin(1, 99, 7)
        self.assertEqual(next_q.output_positions, (8, 9, 10))

    def test_zero_and_full_acceptance_select_exact_input_rows(self):
        c = implementation(self)
        for accepted, expected in [(0, (0,)), (3, (0, 1, 2, 3))]:
            state = c.Frontier("request-A", 2)
            state.initialize((0, 1))
            q = state.begin(0, 5, 2)
            state.record_proposal(q, (6, 7, 8))
            plan = state.plan_commit(0, (5, 6, 7, 8), (2, 3, 4, 5), accepted, 9)
            self.assertEqual(plan.retained_indices, expected)

    def test_stale_round_or_wrong_input_identity_cannot_commit(self):
        c = implementation(self)
        state = c.Frontier("request-A", 2)
        state.initialize((0, 1))
        q = state.begin(0, 5, 2)
        state.record_proposal(q, (6, 7, 8))
        with self.assertRaises(ValueError):
            state.plan_commit(1, (5, 6, 7, 8), (2, 3, 4, 5), 1, 9)
        with self.assertRaises(ValueError):
            state.plan_commit(0, (5, 6, 77, 8), (2, 3, 4, 5), 1, 9)
        state.retire()
        with self.assertRaises(ValueError):
            state.begin(0, 5, 2)

    def test_supplied_tensor_inventory_excludes_head_and_embedding(self):
        c = implementation(self)
        shapes = c.checkpoint_shapes()
        self.assertEqual(len(shapes), 58)
        self.assertEqual(shapes["fc.weight"], (2560, 12800))
        self.assertEqual(shapes["layers.4.self_attn.q_proj.weight"], (6144, 2560))
        self.assertEqual(sum(c.numel(s) for s in shapes.values()), 498106880)
        self.assertFalse(any("embed_tokens" in n or "lm_head" in n for n in shapes))

    def test_safetensors_rejects_duplicate_key_and_uncovered_data(self):
        c = implementation(self)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiny.safetensors"
            duplicate = b'{"x":{"dtype":"BF16","shape":[1],"data_offsets":[0,2]},"x":{"dtype":"BF16","shape":[1],"data_offsets":[0,2]}}'
            p.write_bytes(struct.pack("<Q", len(duplicate)) + duplicate + b"\x00\x00")
            with self.assertRaises(ValueError):
                c.inspect_safetensors(p)
            header = json.dumps({"x": {"dtype": "BF16", "shape": [1], "data_offsets": [0, 2]}}).encode()
            p.write_bytes(struct.pack("<Q", len(header)) + header + b"\x00\x00\x00\x00")
            with self.assertRaises(ValueError):
                c.inspect_safetensors(p)

    def test_safetensors_parses_header_without_importing_torch(self):
        c = implementation(self)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiny.safetensors"
            header = json.dumps({"x": {"dtype": "BF16", "shape": [2], "data_offsets": [0, 4]}}).encode()
            p.write_bytes(struct.pack("<Q", len(header)) + header + b"\x00" * 4)
            manifest = c.inspect_safetensors(p)
            self.assertEqual(manifest.tensors["x"].shape, (2,))
            self.assertEqual(manifest.data_bytes, 4)


if __name__ == "__main__":
    unittest.main()
