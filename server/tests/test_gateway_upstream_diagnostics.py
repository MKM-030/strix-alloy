import asyncio
import json
from pathlib import Path
import sys
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import Backend, Gateway

KEY = 'fixture-public-credential-material-thirtytwo'
PRIVATE = 'PRIVATE_PROMPT_TOKEN_PATH_URL_UNIQUE'


class UpstreamDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.raw = json.dumps({'error': {'message': 'unknown ' + PRIVATE}}).encode()
        self.status = 400
        self.encoding = None
        self.seen = []

        async def health(request):
            return web.json_response({'status': 'ok'})

        async def chat(request):
            self.seen.append(await request.json())
            headers = {'Content-Type': 'application/json'}
            if self.encoding:
                headers['Content-Encoding'] = self.encoding
            response = web.StreamResponse(status=self.status, headers=headers)
            await response.prepare(request)
            # Error JSON arrives in arbitrary transport chunks.
            await response.write(self.raw[:17])
            await asyncio.sleep(0)
            await response.write(self.raw[17:])
            return response

        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_post('/v1/chat/completions', chat)
        self.upstream = TestServer(app)
        await self.upstream.start_server()
        backend = Backend('fixture', str(self.upstream.make_url('')).rstrip('/'),
                          'upstream-model', context=32768)
        self.gateway = Gateway(backend, KEY)
        self.client = TestClient(TestServer(self.gateway.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.upstream.close()

    async def send(self, message, **extra):
        self.raw = json.dumps({'error': {'message': message}}).encode()
        body = {'model': 'fixture', 'messages': [{'role': 'user', 'content': PRIVATE}],
                'max_tokens': 2048, 'tools': [{'function': {'name': PRIVATE}}], **extra}
        with self.assertLogs('alloy.gateway', level='INFO') as captured:
            response = await self.client.post('/v1/chat/completions',
                headers={'Authorization': 'Bearer ' + KEY}, json=body)
            self.assertEqual(await response.read(), self.raw)
            self.assertEqual(response.status, self.status)
        rows = [json.loads(line.split('Gateway upstream rejection ', 1)[1])
                for line in captured.output if 'Gateway upstream rejection ' in line]
        self.assertEqual(len(rows), 1, captured.output)
        self.assertNotIn(PRIVATE, '\n'.join(captured.output))
        self.assertNotIn(KEY, '\n'.join(captured.output))
        self.assertEqual(self.seen[-1]['max_tokens'], body['max_tokens'])
        self.assertEqual(self.seen[-1]['messages'], body['messages'])
        self.assertEqual(self.gateway.active, 0)
        return rows[0]

    async def test_reports_actual_prompt_and_output_budget_without_payload(self):
        row = await self.send('max_tokens 2048 does not fit: prompt is 31000 '
                              'tokens and the context is 32768, leaving room for 1768.')
        self.assertEqual(row['error_class'], 'output_budget_exceeds_context')
        self.assertEqual(row['prompt_tokens'], 31000)
        self.assertEqual(row['context_tokens'], 32768)
        self.assertEqual(row['available_output_tokens'], 1768)
        self.assertEqual(row['requested_max_tokens'], 2048)
        self.assertEqual(row['message_count'], 1)
        self.assertEqual(row['tool_count'], 1)
        self.assertEqual(row['prompt_chars'], len(PRIVATE))

    async def test_unknown_error_does_not_log_its_arbitrary_message(self):
        row = await self.send('unknown ' + PRIVATE)
        self.assertEqual(row['error_class'], 'unclassified')

    async def test_only_whitelisted_parameter_names_leave_validation_error(self):
        row = await self.send('temperature: Input should be a valid number; '
                              + PRIVATE + ': secret value ' + PRIVATE)
        self.assertEqual(row['error_class'], 'request_validation')
        self.assertEqual(row['invalid_fields'], ['temperature'])

    async def test_prompt_too_long_has_numeric_budget_only(self):
        row = await self.send('the prompt does not fit: it is 35000 tokens and '
            'the context is 32768, 2232 tokens over. Shorten the prompt, or raise the context.')
        self.assertEqual(row['error_class'], 'prompt_exceeds_context')
        self.assertEqual(row['prompt_tokens'], 35000)
        self.assertEqual(row['context_tokens'], 32768)

    async def test_encoded_error_body_is_not_parsed(self):
        self.encoding = 'identity'
        row = await self.send('max_tokens 2048 does not fit: prompt is 31000 '
                              'tokens and the context is 32768, leaving room for 1768.')
        self.assertEqual(row['error_class'], 'encoded_body_skipped')

    async def test_oversized_error_is_not_parsed_or_copied_to_log(self):
        row = await self.send('x' * 20000 + PRIVATE)
        self.assertEqual(row['error_class'], 'oversized_body_skipped')

    async def test_invalid_budget_type_is_classified_without_logging_its_value(self):
        row = await self.send('max_tokens: Input should be a valid integer', max_tokens=PRIVATE)
        self.assertEqual(row['max_tokens'], -1)
        self.assertEqual(row['invalid_fields'], ['max_tokens'])

    async def test_reviewed_engine_error_families_never_log_dynamic_suffixes(self):
        cases = (
            ('the engine refused this request: ' + PRIVATE, 'engine_refused'),
            ('the engine rejected this request. ' + PRIVATE, 'engine_refused'),
            ('response_format json_schema needs a ' + PRIVATE, 'invalid_json_schema'),
            ('chat template rejected the request: ' + PRIVATE, 'chat_template_rejected'),
            ('body: Value error, conflicting token budgets (' + PRIVATE, 'conflicting_token_budgets'),
            ('body: Value error, ' + PRIVATE, 'request_validation'),
            ('temperature=3.0 is outside 0.0..2.0. ' + PRIVATE, 'invalid_parameter'),
            ('presence_penalty applies to the sampler, ' + PRIVATE, 'invalid_parameter'),
            ('tool_choice names ' + PRIVATE, 'invalid_parameter'),
            ('drafter ' + PRIVATE, 'invalid_parameter'),
            ('the chat template emitted ' + PRIVATE, 'chat_template_rejected'),
            ('this server does not accept images: ' + PRIVATE, 'image_input_invalid'),
        )
        for message, code in cases:
            with self.subTest(code=code, prefix=message[:25]):
                row = await self.send(message)
                self.assertEqual(row['error_class'], code)

    async def test_output_policy_cap_is_numeric_and_does_not_expose_suffix(self):
        row = await self.send("max_tokens 70000 exceeds this server's cap of 65536. " + PRIVATE)
        self.assertEqual(row['error_class'], 'output_budget_exceeds_policy')
        self.assertEqual(row['requested_max_tokens'], 70000)
        self.assertEqual(row['output_tokens_cap'], 65536)

    async def test_template_failure_reports_only_reviewed_literal_reason(self):
        for reason, code in (
            ('No user query found in messages.', 'no_user_query'),
            ('Unexpected content type.', 'unexpected_content_type'),
            ('Already borrowed', 'tokenizer_already_borrowed'),
            ('Unexpected reasoning effort ' + PRIVATE + '. Supported types are xhigh (default), medium, and low.', 'unsupported_reasoning_effort'),
            ('arbitrary ' + PRIVATE, 'unclassified'),
        ):
            with self.subTest(code=code):
                row = await self.send('chat template rejected the request: ' + reason)
                self.assertEqual(row.get('template_reason'), code)

    async def test_message_roles_and_image_shapes_are_counts_never_raw_values(self):
        row = await self.send('chat template rejected the request: No user query found in messages.',
            enable_thinking=False, reasoning_effort=PRIVATE,
            messages=[{'role': 'system', 'content': PRIVATE},
                      {'role': 'assistant', 'content': None},
                      {'role': PRIVATE, 'content': [{'type': 'image_url', 'image_url': {'url': PRIVATE}},
                                                   {'type': 'text', 'text': PRIVATE}]}])
        self.assertEqual(row.get('role_system'), 1)
        self.assertEqual(row.get('role_user'), 0)
        self.assertEqual(row.get('role_assistant'), 1)
        self.assertEqual(row.get('role_other'), 1)
        self.assertEqual(row.get('content_string'), 1)
        self.assertEqual(row.get('content_null'), 1)
        self.assertEqual(row.get('content_list'), 1)
        self.assertEqual(row.get('image_parts'), 1)
        self.assertEqual(row['prompt_chars'], len(PRIVATE) * 2)
        self.assertEqual(row.get('thinking_enabled'), 0)
        self.assertEqual(row.get('reasoning_effort_class'), 'other')

    async def test_successful_payload_is_forwarded_without_rejection_log(self):
        self.status = 200
        self.raw = json.dumps({'choices': [{'message': {'content': PRIVATE}}]}).encode()
        with self.assertLogs('alloy.gateway', level='INFO') as captured:
            response = await self.client.post('/v1/chat/completions',
                headers={'Authorization': 'Bearer ' + KEY}, json={'model': 'fixture'})
            self.assertEqual(await response.read(), self.raw)
        self.assertFalse(any('Gateway upstream rejection' in line for line in captured.output))
        self.assertNotIn(PRIVATE, '\n'.join(captured.output))


if __name__ == '__main__':
    unittest.main()
