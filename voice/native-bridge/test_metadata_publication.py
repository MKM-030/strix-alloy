"""Offline CREATE/datachannel ordering regressions; no media, model or ServiceNow."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiortc import RTCConfiguration
from native_bridge import Config, Dialog, NativeCall
from native_duplex import NativeDuplex


METADATA = dict(conversation_id='a' * 32, interaction_id='b' * 32,
                creation_message_id='c' * 32, create_request_id='d' * 32)
BINDING = dict(source='servicenow_create_conversation', conversationId='a' * 32,
               interactionId='b' * 32, creationMessageId='c' * 32, createRequestId='d' * 32)


class Channel:
    label = 'transcripts'

    def __init__(self, state='connecting'):
        self.readyState = state
        self.handlers = {}
        self.messages = []
        self.fail_next_send = False

    def on(self, name, handler):
        self.handlers[name] = handler

    def send(self, message):
        if self.fail_next_send:
            self.fail_next_send = False
            raise RuntimeError('synthetic channel send failure')
        self.messages.append(json.loads(message))

    def open(self):
        self.readyState = 'open'
        self.handlers['open']()

    def close(self):
        self.readyState = 'closed'

    @property
    def metadata(self):
        return [m['data'] for m in self.messages if m['type'] == 'metadata']


class MetadataPublicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.call, self.lane = self.make_call()

    def make_call(self):
        config = Config(greeting='')
        dialog = Dialog(config)
        with patch('native_bridge.RTCConfiguration',
                   side_effect=lambda **kw: RTCConfiguration(iceServers=[])):
            call = NativeCall(config, SimpleNamespace(), dialog)
        async def no_model(*args):
            raise AssertionError('Metadata publication must not invoke a model')
        lane = NativeDuplex(call, conversation_factory=no_model)
        self.calls.append(call)
        return call, lane

    async def asyncTearDown(self):
        for call in self.calls:
            await call.peer.close()

    def authoritative_binding(self, call=None):
        (call or self.call).dialog.observe_state({'conversationBinding': dict(BINDING)})

    def settle(self, lane=None, *, result=None, error=None):
        opening = asyncio.get_running_loop().create_future()
        if error is not None:
            opening.set_exception(error)
        else:
            opening.set_result([] if result is None else result)
        lane = lane or self.lane
        lane._bootstrap_state = 'pending'
        lane._settle_bootstrap(opening)

    def channel(self, *, state='connecting', call=None):
        channel = Channel(state)
        (call or self.call).datachannel(channel)
        return channel

    async def test_open_before_create_publishes_when_bootstrap_settles(self):
        channel = self.channel(state='open')
        self.assertEqual(channel.metadata, [])
        self.authoritative_binding()
        self.settle()
        self.assertEqual(channel.metadata, [METADATA])
        self.assertEqual(self.lane._bootstrap_state, 'ready')

    async def test_closed_call_with_still_open_channel_does_not_publish_ready_metadata(self):
        channel = self.channel(state='open')
        self.authoritative_binding()
        self.call.closed = True
        self.settle()
        channel.open()
        self.assertEqual(channel.metadata, [])

    async def test_ready_before_open_publishes_once_without_using_backlog(self):
        channel = self.channel()
        self.authoritative_binding()
        self.settle()
        self.assertEqual(channel.messages, [])
        self.assertEqual(self.call.pending_events, [])
        channel.open()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])

    async def test_tuple_available_at_open_is_not_repeated_at_ready(self):
        self.authoritative_binding()
        channel = self.channel(state='open')
        self.settle()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])

    async def test_repeated_open_events_do_not_duplicate_metadata(self):
        self.authoritative_binding()
        channel = self.channel()
        channel.open()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])

    async def test_each_missing_id_is_suppressed_until_complete_authoritative_tuple(self):
        for missing in METADATA:
            with self.subTest(missing=missing):
                call, lane = self.make_call()
                call.dialog.metadata = dict(METADATA, **{missing: ''})
                channel = self.channel(state='open', call=call)
                self.assertEqual(channel.metadata, [])
                # Restore an empty Dialog scope before its authoritative observation.
                call.dialog.metadata = {key: '' for key in METADATA}
                self.authoritative_binding(call)
                self.settle(lane)
                self.assertEqual(channel.metadata, [METADATA])

    async def test_extra_fields_or_noncanonical_ids_are_not_published(self):
        invalid = [dict(METADATA, extra='unrelated'), list(METADATA), None,
                   dict(METADATA, conversation_id='A' * 32),
                   dict(METADATA, interaction_id='b' * 31),
                   dict(METADATA, creation_message_id=123),
                   dict(METADATA, create_request_id='d' * 31 + '\n'),
                   dict(METADATA, conversation_id='\u212a' * 32)]
        for metadata in invalid:
            with self.subTest(metadata=metadata):
                call, lane = self.make_call()
                call.dialog.metadata = metadata
                channel = self.channel(state='open', call=call)
                self.settle(lane)
                self.assertEqual(channel.metadata, [])

    async def test_wrong_source_observation_never_creates_metadata(self):
        channel = self.channel(state='open')
        self.call.dialog.observe_state({'conversationBinding': dict(BINDING, source='planner_text')})
        self.settle()
        self.assertEqual(channel.metadata, [])

    async def test_full_backlog_cannot_drop_late_metadata(self):
        channel = self.channel()
        for number in range(30):
            self.call.emit('transcript', {'number': number})
        self.authoritative_binding()
        self.settle()
        self.assertEqual(len(self.call.pending_events), 30)
        channel.open()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])
        self.assertEqual([m['data']['number'] for m in channel.messages if m['type'] == 'transcript'],
                         list(range(30)))
        self.assertEqual(self.call.pending_events, [])

    async def test_emission_uses_detached_existing_four_field_contract(self):
        channel = self.channel(state='open')
        self.authoritative_binding()
        with patch.object(self.call, 'emit', wraps=self.call.emit) as emit:
            self.settle()
        metadata = [args.args[1] for args in emit.call_args_list if args.args[0] == 'metadata']
        self.assertEqual(metadata, [METADATA])
        self.assertIsNot(metadata[0], self.call.dialog.metadata)
        self.assertEqual(channel.metadata, [METADATA])
        self.assertEqual(self.lane._context_snapshot, '')
        self.assertEqual(list(self.lane._outputs), [])
        self.assertEqual(self.call.turn_contexts, {})
        self.assertEqual(self.call.dialog.public_replies, [])

    async def test_send_failure_does_not_abort_ready_or_mark_as_published(self):
        channel = self.channel(state='open')
        self.authoritative_binding()
        channel.fail_next_send = True
        with self.assertLogs('native-voice', level='WARNING') as messages:
            self.settle()
        self.assertIn('stage=metadata_send_failed type=RuntimeError', messages.output[0])
        self.assertNotIn(METADATA['conversation_id'], messages.output[0])
        self.assertEqual(self.lane._bootstrap_state, 'ready')
        self.assertEqual(channel.metadata, [])
        channel.open()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])

    async def test_failed_bootstrap_does_not_publish_ready_metadata(self):
        channel = self.channel(state='open')
        self.authoritative_binding()
        with self.assertLogs('native-voice', level='WARNING'):
            self.settle(error=RuntimeError('synthetic startup failure'))
        self.assertEqual(channel.metadata, [])
        self.assertEqual(self.lane._bootstrap_state, 'failed')

    async def test_invalid_bootstrap_result_does_not_publish_ready_metadata(self):
        channel = self.channel(state='open')
        self.authoritative_binding()
        with self.assertLogs('native-voice', level='WARNING'):
            self.settle(result={'not': 'a valid startup reply list'})
        self.assertEqual(channel.metadata, [])
        self.assertEqual(self.lane._bootstrap_state, 'failed')

    async def test_same_tuple_is_published_independently_for_each_owned_call(self):
        other, other_lane = self.make_call()
        channels = [self.channel(state='open'), self.channel(state='open', call=other)]
        self.authoritative_binding()
        self.authoritative_binding(other)
        self.settle()
        self.settle(other_lane)
        self.assertEqual([channel.metadata for channel in channels], [[METADATA], [METADATA]])

    async def test_published_call_does_not_replace_first_tuple(self):
        self.authoritative_binding()
        channel = self.channel(state='open')
        self.call.dialog.metadata = dict(METADATA, conversation_id='f' * 32)
        self.settle()
        channel.open()
        self.assertEqual(channel.metadata, [METADATA])


if __name__ == '__main__':
    unittest.main()
