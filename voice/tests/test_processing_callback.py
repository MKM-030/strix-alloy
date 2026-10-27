import unittest
from voice.tests.test_bridge import BridgeTests


class ProcessingCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = BridgeTests(methodName='runTest')
        await self.fixture.asyncSetUp()

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def test_authenticated_streaming_progress_wakes_existing_events_cursor(self):
        f = self.fixture
        await f.post('/api/start', {})
        await f.callback(streamState='INPROGRESS', body=[{
            'uiType': 'ActionMsg', 'actionType': 'DynamicLoader',
            'progressMessages': [{'message': 'Die Angaben werden geprüft.', 'status': 'COMPLETED'}]}])
        response = await f.ui.get('/api/events?wait=0')
        value = await response.json()
        self.assertTrue(value['busy'])
        self.assertGreater(value['cursor'], 0)
        self.assertEqual(value['processing']['messages'], ['Die Angaben werden geprüft.'])
        self.assertFalse(value['processing']['agentCompletionKnown'])
        self.assertEqual(value['events'], [])
        self.assertEqual(len(f.requests), 1)


if __name__ == '__main__':
    unittest.main()
