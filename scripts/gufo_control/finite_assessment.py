"""Pure fixed-case assessment. Does not send requests, execute code or qualify a service."""
import ast
from hashlib import sha256
import json
import re

from . import finite_responses, smoke_http
from .finite_metrics import validate_metrics
from .finite_workload import Workload

_ADD = {ast.dump(ast.parse('def add(a, b):\n    return ' + expr),
                 include_attributes=False) for expr in ('a + b', 'b + a')}


def _contract(workload, index, attempt):
    if type(workload) is not Workload:
        raise ValueError('finite_assessment_workload')
    workload.__post_init__()
    post = workload.post(index, attempt)
    row = next(r for r in workload.document()['request_pool'] if r['id'] == post.request_id)
    return post, row, json.loads(post.step_json)


def _text_bytes(text):
    if type(text) is not str or len(text) > finite_responses.OUTPUT_LIMIT:
        raise ValueError('finite_assessment_text')
    raw = text.encode('utf-8', 'strict')
    if len(raw) > finite_responses.OUTPUT_LIMIT:
        raise ValueError('finite_assessment_text')
    return raw


def _valid_add(text):
    try:
        return ast.dump(ast.parse(text, type_comments=True), include_attributes=False) in _ADD
    except (SyntaxError, ValueError, RecursionError):
        return False


def _review_text(value, maximum):
    try:
        return type(value) is str and bool(value.strip()) and len(value.encode('utf-8')) <= maximum
    except UnicodeError:
        return False


def _review_status(review, digest, errors):
    if review is None:
        return 'pending_semantic_review'
    keys = {'reviewer', 'response_sha256', 'verdict', 'reason'}
    if (type(review) is not dict or set(review) != keys
            or not _review_text(review['reviewer'], 96)
            or review['response_sha256'] != digest
            or review['verdict'] not in ('pass', 'fail')
            or not _review_text(review['reason'], 512)):
        errors.append('invalid_semantic_review')
        return 'fail'
    if review['verdict'] == 'fail':
        errors.append('semantic_review_failed')
    return review['verdict']


def assess_positive(workload, index, attempt, parsed, *, semantic_review=None, previous=None):
    """Assess a COMPLETE decoded case, using the pinned step and helper counts.

    Caller must authenticate provenance, HTTP status/content type and timing
    evidence first. previous is a verified prior complete same-ID assessment.
    Manual response_sha256 refers to exact extracted text bytes, not HTTP wire.
    Pending prose review permits structural progression, not answer acceptance.
    """
    post, row, step = _contract(workload, index, attempt)
    check = step['check']
    allowed = {'exact_arithmetic_4', 'exact_german_fuenf', 'python_add_ast',
               'report_sum_integer_4', 'english_two_sentence_semantic_review'}
    if post.expected_status != 200 or check not in allowed:
        raise ValueError('finite_assessment_not_complete_positive')
    if type(parsed) is not dict:
        raise ValueError('finite_assessment_parsed')
    text, reasoning, tools = (parsed.get(k) for k in ('visible_answer', 'reasoning_content', 'tool_calls'))
    raw = _text_bytes(text)
    _text_bytes(reasoning)
    if type(tools) is not list:
        raise ValueError('finite_assessment_tools')
    request = smoke_http._json_object(post.body)
    output_limit = request.get('max_output_tokens', request.get('max_tokens'))
    counters = validate_metrics(post.route, parsed.get('usage'), parsed.get('timings'),
        expected_prompt=row['native_preparation']['framed_tokens'], output_limit=output_limit,
        allow_missing_usage=post.request_id == 'tool_chat_2304')
    errors = list(counters['errors'])
    observed = parsed.get('observed_models')
    if type(observed) is not list or any(model != smoke_http.MODEL for model in observed):
        errors.append('wrong_model')
    digest = sha256(raw).hexdigest().upper()
    fingerprint = digest
    answer_status = 'pass'
    if check == 'report_sum_integer_4':
        valid = (parsed.get('finish_reason') == 'tool_calls' and len(tools) == 1
                 and not text.strip() and not reasoning.strip())
        function = None
        if valid:
            call = tools[0]
            valid = (type(call) is dict and call.get('type') == 'function'
                     and type(call.get('id')) is str and bool(call['id']))
            function = call.get('function') if valid else None
            valid = (valid and type(function) is dict and function.get('name') == 'report_sum'
                     and type(function.get('arguments')) is str)
        arguments = None
        if valid:
            try:
                _text_bytes(function['arguments'])
                arguments = smoke_http._strict_json(function['arguments'])
                valid = (type(arguments) is dict and set(arguments) == {'sum'}
                         and type(arguments['sum']) is int and arguments['sum'] == 4)
            except (ValueError, UnicodeError, RecursionError):
                valid = False
        if not valid:
            errors.append('wrong_tool_answer')
        else:
            canonical = json.dumps(dict(name='report_sum', arguments=arguments),
                                   sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
            fingerprint = sha256(canonical).hexdigest().upper()
    else:
        if parsed.get('finish_reason') != 'stop' or tools or reasoning:
            errors.append('unexpected_terminal_tools_or_reasoning')
        if check == 'exact_arithmetic_4' and text.strip() != '4':
            errors.append('wrong_arithmetic_answer')
        elif check == 'exact_german_fuenf' and text.strip() != 'fünf':
            errors.append('wrong_german_answer')
        elif check == 'python_add_ast' and not _valid_add(text):
            errors.append('wrong_python_add_ast')
        elif check == 'english_two_sentence_semantic_review':
            if not text.strip():
                errors.append('empty_prose')
            answer_status = _review_status(semantic_review, digest, errors)
    if check != 'english_two_sentence_semantic_review' and semantic_review is not None:
        errors.append('unexpected_semantic_review')
    repeat = 'not_compared'
    if previous is not None:
        if (type(previous) is not dict
                or previous.get('request_id') != post.request_id
                or previous.get('request_body_sha256') != post.body_sha256
                or previous.get('route') != post.route
                or previous.get('structural_success') is not True
                or previous.get('answer_status') not in ('pass', 'pending_semantic_review')
                or type(previous.get('fingerprint')) is not str
                or re.fullmatch('[0-9A-F]{64}', previous['fingerprint']) is None):
            errors.append('invalid_repeat_reference')
            repeat = 'invalid_reference'
        elif previous['fingerprint'] != fingerprint:
            errors.append('inconsistent_repeat_answer')
            repeat = 'mismatch'
        else:
            repeat = 'match'
    errors = list(dict.fromkeys(errors))
    if errors:
        answer_status = 'fail'
    return dict(request_id=post.request_id, request_body_sha256=post.body_sha256,
                route=post.route, check=check, structural_success=not errors,
                answer_status=answer_status, fully_validated=not errors and answer_status == 'pass',
                answer_sha256=digest, fingerprint=fingerprint, repeat=repeat,
                native_metrics_valid=counters['valid'],
                metrics=counters['metrics'], unavailable_metrics=counters['unavailable'],
                errors=errors, semantic_review=(dict(semantic_review) if semantic_review is not None
                    and check == 'english_two_sentence_semantic_review'
                    and 'invalid_semantic_review' not in errors else None))


def assess_rejection(workload, index, attempt, status, content_type, body):
    """Expected status/code only; this does NOT establish the overlap rendezvous."""
    post, _, _ = _contract(workload, index, attempt)
    if post.expected_status == 200:
        raise ValueError('finite_assessment_not_rejection')
    errors = []
    code = None
    if type(status) is not int or status != post.expected_status:
        errors.append('unexpected_http_status')
    if (type(content_type) is not str
            or content_type.split(';', 1)[0].strip().lower() != 'application/json'):
        errors.append('wrong_rejection_content_type')
    if type(body) is not bytes or len(body) > finite_responses.BODY_LIMIT:
        errors.append('rejection_body_limit')
    else:
        try:
            value = smoke_http._json_object(body)
            error = value.get('error')
            if type(error) is not dict or type(error.get('code')) is not str:
                errors.append('missing_error_code')
            else:
                raw_code = error['code']
                code = raw_code if raw_code.isascii() and len(raw_code) <= 128 else None
                if code != post.expected_error:
                    errors.append('unexpected_error_code')
        except (smoke_http.SmokeError, RecursionError):
            errors.append('malformed_rejection')
    return dict(request_id=post.request_id, request_body_sha256=post.body_sha256,
                structural_success=not errors, request_contract_pass=not errors,
                inference_verified=False, overlap_verified=False,
                status=status, error_code=code, errors=list(dict.fromkeys(errors)))
