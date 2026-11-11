"""CPU worker tests use the actual queue/transaction worker with a fake engine."""
from pathlib import Path
import sys
import threading
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from actor import prefix_hash
from test_actor import FakeEngine
from service import ProducerWorker,MAX_FRAME,read_frame,write_frame


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.prompt=list(range(8192));self.outputs=[];self.arrived=threading.Event()
        self.engine=FakeEngine();self.engine.close=lambda:None
        self.worker=ProducerWorker(lambda:self.engine,self.capture)

    def capture(self,packet):self.outputs.append(packet);self.arrived.set()

    def event(self,actual=(),kind='begin',sequence=None):
        return dict(schema='halogen0201.authoritative-token-feedback.v1',kind=kind,source='native_T',
            request_id=4,request_epoch='a'*32,n_prompt=8192,nonce=7,
            generated_count=len(actual),prefix_count=8192+len(actual),prefix_sha256=prefix_hash(self.prompt+list(actual)),
            current_token=actual[-1]if actual else -1,prompt_ids=list(self.prompt),
            token_ids=list(actual[-1:])if kind=='commit'else [],sequence=sequence or len(actual)+1,
            engine_sha256='7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577',
            tokenizer_sha256='0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3')

    def tearDown(self):self.worker.close(timeout=2)

    def test_worker_publishes_future_prefixes_without_waiting_for_target_feedback(self):
        self.worker.start();self.assertTrue(self.worker.loaded.wait(1))
        self.assertTrue(self.worker.submit_event(self.event()))
        self.assertTrue(self.arrived.wait(1))
        self.assertGreaterEqual(self.outputs[0]['generated_count'],1)
        self.assertNotIn(0,[packet['generated_count']for packet in self.outputs])
        self.assertEqual(self.outputs[0]['prefix_sha256'],prefix_hash(self.prompt+[8192]))
        self.assertEqual(self.outputs[0]['token_ids'][0],8193)

    def test_invalid_target_identity_fails_closed_before_any_model_seed(self):
        data=self.event();data['engine_sha256']='0'*64
        self.worker.start();self.worker.submit_event(data)
        self.assertTrue(self.worker.closed.wait(1))
        self.assertIsNotNone(self.worker.error);self.assertEqual(self.engine.calls,[])

    def test_submitted_event_is_immutable_against_sender_mutation(self):
        event=self.event();self.assertTrue(self.worker.submit_event(event))
        event['prompt_ids'][-1]=42
        self.worker.start();self.assertTrue(self.arrived.wait(1))
        self.assertEqual(self.engine.calls[0][1][-1],8191)

    def test_event_sequence_gap_fails_closed_and_frees_all_snapshots(self):
        self.worker.start();self.worker.submit_event(self.event())
        self.assertTrue(self.arrived.wait(1));self.worker.submit_event(self.event([8192],'commit',sequence=3))
        self.assertTrue(self.worker.closed.wait(1))
        self.assertIsNotNone(self.worker.error);self.assertEqual(self.engine.states,{})

    def test_queue_overflow_retires_without_blocking_or_native_call(self):
        worker=ProducerWorker(lambda:self.engine,self.capture,queue_capacity=1)
        self.assertTrue(worker.submit_event(self.event()))
        self.assertFalse(worker.submit_event(self.event()))
        self.assertIsNotNone(worker.error);self.assertEqual(self.engine.calls,[])
        worker.close(timeout=1)

    def test_framing_handles_fragmentation_and_rejects_oversize_before_payload_read(self):
        class Stream:
            def __init__(self,data=b''):self.data=bytearray(data);self.written=bytearray()
            def recv(self,n):
                part=bytes(self.data[:min(n,3)]);del self.data[:len(part)];return part
            def sendall(self,data):self.written.extend(data)
        stream=Stream();write_frame(stream,dict(token_ids=[1,2,3]));stream.data=stream.written.copy()
        self.assertEqual(read_frame(stream),dict(token_ids=[1,2,3]))
        stream=Stream((MAX_FRAME+1).to_bytes(4,'little'))
        with self.assertRaises(ValueError):read_frame(stream)

    def test_failed_backend_close_cannot_be_reported_as_complete_native_cleanup(self):
        def bad_close():raise RuntimeError('injected close failure')
        self.engine.close=bad_close;self.worker.start();self.assertTrue(self.worker.loaded.wait(1))
        self.worker.close(timeout=1)
        self.assertTrue(self.worker.closed.is_set())
        self.assertIs(self.worker.native_cleanup_complete,False)
        self.assertIn('injected close failure',self.worker.error)

    def test_constructor_failure_retains_uncleared_native_owner_and_marks_cleanup_incomplete(self):
        retained=object()
        def fail_factory():
            error=RuntimeError('construction cleanup failed')
            error.native_cleanup_complete=False;error.resource_owner=retained;raise error
        worker=ProducerWorker(fail_factory,self.capture);worker.start()
        self.assertTrue(worker.closed.wait(1))
        self.assertIs(worker.native_cleanup_complete,False)
        self.assertIs(worker.failed_backend,retained)
        worker.close(timeout=1)


if __name__=='__main__':unittest.main()
