"""CPU-only fault injection: no real DLL or loader-directory function is called."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_backend as m


class Function:
    def __init__(self,body):self.body=body
    def __call__(self,*args):return self.body(*args)


class FakeDLL:
    def __init__(self,events,*,create_handle=123,valid_timing=True):
        self.events=events;self.create_handle=create_handle;self.valid_timing=valid_timing
        def create(model,bundle,timing):
            events.append(('create',model,bundle))
            timing._obj.started_ticks=10;timing._obj.finished_ticks=20 if valid_timing else 0
            timing._obj.frequency=10000000
            return create_handle
        self.sl1012_create=Function(create)
        self.sl1012_close=Function(lambda handle:events.append(('close_engine',handle))or 0)
        self.sl1012_last_error=Function(lambda:b'injected create failure')
        for name in('context','seed','forward','state_read','state_write','state_free'):
            setattr(self,'sl1012_'+name,Function(lambda *args:0))


class Directory:
    def __init__(self,path,events):self.path=path;self.events=events
    def close(self):self.events.append(('close_directory',self.path))


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.wrapper=self.base/'build'/'bridge.dll'
        self.wrapper.parent.mkdir();self.wrapper.write_bytes(b'CPU test placeholder, never loaded')
        self.runtime=self.base/'portable';self.runtime.mkdir();self.events=[]

    def patches(self,library=None,load_error=None,directory_error=None):
        def directory(path):
            self.events.append(('add_directory',path))
            if directory_error==len([e for e in self.events if e[0]=='add_directory']):
                raise OSError('injected directory failure')
            return Directory(path,self.events)
        def load(path):
            self.events.append(('load',path))
            if load_error:raise OSError('injected DLL load failure')
            return library or FakeDLL(self.events)
        return patch.object(m.os,'add_dll_directory',side_effect=directory),patch.object(m.c,'CDLL',side_effect=load)

    def construct(self):return m.NativeBackend(self.wrapper,self.base/'model',self.base/'bundle',self.runtime)

    def test_success_holds_both_explicit_directories_until_after_engine_close(self):
        first,second=self.patches()
        with first,second:
            backend=self.construct()
            self.assertEqual([e[1]for e in self.events if e[0]=='add_directory'],
                             [str(self.wrapper.parent.resolve()),str(self.runtime.resolve())])
            self.assertFalse(any(e[0]=='close_directory'for e in self.events))
            backend.close()
            closes=[e[0]for e in self.events if e[0].startswith('close')]
            self.assertEqual(closes,['close_engine','close_directory','close_directory'])

    def test_post_create_timing_failure_closes_engine_and_every_directory(self):
        first,second=self.patches(FakeDLL(self.events,valid_timing=False))
        with first,second,self.assertRaises(ValueError):self.construct()
        self.assertEqual(sum(e[0]=='close_engine'for e in self.events),1)
        self.assertEqual(sum(e[0]=='close_directory'for e in self.events),2)
        self.assertLess(next(i for i,e in enumerate(self.events)if e[0]=='close_engine'),
                        next(i for i,e in enumerate(self.events)if e[0]=='close_directory'))

    def test_load_failure_closes_registered_directories_without_native_close(self):
        first,second=self.patches(load_error=True)
        with first,second,self.assertRaises(OSError):self.construct()
        self.assertEqual(sum(e[0]=='close_directory'for e in self.events),2)
        self.assertFalse(any(e[0]=='close_engine'for e in self.events))

    def test_second_directory_failure_closes_first_without_loading_DLL(self):
        first,second=self.patches(directory_error=2)
        with first,second,self.assertRaises(OSError):self.construct()
        self.assertEqual(sum(e[0]=='close_directory'for e in self.events),1)
        self.assertFalse(any(e[0]=='load'for e in self.events))

    def test_null_create_closes_both_directories_without_closing_null_handle(self):
        first,second=self.patches(FakeDLL(self.events,create_handle=None))
        with first,second,self.assertRaisesRegex(RuntimeError,'injected create failure'):self.construct()
        self.assertEqual(sum(e[0]=='close_directory'for e in self.events),2)
        self.assertFalse(any(e[0]=='close_engine'for e in self.events))

    def test_missing_runtime_directory_fails_before_registration_or_DLL_load(self):
        self.runtime.rmdir();first,second=self.patches()
        with first,second,self.assertRaises(ValueError):self.construct()
        self.assertEqual(self.events,[])

    def test_cleanup_close_failure_is_explicit_and_retains_dependency_directories(self):
        library=FakeDLL(self.events,valid_timing=False)
        library.sl1012_close=Function(lambda handle:self.events.append(('close_engine',handle))or -1)
        first,second=self.patches(library)
        with first,second:
            with self.assertRaisesRegex(RuntimeError,'cleanup failed')as caught:self.construct()
            failure=caught.exception
            self.assertIs(failure.native_cleanup_complete,False)
            self.assertFalse(any(e[0]=='close_directory'for e in self.events))
            self.assertEqual(failure.resource_owner.handle,123)
            library.sl1012_close=Function(lambda handle:0)
            failure.resource_owner.close()
            self.assertEqual(sum(e[0]=='close_directory'for e in self.events),2)


if __name__=='__main__':unittest.main()
