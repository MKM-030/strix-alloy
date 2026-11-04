"""Real text stack with fake HTTP: terminal identity and partial-reply failures.

These tests reproduce mechanisms, not the cause of any unretained live reply.
No HTTP client, credential file, model or business session is acquired.
"""
import asyncio
from contextlib import asynccontextmanager, nullcontext
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'optional-omni')]

import local_llm_socket
import pipecat_dialogue
from local_llm_socket import LocalTextSocket, CONTROLLER_CHAT_URL, CONTROLLER_MODELS_URL
from omni_conversation import OmniConversation
from pipecat_dialogue import AggregatedTextFrame, PipecatDialogue


FIRST = 'Ja, ich höre Sie gut.'
SECOND = ('Ich kann Ihnen beim Laptop-Onboarding helfen und die Angaben für den neuen '
          'Mitarbeiter gemeinsam mit Ihnen vorbereiten.')


class FakeContent:
    def __init__(self, *, lines=(), payload=b''):
        self.lines, self.payload = lines, payload

    async def read(self, limit):
        return self.payload[:limit]

    def __aiter__(self):
        return self.lines_with_delivery()

    async def lines_with_delivery(self):
        for line in self.lines:
            await asyncio.sleep(.002)
            yield line


class FakeResponse:
    status = 200

    def __init__(self, content, *, stream=False):
        self.content = content
        self.headers = {'Content-Type': 'text/event-stream' if stream else 'application/json'}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeHTTP:
    def __init__(self, *, terminal=True):
        self.requests, self.closed = [], False
        self.lines = []
        for text in (FIRST + ' ', SECOND):
            self.event({'choices': [{'delta': {'content': text}, 'finish_reason': None}]})
        self.event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        if terminal:
            self.lines += [b'data: [DONE]\n', b'\n']

    def event(self, value):
        self.lines += [('data: ' + json.dumps(value, ensure_ascii=False) + '\n').encode(), b'\n']

    def get(self, url, **kwargs):
        if url != CONTROLLER_MODELS_URL:
            raise AssertionError('Unexpected fake selection route')
        self.requests.append(('GET', url))
        return FakeResponse(FakeContent(payload=b'{"data":[{"id":"offline-model"}]}'))

    def post(self, url, **kwargs):
        if url != CONTROLLER_CHAT_URL:
            raise AssertionError('Unexpected fake generation route')
        self.requests.append(('POST', url))
        return FakeResponse(FakeContent(lines=self.lines), stream=True)

    async def close(self):
        self.closed = True


class EOSIdentityTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def source_dialogue(self, *, turns=1):
        http = FakeHTTP()
        source = LocalTextSocket(CONTROLLER_CHAT_URL, 'C:/synthetic-token', http=http)
        adapter = OmniConversation(lambda: source)
        dialogue = PipecatDialogue(adapter)
        with patch.object(local_llm_socket, '_token', return_value='synthetic-only-token'), \
                patch('aiohttp.ClientSession', side_effect=AssertionError('Real HTTP forbidden')):
            try:
                async with asyncio.timeout(3):
                    await dialogue.start('offline-call', 1, 'Offline rules')
                    scope = dict(call_id='offline-call', task_id='offline-task', task_revision=1,
                                 context_revision=1, observation_revision=0)
                    key = dict(scope, output_epoch=1, request_id='offline-request')
                    snapshot = dict(scope, raw_inputs=('Hörst du mich?',), public_findings=())
                    result = await dialogue.respond('Hörst du mich?', snapshot, key)
                self.assertIsNone(result.failure)
                self.assertTrue(adapter.is_stream_current(result.identity))
                self.assertTrue(callable(getattr(dialogue, 'is_source_current', None)),
                                'Pipecat needs a source check separate from presentation scope')
                yield dialogue, adapter, result.identity, key, snapshot
                self.assertEqual(http.requests, [('GET', CONTROLLER_MODELS_URL),
                                                 ('POST', CONTROLLER_CHAT_URL)] * turns)
            finally:
                dialogue.conversation = adapter
                await dialogue.close()

    async def test_source_lease_survives_observation_context_and_task_revision_updates(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            self.assertTrue(dialogue.is_current(identity))
            for field in ('observation_revision', 'context_revision', 'task_revision'):
                with self.subTest(field=field):
                    key[field] += 1
                    snapshot[field] += 1
                    self.assertTrue(await dialogue.observe(snapshot, key))
                    self.assertFalse(dialogue.is_current(identity))
                    self.assertTrue(dialogue.is_source_current(identity))
                    self.assertTrue(adapter.is_stream_current(identity))

    async def test_source_lease_rejects_every_model_identity_mismatch(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            self.assertTrue(dialogue.is_source_current(identity))
            replacements = dict(call_id='other-call', task_id='other-task', task_revision=2,
                context_revision=2, observation_revision=1, output_epoch=2,
                request_id='other-request', socket_instance='other-socket',
                server_session_id='other-session', turn_id=2, generation_id=2)
            for field, value in replacements.items():
                with self.subTest(field=field):
                    self.assertFalse(dialogue.is_source_current(replace(identity, **{field: value})))
            self.assertFalse(dialogue.is_source_current(None))

    async def test_source_lease_requires_the_started_wrapper_and_exact_adapter_owner(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            foreign_wrapper = PipecatDialogue(adapter)
            self.assertFalse(foreign_wrapper.is_source_current(identity))
            self.assertFalse(copy(dialogue).is_source_current(identity))
            replacement = copy(adapter)
            self.assertTrue(replacement.is_stream_current(identity))
            dialogue.conversation = replacement
            self.assertFalse(dialogue.is_source_current(identity))
            dialogue.conversation = adapter
            self.assertTrue(dialogue.is_source_current(identity))

    async def test_source_lease_expires_at_synchronous_output_epoch_invalidation(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            self.assertTrue(dialogue.is_source_current(identity))
            drain = dialogue.invalidate(2, 'Offline user interruption')
            try:
                self.assertFalse(dialogue.is_source_current(identity))
            finally:
                await drain

    async def test_source_lease_expires_when_a_new_model_turn_takes_ownership(self):
        async with self.source_dialogue(turns=2) as (dialogue, adapter, identity, key, snapshot):
            key['request_id'] = 'offline-request-2'
            result = await dialogue.respond('Bitte weiter.', snapshot, key)
            self.assertIsNone(result.failure)
            self.assertFalse(dialogue.is_source_current(identity))
            self.assertTrue(dialogue.is_source_current(result.identity))
            self.assertEqual(result.identity.turn_id, 2)
            self.assertEqual(result.identity.generation_id, 2)

    async def test_source_lease_expires_when_adapter_closes(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            self.assertTrue(dialogue.is_source_current(identity))
            await adapter.close()
            self.assertFalse(dialogue.is_source_current(identity))

    async def test_source_lease_expires_when_wrapper_closes(self):
        async with self.source_dialogue() as (dialogue, adapter, identity, key, snapshot):
            self.assertTrue(dialogue.is_source_current(identity))
            await dialogue.close()
            self.assertFalse(dialogue.is_source_current(identity))

    async def exercise(self, *, delay_final=False, reject_second=False, terminal=True):
        http = FakeHTTP(terminal=terminal)
        source = LocalTextSocket(CONTROLLER_CHAT_URL, 'C:/synthetic-token', http=http)
        adapter = OmniConversation(lambda: source, deadlines=dict(
            handshake_seconds=3, turn_seconds=20, control_seconds=1))
        dialogue = PipecatDialogue(adapter)
        observations, delayed_frames = [], []
        original = pipecat_dialogue._CandidateSink.process_frame

        async def delayed_sink(sink, frame, direction):
            if isinstance(frame, AggregatedTextFrame) and SECOND in frame.text:
                async with asyncio.timeout(1):
                    while adapter._socket.terminal_at is None:
                        await asyncio.sleep(.001)
                await asyncio.sleep(.025)
                delayed_frames.append(True)
            await original(sink, frame, direction)

        async def sentence(candidate):
            observations.append(dict(
                terminal=adapter._socket.terminal_at is not None,
                done=adapter._socket.done_at is not None,
                stream_current=adapter.is_stream_current(candidate.identity),
                completed_current=adapter.is_current(candidate.identity),
                source_current=dialogue.is_source_current(candidate.identity),
                pipecat_current=dialogue.is_current(candidate.identity)))
            if reject_second and len(observations) == 2:
                raise ValueError('Synthetic release rejection')

        frame_patch = patch.object(pipecat_dialogue._CandidateSink, 'process_frame', delayed_sink)
        with patch.object(local_llm_socket, '_token', return_value='synthetic-only-token'), \
                patch('aiohttp.ClientSession', side_effect=AssertionError('Real HTTP forbidden')), \
                (frame_patch if delay_final else nullcontext()):
            try:
                async with asyncio.timeout(3):
                    await dialogue.start('offline-call', 1, 'Offline rules')
                    scope = dict(call_id='offline-call', task_id='offline-task', task_revision=1,
                                 context_revision=1, observation_revision=0)
                    key = dict(scope, output_epoch=1, request_id='offline-request')
                    snapshot = dict(scope, raw_inputs=('Hörst du mich?',), public_findings=())
                    result = await dialogue.respond('Hörst du mich?', snapshot, key,
                                                    on_sentence=sentence)
                evidence = dict(failure=result.failure, cancelled=result.cancelled,
                    state=adapter._state, session_closed=adapter._session.closed,
                    transport_closed=source.closed,
                    final_current=dialogue.is_current(result.identity),
                    observations=observations, delayed_frames=len(delayed_frames))
                self.assertEqual(http.requests, [('GET', CONTROLLER_MODELS_URL),
                                                 ('POST', CONTROLLER_CHAT_URL)])
                return evidence
            finally:
                await dialogue.close()

    async def assert_success(self, *, delay_final):
        result = await self.exercise(delay_final=delay_final)
        self.assertIsNone(result['failure'])
        self.assertFalse(result['cancelled'])
        self.assertEqual(result['state'], 'ready')
        self.assertFalse(result['session_closed'])
        self.assertFalse(result['transport_closed'])
        self.assertTrue(result['final_current'])
        self.assertEqual(len(result['observations']), 2)
        first, final = result['observations']
        self.assertFalse(first['terminal'])
        self.assertFalse(first['completed_current'])
        self.assertTrue(final['terminal'])
        self.assertTrue(final['done'])
        self.assertTrue(final['completed_current'])
        self.assertTrue(all(item['stream_current'] and item['pipecat_current'] and item['source_current']
                            for item in result['observations']))
        self.assertEqual(result['delayed_frames'], int(delay_final))

    async def test_valid_stream_keeps_final_sentence_identity_current_after_terminal(self):
        await self.assert_success(delay_final=False)

    async def test_forced_postterminal_final_frame_delay_keeps_identity_current(self):
        await self.assert_success(delay_final=True)

    async def test_second_callback_rejection_reports_failure_without_closing_adapter(self):
        result = await self.exercise(reject_second=True)
        self.assertEqual(len(result['observations']), 2)
        self.assertEqual(result['failure'], 'output_callback_failed')
        self.assertFalse(result['cancelled'])
        self.assertEqual(result['state'], 'ready')
        self.assertFalse(result['session_closed'])
        self.assertFalse(result['transport_closed'])

    async def test_missing_done_after_first_sentence_reports_unavailable_and_closes_adapter(self):
        result = await self.exercise(terminal=False)
        self.assertEqual(len(result['observations']), 1)
        self.assertEqual(result['failure'], 'unavailable')
        self.assertEqual(result['state'], 'unavailable')
        self.assertTrue(result['session_closed'])
        self.assertTrue(result['transport_closed'])


if __name__ == '__main__':
    unittest.main()
