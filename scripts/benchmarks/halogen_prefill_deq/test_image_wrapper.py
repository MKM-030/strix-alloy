"""Host-only regression for the pinned image's regular HIP .so.7 file."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prefill_deq_wrapper', Path(__file__).with_name('image_wrapper.py'))
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


class InstalledHip(unittest.TestCase):
    def test_regular_versioned_runtime_without_unversioned_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = root / 'libamdhip64.so.7'
            library.write_bytes(b'pinned-image-library-fixture')
            def image_path(value):
                return root / Path(value).name
            with patch.object(wrapper, 'Path', image_path):
                self.assertEqual(wrapper.installed_hip(), library)


if __name__ == '__main__':
    unittest.main()
