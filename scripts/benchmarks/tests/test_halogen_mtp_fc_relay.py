"""Three Linux file-transport checks using fresh tiny host fixtures only.

No native shim/engine/provider runs. These do not qualify a container/WSL pipe.
"""
import os
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import halogen_mtp_fc_relay as relay


@unittest.skipUnless(sys.platform == "linux", "requires actual Linux openat/renameat2 semantics")
class RelayFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/tmp") / ("alloy-mtp-fc-quality-" + uuid.uuid4().hex)
        self.root.mkdir(mode=0o700)
        self.packets = relay.PacketDirectory(str(self.root), os.geteuid())

    def tearDown(self):
        self.packets.close()
        # Only this explicitly created flat fixture; no recursive/path-built
        # shell removal and no link following.
        for path in self.root.iterdir():
            path.unlink()
        self.root.rmdir()

    def test_owner_file_publication_is_exact_and_cannot_replace_an_arm(self):
        content = bytes(range(120))
        self.packets.publish("armed", content)
        self.assertEqual(self.packets.read("armed", 120), content)
        self.assertEqual((self.root / "armed").stat().st_nlink, 1)
        with self.assertRaises(FileExistsError):
            self.packets.publish("armed", bytes(120))
        self.assertEqual(self.packets.read("armed", 120), content)

    def test_fifo_and_symlink_are_rejected_without_blocking_or_following(self):
        os.mkfifo(self.root / "observed.bin", 0o600)
        with self.assertRaises(ValueError):
            self.packets.read("observed.bin", 464)
        (self.root / "observed.bin").unlink()
        (self.root / "observed.bin").symlink_to("missing-target")
        with self.assertRaises(OSError):
            self.packets.read("observed.bin", 464)

    def test_native_regular_packet_requires_exact_mode_and_extent(self):
        path = self.root / "000-request.bin"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, bytes(51424))
        finally:
            os.close(descriptor)
        self.assertEqual(self.packets.read(path.name, 51424), bytes(51424))
        os.chmod(path, 0o644)
        with self.assertRaises(ValueError):
            self.packets.read(path.name, 51424)
        os.chmod(path, 0o600)
        with self.assertRaises(ValueError):
            self.packets.read(path.name, 120)


if __name__ == "__main__":
    unittest.main()
