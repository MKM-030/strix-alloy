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
