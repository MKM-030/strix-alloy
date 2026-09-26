"""Mode-aware native evidence checks for the fixed matched corpus."""
import math

from . import benchmark_suite, matched_recipes, smoke_http

RESPONSE_CONTRACT_SHA256 = '820F53B9D454A58D641283FE8C1383F3891C2F75E9CE859F903F25BEC5D3D3F3'


def assess(row, observation, definition):
    """Return quality assessment and fatal errors; attach compact native evidence."""
    correctness, base_errors = benchmark_suite._assess(row, observation, definition)
    errors = [error for error in base_errors if error != 'known_correctness_failure']
    metrics = observation.get('metrics') or {}
    usage = observation.get('usage') or {}
    timings = observation.get('timings') or {}
    gufo = usage.get('gufo') or {}
    details = usage.get('prompt_tokens_details') or {}
    mtp = definition['profile_id'] == matched_recipes.PROFILE_MTP
    evidence = dict(mode='mtp' if mtp else 'ar', proposed=None, accepted=None,
        acceptance_ratio=None, acceptance_reason='unavailable', lookup_provenance=None,
        quality_failed='known_correctness_failure' in base_errors and observation.get('success') is True,
        expected_prompt_tokens=row['expected_prompt_tokens'], actual_prompt_tokens=None,
        sustained_256_eligible=False)
    observation['matched_evidence'] = evidence

    def integer(source, name, *, minimum=0):
        value = source.get(name) if isinstance(source, dict) else None
        if type(value) is not int or value < minimum:
            errors.append('invalid_'+name)
            return None
        return value

    if observation.get('success') is not True:
        errors.append(observation.get('error') or 'request_failed')
    if observation.get('validation_errors'):
        errors.append('transport_validation_failed')
    if not isinstance(usage, dict) or not isinstance(timings, dict) or not isinstance(gufo, dict) or not isinstance(details, dict):
        errors.append('native_counters_missing')
    proposed = integer(usage, 'draft_tokens')
    accepted = integer(usage, 'draft_tokens_accepted')
    timing_proposed = integer(timings, 'draft_n')
    timing_accepted = integer(timings, 'draft_n_accepted')
    evidence.update(proposed=proposed, accepted=accepted,
                    unaccepted_proposals=proposed-accepted if proposed is not None and accepted is not None and accepted <= proposed else None)
    if None not in (proposed, accepted, timing_proposed, timing_accepted):
        if (accepted > proposed or timing_proposed != proposed or timing_accepted != accepted
                or not mtp and (proposed != 0 or accepted != 0)):
            errors.append('draft_counters_disagree')
        if mtp:
            if proposed:
                ratio = accepted / proposed
                evidence.update(acceptance_ratio=ratio, acceptance_reason='positive_proposals')
                reported = metrics.get('mtp_acceptance')
                if type(reported) not in (int, float) or not math.isfinite(reported) or abs(reported-ratio) > 1e-12:
                    errors.append('acceptance_ratio_disagrees')
            else:
                evidence['acceptance_reason'] = 'no_proposals'
                if accepted or metrics.get('mtp_acceptance') is not None:
                    errors.append('acceptance_ratio_disagrees')
        else:
            evidence['acceptance_reason'] = 'not_applicable'
            if metrics.get('mtp_acceptance') is not None:
                errors.append('unexpected_acceptance')

    lookup = ('lookup_n', 'lookup_n_accepted')
    present = [name in timings for name in lookup]
    if present == [False, False]:
        evidence['lookup_provenance'] = 'omitted_when_zero_in_pinned_emitter'
    elif present == [True, True] and all(type(timings[name]) is int and timings[name] == 0 for name in lookup):
        evidence['lookup_provenance'] = 'explicit_zero'
    else:
        errors.append('lookup_not_zero')

    prompt = integer(usage, 'prompt_tokens', minimum=1)
    completion = integer(usage, 'completion_tokens', minimum=1)
    total = integer(usage, 'total_tokens', minimum=1)
    prefill = integer(gufo, 'prefill_tokens', minimum=1)
    timing_prompt = integer(timings, 'prompt_n', minimum=1)
    predicted = integer(timings, 'predicted_n', minimum=1)
    evidence['actual_prompt_tokens'] = prompt
    if (prompt != row['expected_prompt_tokens'] or prefill != prompt or timing_prompt != prompt
            or metrics.get('logical_prompt_tokens') != prompt or metrics.get('new_prefill_tokens') != prompt):
        errors.append('prompt_count_disagrees')
    if (completion is None or prompt is None or completion > row['output_budget']
            or predicted != completion or metrics.get('completion_tokens') != completion
            or total != prompt+completion):
        errors.append('completion_count_disagrees')
    if row['output_budget'] == 1 and completion != 1:
        errors.append('single_output_count_disagrees')
    for source, name in ((usage,'cached_tokens'), (details,'cached_tokens'),
                         (timings,'cache_n'), (gufo,'cache_restore_bytes'),
                         (gufo,'cache_disk_queued_bytes')):
        value = integer(source,name)
        if value is not None and value != 0:
            errors.append('nonzero_'+name)
    if metrics.get('cached_prompt_tokens') != 0 or gufo.get('cache_hit') is not False or gufo.get('cache_disk_hit') is not False:
        errors.append('cache_hit_or_count')
    if 'cache_common_prefix_tokens' in gufo:
        common = integer(gufo, 'cache_common_prefix_tokens')
        if common != 0:
            errors.append('cache_common_prefix_not_zero')
    snapshot_names=(
        'cache_snapshot_bytes','cache_shared_bytes','cache_shared_prefix_snapshots',
        'cache_shared_prefix_bytes')
    evidence['snapshot_fields']={}
    for name in snapshot_names:
        if name in gufo:
            value=integer(gufo,name)
            if value is not None:
                evidence['snapshot_fields'][name]=value
    for name in ('physical_execution_width','requested_logical_concurrency','resident_requests_at_admission'):
        if integer(gufo,name,minimum=1) != 1:
            errors.append('concurrency_'+name)
    if observation.get('observed_models') != [smoke_http.MODEL] or observation.get('reasoning_content') != '':
        errors.append('identity_or_reasoning_invalid')
    if row['case'] != 'TOOL' and observation.get('tool_calls') != []:
        errors.append('unexpected_tools')
    if row['case'] != 'TOOL' and observation.get('finish_reason') == 'tool_calls':
        errors.append('unexpected_tool_finish')
    if observation.get('finish_reason') not in ('stop','length','tool_calls'):
        errors.append('finish_invalid')
    evidence['sustained_256_eligible'] = (row['case'] == 'LONG' and completion == 256
        and observation.get('finish_reason') == 'length' and not errors)
    evidence['fatal_kind'] = ('native' if observation.get('error') == 'validation_failed' else 'transport') if observation.get('success') is not True else ('native' if errors else None)
    return correctness, list(dict.fromkeys(errors))
