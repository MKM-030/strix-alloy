"""Portable 0.20.0 profile and command forwarding with synthetic metadata."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "server"))
import controller
import manage

BACKEND = REPO / "backends/halogen-wsl2-0.20.0"


class Halogen0200Forwarding(unittest.TestCase):
    def engine(self):
        return dict(kind="halogen", directory="backends/halogen-wsl2-0.20.0",
            checkpoint="v2", context=32768, prompt_cache="Off", launcher="python",
            python_executable=sys.executable, powershell="powershell.exe",
            prefill_chunk=2048, max_prefill_tokens=2048, disable_vision=True,
            kernel_controls={"HALOGEN_DECODE_PREFETCH": 0},
            speculation_policy={"HALOGEN_PLD": "3,3", "HALOGEN_MTP_GATE_P": "0.90"},
            api_defaults={"enable_thinking": False, "reasoning_effort": "low",
                          "max_thinking_tokens": 2048})

    def test_normal_controller_forwards_single_slot_and_two_slot_text_controls(self):
        for capacity, prefill in (({}, 2048), ({}, 8192),
                                  (dict(slots=2, kv_pool_positions=65536), 2048)):
            with self.subTest(capacity=capacity, prefill=prefill):
                engine = self.engine()
                engine.update(capacity, prefill_chunk=prefill, max_prefill_tokens=prefill)
                directory = controller.validate_engine(engine, REPO)
                argv = controller.halogen_launch_command(engine, directory)
                self.assertEqual(directory, BACKEND)
                self.assertEqual(Path(argv[0]), Path(sys.executable))
                self.assertEqual(Path(argv[3]), BACKEND / "scripts/service.py")
                self.assertIn("--disable-vision", argv)
                for flag, value in (("--prefill-chunk", str(prefill)),
                                    ("--max-prefill-tokens", str(prefill)),
                                    ("--context-size", "32768"), ("--prompt-cache", "Off")):
                    self.assertEqual(argv[argv.index(flag) + 1], value)
                for key, flag in (("speculation_policy", "--speculation-policy-json"),
                                  ("api_defaults", "--api-defaults-json"),
                                  ("kernel_controls", "--kernel-controls-json")):
                    self.assertEqual(json.loads(argv[argv.index(flag) + 1]), engine[key])
                self.assertNotIn("--draft-tokens", argv)
                if capacity:
                    self.assertEqual(argv[argv.index("--slots") + 1], "2")
                    self.assertEqual(argv[argv.index("--kv-pool-positions") + 1], "65536")
                else:
                    self.assertNotIn("--slots", argv)
                    self.assertNotIn("--kv-pool-positions", argv)

    def test_synthetic_profile_generation_preserves_defaults_and_both_capacity_versions(self):
        with tempfile.TemporaryDirectory(prefix="alloy0200-profile-cpu-") as folder:
            repo = Path(folder)
            for version in ("0.18.22", "0.19.1", "0.20.0"):
                package = repo / ("backends/halogen-wsl2-" + version)
                (package / ".local").mkdir(parents=True)
                (package / "profiles").mkdir()
                (package / "scripts").mkdir()
                shutil.copy2(REPO / ("backends/halogen-wsl2-" + version) / "scripts/capacity_policy.py",
                             package / "scripts/capacity_policy.py")
                release = dict(version=version, image="synthetic-image-" + version)
                (package / "profiles/release.json").write_text(json.dumps(release), encoding="utf-8")
                (package / ".local/machine.json").write_text(json.dumps(dict(release, pwsh="powershell.exe")), encoding="utf-8")
                (package / ".local/api-token.txt").write_text("synthetic-private-token", encoding="utf-8")
            with patch.object(manage, "REPO", repo), patch.object(controller, "ROOT", repo / "server"):
                for version in ("0.18.22", "0.19.1", "0.20.0"):
                    default = manage.make_profile("Halogen", "v2", 32768, "Off", version)
                    self.assertEqual(default["engine"]["directory"], "backends/halogen-wsl2-" + version)
                    self.assertEqual(default["concurrency"], 1)
                    self.assertEqual(default["minimum_reserve_gib"], 18)
                    for field in ("slots", "kv_pool_positions", "launcher", "python_executable"):
                        self.assertNotIn(field, default["engine"])
                    self.assertEqual(default["backend"]["expected"]["slots"], 1)
                    self.assertEqual(default["backend"]["expected"]["kv_pool_positions"], 32768)
                    for field in ("version.api", "version.engine"):
                        self.assertEqual(default["backend"]["expected"][field], version)
                    for slots in (1, 2):
                        profile = manage.make_profile("Halogen", "v2", 32768, "Off", version,
                            slots=slots, kv_pool_positions=65536, concurrency=2)
                        self.assertEqual(profile["concurrency"], 2)
                        self.assertEqual(profile["minimum_reserve_gib"], 18)
                        self.assertEqual(profile["engine"]["slots"], slots)
                        self.assertEqual(profile["engine"]["kv_pool_positions"], 65536)
                        self.assertEqual(profile["engine"]["launcher"], "python")
                        self.assertIs(profile["engine"]["disable_vision"], True)
                        self.assertEqual(profile["backend"]["expected"]["slots"], slots)
                        self.assertEqual(profile["backend"]["expected"]["kv_pool_positions"], 65536)
                        self.assertEqual(profile["backend"]["expected"]["capability_probe"], "ok")
                        controller.validate_halogen_capacity_profile(profile, repo)
                        self.assertNotIn("synthetic-private-token", json.dumps(profile))
                with self.assertRaisesRegex(ValueError, "concurrency 2"):
                    manage.make_profile("Halogen", "v2", 32768, "Off", "0.20.0",
                        slots=2, kv_pool_positions=65536, concurrency=1)

    def test_current_controller_rejects_conflicting_text_controls(self):
        for changes in ({"disable_vision": False, "slots": 2, "kv_pool_positions": 65536},
                        {"prefill_chunk": 8192, "max_prefill_tokens": 2048},
                        {"api_defaults": {"enable_thinking": "false"}},
                        {"speculation_policy": {"HALOGEN_MTP_GATE_P": 0.9}}):
            with self.subTest(changes=changes):
                engine = self.engine()
                engine.update(copy.deepcopy(changes))
                with self.assertRaises(ValueError):
                    controller.validate_engine(engine, REPO)


if __name__ == "__main__":
    unittest.main()
