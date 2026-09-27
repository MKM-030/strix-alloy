"""Pure response decoding for finite qualification; no network or launch authority.

This module extracts evidence, not answer correctness or valid benchmark rates.
Native usage/timings remain raw and must pass the separate metric/answer checks.
"""
import math
import re

from . import benchmark_http, smoke_http
from .finite_workload import PreparedPost

BODY_LIMIT = 7340032
OUTPUT_LIMIT = 1048576
PART_LIMIT = 65536
CHAT = '/v1/chat/completions'
RESPONSES = '/v1/responses'
MESSAGES = '/v1/messages'


def _fail(code):
    raise smoke_http.SmokeError('finite_response_' + code)


def _body(raw):
    if type(raw) is not bytes or len(raw) > BODY_LIMIT:
        _fail('body_limit')
    return smoke_http._json_object(raw)


def _text(value):
    if type(value) is not str:
        _fail('text')
    try:
        if len(value.encode('utf-8', 'strict')) > OUTPUT_LIMIT:
            _fail('output_limit')
    except UnicodeError:
        _fail('text_utf8')
    return value


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _parts(parts, submitted):
    if (not _finite_number(submitted)
            or submitted < 0 or type(parts) not in (list, tuple)
            or len(parts) > PART_LIMIT):
        _fail('parts')
    size, previous = 0, submitted
    for pair in parts:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            _fail('parts')
        part, arrived = pair
        if (type(part) is not bytes or not part
                or not _finite_number(arrived)
                or arrived < previous):
            _fail('parts')
        size += len(part)
        if size > BODY_LIMIT:
            _fail('body_limit')
        previous = arrived
    return parts


def _base(value, text, reason):
    usage, timings = value.get('usage'), value.get('timings')
    if type(usage) is not dict or type(timings) is not dict:
        _fail('usage_timings')
    model = value.get('model')
    if 'model' in value and (type(model) is not str or not model):
        _fail('model')
    return dict(visible_answer=_text(text), reasoning_content='', tool_calls=[],
                finish_reason=reason, usage=usage, timings=timings,
                observed_models=[] if model is None else [model],
                first_visible_content_ms=None, first_tool_call_ms=None,
                first_useful_output_ms=None)


def _text_blocks(blocks, kind):
    if type(blocks) is not list:
        _fail('content')
    result = []
    size = 0
    for block in blocks:
        if type(block) is not dict or block.get('type') != kind:
            _fail('content')
        text = _text(block.get('text'))
        size += len(text.encode('utf-8'))
        if size > OUTPUT_LIMIT:
            _fail('output_limit')
        result.append(text)
    return ''.join(result)


def _responses(value):
    if (value.get('object') != 'response' or value.get('status') != 'completed'
            or value.get('error') is not None
            or value.get('incomplete_details') is not None):
        _fail('terminal')
    output = value.get('output')
    if type(output) is not list:
        _fail('content')
    text = []
    for item in output:
        if (type(item) is not dict or item.get('type') != 'message'
                or item.get('role') != 'assistant' or item.get('status') != 'completed'):
            _fail('content')
        text.append(_text_blocks(item.get('content'), 'output_text'))
    return _base(value, ''.join(text), 'stop')


def parse_buffered(body, path):
    value = _body(body)
    if path == CHAT:
        result = benchmark_http._parse_json_response(body, path)
    elif path == RESPONSES:
        result = _responses(value)
    elif path == MESSAGES:
        if (value.get('type') != 'message' or value.get('role') != 'assistant'
                or value.get('stop_reason') != 'end_turn' or 'error' in value):
            _fail('terminal')
        result = _base(value, _text_blocks(value.get('content'), 'text'), 'stop')
    else:
        _fail('route')
    return _validate_extracted(result)


def _validate_extracted(result):
    total = len(_text(result['visible_answer']).encode('utf-8'))
    total += len(_text(result['reasoning_content']).encode('utf-8'))
    for tool in result['tool_calls']:
        function = tool['function']
        total += len(_text(function['name']).encode('utf-8'))
        total += len(_text(function['arguments']).encode('utf-8'))
    if total > OUTPUT_LIMIT:
        _fail('output_limit')
    if result['finish_reason'] not in ('stop', 'tool_calls'):
        _fail('terminal')
    if any(model != smoke_http.MODEL for model in result['observed_models']):
        _fail('model')
    return result


def _events(parts):
    """Yield strict semantic SSE frames; timestamps are receive observations."""
    pending = b''
    for part, arrived in parts:
        data = pending + part
        offset = 0
        for match in re.finditer(rb'\r?\n\r?\n', data):
            frame = data[offset:match.start()]
            offset = match.end()
            try:
                lines = [line.removesuffix('\r') for line in frame.decode('utf-8', 'strict').split('\n')]
            except UnicodeError:
                _fail('sse_utf8')
            names, payload = [], []
            for line in lines:
                if not line or line.startswith(':'):
                    continue
                field, separator, content = line.partition(':')
                if not separator or field not in ('event', 'data'):
                    _fail('sse_field')
                content = content[1:] if content.startswith(' ') else content
                (names if field == 'event' else payload).append(content)
            if not names and not payload:
                continue
            if len(names) != 1 or not payload:
                _fail('sse_field')
            value = smoke_http._json_object('\n'.join(payload).encode('utf-8'))
            if value.get('type') != names[0]:
                _fail('sse_type')
            yield value, arrived
        pending = data[offset:]
    if pending:
        _fail('sse_incomplete')


def parse_responses_sse(parts, submitted):
    parts = _parts(parts, submitted)
    output, first, terminal, sequence = [], None, None, 0
    byte_count = 0
    auxiliary = {
        'response.created', 'response.in_progress', 'response.output_item.added',
        'response.content_part.added', 'response.output_text.done',
        'response.content_part.done', 'response.output_item.done',
    }
    for event, arrived in _events(parts):
        if terminal is not None:
            _fail('sse_after_terminal')
        number = event.get('sequence_number')
        if type(number) is not int or number != sequence:
            _fail('sse_sequence')
        sequence += 1
        kind = event['type']
        if kind == 'response.output_text.delta':
            text = _text(event.get('delta'))
            byte_count += len(text.encode('utf-8'))
            if byte_count > OUTPUT_LIMIT:
                _fail('output_limit')
            if text and first is None:
                first = (arrived - submitted) * 1000
                if not math.isfinite(first):
                    _fail('sse_timestamp')
            output.append(text)
        elif kind == 'response.completed':
            value = event.get('response')
            if type(value) is not dict:
                _fail('terminal')
            terminal = _responses(value)
        elif kind not in auxiliary:
            _fail('sse_event')
        if 'response' in event:
            value = event['response']
            if type(value) is not dict:
                _fail('terminal')
            if 'model' in value and value['model'] != smoke_http.MODEL:
                _fail('model')
    if terminal is None:
        _fail('sse_incomplete')
    if terminal['visible_answer'] != ''.join(output):
        _fail('sse_text_disagrees')
    terminal.update(first_visible_content_ms=first, first_useful_output_ms=first)
    return _validate_extracted(terminal)


def parse_positive_response(post, body, parts, submitted):
    """Decode only complete positive bodies. Caller owns HTTP status/type checks.

    This does not authorize requests or validate a PreparedPost's provenance;
    the fixed-workload controller must supply the ledger-bound post.
    """
    if type(post) is not PreparedPost or post.expected_status != 200:
        _fail('post')
    if type(body) is not bytes or len(body) > BODY_LIMIT:
        _fail('body_limit')
    request = smoke_http._json_object(post.body)
    streaming = request.get('stream', False)
    if type(streaming) is not bool:
        _fail('stream')
    if not streaming:
        return parse_buffered(body, post.route)
    parts = _parts(parts, submitted)
    if b''.join(part for part, _ in parts) != body:
        _fail('body_parts_disagree')
    if post.route == RESPONSES:
        return parse_responses_sse(parts, submitted)
    if post.route != CHAT:
        _fail('route')
    # Only this pinned fixture intentionally omits OpenAI stream usage.
    require_usage = post.request_id != 'tool_chat_2304'
    result = smoke_http.parse_sse_response(parts, submitted, require_usage=require_usage)
    if type(result.get('timings')) is not dict or not result['timings']:
        _fail('usage_timings')
    if post.request_id == 'tool_chat_2304':
        calls = result['tool_calls']
        if (result['finish_reason'] != 'tool_calls' or len(calls) != 1
                or calls[0].get('type') != 'function'
                or type(calls[0].get('id')) is not str or not calls[0]['id']):
            _fail('tool_call')
        function = calls[0].get('function')
        if (type(function) is not dict or type(function.get('name')) is not str
                or not function['name'] or type(function.get('arguments')) is not str
                or not function['arguments']):
            _fail('tool_call')
    return _validate_extracted(result)
