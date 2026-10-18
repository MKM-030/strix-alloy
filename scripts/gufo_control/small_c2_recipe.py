"""Fixed three-call, two-session GUFO C2 request manifest."""
from copy import deepcopy

from . import benchmark_recipes as base, complete_answer_recipe as complete


ID = 'small-c2-mtp-d3-20260927-v1'
CASES = ('code_a', 'proof_a')
CORPUS = complete.CORPUS
CORPUS_SHA = complete.CORPUS_SHA


def corpus():
    prompts = complete.corpus()
    return {case: prompts[case] for case in CASES}


def recipe_definition(profile_id):
    if profile_id != ID:
        raise ValueError('unknown_recipe')
    definition = complete.recipe_definition(complete.ID)
    schedule = [deepcopy(definition['schedule'][0])]
    schedule.extend(deepcopy(row) for row in definition['schedule']
                    if row['case'] in CASES)
    for ordinal, row in enumerate(schedule):
        row['ordinal'] = ordinal
    definition.update(profile_id=ID, schedule=schedule, max_requests=3,
        max_prompt_tokens=256, max_output_tokens=1024,
        corpus_prompts=corpus(), physical_sessions=2,
        per_session_context_tokens=4096, max_occupied_context_tokens=1280,
        requested_logical_concurrency=2, max_pending_requests=2,
        max_pending_requests_per_client=2,
        pair_submission='concurrent_after_sequential_warmup',
        pair_require_physical_execution_width=2,
        pair_require_execution_plan='batched-w2',
        max_generation_calls=3, retries=0,
        common_window_decode_tokens_per_second=None)
    if len(schedule) != 3 or [row['case'] for row in schedule] != ['WARMUP', *CASES]:
        raise ValueError('schedule_changed')
    return definition


def recipe_json(profile_id):
    return base.canonical(recipe_definition(profile_id))


def request_for(row, calibration=None):
    return complete.request_for(row, calibration)


def validate_request(row, request):
    schedule = recipe_definition(ID)['schedule']
    ordinal = row.get('ordinal')
    if type(ordinal) is not int or not 0 <= ordinal < len(schedule):
        raise ValueError('schedule_changed')
    expected = schedule[ordinal]
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError('schedule_changed')
    if base.canonical(request) != base.canonical(request_for(expected)):
        raise ValueError('request_changed')


def assess(row, observation, definition):
    correctness, errors = complete.assess(row, observation, definition)
    if row['case'] in CASES:
        prompt = (observation.get('metrics') or {}).get('logical_prompt_tokens')
        if type(prompt) is not int or not 1 <= prompt <= 256:
            if 'complete_input_count_invalid' not in errors:
                errors.append('complete_input_count_invalid')
            correctness['state'] = 'failed'
            observation['matched_evidence'].update(quality_failed=True, fatal_kind='native')
    return correctness, errors
