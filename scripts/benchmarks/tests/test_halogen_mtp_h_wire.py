"""Offline H-only packets: independent layouts, stale bindings and malformed data."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "halogen_mtp_h_wire.py"
HEADER = struct.Struct("<8sIIiiiIiiiI16s16sQQ32s32s32s32s")
HELLO = struct.Struct("<8sIIQ16s16s32s32s32sII")
FRAME = struct.Struct("<8sIIQ32s")


def words(word):
    return struct.pack("<H", word) * 10240


def rehash_request(header, body, rebind=True):
    values = list(HEADER.unpack(header))
    if rebind:
        values[17] = hashlib.sha256(body).digest()
    prefix = HEADER.pack(*values)[:192]
    return prefix + hashlib.sha256(prefix + body).digest() + body


def rehash_response(header, body):
    payload = header + body
    return payload + hashlib.sha256(payload).digest()


class ImplementationTests(unittest.TestCase):
    def test_input_only_h_codec_exists(self):
        self.assertTrue(SOURCE.is_file(), "input-only H codec has not been implemented")


@unittest.skipUnless(SOURCE.is_file(), "codec is not implemented yet")
class HWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("h_wire_under_test", SOURCE)
        cls.wire = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.wire
        spec.loader.exec_module(cls.wire)

    def setUp(self):
        self.session = self.wire.HSession(1729, b"r" * 16, b"e" * 16, b"m" * 32, b"g" * 32)
        self.identity = self.wire.HIdentity(0, 101, 2, 73, 100, 1729, b"r" * 16,
                                           b"e" * 16, 0xdeadbeef12345678, b"m" * 32, b"g" * 32)
        self.input = words(0x3f80)
        self.output = words(0x8000)
        self.request = self.wire.encode_request(self.identity, self.input)

    def test_request_is_only_normalized_input_and_has_two_independent_bindings(self):
        self.assertEqual(HEADER.size, 224)
        self.assertEqual(len(self.request), 20704)
        values = HEADER.unpack_from(self.request)
        self.assertEqual(values[:11], (b"HGNHCPQ1", 1, 20480, 0, 101, 2, 0, 1, 73, 100, 68))
        self.assertEqual(values[11:17], (b"r" * 16, b"e" * 16, 0xdeadbeef12345678,
                                       1729, b"m" * 32, b"g" * 32))
        self.assertEqual(self.request[224:], self.input)
        self.assertEqual(values[17], hashlib.sha256(self.input).digest())
        self.assertEqual(values[18], hashlib.sha256(self.request[:192] + self.input).digest())
        decoded = self.wire.decode_request(self.request, expected_identity=self.identity,
                                            expected_session=self.session)
        self.assertEqual(decoded.identity, self.identity)
        self.assertEqual(decoded.h_norm, self.input)
        self.assertFalse(hasattr(decoded, "native_projection"))
        self.assertFalse(any(self.wire.QUALIFICATIONS.values()))

    def test_response_echoes_every_field_and_preserves_finite_bf16_words(self):
        response = self.wire.make_response(self.request, self.output)
        self.assertEqual(len(response), 20736)
        expected = list(HEADER.unpack_from(self.request))
        expected[0] = b"HGNHCPR1"
        self.assertEqual(response[:224], HEADER.pack(*expected))
        self.assertEqual(response[-32:], hashlib.sha256(response[:-32]).digest())
        self.assertEqual(self.wire.validate_response(self.request, response), self.output)
        for word in (0, 0x8000, 1, 0x7f7f, 0xff7f):
            output = words(word)
            self.assertEqual(self.wire.validate_response(self.request,
                             self.wire.make_response(self.request, output)), output)

    def test_rehashed_malformed_headers_are_rejected(self):
        changes = {0: b"HGNFCPQ1", 1: 2, 2: 20478, 3: 64, 4: -1, 5: -1, 6: 1,
                   7: 4, 8: -1, 9: -1, 10: 65, 11: bytes(16), 12: bytes(16),
                   13: 0, 14: 0, 15: bytes(32), 16: bytes(32)}
        original = list(HEADER.unpack_from(self.request))
        for index, value in changes.items():
            changed = original.copy()
            changed[index] = value
            with self.subTest(field=index), self.assertRaises(ValueError):
                self.wire.decode_request(rehash_request(HEADER.pack(*changed), self.input))

    def test_stale_process_nonce_epoch_model_graph_and_sequence_are_rejected(self):
        response = self.wire.make_response(self.request, self.output)
        changes = dict(sequence=1, position=102, slot=3, token=74, outer_position=101,
                       process_id=1730, run_nonce=b"s" * 16, epoch=b"f" * 16,
                       model_pointer=0x12345678, model_binding=b"n" * 32, graph_binding=b"h" * 32)
        for name, value in changes.items():
            identity = replace(self.identity, **{name: value})
            request = self.wire.encode_request(identity, self.input)
            with self.subTest(field=name):
                with self.assertRaises(ValueError):
                    self.wire.decode_request(request, expected_identity=self.identity)
                with self.assertRaises(ValueError):
                    self.wire.validate_response(request, response)

    def test_bad_digest_and_input_binding_are_rejected(self):
        for offset in (160, 192, 224, len(self.request) - 1):
            packet = bytearray(self.request)
            packet[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.wire.decode_request(bytes(packet))
        body = words(0x3f00)
        with self.assertRaisesRegex(ValueError, "input binding"):
            self.wire.decode_request(rehash_request(self.request[:224], body, False))
        response = self.wire.make_response(self.request, self.output)
        with self.assertRaisesRegex(ValueError, "digest"):
            self.wire.validate_response(self.request, response[:-1] + bytes([response[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, "echo"):
            self.wire.validate_response(self.wire.encode_request(self.identity, body), response)

    def test_nonfinite_words_are_rejected_even_with_valid_digests(self):
        for word in (0x7f80, 0xff80, 0x7fc1):
            body = struct.pack("<H", word) + self.input[2:]
            with self.subTest(word=word):
                with self.assertRaises(ValueError):
                    self.wire.encode_request(self.identity, body)
                with self.assertRaises(ValueError):
                    self.wire.decode_request(rehash_request(self.request[:224], body))
                response = self.wire.make_response(self.request, self.output)
                with self.assertRaises(ValueError):
                    self.wire.validate_response(self.request, rehash_response(response[:224], body))

    def test_every_response_header_field_requires_exact_echo_after_rehash(self):
        response = self.wire.make_response(self.request, self.output)
        original = list(HEADER.unpack_from(response))
        for index, value in enumerate(original):
            changed = original.copy()
            changed[index] = bytes([value[0] ^ 1]) + value[1:] if isinstance(value, bytes) else value + 1
            with self.subTest(field=index), self.assertRaisesRegex(ValueError, "echo"):
                self.wire.validate_response(self.request,
                    rehash_response(HEADER.pack(*changed), self.output))

    def test_handshake_pins_identity_engine_shape_and_finite_budget(self):
        hello = self.wire.encode_hello(self.session)
        self.assertEqual(len(hello), 160)
        values = HELLO.unpack(hello)
        self.assertEqual(values[:8], (b"HGNHHEL1", 1, 64, 1729, b"r" * 16, b"e" * 16,
                                    b"m" * 32, b"g" * 32))
        self.assertEqual(values[8], bytes.fromhex("ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b"))
        self.assertEqual(values[9:], (20480, 68))
        ready = self.wire.make_ready(hello, expected_session=self.session)
        self.assertEqual(ready, b"HGNHACK1" + hello[8:])
        self.wire.validate_ready(hello, ready, expected_session=self.session)
        for offset in (0, 8, 12, 16, 24, 40, 56, 88, 120, 152, 156):
            changed = bytearray(ready)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.wire.validate_ready(hello, bytes(changed))

    def test_framing_exact_extents_digest_and_sequence(self):
        payloads = {1: self.wire.encode_hello(self.session),
                    2: self.wire.make_ready(self.wire.encode_hello(self.session)),
                    3: self.request, 4: self.wire.make_response(self.request, self.output)}
        for kind, payload in payloads.items():
            frame = self.wire.encode_frame(kind, 0, payload)
            self.assertEqual(FRAME.unpack_from(frame), (b"HGNHFRM1", kind, len(payload), 0,
                                                       hashlib.sha256(payload).digest()))
            self.assertEqual(self.wire.decode_frame(frame, expected_kind=kind,
                                                   expected_sequence=0), payload)
            for packet in (frame[:-1], frame + b"x", frame[:56] + bytes([frame[56] ^ 1]) + frame[57:]):
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    self.wire.decode_frame(packet, expected_kind=kind, expected_sequence=0)
        for kind, sequence in ((1, 1), (2, 1), (3, -1), (4, 64)):
            with self.assertRaises(ValueError):
                self.wire.encode_frame(kind, sequence, payloads[kind])

    def test_packet_sequence_cannot_differ_from_bound_frame_sequence(self):
        for kind, payload in ((3, self.request), (4, self.wire.make_response(self.request, self.output))):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "sequence"):
                    self.wire.encode_frame(kind, 1, payload)
                frame = FRAME.pack(b"HGNHFRM1", kind, len(payload), 1, hashlib.sha256(payload).digest()) + payload
                with self.assertRaisesRegex(ValueError, "sequence"):
                    self.wire.decode_frame(frame, expected_kind=kind, expected_sequence=1)

    def test_integer_boundaries_exact_immutable_lengths_and_session_pins(self):
        for name, values in (("sequence", (-1, 64, True)), ("process_id", (0, 1 << 31, True)),
                             ("position", (-1, 1 << 31)), ("model_pointer", (0, 1 << 64)),
                             ("run_nonce", (bytes(16), b"r" * 15)), ("epoch", (bytes(16),)),
                             ("model_binding", (bytes(32),)), ("graph_binding", (bytes(32),))):
            for value in values:
                with self.subTest(field=name), self.assertRaises(ValueError):
                    replace(self.identity, **{name: value})
        for packet in (self.request[:-1], self.request + b"x", bytearray(self.request)):
            with self.assertRaises(ValueError):
                self.wire.decode_request(packet)
        session = replace(self.session, process_id=1730)
        with self.assertRaises(ValueError):
            self.wire.decode_request(self.request, expected_session=session)
        boundary = replace(self.identity, sequence=63, process_id=(1 << 31) - 1,
                           position=(1 << 31) - 1, model_pointer=(1 << 64) - 1)
        self.assertEqual(self.wire.decode_request(self.wire.encode_request(boundary, self.input)).identity,
                         boundary)


if __name__ == "__main__":
    unittest.main()
