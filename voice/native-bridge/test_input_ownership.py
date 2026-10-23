import asyncio
from array import array
from fractions import Fraction
import unittest
from av import AudioFrame
from conversation_router import Route
import test_responsive_native as fixtures


class Track:
    kind = 'audio'
    def __init__(self):
        self.frames = asyncio.Queue()
        self.idle = asyncio.Event()
        self.offset = 0
    def feed(self, voiced=True, count=10):
        self.idle.clear()
        for _ in range(count):
            frame = AudioFrame(format='s16', layout='mono', samples=320)
            frame.planes[0].update(array('h', [2000 if voiced else 0] * 320).tobytes())
            frame.sample_rate, frame.pts = 16000, self.offset
            frame.time_base = Fraction(1, 16000)
            self.offset += 320
            self.frames.put_nowait(frame)
    async def recv(self):
        if self.frames.empty(): self.idle.set()
        frame = await self.frames.get()
        if isinstance(frame, Exception): raise frame
        return frame


class InputOwnershipTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.NativeResponsiveTests.asyncSetUp
    asyncTearDown = fixtures.NativeResponsiveTests.asyncTearDown
    attach = fixtures.NativeResponsiveTests.attach
    call = fixtures.NativeResponsiveTests.call
    start = fixtures.NativeResponsiveTests.start
    say = fixtures.NativeResponsiveTests.say
    transcripts = fixtures.NativeResponsiveTests.transcripts

    def backend_publication(self, call):
        published = asyncio.Event()
        publish = call.responsive_output.publish_deferred
        async def marked(event, validity):
            result = await publish(event, validity)
            published.set()
            return result
        call.responsive_output.publish_deferred = marked
        return published

    async def onset(self, call):
        track = Track()
        track.feed()
        worker = call.receive_track(track)
        await asyncio.wait_for(track.idle.wait(), 2)
        self.assertTrue(call.vad_active)
        return track, worker

    async def drain_scheduling(self):
        # Let the finite enqueue/publication/speech task chain run; no time delay.
        for _ in range(12): await asyncio.sleep(0)

    async def test_held_local_inference_is_invalidated_by_actual_silent_onset(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class HeldRouter:
            async def route(self, text, context):
                entered.set()
                await release.wait()
                return Route('clarification', reply='Old local answer')
        self.coordinator.router = HeldRouter()
        call = await self.start()
        call.turns.put_nowait((0, b'old question'))
        await asyncio.wait_for(entered.wait(), 2)
        await self.onset(call)
        release.set()
        await asyncio.wait_for(call.recognized_turns.join(), 2)
        await self.drain_scheduling()
        self.assertNotIn('Old local answer', self.speech.spoken)
        self.assertFalse(any(t['content'] == 'Old local answer' for t in self.transcripts(call)))
        self.assertEqual(call.playback.data, b'')

    async def test_backend_born_during_actual_input_waits_without_transcript(self):
        call = await self.start()
        await self.say(call, 'first request')
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        await call.responsive_output.wait_idle()
        call.playback.read(len(call.playback.data))
        await self.onset(call)
        published = self.backend_publication(call)
        self.dialog.release.set()
        await asyncio.wait_for(published.wait(), 2)
        await self.drain_scheduling()
        self.assertNotIn('Real backend reply?', self.speech.spoken)
        self.assertFalse(any(t['content'] == 'Real backend reply?' for t in self.transcripts(call)))
        task = self.store.list_tasks(call.call_id)[0]
        self.assertTrue(any(e['type'] == 'backend_observed' for e in self.store.events(task['task_id'], call.call_id)))

    async def endpoint(self, track):
        track.feed(False, 70)
        await asyncio.wait_for(track.idle.wait(), 2)

    async def test_late_old_reply_after_new_endpoint_asr_and_acceptance_is_suppressed(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Router:
            async def route(self, text, context):
                if text == 'old question':
                    entered.set()
                    await release.wait()
                    return Route('clarification', reply='Old local answer')
                return Route('clarification', reply='Current local answer')
        self.coordinator.router = Router()
        call = await self.start()
        call.turns.put_nowait((0, b'old question'))
        await entered.wait()
        async def transcribe(pcm): return 'current question'
        self.speech.transcribe = transcribe
        track, _ = await self.onset(call)
        await self.endpoint(track)
        await call.turns.join()
        self.assertEqual(call.recognized_turns.qsize(), 1)
        release.set()
        await asyncio.wait_for(call.recognized_turns.join(), 2)
        await call.responsive_output.wait_idle()
        self.assertEqual(self.speech.spoken, ['Current local answer'])
        self.assertTrue(any(t['content'] == 'old question' and t['role'] == 'user' for t in self.transcripts(call)))

    async def test_old_business_turn_is_accepted_without_restamping_its_speech(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Router:
            async def route(self, text, context):
                entered.set()
                await release.wait()
                return Route('new_task', agent_alias='desk')
        self.coordinator.router = Router()
        call = await self.start()
        call.turns.put_nowait((0, b'original business request'))
        await entered.wait()
        _, worker = await self.onset(call)
        release.set()
        await asyncio.wait_for(call.recognized_turns.join(), 2)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await self.drain_scheduling()
        await call.responsive_output.wait_idle()
        self.assertEqual([op['text'] for op in self.store.operations(call.call_id)], ['original business request'])
        self.assertEqual(self.speech.spoken, [])
        await self.dialog.started.wait()
        self.assertEqual(len(self.dialog.received), 1)

    async def test_microphone_origin_survives_overlapping_receiver_and_asr(self):
        from dataclasses import FrozenInstanceError
        from native_bridge import _InputEnvelope
        call = await self.start()
        call.asr_task.cancel()
        await asyncio.gather(call.asr_task, return_exceptions=True)
        first, one = await self.onset(call)
        second, two = await self.onset(call)
        self.assertEqual(call._input_epoch, 2)
        await self.endpoint(first)
        audio = call.turns.get_nowait()
        self.assertIsInstance(audio, _InputEnvelope)
        self.assertEqual(audio.input_epoch, 1)
        self.assertEqual(len(audio), 2)
        with self.assertRaises(FrozenInstanceError): audio.input_epoch = 2
        call.turns.task_done()
        # Retirement of the old receiver cannot clear a replacement's VAD.
        one.cancel()
        await asyncio.gather(one, return_exceptions=True)
        self.assertFalse(call._control_ready())
        call.turns.put_nowait(audio)
        recognized = asyncio.Event()
        async def transcribe(pcm):
            recognized.set()
            return 'older queued input'
        self.speech.transcribe = transcribe
        call.asr_task = call.spawn(call.recognize_turns())
        await recognized.wait()
        await call.turns.join()
        await call.recognized_turns.join()
        two.cancel()
        await asyncio.gather(two, return_exceptions=True)
        await self.drain_scheduling()
        await call.responsive_output.wait_idle()
        self.assertEqual([op['text'] for op in self.store.operations(call.call_id)], ['older queued input'])
        self.assertEqual(self.speech.spoken, [])

    async def deferred_backend(self):
        call = await self.start()
        await self.say(call, 'first request')
        await self.dialog.started.wait()
        await call.responsive_output.wait_idle()
        self.speech.spoken.clear()
        track, worker = await self.onset(call)
        published = self.backend_publication(call)
        self.dialog.release.set()
        await asyncio.wait_for(published.wait(), 2)
        await self.drain_scheduling()
        self.assertEqual(self.speech.spoken, [])
        self.assertEqual(call.responsive_output.pending_count, 1)
        return call, track, worker

    async def test_deferred_backend_survives_acceptance_and_speaks_once_after_asr_settles(self):
        call, track, worker = await self.deferred_backend()
        entered, release = asyncio.Event(), asyncio.Event()
        class Router:
            async def route(self, text, context):
                entered.set()
                await release.wait()
                return Route('clarification', reply='Current clarification')
        self.coordinator.router = Router()
        asr, asr_release = asyncio.Event(), asyncio.Event()
        async def transcribe(pcm):
            asr.set()
            await asr_release.wait()
            return 'current input'
        self.speech.transcribe = transcribe
        await self.endpoint(track)
        await asr.wait()
        self.assertFalse(call._input_ready())
        self.assertEqual(self.speech.spoken, [])
        asr_release.set()
        await entered.wait()
        self.assertFalse(call._input_ready())
        self.assertEqual(self.speech.spoken, [])
        release.set()
        await call.recognized_turns.join()
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken, ['Current clarification', 'Real backend reply?'])
        self.assertEqual(len(self.dialog.received), 1)
        self.assertFalse(self.dialog.cancelled)

    async def test_own_task_change_suppresses_deferred_but_retains_journal(self):
        call, track, worker = await self.deferred_backend()
        task = self.store.list_tasks(call.call_id)[0]
        self.store.accept(task['task_id'], call.call_id, 'next', 'changed request', kind='continue_task')
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken, [])
        self.assertTrue(any(e['type'] == 'backend_observed' for e in self.store.events(task['task_id'], call.call_id)))

    async def test_unrelated_focus_change_does_not_invalidate_deferred_task(self):
        call, track, worker = await self.deferred_backend()
        class Router:
            async def route(self, text, context): return Route('new_task', agent_alias='desk')
        self.coordinator.router = Router()
        await self.say(call, 'unrelated task')
        self.assertEqual(call.responsive_output.pending_count, 1)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken, ['Real backend reply?'])
        self.assertEqual(len(self.dialog.received), 1)

    async def test_started_backend_interruption_does_not_replay_or_cancel_observation(self):
        call = await self.start()
        await self.say(call, 'first request')
        await self.dialog.started.wait()
        self.speech.hold = 'Real backend reply?'
        entered = asyncio.Event()
        synthesize = self.speech.synthesize
        async def marked(text):
            if text == self.speech.hold: entered.set()
            async for chunk in synthesize(text): yield chunk
        self.speech.synthesize = marked
        self.dialog.release.set()
        await asyncio.wait_for(entered.wait(), 2)
        _, worker = await self.onset(call)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        self.speech.release.set()
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken.count('Real backend reply?'), 1)
        self.assertEqual(len(self.dialog.received), 1)
        self.assertFalse(self.dialog.cancelled)
        self.assertEqual(call.playback.data, b'')

    async def test_empty_and_failed_asr_release_deferred_without_reviving_old_origin(self):
        # Independent calls are needed because the legacy reservation is per call.
        for fails in (False, True):
            call, track, worker = await self.deferred_backend()
            async def transcribe(pcm):
                if fails: raise RuntimeError('synthetic ASR failure')
                return ''
            self.speech.transcribe = transcribe
            capture = self.assertLogs('native-voice', level='WARNING') if fails else self.assertNoLogs('native-voice', level='WARNING')
            with capture as logs:
                await self.endpoint(track)
                await call.turns.join()
            if fails:
                self.assertTrue(any('stage=asr_failed type=RuntimeError' in line for line in logs.output))
                self.assertEqual(len(logs.output), 1)
            await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
            self.assertEqual(self.speech.spoken, ['Real backend reply?'])
            await call.close()
            # Reset only the fake boundaries for a new independently owned call.
            self.dialog = fixtures.Dialog()
            self.speech = fixtures.Speech()

    async def test_short_discarded_endpoint_releases_deferred(self):
        call = await self.start()
        await self.say(call, 'first request')
        await self.dialog.started.wait()
        await call.responsive_output.wait_idle()
        self.speech.spoken.clear()
        track = Track()
        track.feed(count=5)
        call.receive_track(track)
        await track.idle.wait()
        self.assertTrue(call.vad_active)
        published = self.backend_publication(call)
        self.dialog.release.set()
        await asyncio.wait_for(published.wait(), 2)
        await self.drain_scheduling()
        self.assertEqual(self.speech.spoken, [])
        await self.endpoint(track)
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertTrue(call.turns.empty())
        self.assertEqual(self.speech.spoken, ['Real backend reply?'])

    async def test_lifecycle_control_waits_physical_input_but_not_held_acceptance(self):
        self.dialog.open_release.clear()
        entered, release = asyncio.Event(), asyncio.Event()
        class Router:
            async def route(self, text, context):
                entered.set()
                await release.wait()
                return Route('clarification', reply='Old answer')
        self.coordinator.router = Router()
        call = await self.start()
        call.turns.put_nowait((0, b'held inference'))
        await entered.wait()
        track, worker = await self.onset(call)
        notice = asyncio.create_task(call.responsive_notice('Actual greeting', wait=True))
        await self.drain_scheduling()
        self.assertEqual(self.speech.spoken, [])
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.wait_for(notice, 2)
        self.assertTrue(call._acceptance_active)
        self.assertFalse(call._input_ready())
        release.set()
        await call.recognized_turns.join()
        await call.responsive_output.wait_idle()
        self.assertEqual(self.speech.spoken, ['Actual greeting'])

    async def test_delayed_startup_language_backlog_and_physical_input_do_not_deadlock(self):
        from assistant_settings import CallSettings
        from test_assistant_settings import authorized_settings, SERVICE, AGENT
        settings = CallSettings.from_authorized_response(authorized_settings(), SERVICE, AGENT)
        self.dialog.open_release.clear()
        self.dialog.greetings = ['Startup greeting']
        call = await self.start(settings=settings)
        track, worker = await self.onset(call)
        from native_bridge import _InputEnvelope
        call.turns.put_nowait(_InputEnvelope((call.playback.generation, b'English please.'), 1))
        await call.turns.join()
        call.turns.put_nowait(_InputEnvelope((call.playback.generation, b'first request'), 1))
        await call.turns.join()
        self.assertEqual(call.recognized_turns.qsize(), 1)
        self.dialog.open_release.set()
        await self.drain_scheduling()
        self.assertEqual(self.speech.spoken, [])
        self.assertEqual(self.dialog.received, [])
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.wait_for(call.recognized_turns.join(), 2)
        await asyncio.wait_for(self.dialog.started.wait(), 2)
        self.assertEqual(self.speech.spoken[0], 'Startup greeting')
        self.assertTrue(any(t.get('code') == 'LANGUAGE_SELECTED' for t in self.transcripts(call)))
        self.assertEqual(self.dialog.received[0][1]['language'], 'en-US')
        self.assertEqual(self.speech.maximum, 1)

    async def test_rejected_acceptance_releases_pause_and_stale_notice_is_suppressed(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Router:
            async def route(self, text, context):
                entered.set()
                await release.wait()
                raise RuntimeError('synthetic rejected acceptance')
        self.coordinator.router = Router()
        call = await self.start()
        call.turns.put_nowait((0, b'old question'))
        await entered.wait()
        _, worker = await self.onset(call)
        with self.assertLogs('native-voice', level='WARNING') as logs:
            release.set()
            await call.recognized_turns.join()
        self.assertTrue(any('stage=not_accepted type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await call.responsive_output.wait_idle()
        self.assertTrue(call._input_ready())
        self.assertEqual(self.speech.spoken, [])
        self.assertEqual(self.store.operations(call.call_id), [])

    async def test_explicit_stop_removes_deferred_but_keeps_observed_journal(self):
        call, track, worker = await self.deferred_backend()
        class Router:
            async def route(self, text, context): return Route('stop_speaking')
        self.coordinator.router = Router()
        await self.say(call, 'stop')
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken, [])
        task = self.store.list_tasks(call.call_id)[0]
        self.assertTrue(any(e['type'] == 'backend_observed' for e in self.store.events(task['task_id'], call.call_id)))
        self.assertEqual(len(self.dialog.received), 1)

    async def test_audio_queue_full_and_receiver_retirement_never_fabricate_idle(self):
        call = await self.start()
        call.asr_task.cancel()
        await asyncio.gather(call.asr_task, return_exceptions=True)
        call.turns.put_nowait((0, b'queued one'))
        call.turns.put_nowait((0, b'queued two'))
        track, worker = await self.onset(call)
        await self.endpoint(track)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        self.assertEqual(call.turns.qsize(), 2)
        self.assertFalse(call._control_ready())
        self.assertTrue(any(t.get('code') == 'BUSY' for t in self.transcripts(call)))
        call.asr_task = call.spawn(call.recognize_turns())
        await call.turns.join()
        await call.recognized_turns.join()
        await self.drain_scheduling()
        self.assertTrue(call._input_ready())
        self.assertEqual([op['text'] for op in self.store.operations(call.call_id)], ['queued one', 'queued two'])

    async def test_old_publication_released_after_new_acceptance_remains_invalid(self):
        class Router:
            async def route(self, text, context): return Route('clarification', reply=text + ' answer')
        self.coordinator.router = Router()
        call = await self.start()
        entered, release = asyncio.Event(), asyncio.Event()
        publish = call.responsive_output.publish_guarded
        async def held(event, validity):
            if event['text'] == 'old answer':
                entered.set()
                await release.wait()
            return await publish(event, validity)
        call.responsive_output.publish_guarded = held
        await self.say(call, 'old')
        await asyncio.wait_for(entered.wait(), 2)
        async def transcribe(pcm): return 'new'
        self.speech.transcribe = transcribe
        track, worker = await self.onset(call)
        await self.endpoint(track)
        await call.turns.join()
        await call.recognized_turns.join()
        release.set()
        await self.drain_scheduling()
        await asyncio.wait_for(call.responsive_output.wait_idle(), 2)
        self.assertEqual(self.speech.spoken, ['new answer'])
        self.assertFalse(any(t['content'] == 'old answer' for t in self.transcripts(call)))

    async def test_terminal_input_loss_completes_paused_control_and_drops_deferred(self):
        call, track, worker = await self.deferred_backend()
        entered = asyncio.Event()
        async def transcribe(pcm):
            entered.set()
            await asyncio.Event().wait()
        self.speech.transcribe = transcribe
        await self.endpoint(track)
        await entered.wait()
        waiter = asyncio.create_task(call.responsive_notice('Paused control', wait=True))
        await self.drain_scheduling()
        self.assertFalse(waiter.done())
        with self.assertLogs('native-voice', level='WARNING') as logs:
            track.frames.put_nowait(RuntimeError('synthetic receiver loss'))
            await asyncio.wait_for(call.input_ended.wait(), 2)
        self.assertTrue(any('stage=track_failed type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        await asyncio.wait_for(waiter, 2)
        await asyncio.wait_for(call.turns_settled.wait(), 2)
        self.assertEqual(self.speech.spoken, [])
        self.assertEqual(call.responsive_output.pending_count, 0)
        self.assertFalse(self.dialog.cancelled)

    async def test_hangup_completes_paused_control_without_replaying_backend(self):
        call, track, worker = await self.deferred_backend()
        waiter = asyncio.create_task(call.responsive_notice('Paused control', wait=True))
        await self.drain_scheduling()
        self.assertFalse(waiter.done())
        await asyncio.wait_for(call.close(), 2)
        await asyncio.wait_for(waiter, 2)
        self.assertEqual(self.speech.spoken, [])
        self.assertEqual(call.responsive_output.pending_count, 0)
        self.assertEqual(len(self.dialog.received), 1)

    async def failed_startup(self, *, physical=False):
        opened, fail = asyncio.Event(), asyncio.Event()
        async def open_dialog():
            opened.set()
            await fail.wait()
            raise RuntimeError('synthetic startup failure')
        self.dialog.open = open_dialog
        call = await self.start()
        await opened.wait()
        track = worker = None
        if physical:
            track, worker = await self.onset(call)
        published = asyncio.Event()
        publish = call.responsive_output.publish_control
        async def marked(event, validity=None, **kwargs):
            if event['text'].startswith('Die Verbindung ist nicht bereit.'):
                published.set()
            return await publish(event, validity, **kwargs)
        call.responsive_output.publish_control = marked
        with self.assertLogs('native-voice', level='WARNING') as logs:
            fail.set()
            await published.wait()
        self.assertTrue(any('stage=startup_failed type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        return call, track, worker

    async def test_startup_failure_explains_failure_once_without_dispatch(self):
        call, _, _ = await self.failed_startup()
        await asyncio.wait_for(call.turns_settled.wait(), 2)
        notices = [t for t in self.transcripts(call) if t.get('code') == 'CONNECTION_FAILED']
        self.assertEqual(len(notices), 1)
        self.assertEqual(self.speech.spoken, [notices[0]['content']])
        self.assertEqual(self.dialog.received, [])
        self.assertTrue(call.failed)

    async def test_startup_failure_control_waits_for_actual_endpoint_after_failure(self):
        call, track, worker = await self.failed_startup(physical=True)
        self.assertEqual(self.speech.spoken, [])
        self.assertFalse(call._input_ready())
        await self.endpoint(track)
        await asyncio.wait_for(call.turns_settled.wait(), 2)
        notices = [t for t in self.transcripts(call) if t.get('code') == 'CONNECTION_FAILED']
        self.assertEqual(len(notices), 1)
        self.assertEqual(self.speech.spoken, [notices[0]['content']])
        self.assertEqual(self.dialog.received, [])

    async def retiring_failed_pipeline(self):
        fail, entered, cancelling = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def open_dialog():
            await fail.wait()
            raise RuntimeError('synthetic startup failure')
        async def transcribe(pcm):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelling.set()
                # Model a recognizer whose cancellation cleanup is still active.
                # The terminal close/loss cancels this boundary again.
                await asyncio.Event().wait()
                raise
        self.dialog.open = open_dialog
        self.speech.transcribe = transcribe
        call = await self.start()
        call.turns.put_nowait((0, b'active PCM'))
        await entered.wait()
        call.turns.put_nowait((0, b'queued PCM'))
        with self.assertLogs('native-voice', level='WARNING') as logs:
            fail.set()
            await asyncio.wait_for(cancelling.wait(), 2)
        self.assertTrue(any('stage=startup_failed type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        self.assertTrue(call.recognition_active)
        self.assertFalse(call._control_ready())
        return call

    async def test_startup_failure_control_never_refills_after_input_loss(self):
        call = await self.retiring_failed_pipeline()
        await asyncio.wait_for(call.finish_input_loss(), 2)
        await asyncio.wait_for(call.turns_settled.wait(), 2)
        await asyncio.wait_for(call.turns.join(), 2)
        self.assertEqual(self.speech.spoken, [])
        self.assertFalse(any(t.get('code') == 'CONNECTION_FAILED' for t in self.transcripts(call)))
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(call.playback.data, b'')

    async def test_startup_failure_retirement_remains_interruptible_by_close(self):
        call = await self.retiring_failed_pipeline()
        await asyncio.wait_for(call.close(), 2)
        await asyncio.wait_for(call.turns.join(), 2)
        self.assertEqual(self.speech.spoken, [])
        self.assertFalse(any(t.get('code') == 'CONNECTION_FAILED' for t in self.transcripts(call)))
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(call.playback.data, b'')

    async def test_unrelated_intake_failure_does_not_wait_on_normal_startup(self):
        self.dialog.open_release.clear()
        call = self.call()
        entered = asyncio.Event()
        async def fail_intake():
            entered.set()
            await asyncio.sleep(0)
            raise RuntimeError('synthetic intake failure')
        call.wait_for_user_turn = fail_intake
        with self.assertLogs('native-voice', level='WARNING') as logs:
            call.spawn(call.process_turns())
            await entered.wait()
            await asyncio.wait_for(call.turns_settled.wait(), .5)
        self.assertTrue(any('stage=unavailable type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        self.assertTrue(call.failed)
        self.assertEqual(self.dialog.received, [])

    async def failed_queue_case(self, *, physical=False):
        fail_open, asr_entered, release_asr = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def open_dialog():
            await fail_open.wait()
            raise RuntimeError('synthetic startup failure')
        async def transcribe(pcm):
            asr_entered.set()
            await release_asr.wait()
            return 'unaccepted audio'
        self.dialog.open = open_dialog
        self.speech.transcribe = transcribe
        call = await self.start()
        track = None
        if physical:
            track, _ = await self.onset(call)
        call.turns.put_nowait((0, b'active PCM'))
        await asr_entered.wait()
        call.turns.put_nowait((0, b'queued PCM'))
        published = asyncio.Event()
        publish = call.responsive_output.publish_control
        async def marked(event, validity=None, **kwargs):
            if event['text'].startswith('Die Verbindung ist nicht bereit.'):
                published.set()
            return await publish(event, validity, **kwargs)
        call.responsive_output.publish_control = marked
        with self.assertLogs('native-voice', level='WARNING') as logs:
            fail_open.set()
            await asyncio.wait_for(published.wait(), 2)
        self.assertTrue(any('stage=startup_failed type=RuntimeError' in line for line in logs.output))
        self.assertEqual(len(logs.output), 1)
        release_asr.set()
        await asyncio.gather(call.asr_task, return_exceptions=True)
        self.assertTrue(call.turns.empty(), 'failed recognition left unconsumable queued PCM')
        await asyncio.wait_for(call.turns.join(), 2)
        if physical:
            self.assertFalse(call._control_ready())
            self.assertEqual(self.speech.spoken, [])
            await self.endpoint(track)
        await asyncio.wait_for(call.turns_settled.wait(), 2)
        notices = [t for t in self.transcripts(call) if t.get('code') == 'CONNECTION_FAILED']
        self.assertEqual(len(notices), 1)
        self.assertEqual(self.speech.spoken, [notices[0]['content']])
        self.assertEqual(self.dialog.received, [])
        self.assertEqual(self.store.operations(call.call_id), [])

    async def test_startup_failure_retires_active_asr_and_discards_queued_pcm(self):
        await self.failed_queue_case()

    async def test_failed_queue_retirement_does_not_clear_live_receiver_vad(self):
        await self.failed_queue_case(physical=True)


if __name__ == '__main__': unittest.main()
