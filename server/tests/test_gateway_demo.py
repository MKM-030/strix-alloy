"""Loopback contract checks; no production engine or ServiceNow calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import load_config

KEY = 'fixture-demo-no-thinking-key-32-characters'
HEADERS = {'Authorization': 'Bearer ' + KEY}


class DemoNoThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen = []
        async def health(request):
            return web.json_response({'status': 'ok'})
        async def capture(request):
            self.seen.append((request.path, await request.json()))
            return web.json_response({'ok': True})
        app = web.Application()
        app.router.add_get('/health', health)
        app.router.add_post('/v1/chat/completions', capture)
        app.router.add_post('/v1/responses', capture)
        self.up = TestServer(app)
        await self.up.start_server()
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / 'key.txt').write_text(KEY, encoding='ascii')
        self.config_path = root / 'gateway.json'
        self.config = {
            'schema': 1, 'token_file': 'key.txt',
            'backend': {'identifier': 'halogen-v2',
                'upstream': str(self.up.make_url('')).rstrip('/'),
                'model': 'halogen-qwen3.8-flash-next',
                'routes': ['/v1/chat/completions', '/v1/responses']}}
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        await self.up.close()
        self.directory.cleanup()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')

    async def client(self, target=None):
        if target is not None:
            self.config['demo_no_thinking_model'] = target
        self.write_config()
        gateway = load_config(self.config_path)
        client = TestClient(TestServer(gateway.app))
        self.clients.append(client)
        await client.start_server()
        return client

    async def send(self, client, model='halogen-v2', route='/v1/chat/completions'):
        body = {'model': model, 'messages': [{'role': 'user', 'content': 'fixture'}],
                'enable_thinking': True, 'reasoning_effort': 'medium',
                'max_tokens': 2048, 'max_thinking_tokens': 2048, 'stream': False,
                'response_format': {'type': 'json_object'},
                'tools': [{'type': 'function', 'function': {'name': 'fixture'}}]}
        response = await client.post(route, headers=HEADERS, json=body)
        self.assertEqual(response.status, 200)
        await response.read()
        return body, self.seen[-1][1]

    async def test_enabled_alias_overrides_thinking_and_preserves_tool_contract(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client)
        expected = dict(original, model='halogen-qwen3.8-flash-next',
                        enable_thinking=False, reasoning_effort='none')
        self.assertEqual(observed, expected)

    async def test_default_off_preserves_original_request_settings(self):
        client = await self.client()
        original, observed = await self.send(client)
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_explicit_off_preserves_original_request_settings(self):
        client = await self.client('')
        original, observed = await self.send(client)
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_upstream_model_name_does_not_trigger_alias_override(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client, model='halogen-qwen3.8-flash-next')
        self.assertEqual(observed, original)

    async def test_demo_flat_system_task_keeps_system_and_adds_required_user_dispatch(self):
        client = await self.client('halogen-v2')
        content = ('Vollstaendige Aufgabe: Bitte einen Laptop fuer Philipp Borchert bestellen. '
                   'Vor dem Absenden die Bestaetigung einholen. PRIVATE_FIXTURE_CONTENT') * 400
        message = {'role': 'system', 'content': content, 'name': 'fixture',
                   'metadata': {'fixture': 'preserve'}}
        body = {'model': 'halogen-v2', 'messages': [message], 'max_tokens': 4096,
                'temperature': 0, 'stream': False, 'response_format': {'type': 'json_object'}}
        with self.assertLogs('alloy.gateway', level='INFO') as captured:
            response = await client.post('/v1/chat/completions', headers=HEADERS, json=body)
            self.assertEqual(response.status, 200)
            await response.read()
        dispatch = 'Bitte bearbeite die im Systemtext beschriebene Aufgabe und beachte das dort geforderte Ausgabeformat.'
        self.assertEqual(self.seen[-1][1], dict(body,
            messages=[message, {'role': 'user', 'content': dispatch}], model='halogen-qwen3.8-flash-next',
            enable_thinking=False, reasoning_effort='none'))
        self.assertTrue(any('compatibility=single_system_flat_prompt' in line
                            for line in captured.output))
        self.assertNotIn('PRIVATE_FIXTURE_CONTENT', '\n'.join(captured.output))
        self.assertNotIn('Philipp Borchert', '\n'.join(captured.output))

    async def test_flat_prompt_compatibility_leaves_other_contracts_unchanged(self):
        enabled = await self.client('halogen-v2')
        disabled = await self.client('')
        shapes = [
            [{'role': 'user', 'content': 'fixture'}],
            [{'role': 'system', 'content': 'rules'}, {'role': 'user', 'content': 'task'}],
            [{'role': 'system', 'content': [{'type': 'text', 'text': 'fixture'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,fixture'}}]}],
            [{'role': 'assistant', 'content': 'fixture'}],
            [{'role': 'tool', 'content': 'fixture', 'tool_call_id': 'fixture'}],
            [{'role': 'system', 'content': {'text': 'fixture'}}],
            [{'role': 'system', 'content': None}], [],
            [{'role': 'system', 'content': ''}],
            [{'role': 'system', 'content': '   '}],
        ]
        cases = [(enabled, 'halogen-v2', '/v1/chat/completions', messages, True)
                 for messages in shapes]
        system = [{'role': 'system', 'content': 'fixture'}]
        cases.extend([
            (disabled, 'halogen-v2', '/v1/chat/completions', system, False),
            (enabled, 'halogen-qwen3.8-flash-next', '/v1/chat/completions', system, False),
            (enabled, 'halogen-v2', '/v1/responses', system, False),
        ])
        for client, model, route, messages, thinking_override in cases:
            body = {'model': model, 'messages': messages, 'max_tokens': 4096,
                    'enable_thinking': True, 'reasoning_effort': 'medium'}
            with self.subTest(route=route, model=model, messages=messages):
                with self.assertLogs('alloy.gateway', level='INFO') as captured:
                    response = await client.post(route, headers=HEADERS, json=body)
                    self.assertEqual(response.status, 200)
                    await response.read()
                expected = dict(body, model='halogen-qwen3.8-flash-next')
                if thinking_override:
                    expected.update(enable_thinking=False, reasoning_effort='none')
                self.assertEqual(self.seen[-1][1], expected)
                self.assertFalse(any('compatibility=single_system_flat_prompt' in line
                                     for line in captured.output))
        for tools in ([{'type': 'function', 'function': {'name': 'fixture'}}], {}, False):
            body = {'model': 'halogen-v2', 'messages': system, 'tools': tools}
            response = await enabled.post('/v1/chat/completions', headers=HEADERS, json=body)
            self.assertEqual(response.status, 200)
            await response.read()
            self.assertEqual(self.seen[-1][1], dict(body,
                model='halogen-qwen3.8-flash-next', enable_thinking=False, reasoning_effort='none'))

    async def test_scc_persona_history_and_action_reach_model_unchanged_before_system_dispatch(self):
        client = await self.client('halogen-v2')
        content = ('SCC Laptop Onboarding Voice\npersona: Antworte auf Deutsch.\n'
                   'conversation_history: Fuer den Mitarbeiter Philipp Borchert.\n'
                   'action_id: FIXED_CONTROL; input_key: employee; require explicit confirmation.')
        system = {'role': 'system', 'content': content, 'name': 'fixture'}
        body = {'model': 'halogen-v2', 'messages': [system], 'max_tokens': 4096,
                'response_format': {'type': 'json_object'}, 'temperature': 0, 'stream': False}
        response = await client.post('/v1/chat/completions', headers=HEADERS, json=body)
        self.assertEqual(response.status, 200)
        await response.read()
        dispatch = {'role': 'user', 'content': 'Bitte bearbeite die im Systemtext beschriebene Aufgabe und beachte das dort geforderte Ausgabeformat.'}
        # The generic adapter preserves the caller's language policy; the
        # historical gateway-level German override is intentionally retired.
        self.assertEqual(self.seen[-1][1], dict(body,
            messages=[system, dispatch],
            model='halogen-qwen3.8-flash-next', enable_thinking=False, reasoning_effort='none'))

    async def test_locale_http_boundary_preserves_existing_suffix_and_other_use_cases(self):
        client = await self.client('halogen-v2')
        marker = '<scc_voice_locale_override_20261013>'
        cases = (
            ([{'role': 'user', 'content': 'SCC Laptop Onboarding Voice ' + marker + 'custom'}], {}),
            ([{'role': 'user', 'content': 'Antragsformular ausfuellen.'}], {}),
            ([{'role': 'system', 'content': 'SCC Laptop Onboarding Voice'},
              {'role': 'user', 'content': 'Eine andere Aufgabe.'}], {}),
            ([{'role': 'user', 'content': [{'type': 'text', 'text': 'SCC Laptop Onboarding Voice'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,fixture'}}]}], {}),
            ([{'role': 'system', 'content': 'SCC Laptop Onboarding Voice'}],
                {'tools': [{'type': 'function', 'function': {'name': 'fixture'}}]}),
        )
        for messages, extras in cases:
            body = dict(model='halogen-v2', messages=messages,
                        response_format={'type': 'json_object'}, max_tokens=4096, **extras)
            response = await client.post('/v1/chat/completions', headers=HEADERS, json=body)
            self.assertEqual(response.status, 200)
            await response.read()
            self.assertEqual(self.seen[-1][1], dict(body,
                model='halogen-qwen3.8-flash-next', enable_thinking=False, reasoning_effort='none'))

    async def test_other_route_does_not_trigger_chat_override(self):
        client = await self.client('halogen-v2')
        original, observed = await self.send(client, route='/v1/responses')
        self.assertEqual(observed, dict(original, model='halogen-qwen3.8-flash-next'))

    async def test_unknown_alias_is_still_rejected_before_forwarding(self):
        client = await self.client('halogen-v2')
        response = await client.post('/v1/chat/completions', headers=HEADERS,
                                     json={'model': 'another-alias'})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.seen, [])

    def test_invalid_or_conflicting_target_configuration_is_rejected(self):
        for value in (True, None, [], 'another-alias', 'halogen-qwen3.8-flash-next'):
            with self.subTest(value=value):
                self.config['demo_no_thinking_model'] = value
                self.write_config()
                with self.assertRaises(ValueError):
                    load_config(self.config_path)


if __name__ == '__main__':
    unittest.main()
