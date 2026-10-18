"""Exact paired AR/MTP profiles for the fixed historical 36-request corpus."""
from dataclasses import replace
from hashlib import sha256

from . import benchmark_guard, benchmark_recipes, matched_recipes, operator_store, smoke_store
from .model_identity import MTP_SIDECAR


MARGIN_SHA256 = '49433BB54E71F7F27418FEC63E71DA98F4C372F31E19E6A95292E21148874344'
D3_MARGIN_SHA256 = '825F2BDE34A4BE070517EE4DD00EA3FA911A4141326591A8DDB47A43FD0AE66D'
PROFILE_FILES = {
    matched_recipes.PROFILE_AR: ('gufo-matched-ar4k-v1-runs', 'gufo-matched-ar4k-v1-qualification.json'),
    matched_recipes.PROFILE_AR_V2: ('gufo-matched-ar4k-v2-runs', 'gufo-matched-ar4k-v2-qualification.json'),
    matched_recipes.PROFILE_MTP: ('gufo-matched-mtp4k-v1-runs', 'gufo-matched-mtp4k-v1-qualification.json'),
    matched_recipes.PROFILE_MTP_D3: ('gufo-matched-mtp4k-d3-v1-runs', 'gufo-matched-mtp4k-d3-v1-qualification.json'),
}


def experiment_definition(profile_id):
    definition = matched_recipes.recipe_definition(profile_id)
    mtp = profile_id in matched_recipes.MTP_DRAFT_LIMITS
    result = dict(profile_id=profile_id,
        recipe_sha256=sha256(matched_recipes.recipe_json(profile_id).encode()).hexdigest().upper(),
        context_tokens=4096, max_prompt_tokens=2304, max_output_tokens=256,
        max_requests=36, sessions=1, max_connections=16,
        max_request_bytes=262144, max_response_bytes=1048576,
        request_seconds=60, startup_seconds=480, lifetime_seconds=600,
        speculative=mtp, disk_cache=False)
    if mtp:
        result.update(draft_tokens=matched_recipes.MTP_DRAFT_LIMITS[profile_id], min_draft_tokens=1,
                      mtp_policy='length', mtp_draft_vocab='full')
    if len(definition['schedule']) != result['max_requests']:
        raise ValueError('matched_schedule_changed')
    return result


def profile_pins(profile_id):
    if profile_id not in PROFILE_FILES:
        raise ValueError('unknown_profile')
    parent = benchmark_guard.profile_pins(benchmark_recipes.PROFILE_16K)
    if (parent.predecessors[0].result_sha256 != smoke_store.MTP_PREDECESSOR_SHA256
            or parent.predecessors[0].profile_id != benchmark_recipes.PROFILE_4K):
        raise ValueError('matched_predecessor_identity_invalid')
    reports = smoke_store.ROOT / 'reports'
    evidence, qualification = PROFILE_FILES[profile_id]
    mtp = profile_id in matched_recipes.MTP_DRAFT_LIMITS
    d3 = profile_id == matched_recipes.PROFILE_MTP_D3
    margin_name = ('gufo-mtp-draft3-envelope-review-20260926.md' if d3
                   else 'gufo-matched-mtp-envelope-review-20260926.md')
    margin_sha = D3_MARGIN_SHA256 if d3 else MARGIN_SHA256
    return replace(parent, profile_id=profile_id, evidence=reports/evidence,
        qualification=reports/qualification,
        margin_report=reports/margin_name,
        margin_sha256=margin_sha,
        bounds=dict(smoke_store.profile_bounds(profile_id)),
        experiment_json=benchmark_recipes.canonical(experiment_definition(profile_id)),
        sidecar=MTP_SIDECAR if mtp else None,
        sidecar_stamp=tuple(operator_store.stamp(MTP_SIDECAR.path)) if mtp else None)


def build_argv(profile_id, secret):
    if profile_id not in PROFILE_FILES:
        raise ValueError('unknown_profile')
    argv = benchmark_recipes.build_argv(benchmark_recipes.PROFILE_4K, secret)
    if profile_id in matched_recipes.MTP_DRAFT_LIMITS:
        argv[argv.index('--speculative')+1] = 'mtp'
        argv.extend(['--mtp-model', str(MTP_SIDECAR.path), '--draft-tokens',
                     str(matched_recipes.MTP_DRAFT_LIMITS[profile_id]),
                     '--min-draft-tokens', '1', '--mtp-policy', 'length',
                     '--mtp-draft-vocab', 'full'])
    return argv
