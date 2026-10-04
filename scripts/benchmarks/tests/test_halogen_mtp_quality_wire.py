"""Bounded CPU-only checks of candidate publication's stale/corrupt-data gates."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "halogen_mtp_quality_wire.py"
HEADER = struct.Struct("<8sIIiiiI16s32s")


def request(sequence=0, position=100, slot=2, nonce=b"a" * 16):
    body = (struct.pack("<2560H", *([0x3f80] * 2560))
            + struct.pack("<10i", *range(10))
            + struct.pack("<10f", *([.1] * 10))
            + struct.pack("<2560H", *([0x4000] * 2560)))
    header = HEADER.pack(b"HGNMLPQ1", 1, len(body), sequence, position,
                         slot, 0, nonce, bytes(32))
    digest = hashlib.sha256(header[:48] + body).digest()
    return header[:48] + digest + body


class QualityWireTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), "quality wire implementation is missing")
        spec = importlib.util.spec_from_file_location("quality_wire_under_test", SOURCE)
        self.wire = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.wire
        spec.loader.exec_module(self.wire)

    def test_roundtrip_preserves_candidate_bits(self):
        candidate = struct.pack("<2560H", *([0x3e80] * 2560))
        response = self.wire.encode_response(request(), candidate)
        self.assertEqual(len(response), 5232)
        self.assertEqual(self.wire.decode_response(request(), response), candidate)

    def test_prior_position_slot_run_and_sequence_are_rejected(self):
        response = self.wire.encode_response(request(), bytes(5120))
        for changed in (request(position=101), request(slot=3), request(sequence=1),
                        request(nonce=b"b" * 16)):
            with self.subTest(binding=changed[:48]):
                with self.assertRaises(ValueError):
                    self.wire.decode_response(changed, response)

    def test_corrupt_request_and_response_are_rejected(self):
        original = request()
        damaged = original[:-1] + bytes([original[-1] ^ 1])
        with self.assertRaises(ValueError):
            self.wire.decode_request(damaged)
        response = self.wire.encode_response(original, bytes(5120))
        damaged = response[:-1] + bytes([response[-1] ^ 1])
        with self.assertRaises(ValueError):
            self.wire.decode_response(original, damaged)

    def test_nonfinite_bf16_candidate_is_rejected(self):
        for bits in (0x7f80, 0xff80, 0x7fc1):
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                self.wire.encode_response(request(), struct.pack("<H", bits) + bytes(5118))

    def test_truncated_and_extra_bytes_are_rejected(self):
        packet = request()
        response = self.wire.encode_response(packet, bytes(5120))
        for damaged in (response[:-1], response + b"x"):
            with self.assertRaises(ValueError):
                self.wire.decode_response(packet, damaged)
        for candidate in (bytes(5118), bytes(5122)):
            with self.assertRaises(ValueError):
                self.wire.encode_response(packet, candidate)

    def test_out_of_bound_request_identity_is_rejected(self):
        for packet in (request(sequence=4), request(position=-1), request(slot=-1)):
            with self.assertRaises(ValueError):
                self.wire.decode_request(packet)

    def test_atomic_publication_refuses_overwrite_without_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming, candidate = root / "000-request.bin", root / "candidate.bin"
            incoming.write_bytes(request())
            candidate.write_bytes(bytes(5120))
            output = self.wire.publish_response(incoming, candidate)
            saved = output.read_bytes()
            self.assertEqual(self.wire.decode_response(incoming.read_bytes(), saved), bytes(5120))
            with self.assertRaises(FileExistsError):
                self.wire.publish_response(incoming, candidate)
            self.assertEqual(output.read_bytes(), saved)
            self.assertFalse(list(root.glob("*.partial-*")))

    def test_invalid_candidate_creates_no_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming, candidate = root / "000-request.bin", root / "candidate.bin"
            incoming.write_bytes(request())
            candidate.write_bytes(struct.pack("<H", 0x7f80) + bytes(5118))
            with self.assertRaises(ValueError):
                self.wire.publish_response(incoming, candidate)
            self.assertFalse((root / "000-response.bin").exists())
            self.assertFalse(list(root.glob("*.partial-*")))


if __name__ == "__main__":
    unittest.main()
