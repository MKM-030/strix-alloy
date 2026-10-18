"""Portable voice profile contract; no model download needed for these tests."""
import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class VoiceProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.audio = b"fixture-waveform"
        (self.folder / "reference.wav").write_bytes(self.audio)
        self.profile = {
            "schema_version": 1,
            "name": "SCC Demo",
            "kind": "designed_synthetic_voice",
            "language": "German",
            "base_model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
            "reference_text": "Guten Tag. Ich helfe Ihnen bei der Einrichtung.",
            "reference_sha256": hashlib.sha256(self.audio).hexdigest(),
        }
        self.write_profile()

    def helper(self):
        try:
            return importlib.import_module("prepare_demo_voice")
        except ModuleNotFoundError as exc:
            self.fail(f"Voice preparation helper is not implemented: {exc}")

    def write_profile(self):
        (self.folder / "voice.json").write_text(
            json.dumps(self.profile, ensure_ascii=False), encoding="utf-8"
        )

    def test_portable_profile_preserves_german_transcript(self):
        actual = self.helper().read_voice_profile(self.folder)
        self.assertEqual(actual["reference_text"], self.profile["reference_text"])

    def test_replaced_reference_cannot_silently_reuse_voice_identity(self):
        (self.folder / "reference.wav").write_bytes(b"different-speaker")
        with self.assertRaisesRegex(ValueError, "reference.*hash"):
            self.helper().read_voice_profile(self.folder)

    def test_non_synthetic_profile_is_rejected(self):
        self.profile["kind"] = "unknown-recording"
        self.write_profile()
        with self.assertRaisesRegex(ValueError, "synthetic"):
            self.helper().read_voice_profile(self.folder)

    def test_cache_changes_when_transcript_or_package_changes(self):
        helper = self.helper()
        key = helper.prompt_cache_key(self.profile, "0.1")
        self.assertNotEqual(key, helper.prompt_cache_key(self.profile, "0.2"))
        altered = dict(self.profile, reference_text="Ein anderer Satz.")
        self.assertNotEqual(key, helper.prompt_cache_key(altered, "0.1"))

    def test_cache_rejects_wrong_base_model(self):
        with self.assertRaisesRegex(ValueError, "Base model"):
            self.helper().read_voice_profile(self.folder, expected_model="unrelated/model")

    def test_corrupt_derived_cache_is_rebuilt_from_valid_reference(self):
        helper = self.helper()
        (self.folder / "prompt.pt").write_bytes(b"truncated-cache")

        @dataclass
        class Prompt:
            ref_code: object = None
            ref_spk_embedding: object = "fixture-embedding"
            x_vector_only_mode: bool = False
            icl_mode: bool = True
            ref_text: str = "Guten Tag."

        class Model:
            def create_voice_clone_prompt(model_self, ref_audio, ref_text, x_vector_only_mode):
                self.assertEqual(Path(ref_audio).read_bytes(), self.audio)
                return [Prompt(ref_text=ref_text)]

        def corrupt_load(*args, **kwargs):
            raise EOFError("truncated-cache")

        fake_torch = types.SimpleNamespace(
            load=corrupt_load,
            save=lambda payload, path: Path(path).write_text(json.dumps(payload), encoding="utf-8"),
            is_tensor=lambda value: False,
        )
        with patch.dict(sys.modules, {"torch": fake_torch, "qwen_tts": types.SimpleNamespace(VoiceClonePromptItem=Prompt)}):
            with patch.object(helper, "version", return_value="0.1"):
                prompts, profile = helper.load_or_create_clone_prompt(Model(), self.folder)
        self.assertEqual(prompts[0].ref_text, self.profile["reference_text"])
        self.assertEqual(profile["reference_sha256"], self.profile["reference_sha256"])
        rebuilt = json.loads((self.folder / "prompt.pt").read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["items"][0]["ref_text"], self.profile["reference_text"])

    def test_failed_reference_manifest_does_not_publish_partial_voice(self):
        helper = self.helper()
        destination = self.folder / "new-voice"
        fake_model = types.SimpleNamespace(generate_voice_design=lambda **kwargs: ([[0.0] * 32], 24000))
        fake_sf = types.SimpleNamespace(write=lambda path, *args, **kwargs: Path(path).write_bytes(b"new-waveform"))
        with patch.dict(sys.modules, {"soundfile": fake_sf, "torch": types.SimpleNamespace(manual_seed=lambda seed: None)}):
            with patch.object(helper, "load_model", return_value=fake_model), patch.object(helper, "version", return_value="0.1"):
                with patch.object(helper, "_write_json", side_effect=OSError("disk full")):
                    with self.assertRaisesRegex(OSError, "disk full"):
                        helper.prepare_reference(destination)
        self.assertFalse(destination.exists(), "Incomplete reference/profile must not become an installed voice")


if __name__ == "__main__":
    unittest.main()
