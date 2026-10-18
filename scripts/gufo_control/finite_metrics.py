"""Native-counter validation for the fixed AR/cold lifecycle, not launch authority."""
import math

from . import benchmark_http, smoke_http
from .finite_responses import CHAT, RESPONSES, MESSAGES


_RATE_TOLERANCE = 1e-9


def _finite_number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _check_redundant_number(source, name, expected, errors, unavailable, label):
    if name not in source:
        unavailable.append(label)
        return
    actual = _finite_number(source[name])
    if actual is None:
        errors.append('invalid_' + label)
    elif expected is None:
        errors.append(label + '_unverifiable')
    elif not math.isclose(actual, expected, rel_tol=_RATE_TOLERANCE,
                          abs_tol=_RATE_TOLERANCE):
        errors.append(label + '_disagrees')


def validate_metrics(route, usage, timings, *, expected_prompt, output_limit,
                     allow_missing_usage=False):
    """Return compact derived metrics; never replace the original wire usage.

    Mapping non-Chat counters into the existing validator is internal only.
    Missing lookup counters stay unavailable; omitted zero-only source fields
    are not rewritten as measured zeros. This AR profile forbids positive drafts.
    """
    if (route not in (CHAT, RESPONSES, MESSAGES)
            or type(expected_prompt) is not int or not 1 <= expected_prompt <= 2304
            or type(output_limit) is not int or not 1 <= output_limit <= 256
            or type(allow_missing_usage) is not bool
            or (allow_missing_usage and route != CHAT)):
        raise ValueError('finite_metrics_contract')
    errors, unavailable = [], []
    if type(timings) is not dict:
        timings = {}
        errors.append('missing_timings')
    native = {}
    for name in ('prompt_n', 'cache_n', 'predicted_n', 'draft_n', 'draft_n_accepted'):
        value = smoke_http._int_or_none(timings.get(name))
        native[name] = value
        if value is None:
            errors.append('missing_or_invalid_timings.' + name)
            unavailable.append('timings.' + name)
    p, c, out = (native[k] for k in ('prompt_n', 'cache_n', 'predicted_n'))
    logical = p + c if p is not None and c is not None else None
    if logical is not None and logical != expected_prompt:
        errors.append('prepared_prompt_count_disagrees')
    if p is not None and p > expected_prompt:
        errors.append('prefill_exceeds_' + str(expected_prompt))
    if c is not None and c > expected_prompt:
        errors.append('cached_prompt_exceeds_' + str(expected_prompt))
    if out == 0:
        errors.append('empty_generation')
    if out is not None and out > output_limit:
        errors.append('completion_exceeds_' + str(output_limit))
    for name in ('draft_n', 'draft_n_accepted'):
        if native[name] not in (None, 0):
            errors.append('drafting_in_ar_profile')
    lookup = {}
    for name in ('lookup_n', 'lookup_n_accepted'):
        if name not in timings:
            lookup[name] = None
            unavailable.append('timings.' + name)
        else:
            lookup[name] = smoke_http._int_or_none(timings[name])
            if lookup[name] is None or lookup[name] != 0:
                errors.append('lookup_in_ar_profile_or_invalid')
    if ('lookup_n' in timings) != ('lookup_n_accepted' in timings):
        errors.append('incomplete_lookup_pair')

    source = 'usage.prompt_tokens' if route == CHAT else 'usage.input_tokens'
    if usage is None and allow_missing_usage:
        normalized = dict(prompt_tokens=logical, completion_tokens=out)
        source = 'derived:timings.prompt_n+timings.cache_n'
        unavailable.append('usage')
    elif type(usage) is not dict:
        normalized = {}
        errors.append('missing_or_invalid_usage')
        unavailable.append('usage')
    elif route == CHAT:
        normalized = dict(usage)
    else:
        normalized = dict(prompt_tokens=usage.get('input_tokens'),
                          completion_tokens=usage.get('output_tokens'))
        if 'total_tokens' in usage:
            normalized['total_tokens'] = usage['total_tokens']
        if route == RESPONSES:
            details = usage.get('input_tokens_details')
            if type(details) is not dict:
                errors.append('missing_or_invalid_usage.input_tokens_details')
                details = {}
            normalized['prompt_tokens_details'] = dict(cached_tokens=details.get('cached_tokens'))
            if 'cache_write_tokens' in details:
                value = smoke_http._int_or_none(details['cache_write_tokens'])
                if value is None or p is None or value != p:
                    errors.append('cache_write_tokens_disagree')
        else:
            normalized['cached_tokens'] = usage.get('cache_read_input_tokens')
            if 'cache_creation_input_tokens' in usage:
                value = smoke_http._int_or_none(usage['cache_creation_input_tokens'])
                if value != 0:
                    errors.append('invalid_compatibility_cache_creation_field')
    # Add only internal comparison keys backed by native draft counters.
    for key, native_key in (('draft_tokens', 'draft_n'), ('draft_tokens_accepted', 'draft_n_accepted')):
        if key in normalized:
            value = smoke_http._int_or_none(normalized[key])
            if value is None or value != native[native_key]:
                errors.append(key + '_disagrees')
        elif native[native_key] is not None:
            normalized[key] = native[native_key]
    gufo = normalized.get('gufo', {})
    if type(gufo) is dict:
        for flag in ('cache_hit', 'cache_disk_hit'):
            if flag in gufo and type(gufo[flag]) is not bool:
                errors.append('invalid_' + flag)
    try:
        metrics, problems, _ = smoke_http._validate_usage(
            normalized, timings, max_prompt_tokens=expected_prompt,
            max_completion_tokens=output_limit, cache_policy='cold')
    except OverflowError:
        metrics = dict(logical_prompt_tokens=logical, new_prefill_tokens=p,
                       cached_prompt_tokens=c, completion_tokens=out)
        problems = ['unrepresentable_metric_number']
    errors.extend(problems)
    for key in ('prompt_ms', 'predicted_ms'):
        if key not in timings:
            unavailable.append('timings.' + key)

    prompt_ms = metrics.get('engine_timing_prompt_ms')
    predicted_ms = metrics.get('engine_timing_predicted_ms')
    prompt_count_valid = p is not None and p <= expected_prompt
    output_count_valid = out is not None and 0 < out <= output_limit
    expected_values = {
        'prompt_per_token_ms': prompt_ms / p if prompt_count_valid and p > 0 and prompt_ms is not None else None,
        'prompt_per_second': p * 1000.0 / prompt_ms if prompt_count_valid and prompt_ms and prompt_ms > 0 else
                             (0.0 if prompt_count_valid and prompt_ms == 0 else None),
        'predicted_per_token_ms': predicted_ms / out if output_count_valid and predicted_ms is not None else None,
        'predicted_per_second': out * 1000.0 / predicted_ms if output_count_valid and predicted_ms and predicted_ms > 0 else
                                (0.0 if output_count_valid and predicted_ms == 0 else None),
    }
    for name, expected in expected_values.items():
        _check_redundant_number(timings, name, expected, errors, unavailable,
                                'timings.' + name)
    if route == CHAT and type(usage) is dict:
        _check_redundant_number(usage, 'prompt_tokens_per_second',
                                expected_values['prompt_per_second'], errors,
                                unavailable, 'usage.prompt_tokens_per_second')
        _check_redundant_number(usage, 'completion_tokens_per_second',
                                expected_values['predicted_per_second'], errors,
                                unavailable, 'usage.completion_tokens_per_second')
    metrics.update(logical_prompt_tokens_source=source, lookup_tokens=lookup['lookup_n'],
                   lookup_tokens_accepted=lookup['lookup_n_accepted'])
    errors = list(dict.fromkeys(errors))
    benchmark_http._rates(metrics, errors, pp1=False)
    for key, value in metrics.items():
        if value is None:
            unavailable.append(key)
    return dict(valid=not errors, metrics=metrics, errors=errors,
                unavailable=list(dict.fromkeys(unavailable)))
