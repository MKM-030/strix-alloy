"""Offline identity binding tests; no runtime, BPF, container, or device calls."""
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
target = HERE / "halogen_npu_wsl_handoff_v3.py"
spec = importlib.util.spec_from_file_location("handoff_v3_test", target)
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


def starting():
    return {"native_pid": 1, "native_starttime_ticks": 11, "clock_ticks_per_second": 100,
            "kernel_identity": {"kernel_pid": 3000, "kernel_tgid": 3000,
                "namespace_pid": 1, "namespace_tid": 1, "proc_pid_namespace_inode": 4026533001,
                "native_starttime_ticks": 11, "boot_id": "a" * 8 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 12,
                "namespace_pids": [1], "scope": "own-socket-only", "probe_fds_closed": True,
                "persistent_kernel_attachment": False}}


def qualify_native_prehip(command):
    """Root supplies its owned CPU-only command prefix ending at the binary.

    Deliberately malformed init is sent before any file access, dlopen, or HIP.
    This launches no provider or GPU itself; root owns container qualification.
    """
    binding = "b" * 64
    stream = io.BytesIO()
    handoff.write_frame(stream, {"schema": handoff.PIPE_SCHEMA, "kind": "wrong-init", "model_binding": binding})
    args = ["/cpu-only-unused-engine", "/cpu-only-unused-code", "/cpu-only-unused-runtime", "0" * 64,
            "/cpu-only-unused-output", "--init-barrier", "--pipe-rows", binding]
    completed = subprocess.run([*command, *args], input=stream.getvalue(), capture_output=True, timeout=20)
    frames = io.BytesIO(completed.stdout)
    first, first_payload = handoff.read_frame(frames)
    terminal, terminal_payload = handoff.read_frame(frames)
    handoff.validate_kernel_identity(first)
    handoff.require_same_kernel_identity(terminal, first)
    if (completed.returncode != 1 or first.get("kind") != "starting" or
            first.get("GPU_context_not_yet_initialized") is not True or first_payload or terminal_payload or frames.read() or
            terminal.get("kind") != "closed" or terminal.get("passed") is not False or
            terminal.get("error") != "owned-GPU-init-release-required" or
            any(type(terminal.get(key)) is not int or terminal[key] != 0 for key in
                ("consumed_rows", "launches", "copies", "allocations", "frees", "module_loads", "module_unloads", "cleanup_errors"))):
        raise ValueError("CPU-only malformed-init must exit before GPU/file/runtime work with checked cleanup")
    return {"passed": True, "starting": first, "closed": terminal, "returncode": completed.returncode,
            "stderr": completed.stderr.decode("utf-8", errors="replace"), "GPU_calls": 0,
            "scope": "actual-native-malformed-init-before-file-access-dlopen-HIP"}


class KernelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.container = handoff.OwnedGpuContainer.__new__(handoff.OwnedGpuContainer)
        self.container.cid, self.container.name, self.container.identity, self.container.image_id = "c" * 64, "owned", "uuid", "image-id"
        self.container.args = SimpleNamespace(gpu_consumer_sha256="a" * 64)
        self.container.verify = lambda: {"State": {"Pid": 884, "Running": True}}
        self.raw = ("PID\t2264\nNSPID\t2264 884 1\nSTART\t11\nBOOT\t" + starting()["kernel_identity"]["boot_id"] +
            "\nEXE\t/candidate/consumer\nSHA\t" + "a" * 64 + "  /proc/2264/exe\nCGROUP\t0::/docker/" + "c" * 64 +
            "|\nNAME\tconsumer\nPID_NS_INODE\t4026533001\nTASK\t2264\t2264 884 1\t11\tconsumer\nSTART_AFTER\t11\n")

    def attest(self, value, raw=None):
        with patch.object(handoff.subprocess, "run", return_value=SimpleNamespace(stdout=raw or self.raw)):
            return self.container.attest_starting(value)

    def test_kernel_pid_is_source_of_etw_candidate_even_when_system_proc_omits_it(self):
        proof = self.attest(starting())
        self.assertEqual(proof["initial_namespace_pid"], 3000)
        self.assertEqual(proof["process_id_in_vm_candidate"], 3000)
        self.assertEqual(proof["system_proc_pid"], 2264)
        self.assertEqual(proof["system_proc_namespace_pids"], [2264, 884, 1])
        self.assertEqual(proof["linux_task_evidence"]["initial_namespace_tid"], 3000)

    def test_probe_and_proc_evidence_must_describe_same_lifetime_namespace_and_boot(self):
        for key, value in (("kernel_pid", 3001), ("kernel_tgid", True), ("probe_fds_closed", False),
                ("persistent_kernel_attachment", True), ("namespace_pid", 2),
                ("native_starttime_ticks", 12), ("namespace_pids", [2]),
                ("proc_pid_namespace_inode", 4026533002), ("boot_id", "b" * 36)):
            candidate = starting()
            candidate["kernel_identity"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.attest(candidate)

    def test_no_kernel_id_is_inferred_from_proc_chain(self):
        value = starting()
        del value["kernel_identity"]
        with self.assertRaises(ValueError):
            self.attest(value)


if __name__ == "__main__":
    unittest.main()
