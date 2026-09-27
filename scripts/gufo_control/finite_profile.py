"""Closed finite profile; pure review binding, no launch or acceptance mutation."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path

from . import service_store, smoke_store
from .finite_workload import WORKLOAD_SHA256

PROFILE_ID = smoke_store.FINITE_SERVICE
CONTROLLER_ID = 'gufo-native-finite-controller-v1'
ANCHOR_PATH = Path(__file__).resolve().parents[2]/'config/gufo-finite-review-anchor.json'
PINS = replace(deepcopy(service_store.PINS), profile_id=PROFILE_ID,
    evidence=smoke_store.ROOT/'reports/gufo-service-lifecycle-v1-runs',
    qualification=smoke_store.ROOT/'reports/gufo-service-lifecycle-v1-review.json')
REVIEW_FIELDS = frozenset(('qualification', 'qualification_stamp',
                         'qualification_anchor', 'qualification_anchor_stamp'))


def finite_binding(pins):
    # Canonical comparison retains bool/int distinctions in dataclass fields.
    canonical = lambda p: json.dumps(asdict(p), default=str, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False)
    if (canonical(pins) != canonical(PINS)
            or pins.profile_id != PROFILE_ID
            or pins.evidence.name != smoke_store.PROFILE_ROOTS[PROFILE_ID]
            or pins.bounds != smoke_store.BOUNDS
            or any(type(value) is not int for value in pins.bounds.values())):
        raise ValueError('finite_identity_invalid')
    return dict(profile_id=PROFILE_ID, controller_id=CONTROLLER_ID,
        source_tree=service_store.SOURCE_TREE,
        runtime_variant=service_store.RUNTIME_VARIANT,
        runtime_policy_sha256=service_store.RUNTIME_POLICY_SHA256,
        workload_sha256=WORKLOAD_SHA256, max_lifecycles=2,
        acceptance_status='finite_only_not_installed_acceptance')


def review_record(candidate_sha256, review_id, envelope_review_id, footprint_review_id):
    if (not smoke_store._digest_valid(candidate_sha256)
            or any(type(v) is not str or not v.strip() or len(v) > 256
                   for v in (review_id, envelope_review_id, footprint_review_id))):
        raise ValueError('finite_review_identity')
    return dict(schema=1, kind='gufo-finite-two-lifecycle-review',
        status='finite-two-lifecycle-reviewed', profile_id=PROFILE_ID,
        controller_id=CONTROLLER_ID, source_commit=PINS.source_commit,
        runtime_variant=service_store.RUNTIME_VARIANT,
        workload_sha256=WORKLOAD_SHA256, candidate_sha256=candidate_sha256,
        envelope=dict(PINS.bounds), max_lifecycles=2,
        review_id=review_id, envelope_review_id=envelope_review_id,
        footprint_review_id=footprint_review_id)


def validate_review(record):
    try:
        expected = review_record(record['candidate_sha256'], record['review_id'],
                                 record['envelope_review_id'], record['footprint_review_id'])
        if service_store._canonical(record) != service_store._canonical(expected):
            raise ValueError('finite_review_mismatch')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('finite_review_invalid') from error
    return record


def candidate_part(manifest):
    return {key: value for key, value in manifest.items() if key not in REVIEW_FIELDS}


def validate_anchor(anchor):
    if (type(anchor) is not dict or set(anchor) != {'schema', 'profile_id', 'certificate_sha256'}
            or type(anchor['schema']) is not int or anchor['schema'] != 1
            or anchor['profile_id'] != PROFILE_ID
            or (anchor['certificate_sha256'] is not None
                and not smoke_store._digest_valid(anchor['certificate_sha256']))):
        raise ValueError('finite_anchor_invalid')
    return anchor


def bind_manifest(manifest, *, pins=PINS):
    try:
        binding = finite_binding(pins)
        q = validate_review(manifest['qualification'])
        anchor = validate_anchor(manifest['qualification_anchor'])
        if (anchor['certificate_sha256'] is None
                or manifest['qualification_stamp']['sha256'] != anchor['certificate_sha256']
                or q['candidate_sha256'] != service_store._digest(candidate_part(manifest))
                or service_store._canonical(manifest['finite_profile']) != service_store._canonical(binding)
                or manifest['profile'] != PROFILE_ID or manifest['source'] != pins.source_commit
                or service_store._canonical(manifest['bounds']) != service_store._canonical(pins.bounds)
                or manifest['executable'] != str(pins.build/pins.executable_name)
                or manifest['model']['revision'] != pins.model_revision
                or manifest['model']['first_shard'] != str(pins.first_shard)
                or manifest['margin_report']['sha256'] != pins.margin_sha256):
            raise ValueError('finite_manifest_mismatch')
        return q
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('finite_manifest_invalid') from error


def profile_from_manifest(manifest, *, pins=PINS):
    from .smoke_policy import SmokeProfile, _demand
    q = bind_manifest(manifest, pins=pins)
    return SmokeProfile(**_demand(pins), profile_id=PROFILE_ID,
        source_commit=pins.source_commit, model_revision=pins.model_revision,
        qualified=True, review_id=q['review_id'],
        shared_allowance_review_id=q['envelope_review_id'],
        qualification_json=service_store._canonical(q))


def profile_valid(profile, *, pins=PINS):
    from .smoke_policy import SmokeProfile, _demand
    try:
        finite_binding(pins)
        if type(profile) is not SmokeProfile:
            return False
        q = validate_review(json.loads(profile.qualification_json))
        expected = SmokeProfile(**_demand(pins), profile_id=PROFILE_ID,
            source_commit=pins.source_commit, model_revision=pins.model_revision,
            qualified=True, review_id=q['review_id'],
            shared_allowance_review_id=q['envelope_review_id'],
            qualification_json=service_store._canonical(q))
        return (profile == expected and profile.qualified is True
                and all(type(getattr(profile, key)) is int for key in (
                    'gpu_peak_bytes', 'host_peak_bytes',
                    'shared_physical_allowance_bytes', 'commit_peak_bytes')))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
