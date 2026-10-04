"""Focused offline source tests for fixed discovery/arm and consume-once state."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "halogen_mtp_fc_coordinator.py"
SPEC_OBSERVATION = struct.Struct("<8sII16sIIQQQiiiiiiIIQQQQQQQQQQ120s120siiiI32s")
SPEC_ARMED = struct.Struct("<8sII16s16sQ32s32s")


class FcCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SOURCE.parent))
        try:
            spec = importlib.util.spec_from_file_location("fc_coordinator_under_test", SOURCE)
            cls.codec = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = cls.codec
            spec.loader.exec_module(cls.codec)
        finally:
            sys.path.pop(0)
        cls.wire = cls.codec.wire

    def setUp(self):
        descriptor_e, descriptor_h = bytearray(120), bytearray(120)
        struct.pack_into("<Q", descriptor_e, 0x10, 0x10000000)
        struct.pack_into("<Q", descriptor_h, 0x10, 0x20000000)
        self.observation = self.codec.Observation(
            b"r" * 16, 1234, 4567, 0x17dcc08, 0x100000, 0, 1, 101, 73, 2, 100, 68, 1,
            0x300000, 0x400000, 0x500000, 0x600000, 0x700000, 0x800000,
            0x100908, 0x100980, 0x10000000, 0x20000000, bytes(descriptor_e), bytes(descriptor_h), 74, 0, 101)
        self.model = self.codec.CanonicalBinding.from_hashes("model", assets={"checkpoint": "11" * 32,
            "embedding_raw_q8": "22" * 32, "hidden_raw_q8": "33" * 32}, receipts={"native_asset_receipt": "44" * 32})
        self.graph = self.codec.CanonicalBinding.from_hashes("graph", assets={"graph": "55" * 32,
            "builder": "66" * 32}, receipts={"cpu_receipt": "77" * 32})
        self.buffers = (b"\x80\x3f" * 2560, b"\x00\x40" * 10240,
                        b"\x80\x3e" * 2560, b"\x80\xbf" * 10240)
        self.pair = self.wire.ProjectionPair(b"\x00\x80" * 2560, b"\x01\x00" * 10240)

    def coordinator(self):
        return self.codec.ShadowCoordinator(self.observation, epoch=b"e" * 16,
                                            model_assets=self.model, graph_assets=self.graph)

    def packet(self, coordinator, sequence=0, **changes):
        armed = coordinator.armed
        identity = self.wire.FcIdentity(sequence, 102, 2, 73, 101, armed.run_nonce, armed.epoch,
                                        armed.model_pointer, armed.model_binding, armed.graph_binding)
        return self.wire.encode_request(replace(identity, **changes), *self.buffers)

    def respond(self, coordinator, packet, candidate=None, **process):
        return coordinator.respond(packet, candidate or (lambda request: self.pair),
            expected_pid=process.get("pid", 1234), expected_starttime=process.get("starttime", 4567))

    def test_exact_observation_layout_digest_and_current_process_admission(self):
        packet = self.codec.encode_observation(self.observation)
        self.assertEqual(SPEC_OBSERVATION.size, 464)
        fields = SPEC_OBSERVATION.unpack(packet)
        self.assertEqual(fields[:9], (b"HGNFCO01", 1, 464, b"r" * 16, 1234, 0, 4567, 0x17dcc08, 0x100000))
        self.assertEqual(fields[-1], hashlib.sha256(packet[:432]).digest())
        self.assertEqual(self.codec.decode_observation(packet, b"r" * 16, 1234, 4567), self.observation)
        for nonce, pid, starttime in ((b"x" * 16, 1234, 4567), (b"r" * 16, 1235, 4567), (b"r" * 16, 1234, 4568)):
            with self.assertRaises(ValueError):
                self.codec.decode_observation(packet, nonce, pid, starttime)
        for index, value in ((0, b"OLDMAGIC"), (2, 432), (5, 1), (9, 1), (10, 2), (15, 65), (16, 0), (-2, 1)):
            changed = list(fields)
            changed[index], changed[-1] = value, bytes(32)
            payload = SPEC_OBSERVATION.pack(*changed)[:432]
            with self.assertRaises(ValueError):
                self.codec.decode_observation(payload + hashlib.sha256(payload).digest(), b"r" * 16, 1234, 4567)
        with self.assertRaises(ValueError):
            self.codec.decode_observation(packet[:-1], b"r" * 16, 1234, 4567)
        with self.assertRaises(ValueError):
            replace(self.observation, h_projection_pointer=self.observation.e_norm_pointer)

    def test_exact_arm_echo_and_immutable_canonical_binding(self):
        coordinator = self.coordinator()
        packet = coordinator.armed_packet
        self.assertEqual(SPEC_ARMED.size, 120)
        self.assertEqual(SPEC_ARMED.unpack(packet), (b"HGNFCA01", 1, 0, b"r" * 16, b"e" * 16,
                                                   0x100000, self.model.digest, self.graph.digest))
        self.assertEqual(self.codec.validate_armed(self.observation, packet), coordinator.armed)
        wrong = replace(coordinator.armed, model_pointer=0x200000)
        with self.assertRaises(ValueError):
            self.codec.validate_armed(self.observation, self.codec.encode_armed(wrong))
        values = {"b": "22" * 32, "a": "11" * 32}
        binding = self.codec.CanonicalBinding.from_hashes("model", assets=values, receipts={"proof": "33" * 32})
        digest = binding.digest
        values["a"] = "44" * 32
        self.assertEqual(binding.digest, digest)
        self.assertEqual(digest, self.codec.CanonicalBinding.from_hashes("model", assets={"a": "11" * 32,
            "b": "22" * 32}, receipts={"proof": "33" * 32}).digest)
        with self.assertRaises(ValueError):
            self.codec.CanonicalBinding.from_hashes("graph", assets={"graph": True}, receipts={"proof": "33" * 32})
        self.assertFalse(any(coordinator.qualifications.values()))

    def test_four_ordered_sequences_echo_and_preserve_both_candidates(self):
        coordinator, seen = self.coordinator(), []
        for sequence in range(4):
            packet = self.packet(coordinator, sequence)
            def candidate(request):
                seen.append(request.identity.sequence)
                self.assertEqual(len(coordinator.consumed_requests), sequence + 1)
                return self.pair
            response = self.respond(coordinator, packet, candidate)
            self.assertEqual(self.wire.validate_response(packet, response), self.pair)
        self.assertEqual(seen, [0, 1, 2, 3])
        self.assertIsNone(coordinator.failure_reason)
        self.assertEqual(tuple(seq for seq, binding in coordinator.consumed_requests), (0, 1, 2, 3))

    def test_stale_armed_or_process_identity_latches_before_candidate(self):
        for changes in ({"run_nonce": b"x" * 16}, {"epoch": b"x" * 16}, {"model_pointer": 0x200000},
                        {"model_binding": b"x" * 32}, {"graph_binding": b"x" * 32}):
            coordinator, seen = self.coordinator(), []
            with self.assertRaises(ValueError):
                self.respond(coordinator, self.packet(coordinator, **changes), lambda request: seen.append(request))
            self.assertEqual(seen, [])
            self.assertEqual(coordinator.consumed_requests, ())
            self.assertIsNotNone(coordinator.failure_reason)
        for process in ({"pid": 1235}, {"starttime": 4568}):
            coordinator = self.coordinator()
            with self.assertRaises(ValueError):
                self.respond(coordinator, self.packet(coordinator), **process)
            self.assertIsNotNone(coordinator.failure_reason)

    def test_gap_and_replay_are_terminal(self):
        coordinator = self.coordinator()
        with self.assertRaises(ValueError):
            self.respond(coordinator, self.packet(coordinator, 1))
        with self.assertRaises(ValueError):
            self.respond(coordinator, self.packet(coordinator, 0))
        coordinator = self.coordinator()
        packet = self.packet(coordinator)
        self.respond(coordinator, packet)
        with self.assertRaises(ValueError):
            self.respond(coordinator, packet)
        self.assertEqual(len(coordinator.consumed_requests), 1)

    def test_corrupt_request_latches_before_candidate_or_sequence_burn(self):
        coordinator, seen = self.coordinator(), []
        packet = bytearray(self.packet(coordinator))
        packet[-1] ^= 1
        with self.assertRaises(ValueError):
            self.respond(coordinator, bytes(packet), lambda request: seen.append(request))
        self.assertEqual(seen, [])
        self.assertEqual(coordinator.consumed_requests, ())
        with self.assertRaises(ValueError):
            self.respond(coordinator, self.packet(coordinator))

    def test_candidate_timeout_or_nonfinite_pair_burns_before_failure(self):
        for failure in (TimeoutError, ValueError):
            coordinator, seen = self.coordinator(), []
            packet = self.packet(coordinator)
            def candidate(request):
                seen.append(request.request_binding)
                if failure is TimeoutError:
                    raise TimeoutError("external candidate deadline")
                return self.wire.ProjectionPair(self.pair.e_projection, b"\x80\x7f" * 10240)
            with self.assertRaises(failure):
                self.respond(coordinator, packet, candidate)
            self.assertEqual(len(coordinator.consumed_requests), 1)
            with self.assertRaises(ValueError):
                self.respond(coordinator, packet, candidate)
            self.assertEqual(len(seen), 1)

    def test_reentrant_or_external_abort_prevents_response_release(self):
        for external in (False, True):
            coordinator = self.coordinator()
            def candidate(request):
                if external:
                    coordinator.abort("transport-failed")
                else:
                    with self.assertRaises(ValueError):
                        self.respond(coordinator, self.packet(coordinator, 1))
                return self.pair
            with self.assertRaises(ValueError):
                self.respond(coordinator, self.packet(coordinator), candidate)
            self.assertEqual(len(coordinator.consumed_requests), 1)
            self.assertIsNotNone(coordinator.failure_reason)


if __name__ == "__main__":
    unittest.main()
