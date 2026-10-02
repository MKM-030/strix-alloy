import pathlib
import json
import tempfile
import unittest

from importlib.util import module_from_spec, spec_from_file_location

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = spec_from_file_location('optin_attention', ROOT / 'optin_attention.py')
optin_attention = module_from_spec(spec)
spec.loader.exec_module(optin_attention)


class AttentionPatchTests(unittest.TestCase):
    def test_opt_in_patch_has_cross_window_split_invariant(self):
        patch = (ROOT / 'patches/attention-window-optin.patch').read_text()
        self.assertIn('carry + total', patch)
        self.assertIn('tile_no % splits', patch)
        self.assertIn('kCarry', patch)
        self.assertIn('AttentionKernel', patch)

    def test_guard_requires_exact_qualified_numerics_source(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / optin_attention.RELATIVE
            target.parent.mkdir(parents=True)
            target.write_text('unqualified source', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'numerics-patched'):
                optin_attention.verify(pathlib.Path(directory))

    def test_expected_hash_is_compatibility_manifest_post_numerics(self):
        manifest = json.loads((ROOT / 'compatibility.json').read_text())
        self.assertEqual(optin_attention.EXPECTED_SHA256,
                         manifest['source_patch']['files'][optin_attention.RELATIVE.as_posix()]['after_sha256'])


if __name__ == '__main__':
    unittest.main()
