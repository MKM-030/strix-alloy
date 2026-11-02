"""Native introduction overlaps one owned VA bootstrap without becoming a task question."""
import asyncio
import unittest
from unittest.mock import patch

from aiortc import RTCConfiguration
from assistant_settings import CallSettings
from native_bridge import Config, NativeCall
from native_duplex import NativeDuplex
from test_assistant_settings import authorized_settings, SERVICE, AGENT
import test_voice_created_lifecycle as created_fixture


TOPIC = 'e34d0bc393b38354e7f2b9fa6aba10fb'
INTRODUCTION = 'Guten Tag. Deutsch bitte.'
QUESTION = 'Wie lautet der Name des Mitarbeiters?'


class CapturingSpeech:
    def __init__(self):
        self.spoken = []
        self.finished = []
        self.release = asyncio.Event()
        self.release.set()

    async def synthesize(self, text):
        self.spoken.append(text)
        yield bytes(480)
        await self.release.wait()
        self.finished.append(text)

    async def transcribe(self, pcm):
        raise AssertionError('The startup test supplies no microphone audio')


async def until(case, predicate, message):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(.005)
    case.assertTrue(predicate(), message)


def make_call(config, speech, dialog, settings, *, duplex=False):
    with patch('native_bridge.RTCConfiguration', side_effect=lambda **kw: RTCConfiguration(iceServers=[])):
        call = NativeCall(config, speech, dialog, settings)
    if duplex:
        async def no_model(*args):
            raise AssertionError('Startup must not invoke the conversational model')
        call.duplex = NativeDuplex(call, conversation_factory=no_model)
    return call


class NativeTopicStartupTests(unittest.IsolatedAsyncioTestCase):
    # Exercise the real Bridge HTTP/callback state machine, using only its Bot fixture.
    asyncSetUp = created_fixture.CreatedLifecycleTests.asyncSetUp
    asyncTearDown = created_fixture.CreatedLifecycleTests.asyncTearDown
    spawn = created_fixture.CreatedLifecycleTests.spawn
    wait_for_sent = created_fixture.CreatedLifecycleTests.wait_for_sent
    callback = created_fixture.CreatedLifecycleTests.callback
    create_confirmed = created_fixture.CreatedLifecycleTests.create_confirmed

    def call(self):
        self.dialog.config.initial_topic_id = TOPIC
        speech = CapturingSpeech()
        call = make_call(Config(backend_url=self.bridge.origin, greeting='Unused host introduction.'),
                         speech, self.dialog, self.call_settings, duplex=True)
        processing = call.spawn(call.process_turns())
        self.tasks.append(processing)
        return call, speech, processing

    async def complete_topic(self, processing):
        await self.wait_for_sent(1, processing)
        creation = self.sent[0]
        self.assertEqual(creation['action'], 'CREATE_CONVERSATION')
        startup = await self.create_confirmed(processing, creation)
        await self.callback(startup, [dict(uiType='TopicPickerControl', uiMetadata=dict(
            categories=[dict(options=[dict(label='SCC Laptop Onboarding', value=TOPIC)])]))])
        await self.wait_for_sent(3, processing)
        selection = self.sent[2]
        self.assertEqual(selection['message']['text'], TOPIC)
        self.assertIs(selection['message']['typed'], False)
        self.assertNotIn('history', creation)
        self.assertNotIn('history', startup)
        self.assertNotIn('history', selection)
        await self.callback(selection, [dict(uiType='InputText', label=QUESTION)])
        return selection

    async def test_native_introduction_is_emitted_before_delayed_create_ack(self):
        self.create_ack_gate.clear()
        call, speech, processing = self.call()
        try:
            await self.wait_for_sent(1, processing)
            await until(self, lambda: bool(speech.finished),
                        'The authoritative introduction must not wait for VA bootstrap')
            self.assertEqual(speech.spoken, [INTRODUCTION])
            self.assertEqual([event['data']['content'] for event in call.pending_events
                              if event['type'] == 'transcript'], [INTRODUCTION])
            self.assertGreater(call.playback.accepted_samples, 0)
            self.assertEqual(len(self.sent), 1, 'No topic/business turn may precede CREATE readiness')
            self.assertFalse(processing.done())
            call.playback.read(len(call.playback.data))
            self.create_ack_gate.set()
            await self.complete_topic(processing)
            await until(self, lambda: QUESTION in speech.finished, 'The real question must follow startup')
            self.assertEqual(speech.spoken, [INTRODUCTION, QUESTION])
            self.assertEqual([item.get('action') for item in self.sent],
                             ['CREATE_CONVERSATION', 'START_CREATED_CONVERSATION', None])
        finally:
            self.create_ack_gate.set()
            await asyncio.wait_for(call.close(), 2)

    async def test_topic_question_retains_actual_input_control_binding(self):
        call, speech, processing = self.call()
        try:
            await until(self, lambda: INTRODUCTION in speech.finished,
                        'The native introduction must finish before the next speaker')
            # The real RTC SpeakerTrack drains these samples. This fixture has
            # no media sender, so consume them before waiting for its successor.
            call.playback.read(len(call.playback.data))
            selection = await self.complete_topic(processing)
            await until(self, lambda: QUESTION in speech.finished, 'The real question must be spoken')
            call.playback.read(len(call.playback.data))
            question, source, complete = call.duplex.question_context()
            self.assertEqual((question, source, complete),
                             (QUESTION, 'servicenow_input_control', True))
            self.assertEqual(call.duplex._spoken_question['binding'], selection['requestId'])
            self.assertEqual(speech.spoken, [INTRODUCTION, QUESTION])
            self.assertEqual(self.dialog.greeting_history, [])
        finally:
            await asyncio.wait_for(call.close(), 2)


class GatedDialog:
    metadata = {}
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.settled = asyncio.Event()
        self.opens = 0
        self.closes = 0

    async def open(self):
        self.opens += 1
        self.started.set()
        try:
            await self.release.wait()
            return [QUESTION]
        finally:
            self.settled.set()

    async def close(self):
        self.closes += 1

    def record_greeting(self, text):
        raise AssertionError('Profile-bound native startup must not inject greeting history')


class NativeStartupOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def call(self):
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        dialog, speech = GatedDialog(), CapturingSpeech()
        call = make_call(Config(), speech, dialog, settings)
        processing = call.spawn(call.process_turns())
        return call, speech, dialog, processing

    async def test_close_cancels_one_pending_bootstrap_and_cannot_leak_into_next_call(self):
        call, speech, dialog, processing = self.call()
        await asyncio.wait_for(dialog.started.wait(), 1)
        await asyncio.wait_for(call.close(), 1)
        self.assertTrue(dialog.settled.is_set(), 'The separate bootstrap must be drained by close')
        self.assertTrue(processing.done())
        self.assertEqual((dialog.opens, dialog.closes), (1, 1))
        prior_events = list(call.pending_events)
        dialog.release.set()
        fresh, next_speech, next_dialog, _ = self.call()
        try:
            await until(self, lambda: bool(next_speech.finished), 'The fresh call needs its own introduction')
            self.assertEqual(next_speech.spoken, [INTRODUCTION])
            self.assertEqual(call.pending_events, prior_events)
            self.assertNotIn(QUESTION, speech.spoken)
            self.assertEqual(next_dialog.opens, 1)
        finally:
            await asyncio.wait_for(fresh.close(), 1)

    async def test_barge_in_during_introduction_does_not_release_stale_startup_audio(self):
        call, speech, dialog, _ = self.call()
        speech.release.clear()
        try:
            await until(self, lambda: bool(speech.spoken), 'Native introduction should start during bootstrap')
            call.input_started = True
            call.playback.interrupt()
            speech.release.set()
            dialog.release.set()
            await asyncio.wait_for(dialog.settled.wait(), 1)
            await asyncio.sleep(.02)
            self.assertEqual(speech.spoken, [INTRODUCTION])
            self.assertEqual(len(call.playback.data), 0)
            self.assertEqual(dialog.opens, 1)
        finally:
            speech.release.set()
            await asyncio.wait_for(call.close(), 1)

    async def test_input_before_startup_suppresses_introduction_and_late_question_audio(self):
        call, speech, dialog, _ = self.call()
        call.input_started = True
        call.playback.interrupt()
        try:
            await asyncio.wait_for(dialog.started.wait(), 1)
            dialog.release.set()
            await asyncio.wait_for(dialog.settled.wait(), 1)
            await asyncio.sleep(.02)
            self.assertEqual(speech.spoken, [])
            self.assertEqual(len(call.playback.data), 0)
            self.assertEqual(dialog.opens, 1)
        finally:
            await asyncio.wait_for(call.close(), 1)


if __name__ == '__main__':
    unittest.main()
