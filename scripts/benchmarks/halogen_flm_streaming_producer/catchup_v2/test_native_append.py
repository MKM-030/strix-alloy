"""Fake typed C ABI only; no loader, compiled DLL, device or model is used."""
import ctypes as c
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_backend as m
from request_scoped_backend import RequestScopedBackend


class Function:
    def __init__(self,body):self.body=body
    def __call__(self,*args):return self.body(*args)


class FakeDLL:
    def __init__(self):
        self.calls=[];self.count=512;self.fail=False;self.ticks=1
        self.sl1012_last_error=Function(lambda:b'injected scalar append error')
        self.sl1012_create=Function(self.create)
        self.sl1012_close=Function(lambda handle:self.calls.append(('close',handle))or 0)
        self.sl1012_context=Function(self.context)
        self.sl1012_append_only=Function(self.append)
        self.sl1012_forward=Function(self.forward)
        self.sl1012_seed=Function(lambda *args:0)
        for name in ('state_read','state_write','state_free'):setattr(self,'sl1012_'+name,Function(lambda *args:0))

    def timing(self,out):
        self.ticks+=2;out._obj.started_ticks=self.ticks;out._obj.finished_ticks=self.ticks+1;out._obj.frequency=10000000
    def create(self,model,bundle,timing):self.calls.append(('create',));self.timing(timing);return 71
    def context(self,handle,out):out._obj.value=self.count;return 0
    def append(self,handle,token,timing):
        self.calls.append(('append_only',token));self.timing(timing)
        if self.fail:return -1
        self.count+=1;return 0
    def forward(self,handle,token,row,rows,greedy,timing):
        self.calls.append(('forward_row',token));self.count+=1;row[5]=0x3f80
        greedy._obj.value=5;self.timing(timing);return 0


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.dll_path=self.path/'wrapper/new.dll'
        self.dll_path.parent.mkdir();self.dll_path.write_bytes(b'not a native DLL; never loaded')
        self.runtime=self.path/'runtime';self.runtime.mkdir();self.library=FakeDLL();self.closed=[]

    def backend(self):
        def directory(path):return type('Directory',(),{'close':lambda obj:self.closed.append(path)})()
        with patch.object(m.os,'add_dll_directory',side_effect=directory),patch.object(m.c,'CDLL',return_value=self.library):
            result=m.NativeBackend(self.dll_path,self.path/'model',self.path/'bundle',self.runtime)
        self.addCleanup(lambda:result.close()if result.handle is not None else None)
        return result

    def test_append_has_typed_no_row_ABI_and_advances_once_without_snapshot(self):
        backend=self.backend()
        with patch.object(backend,'_row',side_effect=AssertionError('No intermediate row allowed')):
            self.assertIsNone(backend.append_only(7))
        self.assertEqual(self.library.count,513)
        self.assertEqual(self.library.calls,[('create',),('append_only',7)])
        self.assertEqual(self.library.sl1012_append_only.argtypes,[c.c_void_p,c.c_int32,c.POINTER(m.Timing)])
        self.assertIs(self.library.sl1012_append_only.restype,c.c_int)
        self.assertEqual(backend.operations[-1]['operation'],'append_only')
        self.assertEqual(backend.operations[-1]['local_count'],513)
        self.assertNotIn('owned_row_sha256',backend.operations[-1])
        self.assertFalse(backend.states)

    def test_final_forward_still_returns_complete_independent_owned_row(self):
        backend=self.backend();backend.append_only(7);backend.append_only(8);row=backend.forward(9)
        self.assertEqual(self.library.count,515)
        self.assertEqual([call[0]for call in self.library.calls],['create','append_only','append_only','forward_row'])
        self.assertEqual(len(row.data),248070*2);self.assertIs(type(row.data),bytes)
        self.assertEqual(row.greedy_id,5);self.assertIn('owned_row_sha256',backend.operations[-1])

    def test_append_error_is_propagated_and_existing_native_close_still_runs(self):
        backend=self.backend();self.library.fail=True
        with self.assertRaisesRegex(RuntimeError,'scalar append'):backend.append_only(7)
        self.assertEqual(self.library.count,512);self.assertEqual(len(backend.operations),1)
        backend.close();self.assertIsNone(backend.handle)
        self.assertEqual(sum(call[0]=='close'for call in self.library.calls),1)
        self.assertEqual(len(self.closed),2)

    def test_foreign_thread_and_non_int32_shared_ids_never_call_native_append(self):
        backend=self.backend();errors=[]
        def other():
            try:backend.append_only(7)
            except RuntimeError as error:errors.append(str(error))
        thread=threading.Thread(target=other);thread.start();thread.join(1)
        self.assertEqual(len(errors),1)
        for token in (True,-1,248070,1<<32):
            with self.assertRaises(ValueError):backend.append_only(token)
        self.assertEqual(self.library.calls,[('create',)])

    def test_old_DLL_without_new_export_fails_before_engine_construction_and_cleans_scopes(self):
        del self.library.sl1012_append_only
        with self.assertRaises(AttributeError):self.backend()
        self.assertEqual(self.library.calls,[]);self.assertEqual(len(self.closed),2)

    def test_request_proxy_keeps_anchor_until_end_and_archives_append_call(self):
        class FakeBackend:
            def __init__(obj):obj.handle=71;obj.states={1};obj.operations=[];obj.count=512
            def seed(obj,ids):return None
            def append_only(obj,token):
                obj.count+=1;obj.operations.append(dict(operation='append_only',local_count=obj.count))
            def close(obj):obj.handle=None;obj.states.clear()
            def free(obj,state):obj.states.remove(state)
        fake=FakeBackend();proxy=RequestScopedBackend(None,None,None,None,backend_factory=lambda:fake)
        proxy.seed([1]*512);self.assertIsNone(proxy.append_only(7))
        self.assertTrue(proxy.context_active);self.assertEqual(fake.states,{1});self.assertEqual(fake.count,513)
        proxy.free(1);self.assertFalse(proxy.context_active)
        self.assertTrue(proxy.operations[0]['request_context_closed'])
        self.assertEqual(proxy.operations[0]['operation'],'append_only')


if __name__=='__main__':unittest.main()
