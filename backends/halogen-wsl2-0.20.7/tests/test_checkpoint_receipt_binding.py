"""Receipt-to-bridge binding without model, WSL, container, or GPU access."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import checkpoint_integrity as ci
import service


def receipt(size, sha, inode):
    return {
        "sha256": sha,
        "identity": {
            "size": size,
            "device": 2049,
            "inode": inode,
            "mtime_ns": 10_000_000_001,
            "ctime_ns": 20_000_000_002,
        },
    }


class CheckpointReceiptBindingTests(unittest.TestCase):
    def setUp(self):
        self.receipts = {
            "main": receipt(ci.SIZE, ci.SHA, 41),
            "r2": receipt(ci.DRAFTER_SIZE, ci.DRAFTER_SHA, 42),
            "vision": receipt(
                897916416,
                "d62e0ae553fe88afd3833733d4a4c669f34d20fd8dfce4b9610525bed2134b10",
                43,
            ),
        }

    def test_all_bridge_mappings_use_complete_hash_receipts(self):
        self.assertTrue(hasattr(ci, "verify_vision"),
                        "vision must use the bounded complete-file receipt path")
        machine = {"models": "/models"}
        with patch.object(ci, "verify", return_value=self.receipts["main"]) as main, \
                patch.object(ci, "verify_ngram", return_value={"qualified": True}) as ngram, \
                patch.object(ci, "verify_drafter", return_value=self.receipts["r2"]) as r2, \
                patch.object(ci, "verify_vision", return_value=self.receipts["vision"]) as vision, \
                patch.object(service.portable, "check_hash"):
            actual = service.verify_checkpoint(machine, "v2", disable_vision=False)
        self.assertEqual(actual, self.receipts)
        main.assert_called_once_with(machine, service.LOCAL)
        ngram.assert_called_once_with(machine, service.LOCAL)
        r2.assert_called_once_with(machine, service.LOCAL)
        vision.assert_called_once_with(machine, service.LOCAL)

    def test_manifest_binds_post_hash_generation_to_bridge_environment(self):
        options = service.options(["--context-size", "32768"])
        base = {"stage": "serve", "artifacts": {
            "bridge": {"path": "C:/fixture/bridge.so",
                       "container_path": "/candidate/bridge.so"},
            "private": {"path": "C:/fixture/private.so",
                        "container_path": "/candidate/private.so"},
        }}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(service.r, "manifest_for", return_value=base), \
                patch.object(service.r, "MACHINE", {"ngram_source": "fixture.hgn"}), \
                patch.object(service.r, "FIXED_MOUNTS", {}):
            attempt = Path(folder)
            (attempt / "entrypoint-service.sh").write_bytes(b"fixture")
            try:
                manifest = service.build_manifest(
                    options, attempt, "a" * 32, checkpoint_receipts=self.receipts)
            except TypeError as exc:
                self.fail(f"build_manifest does not accept verified receipts: {exc}")
        self.assertEqual(
            manifest["environment"]["HALOGEN_V2_MAIN_IDENTITY"],
            "2049,41,66687678432,10000000001,20000000002",
        )
        self.assertEqual(
            manifest["environment"]["HALOGEN_V2_R2_IDENTITY"],
            "2049,42,1488276864,10000000001,20000000002",
        )
        self.assertEqual(
            manifest["environment"]["HALOGEN_V2_VISION_IDENTITY"],
            "2049,43,897916416,10000000001,20000000002",
        )

    def test_missing_or_changed_receipt_identity_fails_closed(self):
        self.assertTrue(hasattr(service, "checkpoint_receipt_environment"),
                        "service must encode verified receipt generations")
        for name, changed in (
            ("missing", {"main": self.receipts["main"], "r2": self.receipts["r2"]}),
            ("changed", {
                **self.receipts,
                "r2": {
                    **self.receipts["r2"],
                    "sha256": "0" * 64,
                },
            }),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                service.checkpoint_receipt_environment(changed, disable_vision=False)


if __name__ == "__main__":
    unittest.main()
