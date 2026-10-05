"""Source-only extraction guard regression: no file contents are read."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


class BoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name("pack.py")
        spec = importlib.util.spec_from_file_location("bound_pack", source)
        cls.pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pack)

    def argv(self):
        return ["pack.py", "--raw", "test-original-H.q8", "--raw-sha256", "0" * 64,
                "--out-dir", "test-fresh-output"]

    def test_checkpoint_extent_is_rejected_before_open_or_read(self):
        with patch("sys.argv", self.argv()), patch.object(Path, "exists", return_value=False), \
                patch.object(Path, "stat", return_value=SimpleNamespace(st_size=66 * 1024**3)), \
                patch.object(Path, "open", side_effect=AssertionError("checkpoint opened before extent admission")) as opened, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.pack.main()
        self.assertEqual(error.exception.code, 2)
        opened.assert_not_called()

    def test_extent_change_uses_bounded_read_then_fails_before_hash_or_publish(self):
        source = MagicMock()
        reader = MagicMock()
        source.__enter__.return_value = reader
        reader.read.return_value = b"short"
        with patch("sys.argv", self.argv()), patch.object(Path, "exists", return_value=False), \
                patch.object(Path, "stat", return_value=SimpleNamespace(st_size=self.pack.WEIGHT_BYTES)), \
                patch.object(Path, "open", return_value=source), patch.object(self.pack, "sha") as hashed, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            self.pack.main()
        self.assertEqual(error.exception.code, 2)
        reader.read.assert_called_once_with(self.pack.WEIGHT_BYTES + 1)
        hashed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
