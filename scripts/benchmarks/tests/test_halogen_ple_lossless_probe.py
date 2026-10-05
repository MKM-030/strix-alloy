"""Three bounded stdlib codec fixtures; no checkpoint, device or provider reads."""
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "halogen_ple_lossless_probe.py"


class PleLosslessProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("halogen_ple_lossless_probe", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def test_held_out_all_symbols_and_independent_indexed_rows(self):
        m = self.module
        scale = bytes.fromhex("12345678")
        train = bytes(256 * m.ROW_BYTES)
        evaluation = bytes(range(256)) * m.ROW_BYTES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            windows = []
            for index, (data, split) in enumerate(((train, "train"), (evaluation, "eval"))):
                path = root / f"window-{index}.u8"
                path.write_bytes(data)
                windows.append(dict(file=str(path), sha256=hashlib.sha256(data).hexdigest(),
                                    region="fixture", window_index=index, rows=256, split=split))
            manifest = dict(schema="halogen.ple-samples.v1", row_bytes=160,
                            global_scale_bits=scale.hex(), source=dict(
                                extraction_receipt_sha256="1" * 64, tensor_sha256="2" * 64),
                            windows=windows)
            path = root / "manifest.json"
            raw_manifest = json.dumps(manifest).encode()
            path.write_bytes(raw_manifest)
            loaded = m.load_samples(path, hashlib.sha256(raw_manifest).hexdigest())
        lengths = m.train_lengths(loaded.train_bytes)
        trained_bank = m.encode_rows(train, lengths, scale)
        self.assertLess(trained_bank.accounting()["net_bytes"], len(train))
        # A one-symbol training distribution still encodes every unseen symbol.
        self.assertEqual(len(lengths), 256)
        self.assertTrue(all(lengths))
        bank = m.encode_rows(evaluation, lengths, scale)
        self.assertEqual(bank.global_scale, scale)
        for index in (255, 0, 17, 1, 128):
            self.assertEqual(m.decode_row(bank, index),
                             evaluation[index * 160:(index + 1) * 160])
        self.assertEqual(b"".join(m.decode_row(bank, i) for i in range(256)), evaluation)
        report = m.probe_samples(loaded)
        self.assertTrue(report["huffman"]["exact_roundtrip"])
        self.assertEqual(report["huffman"]["training_bytes"], len(train))
        self.assertEqual(report["huffman"]["rows"], 512)
        self.assertFalse(report["live_consumer_implemented"])

    def test_truncated_corrupt_and_noncanonical_trailing_rows_rejected(self):
        m = self.module
        raw = bytes(range(160)) * 3
        bank = m.encode_rows(raw, m.train_lengths(raw), bytes.fromhex("0000803f"))
        with self.assertRaisesRegex(ValueError, "offset|extent"):
            dataclasses.replace(bank, payload=bank.payload[:-1])
        mutated = bytes([bank.payload[0] ^ 128]) + bank.payload[1:]
        with self.assertRaisesRegex(ValueError, "checksum|truncated|trailing|padding"):
            m.decode_row(dataclasses.replace(bank, payload=mutated), 0)
        offsets = (*bank.offsets[:-1], bank.offsets[-1] + 1)
        with self.assertRaisesRegex(ValueError, "trailing|padding"):
            m.decode_row(dataclasses.replace(bank, payload=bank.payload + b"\0", offsets=offsets), 2)
        with self.assertRaisesRegex(ValueError, "code lengths"):
            m.encode_rows(raw, bytes([1] * 256), bank.global_scale)
        with self.assertRaisesRegex(ValueError, "row index"):
            m.decode_row(bank, 3)

    def test_uniform_incompressible_control_includes_all_metadata(self):
        m = self.module
        raw = bytes(range(256)) * 5  # Eight independent 160-byte rows; every byte equally frequent.
        lengths = m.train_lengths(raw)
        self.assertEqual(lengths, bytes([8] * 256))
        bank = m.encode_rows(raw, lengths, bytes.fromhex("01020304"))
        account = bank.accounting()
        self.assertEqual(account["encoded_data_bytes"], len(raw))
        self.assertEqual(account["row_directory_bytes"], 4 * (8 + 1))
        self.assertEqual(account["row_checksum_bytes"], 4 * 8)
        self.assertEqual(account["canonical_lengths_bytes"], 256)
        self.assertEqual(account["global_scale_bytes"], 4)
        self.assertEqual(account["net_bytes"], len(raw) + 4 * 9 + 4 * 8 + 256 + 4)
        self.assertGreater(account["net_bytes"], len(raw) + 4)
        self.assertAlmostEqual(m.byte_entropy(raw), 8.0)
        self.assertEqual(b"".join(m.decode_row(bank, i) for i in range(8)), raw)
        blocks = m.zlib_blocks(raw, rows_per_block=4, global_scale=bank.global_scale)
        self.assertTrue(blocks["exact_roundtrip"])
        self.assertEqual(blocks["block_directory_bytes"], 4 * 3)
        self.assertEqual(blocks["net_bytes"], blocks["encoded_data_bytes"] + 4 * 3 + 4)
        self.assertEqual(blocks["worst_single_row_raw_decode_bytes"], 640)


if __name__ == "__main__":
    unittest.main()
