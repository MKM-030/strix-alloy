"""Synthetic, read-only-lease tests for the native NTFS generation witness."""

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ntfs_file_generation as generation


def usn_record(file_id, major, usn):
    record_size, usn_offset, reference_size = {2: (64, 24, 8), 3: (80, 40, 16)}[major]
    record = bytearray(record_size)
    struct.pack_into('<IHH', record, 0, record_size, major, 0)
    record[8:8+reference_size] = file_id[:reference_size]
    struct.pack_into('<q', record, usn_offset, usn)
    return bytes(record)


class NtfsGenerationParsing(unittest.TestCase):
    def test_local_windows_path_requires_ordinary_canonical_filename(self):
        self.assertEqual(str(generation._checked_path(r'C:\data\fixture.bin')),
                         r'C:\data\fixture.bin')
        for path in (r'C:fixture.bin', r'\\server\share\fixture.bin', r'\\?\C:\fixture.bin',
                     'C:\\', r'C:\a\..\fixture.bin', r'C:\a\.\fixture.bin',
                     r'C:\fixture.bin:other', 'C:\\fixture.bin ', 'C:\\a\\\\fixture.bin',
                     'C:\\bad\nfixture.bin'):
            with self.subTest(path=path), self.assertRaises(generation.NtfsGenerationUnavailable):
                generation._checked_path(path)

    def test_journal_buffer_and_range(self):
        record = struct.pack('<QqqqqQQ', 7, 100, 200, 60, 1000, 65536, 4096)
        self.assertEqual(generation._parse_journal(record), (7, 100, 200, 60))
        malformed = (
            record[:55],
            struct.pack('<QqqqqQQ', 0, 100, 200, 60, 1000, 65536, 4096),
            struct.pack('<QqqqqQQ', 7, 201, 200, 60, 1000, 65536, 4096),
            struct.pack('<QqqqqQQ', 7, 100, 200, 201, 1000, 65536, 4096),
        )
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(generation.NtfsGenerationUnavailable):
                generation._parse_journal(data)

    def test_file_record_requires_authoritative_reference_and_supported_layout(self):
        file_id = bytes(range(16))
        record = usn_record(file_id, 3, 115)
        self.assertEqual(generation._parse_file_usn(record, file_id), (115, 3))
        ntfs_64_id = file_id[:8] + bytes(8)
        self.assertEqual(generation._parse_file_usn(usn_record(ntfs_64_id, 2, 119), ntfs_64_id),
                         (119, 2))
        for data, expected in (
            (record[:7], file_id),
            (record[:50], file_id),
            (usn_record(file_id, 3, -1), file_id),
            (record[:4] + b'\x04\x00' + record[6:], file_id),
            (record[:6] + b'\x01\x00' + record[8:], file_id),
            (record, bytes(16)),
            (usn_record(file_id, 2, 115), file_id),
        ):
            with self.subTest(data=data, expected=expected), \
                    self.assertRaises(generation.NtfsGenerationUnavailable):
                generation._parse_file_usn(data, expected)

    def test_system_journal_fallback_requires_each_exact_field(self):
        output = (b'Usn Journal ID   : 0x0007\r\nFirst Usn        : 0x0064\r\n'
                  b'Next Usn         : 0x00c8\r\nLowest Valid Usn : 0x003c\r\n')
        self.assertEqual(generation._parse_fsutil(output), (7, 100, 200, 60))
        for data in (output + b'Next Usn : 0x00c9\r\n',
                     output.replace(b'Next Usn', b'Andere Ausgabe'),
                     output.replace(b'0x0064', b'0x0100'),
                     output.replace(b'0x0007', b'0x0000')):
            with self.subTest(data=data), self.assertRaises(generation.NtfsGenerationUnavailable):
                generation._parse_fsutil(data)

    def test_same_handle_snapshot_rejects_journal_reset_and_file_race(self):
        file_id = bytes(range(16))
        path = generation._checked_path(r'C:\data\fixture.bin')
        original_journal = generation._Journal(7, 100, 200, 60)
        current_journal = generation._Journal(7, 101, 208, 60)
        reset_journal = generation._Journal(8, 100, 200, 60)
        reversed_journal = generation._Journal(7, 100, 199, 60)
        for journals, last, accepted in (
            ((original_journal, current_journal), 115, True),
            ((original_journal, reset_journal), 115, False),
            ((original_journal, reversed_journal), 115, False),
            ((original_journal, current_journal), 116, False),
        ):
            with self.subTest(journals=journals, last=last):
                api, handle = Mock(), object()
                api.direct_journal.side_effect = journals
                api.metadata.return_value = {'file_id': file_id.hex(), 'eof': 15}
                api.ioctl.side_effect = [usn_record(file_id, 3, 115), usn_record(file_id, 3, last)]
                lease = generation._NtfsReadLease(api, handle, path, 'volume')
                if accepted:
                    self.assertEqual(lease.snapshot()['file_usn'], 115)
                else:
                    with self.assertRaises(generation.NtfsGenerationUnavailable):
                        lease.snapshot()
                self.assertEqual([item.args[0] for item in api.metadata.call_args_list], [handle, handle])
                self.assertEqual([item.args[0] for item in api.ioctl.call_args_list], [handle, handle])


@unittest.skipUnless(os.name == 'nt', 'Native Win32 fixture')
class NativeNtfsLease(unittest.TestCase):
    def test_file_generation_and_share_modes(self):
        temp_root = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(prefix='alloy-ntfs-generation-fixture-', dir=temp_root) as folder:
            fixture = Path(folder).resolve()
            self.assertEqual(fixture.parent, temp_root)
            target = fixture / 'fixture.bin'
            target.write_bytes(b'initial fixture')
            alternate = fixture / 'alternate.bin'
            alternate.write_bytes(b'updated fixture')

            try:
                with generation.open_read_lease(target) as lease:
                    original = lease.snapshot()
                    self.assertEqual(original, lease.snapshot())
                    self.assertEqual(target.read_bytes(), b'initial fixture')
                    self.assertEqual(original['eof'], len(b'initial fixture'))
                    self.assertRegex(original['file_id'], r'^[0-9a-f]{32}$')
                    self.assertGreater(original['journal_id'], 0)
                    with self.assertRaises(PermissionError):
                        with target.open('r+b'):
                            pass
                    with self.assertRaises(PermissionError):
                        alternate.replace(target)
            except generation.NtfsGenerationUnavailable as exc:
                if getattr(exc.__cause__, 'winerror', None) in (1, 5, 50, 1178, 1179) \
                        or str(exc) == 'Local drive does not use NTFS':
                    self.skipTest(f'Native NTFS journal unavailable for this test: {exc}')
                raise

            with self.assertRaises(generation.NtfsGenerationUnavailable):
                lease.snapshot()
            ignored = OSError('caller failed after opening lease')
            with self.assertRaises(OSError) as original_error:
                with generation.open_read_lease(target):
                    raise ignored
            self.assertIs(original_error.exception, ignored)
            old = target.stat()
            target.write_bytes(b'updated fixture')
            os.utime(target, ns=(old.st_atime_ns, old.st_mtime_ns))
            with generation.open_read_lease(target) as amended:
                changed = amended.snapshot()
            self.assertEqual(changed['eof'], original['eof'])
            self.assertEqual(changed['file_id'], original['file_id'])
            self.assertEqual(changed['written_100ns'], original['written_100ns'])
            self.assertNotEqual(changed['file_usn'], original['file_usn'])

            alternate.replace(target)
            with generation.open_read_lease(target) as replaced:
                self.assertNotEqual(replaced.snapshot()['file_id'], original['file_id'])


if __name__ == '__main__':
    unittest.main()
