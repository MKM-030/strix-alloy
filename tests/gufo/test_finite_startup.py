import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gufo_control.finite_startup import ListeningHint

MARKER = (b'2026-09-27 12:34:56 [INFO] [server] event=listening '
          b'address=http://127.0.0.1:8836 auth=bearer '
          b'max_connections=3 max_body_bytes=16384\n')

class ListeningHintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'run'
        self.root.mkdir()
        self.log = self.root / 'stderr.log'
        self.log.write_bytes(b'')
        self.now = [100.0]
        self.hint = ListeningHint(self.root, clock=lambda: self.now[0])

    def test_split_exact_marker_and_incremental_offset(self):
        with self.log.open('ab') as stream:
            stream.write(MARKER[:20])
        self.assertFalse(self.hint.poll(580.0))
        self.assertEqual(self.hint.offset, 20)
        with self.log.open('ab') as stream:
            stream.write(MARKER[20:-1])
        self.assertFalse(self.hint.poll(580.0))
        with self.log.open('ab') as stream:
            stream.write(b'\n')
        self.assertTrue(self.hint.poll(580.0))
        self.assertEqual(self.hint.offset, len(MARKER))
        self.assertTrue(self.hint.poll(580.0))

    def test_changed_consumed_prefix_between_polls_is_rejected(self):
        self.log.write_bytes(MARKER[:20])
        self.assertFalse(self.hint.poll(580.0))
        self.log.write_bytes(b'X' * 20 + MARKER[20:])
        with self.assertRaisesRegex(ValueError, 'finite_listening_file_changed'):
            self.hint.poll(580.0)

    def test_open_handle_replacement_during_read_is_rejected(self):
        self.log.write_bytes(MARKER)
        original_open = Path.open
        log_path = self.log
        root_dir = self.root

        class ReplacingReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def seek(self, *args):
                return self.stream.seek(*args)

            def fileno(self):
                return self.stream.fileno()

            def read(self, *args):
                chunk = self.stream.read(*args)
                self.stream.close()
                log_path.rename(root_dir / 'old-stderr.log')
                with original_open(log_path, 'wb') as changed:
                    changed.write(b'changed\n')
                return chunk

        def replacing_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path == self.log:
                return ReplacingReader(stream)
            return stream

        with patch.object(Path, 'open', replacing_open):
            with self.assertRaisesRegex(ValueError, 'finite_listening_file_changed'):
                self.hint.poll(580.0)

    def test_growth_past_total_bound_during_read_is_rejected(self):
        self.log.write_bytes(MARKER)
        original_open = Path.open
        log_path = self.log

        class GrowingReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def seek(self, *args):
                return self.stream.seek(*args)

            def fileno(self):
                return self.stream.fileno()

            def read(self, *args):
                chunk = self.stream.read(*args)
                with original_open(log_path, 'ab') as append:
                    append.write(b'x' * (1048576 + 1))
                return chunk

        def growing_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path == self.log:
                return GrowingReader(stream)
            return stream

        with patch.object(Path, 'open', growing_open):
            with self.assertRaisesRegex(ValueError, 'finite_listening_byte_limit'):
                self.hint.poll(580.0)

    def test_cached_match_rechecks_replaced_file(self):
        self.log.write_bytes(MARKER)
        self.assertTrue(self.hint.poll(580.0))
        self.log.rename(self.root / 'old-stderr.log')
        self.log.write_bytes(MARKER)
        with self.assertRaisesRegex(ValueError, 'finite_listening_file_changed'):
            self.hint.poll(580.0)

    def test_cached_match_rechecks_consumed_prefix(self):
        self.log.write_bytes(MARKER)
        self.assertTrue(self.hint.poll(580.0))
        self.log.write_bytes(b'X' + MARKER[1:])
        with self.assertRaisesRegex(ValueError, 'finite_listening_file_changed'):
            self.hint.poll(580.0)

    def test_multiple_carriage_returns_do_not_match(self):
        self.log.write_bytes(MARKER[:-1] + b'\r\r\n')
        self.assertFalse(self.hint.poll(580.0))

    def test_reparse_validation_after_read_uses_synthetic_injected_seam(self):
        self.log.write_bytes(MARKER)
        original_open = Path.open
        real_checked_path = __import__(
            'gufo_control.finite_startup', fromlist=['checked_path']).checked_path
        after_read = [False]

        class ReadObserved:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def seek(self, *args):
                return self.stream.seek(*args)

            def fileno(self):
                return self.stream.fileno()

            def read(self, *args):
                result = self.stream.read(*args)
                after_read[0] = True
                return result

        def observed_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return ReadObserved(stream) if path == self.log else stream

        def synthetic_reparse_check(path, **kwargs):
            if after_read[0] and Path(path) == self.log:
                raise ValueError('reparse_path:synthetic_test_injection')
            return real_checked_path(path, **kwargs)

        with patch.object(Path, 'open', observed_open), patch(
                'gufo_control.finite_startup.checked_path', synthetic_reparse_check):
            with self.assertRaisesRegex(ValueError, 'reparse_path:synthetic_test_injection'):
                self.hint.poll(580.0)

    def test_marker_io_that_crosses_deadline_fails(self):
        self.log.write_bytes(MARKER)
        original_open = Path.open
        def late_open(path, *args, **kwargs):
            result = original_open(path, *args, **kwargs)
            if path == self.log:
                self.now[0] = 580.0
            return result
        with patch.object(Path, 'open', late_open):
            with self.assertRaisesRegex(TimeoutError, 'finite_listening_deadline'):
                self.hint.poll(580.0)

    def test_wrong_fields_and_bare_marker_do_not_schedule(self):
        for row in (b'event=listening\n',
                    MARKER.replace(b'auth=bearer', b'auth=off'),
                    MARKER.replace(b'max_connections=3', b'max_connections=4'),
                    MARKER.replace(b'max_body_bytes=16384', b'max_body_bytes=16385'),
                    MARKER.replace(b'127.0.0.1:8836', b'0.0.0.0:8836')):
            with self.subTest(row=row):
                self.log.write_bytes(row)
                hint = ListeningHint(self.root, clock=lambda: self.now[0])
                self.assertFalse(hint.poll(580.0))

    def test_absolute_deadline_and_line_bound(self):
        self.now[0] = 580.0
        self.log.write_bytes(MARKER)
        with self.assertRaisesRegex(TimeoutError, 'finite_listening_deadline'):
            self.hint.poll(580.0)
        self.now[0] = 100.0
        self.log.write_bytes(b'x' * 4097)
        with self.assertRaisesRegex(ValueError, 'finite_listening_line_limit'):
            ListeningHint(self.root, clock=lambda: self.now[0]).poll(580.0)

    def test_replacement_and_total_bound(self):
        self.log.write_bytes(b'noise\n')
        self.assertFalse(self.hint.poll(580.0))
        old = self.root / 'old-stderr.log'
        self.log.rename(old)
        self.log.write_bytes(MARKER)
        with self.assertRaisesRegex(ValueError, 'finite_listening_file_changed'):
            self.hint.poll(580.0)
        self.log.write_bytes((b'x' * 4095 + b'\n') * 257)
        with self.assertRaisesRegex(ValueError, 'finite_listening_byte_limit'):
            ListeningHint(self.root, clock=lambda: self.now[0]).poll(580.0)
