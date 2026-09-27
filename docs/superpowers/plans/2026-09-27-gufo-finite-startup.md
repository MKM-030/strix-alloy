# GUFO finite startup hint implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wait for the owned GUFO listener without making premature unreserved or failed readiness connections.

**Architecture:** An incremental bounded reader recognizes the exact flushed native stderr marker. It is a scheduling hint only; the later finite readiness worker must still reserve and verify GET /ready, GET /v1/models and POST1. This component never launches anything.

**Tech Stack:** Python 3.12 standard library and synthetic unittest temporary files.

## Global Constraints

- Work in `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`, baseline `acf64f8e7e14ece9612b7431e6805bbdd58cae38`.
- Preserve working installations, pinned workload and reviewed transport/ledger/assessment. No model, GPU, helper, telemetry, real sockets, recovery, D: access, persistent system settings, public push or installed acceptance changes.
- Preserve 49 GiB prelaunch physical, 24 GiB runtime physical, 12 GiB commit floors and reviewed 68/4/20 GiB GPU/host/shared envelope. Offline tests do not establish any of these live gates.
- The marker is emitted by the owned child's fresh `stderr.log`; syntax must match endpoint 127.0.0.1:8836, auth=bearer, max_connections=3, max_body_bytes=16384. It is not readiness, ownership or model correctness proof.
- Preserve an absolute readiness deadline (resume+480 seconds); missing, replaced, truncated, reparse, oversized or late log evidence fails closed. A partial line never schedules a request. No fixed sleep or extra socket probe is readiness proof.
- Bound total bytes to 1 MiB, line bytes to 4 KiB, each read to 8 KiB. A file that grows during reading must remain bounded. Recheck deadline after I/O before success.
- All code snippets are starting implementations, not exceptions to these normative requirements. Fix scoped issues through focused RED/GREEN tests; do not introduce launch authority or broaden this task.

## File map

| Path | Responsibility |
| --- | --- |
| `scripts/gufo_control/finite_startup.py` | Bounded incremental owned stderr marker reader. |
| `tests/gufo/test_finite_startup.py` | Synthetic file append/replacement/bounds/deadline tests. |

### Task 1: Owned-run listening hint

**Files:** Create `scripts/gufo_control/finite_startup.py` and `tests/gufo/test_finite_startup.py` only.

**Interfaces:** `ListeningHint(run_dir: Path, *, clock: Callable[[],float])`; `poll(deadline: float) -> bool`. `False` means no complete marker line yet. `True` means an exact marker was observed before the absolute deadline, not that the model is ready.

- [ ] **Step 1: Add `tests/gufo/test_finite_startup.py` exactly as a RED starting test.** The tests use files only and assert that partial lines cannot trigger a GET.

```python
import tempfile
import unittest
from pathlib import Path

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

    def test_marker_io_that_crosses_deadline_fails(self):
        self.log.write_bytes(MARKER)
        original_open = Path.open
        def late_open(path, *args, **kwargs):
            result = original_open(path, *args, **kwargs)
            if path == self.log:
                self.now[0] = 580.0
            return result
        from unittest.mock import patch
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
```

- [ ] **Step 2: Run RED:** set `$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'`; run `python -m unittest test_finite_startup -v`. Expected: import failure for `gufo_control.finite_startup`.
- [ ] **Step 3: Create `scripts/gufo_control/finite_startup.py` with this complete starting implementation.** It never opens a socket or reads another run's log. The timestamp is native local time; only its syntax is checked. An invalid/mismatched listening line is ignored, while replacement, reparse, deadline and resource bounds fail closed.

```python
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
```

- [ ] **Step 4: Run GREEN** with the same command. Also run `git diff --check`. A timed-out marker wait consumes zero GET slots; it never extends resume+480 seconds.


- [ ] **Step 5: Commit the two scoped files.**

```powershell
git add scripts/gufo_control/finite_startup.py tests/gufo/test_finite_startup.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat: add bounded GUFO listener startup hint"
```

## Verification boundary

Synthetic tests prove only the reader. Future phase executor and guardian integration must verify run ownership and actual readiness, live worker receipts, full coverage and cleanup. No model run or throughput claim is authorized by this task.

