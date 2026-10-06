"""Managed launch integration; no engine, model I/O or accelerator execution."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controller
import draft_profiles


class LookupForwardingTests(unittest.TestCase):
    def test_stock_and_explicit_lookup_reach_owned_launcher(self):
        repo = Path(__file__).resolve().parents[2]
        stock = {'kind': 'halogen', 'directory': 'backends/halogen-wsl2-0.16.2',
                 'checkpoint': 'v2', 'context': 65536, 'prompt_cache': 'Off',
                 'powershell': 'pwsh.exe'}
        gateway = SimpleNamespace(secret='', backend_secret='')
        commands = []
        fixture_lock = repo / stock['directory'] / '.local/runner.lock'
        actual_exists = Path.exists

        def fixture_exists(path):
            # Command capture owns no process and must not depend on the live
            # repository's ownership lock. Preserve every other validation.
            return False if path == fixture_lock else actual_exists(path)

        def fake_child(command, *, stdout_path, stderr_path, **unused):
            commands.append(command)
            Path(stdout_path).touch()
            Path(stderr_path).touch()
            return SimpleNamespace()

        with tempfile.TemporaryDirectory(dir=repo / 'server/.local') as temporary:
            directory = Path(temporary)
            receipt = directory / 'lookup.receipt.json'
            receipt.write_text('{}', encoding='utf-8')
            config = {'receipt': str(receipt), 'receipt_sha256': 'a' * 64}
            source = {'backend': {'identifier': 'halogen-v2', 'context': 65536},
                      'engine': stock}
            original = copy.deepcopy(source)
            candidate = draft_profiles.tune(source, draft_tokens=2, lookup_tuning=config)
            self.assertEqual(source, original)
            with patch.object(controller, 'JobChild', side_effect=fake_child), \
                    patch.object(Path, 'exists', fixture_exists):
                for settings in (stock, candidate['engine']):
                    engine = controller.Engine(settings, gateway, repo, directory)
                    try:
                        engine.start()
                    finally:
                        engine.tail_stop.set()
                        if engine.output:
                            engine.output.join(2)
            self.assertEqual(len(commands), 2)
            self.assertNotIn('-LookupReceipt', commands[0])
            self.assertNotIn('-LookupReceiptSha256', commands[0])
            self.assertEqual(commands[1][-4:], ['-LookupReceipt', str(receipt.resolve()),
                                              '-LookupReceiptSha256', config['receipt_sha256']])
            wrong = {**candidate['engine'], 'checkpoint': 'w4b'}
            with self.assertRaisesRegex(ValueError, '0.16.2 v2'):
                controller.validate_engine(wrong, repo)
            self.assertEqual(len(commands), 2)


if __name__ == '__main__':
    unittest.main()
