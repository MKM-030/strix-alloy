"""CPU-only true-event catchup regressions; imports never load a native runtime."""
import hashlib
from pathlib import Path
import queue
import struct
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from actor import OwnedRow,PrefixKey,StatefulActor,prefix_hash
from service import ProducerWorker,ENGINE,TOKENIZER


class FakeEngine:
    def __init__(self):
        self.history=();self.calls=[];self.states={};self.serial=0
        self.fail_save=False;self.fail_append=False;self.closed=False

    @staticmethod
    def row(ids):
        return OwnedRow((ids[-1]+1)%248070,hashlib.sha256(struct.pack('<%di'%len(ids),*ids)).digest())

    def seed(self,ids):
        self.history=tuple(ids);self.calls.append(('seed',tuple(ids)));return self.row(self.history)

    def append_only(self,token):
        self.calls.append(('append_only',token))
        if self.fail_append:raise RuntimeError('append failure')
        self.history+=(token,)

    def forward(self,token):
        self.history+=(token,);self.calls.append(('forward',token));return self.row(self.history)

    def context_length(self):return len(self.history)

    def save(self):
        self.calls.append(('save',len(self.history)))
        if self.fail_save:raise RuntimeError('snapshot failure')
        self.serial+=1;self.states[self.serial]=self.history;return self.serial

    def restore(self,state):
        self.calls.append(('restore',state));self.history=self.states[state];return len(self.history)

    def free(self,state):self.calls.append(('free',state));del self.states[state]

    def close(self):self.closed=True


class Fixture:
    prompt=list(range(8192))

    def key(self,actual=(),epoch='a'*32):
        return PrefixKey(4,8192,epoch,7,len(actual),prefix_hash(self.prompt+list(actual)),actual[-1]if actual else -1)

    def event(self,actual=(),kind='begin',sequence=None,epoch='a'*32,ids=None):
        key=self.key(actual,epoch)
        return dict(schema='halogen0201.authoritative-token-feedback.v1',source='native_T',
            kind=kind,engine_sha256=ENGINE,tokenizer_sha256=TOKENIZER,request_id=key.request_id,
            n_prompt=key.prompt_count,request_epoch=key.epoch,nonce=key.nonce,
            generated_count=key.global_t_count,prefix_count=8192+len(actual),
            prefix_sha256=key.prefix_sha256,current_token=key.current_token,prompt_ids=self.prompt[:],
            token_ids=list(actual[-1:]if ids is None else ids)if kind=='commit'else [],
            sequence=len(actual)+1 if sequence is None else sequence)

    def transactions(self,actual):return [(self.key(actual[:i]),[actual[i-1]])for i in range(1,len(actual)+1)]


class CatchupActorTests(Fixture,unittest.TestCase):
    def setUp(self):
        self.engine=FakeEngine();self.actor=StatefulActor(self.engine)
        self.actor.begin(self.key(),self.prompt)

    def test_queued_true_suffix_has_identical_final_row_with_one_copy_and_snapshot(self):
        actual=[40+i for i in range(16)];before=len(self.engine.calls)
        self.assertTrue(hasattr(self.actor,'commit_batch'),'queued true-event catchup is not implemented')
        self.actor.commit_batch(self.key(),self.transactions(actual))
        calls=self.engine.calls[before:]
        self.assertEqual([call[1]for call in calls if call[0]=='append_only'],actual[:-1])
        self.assertEqual([call[1]for call in calls if call[0]=='forward'],actual[-1:])
        self.assertEqual(sum(call[0]=='save'for call in calls),1)
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))
        ready=self.actor.query(self.key(actual));self.assertEqual(ready.owned_row_sha256,self.engine.row(self.engine.history).sha256)
        self.assertEqual(ready.token_ids,(actual[-1]+1,))
        self.assertEqual(self.actor.committed_ids,tuple(actual))

    def test_entire_batch_hash_is_checked_before_any_native_or_publication_change(self):
        actual=[40,41,42];transactions=self.transactions(actual)
        bad=self.key(actual);transactions[-1]=(PrefixKey(4,8192,'a'*32,7,3,'0'*64,42),[42])
        before=self.engine.calls[:];ready=self.actor.query(self.key())
        with self.assertRaises(ValueError):self.actor.commit_batch(self.key(),transactions)
        self.assertEqual(self.engine.calls,before);self.assertEqual(self.actor.query(self.key()),ready)

    def test_intermediate_key_binding_and_unsupported_id_are_checked_before_native(self):
        for key,ids in ((self.key([40],epoch='b'*32),[40]),(self.key([248070]),[248070])):
            before=self.engine.calls[:]
            with self.assertRaises(ValueError):self.actor.commit_batch(self.key(),[(key,ids)])
            self.assertEqual(self.engine.calls,before)

    def test_cached_match_promotes_without_replay_and_retains_future_snapshots(self):
        for _ in range(3):self.actor.prepare_one()
        predicted=list(self.actor.query(self.key()).token_ids);before=len(self.engine.calls)
        self.actor.commit_batch(self.key(),self.transactions(predicted[:2]))
        self.assertFalse(any(call[0]in('forward','append_only','restore','save')for call in self.engine.calls[before:]))
        self.assertEqual(self.actor.ring_size,2)
        self.assertEqual(self.actor.query(self.key(predicted[:2])).token_ids[0],predicted[2])

    def test_partial_match_restores_only_once_and_appends_each_true_correction_once(self):
        for _ in range(3):self.actor.prepare_one()
        predicted=self.actor.query(self.key()).token_ids[0];actual=[predicted,40,41,42]
        before=len(self.engine.calls);self.actor.commit_batch(self.key(),self.transactions(actual))
        calls=self.engine.calls[before:]
        self.assertEqual(sum(call[0]=='restore'for call in calls),1)
        self.assertEqual([call[1]for call in calls if call[0]in('append_only','forward')],actual[1:])
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))

    def test_anchor_is_retained_until_final_snapshot_exists_and_failure_retires(self):
        self.engine.fail_save=True;self.engine.calls=[]
        with self.assertRaisesRegex(RuntimeError,'snapshot failure'):
            self.actor.commit_batch(self.key(),self.transactions([40,41]))
        calls=self.engine.calls;save=next(i for i,call in enumerate(calls)if call[0]=='save')
        self.assertFalse(any(call[0]=='free'for call in calls[:save]))
        self.assertEqual(self.engine.states,{});self.assertIsNone(self.actor.key)

    def test_single_event_multi_token_feedback_and_batch_bound_are_explicit(self):
        self.actor.commit_batch(self.key(),[(self.key([40,41,42]),[40,41,42])])
        self.assertEqual(self.actor.committed_ids,(40,41,42))
        before=self.engine.calls[:]
        with self.assertRaises(ValueError):self.actor.commit_batch(self.key([40,41,42]),[()] *17)
        self.assertEqual(self.engine.calls,before)


class CatchupWorkerTests(Fixture,unittest.TestCase):
    def setUp(self):
        self.engine=FakeEngine();self.outputs=[]
        self.worker=ProducerWorker(lambda:self.engine,self.outputs.append)

    def tearDown(self):self.worker.close(2)

    def test_batch_sequence_gap_rejects_all_true_tokens_before_native(self):
        self.worker.actor=StatefulActor(self.engine);self.worker._event(self.event())
        events=[self.event([40],kind='commit'),self.event([40,41],kind='commit',sequence=5)]
        before=self.engine.calls[:]
        self.assertTrue(hasattr(self.worker,'_commit_events'),'queued commit batching is not implemented')
        with self.assertRaises(ValueError):self.worker._commit_events(events)
        self.assertEqual(self.engine.calls,before)

    def test_late_batch_identity_error_rejects_all_true_tokens_before_native(self):
        self.worker.actor=StatefulActor(self.engine);self.worker._event(self.event())
        events=[self.event([40],kind='commit'),self.event([40,41],kind='commit')]
        events[-1]['engine_sha256']='0'*64;before=self.engine.calls[:]
        with self.assertRaises(ValueError):self.worker._commit_events(events)
        self.assertEqual(self.engine.calls,before)

    def test_end_then_next_begin_is_fifo_and_drain_is_capped_at16(self):
        observed=[]
        class ObservedWorker(ProducerWorker):
            def _commit_events(inner,events):
                observed.append(('batch',len(events)));return super()._commit_events(events)
            def _event(inner,event):
                observed.append((event['kind'],event['request_epoch']))
                result=super()._event(event)
                if event['kind']=='done'and event['request_epoch']=='b'*32:inner.stop.set()
                return result
        self.worker=ObservedWorker(lambda:self.engine,self.outputs.append)
        self.worker.submit_event(self.event())
        actual=list(range(40,57))
        for i in range(1,18):self.worker.submit_event(self.event(actual[:i],kind='commit'))
        self.worker.submit_event(self.event(actual,kind='done',sequence=19))
        self.worker.submit_event(self.event(epoch='b'*32))
        self.worker.submit_event(self.event(kind='done',sequence=2,epoch='b'*32))
        self.worker.start();self.assertTrue(self.worker.closed.wait(2));self.assertIsNone(self.worker.error)
        self.assertEqual(observed,[('begin','a'*32),('batch',16),('batch',1),('done','a'*32),('begin','b'*32),('done','b'*32)])
        self.assertEqual([call[1]for call in self.engine.calls if call[0]in('append_only','forward')],actual)
        self.assertEqual(sum(call[0]=='save'for call in self.engine.calls),4)
        self.assertEqual(self.engine.states,{})

    def test_no_wait_to_fill_batch_and_current_row_ready_is_published(self):
        ready=threading.Event();packets=[]
        class ObservedWorker(ProducerWorker):
            def _commit_events(inner,events):
                self.assertEqual(len(events),1);return super()._commit_events(events)
        def capture(packet):
            packets.append(packet)
            if packet['generated_count']==1:ready.set()
        self.worker=ObservedWorker(lambda:self.engine,capture)
        self.worker.submit_event(self.event());self.worker.submit_event(self.event([40],kind='commit'))
        self.worker.start();self.assertTrue(ready.wait(1));self.worker.close(2)
        packet=next(packet for packet in packets if packet['generated_count']==1)
        self.assertEqual(packet['prefix_sha256'],self.key([40]).prefix_sha256)
        self.assertEqual(packet['token_ids'][0],41)
        self.assertIsNone(self.worker.error)

    def test_invalid_pending_event_is_not_dropped_or_reordered(self):
        self.worker.submit_event(self.event());self.worker.submit_event(self.event([40],kind='commit'))
        self.worker.submit_event(None);self.worker.submit_event(self.event([40,41],kind='commit'))
        self.worker.start();self.assertTrue(self.worker.closed.wait(1))
        self.assertIsNotNone(self.worker.error)
        self.assertEqual([call[1]for call in self.engine.calls if call[0]in('append_only','forward')],[40])
        self.assertEqual(self.engine.states,{})


if __name__=='__main__':unittest.main()
