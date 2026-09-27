from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from gufo_control import admission, finite_profile as fp, service_store
from gufo_control import smoke_policy, smoke_store
from gufo_control.benchmark_runtime import BoundPolicy
from gufo_control.operator_policy import baseline
from test_operator_policy import frame, series


def candidate():
    return dict(profile=fp.PROFILE_ID, source=fp.PINS.source_commit,
        bounds=dict(fp.PINS.bounds), finite_profile=fp.finite_binding(fp.PINS),
        executable=str(fp.PINS.build/fp.PINS.executable_name),
        sdk=str(fp.PINS.sdk), model=dict(first_shard=str(fp.PINS.first_shard),
        revision=fp.PINS.model_revision), margin_report=dict(sha256=fp.PINS.margin_sha256))


def qualified(value=None):
    m = deepcopy(candidate() if value is None else value)
    q = fp.review_record(service_store._digest(m), 'finite-review',
                         'header-envelope-review', 'controller-footprint-review')
    m.update(qualification=q, qualification_anchor=dict(schema=1,
        profile_id=fp.PROFILE_ID, certificate_sha256='A'*64),
        qualification_stamp=dict(sha256='A'*64),
        qualification_anchor_stamp=dict(sha256='B'*64))
    return m


class FiniteProfileTests(unittest.TestCase):
    def test_closed_registration_preserves_existing_pins(self):
        installed = deepcopy(service_store.PINS)
        historical = deepcopy(smoke_store.PINS)
        self.assertEqual(smoke_store.PROFILE_ROOTS[fp.PROFILE_ID],
                         'gufo-service-lifecycle-v1-runs')
        self.assertEqual(smoke_store.profile_bounds(fp.PROFILE_ID), smoke_store.BOUNDS)
        self.assertEqual(smoke_store._binding(fp.PINS), fp.finite_binding(fp.PINS))
        self.assertEqual(service_store.PINS, installed)
        self.assertEqual(smoke_store.PINS, historical)
        for change in (dict(source_commit='0'*40), dict(evidence=installed.evidence),
                       dict(bounds=dict(fp.PINS.bounds, host_gib=5)),
                       dict(bounds=dict(fp.PINS.bounds, gpu_gib=68.0))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                smoke_store._binding(replace(fp.PINS, **change))

    def test_certificate_does_not_accept_installed_or_changed_candidate(self):
        good = qualified()
        p = BoundPolicy(fp.PINS).profile_from_manifest(good)
        self.assertTrue(BoundPolicy(fp.PINS)._profile_valid(p))
        self.assertFalse(smoke_policy._profile_valid(p))
        self.assertFalse(BoundPolicy(service_store.PINS)._profile_valid(p))
        for change in (
            lambda m: m['qualification'].update(status='persistent-service-accepted'),
            lambda m: m['qualification'].update(max_lifecycles=True),
            lambda m: m['qualification'].update(footprint_review_id=''),
            lambda m: m['qualification_anchor'].update(certificate_sha256=None),
            lambda m: m['qualification_stamp'].update(sha256='C'*64),
            lambda m: m['bounds'].update(shared_gib=19),
            lambda m: m['finite_profile'].update(workload_sha256='0'*64)):
            changed = deepcopy(good); change(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                BoundPolicy(fp.PINS).profile_from_manifest(changed)
        self.assertFalse(BoundPolicy(fp.PINS)._profile_valid(replace(p, host_peak_bytes=True)))

    def test_review_is_separate_from_installed_anchor(self):
        anchor = service_store.expected_anchor(service_store.expected_profile(service_store.PINS))
        self.assertIsNone(anchor['acceptance_sha256'])
        self.assertIsNone(anchor['installed_workload'])
        self.assertNotEqual(fp.ANCHOR_PATH, service_store.ANCHOR_PATH)
        with patch.object(service_store, '_acceptance', side_effect=AssertionError):
            self.assertTrue(BoundPolicy(fp.PINS).profile_from_manifest(qualified()).qualified)

    def test_finite_admission_uses_exact_header_source_without_changing_math(self):
        p = BoundPolicy(fp.PINS).profile_from_manifest(qualified())
        b = baseline(series()); f = frame(12)
        kw = dict(now=f.query_end, now_utc=f.validated_utc)
        actual = BoundPolicy(fp.PINS).admission_decision(p, b, f, **kw)
        self.assertEqual(actual['reasons'], [])
        direct = admission._evaluate_admission(f.snapshot, dict(p.envelope),
            now=f.query_end, source_commit=fp.PINS.source_commit)
        self.assertEqual(actual['predicted_available_bytes'], direct['predicted_available_bytes'])
        stale = BoundPolicy(fp.PINS).admission_decision(p, b, f,
            now=f.query_end+3, now_utc=f.validated_utc)
        self.assertFalse(stale['allowed'])
        with patch.object(admission, '_evaluate_admission') as evaluate:
            admission._evaluate_service_admission({}, {}, now=1, pins=fp.PINS)
            self.assertEqual(evaluate.call_args.kwargs['source_commit'], fp.PINS.source_commit)


if __name__ == '__main__':
    unittest.main()
