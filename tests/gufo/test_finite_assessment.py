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

    def test_present_redundant_rates_and_per_token_timings_must_agree(self):
        cases = [
            (1, 'timings', 'prompt_per_token_ms', 99.0),
            (1, 'timings', 'prompt_per_second', 99.0),
            (1, 'timings', 'predicted_per_token_ms', 99.0),
            (1, 'timings', 'predicted_per_second', 99.0),
            (1, 'usage', 'prompt_tokens_per_second', 99.0),
            (1, 'usage', 'completion_tokens_per_second', 99.0),
        ]
        for attempt, section, field, value in cases:
            parsed = parsed_for(attempt)
            parsed[section][field] = value
            with self.subTest(section=section, field=field):
                self.assertFalse(self.positive(attempt, parsed)['native_metrics_valid'])
        for section, field in (('prompt_per_token_ms', 'timings'),):
            parsed = parsed_for(1)
            parsed[field][section] = True
            self.assertFalse(self.positive(1, parsed)['native_metrics_valid'])
        parsed = parsed_for(3)
        parsed['timings']['prompt_per_second'] = float('inf')
        self.assertFalse(self.positive(3, parsed)['native_metrics_valid'])

    def test_redundant_rate_serialization_rounding_is_accepted(self):
        parsed = parsed_for(1)
        count = parsed['timings']['prompt_n']
        parsed['timings']['prompt_per_token_ms'] = 10.0 / count + 1e-12
        parsed['timings']['prompt_per_second'] = count * 1000.0 / 10.0 + 1e-8
        parsed['timings']['predicted_per_token_ms'] = 2.0
        parsed['timings']['predicted_per_second'] = 500.0 + 1e-8
        parsed['usage']['prompt_tokens_per_second'] = count * 100.0 + 1e-8
        parsed['usage']['completion_tokens_per_second'] = 500.0 + 1e-8
        self.assertTrue(self.positive(1, parsed)['native_metrics_valid'])

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
