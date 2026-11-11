"""CPU lifecycle tests; factories are fake and no DLL/runtime is loaded."""
from pathlib import Path
import sys
import threading
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from actor import PrefixKey,StatefulActor,prefix_hash
from test_actor import FakeEngine
from request_scoped_backend import RequestScopedBackend
from service import ProducerWorker,ENGINE,TOKENIZER
from service_request_scoped import connect_once
from unittest.mock import patch,Mock


class FakeRequestEngine(FakeEngine):
    def __init__(self,ordinal):
        super().__init__();self.ordinal=ordinal;self.handle=ordinal;self.closed=False
        self.operations=[];self.fail_close=False

    def seed(self,ids):
        self.operations.append(dict(operation='seed',fixture_ordinal=self.ordinal));return super().seed(ids)

    def forward(self,token):
        self.operations.append(dict(operation='forward',fixture_ordinal=self.ordinal));return super().forward(token)

    def close(self):
        self.calls.append(('close',self.ordinal))
        if self.fail_close:raise RuntimeError('injected context cleanup failure')
        self.states.clear();self.handle=None;self.closed=True


class RequestScopedTests(unittest.TestCase):
    def setUp(self):
        self.created=[];self.prompt=list(range(8192))
        def factory():
            backend=FakeRequestEngine(len(self.created)+1);self.created.append(backend);return backend
        self.proxy=RequestScopedBackend('unused.dll','unused-model','unused-bundle','unused-runtime',backend_factory=factory)
        self.actor=StatefulActor(self.proxy)

    def key(self,actual=(),epoch='a'*32):
        return PrefixKey(4,8192,epoch,7,len(actual),prefix_hash(self.prompt+list(actual)),actual[-1]if actual else -1)

    def begin(self,epoch='a'*32):self.actor.begin(self.key(epoch=epoch),self.prompt)

    def tearDown(self):
        for engine in self.created:engine.fail_close=False
        if not self.proxy.cleanup_failed:self.proxy.close()

    def test_idle_listener_proxy_has_no_factory_or_native_load_until_valid_seed(self):
        self.assertEqual(self.created,[]);self.assertEqual(self.proxy.operations,[]);self.assertFalse(self.proxy.states)
        self.proxy.close();self.assertEqual(self.created,[])
        with self.assertRaises(ValueError):self.proxy.seed([False]*512)
        self.assertEqual(self.created,[])
        self.begin();self.assertEqual(len(self.created),1);self.assertFalse(self.created[0].closed)

    def test_cancel_or_end_final_snapshot_release_closes_request_context(self):
        self.begin()
        while self.actor.prepare_one():pass
        self.assertEqual(len(self.proxy.states),4)
        self.actor.cancel()
        self.assertTrue(self.created[0].closed);self.assertFalse(self.proxy.states)
        self.assertFalse(self.proxy.context_active)
        self.assertEqual(sum(c[0]=='close'for c in self.created[0].calls),1)

    def test_normal_promotion_and_correction_always_retain_a_snapshot(self):
        self.begin()
        while self.actor.prepare_one():pass
        first=self.actor.query(self.key()).token_ids[0]
        key=self.key([first]);self.actor.commit(self.key(),key,[first])
        self.assertTrue(self.proxy.states);self.assertFalse(self.created[0].closed)
        self.actor.commit(key,self.key([first,42]),[42])
        self.assertEqual(len(self.proxy.states),1);self.assertFalse(self.created[0].closed)
        self.assertFalse(any(c[0]=='close'for c in self.created[0].calls))
        self.actor.cancel();self.assertTrue(self.created[0].closed)

    def test_new_begin_retires_old_context_and_loads_a_fresh_backend(self):
        self.begin();old=self.created[0]
        self.actor.begin(self.key(epoch='b'*32),self.prompt)
        self.assertTrue(old.closed);self.assertEqual(len(self.created),2)
        self.assertFalse(self.created[1].closed)
        self.actor.cancel();self.assertTrue(self.created[1].closed)

    def test_subsequent_request_preserves_aggregated_operations_with_context_ids(self):
        self.begin();self.actor.cancel();self.begin(epoch='b'*32);self.actor.cancel()
        self.assertEqual([r['request_context']for r in self.proxy.operations],[1,2])
        self.assertTrue(all(r['request_context_closed']is True for r in self.proxy.operations))
        self.assertTrue(all(r['request_close_started_qpc_ns']<=r['request_close_finished_qpc_ns']for r in self.proxy.operations))

    def test_final_close_failure_is_sticky_and_retains_native_resource_owner(self):
        self.begin();engine=self.created[0];engine.fail_close=True
        with self.assertRaises(RuntimeError)as caught:self.actor.cancel()
        self.assertIs(caught.exception.native_cleanup_complete,False)
        self.assertIs(caught.exception.resource_owner,self.proxy)
        self.assertTrue(self.proxy.cleanup_failed);self.assertTrue(self.proxy.context_active)
        self.assertIsNotNone(engine.handle);self.assertFalse(engine.closed)
        self.assertEqual(sum(c[0]=='close'for c in engine.calls),1)
        with self.assertRaises(RuntimeError):self.proxy.close()
        self.assertEqual(sum(c[0]=='close'for c in engine.calls),1)

    def test_partial_constructor_cleanup_failure_is_retained_without_second_load(self):
        owner=object();calls=[]
        def fail():
            calls.append(True);error=RuntimeError('injected partial constructor cleanup failure')
            error.native_cleanup_complete=False;error.resource_owner=owner;raise error
        proxy=RequestScopedBackend('unused.dll','model','bundle','runtime',backend_factory=fail)
        with self.assertRaises(RuntimeError)as caught:proxy.seed(tuple(range(512)))
        self.assertIs(caught.exception.native_cleanup_complete,False)
        self.assertEqual(proxy.retained_failed_owners,(owner,));self.assertTrue(proxy.cleanup_failed)
        with self.assertRaises(RuntimeError):proxy.seed(tuple(range(512)))
        self.assertEqual(len(calls),1)

    def test_seed_failure_without_snapshots_closes_partial_request_context(self):
        def fail_seed(ids):raise RuntimeError('injected seed failure')
        engine=FakeRequestEngine(1);engine.seed=fail_seed
        proxy=RequestScopedBackend('unused.dll','model','bundle','runtime',backend_factory=lambda:engine)
        with self.assertRaisesRegex(RuntimeError,'injected seed failure'):proxy.seed(tuple(range(512)))
        self.assertTrue(engine.closed);self.assertFalse(proxy.context_active)

    def test_actual_worker_stays_cold_then_END_releases_and_next_BEGIN_is_fresh(self):
        ended=threading.Event();created=[]
        def factory():
            engine=FakeRequestEngine(len(created)+1);created.append(engine);close=engine.close
            def finish():close();ended.set()
            engine.close=finish;return engine
        worker=ProducerWorker(lambda:RequestScopedBackend('dll','model','bundle','runtime',backend_factory=factory),lambda packet:None)
        def event(kind,epoch,actual=(),sequence=1):
            return dict(schema='halogen0201.authoritative-token-feedback.v1',source='native_T',kind=kind,
                engine_sha256=ENGINE,tokenizer_sha256=TOKENIZER,request_id=4,request_epoch=epoch,nonce=7,
                n_prompt=8192,prefix_count=8192+len(actual),generated_count=len(actual),
                prefix_sha256=prefix_hash(self.prompt+list(actual)),current_token=actual[-1]if actual else -1,
                token_ids=list(actual[-1:])if kind=='commit'else [],prompt_ids=self.prompt,sequence=sequence)
        worker.start()
        try:
            self.assertTrue(worker.loaded.wait(1));self.assertEqual(created,[])
            worker.submit_event(event('begin','a'*32))
            worker.submit_event(event('commit','a'*32,[8192],2))
            worker.submit_event(event('done','a'*32,[8192],3))
            self.assertTrue(ended.wait(1));self.assertTrue(created[0].closed)
            self.assertIsNone(worker.error);self.assertFalse(worker.backend.context_active)
            ended.clear();worker.submit_event(event('begin','b'*32));worker.submit_event(event('done','b'*32,(),2))
            self.assertTrue(ended.wait(1));self.assertEqual(len(created),2)
            self.assertTrue(created[1].closed);self.assertFalse(worker.backend.context_active)
            self.assertIsNone(worker.error)
        finally:worker.close(timeout=1)

    def test_reverse_connection_is_single_attempt_and_never_loads_backend(self):
        with patch('service_request_scoped.socket.create_connection',side_effect=OSError('fixture route failure'))as create:
            with self.assertRaises(OSError):connect_once('127.0.0.1',8843)
            create.assert_called_once_with(('127.0.0.1',8843),timeout=5)
        self.assertEqual(self.created,[])

    def test_reverse_connection_setup_failure_closes_acquired_socket(self):
        connection=Mock();connection.setsockopt.side_effect=OSError('fixture socket option failure')
        with patch('service_request_scoped.socket.create_connection',return_value=connection)as create:
            with self.assertRaises(OSError):connect_once('127.0.0.1',8843)
            create.assert_called_once();connection.close.assert_called_once()
        self.assertEqual(self.created,[])


if __name__=='__main__':unittest.main()
