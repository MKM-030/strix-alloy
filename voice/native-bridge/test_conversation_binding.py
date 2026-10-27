"""One offline callback/HTTP binding check; no live ServiceNow or model calls."""
import asyncio
import unittest

import test_voice_created_lifecycle as fixtures
from native_bridge import Config, Dialog


class ConversationBindingTests(unittest.IsolatedAsyncioTestCase):
    # Reuse only the local transport fixture, not its unrelated lifecycle tests.
    asyncSetUp = fixtures.CreatedLifecycleTests.asyncSetUp
    asyncTearDown = fixtures.CreatedLifecycleTests.asyncTearDown
    spawn = fixtures.CreatedLifecycleTests.spawn
    wait_for_sent = fixtures.CreatedLifecycleTests.wait_for_sent
    callback = fixtures.CreatedLifecycleTests.callback
    begin_create = fixtures.CreatedLifecycleTests.begin_create

    async def test_private_create_binding_and_reset_isolation(self):
        opening, creation = await self.begin_create()
        control = {'uiType': 'ActionMsg', 'actionType': 'CreateConversation',
            'conversationId': 'a' * 32, 'messageId': 'b' * 32, 'interactionId': 'c' * 32}

        async def readback():
            state = await self.dialog.request('GET', '/api/events', params={'wait': '0'})
            self.dialog.observe_state(state)
            return state

        await self.callback(creation, [control], requestId='d' * 32)
        await self.callback(creation, [control], clientSessionId='e' * 32)
        await self.callback(creation, [control], userId='wrong-user', expected_status=400)
        await self.callback(creation, [control], userId=None)
        self.assertNotIn('conversationBinding', await readback())
        # The missing identity keeps normal CREATE handling intact; use a fresh
        # owned cookie for the exact binding path instead of replaying CREATE.
        await self.wait_for_sent(2, opening)
        await self.callback(self.sent[-1], [{'uiType': 'InputText'}])
        await asyncio.wait_for(opening, 2)
        await self.dialog.close()
        self.assertFalse(any(self.dialog.metadata.values()))
        self.sent.clear()

        for malformed in (dict(control, messageId='NOT-A-SYS-ID'),
                          dict(control, conversationId=7), dict(control, interactionId='INVALID')):
            opening, creation = await self.begin_create()
            await self.callback(creation, [malformed])
            await self.wait_for_sent(2, opening)
            await self.callback(self.sent[-1], [{'uiType': 'InputText'}])
            self.assertEqual(await asyncio.wait_for(opening, 2), [])
            self.assertNotIn('conversationBinding', await readback())
            await self.dialog.close()
            self.sent.clear()

        opening, creation = await self.begin_create()
        await self.callback(creation, [control], streamActive=True)
        self.assertNotIn('conversationBinding', await readback())
        await self.callback(creation, [control], nowSessionId='separate-opaque-session')
        await self.wait_for_sent(2, opening)
        startup = self.sent[-1]
        await self.callback(startup, [{'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        state = await readback()
        binding = {'source': 'servicenow_create_conversation', 'conversationId': 'a' * 32,
            'creationMessageId': 'b' * 32, 'createRequestId': creation['requestId'],
            'interactionId': 'c' * 32}
        self.assertEqual(state['conversationBinding'], binding)
        self.assertEqual(self.dialog.metadata, {'conversation_id': 'a' * 32,
            'creation_message_id': 'b' * 32, 'create_request_id': creation['requestId'],
            'interaction_id': 'c' * 32})
        self.assertEqual(startup['nowSessionId'], 'separate-opaque-session')
        self.assertNotEqual(startup['requestId'], binding['createRequestId'])
        self.assertEqual(state['events'], [])
        self.assertEqual(self.dialog.public_replies, [])

        await self.callback(startup, [dict(control, conversationId='f' * 32)], expected_status=400)
        self.assertEqual((await readback())['conversationBinding'], binding)
        for wrong in (dict(binding, source='untrusted'), dict(binding, conversationId=7)):
            self.dialog.observe_state({'conversationBinding': wrong})
        with self.assertRaisesRegex(RuntimeError, 'binding changed'):
            self.dialog.observe_state({'conversationBinding': dict(binding, conversationId='f' * 32)})
        self.assertEqual(self.dialog.metadata['conversation_id'], 'a' * 32)

        # A different cookie has no binding; reset creates an empty owned scope.
        other = Dialog(Config(backend_url=self.bridge.origin), self.call_settings)
        self.assertFalse(any(other.metadata.values()))
        await self.dialog.close()
        self.assertFalse(any(self.dialog.metadata.values()))
        info = await (await self.ui.get('/api/session')).json()
        self.assertNotIn('conversationBinding', await (await self.ui.get('/api/events?wait=0')).json())
        reset = await self.ui.post('/api/reset', json={}, headers={
            'Origin': self.bridge.origin, 'X-CSRF-Token': info['csrf']})
        self.assertEqual(reset.status, 200)
        self.assertNotIn('conversationBinding', await (await self.ui.get('/api/events?wait=0')).json())
        await self.callback(creation, [control])
        self.assertNotIn('conversationBinding', await (await self.ui.get('/api/events?wait=0')).json())
        await other.shutdown()


# This file intentionally runs exactly the one focused case above.
if __name__ == '__main__':
    unittest.main(defaultTest='ConversationBindingTests.test_private_create_binding_and_reset_isolation')
