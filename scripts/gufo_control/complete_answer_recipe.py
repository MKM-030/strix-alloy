"""Fixed seven-request complete-answer adaptation for native GUFO evidence."""
from copy import deepcopy

from . import benchmark_recipes as base, halogen_mtp_recipe as halogen, smoke_http


ID = 'complete-answer-mtp-d3-20260927-v1'
CASES = ('code_a', 'proof_a', 'proc_b', 'prose_b', 'DE', 'ARITH')
CORPUS = halogen.CORPUS
CORPUS_SHA = halogen.CORPUS_SHA
ARITH_PROMPT = ('Return only a JSON object with keys sum and product. Compute sum = 17 + 25 '
                'and product = 6 * 7. Do not include Markdown.')
# A conservative fixed allowance for the chat template and message delimiters.
PROMPT_WRAPPER_BYTES = 128


def corpus():
    source = halogen.corpus()  # Rechecks the original corpus hash and schema.
    prompts = {case: source[case] for case in CASES if case in halogen.CASES}
    prompts['DE'] = base.FIXTURES['DE']['prompt']
    prompts['ARITH'] = ARITH_PROMPT
    for case in CASES:
        prompt = prompts[case]
        if (not isinstance(prompt, str) or not prompt or
                len(prompt.encode('utf-8')) > 1024 or
                len(prompt.encode('utf-8')) + PROMPT_WRAPPER_BYTES >= 2304):
            raise ValueError('corpus_prompt_bound')
    return prompts


def recipe_definition(profile_id):
    if profile_id != ID:
        raise ValueError('unknown_recipe')
    prompts = corpus()
    definition = base.recipe_definition(base.PROFILE_4K)
    warmup = deepcopy(definition['schedule'][0])
    schedule = [warmup]
    for case in CASES:
        schedule.append(dict(ordinal=len(schedule), kind='correctness', case=case,
            mode='greedy', repetition=0, target_prompt_tokens=None,
            cache_prompt=False, output_budget=1024))
    definition.update(profile_id=ID, context_tokens=4096, max_prompt_tokens=2304,
        max_output_tokens=1024, max_requests=7, schedule=schedule,
        corpus_sha256=CORPUS_SHA, corpus_prompts=prompts,
        prompt_wrapper_bytes=PROMPT_WRAPPER_BYTES,
        speculative=True, draft_tokens=3, mtp_policy='length', mtp_draft_vocab='full',
        observed_prompt_counts_required=True,
        semantic_approval='independent_review_required')
    return definition


def recipe_json(profile_id):
    return base.canonical(recipe_definition(profile_id))


def request_for(row, calibration=None):
    if row['case'] == 'WARMUP':
        return base.request_for(row, calibration)
    if row['case'] not in CASES:
        raise ValueError('unknown_case')
    request = deepcopy(smoke_http.REQUEST)
    request.update(messages=[dict(role='user', content=corpus()[row['case']])],
                   max_tokens=1024, stream=False)
    request.pop('stream_options')
    return request


def validate_request(row, request):
    schedule = recipe_definition(ID)['schedule']
    ordinal = row.get('ordinal')
    if type(ordinal) is not int or not 0 <= ordinal < len(schedule):
        raise ValueError('schedule_changed')
    expected_row = schedule[ordinal]
    if any(row.get(key) != value for key, value in expected_row.items()):
        raise ValueError('schedule_changed')
    if base.canonical(request) != base.canonical(request_for(expected_row)):
        raise ValueError('request_changed')


def assess(row, observation, definition):
    """Return only transport/native failures as fatal suite errors."""
    errors = []
    if observation.get('success') is not True:
        errors.append(observation.get('error') or 'request_failed')
    for error in observation.get('validation_errors') or []:
        if error not in errors:
            errors.append(error)

    metrics = observation.get('metrics') or {}
    prompt = metrics.get('logical_prompt_tokens')
    output = metrics.get('completion_tokens')
    cached = metrics.get('cached_prompt_tokens')
    new = metrics.get('new_prefill_tokens')
    if type(prompt) is not int or not 1 <= prompt <= definition['max_prompt_tokens']:
        errors.append('prompt_count_invalid')
    if type(output) is not int or not 1 <= output <= row['output_budget']:
        errors.append('output_count_invalid')
    if type(cached) is not int or cached != 0 or type(new) is not int or new != prompt:
        errors.append('unexpected_cache')
    if type(prompt) is int and prompt + row['output_budget'] > definition['context_tokens']:
        errors.append('context_overflow')

    proposed, accepted = metrics.get('draft_tokens'), metrics.get('draft_tokens_accepted')
    if (type(proposed) is not int or type(accepted) is not int
            or not 0 <= accepted <= proposed):
        errors.append('draft_counters_invalid')
    usage = observation.get('usage') or {}
    timings = observation.get('timings') or {}
    for value, usage_key, timing_key in ((proposed, 'draft_tokens', 'draft_n'),
                                         (accepted, 'draft_tokens_accepted', 'draft_n_accepted')):
        values = (value, usage.get(usage_key), timings.get(timing_key))
        if any(type(item) is not int or item < 0 for item in values) or len(set(values)) != 1:
            errors.append('draft_counters_disagree')
    models = observation.get('observed_models')
    if not isinstance(models, list) or not models or any(model != smoke_http.MODEL for model in models):
        errors.append('model_identity_invalid')
    if (not isinstance(observation.get('visible_answer'), str)
            or not observation['visible_answer'].strip()
            or observation.get('reasoning_content')
            or observation.get('tool_calls')
            or observation.get('finish_reason') not in ('stop', 'length')):
        errors.append('unexpected_output_shape')

    if row['case'] in ('WARMUP', 'DE'):
        correctness = base.validate_answer(row['case'], observation)
    elif row['case'] == 'ARITH':
        try:
            value = smoke_http._strict_json(observation.get('visible_answer', ''))
            valid = (type(value) is dict and set(value) == {'sum', 'product'}
                     and type(value['sum']) is int and value['sum'] == 42
                     and type(value['product']) is int and value['product'] == 42)
        except (ValueError, TypeError, RecursionError):
            valid = False
        correctness = dict(state='passed' if valid else 'failed',
                           budget_exhausted=observation.get('finish_reason') == 'length')
    else:
        correctness = dict(state='needs_review',
                           budget_exhausted=observation.get('finish_reason') == 'length')

    quality_failed = correctness['state'] == 'failed'
    if errors:
        correctness['state'] = 'failed'
        quality_failed = True
    transport = observation.get('success') is not True and observation.get('error') != 'validation_failed'
    observation['matched_evidence'] = dict(quality_failed=quality_failed,
        semantic_status=('pending_not_certified' if correctness['state'] in
                         ('needs_review', 'semantic_review_pending') else correctness['state']),
        proposed=proposed, accepted=accepted, sustained_256_eligible=False,
        fatal_kind=('transport' if transport else 'native') if errors else None)
    return correctness, errors
