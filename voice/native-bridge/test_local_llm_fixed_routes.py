"""Explicit fixed local routes with fake HTTP only; no credentials or service."""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_llm_socket
from local_llm_socket import LocalTextSocket, validate_local_conversation

SHARED_CHAT = 'http://127.0.0.1:8841/v1/chat/completions'
SHARED_MODELS = 'http://127.0.0.1:8841/v1/models'
DIRECT_CHAT = 'http://127.0.0.1:8840/v1/chat/completions'
DIRECT_MODELS = 'http://127.0.0.1:8840/v1/models'


def wire_context():
    return json.dumps(dict(call_id='fixture-call', task_id='fixture-task', task_revision=1,
        context_revision=1, observation_revision=1, raw_inputs=[], public_findings=[],
        capability_limits=['Use the current observations.']))


class Content:
    def __init__(self, payload=b'', lines=()):
        self.payload, self.lines = payload, lines

    async def read(self, limit):
        return self.payload[:limit]

    def __aiter__(self):
        return self.iterate()

    async def iterate(self):
        for line in self.lines:
            yield line


class Response:
    def __init__(self, payload=b'', lines=(), status=200, stream=False):
        self.status = status
        self.content = Content(payload, lines)
        self.headers = {'Content-Type': 'text/event-stream' if stream else 'application/json'}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class HTTP:
    def __init__(self, chat, models, status=200):
        self.chat, self.models, self.status = chat, models, status
        self.model, self.requests, self.bodies, self.closed = 'selected-first', [], [], False

    def get(self, url, **kwargs):
        if url != self.models:
            raise AssertionError('Model lookup changed fixed route')
        self.requests.append(('GET', url))
        return Response(json.dumps({'data': [{'id': self.model}]}).encode())

    def post(self, url, **kwargs):
        if url != self.chat:
            raise AssertionError('Completion changed fixed route')
        self.requests.append(('POST', url))
        self.bodies.append(kwargs['json'])
        events = [{'choices': [{'delta': {'content': 'Eine natürliche Antwort.'}, 'finish_reason': None}]},
                  {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}]
        lines = []
        for event in events:
            lines.extend([('data: ' + json.dumps(event) + '\n').encode(), b'\n'])
        lines.extend([b'data: [DONE]\n', b'\n'])
        return Response(lines=lines, status=self.status, stream=True)

    async def close(self):
        self.closed = True


class FixedRouteTests(unittest.IsolatedAsyncioTestCase):
    def assert_allowed(self, url):
        allowed = False
        try:
            validate_local_conversation(url, 'C:/synthetic-only-token')
            allowed = True
        except ValueError:
            pass
        self.assertTrue(allowed, 'Explicit fixed route is not admitted: ' + url)

    async def exercise(self, chat, models, *, status=200, turns=1):
        self.assert_allowed(chat)
        http = HTTP(chat, models, status)
        source = LocalTextSocket(chat, 'C:/synthetic-only-token', http=http)
        try:
            with patch.object(local_llm_socket, '_token', return_value='synthetic-only-token'), \
                    patch('aiohttp.ClientSession', side_effect=AssertionError('Real HTTP forbidden')):
                await source.send_json(dict(type='session.start', mode='text', system_prompt='Central rules'))
                await source.send_json(dict(type='session.update', system_prompt_patch=wire_context()))
                for index in range(turns):
                    http.model = 'selected-first' if index == 0 else 'selected-second'
                    await source.send_json(dict(type='input.text', text='Eine freie Frage.'))
                    await asyncio.wait_for(source._task, 1)
            events = []
            while not source.events.empty():
                events.append(source.events.get_nowait())
            return http, events, source.transient_busy
        finally:
            await source.close()

    async def test_shared_route_keeps_models_and_post_on_shared_origin_for_each_input(self):
        http, events, busy = await self.exercise(SHARED_CHAT, SHARED_MODELS, turns=2)
        self.assertEqual(http.requests, [('GET', SHARED_MODELS), ('POST', SHARED_CHAT)] * 2)
        self.assertEqual([body['model'] for body in http.bodies], ['selected-first', 'selected-second'])
        self.assertEqual(len([e for e in events if e['type'] == 'response.text.done']), 2)
        self.assertFalse(busy)

    async def test_explicit_direct_route_uses_direct_models_and_post_once_per_input(self):
        http, events, busy = await self.exercise(DIRECT_CHAT, DIRECT_MODELS, turns=2)
        self.assertEqual(http.requests, [('GET', DIRECT_MODELS), ('POST', DIRECT_CHAT)] * 2)
        self.assertEqual([body['model'] for body in http.bodies], ['selected-first', 'selected-second'])
        self.assertEqual(len([e for e in events if e['type'] == 'response.text.done']), 2)
        self.assertFalse(busy)
        for body in http.bodies:
            self.assertEqual((body['max_tokens'], body['reasoning_effort'], body['enable_thinking']), (192, 'none', False))

    async def test_busy_response_never_retries_or_changes_either_selected_route(self):
        for chat, models in [(SHARED_CHAT, SHARED_MODELS), (DIRECT_CHAT, DIRECT_MODELS)]:
            with self.subTest(chat=chat):
                http, events, busy = await self.exercise(chat, models, status=429)
                self.assertEqual(http.requests, [('GET', models), ('POST', chat)])
                self.assertEqual([e['code'] for e in events if e['type'] == 'error'], ['controller_busy'])
                self.assertFalse(any(e['type'] == 'response.text.done' for e in events))
                self.assertTrue(busy)

    async def test_owned_client_keeps_25_second_deadline_and_proxy_disabled(self):
        for chat, models in [(SHARED_CHAT, SHARED_MODELS), (DIRECT_CHAT, DIRECT_MODELS)]:
            with self.subTest(chat=chat):
                self.assert_allowed(chat)
                http = HTTP(chat, models)
                source = LocalTextSocket(chat, 'C:/synthetic-only-token')
                with patch.object(local_llm_socket, '_token', return_value='synthetic-only-token'), \
                        patch('aiohttp.ClientSession', return_value=http) as factory:
                    try:
                        await source.send_json(dict(type='session.start', mode='text', system_prompt='Central rules'))
                        await source.send_json(dict(type='session.update', system_prompt_patch=wire_context()))
                        await source.send_json(dict(type='input.text', text='Eine freie Frage.'))
                        await asyncio.wait_for(source._task, 1)
                        factory.assert_called_once()
                        self.assertFalse(factory.call_args.kwargs['trust_env'])
                        self.assertEqual(factory.call_args.kwargs['timeout'].total, 25)
                        self.assertEqual(http.requests, [('GET', models), ('POST', chat)])
                    finally:
                        await source.close()
                self.assertTrue(http.closed)

    async def test_only_the_two_literal_routes_are_accepted(self):
        self.assertEqual(local_llm_socket.CONTROLLER_CHAT_URL, SHARED_CHAT)
        self.assertEqual(local_llm_socket.CONTROLLER_MODELS_URL, SHARED_MODELS)
        for route in (SHARED_CHAT, DIRECT_CHAT):
            self.assert_allowed(route)
        for bad in [None, [], {}, 1, 'http://127.0.0.1:8731/v1/chat/completions', 'http://127.0.0.1:8842/v1/chat/completions',
                    'http://localhost:8840/v1/chat/completions', 'https://127.0.0.1:8840/v1/chat/completions',
                    DIRECT_CHAT + '?route=other', DIRECT_CHAT + '#fragment',
                    'http://127.0.0.1:8840/v1/completions', 'http://user@127.0.0.1:8840/v1/chat/completions']:
            with self.subTest(url=bad), self.assertRaises(ValueError):
                validate_local_conversation(bad, 'C:/synthetic-only-token')


if __name__ == '__main__':
    unittest.main()
