import asyncio
import contextlib
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway, load_config

KEY = 'console-fixture-public-secret-32-characters'
BACKEND_KEY = 'console-fixture-backend-secret-32-characters'
HEADERS = {'Authorization': 'Bearer ' + KEY, 'x-api-key': KEY}


def records(output):
    return [json.loads(line[6:]) for line in output.getvalue().splitlines()
            if line.startswith('[api] ')]


class ConsoleGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stdout.__enter__()
        self.release = asyncio.Event()
        self.seen = []
        self.wire = (
            'data: {"choices":[{"index":0,"delta":{"content":"Grüße 😀"}}]}\r\n\r\n'
            'data: {"choices":[{"index":0,"delta":{"reasoning_content":"explicit thought"}}]}\n\n'
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call1",'
            '"type":"function","function":{"name":"lookup","arguments":"{}"}}]},'
            '"finish_reason":"tool_calls"}],"usage":{"completion_tokens":8}}\n\n'
            'data: [DONE]\n\n'
        ).encode('utf-8')

        async def health(request):
            return web.json_response({'status': 'ok'})

        async def chat(request):
            body = await request.json()
            self.seen.append((body, dict(request.headers)))
            if body.get('redirect'):
                raise web.HTTPFound('https://example.invalid/never')
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            boundary = self.wire.index(b'\r\n\r\n') + 4
            await response.write(self.wire[:boundary])
            await self.release.wait()
            try:
                for offset in range(boundary, len(self.wire), 7):
                    await response.write(self.wire[offset:offset + 7])
            except ConnectionResetError:
                pass  # Test peer intentionally disconnects in cancellation coverage.
            return response

        upstream = web.Application()
        upstream.router.add_get('/health', health)
        upstream.router.add_post('/v1/chat/completions', chat)
        self.upstream = TestServer(upstream, handler_cancellation=True)
        await self.upstream.start_server()
        self.backend = Backend('fixture', str(self.upstream.make_url('')).rstrip('/'),
                               'real-model', routes=('/v1/chat/completions',))
        self.clients = []

    async def asyncTearDown(self):
        self.release.set()
        for client in self.clients:
            await client.close()
        await self.upstream.close()
        self.stdout.__exit__(None, None, None)

    async def client(self, **kwargs):
        gateway = Gateway(self.backend, KEY, BACKEND_KEY, **kwargs)
        client = TestClient(TestServer(gateway.app, handler_cancellation=True))
        self.clients.append(client)
        await client.start_server()
        return gateway, client

    async def test_default_does_not_emit_or_construct_trace(self):
        with patch('gateway.ConsoleTrace', side_effect=AssertionError('default must be cheap')):
            gateway, client = await self.client()
            response = await client.post('/v1/chat/completions', headers=HEADERS,
                                         json={'model': 'fixture', 'stream': True})
            self.release.set()
            self.assertEqual(await response.read(), self.wire)
            self.assertEqual(gateway.completed, 1)
        self.assertEqual(self.output.getvalue(), '')

    async def test_trace_is_live_preserves_wire_and_excludes_credentials(self):
        gateway, client = await self.client(console_trace=True)
        prompt = 'visible prompt\x1b[2J\u009b31m ' + KEY
        response = await client.post('/v1/chat/completions', headers=HEADERS,
            json={'model': 'fixture', 'stream': True,
                  'messages': [{'role': 'user', 'content': prompt}], 'api_key': KEY})
        first = await asyncio.wait_for(response.content.readuntil(b'\r\n\r\n'), 2)
        before_end = records(self.output)
        self.assertTrue(any(row['event'] == 'request' for row in before_end))
        self.assertTrue(any(row.get('text') == 'Grüße 😀' for row in before_end))
        self.assertFalse(self.release.is_set())
        self.release.set()
        self.assertEqual(first + await response.read(), self.wire)
        rows = records(self.output)
        self.assertTrue(any(row['event'] == 'reasoning' and row['text'] == 'explicit thought'
                            for row in rows))
        self.assertTrue(any(row['event'] == 'tool_call' for row in rows))
        self.assertTrue(any(row['event'] == 'usage' and row['usage']['completion_tokens'] == 8
                            for row in rows))
        self.assertEqual(rows[-1]['event'], 'end')
        self.assertEqual(rows[-1]['status'], 200)
        self.assertEqual(rows[-1]['outcome'], 'complete')
        self.assertEqual({row['request_id'] for row in rows}, {rows[0]['request_id']})
        self.assertTrue(all(row['timestamp'].endswith('Z') and row['session'] for row in rows))
        text = self.output.getvalue()
        for forbidden in (KEY, BACKEND_KEY, 'Authorization', '\x1b', '\u009b'):
            self.assertNotIn(forbidden, text)
        self.assertIn('[REDACTED]', text)
        self.assertEqual(self.seen[0][0]['model'], 'real-model')
        self.assertEqual(self.seen[0][0]['messages'][0]['content'], prompt)
        self.assertEqual(self.seen[0][1]['Authorization'], 'Bearer ' + BACKEND_KEY)
        self.assertEqual(gateway.completed, 1)

    async def test_rejections_have_unique_request_ids_and_actual_status(self):
        _, client = await self.client(console_trace=True)
        unauthorized = await client.post('/v1/chat/completions', json={'model': 'fixture'})
        self.assertEqual(unauthorized.status, 401)
        invalid = await client.post('/v1/chat/completions', headers=HEADERS, data='{')
        self.assertEqual(invalid.status, 400)
        unsupported = await client.post('/v1/embeddings', headers=HEADERS,
                                        json={'model': 'fixture'})
        self.assertEqual(unsupported.status, 501)
        ends = [row for row in records(self.output) if row['event'] == 'end']
        self.assertEqual([row['status'] for row in ends], [401, 400, 501])
        self.assertEqual(len({row['request_id'] for row in ends}), 3)
        self.assertEqual(self.seen, [])

    async def test_trace_keeps_cancelled_stream_slot_and_end_outcome_correct(self):
        gateway, client = await self.client(console_trace=True)
        response = await client.post('/v1/chat/completions', headers=HEADERS,
                                     json={'model': 'fixture', 'stream': True})
        await asyncio.wait_for(response.content.readuntil(b'\r\n\r\n'), 2)
        response.close()
        for _ in range(100):
            if gateway.active == 0:
                break
            await asyncio.sleep(.01)
        self.assertEqual(gateway.active, 0)
        self.assertEqual(gateway.cancelled, 1)
        ends = [row for row in records(self.output) if row['event'] == 'end']
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]['outcome'], 'cancelled')

    async def test_upstream_failure_end_status_and_busy_rejection_are_reported(self):
        gateway, client = await self.client(console_trace=True)
        failed = await client.post('/v1/chat/completions', headers=HEADERS,
                                   json={'model': 'fixture', 'redirect': True})
        self.assertEqual(failed.status, 503)
        await failed.read()
        gateway.draining = True
        busy = await client.post('/v1/chat/completions', headers=HEADERS,
                                 json={'model': 'fixture'})
        self.assertEqual(busy.status, 429)
        ends = [row for row in records(self.output) if row['event'] == 'end']
        self.assertEqual([(row['status'], row['outcome']) for row in ends],
                         [(503, 'upstream_error'), (429, 'complete')])


class ConsoleDecoderTests(unittest.TestCase):
    def setUp(self):
        from console_trace import ConsoleTrace
        self.output = io.StringIO()
        self.console = ConsoleTrace(secrets=(KEY, BACKEND_KEY), stream=self.output)
        self.trace = self.console.start('POST', '/v1/chat/completions', 'fixture')

    def stream(self, wire, content_type='text/event-stream'):
        self.trace.response(200, content_type)
        # Every byte boundary includes fragmented UTF-8, CRLF, SSE fields, and JSON.
        for byte in wire:
            self.trace.feed(bytes((byte,)))
        self.trace.finish(200)
        return records(self.output)

    def test_one_byte_chunks_multiline_sse_and_cr_boundaries(self):
        wire = ('\ufeff: comment\r\nevent: message\r\ndata: {"choices": [\r\n'
                'data: {"delta":{"content":"café 😀"}}]}\r\n\r\n'
                'data: {"choices":[{"delta":{"content":"after CR"}}]}\r\r'
                'data: [DONE]\n\n').encode('utf-8')
        rows = self.stream(wire)
        self.assertEqual([row['text'] for row in rows if row['event'] == 'answer'],
                         ['café 😀', 'after CR'])
        self.assertFalse(any(row['event'] == 'reasoning' for row in rows))
        self.assertTrue(any(row.get('reason') == 'done' for row in rows))

    def test_oversized_and_invalid_sse_events_recover_at_next_event(self):
        from console_trace import MAX_EVENT_BYTES
        wire = (b'data: {\n\n' + b'data: ' + b'x' * (MAX_EVENT_BYTES + 100) + b'\n\n'
                + b'data: {"choices":[{"delta":{"content":"recovered"}}]}\n\n')
        self.trace.response(200, 'text/event-stream')
        for offset in range(0, len(wire), 1021):
            self.trace.feed(wire[offset:offset + 1021])
        self.trace.finish(200)
        rows = records(self.output)
        self.assertEqual([row['reason'] for row in rows if row['event'] == 'trace_skipped'],
                         ['invalid_sse_json', 'sse_event_limit'])
        self.assertEqual([row['text'] for row in rows if row['event'] == 'answer'], ['recovered'])
        self.assertLess(len(self.output.getvalue()), 4096)

    def test_json_limit_and_incomplete_sse_do_not_emit_partial_answer(self):
        from console_trace import MAX_JSON_BYTES
        self.trace.response(200, 'application/json')
        self.trace.feed(b'{"choices":' + b' ' * MAX_JSON_BYTES)
        self.trace.finish(200)
        self.assertTrue(any(row.get('reason') == 'json_limit' for row in records(self.output)))
        self.assertLess(len(self.output.getvalue()), 4096)
        trace = self.console.start('POST', '/v1/chat/completions', 'fixture')
        trace.response(200, 'text/event-stream')
        trace.feed(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')
        trace.finish(200)
        rows = records(self.output)
        self.assertTrue(any(row.get('reason') == 'incomplete_sse_event' for row in rows))
        self.assertFalse(any(row['event'] == 'answer' for row in rows))

    def test_nonstream_json_exposes_answer_reasoning_tools_and_usage(self):
        wire = json.dumps({'choices': [{'message': {'content': 'Grüße 😀',
                           'reasoning_content': 'returned reasoning',
                           'tool_calls': [{'id': 'call-json', 'function': {'name': 'lookup',
                                          'arguments': '{}'}}]}, 'finish_reason': 'stop'}],
                           'usage': {'total_tokens': 9}}, ensure_ascii=False).encode('utf-8')
        rows = self.stream(wire, 'application/json; charset=utf-8')
        self.assertEqual([row['text'] for row in rows if row['event'] == 'answer'], ['Grüße 😀'])
        self.assertEqual([row['text'] for row in rows if row['event'] == 'reasoning'],
                         ['returned reasoning'])
        self.assertTrue(any(row['event'] == 'tool_call' for row in rows))
        self.assertTrue(any(row.get('usage') == {'total_tokens': 9} for row in rows))

    def test_content_encoding_is_not_decoded_or_changed_and_terminals_are_safe(self):
        self.trace.payload({'Authorization': 'arbitrary credential', 'x-api-key': 'other secret',
                            'nested': {'content': 'visible\u202e\x1b\u009b\x07😀'}})
        self.trace.response(200, 'application/json', 'gzip')
        self.trace.feed(b'not decoded gzip bytes')
        self.trace.finish(200)
        rows = records(self.output)
        self.assertTrue(any(row.get('reason') == 'encoded_response' for row in rows))
        text = self.output.getvalue()
        for forbidden in ('arbitrary credential', 'other secret', '\u202e', '\x1b', '\u009b', '\x07'):
            self.assertNotIn(forbidden, text)
        self.assertTrue(any('visible' in str(row) for row in rows))

    def test_large_request_display_is_bounded_without_mutating_payload(self):
        payload = {'model': 'fixture', 'messages': [{'role': 'user', 'content': 'x' * 300000}]}
        self.trace.payload(payload)
        rows = records(self.output)
        self.assertEqual(len(payload['messages'][0]['content']), 300000)
        self.assertLess(len(self.output.getvalue()), 68000)
        self.assertIn('[TRUNCATED]', str(rows[-1]['payload']))

    def test_responses_and_anthropic_events_display_only_supplied_fields(self):
        events = [
            {'type': 'response.output_text.delta', 'delta': 'answer'},
            {'type': 'response.reasoning_summary_text.delta', 'delta': 'returned summary'},
            {'type': 'response.function_call_arguments.delta', 'delta': '{"q":'},
            {'type': 'response.output_item.added', 'item': {'type': 'function_call',
                 'name': 'lookup', 'call_id': 'call1'}},
            {'type': 'response.completed', 'response': {'usage': {'total_tokens': 10}}},
            {'type': 'content_block_delta', 'index': 0,
             'delta': {'type': 'text_delta', 'text': 'anthropic answer'}},
            {'type': 'content_block_delta', 'index': 1,
             'delta': {'type': 'thinking_delta', 'thinking': 'returned thinking'}},
            {'type': 'content_block_start', 'index': 2,
             'content_block': {'type': 'tool_use', 'id': 'tool1', 'name': 'lookup', 'input': {}}},
            {'type': 'content_block_delta', 'index': 2,
             'delta': {'type': 'input_json_delta', 'partial_json': '{"q":'}},
            {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'},
             'usage': {'output_tokens': 4}},
        ]
        wire = b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events)
        rows = self.stream(wire)
        self.assertEqual([row['text'] for row in rows if row['event'] == 'answer'],
                         ['answer', 'anthropic answer'])
        self.assertEqual([row['text'] for row in rows if row['event'] == 'reasoning'],
                         ['returned summary', 'returned thinking'])
        self.assertEqual(len([row for row in rows if row['event'] == 'tool_call']), 4)
        self.assertTrue(any(row.get('stage') == 'response.completed' for row in rows))
        self.assertTrue(any(row.get('reason') == 'tool_use' for row in rows))

    def test_nonstream_responses_and_anthropic_content_are_visible(self):
        for payload, answer in [
            ({'object': 'response', 'output': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': 'responses answer'}]},
                {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'summary'}]},
                {'type': 'function_call', 'name': 'lookup', 'arguments': '{}'}]}, 'responses answer'),
            ({'type': 'message', 'content': [
                {'type': 'text', 'text': 'anthropic answer'},
                {'type': 'thinking', 'thinking': 'thinking'},
                {'type': 'tool_use', 'name': 'lookup', 'input': {}}]}, 'anthropic answer'),
        ]:
            with self.subTest(answer=answer):
                self.output.seek(0)
                self.output.truncate()
                rows = self.stream(json.dumps(payload).encode(), 'application/json')
                self.assertTrue(any(row['event'] == 'answer' and row['text'] == answer for row in rows))
                self.assertTrue(any(row['event'] == 'reasoning' for row in rows))
                self.assertTrue(any(row['event'] == 'tool_call' for row in rows))

    def test_broken_stdout_and_root_file_handler_do_not_affect_api_or_persist_content(self):
        from console_trace import ConsoleTrace
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'root.log'
            handler = logging.FileHandler(filename, encoding='utf-8')
            logging.getLogger().addHandler(handler)
            try:
                self.trace.payload({'messages': [{'content': 'private prompt'}]})
                self.stream(b'{"choices":[{"message":{"content":"private answer"}}]}',
                            'application/json')
                handler.flush()
                self.assertEqual(filename.read_text(encoding='utf-8'), '')
            finally:
                logging.getLogger().removeHandler(handler)
                handler.close()
        broken = io.StringIO()
        console = ConsoleTrace(stream=broken)
        broken.close()
        trace = console.start('POST', '/v1/chat/completions', 'fixture')
        trace.payload({'messages': [{'content': 'still works'}]})
        trace.response(200, 'application/json')
        trace.feed(b'{}')
        trace.finish(200)


class ConsoleConfigTests(unittest.TestCase):
    def test_config_enables_trace_and_rejects_truthy_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'token').write_text(KEY, encoding='ascii')
            filename = root / 'config.json'
            value = {'schema': 1, 'backend': {'identifier': 'fixture', 'model': 'real-model',
                'upstream': 'http://127.0.0.1:18888'}, 'token_file': 'token', 'console_trace': True}
            filename.write_text(json.dumps(value), encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                gateway = load_config(filename)
                self.assertIsNotNone(gateway.console_trace)
            self.assertEqual(output.getvalue(), '')
            value['console_trace'] = 'false'
            filename.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'boolean'):
                load_config(filename)


if __name__ == '__main__':
    unittest.main()
