"""Model-free tests against the real adapter and frozen TextSession."""
import asyncio
import importlib.util
import dataclasses
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.incoming = asyncio.Queue()
        self.close_count = 0

    async def send_json(self, value):
        self.sent.append(value)

    async def receive_json(self):
        return await self.incoming.get()

    async def close(self):
        self.close_count += 1

    def feed(self, *events):
        for event in events:
            self.incoming.put_nowait(event)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        path = HERE / 'omni_conversation.py'
        spec = importlib.util.spec_from_file_location('omni_conversation', path)
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.mod
        spec.loader.exec_module(cls.mod)

    async def asyncSetUp(self):
        self.socket = FakeSocket()
        self.tick = 10.0
        def clock():
            self.tick += .25
            return self.tick
        self.client = self.mod.OmniConversation(lambda: self.socket, clock=clock,
            deadlines={'handshake_seconds': 1, 'turn_seconds': .5,
                       'control_seconds': .3, 'cleanup_seconds': .05})
        self.socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 's1'})
        await self.client.start('call-A', 1, 'Synthetic trusted rules.')

    async def asyncTearDown(self):
        await self.client.close()

    def complete(self, turn=1, generation=1, text='Vollstaendig'):
        self.socket.feed(
            {'type': 'input.committed', 'turn_id': turn, 'text': True},
            {'type': 'response.created', 'turn_id': turn, 'generation_id': generation},
            {'type': 'response.text.delta', 'generation_id': generation, 'delta': 'partial'},
            {'type': 'response.text.done', 'generation_id': generation, 'text': text},
            {'type': 'metrics', 'turn_id': turn, 'generation_id': generation, 'cancelled': False})

    def key(self, **changes):
        value = dict(call_id='call-A', task_id='task-A', task_revision=1,
                     context_revision=1, observation_revision=1, output_epoch=1, request_id='r1')
        value.update(changes)
        return value

    def snapshot(self, **changes):
        value = dict(call_id='call-A', task_id='task-A', task_revision=1,
                     context_revision=1, observation_revision=1,
                     raw_inputs=('Mara Lueders', 'L, ue, h, d, e, r, s'), public_findings=())
        value.update(changes)
        return value

    async def sent(self, kind):
        async with asyncio.timeout(2):
            while not any(event['type'] == kind for event in self.socket.sent):
                await asyncio.sleep(0)

    async def test_two_turns_return_only_done_and_retain_socket(self):
        for turn in (1, 2):
            self.complete(turn, turn, 'Antwort ' + str(turn))
            result = await self.client.respond('Whisper ' + str(turn), {
                'call_id': 'call-A', 'task_id': 'task-A', 'task_revision': 1,
                'context_revision': turn, 'observation_revision': turn,
                'raw_inputs': ('L, ue, h, d, e, r, s',), 'public_findings': ()}, {
                'call_id': 'call-A', 'task_id': 'task-A', 'task_revision': 1,
                'context_revision': turn, 'observation_revision': turn,
                'output_epoch': 1, 'request_id': 'r' + str(turn)})
            self.assertIsNotNone(result, 'A completed, identity-bound candidate is missing')
            self.assertEqual(result.text, 'Antwort ' + str(turn))
            self.assertEqual(result.identity.turn_id, turn)
            self.assertEqual(result.identity.generation_id, turn)
        self.assertEqual(self.socket.close_count, 0)
        self.assertEqual(sum(e['type'] == 'session.start' for e in self.socket.sent), 1)

    async def test_snapshot_sent_once_before_authoritative_raw_text_and_identity_frozen(self):
        self.complete(text='Antwort')
        result = await self.client.respond('Nein: L, ue, h, d, e, r, s!', self.snapshot(), self.key())
        self.assertIsNone(result.failure)
        self.assertEqual([e['type'] for e in self.socket.sent],
                         ['session.start', 'session.update', 'input.text'])
        patch = json.loads(self.socket.sent[1]['system_prompt_patch'])
        self.assertEqual(patch['context_revision'], 1)
        self.assertEqual(patch['raw_inputs'], ['Mara Lueders', 'L, ue, h, d, e, r, s'])
        self.assertEqual(self.socket.sent[2]['text'], 'Nein: L, ue, h, d, e, r, s!')
        self.assertEqual(result.authoritative_whisper_text, 'Nein: L, ue, h, d, e, r, s!')
        self.assertEqual(result.identity.call_id, 'call-A')
        self.assertEqual(result.identity.server_session_id, 's1')
        self.assertTrue(result.identity.socket_instance)
        self.assertTrue(self.client.is_current(result.identity))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.identity.output_epoch = 100
        self.assertIn('business', self.socket.sent[0]['system_prompt'].lower())

    async def test_empty_valid_delta_is_skipped_and_first_nonempty_is_measured(self):
        self.socket.feed(
            {'type': 'input.committed', 'turn_id': 1, 'text': True},
            {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': ''},
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': '\u00fc'},
            {'type': 'response.text.done', 'generation_id': 1, 'text': 'L\u00fchders'},
            {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        result = await self.client.respond('Buchstabiert', self.snapshot(), self.key())
        self.assertEqual(result.text, 'L\u00fchders')
        self.assertLess(result.submitted_at, result.first_valid_text_at)
        self.assertLess(result.first_valid_text_at, result.done_at)
        self.assertLess(result.done_at, result.terminal_at)

    async def test_done_without_terminal_never_releases_partial_or_full_text(self):
        self.socket.feed(
            {'type': 'input.committed', 'turn_id': 1, 'text': True},
            {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': 'Partial'},
            {'type': 'response.text.done', 'generation_id': 1, 'text': 'Full'})
        result = await self.client.respond('Text', self.snapshot(), self.key())
        self.assertEqual(result.text, '')
        self.assertIsNotNone(result.failure)
        self.assertIsNone(result.terminal_at)
        self.assertEqual(self.socket.close_count, 1)

    async def test_stale_old_output_cannot_complete_new_turn_or_set_its_timing(self):
        self.complete()
        old = await self.client.respond('eins', self.snapshot(), self.key())
        self.socket.feed(
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': 'ALT'},
            {'type': 'response.text.done', 'generation_id': 1, 'text': 'ALT'},
            {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        self.complete(2, 2, 'NEU')
        new = await self.client.respond('zwei', self.snapshot(context_revision=2),
                                        self.key(context_revision=2, request_id='r2'))
        self.assertEqual(new.text, 'NEU')
        self.assertFalse(self.client.is_current(old.identity))
        self.assertTrue(self.client.is_current(new.identity))

    async def test_wrong_scope_and_snapshot_revision_are_rejected_before_send(self):
        before = list(self.socket.sent)
        for key, snapshot in ((self.key(call_id='other'), self.snapshot()),
                              (self.key(), self.snapshot(task_revision=2)),
                              (self.key(output_epoch=2), self.snapshot())):
            result = await self.client.respond('Text', snapshot, key)
            self.assertEqual(result.text, '')
            self.assertIsNotNone(result.failure)
        self.assertEqual(self.socket.sent, before)

    async def test_superseded_revision_and_task_switch_need_current_binding(self):
        self.complete()
        await self.client.respond('eins', self.snapshot(context_revision=2), self.key(context_revision=2))
        before = list(self.socket.sent)
        stale = await self.client.respond('alt', self.snapshot(), self.key(request_id='r2'))
        switched = await self.client.respond('other', self.snapshot(task_id='task-B'),
                                              self.key(task_id='task-B', request_id='r3'))
        self.assertEqual(stale.text, '')
        self.assertEqual(switched.text, '')
        self.assertEqual(self.socket.sent, before)

    async def test_concurrent_respond_is_rejected_without_sending_second_input(self):
        active = asyncio.create_task(self.client.respond('eins', self.snapshot(), self.key()))
        await self.sent('input.text')
        other = await self.client.respond('zwei', self.snapshot(), self.key(request_id='r2'))
        self.assertEqual(other.failure, 'busy')
        self.complete()
        self.assertEqual((await active).text, 'Vollstaendig')
        self.assertEqual(sum(e['type'] == 'input.text' for e in self.socket.sent), 1)

    async def test_invalidate_during_stream_is_immediate_then_drains_before_next_snapshot(self):
        active = asyncio.create_task(self.client.respond('eins', self.snapshot(), self.key()))
        await self.sent('input.text')
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
                         {'type': 'response.text.delta', 'generation_id': 1, 'delta': 'ALT'})
        await asyncio.sleep(0)
        invalidation = self.client.invalidate(2, 'corrected spelling')
        self.assertEqual(self.client.output_epoch, 2)
        draining = asyncio.create_task(invalidation)
        await self.sent('response.cancel')
        early = await self.client.respond('neu', self.snapshot(), self.key(output_epoch=2, request_id='r2'))
        self.assertEqual(early.failure, 'busy')
        self.socket.feed({'type': 'response.cancelled', 'turn_id': 1, 'generation_id': 1, 'kept_text': 'ALT'},
                         {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': True})
        old = await active
        await draining
        self.assertEqual(old.text, '')
        self.assertTrue(old.cancelled)
        self.complete(2, 2, 'NEU')
        result = await self.client.respond('neu', self.snapshot(context_revision=2),
            self.key(output_epoch=2, context_revision=2, request_id='r2'))
        self.assertEqual(result.text, 'NEU')
        kinds = [e['type'] for e in self.socket.sent]
        self.assertEqual(kinds, ['session.start', 'session.update', 'input.text',
                                 'response.cancel', 'session.update', 'input.text'])

    async def test_invalidation_before_created_uncorrelatable_cancel_closes_no_retry(self):
        active = asyncio.create_task(self.client.respond('eins', self.snapshot(), self.key()))
        await self.sent('input.text')
        draining = asyncio.create_task(self.client.invalidate(2, 'correction'))
        await self.sent('response.cancel')
        self.socket.feed({'type': 'response.cancelled', 'turn_id': 1, 'kept_text': ''})
        await draining
        self.assertEqual((await active).text, '')
        self.assertEqual(self.socket.close_count, 1)
        result = await self.client.respond('neu', self.snapshot(), self.key(output_epoch=2))
        self.assertEqual(result.failure, 'unavailable')

    async def test_invalidation_timeout_closes_owned_socket_once(self):
        active = asyncio.create_task(self.client.respond('eins', self.snapshot(), self.key()))
        await self.sent('input.text')
        async with asyncio.timeout(2):
            await self.client.invalidate(2, 'no terminal')
            result = await active
        self.assertEqual(result.text, '')
        self.assertEqual(self.socket.close_count, 1)

    async def test_close_racing_stream_suppresses_result_and_owns_exactly_one_close(self):
        active = asyncio.create_task(self.client.respond('eins', self.snapshot(), self.key()))
        await self.sent('input.text')
        async with asyncio.timeout(2):
            await self.client.close()
            self.complete()
            result = await active
        await self.client.close()
        self.assertEqual(result.text, '')
        self.assertEqual(self.socket.close_count, 1)
        self.assertFalse(any(e['type'] == 'server.shutdown' for e in self.socket.sent))

    async def test_malformed_inputs_are_bounded_and_do_not_send_context(self):
        before = list(self.socket.sent)
        bad = [('', self.snapshot(), self.key()),
               ('x' * 4001, self.snapshot(), self.key()),
               ('ok', self.snapshot(raw_inputs=['raw']), self.key()),
               ('ok', self.snapshot(credentials='secret'), self.key()),
               ('ok', self.snapshot(hidden_reasoning='private'), self.key()),
               ('ok', self.snapshot(raw_inputs=('x' * 12001,)), self.key()),
               ('ok', self.snapshot(), self.key(task_revision=True)),
               ('ok', self.snapshot(), self.key(request_id=1))]
        for text, snapshot, key in bad:
            result = await self.client.respond(text, snapshot, key)
            self.assertEqual(result.text, '')
            self.assertIsNotNone(result.failure)
        self.assertEqual(self.socket.sent, before)

    async def test_nonempty_delta_stream_has_aggregate_bound(self):
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 1, 'generation_id': 1})
        for _ in range(5):
            self.socket.feed({'type': 'response.text.delta', 'generation_id': 1, 'delta': 'x' * 4000})
        self.complete(1, 1, 'not released')
        result = await self.client.respond('text', self.snapshot(), self.key())
        self.assertEqual(result.text, '')
        self.assertEqual(self.socket.close_count, 1)

    async def test_correction_during_context_send_does_not_submit_superseded_input(self):
        release, entered = asyncio.Event(), asyncio.Event()
        original = self.socket.send_json
        async def send(event):
            await original(event)
            if event['type'] == 'session.update':
                entered.set()
                await release.wait()
        self.socket.send_json = send
        active = asyncio.create_task(self.client.respond('old', self.snapshot(), self.key()))
        await entered.wait()
        draining = asyncio.create_task(self.client.invalidate(2, 'new spelling'))
        release.set()
        old = await active
        await draining
        self.assertEqual(old.text, '')
        self.assertFalse(any(e['type'] == 'input.text' for e in self.socket.sent))
        self.assertIsNone(old.identity)
        self.assertIsNone(old.done_at)
        self.complete(text='new')
        new = await self.client.respond('new', self.snapshot(context_revision=2),
            self.key(context_revision=2, output_epoch=2, request_id='r2'))
        self.assertEqual(new.text, 'new')

    async def test_superseding_before_second_input_never_borrows_old_response_identity(self):
        self.complete()
        await self.client.respond('old', self.snapshot(), self.key())
        release, entered = asyncio.Event(), asyncio.Event()
        original = self.socket.send_json
        async def send(event):
            await original(event)
            if event['type'] == 'session.update':
                entered.set()
                await release.wait()
        self.socket.send_json = send
        active = asyncio.create_task(self.client.respond('next', self.snapshot(context_revision=2),
            self.key(context_revision=2, request_id='r2')))
        await entered.wait()
        draining = asyncio.create_task(self.client.invalidate(2, 'correction'))
        release.set()
        result = await active
        await draining
        self.assertEqual(result.text, '')
        self.assertIsNone(result.identity)
        self.assertIsNone(result.first_valid_text_at)
        self.assertIsNone(result.done_at)
        self.assertIsNone(result.terminal_at)

    async def test_new_socket_even_same_server_numbers_cannot_inherit_old_candidate(self):
        self.complete()
        old = await self.client.respond('old', self.snapshot(), self.key())
        socket = FakeSocket()
        other = self.mod.OmniConversation(lambda: socket)
        socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 's1'})
        await other.start('call-A', 1, 'rules')
        socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                    {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
                    {'type': 'response.text.done', 'generation_id': 1, 'text': 'new'},
                    {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        new = await other.respond('new', self.snapshot(), self.key())
        self.assertEqual(new.text, 'new')
        self.assertFalse(other.is_current(old.identity))
        self.assertNotEqual(old.identity.socket_instance, new.identity.socket_instance)
        await other.close()
        self.assertEqual(socket.close_count, 1)
        self.assertEqual(self.socket.close_count, 0)

    async def test_terminal_without_done_is_unavailable_and_does_not_set_current_result(self):
        self.socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                         {'type': 'response.created', 'turn_id': 1, 'generation_id': 1},
                         {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
        result = await self.client.respond('text', self.snapshot(), self.key())
        self.assertEqual(result.text, '')
        self.assertFalse(self.client.is_current(result.identity))
        self.assertEqual(self.socket.close_count, 1)

    async def test_external_respond_cancellation_propagates_and_closes_once(self):
        active = asyncio.create_task(self.client.respond('old', self.snapshot(), self.key()))
        await self.sent('input.text')
        active.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await active
        self.assertEqual(self.socket.close_count, 1)
        result = await self.client.respond('new', self.snapshot(), self.key(request_id='r2'))
        self.assertEqual(result.failure, 'unavailable')

    async def test_stuck_close_and_send_are_bounded_and_do_not_close_foreign_socket(self):
        release = asyncio.Event()
        class Stuck(FakeSocket):
            async def close(inner):
                inner.close_count += 1
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await release.wait()
        socket, foreign = Stuck(), FakeSocket()
        client = self.mod.OmniConversation(lambda: socket,
            deadlines={'handshake_seconds': .2, 'turn_seconds': .2,
                       'control_seconds': .1, 'cleanup_seconds': .05})
        socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 's1'})
        await client.start('call-A', 1, 'rules')
        async def stuck_send(event):
            await asyncio.Event().wait()
        socket.send_json = stuck_send
        try:
            async with asyncio.timeout(2):
                result = await client.respond('text', self.snapshot(), self.key())
                await client.close()
            self.assertEqual(result.text, '')
            self.assertEqual(result.failure, 'unavailable')
            self.assertEqual(socket.close_count, 1)
            self.assertEqual(foreign.close_count, 0)
        finally:
            release.set()
            await asyncio.sleep(0)

    async def test_public_facts_remain_scoped_and_keep_required_child_evidence(self):
        finding = {**{k: self.key()[k] for k in ('call_id', 'task_id', 'task_revision',
                     'context_revision', 'observation_revision')}, 'evidence_id': 'e1',
                   'source_event': 'observed-child-A', 'sequence': 4, 'observed_at': 12.5,
                   'text': 'Das angefragte Modell ist nicht verfuegbar', 'superseded': False}
        snapshot = self.snapshot(public_findings=(finding,), required_children_revision=4,
            required_children=({'child_id': 'A', 'state': 'completed', 'evidence_ids': ('e1',)},
                               {'child_id': 'B', 'state': 'running', 'evidence_ids': ()}))
        self.complete()
        result = await self.client.respond('Zwischenstand?', snapshot, self.key())
        self.assertIsNone(result.failure)
        sent = json.loads(self.socket.sent[1]['system_prompt_patch'])
        self.assertEqual(sent['required_children'][1]['state'], 'running')
        before = len(self.socket.sent)
        for change in ({'task_id': 'foreign'}, {'superseded': True}, {'sequence': True}):
            bad = self.snapshot(public_findings=({**finding, 'context_revision': 2, **change},),
                                context_revision=2)
            failed = await self.client.respond('next', bad, self.key(context_revision=2, request_id='r2'))
            self.assertEqual(failed.text, '')
        self.assertEqual(len(self.socket.sent), before)


    # Each injected identity break must fail closed even for an empty delta.
    async def test_invalid_events_close_without_releasing_done(self):
        cases = [
            {'type': 'response.text.delta', 'generation_id': 2, 'delta': ''},
            {'type': 'response.text.delta', 'generation_id': True, 'delta': ''},
            {'type': 'response.text.delta', 'generation_id': 1, 'turn_id': 2, 'delta': ''},
            {'type': 'response.text.delta', 'generation_id': 1, 'session_id': 'other', 'delta': ''},
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': b'\xc3'},
            {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': 'false'},
            {'type': 'error', 'code': 'WORKER_ABANDONED', 'message': 'untrusted remote prose'},
            {'type': 'response.text.done', 'generation_id': 1, 'text': 'x' * 16385},
            {'type': 'response.text.delta', 'generation_id': 1, 'delta': '', 'junk': 'x' * 20000},
        ]
        for event in cases:
            with self.subTest(event=event['type'], keys=tuple(event)):
                socket = FakeSocket()
                client = self.mod.OmniConversation(lambda: socket,
                    deadlines={'handshake_seconds': 1, 'turn_seconds': .5,
                               'control_seconds': .3, 'cleanup_seconds': .05})
                socket.feed({'type': 'session.ready', 'mode': 'text', 'session_id': 's1'})
                await client.start('call-A', 1, 'rules')
                socket.feed({'type': 'input.committed', 'turn_id': 1, 'text': True},
                            {'type': 'response.created', 'turn_id': 1, 'generation_id': 1}, event,
                            {'type': 'response.text.done', 'generation_id': 1, 'text': 'not accepted'},
                            {'type': 'metrics', 'turn_id': 1, 'generation_id': 1, 'cancelled': False})
                result = await client.respond('test', self.snapshot(), self.key())
                self.assertEqual(result.text, '')
                self.assertIsNotNone(result.failure)
                await client.close()
                self.assertEqual(socket.close_count, 1)


if __name__ == '__main__':
    unittest.main()
