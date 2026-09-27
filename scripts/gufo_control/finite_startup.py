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


class ListeningHint:
    def __init__(self, run_dir: Path, *, clock=time.monotonic):
        self.root = checked_path(run_dir, directory=True)
        self.path = self.root / 'stderr.log'
        self.clock = clock
        self.offset = 0
        self.pending = b''
        self.identity = None
        self.matched = False

    def poll(self, deadline: float) -> bool:
        if self.clock() >= deadline:
            raise TimeoutError('finite_listening_deadline')
        if self.matched:
            return True
        checked_path(self.root, directory=True)
        checked_path(self.path)
        stat = os.stat(self.path, follow_symlinks=False)
        identity = (stat.st_dev, stat.st_ino, stat.st_ctime_ns)
        if self.identity is None:
            self.identity = identity
        if identity != self.identity or stat.st_size < self.offset:
            raise ValueError('finite_listening_file_changed')
        if stat.st_size > 1048576:
            raise ValueError('finite_listening_byte_limit')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            chunk = stream.read(min(8192, 1048577 - self.offset))
        self.offset += len(chunk)
        if self.clock() >= deadline:
            raise TimeoutError('finite_listening_deadline')
        if self.offset > 1048576:
            raise ValueError('finite_listening_byte_limit')
        self.pending += chunk
        while b'\n' in self.pending:
            line, self.pending = self.pending.split(b'\n', 1)
            if len(line) > 4096:
                raise ValueError('finite_listening_line_limit')
            if _EXACT.fullmatch(line.rstrip(b'\r')):
                self.matched = True
                return True
        if len(self.pending) > 4096:
            raise ValueError('finite_listening_line_limit')
        return False
