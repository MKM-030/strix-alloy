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

    async def test_cleaned_dynamic_loader_projects_known_generic_without_business_output(self):
        f = self.fixture
        await f.post('/api/start', {})
        await f.callback(body=[{
            'uiType': 'ActionMsg', 'actionType': 'DynamicLoader',
            'progressMessages': [{'message': '<b>Checking on remaining steps.</b>'}]}])
        value = await (await f.ui.get('/api/events?wait=0')).json()
        self.assertEqual(value['processing']['messages'], ['Die Anfrage wird geprüft.'])
        self.assertTrue(value['busy'])
        self.assertEqual(value['events'], [])
        self.assertEqual(value['backendEvents'], [])
        self.assertEqual(len(f.requests), 1)

    async def test_same_text_in_authoritative_reply_and_input_controls_is_not_projected(self):
        f = self.fixture
        await f.post('/api/start', {})
        label = 'Checking on remaining steps.'
        for kind in ('OutputText', 'InputText', 'Boolean'):
            with self.subTest(kind=kind):
                control = {'uiType': kind, 'value' if kind == 'OutputText' else 'label': label}
                await f.callback(body=[control])
                value = await (await f.ui.get('/api/events?wait=0')).json()
                self.assertIsNone(value['processing'])
                self.assertEqual(value['events'][-1]['text'], label)
                self.assertEqual(value['backendEvents'][-1]['text'], label)
                self.assertEqual(value['backendEvents'][-1]['uiType'], kind)


if __name__ == '__main__':
    unittest.main()
