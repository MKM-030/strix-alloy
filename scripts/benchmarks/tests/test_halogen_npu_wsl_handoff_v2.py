"""Offline binary-pipe framing and GPU-ack checks. No provider/GPU imports."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "halogen_npu_wsl_handoff_v2.py"
spec = importlib.util.spec_from_file_location("handoff_pipe_contract", SOURCE)
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)

SCHEMA = "halogen-npu-wsl-binary-pipe.v2"
MAGIC = b"HGNPIPE2"
ROW_BYTES = 5120


def encoded_frame(meta, payload=b""):
    header = json.dumps(meta, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return MAGIC + struct.pack(">II", len(header), len(payload)) + header + payload


class FragmentedStream(io.BytesIO):
    """Model pipe reads returning fewer bytes than requested."""

    def read(self, size=-1):
        return super().read(min(size, 7) if size >= 0 else 7)


class BinaryPipeContractTests(unittest.TestCase):
    def setUp(self):
        # Include CR, LF, NUL, and invalid UTF-8; BF16 rows are opaque bytes here.
        self.payload = bytes(range(256)) * 20
        self.binding = "b" * 64
        self.ready = {"native_pid": 7, "native_starttime_ticks": 11}
        sha = hashlib.sha256(self.payload).hexdigest()
        self.meta = {"schema": SCHEMA, "kind": "row", "sequence": 0,
                     "model_binding": self.binding, "input_sha256": sha,
                     "input_bytes": ROW_BYTES}
        self.ack = {"schema": SCHEMA, "kind": "row", "sequence": 0,
                    "model_binding": self.binding, "transport": "binary-pipe", "passed": True,
                    "input_sha256": sha, "output_sha256": sha,
                    "input_bytes": ROW_BYTES, "output_bytes": ROW_BYTES,
                    "h2d_bytes": 2 * ROW_BYTES, "d2h_bytes": ROW_BYTES,
                    "copies": 3, "kernel_launches": 1, "completion_waits": 1,
                    "exact_bytes": True, **self.ready,
                    **{name: .1 for name in ("gpu_kernel_event_ms", "load_hash_ms",
                                            "h2d_and_poison_ms", "enqueue_wait_host_ms",
                                            "readback_ms", "consumer_total_ms", "monotonic_start_ms")}}

    def test_write_envelope_and_fragmented_read_preserve_arbitrary_bytes(self):
        stream = io.BytesIO()
        handoff.write_frame(stream, self.meta, self.payload)
        self.assertEqual(stream.getvalue(), encoded_frame(self.meta, self.payload))
        # Consecutive frames exercise exact consumption without newline parsing.
        terminal = {"schema": SCHEMA, "kind": "closed"}
        framed = FragmentedStream(stream.getvalue() + encoded_frame(terminal))
        self.assertEqual(handoff.read_frame(framed), (self.meta, self.payload))
        self.assertEqual(handoff.read_frame(framed), (terminal, b""))
        self.assertEqual(framed.read(), b"")

    def test_truncated_frames_fail_at_every_boundary(self):
        frame = encoded_frame(self.meta, self.payload)
        header_end = len(frame) - ROW_BYTES
        for end in (0, 7, 8, 11, 12, 15, 16, header_end - 1, header_end,
                    header_end + 1, len(frame) - 1):
            with self.subTest(end=end), self.assertRaises((EOFError, ValueError)):
                handoff.read_frame(FragmentedStream(frame[:end]))

    def test_read_rejects_magic_and_unbounded_or_invalid_lengths(self):
        valid = encoded_frame(self.meta, self.payload)
        with self.assertRaises(ValueError):
            handoff.read_frame(io.BytesIO(b"BADMAGIC" + valid[8:]))
        for header_bytes, payload_bytes in ((0, 0), (4097, 0), (2**32 - 1, 0),
                                            (2, 1), (2, 5119), (2, 5121), (2, 2**32 - 1)):
            with self.subTest(header=header_bytes, payload=payload_bytes), self.assertRaises(ValueError):
                handoff.read_frame(io.BytesIO(MAGIC + struct.pack(">II", header_bytes, payload_bytes)))

    def test_read_rejects_invalid_header_and_write_rejects_invalid_sizes(self):
        for header in (b"\xff", b"{", b"[]", b"null",
                       json.dumps({"schema": "wrong", "kind": "row"}).encode(),
                       json.dumps({"schema": 2, "kind": "row"}).encode(),
                       json.dumps({"schema": SCHEMA}).encode()):
            frame = MAGIC + struct.pack(">II", len(header), 0) + header
            with self.subTest(header=header), self.assertRaises(ValueError):
                handoff.read_frame(io.BytesIO(frame))
        with self.assertRaises(ValueError):
            handoff.write_frame(io.BytesIO(), {**self.meta, "extra": "x" * 4096})
        for meta in ([], None, {"schema": 2, "kind": "row"}, {"schema": "wrong", "kind": "row"}):
            with self.subTest(meta=meta), self.assertRaises(ValueError):
                handoff.write_frame(io.BytesIO(), meta)
        for size in (1, 5119, 5121):
            with self.subTest(size=size), self.assertRaises(ValueError):
                handoff.write_frame(io.BytesIO(), self.meta, b"x" * size)

    def test_ack_binds_sequence_hash_model_birth_and_real_copy_counts(self):
        self.assertEqual(handoff.validate_pipe_ack(self.ack, self.payload, 0, self.payload,
                                                  self.ready, self.binding), self.ack)
        for key, wrong in (("schema", "wrong"), ("kind", "ready"), ("sequence", 1),
                           ("sequence", False), ("model_binding", "c" * 64),
                           ("model_binding", "B" * 64), ("transport", "staged-file"),
                           ("input_sha256", "a" * 64), ("output_sha256", "f" * 64),
                           ("input_bytes", 5119), ("output_bytes", 5119),
                           ("h2d_bytes", ROW_BYTES), ("d2h_bytes", 0), ("copies", 2),
                           ("native_pid", 8), ("native_starttime_ticks", 12),
                           ("passed", 1), ("exact_bytes", 1), ("kernel_launches", 0),
                           ("completion_waits", 0), ("gpu_kernel_event_ms", float("nan")),
                           ("h2d_and_poison_ms", -1)):
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                handoff.validate_pipe_ack({**self.ack, key: wrong}, self.payload, 0,
                                          self.payload, self.ready, self.binding)

    def test_ack_requires_exact_full_readback_and_input(self):
        for readback, payload in ((self.payload[:-1], self.payload),
                                  (b"\x00" * ROW_BYTES, self.payload),
                                  (self.payload, self.payload[:-1]),
                                  (self.payload, b"\x00" * ROW_BYTES)):
            with self.subTest(readback_bytes=len(readback), payload_bytes=len(payload)), self.assertRaises(ValueError):
                handoff.validate_pipe_ack(self.ack, readback, 0, payload, self.ready, self.binding)

    def test_diagnostic_failure_still_cancels_owned_consumer(self):
        consumer = handoff.Consumer.__new__(handoff.Consumer)
        consumer._flush_diagnostics = lambda: (_ for _ in ()).throw(OSError("log failed"))
        with patch.object(handoff.v1.Consumer, "abort", return_value=["base cleanup evidence"]) as cancelled:
            errors = consumer.abort()
        cancelled.assert_called_once_with()
        self.assertIn("log failed", errors[0])
        self.assertEqual(errors[1], "base cleanup evidence")

    def test_vm_root_attestation_uses_outer_pid_and_checks_birth_sha_and_cgroup(self):
        consumer = handoff.OwnedGpuContainer.__new__(handoff.OwnedGpuContainer)
        consumer.cid, consumer.name, consumer.identity, consumer.image_id = "c" * 64, "owned", "uuid", "image-id"
        consumer.args = SimpleNamespace(gpu_consumer_sha256="a" * 64)
        consumer.verify = lambda: {"State": {"Pid": 884, "Running": True}}
        raw = ("PID\t2264\nNSPID\t2264 884 1\nSTART\t11\nBOOT\tboot-id\nEXE\t/candidate/consumer\n"
               "SHA\t" + "a" * 64 + "  /proc/2264/exe\nCGROUP\t0::/docker/" + "c" * 64 + "|\n"
               "NAME\tconsumer\nTASK\t2264\t2264 884 1\t11\tconsumer\nSTART_AFTER\t11\n")
        starting = {"native_pid": 1, "native_starttime_ticks": 11}
        with patch.object(handoff.subprocess, "run", return_value=SimpleNamespace(stdout=raw)) as invoked:
            proof = consumer.attest_starting(starting)
        self.assertEqual(proof["initial_namespace_pid"], 2264)
        self.assertEqual(proof["docker_host_namespace_pid"], 884)
        self.assertEqual(proof["namespace_pids"], [2264, 884, 1])
        self.assertEqual(proof["linux_task_evidence"]["initial_namespace_tid"], 2264)
        self.assertEqual(invoked.call_args.args[0][:5], ["wsl.exe", "--system", "--user", "root", "--exec"])
        for bad in (raw.replace("2264 884 1", "2264 885 1"), raw.replace("START\t11", "START\t12"),
                    raw.replace("a" * 64, "b" * 64), raw.replace("c" * 64, "d" * 64),
                    raw.replace("START_AFTER\t11", "START_AFTER\t12")):
            with self.subTest(bad=bad), patch.object(handoff.subprocess, "run", return_value=SimpleNamespace(stdout=bad)):
                with self.assertRaises(ValueError):
                    consumer.attest_starting(starting)


if __name__ == "__main__":
    unittest.main()
