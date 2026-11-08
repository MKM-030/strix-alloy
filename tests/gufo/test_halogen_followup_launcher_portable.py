"""Portable Windows PowerShell5.1 PrintOnly checks with synthetic installed metadata.

Copies finite tracked Python sources into a temporary checkout; no live token,
installed repo environment, model, API, WSL or lifecycle state is consumed.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv

HERE = Path(__file__).resolve().parent
REPO = next(parent for parent in (HERE, *HERE.parents) if (parent/"server/manage.py").is_file())
LAUNCHER = HERE/"Start-Halogen-ServiceNow.ps1"
if not LAUNCHER.is_file():
    LAUNCHER = REPO/"scripts/Start-Halogen-ServiceNow.ps1"
PS = Path(os.environ.get("SystemRoot", "C:/Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"


@unittest.skipUnless(os.name == "nt" and PS.is_file(), "Windows PowerShell5.1 is required")
class FollowupLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="alloy-followup-launcher-cpu-")
        cls.root = Path(cls.temporary.name)/"project"
        server = cls.root/"server"
        server.mkdir(parents=True)
        for source in (REPO/"server").glob("*.py"):
            shutil.copy2(source, server/source.name)
        cls.script = cls.root/"scripts/Start-Halogen-ServiceNow.ps1"
        cls.script.parent.mkdir()
        shutil.copy2(LAUNCHER, cls.script)
        cls.fixture_venv = server/".local/venv"
        venv.EnvBuilder(with_pip=False).create(cls.fixture_venv)
        cls.stable = server/".local/servicenow-api-token.txt"
        cls.stable.write_text("SYNTHETIC_PUBLIC_TOKEN_NEVER_PRINT_123", encoding="utf-8")
        for version in ("0.18.10", "0.18.22", "0.19.1", "0.20.0"):
            package = cls.root/("backends/halogen-wsl2-"+version)
            (package/"profiles").mkdir(parents=True)
            (package/".local").mkdir()
            release = dict(version=version, image="synthetic-image-"+version)
            (package/"profiles/release.json").write_text(json.dumps(release))
            (package/".local/machine.json").write_text(json.dumps(dict(version=version, image=release["image"], pwsh=str(PS))))
            (package/".local/api-token.txt").write_text("SYNTHETIC_BACKEND_TOKEN_NEVER_PRINT_456")
            if version in ("0.18.22", "0.19.1", "0.20.0"):
                (package/"scripts").mkdir()
                shutil.copy2(REPO/("backends/halogen-wsl2-"+version)/"scripts/capacity_policy.py",
                             package/"scripts/capacity_policy.py")
        cls.env = os.environ.copy()
        packages = [str(Path(item)) for item in sys.path if (Path(item)/"aiohttp").is_dir()]
        cls.env["PYTHONPATH"] = os.pathsep.join(packages)
        cls.env["PATH"] = str(cls.fixture_venv/"Scripts")+os.pathsep+cls.env["PATH"]
        cls.env["PYTHONDONTWRITEBYTECODE"] = "1"

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self, *arguments, profile="FollowupText32K"):
        args = [str(PS), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(self.script), "-PrintOnly"]
        if profile is not None:
            args += ["-Profile", profile]
        result = subprocess.run(args+list(arguments), cwd=self.root, env=self.env, text=True,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertNotIn("SYNTHETIC_PUBLIC_TOKEN_NEVER_PRINT_123", result.stdout+result.stderr)
        self.assertNotIn("SYNTHETIC_BACKEND_TOKEN_NEVER_PRINT_456", result.stdout+result.stderr)
        self.assertFalse((self.root/"server/.local/servicenow-sessions").exists())
        self.assertFalse((self.root/"server/.local/current.json").exists())
        return result

    def decoded(self, result):
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        start = result.stdout.find("{")
        self.assertGreaterEqual(start, 0, result.stdout)
        return json.JSONDecoder().raw_decode(result.stdout[start:])[0]

    def expected_current(self, version="0.20.0", prefill=2048):
        return {
            "schema":1, "minimum_reserve_gib":18, "token_file":str(self.stable),
            "backend_token_file":str(self.root/("backends/halogen-wsl2-"+version)/".local/api-token.txt"),
            "concurrency":1, "body_bytes":16777216, "request_seconds":1800,
            "backend":{"identifier":"halogen-v2", "upstream":"http://127.0.0.1:8731",
                "model":"halogen-qwen3.8-flash-next", "checkpoint":"v2", "context":32768,
                "expected":{"status":"ok", "version.api":version, "version.engine":version,
                    "version.match":True, "context":32768, "slot_ctx":32768,
                    "kv_pool_positions":32768, "slots":1, "vision.enabled":False},
                "routes":["/v1/chat/completions", "/v1/completions", "/v1/responses",
                          "/v1/messages", "/v1/messages/count_tokens"]},
            "engine":{"kind":"halogen", "directory":"backends/halogen-wsl2-"+version, "checkpoint":"v2",
                "context":32768, "prompt_cache":"Off", "powershell":str(PS),
                "launcher":"python", "python_executable":str(self.fixture_venv/"Scripts/python.exe"),
                "speculation_policy":{"HALOGEN_PLD":"3,3", "HALOGEN_MTP_GATE_P":"0.90"},
                "prefill_chunk":prefill, "max_prefill_tokens":prefill,
                "api_defaults":{"enable_thinking":False, "reasoning_effort":"low", "max_thinking_tokens":2048},
                "disable_vision":True, "kernel_controls":{"HALOGEN_DECODE_PREFETCH":0}},
            "console_trace":False,
        }

    def normalize(self, value):
        value = copy.deepcopy(value)
        value["engine"]["powershell"] = os.path.normcase(value["engine"]["powershell"])
        return value

    def test_current_text32k_exact_contract_stays_cacheoff(self):
        actual = self.decoded(self.invoke(profile="CurrentText32K"))
        self.assertEqual(self.normalize(actual), self.normalize(self.expected_current()))

    def test_followup_differs_only_by_measured_version_cache_and_prefill(self):
        current = self.decoded(self.invoke(profile="CurrentText32K"))
        result = self.invoke()
        followup = self.decoded(result)
        expected = self.expected_current("0.18.22", prefill=8192)
        expected["engine"]["prompt_cache"] = "Flexible"
        self.assertEqual(self.normalize(followup), self.normalize(expected))
        current["backend_token_file"] = expected["backend_token_file"]
        current["engine"]["directory"] = expected["engine"]["directory"]
        current["engine"]["prompt_cache"] = "Flexible"
        current["engine"]["prefill_chunk"] = 8192
        current["engine"]["max_prefill_tokens"] = 8192
        for field in ("version.api", "version.engine"):
            current["backend"]["expected"][field] = "0.18.22"
        self.assertEqual(followup, current)
        self.assertIn("follow-up latency", result.stdout.lower())
        self.assertIn("no session configuration was written and no engine was launched", result.stdout)

    def test_explicit_matching_selectors_and_console_trace_are_opt_in(self):
        result = self.invoke("-HalogenVersion", "0.18.22", "-Thinking", "Off",
                             "-MtpPolicy", "Auto", "-PromptCache", "Flexible", "-ConsoleTrace")
        actual = self.decoded(result)
        expected = self.expected_current("0.18.22", prefill=8192)
        expected["engine"]["prompt_cache"] = "Flexible"
        expected["console_trace"] = True
        self.assertEqual(self.normalize(actual), self.normalize(expected))
        self.assertIn("MTP policy Confidence90; PLD 3,3; cache Flexible", result.stdout)

    def test_conflicting_pinned_settings_are_rejected_before_launch(self):
        for options in [("-PromptCache", "Off"), ("-PromptCache", "Exact"),
                        ("-HalogenVersion", "0.18.10"), ("-Thinking", "On"),
                        ("-MtpPolicy", "Fixed2")]:
            with self.subTest(options=options):
                result = self.invoke(*options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FollowupText32K requires Halogen 0.18.22", result.stdout+result.stderr)

    def test_missing_stable_token_is_rejected_without_replacement(self):
        saved = self.stable.read_bytes()
        self.stable.unlink()
        try:
            result = self.invoke()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires the existing server/.local/servicenow-api-token.txt", result.stdout+result.stderr)
            self.assertFalse(self.stable.exists())
        finally:
            self.stable.write_bytes(saved)

    def test_bare_default_selects_latest_current_text32k(self):
        result = self.invoke(profile=None)
        actual = self.decoded(result)
        self.assertEqual(self.normalize(actual), self.normalize(self.expected_current()))
        self.assertIn("Profile: CurrentText32K; Halogen 0.20.0 v2; MTP policy Confidence90; PLD 3,3; cache Off", result.stdout)
        self.assertIn("Thinking default: Off; low effort", result.stdout)
        self.assertIn("Prefill chunk / token arena: 2048 / 2048", result.stdout)

    def test_current_text_allows_explicit_larger_prefill(self):
        result = self.invoke("-PrefillTokens", "8192", profile="CurrentText32K")
        actual = self.decoded(result)
        self.assertEqual(self.normalize(actual), self.normalize(self.expected_current(prefill=8192)))
        self.assertIn("Prefill chunk / token arena: 8192 / 8192", result.stdout)

    def test_explicit_legacy_version_with_current4k_preserves_its_policy(self):
        result = self.invoke("-HalogenVersion", "0.18.10", profile="Current4K")
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        self.assertIn("Profile: Current4K; Halogen 0.18.10 v2; MTP policy Fixed2; PLD 3,3; cache Off", result.stdout)
        self.assertIn("Context capacity: 262144", result.stdout)
        self.assertIn("Thinking default: On; medium effort", result.stdout)
        self.assertIn("Prefill chunk / token arena: 4096 / 4096", result.stdout)

    def test_explicit_previous_release_remains_selectable(self):
        result = self.invoke("-HalogenVersion", "0.19.1", "-MtpPolicy", "Confidence90", profile="Current4K")
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        self.assertIn("Profile: Current4K; Halogen 0.19.1 v2; MTP policy Confidence90", result.stdout)

    def test_current_text_forwards_two_slot_capacity_and_2048_prefill(self):
        result = self.invoke("-Slots", "2", "-KvPoolPositions", "65536", "-Concurrency", "2",
                             "-PrefillTokens", "2048", profile="CurrentText32K")
        actual = self.decoded(result)
        expected = self.expected_current()
        expected["concurrency"] = 2
        expected["engine"].update(slots=2, kv_pool_positions=65536,
                                  prefill_chunk=2048, max_prefill_tokens=2048)
        expected["backend"]["expected"].update(slots=2, kv_pool_positions=65536, capability_probe="ok")
        self.assertEqual(self.normalize(actual), self.normalize(expected))
        self.assertIn("Opt-in gateway concurrency: 2; native slots: 2; KV pool: 65536", result.stdout)
        self.assertIn("Prefill chunk / token arena: 2048 / 2048", result.stdout)

    def test_current_text_rejects_conflicting_pinned_selectors(self):
        for options in [("-PromptCache", "Flexible"), ("-PromptCache", "Exact"),
                        ("-HalogenVersion", "0.18.22"), ("-Thinking", "On"),
                        ("-MtpPolicy", "Fixed2")]:
            with self.subTest(options=options):
                result = self.invoke(*options, profile="CurrentText32K")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CurrentText32K requires Halogen 0.20.0", result.stdout+result.stderr)

    def test_capacity_and_prefill_selectors_require_current_text32k(self):
        for profile in ("FollowupText32K", "Current4K"):
            for options, message in [(("-Slots", "2"), "Capacity selectors require CurrentText32K"),
                                     (("-PrefillTokens", "2048"), "PrefillTokens requires CurrentText32K")]:
                with self.subTest(profile=profile, options=options):
                    result = self.invoke(*options, profile=profile)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stdout+result.stderr)

    def test_two_slots_require_explicit_two_request_concurrency(self):
        result = self.invoke("-Slots", "2", "-KvPoolPositions", "65536", profile="CurrentText32K")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("concurrency", result.stdout+result.stderr)

    def test_unsupported_prefill_size_is_rejected_by_powershell(self):
        result = self.invoke("-PrefillTokens", "1024", profile="CurrentText32K")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PrefillTokens", result.stdout+result.stderr)


if __name__ == "__main__":
    unittest.main()
