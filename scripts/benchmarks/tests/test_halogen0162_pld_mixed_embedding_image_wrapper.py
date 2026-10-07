"""Windows-only checks of frozen fixture selection and the native CLI boundary."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/benchmarks/halogen0162_pld_mixed_embedding_image_wrapper.py"
LOCAL = ROOT / "server/.local/optimization9h-20261004"


class MixedImageWrapperTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), "mixed component wrapper is missing")
        spec = importlib.util.spec_from_file_location("mixed_image_wrapper", SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.fc = json.loads((LOCAL / "fc-fixtures-f47a1312c34f47b6a23188247f46741b/fixtures.json").read_text())
        self.rms = json.loads((LOCAL / "embedding-rms-fixtures-78c49b8e265c4de9adb9c0cf3cc8254e/fixtures.json").read_text())

    def test_emits_raw_embedding_then_gamma_then_hidden_in_native_nineteen_argument_order(self):
        # Swapping raw and normalized rows, or changing the argc18 FC order,
        # would bind the wrong native input despite valid individual hashes.
        bindings = {
            key: {"path": path, "sha256": digit * 64}
            for key, path, digit in (
                ("e_weight", "/fc-fixtures/e-weight.q8g64", "1"),
                ("h_weight", "/fc-fixtures/h-weight.q8g64", "2"),
                ("A_raw", "/rms-fixtures/A-input.u16", "3"),
                ("B_raw", "/rms-fixtures/B-input.u16", "4"),
                ("gamma", "/rms-fixtures/raw-gamma.u16", "5"),
                ("A_h", "/fc-fixtures/A-h-norm.u16", "6"),
                ("B_h", "/fc-fixtures/B-h-norm.u16", "7"),
                ("hip", "/pinned/libamdhip64.so.7", "8"),
            )
        }
        self.assertEqual(self.module.component_command(bindings), [
            "/candidate/replay", "/candidate/flash_serve", "/candidate/engine-gfx1151.hsaco",
            "/pinned/libamdhip64.so.7", "8" * 64,
            "/fc-fixtures/e-weight.q8g64", "1" * 64,
            "/fc-fixtures/h-weight.q8g64", "2" * 64,
            "/rms-fixtures/A-input.u16", "3" * 64,
            "/rms-fixtures/B-input.u16", "4" * 64,
            "/rms-fixtures/raw-gamma.u16", "5" * 64,
            "/fc-fixtures/A-h-norm.u16", "6" * 64,
            "/fc-fixtures/B-h-norm.u16", "7" * 64,
            "/result/native",
        ])

    def test_frozen_manifests_select_seven_exact_raw_inputs(self):
        self.assertEqual(self.module.fixture_specs(self.fc, self.rms), [
            ("e_weight", "/fc-fixtures/e-weight.q8g64", "ec6ac9d2e6111b3cf9df7cc408afd555cd33ac291e5613d4000d58cd8a51107d", 6963200),
            ("h_weight", "/fc-fixtures/h-weight.q8g64", "018511894df3996e3a2fcb1dff60860c45a808b65036fd38db472b6e985bdd3f", 6963200),
            ("A_raw", "/rms-fixtures/A-input.u16", "af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374", 5120),
            ("B_raw", "/rms-fixtures/B-input.u16", "e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4", 5120),
            ("gamma", "/rms-fixtures/raw-gamma.u16", "04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86", 5120),
            ("A_h", "/fc-fixtures/A-h-norm.u16", "bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34", 20480),
            ("B_h", "/fc-fixtures/B-h-norm.u16", "0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711", 20480),
        ])

    def test_rejects_normalized_or_escaped_embedding_path(self):
        for replacement in ("B-ort-rms.u16", "../B-input.u16"):
            rms = copy.deepcopy(self.rms)
            rms["rows"][1]["files"]["B-input.u16"]["file"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(RuntimeError):
                self.module.fixture_specs(self.fc, rms)

    def test_rejects_changed_gamma_or_hidden_hash(self):
        rms = copy.deepcopy(self.rms)
        rms["gamma"]["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.module.fixture_specs(self.fc, rms)
        fc = copy.deepcopy(self.fc)
        fc["inputs"]["B"]["h"]["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.module.fixture_specs(fc, self.rms)


if __name__ == "__main__":
    unittest.main()
