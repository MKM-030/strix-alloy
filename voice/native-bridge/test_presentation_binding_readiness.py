"""Offline real Dialog/NativeDuplex readiness boundary; synthetic PCM only."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_duplex as duplex
from native_bridge import Config,Dialog,load_config as load_native_config
from test_native_duplex import FakeCall
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from voice.bridge import load_config as load_bridge_config


class BindingReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dialog=Dialog(Config(presentation_history_enabled=True))
        self.dialog.http=object();self.dialog.csrf='synthetic-csrf'
        self.calls=[]
        async def request(method,path,**kwargs):
            self.calls.append((method,path,kwargs))
            if path=='/api/end':return {'ended':True}
            e=kwargs['json']
            return dict(status='success',state='presentation_history_stored',requestId='f'*32,
                conversationId=self.dialog.metadata['conversation_id'],sequence=e['sequence'],
                eventId=e['event_id'],textSha256=e['text_sha256'],stored=True,hostEmitted=True,
                heard=False,promptIncluded=False)
        self.dialog.request=AsyncMock(side_effect=request)
        self.call=FakeCall();self.call.dialog=self.dialog
        self.lane=duplex.NativeDuplex(self.call,presentation_publisher=self.dialog.publish_presentation_history)
        self.opening=asyncio.get_running_loop().create_future()
        self.running=asyncio.create_task(self.lane.run(bootstrap_task=self.opening))
        await asyncio.sleep(0)

    async def asyncTearDown(self):
        self.running.cancel();await asyncio.gather(self.running,return_exceptions=True)
        await self.lane.close()

    def bind(self,c='c'):
        self.dialog.observe_state({'conversationBinding':dict(source='servicenow_create_conversation',
            conversationId=c*32,creationMessageId='d'*32,createRequestId='e'*32,interactionId='a'*32)})

    def complete_speech(self):
        item=duplex._Output('Complete synthetic local speech.',(0,'Original synthetic input',1,'b'*32,0),
            self.lane.epoch,self.lane.task_revision,None,'conversation')
        state=self.lane._begin_speech(item)
        state['lease']=duplex._SpeechLease(item,self.call.playback.generation,self.lane.epoch,None,None)
        self.call.playback.put(b'\1\0'*960,self.call.playback.generation)
        self.lane._finish_speech(state,complete=True)
        self.call.playback.read(1920);self.lane._update_speech_cursor()
        return state

    async def settle(self):
        for _ in range(10):await asyncio.sleep(0)

    async def test_early_full_speech_waits_before_dequeue_then_publishes_once_after_binding(self):
        state=self.complete_speech();await self.settle()
        self.assertEqual(state['accepted_samples'],state['emitted_samples'])
        self.assertEqual(state['emitted_samples'],960)
        self.assertFalse(self.lane._presentation_outbox.disabled)
        self.assertEqual(self.lane._presentation_outbox._queue.qsize(),1)
        self.assertEqual(self.calls,[]);self.assertFalse(self.running.done())
        self.bind();await self.settle()
        self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][:2],('POST','/api/presentation-history'))
        self.assertEqual(self.calls[0][2]['json']['emitted_samples'],960)
        self.assertEqual(self.calls[0][2]['json']['sequence'],1)
        self.assertFalse(self.lane._presentation_outbox.disabled)
        await self.settle();self.assertEqual(len(self.calls),1)

    async def test_reset_discards_queued_old_generation_even_when_new_binding_arrives(self):
        self.complete_speech();await self.settle()
        self.assertFalse(self.lane._presentation_outbox.disabled)
        await self.dialog.reset_owned_session();self.bind('9');await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertEqual([x[1] for x in self.calls],['/api/end'])
        self.assertTrue(self.running.done() or not self.lane._presentation_outbox._queue.qsize())

    async def test_end_state_retires_binding_gate_and_queued_history(self):
        self.complete_speech();await self.settle()
        self.assertFalse(self.lane._presentation_outbox.disabled)
        self.dialog.observe_state({'ended':True});await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled);self.assertEqual(self.calls,[])

    async def test_unknown_publication_still_disables_once_and_never_retries(self):
        self.bind()
        self.dialog.request.side_effect=lambda *a,**k:dict(stored=False)
        self.complete_speech();await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertEqual(self.dialog.request.await_count,1)
        self.complete_speech();await self.settle();self.assertEqual(self.dialog.request.await_count,1)

    async def test_waiting_gate_close_clears_queue_and_owned_worker(self):
        self.complete_speech();await self.settle();await self.lane.close()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertTrue(all(t.done() for t in self.lane._workers));self.assertEqual(self.calls,[])

    async def test_reset_after_ready_cannot_publish_old_outbox_into_new_session(self):
        self.bind();await self.settle()
        await self.dialog.reset_owned_session();self.bind('9');self.dialog.csrf='new-synthetic-csrf'
        self.complete_speech();await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertEqual([x[1] for x in self.calls],['/api/end'])

    async def test_already_scheduled_attempt_cannot_enter_publisher_after_reset(self):
        self.bind();await self.settle()
        self.complete_speech()
        event=self.lane._presentation_outbox._queue.get_nowait()
        self.lane._presentation_outbox._queue.task_done()
        attempt=self.lane._publish_presentation_history(event)
        await self.dialog.reset_owned_session();self.bind('9');self.dialog.csrf='new-synthetic-csrf'
        self.assertIs(await attempt,False)
        self.assertEqual([x[1] for x in self.calls],['/api/end'])

    async def test_early_queue_stays_bounded16_then_each_event_publishes_once(self):
        for _ in range(17):self.complete_speech()
        await self.settle()
        self.assertFalse(self.lane._presentation_outbox.disabled)
        self.assertEqual(self.lane._presentation_outbox.sequence,16)
        self.assertEqual(self.lane._presentation_outbox._queue.qsize(),16)
        self.assertEqual(self.calls,[])
        self.bind()
        for _ in range(60):await asyncio.sleep(0)
        self.assertEqual(len(self.calls),16)
        self.assertEqual([call[2]['json']['sequence'] for call in self.calls],list(range(1,17)))

    async def test_binding_wait_exceeds_publication_budget_without_starting_attempt(self):
        self.complete_speech()
        await asyncio.sleep(2.05)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.lane._presentation_outbox._queue.qsize(),1)
        original=self.dialog.request.side_effect
        async def slow_request(*args,**kwargs):
            await asyncio.sleep(.05)
            return await original(*args,**kwargs)
        self.dialog.request.side_effect=slow_request
        self.bind()
        await asyncio.wait_for(self.lane._presentation_outbox._queue.join(),1)
        self.assertEqual(len(self.calls),1)
        self.assertFalse(self.lane._presentation_outbox.disabled)

    async def test_close_without_http_retires_waiting_optional_lane(self):
        self.complete_speech();await self.settle();self.dialog.http=None
        await self.dialog.close();await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertEqual(self.calls,[])

    async def test_shutdown_without_http_retires_waiting_optional_lane(self):
        self.complete_speech();await self.settle();self.dialog.http=None
        await self.dialog.shutdown();await self.settle()
        self.assertTrue(self.lane._presentation_outbox.disabled)
        self.assertEqual(self.calls,[])

    async def test_optional_retirement_callback_failure_cannot_block_owned_reset(self):
        self.dialog._presentation_retire_worker=Mock(side_effect=RuntimeError('private detail'))
        await self.dialog.reset_owned_session()
        self.assertEqual([x[1] for x in self.calls],['/api/end'])

    async def test_optional_diagnostics_are_finite_metadata_and_logger_failure_is_isolated(self):
        with patch.object(duplex.LOG,'info') as info:
            self.complete_speech();await self.settle();self.bind();await self.settle()
        messages=[args[0] % args[1:] for args,kwargs in info.call_args_list
            if args and args[0].startswith('Voice presentation history')]
        self.assertTrue(messages)
        for stage in ('offer_accepted','binding_ready','attempt','stored'):
            self.assertTrue(any('stage='+stage+' ' in message for message in messages),stage)
        for message in messages:
            self.assertRegex(message,r'count=(?:[0-9]|1[0-6])$')
            for hidden in ('Complete synthetic local speech.','Original synthetic input','b'*32):
                self.assertNotIn(hidden,message)
        with patch.object(duplex.LOG,'info',side_effect=RuntimeError('private logger error')):
            self.complete_speech();await self.settle()
        self.assertEqual(len(self.calls),2)


class PresentationConfigLoadingTests(unittest.TestCase):
    def test_real_native_loader_and_per_call_replace_preserve_enabled_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'native.synthetic.json'
            path.write_text(json.dumps({'presentation_history_enabled':True}),encoding='utf-8')
            config=replace(load_native_config(path),greeting='Synthetic greeting')
        self.assertIs(config.presentation_history_enabled,True)
        dialog=Dialog(config)
        self.assertIsNotNone(dialog._presentation_ready)

    def test_real_bridge_loader_preserves_history_flag_with_synthetic_token_only(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{},clear=True):
            token=Path(directory)/'audio.synthetic.token'
            token.write_text('synthetic-audio-token-only',encoding='utf-8')
            path=Path(directory)/'bridge.synthetic.json'
            path.write_text(json.dumps({'settings':{'service_now_enabled':False,
                'presentation_history_enabled':True},'audio_token_file':str(token)}),encoding='utf-8')
            bridge=load_bridge_config(path)
        self.assertIs(bridge.settings.presentation_history_enabled,True)
        self.assertEqual(bridge.sessions,{})
