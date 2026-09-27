# GUFO finite parent and bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Code snippets are starting implementations for scoped RED/GREEN refinement. This plan is not authority to run the workload.

**Goal:** Provide one fixed foreground parent that starts at most two finite guardians, remains their authenticated original parent, and starts lifecycle 2 only after actual guardian exit and validated immutable lifecycle-1 history.

**Architecture:** A small bootstrap module handles fixed hidden invocation, retained process ownership and exact evidence binding. A standard-library-only entry shim preserves bounded early failure diagnostics even when controller imports or descriptor validation fail. A separate parent module sequences handoff/status/stop and the two store-authorized lifecycles. FiniteStore remains the sole lifecycle authority; a minimal separate parent journal retains launch ambiguity and exact guardian ownership without claiming admission or cleanup.

**Tech Stack:** Python standard library, existing Windows `Popen`/`service_ipc` identity and authenticated control protocol, strict finite evidence readers, `unittest`, fake process and protocol responses.

## Global Constraints

- Planning provenance: private report `gufo-finite-parent-plan-20260927.md`, SHA256 `776C9F558F99CFAC5BE4BE4B356C1B8A0AAC6D89BA4840228FFDA728D3ED8166`, fully read by the main agent. This executable plan preserves its interfaces and bounds.

- Approved specification: `C:/Projects/strix-alloy-research/integration/docs/superpowers/specs/2026-09-26-gufo-native-design.md`. No redesign or new approval gate.
- Later target: `C:/Projects/strix-alloy-research/integration`, branch `codex/gufo-native-integration`. This planning task only writes this report.
- Prerequisites: reviewed phase implementation; `docs/superpowers/plans/2026-09-27-gufo-finite-store.md`; `docs/superpowers/plans/2026-09-27-gufo-finite-guardian.md` (adapted from private draft SHA256 `754D7CE2F9BEC2E05D5E06A42576E04AEBD9D6382D6D5825A5D6804E876A7D1E`). Its private `_run_guardian(descriptor)` and finite status fields are consumed unchanged.
- Fixed profile `ar4k-service-lifecycle-v1`; no model/path/timeout/override arguments, no installed service acceptance and no installed entrypoint changes.
- Preserve memory floors **49/24/12 GiB**, envelope **68/4/20 GiB**, readiness **480 seconds**, lifecycle **3600/900 seconds**, complete HTTP operation **60 seconds**, exactly **66/6 POSTs**, at most **240 readiness GETs**, exactly **1 models GET**, and three sockets in the guardian's single transport. The parent performs no model HTTP at all.
- Workload hash `30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38`. Store source/runtime/model/controller pins remain authoritative and unchanged.
- Preserve same-parent identity before and after handoff. Lost commit ACK is resolved only by authenticated status and durable handoff for the exact launched guardian/run. No second handoff attempt, inference replay, hidden retry, alternate endpoint or third launch.
- Only the guardian owns the inference child and its non-inherited kill-on-close Job Object. The parent retains its own guardian `Popen` handle and may terminate that exact handle only during failed bounded cleanup. It never enumerates/kills process trees or uses an image-name/PID kill.
- Actual guardian exit, return code 0, strict terminal/history hashes, phase binding, no incomplete latch and the confirmed recovery boundary all precede a fresh independent second admission.
- The parent never holds operator/evidence locks while waiting for a guardian. Its separate lock protects parent launch provenance only.
- No real test execution, socket/listener/pipe, helper, process launch, model, GPU, telemetry, recovery, D: access, settings, installed acceptance, commit or publication occurs during planning. All test code below uses temporary roots and injected fakes. Future production invocation remains blocked by the existing historical latch and absent finite qualification until those separately authorized gates are satisfied.
- The 490-second parent bootstrap/handshake bound includes the existing 10-second pre-resume handshake allowance. It does not extend guardian readiness beyond resume+480. The parent's 90-second terminal grace and 10-second forced-exit wait only observe cleanup; they do not extend serving or model operation deadlines.
- After a possibly committed handoff response, one bounded two-second authenticated status resolution is allowed within the checked existing lifecycle deadline. This observes a commit that may already have occurred; it neither retries handoff nor grants more readiness time.

## Minimal journal and command boundary

Use fixed sibling root `C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-v1-parent`. It must not live inside `FiniteStore.EVIDENCE`, where unrelated directories would correctly be rejected as orphans.

| Artifact | Why needed |
| --- | --- |
| `runner.lock` | Prevent two foreground parents from dispatching concurrently; independent of guardian locks. |
| `pair.json` | Bind this single invocation to its original parent identity and full verified manifest digest; retain evidence if the parent dies before any child can publish an endpoint. |
| `1/bootstrap.json`, `2/bootstrap.json` | Existing exact three-field IPC descriptor, with a fixed sibling endpoint path. |
| `1/launch-intent.json`, `2/launch-intent.json` | Written exclusively before `Popen`; a raised/ambiguous spawn is never treated as proof that no process was created. Timestamp bounds the parent wait. |
| `1/guardian.json`, `2/guardian.json` | Exact identity of the retained `Popen` process, not just a recyclable PID. |
| `1/bootstrap-error.json`, `2/bootstrap-error.json` | At most 8192 bytes, exclusively written by the entry shim on early failure: stage, allowlisted error code/type and bounded source locations; never raw exception messages, source lines, locals, argv, environment or credentials. It is diagnostic evidence, not cleanup proof. |
| `1/parent-terminal.json`, `2/parent-terminal.json` | Bind observed guardian exit to the exact run/result/header hashes; this corroborates, never replaces, store history. |
| `result.json` | First immutable parent outcome. Failure explicitly leaves child cleanup unknown unless authoritative store terminal evidence was verified. |

The journal does not increment a lifecycle, authorize a second attempt or retire any latch. Existing launch evidence causes a new public `run` invocation to refuse automatic retry. This is retention of an unresolved or completed one-pair operation, not a new qualification/review gate. A preflight refusal before `pair.json`/launch intent does not consume a finite attempt. Recovery or resumption of interrupted parent provenance is deliberately absent from this fixed command.

Public commands: `run` (foreground, both lifecycles), `status` (read-only disk facts), `print-only` (read-only fixed plan/static inspection). Cancellation is Ctrl+C handled by the original parent and an authenticated stop. A second independent CLI process cannot issue authenticated finite stop/status because the guardian intentionally requires the original parent; the public `status` command must not pretend otherwise.

Hidden compatibility command: `_guardian 1` or `_guardian 2`; it delegates to the same entry shim. Normal hidden spawning directly invokes `gufo_control.finite_bootstrap_entry 1` or `2` so failures importing `finite_parent`, `finite_bootstrap` or `finite_guardian` cannot escape before the diagnostic handler. The index selects a fixed bootstrap path below the parent root. There is no arbitrary bootstrap path, profile, engine argument or timeout. Direct use is unsupported and still subject to original-parent validation, guardian locks and finite admission. No new PowerShell launcher is needed.

## File map

All relative paths below are relative to `C:/Projects/strix-alloy-research/integration`.

| Path | Responsibility |
| --- | --- |
| `scripts/gufo_control/finite_bootstrap.py` | Fixed descriptor paths, hidden launch, Popen identity binding, exact-run control/header/history checks. |
| `scripts/gufo_control/finite_bootstrap_entry.py` | Minimal standard-library-only exception boundary and bounded credential-safe early failure record. |
| `tests/gufo/test_finite_bootstrap.py` | Synthetic path, identity, handoff, header and terminal contract tests. |
| `scripts/gufo_control/finite_parent.py` | One foreground parent's finite sequence, bounded failure cleanup and narrow CLI. |
| `tests/gufo/test_finite_parent.py` | Synthetic two-attempt ordering, failure/ambiguity and no-retry tests. |

No shared guardian/IPC/store changes are needed. The installed `service.py` is reference material, not a template to copy wholesale. Its temporary bootstrap-directory deletion and readiness-only returning parent are unsuitable here.

## Task 1: Fixed bootstrap and exact evidence binding

**Consumes:** `ipc._validate_descriptor`, `_process_identity`, `_match_identity`, `_reject_reparse`, `control_request`; `fs._read`, `_write`, `_run`, `_history`, `_digest`, `_current_run_markers`; `fp.PINS`; private `finite_guardian._run_guardian(descriptor)`.

**Produces:** `prepare(index, manifest, parent, started) -> dict`, `launch(index) -> Popen`, `claim(process, parent) -> dict`, `bind_endpoint(index, manifest, process, identity) -> dict`, `ledger_header(record, index, started) -> dict`, `handoff(record, digest) -> dict`, `terminal(record, manifest, index, header, process) -> dict`, `hidden(index) -> int`, `bootstrap_error(index) -> dict`, and the independent `finite_bootstrap_entry.run(index) -> int`. All paths are fixed production constants; tests patch the constants below temporary directories.

- [ ] **Step 1: Create the complete `tests/gufo/test_finite_bootstrap.py` module printed below the production block.**
- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_bootstrap -v
```

Expected: missing `finite_bootstrap` import. Do not run installed native IPC tests.

- [ ] **Step 3: Create `scripts/gufo_control/finite_bootstrap.py` with this starting implementation.**

```python
"""Fixed finite parent bootstrap and evidence checks; no import-time I/O."""
import os
import re
import subprocess
import sys
from pathlib import Path

from . import finite_profile as fp, finite_store as fs
from . import service_ipc as ipc, smoke_store
from .build_identity import checked_path
from .finite_ledger import _read as bounded_read
from .finite_workload import WORKLOAD_SHA256

ROOT = fp.PINS.evidence.with_name('gufo-service-lifecycle-v1-parent')


def directory(index):
    if type(index) is not int or index not in (1, 2):
        raise ValueError('finite_parent_index')
    return checked_path(ROOT/str(index), directory=True, exists=False)


def read(path):
    value = bounded_read(path, ipc.MAX_MESSAGE)
    if type(value) is not dict:
        raise ValueError('finite_parent_record')
    return value


def prepare(index, manifest, parent, started):
    root = directory(index)
    root.mkdir()
    descriptor = dict(parent=parent, profile_digest=fs._digest(manifest),
                      record_path=str(root/'endpoint.json'))
    fs._write(root/'bootstrap.json', descriptor)
    fs._write(root/'launch-intent.json', dict(lifecycle=index,
        descriptor_sha256=fs._digest(descriptor), started_monotonic=started))
    return descriptor


def descriptor(index):
    root = directory(index)
    pair = read(ROOT/'pair.json')
    value = read(root/'bootstrap.json')
    intent = read(root/'launch-intent.json')
    if (set(pair) != {'profile', 'parent', 'manifest_sha256'} or
            pair['profile'] != fp.PROFILE_ID or
            not fs._same(value, dict(parent=pair['parent'], profile_digest=pair['manifest_sha256'],
                                    record_path=str(root/'endpoint.json'))) or
            set(intent) != {'lifecycle', 'descriptor_sha256', 'started_monotonic'} or
            type(intent['lifecycle']) is not int or intent['lifecycle'] != index or
            intent['descriptor_sha256'] != fs._digest(value) or
            not fs._time(intent['started_monotonic'])):
        raise ValueError('finite_bootstrap_binding')
    return value


def launch(index):
    value = descriptor(index)
    peer = ipc._validate_descriptor(value)
    try:
        ipc._match_identity(value['parent'], ipc._process_identity(os.getpid()))
    finally:
        peer.close()
    return subprocess.Popen([sys.executable, '-m', 'gufo_control.finite_bootstrap_entry',
        str(index)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        cwd=str(Path(__file__).resolve().parents[2]))


def claim(process, parent):
    if process.poll() is not None:
        raise ValueError('finite_guardian_exited_before_claim')
    identity = ipc._process_identity(process.pid)
    if (process.poll() is not None or identity['pid'] != process.pid or
            identity['user_sid'] != parent['user_sid'] or
            os.path.normcase(identity['executable']) != os.path.normcase(sys.executable)):
        raise ValueError('finite_guardian_identity')
    return identity


def bind_endpoint(index, manifest, process, identity):
    record = read(directory(index)/'endpoint.json')
    run = fs._run(fp.PINS, record['run'])
    fs._current_run_markers(manifest, fp.PINS, run)
    admitted_identity = fs._read(run/'identity.json')
    if (not fs._same(record, read(run/'control.json')) or
            type(admitted_identity['lifecycle']) is not int or
            admitted_identity['lifecycle'] != index):
        raise ValueError('finite_endpoint_changed')
    expected_guardian = dict(identity, profile_digest=fs._digest(manifest))
    child = read(run/'owned.json')
    if (set(record) != {'run_id', 'profile_digest', 'endpoint', 'guardian', 'child',
                        'run', 'credentials', 'api_key'} or
            not fs._same(record['guardian'], expected_guardian) or not fs._same(record['child'], child) or
            record['profile_digest'] != fs._digest(manifest) or
            record['run'] != str(run) or record['api_key'] != '[REDACTED]' or
            record['credentials'] != str(run/'private'/'client-api-key.json') or
            type(record['run_id']) is not str or
            re.fullmatch('[0-9a-f]{32}', record['run_id']) is None or
            record['endpoint'] != r'\\.\pipe\gufo-'+record['run_id'] or
            any(type(child.get(k)) is not int or child[k] <= 0
                for k in ('pid', 'creation_time_100ns')) or
            child.get('executable') != manifest['executable']):
        raise ValueError('finite_endpoint_binding')
    if process.poll() is not None:
        raise ValueError('finite_guardian_exited')
    ipc._match_identity(identity, ipc._process_identity(process.pid))
    if process.poll() is not None:
        raise ValueError('finite_guardian_exited')
    return record


def ledger_header(record, index, started):
    run = fs._run(fp.PINS, record['run'])
    identity = fs._read(run/'identity.json')
    value = read(run/'ledger'/'identity.json')
    if (set(value) != {'schema', 'profile', 'workload_sha256', 'lifecycle',
                      'run_id', 'resumed_at', 'deadline'} or
            type(value['schema']) is not int or value['schema'] != 1 or
            value['profile'] != fp.PROFILE_ID or value['workload_sha256'] != WORKLOAD_SHA256 or
            type(value['lifecycle']) is not int or value['lifecycle'] != index or
            identity['lifecycle'] != index or identity['run'] != str(run) or
            identity['manifest_sha256'] != record['profile_digest'] or
            value['run_id'] != run.name or not fs._time(value['resumed_at']) or
            not fs._time(value['deadline']) or value['resumed_at'] < started or
            value['deadline'] != value['resumed_at'] + (3600 if index == 1 else 900)):
        raise ValueError('finite_ledger_binding')
    return value


def handoff(record, digest):
    if type(digest) is not str or re.fullmatch('[A-Fa-f0-9]{64}', digest) is None:
        raise ValueError('finite_readiness_digest')
    value = read(fs._run(fp.PINS, record['run'])/'handoff.json')
    if not fs._same(value, dict(record, state='committed', finite_readiness_sha256=digest,
                               finite_workload_sha256=WORKLOAD_SHA256)):
        raise ValueError('finite_handoff_binding')
    return value


def terminal(record, manifest, index, header, process):
    # A result file or an IPC stop ACK is insufficient: observe retained process exit.
    if process.poll() is None or process.wait(timeout=0) != 0:
        raise ValueError('finite_guardian_exit_unconfirmed')
    smoke_store._incomplete_latches(fp.PINS)
    chain = fs._history(fp.PINS)
    if len(chain) != index:
        raise ValueError('finite_terminal_history_length')
    item = chain[-1]
    run, result = item['run'], item['result']
    if (str(run) != record['run'] or item['identity']['lifecycle'] != index or
            fs._digest(result['manifest']) != fs._digest(manifest) or
            result['identity'] != record['child'] or
            result['resumed_monotonic'] != header['resumed_at'] or
            not fs._same(read(run/'ledger'/'identity.json'), header) or
            any(run.glob('result-failure-*.json'))):
        raise ValueError('finite_terminal_binding')
    return dict(lifecycle=index, run=str(run), guardian=record['guardian'],
        guardian_exit_code=0, result_sha256=fs._digest(result),
        identity_sha256=fs._digest(item['identity']), ledger_sha256=fs._digest(header),
        finite_recovery_completed_monotonic=result['finite_recovery_completed_monotonic'],
        cleanup_confirmed=True, acceptance='structural_only')


def hidden(index):
    from .finite_bootstrap_entry import run
    return run(index)


def bootstrap_error(index):
    try:
        path = directory(index)/'bootstrap-error.json'
        if not path.exists():
            return dict(state='unavailable')
        value = bounded_read(path, 8192)
        if type(value) is not dict:
            raise ValueError('bootstrap_diagnostic_shape')
        # The public parent output identifies the retained artifact, never
        # repeats untrusted diagnostic strings or claims terminal cleanup.
        return dict(state='retained', path=str(path), sha256=fs._digest(value))
    except (OSError, ValueError, TypeError):
        return dict(state='unreadable_or_invalid')
```

The private descriptor loader does not call installed launch paths. It does not read the engine credential file. Parent-owned bootstrap records are retained rather than stored under `TemporaryDirectory` and deleted. `_current_run_markers` is used only during pre-readiness binding; once terminal evidence exists, the parent uses `_history` instead.

- [ ] **Step 3b: Create `scripts/gufo_control/finite_bootstrap_entry.py` with this complete entry shim.**

```python
"""Credential-safe early bootstrap diagnostics; standard library imports only."""
import importlib
import json
import os
from pathlib import Path
import stat
import sys

# Deliberately independent of finite_profile: that import itself can fail.
# run() compares this fixed path with the normal bootstrap path before use.
ROOT = Path('C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-v1-parent')
PROFILE = 'ar4k-service-lifecycle-v1'
LIMIT = 8192
ERROR_TYPES = frozenset(('ValueError', 'RuntimeError', 'OSError', 'FileNotFoundError',
    'PermissionError', 'ImportError', 'ModuleNotFoundError', 'SyntaxError',
    'TypeError', 'KeyError', 'AttributeError', 'KeyboardInterrupt', 'SystemExit'))
ERROR_CODES = frozenset(('finite_bootstrap_binding', 'finite_parent_record',
    'finite_bootstrap_root_mismatch', 'bootstrap_fields_invalid',
    'bootstrap_record_path_invalid', 'profile_digest_invalid', 'peer_not_live',
    'peer_identity_mismatch', 'bootstrap_user_mismatch', 'credential_path_untrusted'))
SOURCE_FILES = frozenset(('finite_bootstrap_entry.py', 'finite_bootstrap.py',
    'finite_parent.py', 'finite_guardian.py', 'finite_profile.py', 'finite_store.py',
    'finite_session.py', 'finite_phase.py', 'service_ipc.py', 'smoke_guard.py'))


def _checked(path, *, directory=False):
    if not path.is_absolute():
        raise ValueError('diagnostic_path')
    for candidate in (path, *path.parents):
        if candidate.exists():
            info = candidate.lstat()
            if candidate.is_symlink() or getattr(info, 'st_file_attributes', 0) & getattr(
                    stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                raise ValueError('diagnostic_reparse')
    if directory and not path.is_dir():
        raise ValueError('diagnostic_directory_missing')
    return path


def _failure(index, stage, error):
    root = _checked(ROOT/str(index), directory=True)
    # Never create directories or invent a launch record to retain an error.
    for path in (ROOT/'pair.json', root/'launch-intent.json'):
        _checked(path)
        if not path.is_file():
            raise ValueError('diagnostic_launch_missing')
    frames = []
    trace = error.__traceback__
    while trace is not None:
        name = Path(trace.tb_frame.f_code.co_filename).name
        frames.append(dict(file=name if name in SOURCE_FILES else 'dependency',
                           line=trace.tb_lineno))
        frames = frames[-8:]
        trace = trace.tb_next
    if isinstance(error, SyntaxError):
        name = Path(error.filename or '').name
        frames = (frames+[dict(file=name if name in SOURCE_FILES else 'dependency',
                              line=error.lineno if type(error.lineno) is int else 0)])[-8:]
    code = error.args[0] if error.args and type(error.args[0]) is str else None
    kind = type(error).__name__
    value = dict(schema=1, profile=PROFILE, lifecycle=index, stage=stage,
        error_type=kind if kind in ERROR_TYPES else 'Exception',
        error_code=code if code in ERROR_CODES else 'unclassified',
        locations=frames, cleanup_confirmed=None, retry_authorized=False)
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False)+'\n').encode('utf-8')
    if len(data) > LIMIT:
        raise ValueError('diagnostic_size')
    path = _checked(root/'bootstrap-error.json')
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def run(index):
    if type(index) is not int or index not in (1, 2):
        return 2
    stage = 'import_bootstrap'
    try:
        bootstrap = importlib.import_module('gufo_control.finite_bootstrap')
        if bootstrap.ROOT != ROOT:
            raise ValueError('finite_bootstrap_root_mismatch')
        stage = 'validate_descriptor'
        descriptor = bootstrap.descriptor(index)
        stage = 'import_guardian'
        guardian = importlib.import_module('gufo_control.finite_guardian')
        stage = 'guardian'
        result = guardian._run_guardian(descriptor)
        return 0 if result.get('success') is True else 2
    except BaseException as error:
        try:
            _failure(index, stage, error)
        except BaseException:
            # No unsafe fallback file/console or overwrite. The parent retains
            # launch intent, nonzero exit and an unavailable-diagnostic state.
            pass
        return 2


if __name__ == '__main__':
    index = int(sys.argv[1]) if len(sys.argv) == 2 and sys.argv[1] in ('1', '2') else None
    raise SystemExit(run(index))
```

The package `__init__.py` is currently a docstring-only module, verified during this correction. Keep it free of runtime imports so the entry exception boundary can precede controller imports. The shim mirrors the existing exclusive/fsynced JSON write discipline because importing `finite_store` to report a failed controller import would defeat this boundary. It is one failure record, not a logging framework or stream collector. Standard output/error remain hidden; uncaught controller errors are converted to the bounded diagnostic. Runtime/child logs already owned by the guardian are unchanged. Unavailable filesystem access is reported honestly through retained launch intent and nonzero exit, not another output location.

- [ ] **Step 4: Test module for Step 1.**

```python
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from gufo_control import finite_bootstrap as b, finite_store as fs
from gufo_control import finite_bootstrap_entry as entry
from gufo_control.finite_workload import WORKLOAD_SHA256


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parent = dict(pid=1, creation_time_100ns=2,
            executable='python.exe', user_sid='S-1-test')
        self.manifest = {'profile': b.fp.PROFILE_ID, 'executable': 'gufo.exe'}
        self.patch = patch.object(b, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        fs._write(self.root/'pair.json', dict(profile=b.fp.PROFILE_ID,
            parent=self.parent, manifest_sha256=fs._digest(self.manifest)))

    def test_only_two_fixed_bootstrap_paths(self):
        for invalid in (0, 3, True, '../1', '1'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                b.directory(invalid)
        value = b.prepare(1, self.manifest, self.parent, 100.0)
        self.assertEqual(b.descriptor(1), value)
        self.assertEqual(value['record_path'], str(self.root/'1'/'endpoint.json'))
        with self.assertRaises(FileExistsError):
            b.prepare(1, self.manifest, self.parent, 101.0)

    def test_changed_descriptor_or_launch_intent_is_refused(self):
        b.prepare(1, self.manifest, self.parent, 100.0)
        original = b.read
        def tampered(path):
            value = original(path)
            if path.name == 'launch-intent.json':
                value['descriptor_sha256'] = '0'*64
            return value
        with patch.object(b, 'read', side_effect=tampered), \
             self.assertRaisesRegex(ValueError, 'finite_bootstrap_binding'):
            b.descriptor(1)

    def test_claim_brackets_pid_identity_with_retained_process_exit(self):
        process = SimpleNamespace(pid=7, poll=Mock(side_effect=[None, 0]))
        identity = dict(self.parent, pid=7, executable=b.sys.executable)
        with patch.object(b.ipc, '_process_identity', return_value=identity), \
             self.assertRaisesRegex(ValueError, 'finite_guardian_identity'):
            b.claim(process, self.parent)

    def test_hidden_spawn_has_fixed_module_no_path_override_and_no_window(self):
        b.prepare(1, self.manifest, self.parent, 100.0)
        peer = SimpleNamespace(close=Mock())
        with patch.object(b.ipc, '_validate_descriptor', return_value=peer), \
             patch.object(b.ipc, '_process_identity', return_value=self.parent), \
             patch.object(b.subprocess, 'Popen', return_value=object()) as spawn:
            b.launch(1)
        args, kwargs = spawn.call_args
        self.assertEqual(args[0], [b.sys.executable, '-m',
            'gufo_control.finite_bootstrap_entry', '1'])
        self.assertTrue(kwargs['close_fds'])
        self.assertEqual(kwargs['creationflags'], b.subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs['stdin'], b.subprocess.DEVNULL)
        peer.close.assert_called_once()

    def test_import_failure_is_bounded_secret_free_and_immutable(self):
        b.prepare(1, self.manifest, self.parent, 100.0)
        secret = 'synthetic-private-key-'+'x'*20000
        with patch.object(entry, 'ROOT', self.root), \
             patch.object(entry.importlib, 'import_module', side_effect=RuntimeError(secret)):
            self.assertEqual(entry.run(1), 2)
        path = self.root/'1'/'bootstrap-error.json'
        first = path.read_bytes()
        value = fs._read(path)
        self.assertLessEqual(len(first), 8192)
        self.assertNotIn(b'synthetic-private-key', first)
        self.assertEqual(value['stage'], 'import_bootstrap')
        self.assertEqual(value['error_type'], 'RuntimeError')
        self.assertIsNone(value['cleanup_confirmed'])
        self.assertFalse(value['retry_authorized'])
        with patch.object(entry, 'ROOT', self.root), \
             patch.object(entry.importlib, 'import_module', side_effect=ValueError('changed')):
            self.assertEqual(entry.run(1), 2)
        self.assertEqual(path.read_bytes(), first)
        self.assertEqual(b.bootstrap_error(1)['state'], 'retained')

    def test_descriptor_failure_precedes_guardian_import_and_is_retained(self):
        b.prepare(1, self.manifest, self.parent, 100.0)
        with patch.object(entry, 'ROOT', self.root), \
             patch.object(entry.importlib, 'import_module', return_value=b) as imports, \
             patch.object(b, 'descriptor', side_effect=ValueError('finite_bootstrap_binding')):
            self.assertEqual(entry.run(1), 2)
        imports.assert_called_once_with('gufo_control.finite_bootstrap')
        value = fs._read(self.root/'1'/'bootstrap-error.json')
        self.assertEqual(value['stage'], 'validate_descriptor')
        self.assertEqual(value['error_code'], 'finite_bootstrap_binding')
        self.assertIsNone(value['cleanup_confirmed'])

    def test_endpoint_binds_exact_popen_guardian_before_handoff(self):
        run = self.root/'run-1'
        guardian = dict(self.parent, pid=7, profile_digest=fs._digest(self.manifest))
        child = dict(pid=9, creation_time_100ns=10, executable='gufo.exe')
        record = dict(run_id='a'*32, profile_digest=fs._digest(self.manifest),
            endpoint=r'\\.\pipe\gufo-'+'a'*32, guardian=guardian,
            child=child, run=str(run), credentials=str(run/'private'/'client-api-key.json'),
            api_key='[REDACTED]')
        def read(path):
            return child if path.name == 'owned.json' else record
        process = SimpleNamespace(pid=7, poll=lambda: None)
        claimed = dict(self.parent, pid=7)
        with patch.object(b, 'read', side_effect=read), \
             patch.object(fs, '_run', return_value=run), \
             patch.object(fs, '_read', return_value={'lifecycle': 1}), \
             patch.object(fs, '_current_run_markers'), \
             patch.object(b.ipc, '_process_identity', return_value=claimed):
            self.assertEqual(b.bind_endpoint(1, self.manifest, process, claimed), record)
            with self.assertRaisesRegex(ValueError, 'finite_endpoint_binding'):
                b.bind_endpoint(1, self.manifest, process, dict(claimed, pid=88))

    def test_header_exact_run_lifecycle_and_deadline(self):
        run = self.root/'run-1'
        record = {'run': str(run), 'profile_digest': 'a'*64}
        identity = dict(lifecycle=1, run=str(run), manifest_sha256='a'*64)
        header = dict(schema=1, profile=b.fp.PROFILE_ID, workload_sha256=WORKLOAD_SHA256,
            lifecycle=1, run_id='run-1', resumed_at=110.0, deadline=3710.0)
        with patch.object(fs, '_run', return_value=run), \
             patch.object(fs, '_read', return_value=identity), \
             patch.object(b, 'read', return_value=header):
            self.assertEqual(b.ledger_header(record, 1, 100.0), header)
            for key, bad in (('deadline', 3711.0), ('run_id', 'other'),
                             ('lifecycle', 2), ('schema', True)):
                with self.subTest(key=key), patch.object(b, 'read', return_value=dict(header, **{key: bad})), \
                     self.assertRaisesRegex(ValueError, 'finite_ledger_binding'):
                    b.ledger_header(record, 1, 100.0)

    def test_handoff_requires_exact_record_and_digest(self):
        run = self.root/'run-1'
        record = {'run': str(run), 'run_id': 'a'*32}
        good = dict(record, state='committed', finite_readiness_sha256='B'*64,
                    finite_workload_sha256=WORKLOAD_SHA256)
        with patch.object(fs, '_run', return_value=run), patch.object(b, 'read', return_value=good):
            self.assertEqual(b.handoff(record, 'B'*64), good)
            with self.assertRaises(ValueError):
                b.handoff(record, 'C'*64)

    def test_terminal_requires_actual_exit_before_history(self):
        process = SimpleNamespace(poll=lambda: None, wait=Mock())
        with patch.object(fs, '_history') as history, \
             self.assertRaisesRegex(ValueError, 'finite_guardian_exit_unconfirmed'):
            b.terminal({}, self.manifest, 1, {}, process)
        history.assert_not_called()
        process.wait.assert_not_called()

    def test_terminal_rejects_nonzero_exit_even_if_store_looks_clean(self):
        process = SimpleNamespace(poll=lambda: 2, wait=lambda **kwargs: 2)
        with patch.object(fs, '_history') as history, self.assertRaises(ValueError):
            b.terminal({}, self.manifest, 1, {}, process)
        history.assert_not_called()

    def test_terminal_binds_result_child_header_and_history(self):
        run = self.root/'run-1'
        run.mkdir()
        header = {'resumed_at': 110.0, 'deadline': 3710.0}
        result = dict(manifest=self.manifest, identity={'pid': 9},
            resumed_monotonic=110.0, finite_recovery_completed_monotonic=200.0)
        identity = {'lifecycle': 1}
        item = dict(run=run, result=result, identity=identity)
        record = dict(run=str(run), child={'pid': 9}, guardian=self.parent)
        process = SimpleNamespace(poll=lambda: 0, wait=lambda **kwargs: 0)
        with patch.object(b.smoke_store, '_incomplete_latches'), \
             patch.object(fs, '_history', return_value=[item]), \
             patch.object(b, 'read', return_value=header):
            value = b.terminal(record, self.manifest, 1, header, process)
            self.assertTrue(value['cleanup_confirmed'])
            self.assertEqual(value['result_sha256'], fs._digest(result))
            with self.assertRaises(ValueError):
                b.terminal(dict(record, child={'pid': 99}), self.manifest, 1, header, process)
```

- [ ] **Step 5: Confirm GREEN and read-only helper regressions.**

```powershell
python -B -m unittest test_finite_bootstrap test_finite_store test_service_ipc.ProtocolTests -v
git diff --check
```

Expected: selected synthetic tests PASS. No `NativeTests`, actual `launch` call, subprocess or telemetry. Review this unit independently; later parent task consumes these exact signatures. Planning performs no commit.

## Task 2: One original parent, two verified terminal lifecycles

**Consumes:** Task 1 helpers; `FiniteStore.verify_static()`; `fs._history(fp.PINS)`; `ipc.control_request(record: dict, command: str, *, timeout_seconds: float) -> dict`; finite guardian status `finite_complete`, `finite_readiness_sha256`, `handoff_confirmed`, exact `run/guardian/child`.

**Produces:** `run_pair() -> dict`, `_run_one(index, manifest, parent) -> dict`, `main(argv=None) -> int`. The public foreground process stays alive throughout both lifecycles. `status` and `print-only` never create a lock, directory, process, connection or collector.

- [ ] **Step 1: Create the complete `tests/gufo/test_finite_parent.py` module below the production block.**
- [ ] **Step 2: Run RED.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_parent -v
```

Expected: absent `finite_parent` module.

- [ ] **Step 3: Create `scripts/gufo_control/finite_parent.py` with this complete starting implementation.**

```python
"""Fixed foreground finite parent. It never sends a model HTTP request."""
import argparse
import json
import os
import time

from . import finite_bootstrap as b, finite_store as fs
from . import service_ipc as ipc, operator_store, smoke_store
from .build_identity import checked_path

BOOTSTRAP_SECONDS = 490.0
TERMINAL_SECONDS = 90.0
FORCED_EXIT_SECONDS = 10.0


def _request(record, command, timeout):
    if ipc._RETAINED_CLEANUP:
        raise RuntimeError('finite_parent_ipc_cleanup_unconfirmed')
    value = ipc.control_request(record, command, timeout_seconds=timeout)
    if value.get('cleanup_error') or ipc._RETAINED_CLEANUP:
        raise RuntimeError('finite_parent_ipc_cleanup_unconfirmed')
    return value


def _status(record, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('finite_parent_deadline')
    value = _request(record, 'status', min(2.0, remaining))
    if any(value.get(k) != record[k] for k in ('run', 'guardian', 'child')):
        raise ValueError('finite_parent_status_identity')
    if value.get('handoff_confirmed') is not True:
        raise ValueError('finite_parent_commit_unconfirmed')
    b.handoff(record, value.get('finite_readiness_sha256'))
    return value


def _wait_exit(process, deadline):
    while process.poll() is None:
        if time.monotonic() >= deadline:
            return False
        time.sleep(.05)
    process.wait(timeout=0)
    return True


def _abort(process, record):
    # A spawn exception without a returned Popen cannot establish absence of
    # a child. No guessed PID, endpoint search or process-tree operation.
    if process is None:
        return dict(guardian_exit_confirmed=None, cleanup_confirmed=None,
                    failure_cleanup='spawn_unconfirmed')
    if process.poll() is None and record is not None and not ipc._RETAINED_CLEANUP:
        try:
            _request(record, 'stop', 2.0)
        except BaseException:
            pass
    exited = _wait_exit(process, time.monotonic()+TERMINAL_SECONDS)
    forced = False
    if not exited:
        # Popen uses the retained owned process handle on Windows. This closes
        # only our guardian; its sole Job handle handles its own inference child.
        try:
            process.terminate()
            forced = True
        except OSError:
            pass
        exited = _wait_exit(process, time.monotonic()+FORCED_EXIT_SECONDS)
    return dict(guardian_exit_confirmed=exited, cleanup_confirmed=None,
                failure_cleanup='forced_guardian_exit' if forced else 'terminal_unverified')


def _run_one(index, manifest, parent):
    process = record = None
    started = time.monotonic()
    root = b.directory(index)
    try:
        b.prepare(index, manifest, parent, started)
        process = b.launch(index)
        identity = b.claim(process, parent)
        fs._write(root/'guardian.json', dict(identity=identity))
        handshake_deadline = started+BOOTSTRAP_SECONDS
        while not (root/'endpoint.json').exists():
            if process.poll() is not None or time.monotonic() >= handshake_deadline:
                raise ValueError('finite_guardian_bootstrap_unconfirmed')
            time.sleep(.05)
        record = b.bind_endpoint(index, manifest, process, identity)
        remaining = handshake_deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('finite_parent_handshake_timeout')
        response = _request(record, 'handoff', remaining)
        if response.get('state') not in ('committed', 'indeterminate'):
            raise ValueError('finite_parent_handoff_refused')
        # Exactly one handoff. Both normal ACK and an ambiguous ACK are resolved
        # by authenticated status plus exact durable handoff binding.
        header = b.ledger_header(record, index, started)
        now = time.monotonic()
        if header['resumed_at'] > now or now >= header['deadline']:
            raise ValueError('finite_parent_resume_chronology')
        status = _status(record, min(header['deadline'], now+2.0))
        while status.get('finite_complete') is not True:
            if process.poll() is not None:
                raise ValueError('finite_guardian_exited_before_coverage')
            time.sleep(min(.1, max(0, header['deadline']-time.monotonic())))
            status = _status(record, header['deadline'])
        remaining = header['deadline']-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('finite_parent_lifetime_exhausted')
        stopped = _request(record, 'stop', min(2.0, remaining))
        if stopped.get('state') != 'stopping':
            raise ValueError('finite_parent_stop_unconfirmed')
        if not _wait_exit(process, time.monotonic()+TERMINAL_SECONDS):
            raise ValueError('finite_parent_guardian_exit_timeout')
        result = b.terminal(record, manifest, index, header, process)
        fs._write(root/'parent-terminal.json', result)
        return result
    except BaseException as error:
        failure = dict(lifecycle=index, success=False,
            reason=type(error).__name__+':'+str(error), **_abort(process, record),
            bootstrap_error=b.bootstrap_error(index))
        # No replacement of an existing terminal report. A failed write is
        # reported by the pair and retained launch intent still blocks retries.
        if root.exists() and not (root/'parent-terminal.json').exists():
            fs._write(root/'parent-terminal.json', failure)
        raise RuntimeError('finite_lifecycle_failed:'+str(index)) from error


def run_pair():
    store = fs.FiniteStore()
    # Static refusal precedes journal creation and is not a consumed lifecycle.
    manifest = store.verify_static()
    if fs._history(b.fp.PINS):
        raise ValueError('finite_parent_requires_fresh_pair')
    checked_path(b.ROOT, directory=True, exists=False)
    with operator_store.exclusive(b.ROOT):
        if any(path.name != 'runner.lock' for path in b.ROOT.iterdir()):
            raise ValueError('finite_parent_prior_launch_evidence')
        fresh = store.verify_static()
        if fs._digest(fresh) != fs._digest(manifest) or fs._history(b.fp.PINS):
            raise ValueError('finite_parent_preflight_changed')
        parent = ipc._process_identity(os.getpid())
        fs._write(b.ROOT/'pair.json', dict(profile=b.fp.PROFILE_ID,
            parent=parent, manifest_sha256=fs._digest(manifest)))
        completed = []
        try:
            for index in (1, 2):
                # The first guardian has exited before this branch can occur.
                # Fresh baseline acquisition remains in the new guardian.
                if index == 2:
                    next_manifest = store.verify_static()
                    chain = fs._history(b.fp.PINS)
                    if (len(chain) != 1 or
                            fs._digest(chain[0]['result']) != completed[0]['result_sha256'] or
                            fs._digest(next_manifest) != fs._digest(manifest)):
                        raise ValueError('finite_parent_first_terminal_changed')
                completed.append(_run_one(index, manifest, parent))
            smoke_store._incomplete_latches(b.fp.PINS)
            chain = fs._history(b.fp.PINS)
            if len(chain) != 2 or any(fs._digest(item['result']) != proof['result_sha256']
                                     for item, proof in zip(chain, completed)):
                raise ValueError('finite_parent_final_history_changed')
            result = dict(profile=b.fp.PROFILE_ID, success=True,
                completed_lifecycles=completed, acceptance='structural_only',
                installed_service_accepted=False)
        except BaseException as error:
            result = dict(profile=b.fp.PROFILE_ID, success=False,
                completed_lifecycles=completed, acceptance='not_qualified',
                installed_service_accepted=False, cleanup_confirmed=None,
                reason=type(error).__name__+':'+str(error),
                bootstrap_error=b.bootstrap_error(min(len(completed)+1, 2)))
        fs._write(b.ROOT/'result.json', result)
        return result


def inspect():
    result = fs.inspect_finite_profile()
    result.update(mode='read_only', parent_process_live=None,
                  parent_state='not_started', parent_success=None)
    if (b.ROOT/'pair.json').exists():
        b.read(b.ROOT/'pair.json')
        result['parent_state'] = 'recorded; live_state_not_queried'
    if (b.ROOT/'result.json').exists():
        parent = fs._read(b.ROOT/'result.json')
        result['parent_state'] = 'terminal_recorded'
        result['parent_success'] = parent.get('success')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fixed finite GUFO qualification parent')
    parser.add_argument('command', choices=('run', 'status', 'print-only', '_guardian'))
    parser.add_argument('private_index', nargs='?', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command == '_guardian':
        if args.private_index not in ('1', '2') or os.name != 'nt':
            parser.error('invalid private finite bootstrap')
        return b.hidden(int(args.private_index))
    if args.private_index is not None:
        parser.error('public commands accept no additional arguments')
    try:
        if args.command == 'run':
            if os.name != 'nt':
                parser.error('Windows required')
            result = run_pair()
            code = 0 if result['success'] else 2
        else:
            result = inspect()
            if args.command == 'print-only':
                result.update(would_launch=False, profile=b.fp.PROFILE_ID,
                    lifecycle_seconds=[3600, 900], readiness_seconds=480,
                    post_counts=[66, 6], client_http_requests=0)
            code = 0 if result.get('history_valid') else 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        result, code = dict(profile=b.fp.PROFILE_ID, success=False,
            reason=type(error).__name__+':'+str(error), cleanup_confirmed=None), 2
    print(json.dumps(result, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
```

The parent observes only finite control state. It neither reports raw status memory as its own admission decision nor opens the engine endpoint. `_status` failure stops the sequence; it does not turn an unknown handoff into another launch. After a failed bootstrap, `Popen` exit alone is never labeled cleanup or recovery. Where a retained process exists, bounded cancellation/termination touches that exact guardian only, preserving all journal and run artifacts.

The status response carries no fixed lifetime field in the frozen guardian plan. `ledger_header` therefore recovers the existing exact immutable header, verifies the finite schema/run/index/manifest relationship and checks fixed arithmetic. The parent rejects a future resume timestamp and binds terminal `resumed_monotonic` and unchanged header bytes through canonical values. The guardian independently enforces the same hard deadline.

- [ ] **Step 4: Test module for Step 1.**

```python
from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from gufo_control import finite_parent as p
from gufo_control import finite_bootstrap_entry as entry


class ParentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(p.b, 'ROOT', self.root))
        self.stack.enter_context(patch.object(p.ipc, '_RETAINED_CLEANUP', []))

    def test_indeterminate_handoff_is_resolved_once_without_relaunch(self):
        directory = self.root/'2'
        directory.mkdir()
        (directory/'endpoint.json').write_bytes(b'{}')
        process = SimpleNamespace(pid=7, poll=lambda: None)
        record = {'run': 'fixed-run', 'guardian': {'pid': 7}, 'child': {'pid': 9}}
        calls = []
        clock = [100.0]
        def request(got, command, timeout):
            calls.append(command)
            if command == 'handoff':
                clock[0] = 590.0  # Original handshake timeout, after a possible commit.
            return {'state': 'indeterminate' if command == 'handoff' else 'stopping'}
        with patch.object(p.b, 'prepare'), patch.object(p.b, 'launch', return_value=process) as launch, \
             patch.object(p.b, 'claim', return_value={'pid': 7}), \
             patch.object(p.b, 'bind_endpoint', return_value=record), \
             patch.object(p.fs, '_write'), patch.object(p, '_request', side_effect=request), \
             patch.object(p, '_status', return_value={'finite_complete': True}) as status, \
             patch.object(p.b, 'ledger_header', return_value={'resumed_at': 110.0, 'deadline': 1010.0}), \
             patch.object(p.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(p, '_wait_exit', return_value=True), \
             patch.object(p.b, 'terminal', return_value={'cleanup_confirmed': True}):
            self.assertTrue(p._run_one(2, {}, {})['cleanup_confirmed'])
        launch.assert_called_once_with(2)
        self.assertEqual(calls, ['handoff', 'stop'])
        status.assert_called_once_with(record, 592.0)

    def test_status_exact_identity_and_durable_handoff_required(self):
        record = {'run': 'run-1', 'guardian': {'pid': 7}, 'child': {'pid': 9}}
        good = dict(record, handoff_confirmed=True, finite_readiness_sha256='A'*64)
        with patch.object(p.time, 'monotonic', return_value=100.0), \
             patch.object(p, '_request', return_value=good), \
             patch.object(p.b, 'handoff') as handoff:
            self.assertEqual(p._status(record, 200.0), good)
            handoff.assert_called_once_with(record, 'A'*64)
        with patch.object(p.time, 'monotonic', return_value=100.0), \
             patch.object(p, '_request', return_value=dict(good, run='another')), \
             self.assertRaisesRegex(ValueError, 'finite_parent_status_identity'):
            p._status(record, 200.0)

    def test_control_cleanup_ambiguity_prevents_more_connections(self):
        with patch.object(p.ipc, '_RETAINED_CLEANUP', [object()]), \
             patch.object(p.ipc, 'control_request') as request, \
             self.assertRaises(RuntimeError):
            p._request({}, 'status', 2)
        request.assert_not_called()

    def test_spawn_failure_retains_intent_and_never_claims_cleanup(self):
        parent = {'pid': 1}
        with patch.object(p.b, 'launch', side_effect=OSError('synthetic_spawn_failure')), \
             self.assertRaisesRegex(RuntimeError, 'finite_lifecycle_failed:1'):
            p._run_one(1, {'profile': 'synthetic'}, parent)
        self.assertTrue((self.root/'1'/'launch-intent.json').exists())
        failure = p.fs._read(self.root/'1'/'parent-terminal.json')
        self.assertIsNone(failure['guardian_exit_confirmed'])
        self.assertIsNone(failure['cleanup_confirmed'])
        self.assertEqual(failure['failure_cleanup'], 'spawn_unconfirmed')

    def test_failed_cleanup_terminates_only_retained_owned_guardian(self):
        process = SimpleNamespace(poll=lambda: None, terminate=Mock())
        with patch.object(p, '_wait_exit', side_effect=[False, True]), \
             patch.object(p, '_request') as request:
            result = p._abort(process, None)
        process.terminate.assert_called_once()
        request.assert_not_called()
        self.assertTrue(result['guardian_exit_confirmed'])
        self.assertIsNone(result['cleanup_confirmed'])

    def test_failure_before_guardian_run_is_retained_and_no_retry_is_dispatched(self):
        @contextmanager
        def lock(root):
            yield
        parent = dict(pid=1, creation_time_100ns=2, executable='python.exe', user_sid='S-1-test')
        store = SimpleNamespace(verify_static=lambda: {'fixed': True})
        process = SimpleNamespace(pid=7, poll=lambda: 2, wait=lambda **kwargs: 2)
        def launch(index):
            self.assertEqual(entry.run(index), 2)
            return process
        with patch.object(entry, 'ROOT', self.root), \
             patch.object(entry.importlib, 'import_module', side_effect=ImportError('synthetic-secret')), \
             patch.object(p.operator_store, 'exclusive', lock), \
             patch.object(p.fs, 'FiniteStore', return_value=store), \
             patch.object(p.fs, '_history', return_value=[]), \
             patch.object(p.ipc, '_process_identity', return_value=parent), \
             patch.object(p.b, 'launch', side_effect=launch) as launches:
            result = p.run_pair()
            self.assertFalse(result['success'])
            self.assertIsNone(result['cleanup_confirmed'])
            self.assertEqual(result['bootstrap_error']['state'], 'retained')
            self.assertFalse((self.root/'2').exists())
            with self.assertRaisesRegex(ValueError, 'finite_parent_prior_launch_evidence'):
                p.run_pair()
            launches.assert_called_once_with(1)
        raw = (self.root/'1'/'bootstrap-error.json').read_bytes()
        self.assertNotIn(b'synthetic-secret', raw)
        self.assertTrue((self.root/'1'/'launch-intent.json').exists())
        self.assertEqual(p.fs._read(self.root/'1'/'parent-terminal.json')['bootstrap_error']['state'], 'retained')

    def pair_fixture(self, *, fail_first=False, changed_first=False):
        manifest = {'fixed': True}
        first, second = {'life': 1}, {'life': 2}
        chain = []
        events = []
        @contextmanager
        def lock(root):
            self.assertEqual(root, self.root)
            events.append('parent_lock')
            yield
        store = SimpleNamespace(verify_static=Mock(return_value=manifest))
        def one(index, got_manifest, parent):
            events.append(('launch', index))
            if index == 1 and fail_first:
                raise RuntimeError('synthetic_first_failure')
            value = first if index == 1 else second
            chain.append({'result': value})
            events.append(('guardian_exit_and_terminal_verified', index))
            digest = p.fs._digest(value)
            if index == 1 and changed_first:
                chain[0] = {'result': {'changed': True}}
            return dict(result_sha256=digest, lifecycle=index)
        self.stack.enter_context(patch.object(p.operator_store, 'exclusive', lock))
        self.stack.enter_context(patch.object(p.fs, 'FiniteStore', return_value=store))
        self.stack.enter_context(patch.object(p.fs, '_history', side_effect=lambda pins: list(chain)))
        self.stack.enter_context(patch.object(p.ipc, '_process_identity', return_value={'pid': 1}))
        self.stack.enter_context(patch.object(p.smoke_store, '_incomplete_latches'))
        self.stack.enter_context(patch.object(p, '_run_one', side_effect=one))
        return events, store

    def test_second_only_after_actual_first_exit_and_terminal_verification(self):
        events, store = self.pair_fixture()
        result = p.run_pair()
        self.assertTrue(result['success'])
        self.assertEqual(events, ['parent_lock', ('launch', 1),
            ('guardian_exit_and_terminal_verified', 1), ('launch', 2),
            ('guardian_exit_and_terminal_verified', 2)])
        self.assertEqual(store.verify_static.call_count, 3)
        self.assertFalse(result['installed_service_accepted'])

    def test_first_failure_never_starts_second(self):
        events, store = self.pair_fixture(fail_first=True)
        self.assertFalse(p.run_pair()['success'])
        self.assertNotIn(('launch', 2), events)
        self.assertTrue((self.root/'pair.json').exists())
        self.assertTrue((self.root/'result.json').exists())

    def test_changed_first_history_refuses_second(self):
        events, store = self.pair_fixture(changed_first=True)
        self.assertFalse(p.run_pair()['success'])
        self.assertNotIn(('launch', 2), events)

    def test_prior_parent_evidence_is_never_overwritten_or_retried(self):
        events, store = self.pair_fixture()
        (self.root/'pair.json').write_bytes(b'{"prior":true}')
        with self.assertRaisesRegex(ValueError, 'finite_parent_prior_launch_evidence'):
            p.run_pair()
        self.assertEqual((self.root/'pair.json').read_bytes(), b'{"prior":true}')
        self.assertFalse(any(isinstance(item, tuple) for item in events))

    def test_read_only_inspection_never_dispatches_or_creates_directory(self):
        with patch.object(p.fs, 'inspect_finite_profile', return_value={'history_valid': True}), \
             patch.object(p.b, 'launch') as launch, \
             patch.object(p.ipc, 'control_request') as request:
            value = p.inspect()
        self.assertEqual(value['mode'], 'read_only')
        self.assertEqual(list(self.root.iterdir()), [])
        launch.assert_not_called()
        request.assert_not_called()
```

- [ ] **Step 5: Confirm GREEN, then scoped integration regressions.**

```powershell
$env:PYTHONPATH = 'scripts;tests/gufo'
python -B -m unittest test_finite_bootstrap test_finite_parent -v
python -B -m unittest test_finite_guardian test_finite_guardian_seams test_finite_profile test_finite_store test_service_ipc.ProtocolTests -v
git diff --check
git diff --stat
```

Expected: selected synthetic tests PASS. The phase/startup/transport suites are predecessor verification and need only be rerun if implementation integration changes those paths; this plan does not modify them. Avoid broad discovery, `NativeTests`, real bootstrap, live status, model endpoints and system changes. Review the five scoped files. Any later commit follows the main task's existing authorization; planning performs none.

## Self-review and concrete interface concerns

- The original parent remains foreground. The only normal path to launch 2 returns from `_run_one(1)` after retained process exit and authoritative immutable history verification; `verify_static` then runs again, and the new guardian collects its fresh baseline. FiniteStore's monotonic recovery/admission ordering still enforces the safety boundary.
- The separate parent root is not included in finite lifecycle history and never writes an attempt marker or incomplete latch. Prior evidence refuses an automatic fresh pair without deleting anything. This keeps ambiguous pre-attempt spawn evidence without changing FiniteStore's attempt count.
- No model client or engine credential read exists. Parent-only IPC calls cannot increase 66+6 POST counts. There is exactly one handoff per started guardian and a fixed `(1, 2)` loop, no third attempt or fallback model launch.
- Startup descriptor/endpoint/owned identity are bound to the Popen process before handoff. PID reuse is excluded by retained-handle polling around fresh identity reads. Failed cleanup uses that same Popen handle only and labels inference cleanup unknown.
- Early import/descriptor/guardian-entry exceptions are retained exclusively in a fixed, checked, at-most-8192-byte diagnostic with a stage, bounded source locations and allowlisted error classification. No raw exception text or credentials reach console, argv or that file. A synthetic pre-guardian failure test verifies preserved evidence, unknown cleanup, no second launch and refusal to retry an existing parent operation. Write failure leaves diagnostics unavailable and does not change the failed exit or launch retention.
- Shared guardian status lacks resume/deadline fields. The plan consumes the checked ledger header instead of expanding that status API. It binds admitted run, manifest hash, lifecycle, workload and terminal resume time. The parent does not extend the guardian's deadline when resolving an ambiguous ACK.
- The existing `control_request` can return `indeterminate` at its original call deadline. The parent reads and validates the already-created ledger header, then uses a separate two-second status-resolution bound clipped to the original lifecycle deadline. The synthetic lost-ACK test reaches the full 490-second handshake timeout and proves there is one status resolution and no second handoff/launch. This is observation of a possibly durable commit, not an extension of readiness.
- Concrete public interface limitation: independent CLI stop cannot satisfy original-parent authentication. This finite one-pair command intentionally provides foreground Ctrl+C cancellation and read-only disk status, not an unauthenticated administrative stop. The installed service CLI remains separate.
- Phase implementation is still being independently reviewed for delayed readiness re-audit and actual worker joins without a schema change. This parent consumes only the frozen guardian status/terminal contract, so those phase fixes require no parallel edits here.
- Final parent success means two structurally complete, cleaned and recovered finite lifecycles. It does not mean manual semantic approval, measured memory envelope acceptance, persistent installed qualification or a speed improvement. Existing missing review artifacts and historical failed latches remain blocking.
- Plan-writing self-review checked signatures, fixed paths, no extra POSTs, no loop retry, retained evidence and actual-exit ordering. Code blocks are complete starting code for the stated RED/GREEN cycle, not tested production code. No tests or runtime work were executed.

**Frozen status:** prepared for parent/main-agent review; no checkout mutation or implementation. Only this private report was written.
