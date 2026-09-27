# Finite GUFO workload and reservation ledger implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Make the reviewed finite request bytes available to the controller and consume each permitted HTTP attempt durably before a future transport can send it.

**Architecture:** One immutable workload value authenticates the reviewed JSON and returns exact bytes and scheduled expectations. One private, bounded file ledger reuses the existing Windows file-lock helper for exclusive create/fsync reservations and outcomes. Neither module starts HTTP, GUFO, telemetry or recovery, and neither grants service qualification.

**Tech Stack:** Existing Python3.12 standard library, existing checked_path and operator_store.exclusive, unittest and temporary directories.

## Global Constraints

- Preserve working native Strix Alloy, Halogen WSL2 and27B installations; no dual boot.
- Preserve49GiB Windows available physical before model launch,24GiB runtime physical,12GiB commit reserve; reviewed model allowance68GiB GPU/4GiB additional host/20GiB shared. This task grants no launch authority.
- No model/GPU/helper/metadata/collector/socket/guardian/recovery invocation; no real run/attempt/latch/qualification/acceptance changes. Tests use temporary directories and CPU-only standard-library code.
- No BIOS/carve/VGM/driver/services/security/pagefile changes, reboot, D:, publication or unrelated process termination.
- Work only in C:/Projects/strix-alloy-research/integration on codex/gufo-native-integration. Preserve frozen production enginee6feed7, runtime headers, original failed recovery and empty installed acceptance.
- Reuse candidate v2 exactly,132273bytes/SHA25630D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38. It remains a fixture contract, not production qualification.
- Fixed66+6POSTs,240readyGETs and1modelsGET perlife,3600/900seconds,480seconds readiness,60seconds complete operations; request body16384exceptone16385,3sockets later enforced by transport;49/24/12 remain.
- This task implements immutable workload access and durable pre-send accounting only. HTTP phase orchestration, socket semaphore, wire/evidence writers, answer checks, authenticated handoff, private store/guardian binding and actual inference are separate remaining controller work; never claim this layer enforces them.
- The ledger directory is a private dedicated child under a future authenticated run root; keep captures/credentials/other evidence outside that child. Its header binds workload/lifecycle/run/resume time. The future caller must supply the authenticated run identity and current monotonic resume time, verify handoff and refuse launch on historical latches.
- Reserve before any send; every created reservation stays consumed. A failed/partial durable write must propagate and preserve evidence. No deleting failed files, replay, refund, missing-outcome recovery, or generic force override.
- Only task files named below are changed; no dependency installation, engine rebuild, shared SDK or global Git configuration changes. Commit locally with existing one-command identity if needed; no push.

---

### Task 1: Implement pinned workload access and the finite reservation ledger

**Files (all relative to integration):**
- Create config/gufo-service-lifecycle-workload.json (verbatim reviewed artifact).
- Create scripts/gufo_control/finite_workload.py.
- Create scripts/gufo_control/finite_ledger.py.
- Create tests/gufo/test_finite_ledger.py.
- Report outside checkout: C:/Projects/strix-alloy-research/reports/gufo-finite-ledger-implementation-20260927.md.

**Interfaces:** load_workload(path=WORKLOAD_PATH)->Workload; immutable Workload.raw; document/limits/lifecycle return independent values; post(index,attempt)->PreparedPost with exact bytes and scheduled response expectation. Ledger(root,workload,index,run_id,resumed_at,create=False,clock=time.monotonic); reserve(kind,ordinal,body=b'')->dict containing slot and immutable disk record; complete(slot,result)->None (result.success is a strict bool); snapshot()->bounded counters/pending list. Allowed kinds ready/models/post. All operations use a ledger-specific lock; resume refuses any reservation lacking a bound terminal outcome. Outcomes are accounting reports from the future validated client, not self-authenticating inference or recovery evidence.

- [ ] **Step1 — confirm existing clean isolation and evidence; prepare tests and pinned data.**

Read the v2review C:/Projects/strix-alloy-research/reports/gufo-finite-workload-candidate-v2-review-20260927.md and the module-level code below. Read any applicable AGENTS.md. Existing integration67f0e415ebc7463cd83287af3a76cab708a154ab is clean and already isolated. Existing reviewed service offline tests passed before documentation-only commits; do not repeat broad unchanged suites. Record actual dispatchBASE independently.

Copy the already-reviewed artifact verbatim from C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-fixtures-20260927/finite-workload-candidate-v2.json into the config path using apply_patch, preserving LF and final newline. In functions execution the source can remain out of model context:
```javascript
const r = await tools.exec_command({cmd:"Get-Content -LiteralPath 'C:/Projects/strix-alloy-research/reports/gufo-service-lifecycle-fixtures-20260927/finite-workload-candidate-v2.json' -Raw",max_output_tokens:50000});
if (r.exit_code !== 0) throw Error("fixture read failed");
const raw = r.output.replace(/\r?\n$/, "");
text(await tools.apply_patch("*** Begin Patch\n*** Add File: C:/Projects/strix-alloy-research/integration/config/gufo-service-lifecycle-workload.json\n" + raw.split("\n").map(line => "+" + line).join("\n") + "\n*** End Patch"));
```
Check file size and SHA256 match the constraints. Preserve the external original and its reports.

Create the following test file with apply_patch:
```python
"""No-network tests of exact workload bytes and pre-send durable accounting."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from gufo_control.finite_workload import Workload, load_workload, WORKLOAD_SHA256
from gufo_control import finite_ledger
from gufo_control.finite_ledger import Ledger


class WorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = load_workload()

    def test_pinned_identity_and_immutable_copies(self):
        workload = self.workload
        self.assertEqual(sha256(workload.raw).hexdigest().upper(), WORKLOAD_SHA256)
        value = workload.document()
        value['limits']['maximum_connections'] = 999
        self.assertEqual(workload.limits()['maximum_connections'], 3)
        with self.assertRaises(FrozenInstanceError):
            workload.raw = b'bad'
        with self.assertRaisesRegex(ValueError, 'finite_workload_identity'):
            Workload(workload.raw+b' ')

    def test_all_72_bodies_hash_and_only_congestion_probe_overrides(self):
        posts = [self.workload.post(index, attempt) for index, count in ((1, 66), (2, 6))
                 for attempt in range(1, count+1)]
        self.assertEqual(len(posts), 72)
        for post in posts:
            self.assertEqual(sha256(post.body).hexdigest().upper(), post.body_sha256)
        third = self.workload.post(1, 45)
        self.assertEqual((third.expected_status, third.expected_error), (429, 'queue_full'))
        ordinary = [p for p in posts if p.request_id == third.request_id and p.attempt != 45]
        self.assertTrue(ordinary)
        self.assertTrue(all(p.expected_status == 200 for p in ordinary))

    def test_raw_negative_bytes_are_not_reserialized(self):
        body = self.workload.post(1, 60).body
        self.assertEqual(len(body), 16385)
        self.assertEqual(json.loads(body)['model'], 'gufo-flash-next')
        invalid = self.workload.post(1, 64).body
        self.assertIn(b'\xc0', invalid)
        with self.assertRaises(UnicodeDecodeError):
            invalid.decode('utf-8')
        duplicate = self.workload.post(1, 65).body
        self.assertEqual(duplicate.count(b'"max_tokens"'), 2)
        self.assertEqual(self.workload.post(1, 66).body, b'{"model":')

    def test_indices_refuse_bool_and_unknown_slots(self):
        for index, attempt in ((True, 1), (0, 1), (3, 1), (1, True), (1, 67), (2, 7)):
            with self.subTest(index=index, attempt=attempt), self.assertRaises(ValueError):
                self.workload.post(index, attempt)


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workload = load_workload()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'ledger'
        self.now = 100.0
        self.ledger = Ledger(self.root, self.workload, 1, 'unit-run', 100.0,
                             create=True, clock=lambda: self.now)

    def reserve_post(self, attempt=1):
        return self.ledger.reserve('post', attempt,
                                  body=self.workload.post(1, attempt).body)

    def test_reservation_is_durable_before_return_and_never_refunded(self):
        row = self.reserve_post()
        path = self.root/'post-001.reserved.json'
        self.assertTrue(path.exists())
        disk = json.loads(path.read_text())
        self.assertEqual(disk['body_sha256'], row['body_sha256'])
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])
        self.ledger.complete(row['slot'], {'success': True, 'classification': 'expected_rejection'})
        with self.assertRaisesRegex(ValueError, 'consumed_or_out_of_order'):
            self.reserve_post()
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)

    def test_mutated_body_or_out_of_order_refuses_before_reservation(self):
        for attempt, body in ((1, b'{}'), (2, self.workload.post(1, 2).body)):
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                self.ledger.reserve('post', attempt, body=body)
        self.assertEqual(self.ledger.snapshot()['reserved'], 0)

    def test_unknown_and_bool_slots_refuse(self):
        for kind, ordinal in (('POST', 1), ('post', True), ('models', 2), ('ready', 0)):
            with self.subTest(kind=kind, ordinal=ordinal), self.assertRaises(ValueError):
                self.ledger.reserve(kind, ordinal)
        self.assertEqual(self.ledger.snapshot()['reserved'], 0)

    def test_failed_attempt_blocks_new_work(self):
        row = self.reserve_post()
        self.ledger.complete(row['slot'], {'success': False, 'classification': 'ambiguous_send'})
        with self.assertRaisesRegex(ValueError, 'finite_prior_failure'):
            self.reserve_post(2)
        with self.assertRaisesRegex(ValueError, 'finite_outcome_slot'):
            self.ledger.complete(row['slot'], {'success': True})

    def test_handoff_requires_terminal_records_and_exact_identity(self):
        self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_incomplete_handoff'):
            Ledger(self.root, self.workload, 1, 'unit-run', 100.0)
        self.ledger.complete('post-001', {'success': True})
        reopened = Ledger(self.root, self.workload, 1, 'unit-run', 100.0, clock=lambda: self.now)
        self.assertEqual(reopened.snapshot()['counts']['post'], 1)
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            Ledger(self.root, self.workload, 1, 'wrong-run', 100.0)
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            Ledger(self.root, self.workload, 2, 'unit-run', 100.0)

    def test_fsync_failure_consumes_record_and_handoff_fails_closed(self):
        with patch.object(finite_ledger.os, 'fsync', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.reserve_post()
        self.assertTrue((self.root/'post-001.reserved.json').exists())
        with self.assertRaisesRegex(ValueError, 'consumed_or_out_of_order'):
            self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_incomplete_handoff'):
            Ledger(self.root, self.workload, 1, 'unit-run', 100.0)

    def test_limits_and_absolute_deadlines(self):
        self.now = 579.5
        ready = self.ledger.reserve('ready', 1)
        self.assertEqual(ready['deadline'], 580.0)
        self.ledger.complete(ready['slot'], {'success': True, 'ready': False})
        self.now = 580.0
        with self.assertRaisesRegex(ValueError, 'finite_deadline'):
            self.ledger.reserve('ready', 2)
        self.now = 3690.0
        row = self.reserve_post()
        self.assertEqual(row['deadline'], 3700.0)
        self.now = 3700.0
        with self.assertRaisesRegex(ValueError, 'finite_deadline'):
            self.reserve_post(2)

    def test_nonfinite_clock_and_constructor_times(self):
        for value in (-1, True, float('nan'), float('inf'), 10**400):
            self.now = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                self.reserve_post()
        with self.assertRaises(ValueError):
            Ledger(Path(self.temp.name)/'bad', self.workload, 1, 'bad', 1e308, create=True)

    def test_ready_and_model_query_caps_and_no_get_after_post(self):
        for index in range(1, 241):
            self.ledger.reserve('ready', index)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            self.ledger.reserve('ready', 241)
        self.ledger.reserve('models', 1)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            self.ledger.reserve('models', 2)
        fresh = Ledger(Path(self.temp.name)/'after-ready', self.workload, 1, 'fresh',
                       100.0, create=True, clock=lambda: 100.0)
        fresh.reserve('post', 1, body=self.workload.post(1, 1).body)
        with self.assertRaisesRegex(ValueError, 'finite_readiness_finished'):
            fresh.reserve('ready', 1)

    def test_second_lifecycle_post_cap_and_budget_accounting(self):
        ledger = Ledger(Path(self.temp.name)/'second', self.workload, 2, 'second-run',
                        100.0, create=True, clock=lambda: 100.0)
        for attempt in range(1, 7):
            ledger.reserve('post', attempt, body=self.workload.post(2, attempt).body)
        with self.assertRaisesRegex(ValueError, 'finite_slot'):
            ledger.reserve('post', 7)
        observed = ledger.snapshot()
        self.assertEqual(observed['reserved_wire_bytes'], 6*8*1024*1024)
        self.assertLess(observed['reserved_evidence_bytes'], 128*1024*1024)

    def test_budget_failure_does_not_create_a_reservation(self):
        with patch.object(finite_ledger, 'BASE_EVIDENCE_RESERVE',
                          self.ledger.life['maximum_client_evidence_bytes']):
            with self.assertRaisesRegex(ValueError, 'finite_budget_exceeded'):
                self.reserve_post()
        self.assertFalse((self.root/'post-001.reserved.json').exists())

    def test_partial_and_forged_records_refuse(self):
        self.reserve_post()
        path = self.root/'post-001.reserved.json'
        original = path.read_bytes()
        path.write_bytes(b'{"schema":')
        with self.assertRaises(ValueError):
            self.ledger.snapshot()
        path.write_bytes(original)
        self.ledger.complete('post-001', {'success': True})
        outcome = self.root/'post-001.outcome.json'
        row = json.loads(outcome.read_bytes())
        row['reservation_sha256'] = '0'*64
        outcome.write_text(json.dumps(row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'finite_outcome_binding'):
            self.ledger.snapshot()

    def test_oversized_outcome_refuses_and_stays_pending(self):
        self.reserve_post()
        with self.assertRaisesRegex(ValueError, 'finite_record_size'):
            self.ledger.complete('post-001', {'success': True, 'text': 'x'*65536})
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])

    def test_unknown_entry_and_boolean_header_are_not_trusted(self):
        identity = self.root/'identity.json'
        original = identity.read_bytes()
        value = json.loads(original)
        value['schema'] = True
        identity.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_identity'):
            self.ledger.snapshot()
        identity.write_bytes(original)
        (self.root/'unexpected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'finite_ledger_entry'):
            self.ledger.snapshot()

    def test_nonfinite_outcome_stays_uncommitted(self):
        self.reserve_post()
        with self.assertRaises(ValueError):
            self.ledger.complete('post-001', {'success': True, 'seconds': float('nan')})
        self.assertFalse((self.root/'post-001.outcome.json').exists())
        self.assertEqual(self.ledger.snapshot()['pending'], ['post-001'])

    def test_same_slot_race_has_one_winner(self):
        barrier = threading.Barrier(2)
        def compete():
            barrier.wait(timeout=2)
            try:
                self.reserve_post()
                return 'reserved'
            except ValueError:
                return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: compete(), range(2)))
        self.assertEqual(sorted(results), ['refused', 'reserved'])
        self.assertEqual(self.ledger.snapshot()['counts']['post'], 1)


if __name__ == '__main__':
    unittest.main()

```

- [ ] **Step2 — run the focused RED test before implementation.**

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest discover -s tests/gufo -p test_finite_ledger.py -v
```
Expected nonzero because gufo_control.finite_workload does not exist yet. Preserve exact output in new task-owned logs. If failure has a different cause, diagnose before implementing; do not invent a red test by altering existing behavior.

- [ ] **Step3 — implement immutable request bytes and the ledger.**

scripts/gufo_control/finite_workload.py:
```python
"""Pinned, immutable bytes for the finite two-lifecycle qualification."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .build_identity import checked_path

WORKLOAD_SHA256 = '30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38'
WORKLOAD_PATH = Path(__file__).resolve().parents[2] / 'config/gufo-service-lifecycle-workload.json'
MAX_MANIFEST_BYTES = 262144


@dataclass(frozen=True)
class PreparedPost:
    attempt: int
    request_id: str
    route: str
    body: bytes
    body_sha256: str
    expected_status: int
    expected_error: str | None
    step_json: str


@dataclass(frozen=True)
class Workload:
    raw: bytes

    def __post_init__(self):
        if (type(self.raw) is not bytes or len(self.raw) > MAX_MANIFEST_BYTES
                or sha256(self.raw).hexdigest().upper() != WORKLOAD_SHA256):
            raise ValueError('finite_workload_identity')

    def document(self):
        return json.loads(self.raw.decode('utf-8'))

    def limits(self):
        return self.document()['limits']

    def lifecycle(self, index):
        if type(index) is not int or index not in (1, 2):
            raise ValueError('finite_lifecycle_index')
        return self.document()['lifecycles'][index - 1]

    def post(self, index, attempt):
        life = self.lifecycle(index)
        if type(attempt) is not int or not 1 <= attempt <= life['maximum_post_attempts']:
            raise ValueError('finite_post_index')
        step = life['steps'][attempt - 1]
        row = next(row for row in self.document()['request_pool'] if row['id'] == step['request'])
        body = row['body'].encode('utf-8') if row['encoding'] == 'utf8' else bytes.fromhex(row['body'])
        digest = sha256(body).hexdigest().upper()
        if not row['scheduled'] or len(body) != row['body_bytes'] or digest != row['body_sha256']:
            raise ValueError('finite_request_identity')
        status = step.get('expected_http_status', row['expected_http_status'])
        error = row['expected_error_code']
        if 'allowed_error_codes' in step:
            error = step['allowed_error_codes'][0]
        return PreparedPost(attempt, row['id'], row['route'], body, digest,
                            status, error, json.dumps(step, sort_keys=True))


def load_workload(path=WORKLOAD_PATH):
    path = checked_path(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    workload = Workload(raw)
    for index in (1, 2):
        for attempt in range(1, workload.lifecycle(index)['maximum_post_attempts'] + 1):
            workload.post(index, attempt)
    return workload

```

scripts/gufo_control/finite_ledger.py:
```python
"""Durable reservations only: no HTTP, process creation or launch authority.

A single authenticated client owns a Ledger. Its future transport must enforce
phase ordering, sockets, actual wire/evidence writes and answer correctness.
This layer consumes fixed slots before dispatch and never refunds them.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from types import MappingProxyType

from . import operator_store
from .build_identity import checked_path
from .finite_workload import WORKLOAD_SHA256, Workload

KINDS = ('ready', 'models', 'post')
RECORD_LIMIT = 4096
BASE_EVIDENCE_RESERVE = 1048576


def _time(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except (OverflowError, TypeError):
        return False


def _encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def _read(path, maximum):
    checked_path(path)
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('finite_record_size')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('finite_duplicate_key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('finite_nonfinite_json')
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=constant)


def _exclusive(path, value, maximum):
    data = _encoded(value)
    if len(data) > maximum:
        raise ValueError('finite_record_size')
    checked_path(path, exists=False)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class Ledger:
    def __init__(self, root, workload, index, run_id, resumed_at, *, create=False,
                 clock=time.monotonic):
        if (type(workload) is not Workload or type(run_id) is not str
                or re.fullmatch(r'[A-Za-z0-9-]{1,96}', run_id) is None
                or not _time(resumed_at)):
            raise ValueError('finite_ledger_identity')
        self.workload, self.index, self.clock = workload, index, clock
        self.life = MappingProxyType(workload.lifecycle(index))
        self.limits = MappingProxyType(workload.limits())
        self.root = checked_path(root, directory=True, exists=not create)
        self._mutex = threading.Lock()
        self.header = dict(schema=1, profile='ar4k-service-lifecycle-v1',
            workload_sha256=WORKLOAD_SHA256, lifecycle=index, run_id=run_id,
            resumed_at=resumed_at, deadline=resumed_at+self.life['lifetime_seconds'])
        if not _time(self.header['deadline']) or self.header['deadline'] <= resumed_at:
            raise ValueError('finite_ledger_deadline')
        if create:
            self.root.mkdir()
            _exclusive(self.root/'identity.json', self.header, RECORD_LIMIT)
        else:
            checked_path(self.root/'runner.lock')
        with self._locked():
            reservations, outcomes = self._scan()
            if not create and set(reservations) != set(outcomes):
                raise ValueError('finite_incomplete_handoff')

    @contextmanager
    def _locked(self):
        if not self._mutex.acquire(timeout=1):
            raise RuntimeError('finite_ledger_busy')
        try:
            checked_path(self.root, directory=True)
            checked_path(self.root/'runner.lock', exists=False)
            with operator_store.exclusive(self.root):
                if _encoded(_read(self.root/'identity.json', RECORD_LIMIT)) != _encoded(self.header):
                    raise ValueError('finite_ledger_identity')
                yield
        finally:
            self._mutex.release()

    def _spec(self, kind, ordinal):
        if kind not in KINDS or type(ordinal) is not int:
            raise ValueError('finite_slot')
        count = (self.life['maximum_post_attempts'] if kind == 'post' else
                 self.life['maximum_ready_polls'] if kind == 'ready' else 1)
        if not 1 <= ordinal <= count:
            raise ValueError('finite_slot')
        if kind == 'post':
            post = self.workload.post(self.index, ordinal)
            wire = self.limits['post_response_wire_bytes']
            evidence = wire + self.limits['generated_text_or_tool_argument_utf8_bytes']
            evidence += self.limits['post_summary_bytes'] + RECORD_LIMIT
            return dict(method='POST', path=post.route, request_id=post.request_id,
                body_bytes=len(post.body), body_sha256=post.body_sha256,
                wire_allowance=wire, evidence_allowance=evidence)
        wire = self.limits['get_response_wire_bytes']
        return dict(method='GET', path='/ready' if kind == 'ready' else '/v1/models',
            request_id=None, body_bytes=0, body_sha256=sha256(b'').hexdigest().upper(),
            wire_allowance=wire,
            evidence_allowance=wire+self.limits['get_summary_bytes']+RECORD_LIMIT)

    def _scan(self):
        reservations, outcomes, names = {}, {}, []
        maximum = 2 + 2*(self.life['maximum_post_attempts'] + self.life['maximum_ready_polls'] + 1)
        for path in self.root.iterdir():
            names.append(path.name)
            if len(names) > maximum:
                raise ValueError('finite_ledger_entries')
            if path.name in ('identity.json', 'runner.lock'):
                continue
            match = re.fullmatch(r'(ready|models|post)-([0-9]{3})\.(reserved|outcome)\.json', path.name)
            if not match:
                raise ValueError('finite_ledger_entry')
            kind, digits, suffix = match.groups()
            ordinal = int(digits)
            spec = self._spec(kind, ordinal)
            slot = f'{kind}-{ordinal:03d}'
            if suffix == 'reserved':
                row = _read(path, RECORD_LIMIT)
                expected = dict(schema=1, kind=kind, ordinal=ordinal, **spec)
                if (type(row) is not dict or set(row) != set(expected) | {'started', 'deadline'}
                        or any(row[k] != v or type(row[k]) is not type(v) for k, v in expected.items())
                        or not _time(row['started']) or not _time(row['deadline'])
                        or row['started'] < self.header['resumed_at']
                        or row['deadline'] != self._deadline(kind, row['started'])
                        or row['deadline'] <= row['started']):
                    raise ValueError('finite_reservation_invalid')
                reservations[slot] = row
            else:
                limit = self.limits['post_summary_bytes' if kind == 'post' else 'get_summary_bytes']
                row = _read(path, limit)
                if (type(row) is not dict or set(row) != {'schema', 'slot', 'reservation_sha256', 'result'}
                        or type(row['schema']) is not int or row['schema'] != 1 or row['slot'] != slot
                        or type(row['result']) is not dict or type(row['result'].get('success')) is not bool):
                    raise ValueError('finite_outcome_invalid')
                outcomes[slot] = row
        for kind in KINDS:
            numbers = sorted(row['ordinal'] for row in reservations.values() if row['kind'] == kind)
            if numbers != list(range(1, len(numbers)+1)):
                raise ValueError('finite_reservation_gap')
        for slot, row in outcomes.items():
            if (slot not in reservations or row['reservation_sha256'] !=
                    sha256(_encoded(reservations[slot])).hexdigest().upper()):
                raise ValueError('finite_outcome_binding')
        if (sum(row['wire_allowance'] for row in reservations.values()) > self.life['maximum_response_wire_bytes']
                or BASE_EVIDENCE_RESERVE + sum(row['evidence_allowance'] for row in reservations.values())
                > self.life['maximum_client_evidence_bytes']):
            raise ValueError('finite_budget_exceeded')
        return reservations, outcomes

    def _deadline(self, kind, now):
        end = min(now+self.limits['operation_seconds'], self.header['deadline'])
        if kind != 'post':
            end = min(end, self.header['resumed_at']+self.life['readiness_seconds'])
        return end

    def reserve(self, kind, ordinal, *, body=b''):
        with self._locked():
            reservations, outcomes = self._scan()
            if any(row['result']['success'] is False for row in outcomes.values()):
                raise ValueError('finite_prior_failure')
            spec = self._spec(kind, ordinal)
            count = sum(row['kind'] == kind for row in reservations.values())
            if ordinal != count+1:
                raise ValueError('finite_slot_consumed_or_out_of_order')
            if kind != 'post' and any(row['kind'] == 'post' for row in reservations.values()):
                raise ValueError('finite_readiness_finished')
            if (type(body) is not bytes or len(body) != spec['body_bytes']
                    or sha256(body).hexdigest().upper() != spec['body_sha256']):
                raise ValueError('finite_request_identity')
            now = self.clock()
            if not _time(now) or now < self.header['resumed_at'] or now >= self._deadline(kind, now):
                raise ValueError('finite_deadline')
            if (sum(row['wire_allowance'] for row in reservations.values())+spec['wire_allowance']
                    > self.life['maximum_response_wire_bytes']
                    or BASE_EVIDENCE_RESERVE+sum(row['evidence_allowance'] for row in reservations.values())
                    +spec['evidence_allowance'] > self.life['maximum_client_evidence_bytes']):
                raise ValueError('finite_budget_exceeded')
            row = dict(schema=1, kind=kind, ordinal=ordinal, **spec,
                       started=now, deadline=self._deadline(kind, now))
            slot = f'{kind}-{ordinal:03d}'
            _exclusive(self.root/f'{slot}.reserved.json', row, RECORD_LIMIT)
            return dict(slot=slot, **row)

    def complete(self, slot, result):
        with self._locked():
            reservations, outcomes = self._scan()
            if slot not in reservations or slot in outcomes:
                raise ValueError('finite_outcome_slot')
            if type(result) is not dict or type(result.get('success')) is not bool:
                raise ValueError('finite_outcome_invalid')
            kind = reservations[slot]['kind']
            limit = self.limits['post_summary_bytes' if kind == 'post' else 'get_summary_bytes']
            row = dict(schema=1, slot=slot, reservation_sha256=
                sha256(_encoded(reservations[slot])).hexdigest().upper(), result=result)
            _exclusive(self.root/f'{slot}.outcome.json', row, limit)

    def snapshot(self):
        with self._locked():
            reservations, outcomes = self._scan()
            return dict(reserved=len(reservations), completed=len(outcomes),
                pending=sorted(set(reservations)-set(outcomes)),
                counts={kind: sum(row['kind'] == kind for row in reservations.values()) for kind in KINDS},
                reserved_wire_bytes=sum(row['wire_allowance'] for row in reservations.values()),
                reserved_evidence_bytes=BASE_EVIDENCE_RESERVE+
                    sum(row['evidence_allowance'] for row in reservations.values()))

```

The code is the implementation starting point, not an excuse to retain a discovered bug. Fix concrete within-scope problems using a focused failing test and report them. Escalate architecture/scope contradictions before changing other files. There is no HTTP or process launch seam in this task.

- [ ] **Step4 — focused GREEN, self-review and local commit.**

Run the Step2 command. Expected20test methods, zero failures/errors/skips; report actual count rather than hiding differences. The240-reservation loop exercises the exact readiness bound once; do not turn it into repeated stress iterations. Confirm config SHA unchanged and only the four task files differ. Review bool/nonfinite/ordinal rejection, exact rawC0/duplicate/padding preservation, attempt45-only429 override, exclusive writes, crash/partial-file behavior, no replay, bounded reads/entry counts and file locking. The ledger is not a socket limiter or result-verdict oracle.

Run git diff --check and the repository's relevant Python static/format checks only if a configured requirement exists. No new formatter/dependency acquisition. Record test command/output/logs. Commit only the four task paths:
```powershell
git add -- config/gufo-service-lifecycle-workload.json scripts/gufo_control/finite_workload.py scripts/gufo_control/finite_ledger.py tests/gufo/test_finite_ledger.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m 'feat(gufo): add finite workload reservation ledger'
```
The one-command identity matches existing author convention without persistent Git configuration. Report BASE/HEAD, changed files, RED/GREEN evidence, actual assertions/count, known limitations and any self-review fixes. No push. Parent independently reviews the full originalBASE..HEAD diff before transport depends on this layer.

## Self-review

This plan implements one independently testable controller responsibility, not a smaller replacement for the goal. It retains the reviewed request bytes and finite resource limits while making accounting durable. Remaining scope is explicit: transport/response parsers and checks; interrupted streams/overlap orchestration; authenticated readiness handoff and private two-run store; reused guardian/memory/recovery integration; real inference and benchmarks. Existing production artifacts and failed-run evidence remain unchanged. Plan interfaces use exactly the names/types implemented above; no unimplemented helper is invoked by tests. The unchanged256k/260k targets and tuning work are not authorized by this ledger.
