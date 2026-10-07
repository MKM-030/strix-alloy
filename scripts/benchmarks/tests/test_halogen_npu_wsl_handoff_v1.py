"""Offline staged-publication and GPU-ack checks. No provider/GPU imports."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "halogen_npu_wsl_handoff_v1.py"
spec = importlib.util.spec_from_file_location("handoff_contract", SOURCE)
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = b"\x80\x3f" * 2560
        self.ready = {"native_pid": 7, "native_starttime_ticks": 11}
        sha = hashlib.sha256(self.payload).hexdigest()
        self.ack = {"kind": "row", "sequence": 0, "passed": True, "input_sha256": sha,
                    "output_sha256": sha, "input_bytes": 5120, "output_bytes": 5120,
                    "h2d_bytes": 10240, "d2h_bytes": 5120, "copies": 3, "kernel_launches": 1,
                    "completion_waits": 1, "exact_bytes": True, "output_file": "row-000-gpu.u16",
                    **self.ready, **{k: .1 for k in ("gpu_kernel_event_ms", "load_hash_ms", "h2d_and_poison_ms",
                                                  "enqueue_wait_host_ms", "readback_ms", "consumer_total_ms", "monotonic_start_ms")}}

    def test_ack_binds_exact_bytes_sequence_identity_and_actual_copies(self):
        self.assertEqual(handoff.validate_ack(self.ack, 0, self.payload, self.ready), self.ack)
        for key, wrong in (("sequence", 1), ("output_sha256", "f" * 64), ("input_sha256", "a" * 64),
                           ("copies", 2), ("native_starttime_ticks", 12), ("native_pid", 8),
                           ("passed", 1), ("kernel_launches", 0), ("completion_waits", 0),
                           ("gpu_kernel_event_ms", float("nan")), ("h2d_and_poison_ms", -1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                handoff.validate_ack(dict(self.ack, **{key: wrong}), 0, self.payload, self.ready)
        with self.assertRaises(ValueError):
            handoff.validate_ack(self.ack, 0, self.payload[:-2], self.ready)
        with self.assertRaises(ValueError):
            handoff.validate_ack(self.ack, 0, b"\x00\x00" * 2560, self.ready)

    def test_publication_preserves_bytes_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "row.u16"
            facts = handoff.publish_bytes(path, self.payload)
            self.assertEqual(path.read_bytes(), self.payload)
            self.assertEqual(facts["sha256"], hashlib.sha256(self.payload).hexdigest())
            self.assertTrue(facts["fsync_completed_before_rename"])
            self.assertFalse(path.with_name(path.name + ".partial").exists())
            with self.assertRaises(FileExistsError):
                handoff.publish_bytes(path, b"replacement")
            self.assertEqual(path.read_bytes(), self.payload)

    def test_drive_path_requires_an_explicit_windows_volume(self):
        self.assertEqual(handoff.wsl_path(r"C:\Projects\handoff run"), "/mnt/c/Projects/handoff run")
        for value in ("relative/path", r"\Projects\handoff", r"\\server\share\handoff"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                handoff.wsl_path(value)

    def test_container_stop_identity_rejects_foreign_name_label_image_and_entrypoint(self):
        info = {"Id": "a" * 64, "Name": "/hgn-owned", "Image": "sha256:abc",
                "Config": {"Image": handoff.GPU_IMAGE, "Labels": {"strix-alloy.npu-wsl-handoff": "owned-uuid"},
                           "Entrypoint": ["/candidate/consumer"]}}
        self.assertEqual(handoff.validate_container(info, "a" * 64, "hgn-owned", "owned-uuid", "sha256:abc"), info)
        for replacement in ({"Name": "/foreign"}, {"Id": "b" * 64}, {"Image": "sha256:other"},
                            {"Config": {**info["Config"], "Labels": {"strix-alloy.npu-wsl-handoff": "foreign"}}},
                            {"Config": {**info["Config"], "Entrypoint": ["/bin/sh"]}}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                handoff.validate_container({**info, **replacement}, "a" * 64, "hgn-owned", "owned-uuid", "sha256:abc")

    def test_rows_barriers_bind_producer_pid_preserve_context_and_bound_release(self):
        args = SimpleNamespace(gpu_rows_barrier=True, barrier_timeout_s=1)
        consumer = SimpleNamespace(ready=self.ready, process=SimpleNamespace(poll=lambda: None),
                                   container=SimpleNamespace(cid="a" * 64),
                                   container_starting={"initial_namespace_pid": 99})
        guard = SimpleNamespace(check=lambda: None)
        for completed, release_name, marker_name in (
                (False, "gpu-rows-release.json", "gpu-rows-ready.json"),
                (True, "gpu-cleanup-release.json", "gpu-rows-complete.json")):
            with self.subTest(completed=completed), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                handoff.publish_json(directory / release_name,
                                     {"schema": handoff.SCHEMA, "windows_pid": handoff.os.getpid(), "release": True})
                marker = handoff.wait_gpu_rows_release(args, directory, consumer, guard, completed)
                self.assertEqual(marker["rows_completed"], handoff.ROWS if completed else 0)
                self.assertTrue(marker["GPU_context_live"])
                self.assertEqual(marker["initial_namespace_pid"], 99)
                self.assertEqual(marker["container_id"], "a" * 64)
                self.assertGreaterEqual(marker["barrier_wait_ms"], 0)
                self.assertTrue((directory / marker_name).is_file())
        for release in ({"schema": "wrong", "windows_pid": handoff.os.getpid(), "release": True},
                        {"schema": handoff.SCHEMA, "windows_pid": handoff.os.getpid()+1, "release": True},
                        {"schema": handoff.SCHEMA, "windows_pid": handoff.os.getpid(), "release": 1}):
            with self.subTest(release=release), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                handoff.publish_json(directory / "gpu-rows-release.json", release)
                with self.assertRaises(ValueError):
                    handoff.wait_gpu_rows_release(args, directory, consumer, guard)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "gpu-rows-release.json").write_bytes(b" " * 4097)
            with self.assertRaises(ValueError):
                handoff.wait_gpu_rows_release(args, directory, consumer, guard)
        with tempfile.TemporaryDirectory() as directory, patch.object(handoff.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaises(TimeoutError):
                handoff.wait_gpu_rows_release(args, Path(directory), consumer, guard)
        with tempfile.TemporaryDirectory() as directory:
            consumer.process = SimpleNamespace(poll=lambda: 1)
            with self.assertRaises(RuntimeError):
                handoff.wait_gpu_rows_release(args, Path(directory), consumer, guard)
        with tempfile.TemporaryDirectory() as directory:
            marker = handoff.wait_gpu_rows_release(SimpleNamespace(gpu_rows_barrier=False, barrier_timeout_s=1),
                                                  Path(directory), consumer, guard)
            self.assertEqual(marker["barrier_wait_ms"], 0)


if __name__ == "__main__":
    unittest.main()
