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
    def test_chat_usage_option_requires_bool(self):
        for value in (0, 1, None, 'false'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                smoke_http.parse_sse_response([], 1.0, require_usage=value)

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

    def test_buffered_positive_validates_receive_metadata(self):
        workload = load_workload()
        post = next(workload.post(1, attempt) for attempt in range(1, 67)
                    if workload.post(1, attempt).request_id == 'responses_arithmetic')
        body = encoded(response())
        cases = [([], 1.0), ([(b'x', 1.0)], float('nan')),
                 ([(b'x', float('nan'))], 0.0)]
        for parts, submitted in cases:
            with self.subTest(parts=parts, submitted=submitted), self.assertRaises(smoke_http.SmokeError):
                client.parse_positive_response(post, body, parts, submitted)

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
        for timestamp in (True, float('nan'), 0.0, 10**1000):
            with self.subTest(timestamp=timestamp), self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, timestamp)], 1.0)

    def test_response_sse_rejects_elapsed_overflow(self):
        wire = semantic_wire(semantic_events())
        for label, arrived in (('large_int', 10**308), ('large_float', 1e308),
                               ('beyond_float', 10**1000)):
            with self.subTest(timestamp=label), self.assertRaises(smoke_http.SmokeError):
                client.parse_responses_sse([(wire, arrived)], 0)

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
        for label, arrived in (('large_int', 10**308), ('large_float', 1e308),
                               ('beyond_float', 10**1000)):
            with self.subTest(timestamp=label), self.assertRaises(smoke_http.SmokeError):
                client.parse_positive_response(post, wire, [(wire, arrived)], 0)
        incomplete_wire = b''.join(
            b'data: '+encoded(dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')],
                                   timings=dict(prompt_n=2304, predicted_n=10, cache_n=0)))+b'\n\n'
            for _ in range(1)
        ) + b'data: [DONE]\n\n'
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_positive_response(post, incomplete_wire, [(incomplete_wire, 2.0)], 1.0)
        readiness = load_workload().post(1, 1)
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_positive_response(readiness, wire, parts, 1.0)
        with self.assertRaises(smoke_http.SmokeError):
            client.parse_positive_response(post, wire+b' ', parts, 1.0)


if __name__ == '__main__':
    unittest.main()
