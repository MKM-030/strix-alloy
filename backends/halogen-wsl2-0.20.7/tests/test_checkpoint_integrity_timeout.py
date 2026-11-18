"""CPU-only regression coverage for complete-file checksum deadlines."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import checkpoint_integrity


class CheckpointIntegrityTimeoutTests(unittest.TestCase):
    def test_large_ngram_deadline_scales_beyond_old_fixed_timeout(self):
        timeout = checkpoint_integrity.hash_timeout(checkpoint_integrity.NGRAM_SIZE)
        self.assertGreater(timeout, 600)
        self.assertEqual(timeout, 1969)

    def test_deadline_is_bounded_for_small_and_invalid_inputs(self):
        self.assertEqual(checkpoint_integrity.hash_timeout(1), 600)
        self.assertEqual(checkpoint_integrity.hash_timeout(10**15), 3600)
        for value in (0, -1, 1.5, True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checkpoint_integrity.hash_timeout(value)

    def test_official_r2_drafter_uses_the_exact_receipt_identity(self):
        self.assertEqual(checkpoint_integrity.DRAFTER_NAME,
                         "qwen38-flash-next-drafter-r2-ht4.hgn")
        self.assertEqual(checkpoint_integrity.DRAFTER_SIZE, 1488276864)
        self.assertEqual(checkpoint_integrity.DRAFTER_SHA,
                         "f9aa330800cc921fe20f4cf997d660f519c67b0052af0c8078b6b648972b07e6")
        machine = {"models": "/models"}
        with patch.object(checkpoint_integrity, "_verify_file",
                          return_value={"qualified": True}) as verify:
            self.assertEqual(checkpoint_integrity.verify_drafter(machine, "/local"),
                             {"qualified": True})
        verify.assert_called_once_with(
            machine, "/local", "/models/qwen38-flash-next-drafter-r2-ht4.hgn",
            "r2-integrity.json", checkpoint_integrity.DRAFTER_SIZE,
            checkpoint_integrity.DRAFTER_SHA, "r2 draft head")

    def test_official_vision_sidecar_uses_the_exact_receipt_identity(self):
        self.assertEqual(getattr(checkpoint_integrity, "VISION_NAME", None),
                         "qwen38-flash-next-vision.hgn")
        self.assertEqual(getattr(checkpoint_integrity, "VISION_SIZE", None), 897916416)
        self.assertEqual(getattr(checkpoint_integrity, "VISION_SHA", None),
                         "d62e0ae553fe88afd3833733d4a4c669f34d20fd8dfce4b9610525bed2134b10")
        machine = {"models": "/models"}
        with patch.object(checkpoint_integrity, "_verify_file",
                          return_value={"qualified": True}) as verify:
            self.assertEqual(checkpoint_integrity.verify_vision(machine, "/local"),
                             {"qualified": True})
        verify.assert_called_once_with(
            machine, "/local", "/models/qwen38-flash-next-vision.hgn",
            "vision-integrity.json", checkpoint_integrity.VISION_SIZE,
            checkpoint_integrity.VISION_SHA, "vision tower")


if __name__ == "__main__":
    unittest.main()
