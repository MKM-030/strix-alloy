"""Fixed Halogen-corpus adaptation within the existing 4k/36-request bounds."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from . import benchmark_recipes as base, benchmark_suite, smoke_http

ID = 'halogen-ten-mtp-d3-20260927-v1'
CORPUS = Path(r'C:\Projects\strix-alloy-research\sources\halogen-flash-server\tools\eval-prompts.json')
CORPUS_SHA = '23DF9FEB5EC2B343F675BB08DC6C0C2286E17DD6D73ACF4E7D363D0C0C49922B'
CASES = ('code_a','code_b','proof_a','proof_b','proc_a','proc_b',
         'chat_a','chat_b','prose_a','prose_b')


def corpus():
    data = CORPUS.read_bytes()
    if sha256(data).hexdigest().upper() != CORPUS_SHA:
        raise ValueError('corpus_changed')
    value = json.loads(data)
    if tuple(k for k in value if not k.startswith('_')) != CASES:
        raise ValueError('corpus_schema')
    if any(not isinstance(value[k], str) or len(value[k].encode()) > 256 for k in CASES):
        raise ValueError('corpus_prompt_bound')
    return value


def recipe_definition(profile_id):
    if profile_id != ID:
        raise ValueError('unknown_recipe')
    prompts = corpus()
    definition = base.recipe_definition(base.PROFILE_4K)
    old = definition['schedule']
    schedule = [deepcopy(row) for row in old if row['case'] in ('WARMUP','CALIBRATION','PP1')]
    for rep in range(3):
        for case in CASES:
            schedule.append(dict(kind='measurement',case=case,mode='greedy',repetition=rep,
                target_prompt_tokens=None,cache_prompt=False,output_budget=256))
    for ordinal, row in enumerate(schedule):
        row['ordinal'] = ordinal
    definition.update(profile_id=ID, max_prompt_tokens=2304, schedule=schedule,
        corpus_sha256=CORPUS_SHA, corpus_prompts={k:prompts[k] for k in CASES},
        source_commit='c8270bb31cd824a0bf53fe9ecf80059c13e7a5bf',
        speculative=True,draft_tokens=3,mtp_policy='length',mtp_draft_vocab='full',
        exact_historical_protocol=False,
        comparison='Same ten prompts; GUFO explicit greedy/thinking-off/cache-bypass; historical Halogen low-effort thinking differs',
        observed_prompt_counts_required=True)
    if len(schedule) != 36:
        raise ValueError('schedule_count')
    return definition


def recipe_json(profile_id):
    return base.canonical(recipe_definition(profile_id))


def request_for(row, calibration=None):
    if row['case'] not in CASES:
        return base.request_for(row, calibration)
    request = deepcopy(smoke_http.REQUEST)
    request.update(messages=[dict(role='user',content=corpus()[row['case']])],
                   max_tokens=256, stream=False)
    request.pop('stream_options')
    return request


def validate_request(row, request):
    expected_row = recipe_definition(ID)['schedule'][row['ordinal']]
    if any(row.get(k) != v for k,v in expected_row.items()):
        raise ValueError('schedule_changed')
    expected = request_for(expected_row, (13,373))
    if base.canonical(request) != base.canonical(expected):
        raise ValueError('request_changed')


def assess(row, observation, definition):
    if row['case'] not in CASES:
        correctness, errors = benchmark_suite._assess(row, observation, definition)
    else:
        errors = []
        if observation.get('success') is not True:
            errors.append(observation.get('error') or 'request_failed')
        m = observation.get('metrics', {})
        prompt, output = m.get('logical_prompt_tokens'), m.get('completion_tokens')
        if type(prompt) is not int or not 1 <= prompt <= 2304:
            errors.append('prompt_count_invalid')
        if type(output) is not int or not 1 <= output <= 256:
            errors.append('output_count_invalid')
        if m.get('cached_prompt_tokens') != 0 or m.get('new_prefill_tokens') != prompt:
            errors.append('unexpected_cache')
        if (not isinstance(observation.get('visible_answer'), str)
                or not observation['visible_answer'].strip() or observation.get('reasoning_content')
                or observation.get('tool_calls') or observation.get('finish_reason') not in ('stop','length')):
            errors.append('unexpected_output_shape')
        correctness = dict(state='needs_review', budget_exhausted=observation.get('finish_reason')=='length')
    m = observation.get('metrics', {})
    proposed, accepted = m.get('draft_tokens'), m.get('draft_tokens_accepted')
    if (type(proposed) is not int or type(accepted) is not int
            or not 0 <= accepted <= proposed):
        errors.append('draft_counters_invalid')
    usage = observation.get('usage') or {}
    timings = observation.get('timings') or {}
    for value, usage_key, timing_key in ((proposed, 'draft_tokens', 'draft_n'),
                                       (accepted, 'draft_tokens_accepted', 'draft_n_accepted')):
        values = (value, usage.get(usage_key), timings.get(timing_key))
        if any(type(v) is not int or v < 0 for v in values) or len(set(values)) != 1:
            errors.append('draft_counters_disagree')
    models = observation.get('observed_models')
    if not isinstance(models, list) or not models or any(v != smoke_http.MODEL for v in models):
        errors.append('model_identity_invalid')
    observation['matched_evidence'] = dict(quality_failed=bool(errors),
        semantic_status='pending_not_certified', proposed=proposed,accepted=accepted,
        sustained_256_eligible=False, fatal_kind='native' if errors else None)
    if errors:
        correctness['state'] = 'failed'
    return correctness, errors
