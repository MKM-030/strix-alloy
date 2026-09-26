"""Offline bindings: no model, GPU or network is used."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gufo_control import operator_store, smoke_store as store
from test_smoke_store import StoreFixture, digest


FOUR = 'ar4k-iq4xs-correctness-pp1-v2'
SIXTEEN = 'ar16k-iq4xs-pp1-cache-v1'


def experiment(profile=FOUR):
    return dict(profile_id=profile, recipe_sha256='A'*64,
        context_tokens=4096 if profile == FOUR else 16384,
        max_prompt_tokens=3072 if profile == FOUR else 16383,
        max_output_tokens=256, max_requests=36 if profile == FOUR else 13,
        sessions=1, max_connections=16, max_request_bytes=262144,
        max_response_bytes=1048576, request_seconds=60, startup_seconds=480,
        lifetime_seconds=600, speculative=False, disk_cache=False)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class BenchmarkFixture(StoreFixture):
    def bind(self, profile=FOUR):
        predecessor_id = store.PROFILE_ID if profile == FOUR else FOUR
        root = self.root / ('gufo-ar4k-http-slots-smoke-runs' if profile == FOUR
                            else 'gufo-ar4k-benchmark-v2-runs')
        run = root / (store.FIRST_PREDECESSOR_RUN if profile == FOUR else 'reviewed-run')
        run.mkdir(parents=True)
        result = dict(profile=predecessor_id, success=True, owned_exit_confirmed=True,
            collector_terminal=True, collector_cleanup_confirmed=True, http_terminal=True,
            inspection_terminal=True, inspection_duplicate_closed=True,
            evidence_write_confirmed=True, cleanup_confirmed=True, recovery_samples=5)
        if profile == SIXTEEN:
            rows = []
            for ordinal in range(36):
                name = f'request-{ordinal:03d}.json'
                raw = b'x' * (2*1024*1024+1) if ordinal == 0 else b'raw'
                (run/name).write_bytes(raw)
                rows.append(dict(status='completed', artifact=dict(name=name,
                    size_bytes=len(raw), sha256=digest(raw))))
            result['http'] = dict(success=True, rows=rows)
            result['manifest'] = dict(experiment=experiment())
        operator_store.atomic_json(run/'result.json', result)
        result_sha = digest((run/'result.json').read_bytes())
        operator_store.atomic_json(root/'attempt.json', dict(run=str(run), profile=predecessor_id))
        self.predecessor_run = run
        self.evidence = self.root / ('gufo-ar4k-benchmark-v2-runs' if profile == FOUR
                                     else 'gufo-ar16k-benchmark-runs')
        self.evidence.mkdir(exist_ok=True)
        acceptance_sha = None
        if profile == SIXTEEN:
            acceptance = self.root/'gufo-ar4k-benchmark-acceptance.json'
            operator_store.atomic_json(acceptance, dict(profile_id=FOUR, run=str(run),
                result_sha256=result_sha, semantic_status='passed', review_id='semantic-review'))
            acceptance_sha = digest(acceptance.read_bytes())
        self.pins = replace(self.pins, profile_id=profile, evidence=self.evidence,
            experiment_json=canonical(experiment(profile)),
            predecessors=(store.PredecessorPin(predecessor_id, run, result_sha),),
            acceptance_sha256=acceptance_sha)
        self._write_qualification()
        return result_sha


class BenchmarkRuntimeTests(unittest.TestCase):
    def test_old_v1_latch_blocks_v2_but_clean_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            f = BenchmarkFixture(temp)
            sha = f.bind(FOUR)
            old = f.root/'gufo-ar4k-benchmark-runs'
            old.mkdir()
            operator_store.atomic_json(old/'attempt.json', {'run': str(old/'old-clean-run')})
            with patch.object(store, 'FIRST_PREDECESSOR_SHA256', sha):
                manifest = f.verify()
                f.recheck(manifest)
                operator_store.atomic_json(old/'incomplete.json', {'run': str(old/'old-failed-run')})
                run = f.evidence/'current-run'; run.mkdir()
                for action in (f.verify, lambda: f.recheck(manifest),
                               lambda: store._begin_run(run, manifest, f.base, f.pins)):
                    with self.assertRaisesRegex(ValueError, 'prior_smoke_incomplete'):
                        action()
                self.assertFalse((f.evidence/'attempt.json').exists())

    def test_recheck_is_stamp_only_and_bound_begin_checks_changed_evidence(self):
        from gufo_control.benchmark_runtime import BoundStore
        with tempfile.TemporaryDirectory() as temp:
            f = BenchmarkFixture(temp); f.bind(SIXTEEN)
            manifest = f.verify()
            with patch.object(operator_store, 'artifact_record', side_effect=AssertionError('rehash')):
                f.recheck(manifest)
            run = f.evidence/'current-run'; run.mkdir()
            (f.predecessor_run/'request-000.json').write_bytes(b'changed')
            with patch.object(operator_store, 'source_identity', return_value=None):
                with self.assertRaises(ValueError):
                    BoundStore(f.pins).begin_run(run, manifest, f.base)
            self.assertFalse((f.evidence/'attempt.json').exists())

    def test_acceptance_schema_requires_independent_passed_review(self):
        for changes in ({'semantic_status': 'pending'}, {'review_id': ''},
                        {'profile_id': SIXTEEN}, {'extra': 'unapproved'}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temp:
                f = BenchmarkFixture(temp); f.bind(SIXTEEN)
                path = f.root/'gufo-ar4k-benchmark-acceptance.json'
                value = operator_store.read_json(path); value.update(changes)
                operator_store.atomic_json(path, value)
                f.pins = replace(f.pins, acceptance_sha256=digest(path.read_bytes()))
                f._write_qualification()
                with self.assertRaisesRegex(ValueError, 'acceptance_invalid'): f.verify()

    def test_bound_store_and_policy_accept_both_reviewed_profiles(self):
        from gufo_control.benchmark_runtime import BoundStore, BoundPolicy
        for profile in (FOUR, SIXTEEN):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temp:
                f = BenchmarkFixture(temp)
                sha = f.bind(profile)
                with patch.object(store, 'FIRST_PREDECESSOR_SHA256', sha):
                    m = f.verify()
                    f.recheck(m)
                    bound = BoundPolicy(f.pins)
                    p = bound.profile_from_manifest(m)
                    self.assertTrue(bound._profile_valid(p))
                    self.assertEqual(p.profile_id, profile)
                    self.assertEqual(p.gpu_peak_bytes, 68*1024**3)
                    self.assertIs(BoundStore(f.pins).PINS, f.pins)
                    self.assertEqual(m['experiment'], experiment(profile))
                    self.assertEqual(m['predecessors'][0]['identity']['result_sha256'], sha)

    def test_experiment_schema_is_exact_and_canonical(self):
        with tempfile.TemporaryDirectory() as temp:
            f = BenchmarkFixture(temp)
            sha = f.bind()
            valid = f.pins
            variants = [None, json.dumps(experiment())]
            for key, value in [('sessions', True), ('context_tokens', 8192),
                               ('recipe_sha256', 'a'*64), ('surprise', 1)]:
                changed = experiment(); changed[key] = value
                variants.append(canonical(changed))
            with patch.object(store, 'FIRST_PREDECESSOR_SHA256', sha):
                for value in variants:
                    f.pins = replace(valid, experiment_json=value)
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        f.verify()
                for changes in (dict(predecessors=()), dict(profile_id='ar4k-unknown'),
                        dict(bounds=dict(store.BOUNDS, gpu_gib=69)),
                        dict(acceptance_sha256='A'*64), dict(profile_id=store.PROFILE_ID)):
                    f.pins = replace(valid, **changes)
                    with self.subTest(changes=changes), self.assertRaises(ValueError): f.verify()

    def test_raw_and_acceptance_changes_refuse_recheck(self):
        for target in ('request-000.json', 'acceptance'):
            with tempfile.TemporaryDirectory() as temp:
                f = BenchmarkFixture(temp); f.bind(SIXTEEN)
                m = f.verify()
                path = (f.predecessor_run/target if target != 'acceptance' else
                        f.root/'gufo-ar4k-benchmark-acceptance.json')
                path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaises(ValueError): f.recheck(m)

    def test_predecessor_cleanup_root_hash_and_raw_rows_fail_closed(self):
        for mutation in ('cleanup', 'root', 'hash', 'raw_hash', 'row_count', 'row_status', 'traversal'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                f = BenchmarkFixture(temp); f.bind(SIXTEEN)
                pin = f.pins.predecessors[0]
                if mutation in ('root', 'hash'):
                    pin = replace(pin, **({'run': f.root} if mutation == 'root' else
                                          {'result_sha256': 'B'*64}))
                else:
                    result = operator_store.read_json(pin.run/'result.json')
                    if mutation == 'cleanup': result['cleanup_confirmed'] = False
                    if mutation == 'raw_hash': result['http']['rows'][0]['artifact']['sha256'] = 'B'*64
                    if mutation == 'row_count': result['http']['rows'].pop()
                    if mutation == 'row_status': result['http']['rows'][0]['status'] = 'not_run'
                    if mutation == 'traversal': result['http']['rows'][0]['artifact']['name'] = '../escape'
                    operator_store.atomic_json(pin.run/'result.json', result)
                    pin = replace(pin, result_sha256=digest((pin.run/'result.json').read_bytes()))
                    acceptance = f.root/'gufo-ar4k-benchmark-acceptance.json'
                    value = operator_store.read_json(acceptance); value['result_sha256'] = pin.result_sha256
                    operator_store.atomic_json(acceptance, value)
                    f.pins = replace(f.pins, acceptance_sha256=digest(acceptance.read_bytes()))
                f.pins = replace(f.pins, predecessors=(pin,))
                f._write_qualification()
                with self.assertRaises(ValueError): f.verify()
