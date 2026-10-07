"""Focused offline guards for the isolated stock-controller overlay."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("halogen_serving_kernel_service_wrapper.py")
spec = importlib.util.spec_from_file_location("service_overlay", SOURCE)
wrapper = importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)


class OverlayTest(unittest.TestCase):
    def setUp(self):
        self.adapter, self.api = wrapper.modules()
        self.argv = ["--checkpoint", "v2", "--context-size", "129024", "--serve-seconds", "30"]
        self.cid = "1" * 64
        self.plan = dict(nonce="2" * 32, policy_directory="/home/revn/halogen-re/serving-kernel-service-" + "2" * 32,
                         helper=dict(linux_path="/home/revn/halogen-re/helper.so", sha256="3" * 64, bytes=20800),
                         baseline=dict(sha256="4" * 64), source_sha256={key: "5" * 64 for key in wrapper.SOURCE_PATHS})
        self.manifest = dict(image=wrapper.IMAGE, run_id="6" * 32, entrypoint_sha256="7" * 64,
                             mounts={"/candidate/test": "/owned/test"},
                             environment=dict(HALOGEN_CHECKPOINT="/models/qwen38-flash-next-v2.hgn", HALOGEN_CHECKPOINT_VARIANT="v2",
                                              HALOGEN_KV_SLOTS="1", HALOGEN_CTX="129024", HALOGEN_KV_POOL_POSITIONS="129024"))
        self.info = dict(Id=self.cid, State=dict(Running=False),
                         Config=dict(Image=wrapper.IMAGE, Env=[key + "=" + value for key, value in self.manifest["environment"].items()]),
                         HostConfig=dict(CapAdd=["SYS_PTRACE", "BPF"], CapDrop=None, Privileged=False,
                                         CgroupnsMode="host", SecurityOpt=["seccomp=unconfined"]),
                         Mounts=[dict(Destination="/candidate/test", Source="/owned/test", RW=False, Type="bind")])
        self.events = []
        self.service = SimpleNamespace(build_manifest=lambda *args: self.manifest, command=lambda *args: [],
                                       owned=lambda *args: self.events.append("owned"), atomic=lambda *args: self.events.append("seal-record"),
                                       r=SimpleNamespace(docker=lambda *args, **kwargs: self.cid,
                                                         inspect=lambda cid: copy.deepcopy(self.info)))

    def overlay(self):
        value = wrapper.Overlay(self.service, self.adapter, self.api, self.plan, "8" * 64, self.argv)
        value.manifest = self.manifest
        value.inputs = lambda: self.events.append("input-pins")
        value.linux = lambda action, **kwargs: self.events.append(action)
        return value

    def test_default_off_stops_before_import_or_runtime(self):
        with patch.object(wrapper, "modules", side_effect=AssertionError("Runtime touched")), self.assertRaises(ValueError):
            wrapper.run(Path("unused"), "0" * 64, self.argv)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.txt"; raw = b"exact\r\nbytes\r\n"; path.write_bytes(raw)
            with wrapper.local_pin(self.api, path, hashlib.sha256(raw).hexdigest(), 64) as fd:
                self.assertEqual(wrapper.os.read(fd, 64), raw)

    def test_wrong_created_identity_capabilities_mounts_or_environment_are_rejected(self):
        value = self.overlay(); value.check_created(self.cid)
        changes = (lambda info: info.update(Id="9" * 64),
                   lambda info: info["HostConfig"].update(CapAdd=["SYS_PTRACE", "BPF", "SYS_ADMIN"]),
                   lambda info: info["Mounts"][0].update(RW=True),
                   lambda info: info["Config"].update(Env=[]))
        original = copy.deepcopy(self.info)
        for change in changes:
            self.info = copy.deepcopy(original); change(self.info)
            with self.assertRaises(ValueError): value.check_created(self.cid)

    def test_create_checks_identity_before_policy_sealing(self):
        value = self.overlay()
        with tempfile.TemporaryDirectory() as directory:
            value.attempt = Path(directory); (value.attempt / "manifest.json").write_text(json.dumps(self.manifest))
            self.info["HostConfig"]["CapAdd"].append("SYS_ADMIN")
            with self.assertRaises(ValueError): value.docker("create")
        self.assertNotIn("seal", self.events); self.assertIsNone(value.cid)

    def test_sealed_policy_binds_full_cid_manifest_and_expected_argv_before_start(self):
        value = self.overlay()
        with tempfile.TemporaryDirectory() as directory:
            value.attempt = Path(directory); (value.attempt / "manifest.json").write_text(json.dumps(self.manifest))
            cid = value.docker("create")
        self.assertEqual(cid, self.cid); self.assertLess(self.events.index("owned"), self.events.index("seal"))
        self.assertIsNotNone(value.policy_sha)
        policy = value.policy(self.cid, "9" * 64)
        self.assertEqual(policy["container_id"], self.cid); self.assertEqual(policy["manifest_sha256"], "9" * 64)
        self.assertEqual(policy["baseline_receipt_sha256"], self.plan["baseline"]["sha256"])
        self.assertEqual(policy["argv_sha256"], self.api.digest_json(wrapper.expected_argv(self.api, self.manifest)))
        small = copy.deepcopy(self.manifest)
        small["environment"].update(HALOGEN_CTX="4096", HALOGEN_KV_POOL_POSITIONS="4096")
        self.assertEqual(wrapper.expected_argv(self.api, small)[12], "4096")
        with self.assertRaises(ValueError): value.docker("start", "0" * 64)
        value.docker("start", self.cid)
        self.assertIn("verify-sealed", self.events)


if __name__ == "__main__": unittest.main()
