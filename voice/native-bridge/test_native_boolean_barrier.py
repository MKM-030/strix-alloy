"""A typed native Boolean cannot consume unheard, earlier caller remarks."""
import asyncio
import json
import unittest

import test_native_backend_events as fixtures


SUMMARY = 'Mitarbeiter und Führungskraft sind angegeben, Eintritt am ersten November, Lieferort Berlin. Soll ich das bestellen?'


class NativeDispatchBarrierTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.BackendEventTests.asyncSetUp
    asyncTearDown = fixtures.BackendEventTests.asyncTearDown
    begin = fixtures.BackendEventTests.begin
    callback = fixtures.BackendEventTests.callback
    state = fixtures.BackendEventTests.state

    async def prepare(self):
        await self.begin()
        await self.callback([{'uiType': 'Boolean', 'label': SUMMARY, 'uniqueIdentifier': 'genuine-boolean-9'}])
        receipt = (await self.state())['inputControl']
        return dict(businessRequestId=receipt['businessRequestId'], controlType='Boolean',
            label=receipt['text'], eventId=receipt['id'], controlUid=receipt['controlUid'])

    async def submit(self, raw, binding):
        native = dict(version=1, attemptId='2' * 32, ownerId='1' * 32, binding=binding)
        response = await self.dialog.http.post(self.bridge.origin + '/api/message',
            json={'text': raw, 'nativeInput': native},
            headers={'Origin': self.bridge.origin, 'X-CSRF-Token': self.dialog.csrf})
        try:
            payload = await response.json(content_type=None)
        except json.JSONDecodeError:
            payload = {}
        await response.read()
        return response.status, payload, native

    async def test_every_unheard_input_is_blocked_before_dispatch(self):
        await self.prepare()
        for raw in ('Wie geht jetzt weiter', 'Ja und was ist jetzt damit? Sind wir jetzt fertig oder',
                    'Ja', 'Bitte ändere den Lieferort.', 'Am ersten November.'):
            with self.subTest(raw=raw):
                status, payload, native = await self.submit(raw, None)
                self.assertEqual(status, 409)
                self.assertEqual(payload.get('dispatch'), 'not_started')
                self.assertEqual(payload.get('attemptId'), native['attemptId'])
                self.assertEqual(payload.get('ownerId'), native['ownerId'])
                self.assertEqual(payload.get('inputControl', {}).get('controlUid'), 'genuine-boolean-9')
                self.assertTrue(self.sent.empty(), 'Unheard input must never leave the Bridge')

    async def test_exact_bound_fresh_raw_answer_is_sent_once_without_boolean_conversion(self):
        binding = await self.prepare()
        raw = 'Nein, ich möchte zuerst etwas ändern.'
        status, payload, _ = await self.submit(raw, binding)
        self.assertEqual(status, 202)
        outbound = await asyncio.wait_for(self.sent.get(), 1)
        self.assertEqual(outbound['message']['text'], raw)
        self.assertTrue(outbound['message']['typed'])
        self.assertEqual(payload['businessRequestId'], outbound['requestId'])
        self.assertTrue(self.sent.empty())

    async def test_changed_control_uid_rejects_even_when_summary_text_is_identical(self):
        binding = await self.prepare()
        await self.callback([{'uiType': 'Boolean', 'label': SUMMARY, 'uniqueIdentifier': 'replacement-boolean'}])
        status, payload, _ = await self.submit('Ja', binding)
        self.assertEqual(status, 409)
        self.assertEqual(payload.get('inputControl', {}).get('controlUid'), 'replacement-boolean')
        self.assertTrue(self.sent.empty())

    async def test_control_is_compared_after_waiting_for_context_dispatch_lock(self):
        binding = await self.prepare()
        class ObservedLock(asyncio.Lock):
            async def __aenter__(self):
                entered.set()
                return await super().__aenter__()
        entered = asyncio.Event()
        session = next(iter(self.bridge.sessions.values()))
        session.context_lock = ObservedLock()
        await session.context_lock.acquire()
        sending = asyncio.create_task(self.submit('Ja', binding))
        self.tasks.append(sending)
        await asyncio.wait_for(entered.wait(), 1)
        await self.callback([{'uiType':'Boolean', 'label':SUMMARY, 'uniqueIdentifier':'changed-under-lock'}])
        session.context_lock.release()
        status, payload, _ = await asyncio.wait_for(sending, 1)
        self.assertEqual(status, 409)
        self.assertEqual(payload['inputControl']['controlUid'], 'changed-under-lock')
        self.assertTrue(self.sent.empty())

    async def test_native_none_is_sent_and_proven_conflict_is_not_dispatched(self):
        await self.prepare()
        async def deliver(event):
            self.fail('A rejected submission has no new output')
        turning = asyncio.create_task(self.dialog.turn('Wie geht jetzt weiter', on_event=deliver,
                                                       native_control_binding=None))
        self.tasks.append(turning)
        async with asyncio.timeout(1):
            while not turning.done() and self.sent.empty():
                await asyncio.sleep(.002)
        self.assertTrue(self.sent.empty(), 'Native must send its explicit unheard binding before dispatch')
        error = turning.exception()
        self.assertEqual(type(error).__name__, 'BackendControlChanged')
        self.assertTrue(error.body_closed)
        self.assertIs(error.owner, self.dialog.backend_owner)
        self.assertEqual(error.input_control.control_uid, 'genuine-boolean-9')


if __name__ == '__main__':
    unittest.main()
