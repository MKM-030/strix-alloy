"""Obsolete optional work leaves a fake HTTP queue without disturbing speech.

The real Native/Pipecat/protocol/LocalTextSocket stack is used; no model,
credential file, HTTP connection, audio device or business request is opened.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'optional-omni')]

import local_llm_socket
from local_llm_socket import LocalTextSocket, CONTROLLER_CHAT_URL
from native_duplex import NativeDuplex
from omni_conversation import OmniConversation
from pipecat_dialogue import PipecatDialogue
from test_native_duplex import FakeCall
from test_pipecat_eos_identity import FakeContent, FakeHTTP, FakeResponse


class QueuedHTTP(FakeHTTP):
    def __init__(self):
        super().__init__()
        self.queued, self.release = asyncio.Event(), asyncio.Event()
        self.removed, self.dispatched = asyncio.Event(), asyncio.Event()
        self.first_text, self.finish = asyncio.Event(), asyncio.Event()
        self.posts = 0

    def post(self, url, **kwargs):
        normal = super().post(url, **kwargs)
        self.posts += 1
        if self.posts != 1:
            return normal
        owner = self

        class Content(FakeContent):
            async def lines_with_delivery(self):
                for index, line in enumerate(self.lines):
                    yield line
                    if index == 1:
                        owner.first_text.set()
                        await owner.finish.wait()

        class Response(FakeResponse):
            async def __aenter__(self):
                owner.queued.set()
                try:
                    await owner.release.wait()
                except asyncio.CancelledError:
                    owner.removed.set()
                    raise
                owner.dispatched.set()
                return self

        return Response(Content(lines=self.lines), stream=True)


class OptionalContextRetirementTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def fixture(self):
        http = QueuedHTTP()
        socket = LocalTextSocket(CONTROLLER_CHAT_URL, 'C:/synthetic-token', http=http)
        adapter = OmniConversation(lambda: socket)
        dialogue = PipecatDialogue(adapter)
        call = FakeCall()
        lane = NativeDuplex(call)
        lane.conversation = dialogue
        turn = (0, 'Was ist der nächste Schritt?', 1, 'a' * 32, 1)
        lane._raw.append(turn[1])
        lane._dialogue_turn = turn
        lane._business_delivery = dict(turn_id=turn[3], owner=call.dialog.backend_owner,
                                       request_id=None, phase='handoff')
        tasks = []
        with patch.object(local_llm_socket, '_token', return_value='synthetic-only-token'), \
                patch('aiohttp.ClientSession', side_effect=AssertionError('Real HTTP forbidden')):
            try:
                await dialogue.start(call.call_id, 1, 'Offline rules')
                key, snapshot, _ = lane._dialogue_snapshot(turn, 1)
                lane._dialogue_observation_state = (
                    dialogue, lane._dialogue_signature(snapshot, key), object())
                yield http, socket, adapter, dialogue, lane, key, snapshot, tasks
            finally:
                http.release.set()
                http.finish.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await lane.close()

    async def observe(self, lane):
        lane._queue_dialogue_observation()
        tasks = tuple(lane._observations)
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), 2)

    def change_boundary(self, lane):
        lane.call.dialog.observation_revision += 1
        lane.call.dialog.input_boundary = dict(source='servicenow_input_control',
            businessRequestId='b' * 32, controlType='InputText', label='Welche Lieferadresse gilt?')

    async def test_semantic_change_removes_queued_optional_work_and_reuses_session(self):
        async with self.fixture() as (http, socket, adapter, dialogue, lane, key, snapshot, tasks):
            reply = asyncio.create_task(dialogue.respond('Was ist der nächste Schritt?', snapshot, key))
            native_work = asyncio.create_task(asyncio.Event().wait())
            tasks.extend((reply, native_work))
            await asyncio.wait_for(http.queued.wait(), 1)

            # An owned transport ACK, raw passive sound and presentation-only
            # observation counter do not change Native's semantic context.
            lane.call.dialog.business_request_id = 'c' * 32
            lane._business_delivery['request_id'] = lane.call.dialog.business_request_id
            lane.call.dialog.observation_revision += 1
            lane._raw.append('Mhm.')
            await self.observe(lane)
            self.assertFalse(http.removed.is_set())
            self.assertFalse(reply.done())

            self.change_boundary(lane)
            await self.observe(lane)
            self.assertTrue(http.removed.is_set(), 'Obsolete request still occupies the HTTP queue')
            self.assertFalse(http.dispatched.is_set(), 'Obsolete queued work reached inference')
            result = await asyncio.wait_for(reply, 1)
            self.assertTrue(result.cancelled)
            self.assertEqual(result.failure, 'superseded')
            self.assertFalse(native_work.done())
            self.assertEqual(lane.call.dialog.calls, [])
            self.assertEqual(adapter._state, 'ready')
            self.assertFalse(socket.closed)
            self.assertFalse(adapter._session.closed)

            fresh_key, fresh_snapshot, _ = lane._dialogue_snapshot(lane._dialogue_turn, 1)
            fresh_key['request_id'] = 'fresh-request'
            fresh = await asyncio.wait_for(dialogue.respond('Bitte weiter.', fresh_snapshot, fresh_key), 1)
            self.assertIsNone(fresh.failure)
            self.assertEqual(http.posts, 2)

    async def test_context_update_await_cannot_launch_retired_request_after_release(self):
        async with self.fixture() as (http, socket, adapter, dialogue, lane, key, snapshot, tasks):
            entered, release = asyncio.Event(), asyncio.Event()
            original = adapter._session.update_context
            async def held_context(value):
                entered.set()
                await release.wait()
                await original(value)
            adapter._session.update_context = held_context
            reply = asyncio.create_task(dialogue.respond('Was ist der nächste Schritt?', snapshot, key))
            tasks.append(reply)
            await asyncio.wait_for(entered.wait(), 1)
            self.change_boundary(lane)
            observation = asyncio.create_task(self.observe(lane))
            tasks.append(observation)
            try:
                async with asyncio.timeout(.5):
                    while adapter._key is not None:
                        await asyncio.sleep(.001)
            finally:
                release.set()
            await observation
            result = await asyncio.wait_for(reply, 1)
            self.assertTrue(result.cancelled)
            self.assertEqual(http.posts, 0)
            self.assertEqual(adapter._state, 'ready')
            self.assertFalse(socket.closed)

    async def test_first_text_preserves_source_lease_while_observation_rejects_future_text(self):
        async with self.fixture() as (http, socket, adapter, dialogue, lane, key, snapshot, tasks):
            reply = asyncio.create_task(dialogue.respond('Was ist der nächste Schritt?', snapshot, key))
            tasks.append(reply)
            await asyncio.wait_for(http.queued.wait(), 1)
            http.release.set()
            async with asyncio.timeout(1):
                while dialogue._operation.identity is None:
                    await asyncio.sleep(.001)
            identity = dialogue._operation.identity
            self.assertIsNotNone(adapter._socket.first_at)
            self.change_boundary(lane)
            await self.observe(lane)
            self.assertFalse(reply.done())
            self.assertFalse(http.removed.is_set())
            self.assertTrue(dialogue.is_source_current(identity))
            self.assertFalse(dialogue.is_current(identity))
            self.assertFalse(socket.closed)
            http.finish.set()
            result = await asyncio.wait_for(reply, 1)
            self.assertEqual(result.failure, 'superseded')
            self.assertTrue(dialogue.is_source_current(identity))


if __name__ == '__main__':
    unittest.main()
