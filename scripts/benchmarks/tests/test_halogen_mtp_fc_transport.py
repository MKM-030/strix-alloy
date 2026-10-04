"""Focused pure-pipe checks; no process, file transport or device claims."""
import io
from pathlib import Path
import sys
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import halogen_mtp_fc_transport as transport


class SplitReader(io.BytesIO):
    def read(self, count=-1):
        return super().read(min(count, 7))


class SplitWriter(io.BytesIO):
    def write(self, payload):
        return super().write(payload[:11])


class TransportTests(unittest.TestCase):
    def test_fragmented_binary_pipe_round_trip(self):
        payload = bytes(range(256)) * 200 + bytes(224)
        writer = SplitWriter()
        transport.write_frame(writer, transport.REQUEST, 3, payload)
        self.assertEqual(transport.read_frame(SplitReader(writer.getvalue())),
                         (transport.REQUEST, 3, payload))

    def test_digest_tampering_and_truncation_are_rejected(self):
        packet = transport.encode_frame(transport.ARM, 0, bytes(120))
        changed = packet[:-1] + bytes((packet[-1] ^ 1,))
        with self.assertRaises(ValueError):
            transport.read_frame(io.BytesIO(changed))
        with self.assertRaises(EOFError):
            transport.read_frame(SplitReader(packet[:-1]))

    def test_bad_extent_is_rejected_before_payload_read(self):
        class HeaderOnly:
            called = False

            def read(self, count):
                if self.called:
                    raise AssertionError("invalid header requested payload")
                self.called = True
                return transport.FRAME.pack(transport.MAGIC, transport.REQUEST, 0xffffffff, 0, bytes(32))

        with self.assertRaises(ValueError):
            transport.read_frame(HeaderOnly())

    def test_control_and_epoch_sequence_are_bounded(self):
        for kind, sequence, payload in ((transport.HELLO, 1, bytes(464)),
                                        (transport.REQUEST, 4, bytes(51424)),
                                        (transport.DONE, 0, b""),
                                        (transport.ERROR, 0, bytes(4097))):
            with self.assertRaises(ValueError):
                transport.encode_frame(kind, sequence, payload)

    def test_resident_bridge_uses_live_attestation_and_coordinator_pair_contract(self):
        import halogen_mtp_fc_coordinator as state
        import halogen_mtp_fc_wire as wire
        e_descriptor, h_descriptor = bytearray(120), bytearray(120)
        struct.pack_into("<Q", e_descriptor, 0x10, 0x10000000)
        struct.pack_into("<Q", h_descriptor, 0x10, 0x20000000)
        observation = state.Observation(
            b"r" * 16, 1234, 4567, 0x17dcc08, 0x100000, 0, 1, 101, 73, 2, 100, 68, 1,
            0x300000, 0x400000, 0x500000, 0x600000, 0x700000, 0x800000,
            0x100908, 0x100980, 0x10000000, 0x20000000, bytes(e_descriptor), bytes(h_descriptor), 74, 0, 101)
        model = state.CanonicalBinding.from_hashes("model", assets={"fixture": "11" * 32},
                                                  receipts={"fixture": "22" * 32})
        graph = state.CanonicalBinding.from_hashes("graph", assets={"fixture": "33" * 32},
                                                  receipts={"fixture": "44" * 32})
        coordinator = state.ShadowCoordinator(observation, epoch=b"e" * 16,
                                              model_assets=model, graph_assets=graph)
        hello = state.encode_observation(observation)
        requests, frames = [], [transport.encode_frame(transport.HELLO, 0, hello)]
        arm = coordinator.armed
        for sequence in range(4):
            identity = wire.FcIdentity(sequence, 102 + sequence, 2, 73, 101 + sequence,
                                       arm.run_nonce, arm.epoch, arm.model_pointer,
                                       arm.model_binding, arm.graph_binding)
            request = wire.encode_request(identity, bytes(wire.E_BYTES), bytes(wire.H_BYTES),
                                          b"\x80\x3f" * 2560, b"\x00\x40" * 10240)
            requests.append(request)
            frames.append(transport.encode_frame(transport.REQUEST, sequence, request))
        frames.append(transport.encode_frame(transport.DONE, 0, b'{"requests":4}'))
        output = SplitWriter()
        result = transport.bridge_loop(SplitReader(b"".join(frames)), output,
            expected_observation=hello, armed_packet=coordinator.armed_packet, coordinator=coordinator,
            compute_pair=lambda request: request.native_projections, live_guard=lambda: (1234, 4567))
        self.assertEqual(result["requests"], 4)
        self.assertFalse(result["npu_qualified"])
        replies = SplitReader(output.getvalue())
        self.assertEqual(transport.read_frame(replies), (transport.ARM, 0, coordinator.armed_packet))
        for sequence, request in enumerate(requests):
            kind, returned_sequence, response = transport.read_frame(replies)
            self.assertEqual((kind, returned_sequence), (transport.RESPONSE, sequence))
            self.assertEqual(wire.validate_response(request, response), wire.decode_request(request).native_projections)


if __name__ == "__main__":
    unittest.main()
