"""Immutable, offline request corpus shared by the matched AR and MTP profiles."""
from hashlib import sha256

from . import benchmark_recipes as base


PROFILE_AR = 'matched4k-iq4xs-ar-v1'
PROFILE_MTP = 'matched4k-iq4xs-mtp-length-d1-v1'
REFERENCE_PROFILE = 'ar4k-iq4xs-correctness-pp1-v2'
REFERENCE_RESULT_SHA256 = '692149EEB38F89E662D9428A725533F14793680F5C70E8477A3B53E2DE8B04F3'
REQUESTS_SHA256 = 'EF677B664873CC42C07E4A22DA69723D6743AB57BF7944A0163A8E4799F394AB'
CALIBRATION = (13, 373)
PROMPT_COUNTS = (26, 61, 61, 115, 115, 55, 55, 326, 326, 71, 71, 115,
                 115, 55, 55, 326, 326, 71, 71, 61, 61, 55, 55, 326,
                 326, 71, 71, 61, 61, 115, 115, 13, 373, 2047, 2047, 2047)
_IDENTITY_FIELDS = ('ordinal', 'kind', 'case', 'mode', 'repetition',
                    'target_prompt_tokens', 'cache_prompt', 'output_budget')


def validate_fixture() -> list[dict]:
    """Rebuild and verify the complete ordered corpus without historical I/O."""
    try:
        definition = base.recipe_definition(REFERENCE_PROFILE)
        rows = definition['schedule']
        if len(rows) != len(PROMPT_COUNTS) or any(
            type(row['ordinal']) is not int or row['ordinal'] != index
            for index, row in enumerate(rows)
        ):
            raise ValueError('matched_fixture_changed')
        requests = [base.request_for(row, CALIBRATION) for row in rows]
        digest = sha256(base.canonical(requests).encode('utf-8')).hexdigest().upper()
        if digest != REQUESTS_SHA256:
            raise ValueError('matched_fixture_changed')
        return requests
    except (KeyError, TypeError, IndexError, ValueError, OverflowError) as exc:
        raise ValueError('matched_fixture_changed') from exc


def recipe_definition(profile_id: str) -> dict:
    if profile_id not in (PROFILE_AR, PROFILE_MTP):
        raise ValueError('unknown_profile')
    validate_fixture()
    definition = base.recipe_definition(REFERENCE_PROFILE)
    definition['profile_id'] = profile_id
    definition['max_prompt_tokens'] = 2304
    mtp = profile_id == PROFILE_MTP
    definition.update(
        reference_profile=REFERENCE_PROFILE,
        reference_result_sha256=REFERENCE_RESULT_SHA256,
        matched_requests_sha256=REQUESTS_SHA256,
        fixed_calibration=list(CALIBRATION),
        input_count_provenance='same_pinned_tokenizer_template_and_request',
        speculative=mtp,
        draft_tokens=1 if mtp else 0,
        mtp_policy='length' if mtp else None,
        mtp_draft_vocab='full' if mtp else None,
    )
    for row, count in zip(definition['schedule'], PROMPT_COUNTS):
        row['expected_prompt_tokens'] = count
    return definition


def recipe_json(profile_id: str) -> str:
    return base.canonical(recipe_definition(profile_id))


def _validate_calibration(calibration) -> None:
    if calibration is None:
        return
    if type(calibration) not in (list, tuple) or len(calibration) > 2:
        raise ValueError('invalid_calibration_counts')
    if (any(type(value) is not int for value in calibration)
            or tuple(calibration) != CALIBRATION[:len(calibration)]):
        raise ValueError('invalid_calibration_counts')


def request_for(row, calibration=None) -> dict:
    _validate_calibration(calibration)
    if not isinstance(row, dict):
        raise ValueError('matched_row_changed')
    ordinal = row.get('ordinal')
    if type(ordinal) is not int or not 0 <= ordinal < len(PROMPT_COUNTS):
        raise ValueError('matched_row_changed')
    expected_rows = base.recipe_definition(REFERENCE_PROFILE)['schedule']
    reference = expected_rows[ordinal]
    if any(field not in row or type(row[field]) is not type(reference[field])
           or row[field] != reference[field] for field in _IDENTITY_FIELDS):
        raise ValueError('matched_row_changed')
    if 'expected_prompt_tokens' in row and (
        type(row['expected_prompt_tokens']) is not int
        or row['expected_prompt_tokens'] != PROMPT_COUNTS[ordinal]
    ):
        raise ValueError('matched_row_changed')
    return validate_fixture()[ordinal]


def validate_request(row, request) -> int:
    expected = request_for(row)
    if not isinstance(request, dict):
        raise ValueError('matched_request_changed')
    try:
        if base.canonical(request) != base.canonical(expected):
            raise ValueError('matched_request_changed')
    except (TypeError, OverflowError) as exc:
        raise ValueError('matched_request_changed') from exc
    count = PROMPT_COUNTS[row['ordinal']]
    if count > 2304 or count + row['output_budget'] > 4096:
        raise ValueError('matched_request_capacity')
    return count


def validate_answer(case, observation):
    return base.validate_answer(case, observation)
