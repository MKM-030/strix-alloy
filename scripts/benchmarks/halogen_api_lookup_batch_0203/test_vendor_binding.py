"""Small provenance tests with ordinary fake files; no native module is loaded."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def subject():
    spec = importlib.util.spec_from_file_location('lookup_vendor_harness', HERE / 'real_tokenizer_harness.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(HERE))
    return module


class VendorBindingTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        package = root / 'vendor/tokenizers'
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('# CPU metadata fixture only\n', encoding='utf-8')
        native = package / 'tokenizers.abi3.pyd'
        native.write_bytes(b'Ordinary fake file; never loaded as native code')
        cls = object()
        return root, NS(__file__=str(package / '__init__.py'), Tokenizer=cls), NS(__file__=str(native), Tokenizer=cls)

    def test_empty_vendor_cannot_fall_back_to_cached_ambient_package(self):
        h = subject()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vendor = root / 'empty-vendor'
            vendor.mkdir()
            tokenizer = root / 'tokenizer.json'
            tokenizer.write_bytes(b'CPU metadata fixture')
            ambient = NS(__version__='0.23.2', Tokenizer=NS(from_file=lambda path: self.fail('Ambient tokenizer constructor reached')))
            with patch.object(h, 'TOKENIZER_SHA', hashlib.sha256(tokenizer.read_bytes()).hexdigest()), \
                    patch.dict(sys.modules, {'tokenizers': ambient}):
                with self.assertRaisesRegex(ValueError, 'vendor'):
                    h.run(root / 'api.py', tokenizer, vendor, root / 'output.json')

    def test_actual_package_and_native_paths_and_hashes_are_bound(self):
        h = subject()
        root, package, native = self.fixture()
        result = h.validate_vendor_binding(root / 'vendor', package, native)
        self.assertEqual(result['package']['sha256'], h.pin(package.__file__)['sha256'])
        self.assertEqual(result['native']['sha256'], h.pin(native.__file__)['sha256'])
        self.assertTrue(result['Tokenizer_class_matches_loaded_native'])

    def test_ambient_package_is_rejected_before_native_import(self):
        h = subject()
        root, package, native = self.fixture()
        outside = root / 'ambient.py'
        outside.write_text('# outside vendor\n', encoding='utf-8')
        package.__file__ = str(outside)
        with patch.object(h.importlib, 'import_module', return_value=package) as importer:
            with self.assertRaisesRegex(ValueError, 'package'):
                h.load_vendor_tokenizers(root / 'vendor')
        importer.assert_called_once_with('tokenizers')

    def test_native_module_outside_vendor_is_rejected(self):
        h = subject()
        root, package, native = self.fixture()
        outside = root / 'ambient.pyd'
        outside.write_bytes(b'Fake outside native file')
        native.__file__ = str(outside)
        with self.assertRaisesRegex(ValueError, 'native'):
            h.validate_vendor_binding(root / 'vendor', package, native)

    def test_mixed_exported_Tokenizer_class_is_rejected(self):
        h = subject()
        root, package, native = self.fixture()
        package.Tokenizer = object()
        with self.assertRaisesRegex(ValueError, 'Tokenizer'):
            h.validate_vendor_binding(root / 'vendor', package, native)

    def test_valid_mocked_loader_restores_import_path_without_loading_native_code(self):
        h = subject()
        root, package, native = self.fixture()
        before = list(sys.path)
        with patch.object(h.importlib, 'import_module', side_effect=[package, native]) as importer:
            loaded, binding = h.load_vendor_tokenizers(root / 'vendor')
        self.assertIs(loaded, package)
        self.assertEqual([call.args[0] for call in importer.call_args_list], ['tokenizers', 'tokenizers.tokenizers'])
        self.assertEqual(sys.path, before)
        self.assertEqual(binding['native']['path'], native.__file__)


if __name__ == '__main__':
    unittest.main()
