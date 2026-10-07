"""Offline validation of isolated entrypoint rendering and final hash binding."""
import importlib.util
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

TARGET = Path(__file__).with_name("halogen_serving_kernel_adapter.py")
ROOT = Path(__file__).resolve().parents[2]


class AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if TARGET.exists():
            spec = importlib.util.spec_from_file_location("kernel_adapter", TARGET)
            cls.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.module)

    def setUp(self):
        self.assertIsNotNone(self.module, "Adapter is not implemented")
        self.m = self.module
        self.source = (ROOT / "backends/halogen-wsl2-0.16.2/.local/entrypoint-wsl.sh").read_bytes()
        self.service = (ROOT / "backends/halogen-wsl2-0.16.2/scripts/service.py").read_bytes()

    def test_default_render_is_exact_existing_authenticated_service(self):
        result = self.m.render(self.source, self.service)
        self.assertEqual(result, self.source.replace(self.m.API_NEEDLE, self.m.AUTH_API))
        self.assertNotIn(b"halogen_serving_kernel_adapter", result)
        self.assertEqual(result.count(self.m.AUTH_API), 5)

    def test_active_render_wraps_only_all_engine_boundary(self):
        result = self.m.render(self.source, self.service, activate=True)
        self.assertEqual(result.count(self.m.ADAPTER_COMMAND), 1)
        self.assertEqual(result.count(self.m.AUTH_API), 5)
        self.assertIn(self.m.WRAPPED_LAUNCH + b"  ENGINE_PID=$!\n", result)
        authenticated = self.source.replace(self.m.API_NEEDLE, self.m.AUTH_API)
        reverted = result.replace(self.m.NPU_GUARD, b"").replace(self.m.WRAPPED_LAUNCH, self.m.ENGINE_LAUNCH)
        self.assertEqual(reverted, authenticated)
        with self.assertRaises(ValueError): self.m.render(self.source + b"\n", self.service, activate=True)
        with self.assertRaises(ValueError): self.m.render(self.source, self.service + b"\n", activate=True)
        command = ["create", "--cap-add=SYS_PTRACE", "--security-opt=seccomp=unconfined", "--entrypoint", "python3", "pinned-image"]
        self.assertEqual(self.m.isolate_command(command), command)
        self.assertEqual(self.m.isolate_command(command, activate=True), command[:2] + ["--cap-add=BPF", "--cgroupns=host"] + command[2:])
        with self.assertRaises(ValueError): self.m.isolate_command(command + ["--cap-add=SYS_ADMIN"], activate=True)

    def test_plan_binds_final_environment_without_plaintext_credentials(self):
        api = self.m.bootstrap()
        argv = [api.ENGINE, "--ck", "/models/qwen38-flash-next-v2.hgn", "--port", "8730", "--bind", "127.0.0.1",
                "--slots", "1", "--ctx", "129024", "--max-tok", "32768", "--kv-pool", "129024"]
        env = dict(API_TOKEN="synthetic-secret-marker", HALOGEN_CHECKPOINT_VARIANT="v2", LD_PRELOAD="/candidate/original.so")
        policy = {key: "1" * 64 for key in ("manifest_sha256", "bootstrap_sha256", "native_source_sha256", "native_helper_sha256")}
        policy.update(nonce="2" * 32, service_run_id="3" * 32, container_id="4" * 64,
                      native_helper_path="/candidate/halogen_serving_kernel_identity.so", native_helper_bytes=32768,
                      frozen_header_sha256=api.FROZEN_HEADER_SHA256, argv_sha256=api.digest_json(argv))
        masks = dict(effective=(1 << 8) | (1 << 19), permitted=(1 << 8) | (1 << 19), inheritable=0,
                     bounding=(1 << 8) | (1 << 19), ambient=0)
        capability = self.m.capability_policy(api, masks)
        plan = self.m.derive_launch_plan(api, policy, argv, env, capability)
        self.assertEqual(plan["environment_sha256"], api.digest_json(env))
        self.assertNotIn("synthetic-secret-marker", str(plan))
        self.assertNotIn("environment", plan)
        bad = dict(masks, effective=1 << 8)
        with self.assertRaises(ValueError): self.m.capability_policy(api, bad)
        with self.assertRaises(ValueError): self.m.derive_launch_plan(api, policy, argv, dict(env, HALOGEN_NPU_MODELS="configured"), capability)

    def test_runtime_delegates_fresh_hash_only_plan_and_requires_activation(self):
        api = self.m.bootstrap()
        with patch.object(self.m, "bootstrap", side_effect=AssertionError("Runtime touched")), self.assertRaises(ValueError):
            self.m.engine(Path("unused"), "1" * 64, [], activate=False)
        argv = [api.ENGINE, "--ck", "/models/qwen38-flash-next-v2.hgn", "--port", "8730", "--bind", "127.0.0.1",
                "--slots", "1", "--ctx", "129024", "--max-tok", "32768", "--kv-pool", "129024"]
        policy = {key: "1" * 64 for key in ("manifest_sha256", "bootstrap_sha256", "native_source_sha256", "native_helper_sha256",
                                           "adapter_sha256", "candidate_entrypoint_sha256", "service_sha256", "baseline_receipt_sha256")}
        policy.update(nonce="2" * 32, service_run_id="3" * 32, container_id="4" * 64,
                      native_helper_path="/candidate/halogen_serving_kernel_identity.so", native_helper_bytes=32768,
                      frozen_header_sha256=api.FROZEN_HEADER_SHA256, argv_sha256=api.digest_json(argv))
        masks = dict(effective=(1 << 8) | (1 << 19), permitted=(1 << 8) | (1 << 19), inheritable=0,
                     bounding=(1 << 8) | (1 << 19), ambient=0)
        published = []
        @contextmanager
        def verified(*args, **kwargs): yield 73
        env = dict(HALOGEN_CHECKPOINT_VARIANT="v2", API_TOKEN="synthetic-secret-marker", _="/usr/local/bin/python3")
        with (patch.object(self.m, "bootstrap", return_value=api), patch.object(api, "_require_linux"),
              patch.object(self.m, "load_policy", return_value=policy),
              patch.object(self.m, "read_baseline", return_value=self.m.capability_policy(api, masks)),
              patch.object(api, "_verified_fd", side_effect=verified), patch.object(api, "_require_fresh_receipt"),
              patch.object(api, "_publish_fresh", side_effect=lambda path, value: published.append((path, value))),
              patch.object(api.os, "environ", env), patch.object(api, "launch") as launch):
            self.m.engine(Path(self.m.POLICY_PATH), "5" * 64, argv, activate=True)
        self.assertEqual(len(published), 2)
        payload = json.dumps(published[0][1], sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        launch.assert_called_once_with(published[0][0], hashlib.sha256(payload).hexdigest(), argv, activate=True)
        self.assertNotIn("synthetic-secret-marker", str(published))
        self.assertFalse(published[1][1]["ancestor_bpf_removal_claimed"])
        self.assertEqual(env["_"], api.ENGINE)
        self.assertEqual(published[0][1]["environment_sha256"], api.digest_json(env))


if __name__ == "__main__": unittest.main()
