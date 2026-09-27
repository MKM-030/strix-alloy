"""Bounded owned-stderr scheduling hint; never a readiness proof."""
import os
import re
import time
from pathlib import Path

from .build_identity import checked_path

_EXACT = re.compile(
    rb'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} '
    rb'\[INFO\] \[server\] event=listening '
    rb'address=http://127\.0\.0\.1:8836 auth=bearer '
    rb'max_connections=3 max_body_bytes=16384')


def _identity(info):
    return info.st_dev, info.st_ino


class ListeningHint:
    def __init__(self, run_dir: Path, *, clock=time.monotonic):
        self.root = checked_path(run_dir, directory=True)
        self.path = self.root / 'stderr.log'
        self.clock = clock
        self.offset = 0
        self.pending = b''
        self.identity = None
        self.matched = False

    def _path_stat(self):
        checked_path(self.root, directory=True)
        checked_path(self.path)
        return os.stat(self.path, follow_symlinks=False)

    def _check_file(self, info):
        identity = _identity(info)
        if self.identity is None:
            self.identity = identity
        if identity != self.identity or info.st_size < self.offset:
            raise ValueError('finite_listening_file_changed')
        if info.st_size > 1048576:
            raise ValueError('finite_listening_byte_limit')

    def _check_deadline(self, deadline):
        if self.clock() >= deadline:
            raise TimeoutError('finite_listening_deadline')

    def poll(self, deadline: float) -> bool:
        self._check_deadline(deadline)
        before = self._path_stat()
        self._check_file(before)
        if self.matched:
            self._check_deadline(deadline)
            return True
        with self.path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if _identity(opened) != self.identity:
                raise ValueError('finite_listening_file_changed')
            stream.seek(self.offset)
            chunk = stream.read(min(8192, 1048577 - self.offset))
            try:
                opened_after = os.fstat(stream.fileno())
            except (OSError, ValueError) as error:
                raise ValueError('finite_listening_file_changed') from error
        self.offset += len(chunk)
        if self.offset > 1048576:
            raise ValueError('finite_listening_byte_limit')
        after = self._path_stat()
        self._check_file(after)
        if (_identity(opened_after) != self.identity
                or _identity(after) != _identity(opened_after)):
            raise ValueError('finite_listening_file_changed')
        if opened_after.st_size < self.offset:
            raise ValueError('finite_listening_file_changed')
        if opened_after.st_size > 1048576:
            raise ValueError('finite_listening_byte_limit')
        self._check_deadline(deadline)
        self.pending += chunk
        while b'\n' in self.pending:
            line, self.pending = self.pending.split(b'\n', 1)
            if len(line) > 4096:
                raise ValueError('finite_listening_line_limit')
            candidate = line[:-1] if line.endswith(b'\r') else line
            if _EXACT.fullmatch(candidate):
                self.matched = True
                return True
        if len(self.pending) > 4096:
            raise ValueError('finite_listening_line_limit')
        return False
