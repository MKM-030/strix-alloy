"""CPU transactions exercise the production coordinator with an opaque fake engine."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from actor import OwnedRow, PrefixKey, StatefulActor, prefix_hash


class FakeEngine:
    def __init__(self):
        self.history=();self.calls=[];self.states={};self.next_state=0
        self.maximum_states=0;self.after_forward=None;self.fail_restore=False

    @staticmethod
    def row(history):
        raw=hashlib.sha256(struct.pack('<%di'%len(history),*history)).digest()
        return OwnedRow((history[-1]+1)%248070,raw)

    def seed(self,ids):
        self.calls.append(('seed',tuple(ids)));self.history=tuple(ids)
        return self.row(self.history)

    def forward(self,token):
        self.calls.append(('forward',token));self.history+=(token,)
        row=self.row(self.history)
        if self.after_forward:self.after_forward()
        return row

    def context_length(self):return len(self.history)

    def save(self):
        self.next_state+=1;self.states[self.next_state]=self.history
        self.maximum_states=max(self.maximum_states,len(self.states))
        self.calls.append(('save',self.next_state));return self.next_state

    def restore(self,state):
        self.calls.append(('restore',state))
        if self.fail_restore:raise RuntimeError('injected restore failure')
        self.history=self.states[state]
        return len(self.history)

    def free(self,state):self.calls.append(('free',state));del self.states[state]


class ActorTests(unittest.TestCase):
    def setUp(self):
        self.prompt=[i%100 for i in range(8192)]
        self.engine=FakeEngine();self.actor=StatefulActor(self.engine)
        self.key=self.make_key([])

    def make_key(self,actual,epoch='a'*32,nonce=7):
        return PrefixKey(request_id=4,prompt_count=len(self.prompt),epoch=epoch,nonce=nonce,
            global_t_count=len(actual),prefix_sha256=prefix_hash(self.prompt+actual),
            current_token=actual[-1]if actual else -1)

    def begin(self):self.actor.begin(self.key,self.prompt)

    def prepare(self,count=3):
        for _ in range(count):self.assertTrue(self.actor.prepare_one())

    def test_seed_uses_exact_tail_and_initial_ready_never_calls_engine(self):
        self.begin();before=list(self.engine.calls);ready=self.actor.query(self.key)
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]))
        self.assertEqual(ready.token_ids,((self.prompt[-1]+1)%248070,))
        self.assertEqual(self.engine.calls,before)
        self.assertEqual(self.actor.committed_ids,())

    def test_lookahead_is_bounded_and_publications_expand_progressively(self):
        self.begin()
        for expected in (2,3,3):
            self.assertTrue(self.actor.prepare_one())
            self.assertEqual(len(self.actor.query(self.key).token_ids),expected)
        self.assertFalse(self.actor.prepare_one())
        self.assertEqual(self.actor.ring_size,4)
        self.assertEqual(self.engine.maximum_states,4)
        self.assertEqual(len(self.engine.history),515)

    def test_full_match_promotes_owned_row_and_state_without_native_replay(self):
        self.begin();self.prepare();actual=list(self.actor.query(self.key).token_ids)
        before=len(self.engine.calls)
        self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertFalse(any(c[0]in('forward','restore','seed')for c in calls))
        self.assertEqual(self.actor.committed_ids,tuple(actual))
        self.assertEqual(self.actor.ring_size,1)
        self.assertEqual(self.actor.query(self.make_key(actual)).owned_row_sha256,
                         hashlib.sha256(self.engine.row(self.engine.history).data).hexdigest())

    def test_partial_match_restores_confirmed_prefix_and_only_replays_corrections(self):
        self.begin();self.prepare();prediction=list(self.actor.query(self.key).token_ids)
        actual=[prediction[0],45,46];before=len(self.engine.calls)
        self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertEqual([c[1]for c in calls if c[0]=='forward'],[45,46])
        self.assertEqual(sum(c[0]=='restore'for c in calls),1)
        self.assertFalse(any(c[0]=='seed'for c in calls))
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))
        self.assertEqual(self.actor.committed_ids,tuple(actual))
        self.assertEqual(self.actor.ring_size,1)

    def test_zero_match_restores_committed_snapshot_and_no_guessed_token_survives(self):
        self.begin();self.prepare();actual=[5,8,13]
        self.actor.commit(self.key,self.make_key(actual),actual)
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))
        self.assertEqual(self.actor.committed_ids,tuple(actual))
        self.assertEqual(self.actor.ring_size,1)

    def test_partial_feedback_keeps_valid_future_states_for_next_target_tokens(self):
        self.begin();self.prepare();pred=list(self.actor.query(self.key).token_ids)
        one=self.make_key(pred[:1]);self.actor.commit(self.key,one,pred[:1])
        self.assertIsNone(self.actor.query(self.key))
        self.assertEqual(self.actor.ring_size,3)
        self.assertEqual(self.actor.query(one).token_ids[:2],tuple(pred[1:]))
        self.assertEqual(self.actor.committed_ids,tuple(pred[:1]))

    def test_all_128_actual_tokens_preserve_history_and_speculative_capacity(self):
        self.begin();actual=[];previous=self.key
        for step in range(128):
            while self.actor.prepare_one():pass
            token=(self.actor.query(previous).token_ids[0]if step%3 else 40+step)
            actual.append(token);new=self.make_key(actual)
            self.actor.commit(previous,new,[token]);previous=new
            self.assertLessEqual(len(self.engine.history),640)
            self.assertLessEqual(self.actor.ring_size,4)
        self.assertEqual(self.actor.committed_ids,tuple(actual))
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))
        self.assertFalse(self.actor.prepare_one());self.assertIsNone(self.actor.query(previous))
        self.assertEqual(sum(c[0]=='seed'for c in self.engine.calls),1)
        self.assertLessEqual(self.engine.maximum_states,4)

    def test_stale_epoch_nonce_count_hash_and_authority_rejected_before_native_calls(self):
        self.begin();self.prepare();before=list(self.engine.calls)
        for bad in (self.make_key([],epoch='b'*32),self.make_key([],nonce=8),
                    PrefixKey(4,8192,'a'*32,7,0,'0'*64,-1)):
            self.assertIsNone(self.actor.query(bad))
        self.assertEqual(self.engine.calls,before)
        bad=self.make_key([1]);bad=PrefixKey(4,8192,'a'*32,7,1,'0'*64,1)
        with self.assertRaises(ValueError):self.actor.commit(self.key,bad,[1])
        self.assertEqual(self.engine.calls,before)

    def test_unsupported_teacher_is_rejected_before_native_replay(self):
        self.begin();before=list(self.engine.calls)
        with self.assertRaises(ValueError):self.actor.commit(self.key,self.make_key([248070]),[248070])
        self.assertEqual(self.engine.calls,before)

    def test_query_is_engine_free_even_while_native_forward_is_in_flight(self):
        self.begin();seen=[]
        def query_inside_forward():
            before=len(self.engine.calls);ready=self.actor.query(self.key)
            seen.append(ready);self.assertEqual(len(self.engine.calls),before)
        self.engine.after_forward=query_inside_forward
        self.actor.prepare_one()
        self.assertEqual(len(seen),1)
        self.assertIsNotNone(seen[0])

    def test_cached_future_prefix_is_ready_before_worker_promotes_feedback(self):
        self.begin();self.actor.prepare_one()
        proposed=self.actor.query(self.key).token_ids[0]
        future=self.make_key([proposed]);before=list(self.engine.calls)
        self.assertIsNotNone(self.actor.query(future))
        self.assertEqual(self.actor.committed_ids,())
        self.assertEqual(self.engine.calls,before)
        self.assertIsNone(self.actor.query(self.make_key([(proposed+1)%248070])))
        observed=[]
        self.engine.after_forward=lambda:observed.append(self.actor.query(future))
        self.actor.prepare_one()
        self.assertIsNotNone(observed[0])
        self.assertEqual(self.actor.committed_ids,())

    def test_all_four_publications_have_exact_prospective_hashes_and_bounded_ids(self):
        self.begin();self.prepare();prefix=[]
        for depth in range(4):
            ready=self.actor.query(self.make_key(prefix))
            self.assertIsNotNone(ready)
            self.assertLessEqual(len(ready.token_ids),3)
            self.assertEqual(ready.key.current_token,prefix[-1]if prefix else -1)
            if depth<3:prefix.append(ready.token_ids[0])

    def test_failed_restore_retires_publication_and_frees_all_snapshots(self):
        self.begin();self.prepare();self.engine.fail_restore=True
        with self.assertRaises(RuntimeError):self.actor.commit(self.key,self.make_key([42]),[42])
        self.assertIsNone(self.actor.query(self.key));self.assertEqual(self.engine.states,{})

    def test_cancellation_frees_snapshots_and_new_epoch_never_reuses_them(self):
        self.begin();self.prepare();self.actor.cancel();self.assertEqual(self.engine.states,{})
        self.assertIsNone(self.actor.query(self.key))
        next_key=self.make_key([],epoch='b'*32)
        self.actor.begin(next_key,self.prompt)
        self.assertIsNone(self.actor.query(self.key));self.assertIsNotNone(self.actor.query(next_key))

    def test_serial_reentry_during_native_operation_is_rejected(self):
        self.begin()
        def reenter():
            with self.assertRaises(RuntimeError):self.actor.prepare_one()
        self.engine.after_forward=reenter;self.actor.prepare_one()

    def test_busy_publication_lock_is_an_immediate_engine_free_miss(self):
        self.begin();before=list(self.engine.calls)
        self.actor.mailbox.lock.acquire()
        try:self.assertIsNone(self.actor.query(self.key))
        finally:self.actor.mailbox.lock.release()
        self.assertEqual(self.engine.calls,before)

    def test_foreign_actor_thread_cannot_call_the_backend(self):
        import threading
        self.begin();before=list(self.engine.calls);errors=[]
        def other():
            try:self.actor.prepare_one()
            except RuntimeError as error:errors.append(str(error))
        thread=threading.Thread(target=other);thread.start();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(len(errors),1)
        self.assertEqual(self.engine.calls,before)

    def test_unforwarded_greedy_catchup_uses_live_committed_prefix_without_restore(self):
        self.begin();actual=list(self.actor.query(self.key).token_ids[:1]);before=len(self.engine.calls)
        self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertFalse(any(call[0]=='restore'for call in calls))
        self.assertEqual([call[1]for call in calls if call[0]=='forward'],actual)
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))

    def test_matched_cached_tail_only_forwards_uncached_true_suffix_without_restore(self):
        self.begin();self.actor.prepare_one();actual=list(self.actor.query(self.key).token_ids)
        self.assertEqual(len(actual),2);before=len(self.engine.calls)
        self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertFalse(any(call[0]=='restore'for call in calls))
        self.assertEqual([call[1]for call in calls if call[0]=='forward'],actual[1:])
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))

    def test_live_tail_context_mismatch_fails_before_skip_or_authoritative_forward(self):
        self.begin();actual=list(self.actor.query(self.key).token_ids[:1])
        self.engine.history+=(42,);before=len(self.engine.calls)
        with self.assertRaisesRegex(ValueError,'Native context differs'):
            self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertFalse(any(call[0]in('restore','forward')for call in calls))
        self.assertIsNone(self.actor.query(self.key));self.assertEqual(self.engine.states,{})

    def test_rejected_speculative_suffix_still_requires_exact_snapshot_restore(self):
        self.begin();self.prepare();actual=[45];before=len(self.engine.calls)
        self.actor.commit(self.key,self.make_key(actual),actual)
        calls=self.engine.calls[before:]
        self.assertEqual(sum(call[0]=='restore'for call in calls),1)
        self.assertEqual(self.engine.history,tuple(self.prompt[-512:]+actual))


if __name__=='__main__':unittest.main()
