"""Offline synchronous START contract through real Bridge and loopback HTTP."""
import asyncio
import copy
import unittest
from unittest.mock import patch

from aiohttp import ClientTimeout

from aiohttp import web
from aiohttp.test_utils import TestServer

import test_voice_created_lifecycle as lifecycle


class SynchronousStartTests(unittest.IsolatedAsyncioTestCase):
    spawn = lifecycle.CreatedLifecycleTests.spawn
    wait_for_sent = lifecycle.CreatedLifecycleTests.wait_for_sent
    callback = lifecycle.CreatedLifecycleTests.callback
    begin_create = lifecycle.CreatedLifecycleTests.begin_create
    create_confirmed = lifecycle.CreatedLifecycleTests.create_confirmed
    asyncTearDown = lifecycle.CreatedLifecycleTests.asyncTearDown

    async def asyncSetUp(self):
        await lifecycle.CreatedLifecycleTests.asyncSetUp(self)
        await self.bot.close()
        self.reply = None
        self.reply_status = 200
        self.raw_reply = None
        self.start_received = asyncio.Event()
        self.callback_body = None
        self.wrapped = False

        async def receive(request):
            payload = await request.json()
            self.sent.append(payload)
            if payload.get('action') != 'START_CREATED_CONVERSATION':
                return web.json_response({'status': 'success'})
            self.start_received.set()
            self.start_payload = payload
            self.output = self.envelope(payload, self.callback_body or self.picker())
            await self.start_ack_gate.wait()
            if self.raw_reply is not None:
                return web.Response(body=self.raw_reply, status=self.reply_status)
            content = self.reply(copy.deepcopy(self.output)) if self.reply else self.output
            return web.json_response({'result': content} if self.wrapped else content,
                                     status=self.reply_status)

        app = web.Application()
        app.router.add_post('/bot', receive)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge.bot_url = str(self.bot.make_url('/bot'))

    @staticmethod
    def picker():
        return [{'uiType': 'TopicPickerControl', 'label': 'Choose support.',
                 'options': [{'label': 'Support', 'value': 'support'}]}]

    @staticmethod
    def envelope(payload, body):
        return {'requestId': payload['requestId'], 'userId': payload['userId'],
                'clientSessionId': payload['clientSessionId'],
                'appInboundId': payload['appInboundId'], 'body': body}

    @property
    def session(self):
        return next(iter(self.bridge.sessions.values()))

    async def start(self, gated=False):
        if gated:
            self.start_ack_gate.clear()
        opening, creation = await self.begin_create()
        startup = await self.create_confirmed(opening, creation)
        await asyncio.wait_for(self.start_received.wait(), 2)
        return opening, startup

    async def settled(self):
        for _ in range(200):
            if not self.bridge.bootstrap_tasks:
                return
            await asyncio.sleep(.005)
        self.fail('START did not settle')

    async def post_output(self, output, authorization='Bearer fixture-callback', status=200):
        response = await self.callbacks.post('/callback', json=output,
                                            headers={'Authorization': authorization})
        self.assertEqual(response.status, status)
        await response.read()

    async def assert_ready(self, opening, startup):
        await self.settled()
        self.assertFalse(self.session.failed, 'Valid synchronous controls must not fail startup')
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        self.assertFalse(self.session.busy)
        self.assertEqual(self.session.input_boundary_request_id, startup['requestId'])
        self.assertEqual(self.session.input_boundary_kind, 'TopicPickerControl')
        self.assertEqual(self.session.choices, [{'label': 'Support', 'value': 'support'}])
        self.assertEqual(self.session.input_label, 'Choose support.')
        self.assertEqual(len(self.sent), 2)

    async def test_direct_content_without_status_establishes_offered_boundary_once(self):
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)
        self.assertIs(startup.get('syncResponse'), True)
        cursor = self.session.sequence
        await self.post_output(self.output)
        self.assertEqual(self.session.sequence, cursor)

    async def test_result_content_without_status_establishes_offered_boundary_once(self):
        self.wrapped = True
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)
        self.assertIs(startup.get('syncResponse'), True)
        cursor = self.session.sequence
        await self.post_output(self.output)
        self.assertEqual(self.session.sequence, cursor)

    async def test_early_callback_and_wrapped_http_share_dedup_until_success(self):
        self.wrapped = True
        opening, startup = await self.start(gated=True)
        await self.post_output(self.output)
        cursor = self.session.sequence
        self.assertTrue(self.session.busy)
        self.assertFalse(opening.done())
        self.start_ack_gate.set()
        await self.assert_ready(opening, startup)
        self.assertEqual(self.session.sequence, cursor + 1)
        self.assertEqual(len(self.session.fingerprints), 2)  # CREATE plus one START

    async def test_optional_field_variation_is_idempotent_and_speech_suppressed(self):
        self.callback_body = self.picker() + [{'uiType': 'OutputText', 'value': 'Private greeting.'}]
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)
        cursor = self.session.sequence
        output = dict(self.output)
        del output['appInboundId']
        await self.post_output(output)
        self.assertEqual(self.session.sequence, cursor)
        self.assertFalse(self.session.events)

    async def test_empty_success_waits_for_actual_callback(self):
        self.reply = lambda output: {'status': 'success'}
        opening, startup = await self.start()
        await self.settled()
        self.assertFalse(self.session.failed)
        self.assertTrue(self.session.busy)
        self.assertFalse(self.session.input_boundary_request_id)
        await self.post_output(self.output)
        await self.assert_ready(opening, startup)

    async def test_wrapped_empty_success_waits_for_actual_callback(self):
        self.wrapped = True
        await self.test_empty_success_waits_for_actual_callback()

    async def test_markers_and_stream_end_do_not_release_input(self):
        self.callback_body = [{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}]
        self.reply = lambda output: dict(output, streamState='END', streamActive=False)
        opening, startup = await self.start()
        await self.settled()
        self.assertFalse(self.session.failed)
        self.assertTrue(self.session.busy)
        self.assertFalse(opening.done())
        await self.callback(startup, self.picker())
        await self.assert_ready(opening, startup)

    async def test_http_failure_overrides_early_input_callback_and_preserves_end(self):
        self.reply_status = 502
        opening, startup = await self.start(gated=True)
        owned = self.session
        binding = owned.conversation_binding
        await self.post_output(self.output)
        self.assertTrue(owned.busy)
        self.start_ack_gate.set()
        await self.settled()
        self.assertTrue(owned.failed, 'Invalid START response must fail before publishing readiness')
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        self.assertEqual(owned.conversation_binding, binding)
        await self.dialog.close()
        self.assertEqual([p.get('action') for p in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', 'END_CONVERSATION'])
        self.assertNotIn('syncResponse', self.sent[-1])

    async def test_end_during_http_wait_fences_late_content(self):
        opening, startup = await self.start(gated=True)
        owned = self.session
        ending = self.spawn(self.dialog.close())
        for _ in range(200):
            if owned.ending:
                break
            await asyncio.sleep(.005)
        self.assertTrue(owned.ending)
        self.start_ack_gate.set()
        await asyncio.wait_for(ending, 2)
        self.assertFalse(owned.bootstrap_input_ready)
        self.assertFalse(owned.input_boundary_request_id)
        self.assertFalse(owned.choices)
        self.assertFalse(self.bridge.sessions)
        self.assertEqual([p.get('action') for p in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', 'END_CONVERSATION'])

    async def test_cancelled_start_never_reopens_on_late_http(self):
        opening, startup = await self.start(gated=True)
        owned = self.session
        task = next(iter(self.bridge.bootstrap_tasks))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.start_ack_gate.set()
        await asyncio.sleep(.02)
        self.assertTrue(owned.failed)
        self.assertFalse(owned.bootstrap_input_ready)
        self.assertFalse(owned.input_boundary_request_id)
        await self.dialog.close()
        self.assertFalse(self.bridge.sessions)

    async def test_ordinary_turn_remains_async_and_stale_start_cannot_mutate_it(self):
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)
        turning = self.spawn(self.dialog.turn('Synthetic fixture turn.'))
        await self.wait_for_sent(3, turning)
        ordinary = self.sent[-1]
        self.assertNotIn('syncResponse', ordinary)
        self.assertNotIn('action', ordinary)
        self.assertTrue(self.session.busy)
        await self.post_output(self.output)
        self.assertTrue(self.session.busy)
        await self.callback(ordinary, [{'uiType': 'OutputText', 'value': 'Fixture answer.'},
                                      {'uiType': 'InputText'}])
        self.assertEqual(await asyncio.wait_for(turning, 2), ['Fixture answer.'])
        self.assertNotIn('syncResponse', self.sent[0])

    async def test_callback_authentication_still_required(self):
        opening, startup = await self.start(gated=True)
        await self.post_output(self.output, authorization='Bearer incorrect', status=401)
        self.assertFalse(self.session.bootstrap_input_ready)
        self.start_ack_gate.set()
        await self.assert_ready(opening, startup)

    async def test_optional_routing_fields_may_be_absent(self):
        self.reply = lambda o: {k: v for k, v in o.items()
                                if k not in ('clientSessionId', 'appInboundId')}
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)

    async def test_success_status_with_content_is_accepted(self):
        self.reply = lambda o: dict(o, status='success')
        opening, startup = await self.start()
        await self.assert_ready(opening, startup)

    async def test_real_now_session_is_forwarded_without_substitution(self):
        self.start_ack_gate.clear()
        opening, creation = await self.begin_create()
        self.session.now_session = 'genuine-native-session-from-create'
        startup = await self.create_confirmed(opening, creation)
        self.assertEqual(startup['nowSessionId'], 'genuine-native-session-from-create')
        self.start_ack_gate.set()
        await self.assert_ready(opening, startup)
        self.assertEqual(self.session.now_session, 'genuine-native-session-from-create')

    async def test_invalid_json_preserves_owned_end(self):
        self.raw_reply = b'not JSON'
        await self.assert_rejected(None)

    async def test_oversized_response_preserves_owned_end(self):
        self.raw_reply = b'x' * 65537
        await self.assert_rejected(None)

    async def test_timeout_preserves_owned_end_and_never_retries(self):
        # Shorten only the local transport deadline; all HTTP remains real.
        with patch('voice.bridge.ClientTimeout', side_effect=lambda **kw: ClientTimeout(total=.05)):
            opening, startup = await self.start(gated=True)
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(opening, 2)
        self.assertTrue(self.session.failed)
        self.assertFalse(self.session.bootstrap_input_ready)
        self.start_ack_gate.set()
        await self.dialog.close()
        self.assertEqual([p.get('action') for p in self.sent],
                         ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', 'END_CONVERSATION'])

    async def test_secure_response_uses_existing_failure_state(self):
        self.callback_body = [{'uiType': 'InputText', 'maskType': 'SECURE'}]
        opening, startup = await self.start()
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        self.assertTrue(self.session.failed)
        cursor = self.session.sequence
        await self.post_output(self.output)
        self.assertEqual(self.session.sequence, cursor)
        self.assertFalse(self.session.input_boundary_request_id)

    async def test_terminal_response_never_releases_input(self):
        self.reply = lambda o: dict(o, completed=True)
        opening, startup = await self.start()
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        self.assertTrue(self.session.ended)
        self.assertFalse(self.session.choices)
        cursor = self.session.sequence
        await self.post_output(self.output)
        self.assertEqual(self.session.sequence, cursor)

    async def assert_rejected(self, transform):
        self.reply = transform
        opening, startup = await self.start()
        owned = self.session
        binding = owned.conversation_binding
        await self.settled()
        self.assertTrue(owned.failed, 'Invalid START response must fail before publishing readiness')
        with self.assertRaises(RuntimeError):
            await asyncio.wait_for(opening, 2)
        self.assertFalse(owned.bootstrap_input_ready)
        self.assertFalse(owned.input_boundary_request_id)
        self.assertFalse(owned.choices)
        self.assertEqual(owned.conversation_binding, binding)
        self.assertEqual(len(self.sent), 2)
        await self.dialog.close()
        self.assertFalse(self.bridge.sessions)
        self.assertEqual(self.sent[-1]['action'], 'END_CONVERSATION')


def rejection_case(transform):
    async def test(self):
        await self.assert_rejected(transform)
    return test


for name, transform in {
    'wrong_request': lambda o: dict(o, requestId='stale-request'),
    'missing_request': lambda o: {k: v for k, v in o.items() if k != 'requestId'},
    'wrong_user': lambda o: dict(o, userId='other-user'),
    'missing_user': lambda o: {k: v for k, v in o.items() if k != 'userId'},
    'wrong_session': lambda o: dict(o, clientSessionId='other-session'),
    'wrong_app': lambda o: dict(o, appInboundId='other-app'),
    'malformed_body': lambda o: dict(o, body={}),
    'malformed_control': lambda o: dict(o, body=[None]),
    'missing_control_type': lambda o: dict(o, body=[{}]),
    'empty_error_with_content': lambda o: dict(o, error={}),
    'empty_errors_with_content': lambda o: dict(o, errors=[]),
    'invalid_option_entry': lambda o: dict(o, body=[{'uiType': 'Picker', 'options': [None]}]),
    'invalid_topic_metadata': lambda o: dict(o, body=[{'uiType': 'TopicPickerControl', 'uiMetadata': []}]),
    'invalid_options': lambda o: dict(o, body=[{'uiType': 'Picker', 'options': {}}]),
    'failure_status': lambda o: dict(o, status='failure'),
    'error_with_success': lambda o: dict(o, status='success', error={'message': 'fixture'}),
    'contradictory_outer_status': lambda o: {'status': 'failure', 'result': o},
    'contradictory_inner_status': lambda o: {'status': 'success', 'result': dict(o, status='failure')},
    'internal_builder_structure': lambda o: {'status': 200, 'content': o},
    'bodyless_content': lambda o: {k: v for k, v in dict(o, status='success').items() if k != 'body'},
    'conversation_conflict': lambda o: dict(o, body=[{'uiType': 'ActionMsg',
        'actionType': 'StartConversation', 'conversationId': 'd'*32}]),
    'interaction_conflict': lambda o: dict(o, body=[{'uiType': 'ActionMsg',
        'actionType': 'StartConversation', 'interactionId': 'd'*32}]),
    'unexpected_create': lambda o: dict(o, body=[{'uiType': 'ActionMsg',
        'actionType': 'CreateConversation', 'conversationId': 'd'*32, 'messageId': 'e'*32}]),
}.items():
    setattr(SynchronousStartTests, 'test_reject_' + name, rejection_case(transform))


def input_case(kind):
    async def test(self):
        self.callback_body = [{'uiType': kind}]
        opening, startup = await self.start()
        await self.settled()
        self.assertFalse(self.session.failed)
        self.assertEqual(await asyncio.wait_for(opening, 2), [])
        self.assertFalse(self.session.busy)
        self.assertEqual(self.session.input_boundary_request_id, startup['requestId'])
        self.assertEqual(self.session.input_boundary_kind, kind)
    return test


for kind in ('InputText', 'Picker', 'Boolean', 'Date', 'DateTime', 'Time'):
    setattr(SynchronousStartTests, 'test_input_boundary_' + kind.lower(), input_case(kind))


if __name__ == '__main__':
    unittest.main()
