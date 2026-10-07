"""Offline serving bootstrap checks; native/proc/exec boundaries are simulated."""
import copy
from contextlib import contextmanager
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TARGET = Path(__file__).with_name("halogen_serving_kernel_bootstrap.py")


class BootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if TARGET.exists():
            spec = importlib.util.spec_from_file_location("serving_bootstrap", TARGET)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertIsNotNone(self.module, "Standalone serving bootstrap is not implemented")
        self.m = self.module
        self.argv = [self.m.ENGINE, "--ck", "/models/qwen38-flash-next-v2.hgn",
                     "--port", "8730", "--bind", "127.0.0.1", "--slots", "1",
                     "--ctx", "262144", "--max-tok", "32768", "--kv-pool", "262144"]
        self.env = {"LD_PRELOAD": "/candidate/original.so", "API_KEY": "test-private-secret"}
        baseline = dict(effective=1 << 8, permitted=1 << 8, inheritable=0,
                        bounding=1 << 8, ambient=0)
        before = {key: value | (self.m.BPF_MASK if key in {"effective", "permitted", "bounding"} else 0)
                  for key, value in baseline.items()}
        self.plan = dict(schema=self.m.PLAN_SCHEMA, enabled=True, nonce="1" * 32,
                         service_run_id="2" * 32, container_id="3" * 64,
                         manifest_sha256="4" * 64, bootstrap_sha256="5" * 64,
                         native_source_sha256="6" * 64, frozen_header_sha256=self.m.FROZEN_HEADER_SHA256,
                         native_helper_path="/candidate/serving-kernel-identity.so",
                         native_helper_sha256="7" * 64, native_helper_bytes=32768,
                         engine_sha256=self.m.ENGINE_SHA256, engine_bytes=self.m.ENGINE_BYTES,
                         argv_sha256=self.m.digest_json(self.argv), environment_sha256=self.m.digest_json(self.env),
                         capability_policy=dict(only_added="CAP_BPF", baseline_masks=baseline,
                                                expected_before_masks=before))
        self.snapshot = dict(pid=1, uid=0, start_ticks=4549,
                             boot_id="06019efd-ff1b-4b8d-8c9f-24401e543bfd",
                             namespace_inode=4026532233, namespace_pids=[1], task_count=1,
                             capabilities=before, container_id=self.plan["container_id"])
        self.native = dict(abi_version=1, struct_bytes=self.m.NATIVE_STRUCT_BYTES,
                           kernel_pid=2302, kernel_tgid=2302, namespace_pid=1, namespace_tid=1,
                           proc_pid_namespace_inode=4026532233, capability_count=41,
                           probe_fds_closed=1, capability_drop_checked=1,
                           failure_stage=0, probe_errno=0, drop_errno=0,
                           before=before, after=baseline)

    def test_default_off_stops_before_any_runtime_boundary(self):
        with patch.object(self.m, "_require_linux", side_effect=AssertionError("runtime touched")):
            with self.assertRaisesRegex(ValueError, "explicit activation"):
                self.m.launch(Path("unused"), "0" * 64, self.argv, activate=False)

    def test_disabled_plan_and_credential_fields_are_rejected(self):
        bad = copy.deepcopy(self.plan)
        bad["enabled"] = False
        with self.assertRaises(ValueError): self.m.validate_plan(bad)
        for key in ("argv", "environment", "api_key"):
            bad = dict(self.plan, **{key: "test-private-secret"})
            with self.subTest(key=key), self.assertRaises(ValueError): self.m.validate_plan(bad)

    def test_changed_engine_and_added_non_bpf_capability_are_rejected(self):
        bad = dict(self.plan, engine_sha256="f" * 64)
        with self.assertRaises(ValueError): self.m.validate_plan(bad)
        bad = copy.deepcopy(self.plan)
        bad["capability_policy"]["expected_before_masks"]["effective"] |= 1 << 21
        with self.assertRaises(ValueError): self.m.validate_plan(bad)

    def test_native_result_rejects_open_probe_or_incomplete_capability_removal(self):
        self.m.validate_native(self.native, self.plan, self.snapshot)
        for field, value in (("probe_fds_closed", 0), ("capability_drop_checked", 0),
                             ("kernel_tgid", 2303), ("namespace_tid", 2), ("failure_stage", 6)):
            bad = copy.deepcopy(self.native); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.m.validate_native(bad, self.plan, self.snapshot)
        bad = copy.deepcopy(self.native); bad["after"]["effective"] |= self.m.BPF_MASK
        with self.assertRaises(ValueError): self.m.validate_native(bad, self.plan, self.snapshot)
        bad = copy.deepcopy(self.native); bad["after"]["permitted"] = 0
        with self.assertRaises(ValueError): self.m.validate_native(bad, self.plan, self.snapshot)

    def test_fresh_receipt_never_overwrites_an_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            self.m._publish_fresh(path, {"nonce": "1" * 32})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError): self.m._publish_fresh(path, {"nonce": "2" * 32})
            self.assertEqual(path.read_bytes(), original)

    def test_file_hash_check_tolerates_access_time_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pinned.bin"; path.write_bytes(b"pinned")
            first = os.stat(path)
            later = SimpleNamespace(**{key: getattr(first, key) for key in dir(first) if key.startswith("st_")})
            later.st_atime += 5
            later.st_atime_ns += 5_000_000_000
            with patch.object(self.m.os, "fstat", side_effect=[first, later]):
                try:
                    with self.m._verified_fd(path, hashlib.sha256(b"pinned").hexdigest(), 64) as fd:
                        self.assertEqual(os.read(fd, 64), b"pinned")
                except ValueError:
                    self.fail("Access time alone must not invalidate a content pin")

    def test_held_file_content_is_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pinned.bin"; path.write_bytes(b"pinned")
            digest = hashlib.sha256(b"pinned").hexdigest()
            with self.m._verified_fd(path, digest, 64) as fd:
                path.write_bytes(b"mutate")
                with self.assertRaises(ValueError): self.m._check_fd(fd, digest, 64)

    def test_proc_reads_are_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proc-field"; path.write_bytes(b"12345")
            self.assertEqual(self.m._read_proc(path, 5), b"12345")
            with self.assertRaises(ValueError): self.m._read_proc(path, 4)

    def test_container_binding_requires_the_complete_id_in_self_view(self):
        cid = self.plan["container_id"]
        self.assertTrue(self.m._in_container({"cgroup": "0::/docker/" + cid + "\n"}, cid))
        self.assertTrue(self.m._in_container({"cgroup": "0::/system.slice/docker-" + cid + ".scope\n"}, cid))
        self.assertFalse(self.m._in_container({"cgroup": "0::/\n"}, cid))
        self.assertFalse(self.m._in_container({"cgroup": "0::/docker/" + cid + "a\n"}, cid))

    def launch_boundaries(self, snapshots):
        events = []
        @contextmanager
        def verified(path, *args, **kwargs):
            events.append("file"); yield 73
        def observe(*args): events.append("probe"); return copy.deepcopy(self.native)
        def publish(path, receipt): events.append("publish"); self.published = receipt
        def execute(fd, argv, env):
            events.append("exec")
            self.assertEqual(fd, 73); self.assertEqual(argv, self.argv); self.assertEqual(env, self.env)
            raise OSError("simulated exec failure")
        return events, [patch.object(self.m, "_require_linux"),
                        patch.object(self.m, "load_plan", return_value=self.plan),
                        patch.object(self.m, "_snapshot", side_effect=snapshots),
                        patch.object(self.m, "_verified_fd", side_effect=verified),
                        patch.object(self.m, "_check_fd"),
                        patch.object(self.m, "_require_fresh_receipt"),
                        patch.object(self.m, "_observe_native", side_effect=observe),
                        patch.object(self.m, "_publish_fresh", side_effect=publish),
                        patch.object(self.m.os, "environ", self.env),
                        patch.object(self.m.os, "execve", side_effect=execute)]

    def run_launch(self, snapshots):
        from contextlib import ExitStack
        events, patches = self.launch_boundaries(snapshots)
        with ExitStack() as stack:
            for item in patches: stack.enter_context(item)
            with self.assertRaises((OSError, ValueError)):
                self.m.launch(Path("unused"), "0" * 64, self.argv, activate=True)
        return events

    def test_receipt_binding_hides_argv_and_environment(self):
        after = dict(self.snapshot, capabilities=self.plan["capability_policy"]["baseline_masks"])
        events = self.run_launch([self.snapshot, after, after])
        self.assertLess(events.index("probe"), events.index("publish"))
        self.assertLess(events.index("publish"), events.index("exec"))
        payload = json.dumps(self.published)
        self.assertNotIn("test-private-secret", payload)
        self.assertNotIn("LD_PRELOAD", payload)
        self.assertNotIn("argv", self.published)
        self.assertNotIn("environment", self.published)
        self.assertEqual(self.published["argv_sha256"], self.plan["argv_sha256"])
        self.assertEqual(self.published["kernel_identity"]["kernel_pid"], 2302)

    def test_stale_nonce_fails_before_native_call(self):
        from contextlib import ExitStack
        events, patches = self.launch_boundaries([self.snapshot])
        with ExitStack() as stack:
            for item in patches: stack.enter_context(item)
            stack.enter_context(patch.object(self.m, "_require_fresh_receipt", side_effect=FileExistsError))
            with self.assertRaises(FileExistsError):
                self.m.launch(Path("unused"), "0" * 64, self.argv, activate=True)
        self.assertNotIn("probe", events); self.assertNotIn("publish", events); self.assertNotIn("exec", events)

    def inspect_boundaries(self, current=None, *, argv=None, pin_error=False, image_changes=False, argv_changes=False):
        from contextlib import ExitStack
        after = dict(self.snapshot, capabilities=self.plan["capability_policy"]["baseline_masks"])
        self.run_launch([self.snapshot, after, after])
        receipt = copy.deepcopy(self.published)
        raw = json.dumps(receipt).encode()
        pin_checks = 0
        @contextmanager
        def verified(*args, **kwargs):
            nonlocal pin_checks
            pin_checks += 1
            if pin_error or image_changes and pin_checks == 2: raise ValueError("Wrong executable pin")
            yield 73
        commands = [b"\0".join(item.encode() for item in (argv or self.argv)) + b"\0"] * 2
        if argv_changes:
            changed = list(self.argv); changed[4] = "8731"
            commands[1] = b"\0".join(item.encode() for item in changed) + b"\0"
        with ExitStack() as stack:
            for item in (patch.object(self.m, "_require_linux"),
                         patch.object(self.m, "load_plan", return_value=self.plan),
                         patch.object(self.m, "_read_receipt", return_value=(receipt, raw, 0)),
                         patch.object(self.m, "_snapshot", side_effect=[current or after, current or after]),
                         patch.object(self.m, "_read_proc", side_effect=commands),
                         patch.object(self.m, "_verified_fd", side_effect=verified)):
                stack.enter_context(item)
            return self.m.inspect(Path("unused"), "0" * 64)

    def test_inspect_rejects_stale_birth_altered_argv_exe_or_capabilities(self):
        result = self.inspect_boundaries()
        self.assertTrue(result["post_exec_verified"])
        self.assertFalse(result["qualifications"])
        self.assertNotIn("test-private-secret", json.dumps(result))
        for field, value in (("start_ticks", 4550), ("boot_id", "other-boot"), ("namespace_inode", 7)):
            after = dict(self.snapshot, capabilities=self.plan["capability_policy"]["baseline_masks"], **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError): self.inspect_boundaries(after)
        after = copy.deepcopy(self.snapshot)
        with self.assertRaises(ValueError): self.inspect_boundaries(after)
        after = dict(self.snapshot, capabilities=dict(self.plan["capability_policy"]["baseline_masks"]))
        after["capabilities"]["effective"] |= 1 << 21
        with self.assertRaises(ValueError): self.inspect_boundaries(after)
        changed = list(self.argv); changed[4] = "8731"
        with self.assertRaises(ValueError): self.inspect_boundaries(argv=changed)
        with self.assertRaises(ValueError): self.inspect_boundaries(pin_error=True)

    def test_inspect_rejects_same_birth_image_or_argv_change(self):
        with self.assertRaises(ValueError): self.inspect_boundaries(image_changes=True)
        with self.assertRaises(ValueError): self.inspect_boundaries(argv_changes=True)

    def test_changed_held_engine_prevents_exec(self):
        from contextlib import ExitStack
        after = dict(self.snapshot, capabilities=self.plan["capability_policy"]["baseline_masks"])
        events, patches = self.launch_boundaries([self.snapshot, after, after])
        def recheck(fd, digest, *args, **kwargs):
            if digest == self.m.ENGINE_SHA256: raise ValueError("Engine bytes changed")
        with ExitStack() as stack:
            for item in patches: stack.enter_context(item)
            stack.enter_context(patch.object(self.m, "_check_fd", side_effect=recheck))
            with self.assertRaises(ValueError): self.m.launch(Path("unused"), "0" * 64, self.argv, activate=True)
        self.assertIn("probe", events); self.assertNotIn("exec", events)

    def test_changed_birth_or_extra_thread_prevents_publish_and_exec(self):
        for field, value in (("start_ticks", 4550), ("boot_id", "other-boot"), ("task_count", 2),
                             ("namespace_inode", 7)):
            after = dict(self.snapshot, capabilities=self.plan["capability_policy"]["baseline_masks"])
            after[field] = value
            with self.subTest(field=field):
                events = self.run_launch([self.snapshot, after])
                self.assertNotIn("publish", events); self.assertNotIn("exec", events)

    def test_changed_arg_or_environment_hash_prevents_native_call(self):
        for key in ("argv_sha256", "environment_sha256"):
            original = self.plan[key]; self.plan[key] = "f" * 64
            with self.subTest(key=key):
                events = self.run_launch([self.snapshot])
                self.assertNotIn("probe", events); self.assertNotIn("exec", events)
            self.plan[key] = original


if __name__ == "__main__":
    unittest.main()
