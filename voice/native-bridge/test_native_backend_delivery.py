"""Typed authoritative information survives optional local conversation backlog."""
import asyncio
import json
from types import SimpleNamespace
import unittest

from native_backend import BackendEvent, BackendState
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


RESULT = 'Die aufgezeichnete Anforderung wurde angelegt: REQ0099000, Position RITM0099000.'


class BackendDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.tasks = []

    async def asyncTearDown(self):
        self.call.closed = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.lane.close()

    async def until(self, predicate):
        async with asyncio.timeout(.3):
            while not predicate():
                self.call.playback.read(len(self.call.playback.data))
                await asyncio.sleep(.002)

    async def test_typed_information_is_voiced_with_four_later_originals_pending(self):
        turn = (0, 'Ursprüngliche Anfrage.', 1, 'original', 0)
        business = asyncio.create_task(self.lane._business(turn))
        self.tasks.append(business)
        await self.call.dialog.started.get()
        self.lane.task_revision += 1
        pending = [(0, f'Weitere Originalfrage {i}', i+2, f'later-{i}', 0) for i in range(4)]
        self.lane._pending.extend(pending)
        self.call.dialog.release.put_nowait(json.dumps({'processed_output':RESULT}))
        await business
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        try:
            await self.until(lambda: RESULT in self.call.spoken)
        except TimeoutError:
            self.fail('A genuine typed output was suppressed by the local backlog')
        self.assertEqual(self.call.spoken, [RESULT])
        self.assertEqual(list(self.lane._pending), pending)
        self.assertEqual(self.call.dialog.calls, ['Ursprüngliche Anfrage.'])

    async def test_admitted_receipt_survives_new_ack_and_local_queue_clear(self):
        self.assertTrue(callable(getattr(self.lane, '_admit_backend_event', None)),
                        'Native has no durable authoritative receipt queue')
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.assertTrue(self.lane._admit_backend_event(event, None))
        self.call.dialog.business_request_id = 'b'*32
        self.lane.interrupt()
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: RESULT in self.call.spoken)
        self.assertEqual(self.call.spoken, [RESULT])

    async def test_actual_information_remains_truthful_for_status_and_repeat_after_end(self):
        self.assertTrue(callable(getattr(self.lane, '_admit_backend_event', None)),
                        'Native has no durable authoritative receipt queue')
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.call.dialog.conversation_ended = True
        self.lane._pending.append((0, 'Und jetzt?', 2, 'later', 0))
        for text in (self.lane._status(), self.lane._repeat_last_reply()):
            self.assertIn(RESULT, text)
            self.assertNotIn('liegt weiterhin nicht vor', text)
        self.assertEqual([finding.text for finding in self.lane._current_public_findings()], [RESULT])

    async def test_owned_end_closes_input_but_preserves_received_information(self):
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.call.dialog.backend_state = BackendState('a'*32, 'MESSAGE', False, True, False,
                                                     self.call.dialog.backend_owner)
        self.call.dialog.conversation_ended = True
        self.lane._settle_backend_state()
        await self.lane._business((0, 'Neue Frage nach Ende.', 2, 'after-end', 0))
        self.assertEqual(self.call.dialog.calls, [])
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: RESULT in self.call.spoken)

    async def test_untyped_end_flag_cannot_close_native_input(self):
        self.call.dialog.backend_state = SimpleNamespace(owner=self.call.dialog.backend_owner, ended=True)
        self.lane._settle_backend_state()
        self.assertFalse(self.lane._backend_input_closed)

    async def test_matching_typed_output_and_boolean_label_are_spoken_once_as_control(self):
        self.call.dialog.business_request_id = 'a'*32
        label = 'Soll ich mit diesen Angaben fortfahren?'
        self.call.dialog.input_control = BackendEvent(2, 'a'*32, 'Boolean', label, 'native-uid',
                                                       self.call.dialog.backend_owner)
        self.lane._sync_native_control()
        event = BackendEvent(1, 'a'*32, 'OutputText', label, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: bool(self.call.spoken))
        await asyncio.sleep(.02)
        self.assertEqual(self.call.spoken, [label])
        self.assertEqual(self.lane._spoken_question['control_binding'].control_uid, 'native-uid')

    async def test_matching_nonboolean_label_does_not_swallow_information_with_backlog(self):
        self.call.dialog.business_request_id = 'a'*32
        self.call.dialog.input_control = BackendEvent(2, 'a'*32, 'InputText', RESULT, 'input-uid',
                                                       self.call.dialog.backend_owner)
        self.lane._pending.extend((0, f'Later{i}', i+2, f'later{i}', 0) for i in range(4))
        self.lane._admit_backend_event(BackendEvent(1, 'a'*32, 'OutputText', RESULT, '',
                                                   self.call.dialog.backend_owner), None)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        try:
            await self.until(lambda: RESULT in self.call.spoken)
        except TimeoutError:
            self.fail('Coalescing swallowed a genuine OutputText behind a stale non-Boolean question')

    async def test_interrupt_after_synthesis_before_drain_marks_receipt_interrupted(self):
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: RESULT in self.call.spoken)
        self.assertGreater(len(self.call.playback.data), 0)
        self.lane.interrupt()
        self.assertEqual(self.lane._backend_receipts[self.lane._backend_key(event)]['state'], 'interrupted')

    async def test_old_input_control_from_same_poll_cannot_follow_current_boolean(self):
        request = 'a'*32
        old_label = 'Beschreiben Sie Ihr Anliegen.'
        question = 'Soll ich das bestellen?'
        current = BackendEvent(4, request, 'Boolean', question, 'new-bool', self.call.dialog.backend_owner)
        old = BackendEvent(2, request, 'InputText', old_label, 'old-input', self.call.dialog.backend_owner)
        async def turn(raw, on_event=None, **kwargs):
            self.call.dialog.business_request_id = request
            self.call.dialog.input_control = current
            self.call.dialog.input_boundary = dict(source='servicenow_input_control',
                businessRequestId=request, controlType='Boolean', label=question)
            self.call.dialog.backend_state = BackendState(request, 'MESSAGE', False, False, False,
                                                          self.call.dialog.backend_owner)
            await on_event(old)
            await on_event(current)
            return [old_label, question]
        self.call.dialog.turn = turn
        await self.lane._business((0, 'Ursprüngliche Angabe.', 1, 'first', 0))
        self.assertEqual([item.text for item in self.lane._outputs], [question])

    async def test_backend_owner_reset_flushes_buffered_post_synthesis_audio(self):
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: RESULT in self.call.spoken)
        self.assertGreater(len(self.call.playback.data), 0)
        self.call.dialog.backend_owner = object()
        self.lane._update_speech_cursor()
        self.assertEqual(len(self.call.playback.data), 0)
        self.assertEqual(self.lane._backend_receipts[self.lane._backend_key(event)]['state'], 'interrupted')

    async def test_close_retires_unemitted_receipt_and_flushes_owned_pcm(self):
        self.call.dialog.business_request_id = 'a'*32
        event = BackendEvent(1, 'a'*32, 'OutputText', RESULT, '', self.call.dialog.backend_owner)
        self.lane._admit_backend_event(event, None)
        self.tasks.append(asyncio.create_task(self.lane._speak_loop()))
        await self.until(lambda: RESULT in self.call.spoken)
        await self.lane.close()
        self.assertEqual(len(self.call.playback.data), 0)
        self.assertEqual(self.lane._backend_receipts[self.lane._backend_key(event)]['state'], 'retired_by_call_close')


if __name__ == '__main__':
    unittest.main()
