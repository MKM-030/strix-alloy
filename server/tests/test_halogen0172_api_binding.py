"""The authenticated wrapper must accept the API pinned by its selected release."""
import ast
import json
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[2] / 'backends/halogen-wsl2-0.17.2'

class Halogen0172ApiBindingTests(unittest.TestCase):
    def test_auth_wrapper_pin_matches_selected_release_api(self):
        release = json.loads((PACKAGE / 'profiles/release.json').read_text(encoding='utf-8-sig'))
        tree = ast.parse((PACKAGE / 'scripts/auth_api.py').read_text(encoding='utf-8-sig'))
        pins = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name)
                    and target.id == 'UPSTREAM_SHA256' for target in node.targets)]
        self.assertEqual(pins,[release['upstream_api_sha256']])

if __name__ == '__main__': unittest.main()
