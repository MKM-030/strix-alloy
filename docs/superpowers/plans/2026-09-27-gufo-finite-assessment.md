# Finite native counters and answer assessment implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate fixed native GUFO lifecycle answers and token counters before integrating transport or making performance claims.

**Architecture:** Add two pure modules: route-native metrics adapting the existing metric validator, and workload-bound answer/rejection assessment. Reuse immutable Workload and the completed response decoder. This is the next existing controller task, not a new backend design.

**Tech Stack:** Python 3.12 standard library, unittest, pinned GUFO e6feed7 response contracts.

## Global Constraints

- Preserve working native Strix Alloy, Halogen WSL2 and 27B installations; no dual boot.
- Preserve at least 49 GiB available Windows physical memory before launch, a 24 GiB available Windows physical-memory stop floor, and at least 12 GiB system commit headroom. This task creates no launch authority; the reviewed 68/4/20 GiB GPU/additional-host/shared envelope remains unchanged.
- No model, GPU, native fixture helper, metadata reader, collector, guardian, recovery, listener, real network socket, production attempt/latch, or installed acceptance invocation/change. CPU-only fixtures use memory and temporary test evidence only.
- No BIOS/carve/VGM/driver/services/security/pagefile changes, reboot, D: access, publication, unrelated process termination, dependency installation, SDK changes or broad engine rebuild.
- Work only in C:/Projects/strix-alloy-research/integration on codex/gufo-native-integration; preserve unrelated changes, frozen production engine e6feed7, staged runtime and failed recovery evidence.
- Do not modify config/gufo-service-lifecycle-workload.json: 132273 bytes, SHA256 30D633A46F3F16433557CFF41E7F01C3A28D75132B875BEE63B8E39A332ACC38.
- Do not change the fixed 66+6 POST sequence or request bodies. Missing counters remain unavailable, never zero; SSE events and text fragments are not token counters.
- This pure assessment is not transport/provenance validation, request admission, cancellation, overlap proof, lifetime enforcement, authentication, memory recovery, or installed qualification. A per-case fully_validated result does not grant launch or service acceptance.
- Keep raw route-native usage and timings unchanged. Validate all required counts and all present redundant count/timing fields. Label internal derivation; do not invent a wire usage object for tool_chat_2304.
- A pending manual prose review permits structural progression only. Final useful-answer qualification requires a passing review bound to exact extracted UTF-8 text, along with all lifecycle/recovery requirements.
- Only the three task source/test files named below may change; commit locally with one-command identity if necessary, no push. Code below is a starting implementation, not a mandate to retain a bug; fix concrete within-scope defects and explain deviations.

---

### Task 1: Implement native-counter and fixed-answer assessment

**Files:**
- Create scripts/gufo_control/finite_metrics.py.
- Create scripts/gufo_control/finite_assessment.py.
- Create tests/gufo/test_finite_assessment.py.
- Report C:/Projects/strix-alloy-research/reports/gufo-finite-assessment-implementation-20260927.md.

**Interfaces:**
- validate_metrics(route,usage,timings,*,expected_prompt,output_limit,allow_missing_usage=False)->dict with valid, metrics, errors and unavailable. Pure; no mutation of supplied route-native evidence.
- assess_positive(workload:Workload,index:int,attempt:int,parsed:dict,*,semantic_review=None,previous=None)->dict with case identity, structural_success, answer_status, fully_validated, exact answer hash, repeat fingerprint/result, native metrics and errors.
- assess_rejection(workload,index,attempt,status,content_type,body)->dict with exact status/error validation; never proves overlap or inference.
- The caller supplies authenticated complete protocol-decoder output plus HTTP status/content-type validation. It must persist/authenticate previous assessments and manual reviews before feeding them here. These helpers do not authorize new requests or trust arbitrary ledger history.

**Requirements and provenance:** Read C:/Projects/strix-alloy-research/reports/gufo-finite-response-contract-map-20260927.md, pinned workload answer_contract, finite_workload.py and relevant helpers in smoke_http.py/benchmark_http.py. Native prompt_n + cache_n must equal pinned helper framed_tokens, predicted_n must equal output usage and stay within the fixed request max. All core native counts must be strict nonnegative integers (not bool); require a positive output. Fixed AR/cold profile requires zero drafts/cache; optional lookup counters remain unavailable if absent, otherwise require a consistent zero pair. Missing/zero timings yield unavailable rates, invalid or contradictory timings fail validation. Never derive HTTP or common-window rates here.

Exact checks: whitespace-only trimming for 4 and fünf; parse Python add AST without executing; exactly one report_sum tool with strict duplicate-free integer sum=4. Same-ID repeats compare exact text bytes or canonical function/arguments excluding random call IDs; different IDs are not same-case references. Prose stays pending until an explicit reviewer/verdict/reason bound to its text SHA256 is supplied; never use sentence-count regex as semantic acceptance. Expected status/error alone must not certify queue overlap.

- [ ] **Step 1: Add the test file below and capture RED before production edits.**

```python
"""Offline synthetic assessment fixtures; rates here are not measurements."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from gufo_control import finite_assessment as assess, finite_metrics, finite_responses, smoke_http
from gufo_control.finite_workload import load_workload

WORKLOAD = load_workload()
PROSE = 'Automated tests detect bugs before release. They catch regressions and help maintain software.'


def parsed_for(attempt, text=None, index=1):
    post = WORKLOAD.post(index, attempt)
    row = next(r for r in WORKLOAD.document()['request_pool'] if r['id'] == post.request_id)
    count = row['native_preparation']['framed_tokens']
    check = json.loads(post.step_json)['check']
    if text is None:
        text = {'exact_arithmetic_4': '4', 'exact_german_fuenf': 'fünf',
                'python_add_ast': 'def add(a, b):\n    return a + b\n',
                'report_sum_integer_4': '',
                'english_two_sentence_semantic_review': PROSE}[check]
    timing = dict(prompt_n=count, cache_n=0, predicted_n=1,
                  draft_n=0, draft_n_accepted=0, prompt_ms=10.0, predicted_ms=2.0)
    if post.route == finite_responses.CHAT:
        usage = dict(prompt_tokens=count, completion_tokens=1, total_tokens=count+1,
                     prompt_tokens_details=dict(cached_tokens=0))
    elif post.route == finite_responses.RESPONSES:
        usage = dict(input_tokens=count, output_tokens=1, total_tokens=count+1,
                     input_tokens_details=dict(cached_tokens=0, cache_write_tokens=count))
    else:
        usage = dict(input_tokens=count, output_tokens=1,
                     cache_read_input_tokens=0, cache_creation_input_tokens=0)
    tools = []
    if check == 'report_sum_integer_4':
        usage = None
        tools = [dict(id='call-a', type='function',
                      function=dict(name='report_sum', arguments='{"sum":4}'))]
    return dict(visible_answer=text, reasoning_content='', tool_calls=tools,
                finish_reason='tool_calls' if tools else 'stop', usage=usage, timings=timing,
                observed_models=[smoke_http.MODEL])


def review_for(text, verdict='pass'):
    return dict(reviewer='offline-test-reviewer',
                response_sha256=sha256(text.encode('utf-8')).hexdigest().upper(),
                verdict=verdict, reason='Synthetic test of the review contract.')


class AssessmentTests(unittest.TestCase):
    def positive(self, attempt, parsed=None, **kwargs):
        return assess.assess_positive(WORKLOAD, 1, attempt,
            parsed if parsed is not None else parsed_for(attempt), **kwargs)

    def test_first_six_across_both_lifecycles(self):
        for index in (1, 2):
            for attempt in range(1, 7):
                with self.subTest(index=index, attempt=attempt):
                    result = assess.assess_positive(WORKLOAD, index, attempt,
                                                    parsed_for(attempt, index=index))
                    self.assertTrue(result['fully_validated'])
                    self.assertEqual(result['errors'], [])
                    self.assertIsNone(result['metrics']['http_pp_tokens_per_second'])
                    self.assertIsNone(result['metrics']['common_window_decode_tokens_per_second'])

    def test_tool_absent_usage_stays_absent_and_counters_are_labelled(self):
        parsed = parsed_for(12)
        original = deepcopy(parsed)
        result = self.positive(12, parsed)
        self.assertTrue(result['fully_validated'])
        self.assertEqual(parsed, original)
        self.assertIsNone(parsed['usage'])
        self.assertIn('usage', result['unavailable_metrics'])
        self.assertEqual(result['metrics']['logical_prompt_tokens'], 2304)
        self.assertEqual(result['metrics']['logical_prompt_tokens_source'],
                         'derived:timings.prompt_n+timings.cache_n')
        self.assertIsNone(result['metrics']['lookup_tokens'])
        self.assertIn('timings.lookup_n', result['unavailable_metrics'])

    def test_required_native_counters_reject_missing_bool_negative_and_mismatch(self):
        for key in ('prompt_n', 'cache_n', 'predicted_n', 'draft_n', 'draft_n_accepted'):
            for value in (None, True, -1, 0.5):
                parsed = parsed_for(1)
                if value is None:
                    del parsed['timings'][key]
                else:
                    parsed['timings'][key] = value
                with self.subTest(key=key, value=value):
                    result = self.positive(1, parsed)
                    self.assertFalse(result['fully_validated'])
                    self.assertFalse(result['native_metrics_valid'])
        for key, value in (('prompt_n', 25), ('cache_n', 1), ('predicted_n', 0),
                           ('predicted_n', 257), ('draft_n', 1), ('draft_n_accepted', 1)):
            parsed = parsed_for(1)
            parsed['timings'][key] = value
            self.assertFalse(self.positive(1, parsed)['native_metrics_valid'])

    def test_redundant_route_counters_and_cold_cache_must_agree(self):
        mutations = [
            (1, lambda p: p['usage'].update(prompt_tokens=25)),
            (1, lambda p: p['usage'].update(total_tokens=99)),
            (1, lambda p: p['usage'].update(completion_tokens=True)),
            (1, lambda p: p['usage'].update(draft_tokens=1)),
            (1, lambda p: p['usage'].update(gufo=dict(cache_hit=True))),
            (1, lambda p: p['usage'].update(gufo=dict(cache_disk_hit=0))),
            (1, lambda p: p['usage'].update(gufo=dict(prefill_tokens=1))),
            (3, lambda p: p['usage']['input_tokens_details'].update(cached_tokens=1)),
            (3, lambda p: p['usage']['input_tokens_details'].update(cache_write_tokens=1)),
            (5, lambda p: p['usage'].update(cache_read_input_tokens=1)),
            (5, lambda p: p['usage'].update(cache_creation_input_tokens=True)),
        ]
        for attempt, mutate in mutations:
            parsed = parsed_for(attempt)
            mutate(parsed)
            with self.subTest(attempt=attempt, parsed=parsed):
                self.assertFalse(self.positive(attempt, parsed)['native_metrics_valid'])

    def test_optional_timings_missing_or_zero_produce_no_rate(self):
        for value in (None, 0):
            parsed = parsed_for(1)
            for key in ('prompt_ms', 'predicted_ms'):
                if value is None:
                    del parsed['timings'][key]
                else:
                    parsed['timings'][key] = value
            result = self.positive(1, parsed)
            self.assertTrue(result['fully_validated'])
            self.assertIsNone(result['metrics']['engine_pp_tokens_per_second'])
            self.assertIsNone(result['metrics']['engine_tg_tokens_per_second'])
        for value in (True, -1, float('nan'), float('inf'), 10**1000):
            parsed = parsed_for(1)
            parsed['timings']['prompt_ms'] = value
            self.assertFalse(self.positive(1, parsed)['native_metrics_valid'])

    def test_lookup_fields_are_zero_or_absent_as_a_pair(self):
        for fields, expected in (({}, True), (dict(lookup_n=0, lookup_n_accepted=0), True),
                                 (dict(lookup_n=0), False),
                                 (dict(lookup_n=1, lookup_n_accepted=0), False),
                                 (dict(lookup_n=0, lookup_n_accepted=True), False)):
            parsed = parsed_for(1)
            parsed['timings'].update(fields)
            self.assertEqual(self.positive(1, parsed)['native_metrics_valid'], expected)

    def test_exact_answers_and_no_truncation_reasoning_or_wrong_model(self):
        for attempt, answers in ((1, ('4.', 'The answer is 4', '')),
                                 (2, ('funf', 'fuenf', 'fu\u0308nf', 'fünf.'))):
            for text in answers:
                self.assertFalse(self.positive(attempt, parsed_for(attempt, text))['fully_validated'])
        self.assertTrue(self.positive(1, parsed_for(1, '\u20034\n'))['fully_validated'])
        self.assertTrue(self.positive(2, parsed_for(2, '\tfünf\u2003'))['fully_validated'])
        for field, value in (('finish_reason', 'length'), ('reasoning_content', 'why'),
                              ('observed_models', ['different'])):
            parsed = parsed_for(1)
            parsed[field] = value
            self.assertFalse(self.positive(1, parsed)['fully_validated'])

    def test_python_ast_is_strict_and_never_executes(self):
        for text in ('def add(a,b): return a+b', 'def add(a, b):\n    return b + a\n'):
            self.assertTrue(self.positive(8, parsed_for(8, text))['fully_validated'])
        invalid = [
            'def add(a,b): return a-b', 'def add(a,b=1): return a+b',
            'def add(a:int,b): return a+b', 'def add(a,b)->int: return a+b',
            'def add(a,b,/): return a+b', 'def add(a,b,*args): return a+b',
            'async def add(a,b): return a+b', '@decorator\ndef add(a,b): return a+b',
            'import os\ndef add(a,b): return a+b', 'def add(a,b):\n    print(a)\n    return a+b',
            'def add(a,b): return __import__("os").system("unused")',
            chr(96)*3+'python\ndef add(a,b): return a+b\n'+chr(96)*3]
        for text in invalid:
            with self.subTest(text=text):
                self.assertFalse(self.positive(8, parsed_for(8, text))['fully_validated'])

    def test_tool_requires_one_exact_integer_call_and_repeats_ignore_random_id(self):
        first = self.positive(12)
        parsed = parsed_for(12)
        parsed['tool_calls'][0]['id'] = 'different-random-id'
        self.assertEqual(self.positive(12, parsed, previous=first)['repeat'], 'match')
        for arguments in ('{"sum":true}', '{"sum":4.0}', '{"sum":4,"sum":4}',
                          '{"sum":4,"other":1}', '{"sum":NaN}', '{"sum":5}'):
            parsed = parsed_for(12)
            parsed['tool_calls'][0]['function']['arguments'] = arguments
            self.assertFalse(self.positive(12, parsed)['fully_validated'])
        for field, value in (('id', ''), ('type', 'other')):
            parsed = parsed_for(12)
            parsed['tool_calls'][0][field] = value
            self.assertFalse(self.positive(12, parsed)['fully_validated'])

    def test_prose_needs_hash_bound_review_not_sentence_regex(self):
        parsed = parsed_for(9)
        result = self.positive(9, parsed)
        self.assertTrue(result['structural_success'])
        self.assertFalse(result['fully_validated'])
        self.assertEqual(result['answer_status'], 'pending_semantic_review')
        reviewed = self.positive(9, parsed, semantic_review=review_for(PROSE))
        self.assertTrue(reviewed['fully_validated'])
        for key, value in (('response_sha256', '0'*64), ('reviewer', ''), ('reviewer', '\ud800'),
                           ('reviewer', 'x'*97), ('verdict', 'unknown'), ('reason', '')):
            review = review_for(PROSE)
            review[key] = value
            self.assertFalse(self.positive(9, parsed, semantic_review=review)['fully_validated'])
        failed = self.positive(9, parsed, semantic_review=review_for(PROSE, 'fail'))
        self.assertIn('semantic_review_failed', failed['errors'])
        self.assertFalse(self.positive(1, semantic_review=review_for('4'))['fully_validated'])

    def test_repeats_use_exact_same_id_text_and_reject_invalid_reference(self):
        first = self.positive(7)
        self.assertEqual(self.positive(16, previous=first)['repeat'], 'match')
        changed = self.positive(16, parsed_for(16, ' fünf'), previous=first)
        self.assertEqual(changed['repeat'], 'mismatch')
        self.assertFalse(changed['fully_validated'])
        self.assertEqual(self.positive(10, previous=first)['repeat'], 'invalid_reference')

    def test_all_rejection_steps_check_code_but_do_not_prove_overlap(self):
        count = 0
        for attempt in range(1, 67):
            post = WORKLOAD.post(1, attempt)
            if post.expected_status == 200:
                continue
            body = json.dumps(dict(error=dict(code=post.expected_error))).encode()
            result = assess.assess_rejection(WORKLOAD, 1, attempt, post.expected_status,
                                            'application/json; charset=utf-8', body)
            self.assertTrue(result['request_contract_pass'])
            self.assertFalse(result['overlap_verified'])
            self.assertFalse(result['inference_verified'])
            count += 1
        self.assertEqual(count, 20)

    def test_rejections_fail_wrong_status_type_code_or_encoding(self):
        good = b'{"error":{"code":"queue_full"}}'
        cases = [(200, 'application/json', good),
                 (True, 'application/json', good),
                 (429, 'text/event-stream', good),
                 (429, 'application/json', b'{"error":{"code":"other"}}'),
                 (429, 'application/json', b'{"error":{"code":"queue_full","code":"queue_full"}}'),
                 (429, 'application/json', b'\xff'),
                 (429, 'application/json', b'{"error":{"code":"\\ud800"}}')]
        for status, content_type, body in cases:
            self.assertFalse(assess.assess_rejection(WORKLOAD, 1, 45, status,
                             content_type, body)['request_contract_pass'])
        with patch.object(finite_responses, 'BODY_LIMIT', len(good)-1):
            self.assertFalse(assess.assess_rejection(WORKLOAD, 1, 45, 429,
                             'application/json', good)['request_contract_pass'])

    def test_contracts_refuse_cancel_as_complete_and_unpinned_inputs(self):
        with self.assertRaises(ValueError):
            self.positive(31, parsed_for(1))
        with self.assertRaises(ValueError):
            assess.assess_rejection(WORKLOAD, 1, 1, 400, 'application/json', b'{}')
        with self.assertRaises(ValueError):
            assess.assess_positive(object(), 1, 1, parsed_for(1))
        for prompt, limit in ((True, 64), (26, True), (2305, 64), (26, 257)):
            with self.assertRaises(ValueError):
                finite_metrics.validate_metrics(finite_responses.CHAT, {}, {},
                    expected_prompt=prompt, output_limit=limit)

if __name__ == '__main__':
    unittest.main()

```

Run from integration (PowerShell):
```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest test_finite_assessment -v
```
Expected initial RED: missing finite_assessment module; retain actual command/output/exit code. Add focused behavioral regressions for concrete defects, preserving their actual RED output. Do not change valid tests merely to fit a flawed implementation.

- [ ] **Step 2: Implement the two modules.**

scripts/gufo_control/finite_metrics.py:
```python
"""Native-counter validation for the fixed AR/cold lifecycle, not launch authority."""
from . import benchmark_http, smoke_http
from .finite_responses import CHAT, RESPONSES, MESSAGES


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
    if out == 0:
        errors.append('empty_generation')
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
    metrics.update(logical_prompt_tokens_source=source, lookup_tokens=lookup['lookup_n'],
                   lookup_tokens_accepted=lookup['lookup_n_accepted'])
    errors = list(dict.fromkeys(errors))
    benchmark_http._rates(metrics, errors, pp1=False)
    for key, value in metrics.items():
        if value is None:
            unavailable.append(key)
    return dict(valid=not errors, metrics=metrics, errors=errors,
                unavailable=list(dict.fromkeys(unavailable)))

```

scripts/gufo_control/finite_assessment.py:
```python
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

```

- [ ] **Step 3: Run GREEN and direct parser regressions once.**

```powershell
$env:PYTHONPATH='C:\Projects\strix-alloy-research\integration\scripts;C:\Projects\strix-alloy-research\integration\tests\gufo'
& 'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe' -m unittest test_finite_assessment test_finite_responses test_smoke_http.ReusableHelpersTests -v
```
All selected tests must pass, zero skips/errors/failures. These are CPU-only; do not run network/listener/model suites. Synthetic counts/timings are protocol fixtures, not benchmark evidence. Capture exact output outside checkout in the named report.

- [ ] **Step 4: Self-review and commit only the three code/test paths.**

```powershell
git diff --check
git add -- scripts/gufo_control/finite_metrics.py scripts/gufo_control/finite_assessment.py tests/gufo/test_finite_assessment.py
git diff --cached --check
git -c user.name=Codex -c user.email=codex@openai.com commit -m 'feat(gufo): validate finite native counters and answers'
```
Report scope, exact test commands/results, RED/GREEN evidence, deviations and limitations. Independent task review is required before controller integration. Remaining full-spec work includes bounded transport/evidence/phase runner, pinned finite store and guardian/IPC integration, actual two-lifecycle evidence and recovery, manual semantic reviews, broader optimization and comparison work; this task does not redefine goal completion.

