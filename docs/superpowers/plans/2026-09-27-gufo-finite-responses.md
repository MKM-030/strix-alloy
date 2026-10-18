# Finite response decoding implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode complete GUFO chat, Responses and Messages evidence without confusing route formats or inventing missing usage.

**Architecture:** Reuse existing chat JSON/SSE parsers with an explicit backward-compatible usage switch. Add a pure finite response adapter for the Responses semantic stream and text-only buffered routes. This is one independently testable parser task in the existing controller plan, not a new backend architecture.

**Tech Stack:** Python 3.12 standard library, unittest, pinned GUFO e6feed7 wire contracts.

## Global Constraints

- Preserve working native Strix Alloy, Halogen WSL2 and 27B installations; no dual boot.
- Preserve at least 49 GiB available Windows physical memory before launch, a 24 GiB available Windows physical-memory stop floor, and at least 12 GiB system commit headroom. This task creates no launch authority; the reviewed 68/4/20 GiB GPU/additional-host/shared envelope remains unchanged.
- No model, GPU, native fixture helper, metadata reader, collector, guardian, recovery, listener, real network socket, production attempt/latch, or installed acceptance invocation/change. CPU-only parser fixtures use memory and temporary test evidence only.
- No BIOS/carve/VGM/driver/services/security/pagefile changes, reboot, D: access, publication, unrelated process termination, dependency installation, SDK changes or broad engine rebuild.
- Work only in C:/Projects/strix-alloy-research/integration on codex/gufo-native-integration; preserve unrelated changes, frozen production engine e6feed7, staged runtime and failed recovery evidence.
- Do not modify config/gufo-service-lifecycle-workload.json: 132273 bytes, SHA256 30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38.
- Do not change the fixed 66+6 POST sequence or request bodies. Missing counters remain unavailable, never zero; SSE events and text fragments are not token counters.
- Positive response decoding is not semantic answer acceptance, token-counter validation, request admission, status/content-type validation, cancellation, transport, lifetime enforcement, authentication, memory recovery, or qualification. Those remain separate controller work.
- Preserve existing smoke/benchmark parser behavior by default. The only opt-out is an explicit require_usage=False parser argument, used by the finite adapter for the pinned tool_chat_2304 fixture. No fabricated usage object.
- Complete response body cap 7340032 bytes, combined extracted text/reasoning/tool names/arguments cap 1048576 UTF-8 bytes. At most 65536 nonempty receive parts are retained by this decoder, each with finite monotonic timestamp >= submission and prior arrival. The future transport must enforce these before retaining input, plus wire/evidence/socket/deadline caps; this decoder alone is not an RSS bound.
- Only the three task source/test files named below may change; commit locally with one-command identity if necessary, no push. Code below is a starting implementation, not a mandate to retain a bug; fix concrete within-scope defects and explain deviations.

---

### Task 1: Implement finite route response decoding

**Files:**
- Modify scripts/gufo_control/smoke_http.py: parse_sse_response signature, explicit option validation and final usage condition only.
- Create scripts/gufo_control/finite_responses.py.
- Create tests/gufo/test_finite_responses.py.
- Report C:/Projects/strix-alloy-research/reports/gufo-finite-responses-implementation-20260927.md.

**Interfaces:** parse_buffered(body:bytes,path:str)->dict; parse_responses_sse(parts:list[tuple[bytes,float]],submitted:float)->dict; parse_positive_response(post:PreparedPost,body:bytes,parts:list[tuple[bytes,float]],submitted:float)->dict. Result uses existing visible_answer, reasoning_content, tool_calls, finish_reason, raw usage/timings, observed_models and first-output timing fields. Positive only: caller still checks HTTP status/content type and exact ledger-bound provenance. Rejected/cancelled requests are not passed as complete positives. Responses timestamps measure arrival of complete content events, not GPU token times.

**Source evidence:** Read C:/Projects/strix-alloy-research/reports/gufo-finite-response-contract-map-20260927.md and the answer_contract at the end of the pinned workload. The source map is complete; no need to repeat repository research/native helper execution. Inspect existing smoke_http.parse_sse_response, benchmark_http._parse_json_response and their direct parser tests. Production Responses uses event names matching JSON type, contiguous sequence_number from zero, semantic completion with response.usage/timings, no [DONE]. Native Messages cache_creation_input_tokens=0 is a compatibility field, not no-snapshot proof. Preserve native usage shapes. This task does not calculate rates or pass semantic prose/code/tool checks.

- [ ] **Step 1: Add the focused test file, run RED before production edits.**

```python
"""CPU-only protocol fixtures; no HTTP, GPU, sockets, or model execution."""
import json
import unittest
from unittest.mock import patch

from gufo_control import finite_responses as client, smoke_http
from gufo_control.finite_workload import load_workload


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def response(text='fünf'):
    return dict(object='response', status='completed', error=None,
        incomplete_details=None, model=smoke_http.MODEL,
        output=[dict(type='message', status='completed', role='assistant',
                     content=[dict(type='output_text', text=text)])],
        usage=dict(input_tokens=25, output_tokens=2, total_tokens=27,
                   input_tokens_details=dict(cached_tokens=0)),
        timings=dict(prompt_n=25, predicted_n=2, cache_n=0))


def semantic_events(text='fünf'):
    value = response(text)
    return [
        dict(type='response.created', sequence_number=0,
             response=dict(model=smoke_http.MODEL, status='in_progress')),
        dict(type='response.output_text.delta', sequence_number=1, delta=text),
        dict(type='response.completed', sequence_number=2, response=value),
    ]


def semantic_wire(events):
    return b''.join(b'event: ' + e['type'].encode() + b'\r\ndata: ' + encoded(e)
                    + b'\r\n\r\n' for e in events)


class ResponseTests(unittest.TestCase):
    def test_buffered_routes_preserve_native_usage(self):
        value = response()
        result = client.parse_buffered(encoded(value), client.RESPONSES)
        self.assertEqual(result['visible_answer'], 'fünf')
        self.assertEqual(result['usage'], value['usage'])
        self.assertNotIn('prompt_tokens', result['usage'])
        msg = dict(type='message', role='assistant', model=smoke_http.MODEL,
                   stop_reason='end_turn', content=[dict(type='text', text='4')],
                   usage=dict(input_tokens=26, output_tokens=1), timings=value['timings'])
        self.assertEqual(client.parse_buffered(encoded(msg), client.MESSAGES)['visible_answer'], '4')
        msg['content'][0]['type'] = 'thinking'
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_buffered(encoded(msg), client.MESSAGES)

    def test_chat_buffered_reuse(self):
        value = dict(model=smoke_http.MODEL, choices=[dict(index=0,
            message=dict(role='assistant', content='4'), finish_reason='stop')],
            usage=dict(prompt_tokens=26, completion_tokens=1), timings=dict(prompt_n=26))
        self.assertEqual(client.parse_buffered(encoded(value), client.CHAT)['visible_answer'], '4')
        value['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_buffered(encoded(value), client.CHAT)

    def test_response_sse_split_utf8_crlf_and_terminal(self):
        wire = semantic_wire(semantic_events())
        split = wire.index('ü'.encode()) + 1
        parts = [(wire[:split], 2.0), (wire[split:split+1], 2.1), (wire[split+1:], 2.2)]
        result = client.parse_responses_sse(parts, 1.0)
        self.assertEqual(result['visible_answer'], 'fünf')
        self.assertAlmostEqual(result['first_visible_content_ms'], 1200)
        self.assertEqual(result['timings']['predicted_n'], 2)

    def test_response_sse_rejects_conflicts(self):
        cases = []
        events = semantic_events(); events[1]['sequence_number'] = True; cases.append(events)
        events = semantic_events(); events[1]['sequence_number'] = 4; cases.append(events)
        events = semantic_events(); events[-1]['response']['output'][0]['content'][0]['text'] = 'other'; cases.append(events)
        events = semantic_events(); events[-1]['response']['status'] = 'incomplete'; cases.append(events)
        events = semantic_events(); events[0]['response']['model'] = 'other'; cases.append(events)
        cases.extend([semantic_events()[:-1], semantic_events() + [semantic_events()[1]]])
        for events in cases:
            with self.subTest(events=events), self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(semantic_wire(events), 2.0)], 1.0)

    def test_strict_json_utf8_sse_fields(self):
        wires = [
            b'event: response.completed\ndata: {"type":"other"}\n\n',
            b'event: x\ndata: {"type":"x","type":"x"}\n\n',
            b'event: x\ndata: {"type":"x","value":1e400}\n\n',
            b'event: x\ndata: \xc0\n\n',
            b'event: x\ndata: {"type":"x"}',
        ]
        for wire in wires:
            with self.subTest(wire=wire), self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, 2.0)], 1.0)
        value = response('\ud800')
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_buffered(json.dumps(value).encode(), client.RESPONSES)

    def test_limits_and_bad_timestamps(self):
        wire = semantic_wire(semantic_events())
        with patch.object(client, 'BODY_LIMIT', len(wire)-1):
            with self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, 2.0)], 1.0)
        with patch.object(client, 'OUTPUT_LIMIT', 4):
            with self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, 2.0)], 1.0)
        for timestamp in (True, float('nan'), 0.0):
            with self.subTest(timestamp=timestamp), self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, timestamp)], 1.0)

    def test_tool_without_usage_only_opt_in_and_native_timings(self):
        workload = load_workload()
        post = next(post for post in (workload.post(1, n) for n in range(1, 67))
                    if post.request_id == 'tool_chat_2304')
        call = dict(index=0, id='call-1', type='function',
                    function=dict(name='report_sum', arguments='{"sum":4}'))
        chunks = [
            dict(model=smoke_http.MODEL, choices=[dict(index=0, delta=dict(tool_calls=[call]), finish_reason=None)]),
            dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')],
                 timings=dict(prompt_n=2304, predicted_n=10, cache_n=0)),
        ]
        wire = b''.join(b'data: '+encoded(c)+b'\n\n' for c in chunks)+b'data: [DONE]\n\n'
        parts = [(wire, 2.0)]
        with self.assertRaises(smoke_http.SmokeError):
            smoke_http.parse_sse_response(parts, 1.0)
        result = client.parse_positive_response(post, wire, parts, 1.0)
        self.assertIsNone(result['usage'])
        self.assertEqual(result['tool_calls'][0]['function']['name'], 'report_sum')
        self.assertEqual(result['timings']['prompt_n'], 2304)
        readiness = load_workload().post(1, 1)
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_positive_response(readiness, wire, parts, 1.0)
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_positive_response(post, wire+b' ', parts, 1.0)


if __name__ == '__main__':
    unittest.main()

```

Run from integration (PowerShell):
```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest test_finite_responses -v
```
Expected RED: import error because finite_responses does not exist. Record actual command/output/exit code. Strengthen focused tests for concrete defects found during implementation; do not change tests merely to match incorrect code.

- [ ] **Step 2: Add the adapter below and the narrowly scoped existing parser change.**

Replace the existing signature with:
```python
def parse_sse_response(parts, submitted, *, path="/v1/chat/completions", require_usage=True):
    if type(require_usage) is not bool:
        raise ValueError("invalid_require_usage")
```
Keep the existing body following the added validation. Replace only its final completeness condition with:
```python
    if bytes(pending).strip() or not done or terminal is None or (require_usage and usage is None):
        raise SmokeError("incomplete_sse")
```
All other old defaults and functions remain unchanged. New finite_responses.py:
```python
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


def _parts(parts, submitted):
    if (type(submitted) not in (int, float) or not math.isfinite(submitted)
            or submitted < 0 or type(parts) not in (list, tuple)
            or len(parts) > PART_LIMIT):
        _fail('parts')
    size, previous = 0, submitted
    for pair in parts:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            _fail('parts')
        part, arrived = pair
        if (type(part) is not bytes or not part
                or type(arrived) not in (int, float) or not math.isfinite(arrived)
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
    return _validate_extracted(result)

```

- [ ] **Step 3: Run GREEN and the focused existing parser class once.**

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest test_finite_responses test_smoke_http.ReusableHelpersTests -v
```
Expected all selected methods pass, zero skips/failures/errors. ReusableHelpersTests is CPU-only; do not select the live-loopback SmokeHttpTests or BenchmarkTests classes. Verify no listener/model/network action. Preserve raw RED/GREEN log evidence outside checkout. Exact counts and timings from output, not predeclared success.

- [ ] **Step 4: Self-review, report and locally commit scoped changes.**

Check new code against source mapping and all constraints, including UTF-8 split/CRLF semantics, expected-model identity, terminal errors, no missing usage substitution, unchanged default chat requirement and bounded outputs. Use apply_patch for edits. Verify staged paths and git diff --check, then commit only these three files:
```powershell
git diff --check
git add -- scripts/gufo_control/smoke_http.py scripts/gufo_control/finite_responses.py tests/gufo/test_finite_responses.py
git diff --cached --check
git -c user.name=Codex -c user.email=codex@openai.com commit -m 'feat(gufo): decode finite multi-route response evidence'
```
Report code changes, scope deviations, exact RED/GREEN commands/output, self-review and limits. No response decoder success grants launch or service acceptance; controller transport/store/guardian integration and live correctness remain necessary. Parent independently reviews before dependent task execution.
