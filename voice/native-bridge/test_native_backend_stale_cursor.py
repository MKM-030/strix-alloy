"""An unread late old receipt cannot poison the following owned Native turn."""
import asyncio
import unittest
import test_native_backend_events as fixtures


class StaleBackendCursorTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.BackendEventTests.asyncSetUp
    asyncTearDown = fixtures.BackendEventTests.asyncTearDown
    callback = fixtures.BackendEventTests.callback

    async def test_known_retired_request_is_not_relabelled_or_allowed_to_poison_next_turn(self):
        received = []
        async def deliver(event):
            received.append(event)
        first = asyncio.create_task(self.dialog.turn('First original.', on_event=deliver))
        self.tasks.append(first)
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        old_request = self.original['requestId']
        await self.callback([{'uiType':'InputText', 'label':'First genuine question?'}])
        await asyncio.wait_for(first, 1)
        await self.callback([{'uiType':'OutputText', 'value':'Late old information.'}])
        second = asyncio.create_task(self.dialog.turn('New original.', on_event=deliver))
        self.tasks.append(second)
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        await self.callback([{'uiType':'OutputText', 'value':'New current information.'},
                             {'uiType':'InputText', 'label':'New genuine question?'}])
        try:
            await asyncio.wait_for(second, 1)
        except Exception as error:
            self.fail(f'Known retired receipt poisoned a new owned turn: {type(error).__name__}')
        self.assertNotIn('Late old information.', [event.text for event in received])
        self.assertEqual([(event.text, event.business_request_id) for event in received[-2:]],
            [('New current information.', self.original['requestId']),
             ('New genuine question?', self.original['requestId'])])
        self.assertNotEqual(old_request, self.original['requestId'])

    async def test_legacy_turn_ack_is_known_before_a_late_receipt_meets_typed_turn(self):
        first = asyncio.create_task(self.dialog.turn('Legacy initial topic input.'))
        self.tasks.append(first)
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        await self.callback([{'uiType':'InputText', 'label':'Legacy genuine question?'}])
        await asyncio.wait_for(first, 1)
        old_request = self.original['requestId']
        self.assertEqual(self.dialog.business_request_id, old_request)
        await self.callback([{'uiType':'OutputText', 'value':'Late bootstrap information.'}])
        received = []
        async def deliver(event):
            received.append(event)
        second = asyncio.create_task(self.dialog.turn('New typed input.', on_event=deliver))
        self.tasks.append(second)
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        await self.callback([{'uiType':'InputText', 'label':'Current typed question?'}])
        await asyncio.wait_for(second, 1)
        self.assertEqual([event.text for event in received], ['Current typed question?'])

    async def test_direct_initial_topic_post_remembers_valid_ack_without_legacy_requirements(self):
        ack = await self.dialog.request('POST', '/api/message', json={'text':'Initial topic selection.'})
        self.original = await asyncio.wait_for(self.sent.get(), 1)
        self.assertEqual(self.dialog.business_request_id, ack['businessRequestId'])


if __name__ == '__main__':
    unittest.main()
