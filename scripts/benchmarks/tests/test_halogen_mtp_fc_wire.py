"""Focused offline checks of fixed FC framing, bindings and complete echo."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "halogen_mtp_fc_wire.py"
SPEC_HEADER = struct.Struct("<8sIIiiiIiiiI16s16sQQ32s32s32s32s")


def words(size, value):
    return struct.pack("<H", value) * (size // 2)


def request_rehash(header, body, rebind_inputs=False):
    fields = list(SPEC_HEADER.unpack(header))
    if rebind_inputs:
        fields[17] = hashlib.sha256(body[:25600]).digest()
    fields[18] = bytes(32)
    prefix = SPEC_HEADER.pack(*fields)[:192]
    return prefix + hashlib.sha256(prefix + body).digest() + body


def response_rehash(header, body):
    payload = header + body
    return payload + hashlib.sha256(payload).digest()


class FcWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fc_wire_under_test", SOURCE)
        cls.wire = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.wire
        spec.loader.exec_module(cls.wire)

    def setUp(self):
        self.identity = self.wire.FcIdentity(0, 101, 2, 73, 100, b"r" * 16, b"e" * 16,
                                             0xdeadbeef12345678, b"m" * 32, b"g" * 32)
        self.buffers = (words(5120, 0x3f80), words(20480, 0x4000),
                        words(5120, 0x3e80), words(20480, 0xbf80))
        self.request = self.wire.encode_request(self.identity, *self.buffers)
        self.candidates = (words(5120, 0x8000), words(20480, 0x0001))

    def test_exact_layout_digest_boundaries_and_bit_preserving_roundtrip(self):
        self.assertEqual(SPEC_HEADER.size, 224)
        self.assertEqual(len(self.request), 51424)
        header = SPEC_HEADER.unpack_from(self.request)
        self.assertEqual(header[:11], (b"HGNFCPQ1", 1, 51200, 0, 101, 2, 0, 1, 73, 100, 68))
        self.assertEqual(header[11:17], (b"r" * 16, b"e" * 16, 0xdeadbeef12345678, 0, b"m" * 32, b"g" * 32))
        body = b"".join(self.buffers)
        self.assertEqual(self.request[224:], body)
        self.assertEqual(header[17], hashlib.sha256(body[:25600]).digest())
        self.assertEqual(header[18], hashlib.sha256(self.request[:192] + body).digest())
        decoded = self.wire.decode_request(self.request, expected_identity=self.identity)
        self.assertEqual(decoded.identity, self.identity)
        self.assertEqual((decoded.e_norm, decoded.h_norm), self.buffers[:2])
        self.assertEqual((decoded.native_projections.e_projection, decoded.native_projections.h_projection), self.buffers[2:])
        response = self.wire.make_response(self.request, *self.candidates)
        self.assertEqual(len(response), 25856)
        wanted_header = list(header)
        wanted_header[0], wanted_header[2] = b"HGNFCPR1", 25600
        self.assertEqual(response[:224], SPEC_HEADER.pack(*wanted_header))
        self.assertEqual(response[-32:], hashlib.sha256(response[:-32]).digest())
        pair = self.wire.validate_response(self.request, response, expected_identity=self.identity)
        self.assertEqual((pair.e_projection, pair.h_projection), self.candidates)
        self.assertFalse(any(self.wire.QUALIFICATIONS.values()))

    def test_rehashed_malformed_request_headers_are_rejected(self):
        changes = {0: b"HGNMLPQ1", 1: 2, 2: 25600, 3: 4, 4: -1, 5: -1,
                   6: 1, 7: 2, 8: -1, 9: -1, 10: 65, 11: bytes(16),
                   12: bytes(16), 13: 0, 14: 1, 15: bytes(32), 16: bytes(32)}
        original = list(SPEC_HEADER.unpack_from(self.request))
        for index, value in changes.items():
            with self.subTest(field=index):
                changed = original.copy()
                changed[index] = value
                packet = request_rehash(SPEC_HEADER.pack(*changed), self.request[224:])
                with self.assertRaises(ValueError):
                    self.wire.decode_request(packet)

    def test_request_hash_covers_native_outputs_and_separate_input_binding(self):
        for offset in (224, 224 + 25600, len(self.request) - 1):
            with self.subTest(offset=offset):
                changed = bytearray(self.request)
                changed[offset] ^= 1
                with self.assertRaises(ValueError):
                    self.wire.decode_request(bytes(changed))
        body = bytearray(self.request[224:])
        body[0] ^= 1
        packet = request_rehash(self.request[:224], bytes(body))
        with self.assertRaisesRegex(ValueError, "input binding"):
            self.wire.decode_request(packet)

    def test_nonfinite_words_in_each_request_array_are_rejected_after_rebinding(self):
        for offset in (0, 5120, 25600, 30720):
            for value in (0x7f80, 0xff80, 0x7fc1):
                with self.subTest(array_offset=offset, word=value):
                    body = bytearray(self.request[224:])
                    body[offset:offset + 2] = struct.pack("<H", value)
                    packet = request_rehash(self.request[:224], bytes(body), rebind_inputs=True)
                    with self.assertRaises(ValueError):
                        self.wire.decode_request(packet)

    def test_every_response_header_field_is_echoed_even_with_valid_final_digest(self):
        response = self.wire.make_response(self.request, *self.candidates)
        original = list(SPEC_HEADER.unpack_from(response))
        for index, value in enumerate(original):
            changed = original.copy()
            changed[index] = bytes([value[0] ^ 1]) + value[1:] if isinstance(value, bytes) else value + 1
            packet = response_rehash(SPEC_HEADER.pack(*changed), response[224:-32])
            with self.subTest(field=index), self.assertRaisesRegex(ValueError, "echo"):
                self.wire.validate_response(self.request, packet)

    def test_prior_model_epoch_run_graph_and_call_identities_are_rejected(self):
        response = self.wire.make_response(self.request, *self.candidates)
        changes = dict(sequence=1, position=102, slot=3, token=74, outer_position=99,
                       run_nonce=b"s" * 16, epoch=b"f" * 16, model_pointer=0x12345678,
                       model_binding=b"n" * 32, graph_binding=b"h" * 32)
        for name, value in changes.items():
            identity = replace(self.identity, **{name: value})
            packet = self.wire.encode_request(identity, *self.buffers)
            with self.subTest(identity=name):
                with self.assertRaisesRegex(ValueError, "armed"):
                    self.wire.decode_request(packet, expected_identity=self.identity)
                with self.assertRaisesRegex(ValueError, "echo"):
                    self.wire.validate_response(packet, response)
                with self.assertRaisesRegex(ValueError, "armed"):
                    self.wire.make_response(packet, *self.candidates, expected_identity=self.identity)

    def test_same_identity_but_changed_request_body_rejects_old_response(self):
        response = self.wire.make_response(self.request, *self.candidates)
        for index in (0, 2):
            changed = list(self.buffers)
            changed[index] = words(len(changed[index]), 0x3f00)
            packet = self.wire.encode_request(self.identity, *changed)
            with self.subTest(array=index), self.assertRaisesRegex(ValueError, "echo"):
                self.wire.validate_response(packet, response)

    def test_response_digest_and_finite_pair_checks_precede_any_output_return(self):
        response = self.wire.make_response(self.request, *self.candidates)
        with self.assertRaisesRegex(ValueError, "digest"):
            self.wire.validate_response(self.request, response[:-1] + bytes([response[-1] ^ 1]))
        for offset in (0, 5120):
            body = bytearray(response[224:-32])
            body[offset:offset + 2] = struct.pack("<H", 0x7f81)
            with self.subTest(array_offset=offset), self.assertRaisesRegex(ValueError, "nonfinite"):
                self.wire.validate_response(self.request, response_rehash(response[:224], bytes(body)))
        for index in (0, 1):
            pair = list(self.candidates)
            pair[index] = struct.pack("<H", 0xff80) + pair[index][2:]
            with self.subTest(candidate=index), self.assertRaises(ValueError):
                self.wire.make_response(self.request, *pair)

    def test_exact_lengths_integer_ranges_and_nonzero_bindings(self):
        response = self.wire.make_response(self.request, *self.candidates)
        for packet in (self.request[:-1], self.request + b"x"):
            with self.assertRaises(ValueError):
                self.wire.decode_request(packet)
        for packet in (response[:-1], response + b"x"):
            with self.assertRaises(ValueError):
                self.wire.validate_response(self.request, packet)
        for index in (0, 1):
            pair = list(self.candidates)
            pair[index] = pair[index][:-2]
            with self.assertRaises(ValueError):
                self.wire.make_response(self.request, *pair)
        for name, values in (("sequence", (-1, 4, True)), ("position", (-1, 1 << 31)),
                             ("slot", (-1, 1 << 31)), ("token", (-1, 1 << 31)),
                             ("outer_position", (-1, 1 << 31)), ("model_pointer", (0, 1 << 64)),
                             ("run_nonce", (bytes(16), b"r" * 15)), ("epoch", (bytes(16), b"e" * 17)),
                             ("model_binding", (bytes(32), b"m" * 31)), ("graph_binding", (bytes(32), b"g" * 33))):
            for value in values:
                with self.subTest(identity=name, value=value), self.assertRaises(ValueError):
                    replace(self.identity, **{name: value})
        boundary = replace(self.identity, sequence=3, position=(1 << 31) - 1,
                           slot=(1 << 31) - 1, token=(1 << 31) - 1, outer_position=(1 << 31) - 1,
                           model_pointer=(1 << 64) - 1)
        packet = self.wire.encode_request(boundary, *self.buffers)
        self.assertEqual(self.wire.decode_request(packet).identity, boundary)


if __name__ == "__main__":
    unittest.main()
