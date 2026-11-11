"""CPU-only owned-stop and actual service-finalizer tests with fake transport."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import service_request_scoped_v2 as m


class StopTests(unittest.TestCase):
    def test_only_exact_nonce_on_fresh_regular_owned_file_requests_stop(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'stop';stop=m.OwnedStop(path,'a'*32)
            self.assertFalse(stop.requested())
            path.write_text(json.dumps(dict(nonce='b'*32))+'\n');self.assertFalse(stop.requested())
            path.write_text(json.dumps(dict(nonce='a'*32))+'\n');self.assertTrue(stop.requested())
            self.assertEqual(stop.identity['bytes'],path.stat().st_size);self.assertTrue(path.is_file())
            with self.assertRaises(ValueError):m.OwnedStop(path,'a'*32)

    def test_hardlinked_stop_is_rejected_without_accepting_the_nonce(self):
        import os
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'stop';stop=m.OwnedStop(path,'a'*32)
            path.write_text(json.dumps(dict(nonce='a'*32))+'\n');os.link(path,Path(tmp)/'alias')
            with self.assertRaises(ValueError):stop.requested()

    def test_oversized_or_partial_stop_is_not_an_owned_stop(self):
        with tempfile.TemporaryDirectory()as tmp:
            path=Path(tmp)/'stop';stop=m.OwnedStop(path,'a'*32)
            for raw in(b'{"nonce":',b'X'*129,b''):
                path.write_bytes(raw)
                with self.subTest(size=len(raw)),self.assertRaises(ValueError):stop.requested()

    def test_actual_service_observes_stop_then_runs_thread_and_backend_finalizers(self):
        class Connection:
            def __init__(self):self.ended=threading.Event();self.closed=False
            def recv(self,n):self.ended.wait(2);return b''
            def sendall(self,data):raise AssertionError('Cold fixture has no READY packets')
            def shutdown(self,how):self.ended.set()
            def close(self):self.closed=True;self.ended.set()
        class Backend:
            def __init__(self,*args):
                self.context_active=False;self.operations=[];self.states=set();self.closed=False;created.append(self);loaded.set()
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);report=root/'report.json';stop=root/'stop';loaded=threading.Event();created=[];connection=Connection()
            args=['service','--enable-native-component','--dll','unused.dll','--model','unused-model',
                  '--bundle','unused-bundle','--runtime-dir','unused-runtime','--report',str(report),
                  '--connect-port','8843','--maximum-seconds','5','--stop-file',str(stop),'--stop-nonce','a'*32]
            def write_stop():
                if loaded.wait(1):stop.write_text(json.dumps(dict(nonce='a'*32))+'\n')
            writer=threading.Thread(target=write_stop);writer.start()
            try:
                with patch.object(sys,'argv',args),patch.object(m,'connect_once',return_value=connection),patch.object(m,'RequestScopedBackend',Backend):
                    self.assertEqual(m.main(),0)
            finally:connection.ended.set();writer.join(1)
            value=json.loads(report.read_bytes())
            self.assertTrue(value['stop_request_observed']);self.assertTrue(value['native_closed'])
            self.assertTrue(value['worker_thread_closed']);self.assertTrue(created[0].closed)
            self.assertTrue(connection.closed);self.assertIsNone(value['error'])


if __name__=='__main__':unittest.main()
